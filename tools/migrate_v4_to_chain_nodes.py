#!/usr/bin/env python3
"""数据迁移脚本: V4节点到chain_nodes表.

从两个数据源迁移V4产业节点数据:
  1. V4 JSON配置: packages/kronos-factors/configs/supply_chain_bom_v4.json
  2. PG V4表: supply_chain_bom_nodes

迁移目标:
  - industry_themes: 先填充主题表 (FK依赖)
  - chain_nodes: 填充节点表

字段映射规则:
  - V4 'level' ('chain'/'component') → 'layer' (int: chain=1, component=2)
  - V4 'name' → 'node_name'
  - V4 'keywords'/'chain_id'/'node_type' → value_chain JSONB字段 (保留扩展信息)

Usage:
    # 正常执行 (写入数据库)
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/migrate_v4_to_chain_nodes.py

    # dry-run模式 (只预览,不写入)
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/migrate_v4_to_chain_nodes.py --dry-run

验收标准:
    AC-1: 迁移脚本读取V4 JSON配置 + PG V4表数据
    AC-2: 每个节点补充chokepoint_level默认值'普通' (存入value_chain JSONB)
    AC-3: 迁移后chain_nodes表行数>=V4行数 (>=4节点)
    AC-4: FK一致性验证: theme_id存在
    AC-5: 脚本支持dry-run模式预览
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")

# V4 JSON配置路径
V4_CONFIG_PATH = PROJ / "packages/kronos-factors/configs/supply_chain_bom_v4.json"

# 输出日志路径
LOG_PATH = PROJ / "outputs/migration_v4_to_chain.log"


def parse_args():
    """解析命令行参数."""
    parser = argparse.ArgumentParser(description="迁移V4节点到chain_nodes表")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式: 不写入数据库,只打印将要执行的操作")
    parser.add_argument("--force-json", action="store_true",
                        help="强制只使用JSON配置,忽略PG V4表数据")
    parser.add_argument("--force-pg", action="store_true",
                        help="强制只使用PG V4表数据,忽略JSON配置")
    return parser.parse_args()


def load_v4_json_config():
    """加载V4 JSON配置文件."""
    if not V4_CONFIG_PATH.exists():
        raise FileNotFoundError(f"V4配置文件不存在: {V4_CONFIG_PATH}")

    with open(V4_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    return config


def fetch_pg_v4_nodes(conn):
    """从PG supply_chain_bom_nodes表读取现有数据."""
    cur = conn.cursor()
    cur.execute("""
        SELECT node_id, theme_id, chain_id, parent_node_id, level, name,
               node_type, keywords, policy_weight
        FROM supply_chain_bom_nodes
        ORDER BY node_id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def level_to_layer(level: str) -> int:
    """V4 level字符串转换为layer整数.

    映射规则:
      - 'chain' → 1 (产业链根节点)
      - 'component' → 2 (零部件层)

    PRD设计: 产业链拆解树包含5层:
      1. 原材料
      2. 核心零部件
      3. 制造
      4. 渠道
      5. 终端应用

    V4的'chain'对应产业根节点(layer=1), 'component'对应零部件(layer=2).
    """
    level_map = {
        "chain": 1,
        "component": 2,
    }
    return level_map.get(level, 1)


def prepare_themes_from_json(config):
    """从V4 JSON配置提取themes数据."""
    themes = []
    for t in config.get("themes", []):
        themes.append({
            "theme_id": t["theme_id"],
            "theme_name": t["name"],
            "category": "战新",  # V4配置中的主题都属于战新产业
            "key_directions": json.dumps(t.get("keywords", [])),
            "policy_intensity_stars": 3,  # 默认3星
        })
    return themes


def prepare_nodes_from_json(config):
    """从V4 JSON配置提取nodes数据."""
    nodes = []
    for n in config.get("nodes", []):
        # 构建value_chain JSONB (存储V4额外字段)
        value_chain = {
            "chain_id": n.get("chain_id"),
            "node_type": n.get("node_type"),
            "keywords": n.get("keywords", []),
            "policy_weight": n.get("policy_weight", 1.0),
            "chokepoint_level": "普通",  # AC-2: 默认值
        }

        nodes.append({
            "node_id": n["node_id"],
            "theme_id": n["theme_id"],
            "node_name": n["name"],
            "layer": level_to_layer(n.get("level", "chain")),
            "parent_node_id": n.get("parent_node_id"),
            "upstream_nodes": None,
            "downstream_nodes": None,
            "value_chain": json.dumps(value_chain),
            "competition": None,
        })
    return nodes


def prepare_nodes_from_pg(pg_rows):
    """从PG V4表数据转换为chain_nodes格式."""
    nodes = []
    for row in pg_rows:
        node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight = row

        # 构建value_chain JSONB
        keywords_list = keywords if isinstance(keywords, list) else []
        value_chain = {
            "chain_id": chain_id,
            "node_type": node_type,
            "keywords": keywords_list,
            "policy_weight": float(policy_weight) if policy_weight else 1.0,
            "chokepoint_level": "普通",  # AC-2: 默认值
        }

        nodes.append({
            "node_id": node_id,
            "theme_id": theme_id,
            "node_name": name,
            "layer": level_to_layer(level),
            "parent_node_id": parent_node_id,
            "upstream_nodes": None,
            "downstream_nodes": None,
            "value_chain": json.dumps(value_chain),
            "competition": None,
        })
    return nodes


def merge_nodes(json_nodes, pg_nodes):
    """合并JSON和PG节点数据 (去重,优先JSON)."""
    # 以node_id为key,JSON配置优先
    merged = {}
    for n in json_nodes:
        merged[n["node_id"]] = n
    for n in pg_nodes:
        if n["node_id"] not in merged:
            merged[n["node_id"]] = n
    return list(merged.values())


def check_themes_exist(conn, theme_ids):
    """验证FK: 检查themes是否存在于industry_themes表."""
    cur = conn.cursor()
    existing = set()
    for tid in theme_ids:
        cur.execute("SELECT 1 FROM industry_themes WHERE theme_id = %s", (tid,))
        if cur.fetchone():
            existing.add(tid)
    cur.close()
    return existing


def insert_themes(conn, themes, dry_run=False):
    """插入themes到industry_themes表."""
    if dry_run:
        print("\n[DRY-RUN] 将插入以下themes到industry_themes表:")
        for t in themes:
            print(f"  - theme_id: {t['theme_id']}, theme_name: {t['theme_name']}")
        return len(themes)

    cur = conn.cursor()
    count = 0
    for t in themes:
        cur.execute("""
            INSERT INTO industry_themes (theme_id, theme_name, category, key_directions, policy_intensity_stars)
            VALUES (%s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (theme_id) DO UPDATE SET
                theme_name = EXCLUDED.theme_name,
                category = EXCLUDED.category,
                key_directions = EXCLUDED.key_directions,
                policy_intensity_stars = EXCLUDED.policy_intensity_stars
        """, (t["theme_id"], t["theme_name"], t["category"], t["key_directions"], t["policy_intensity_stars"]))
        count += 1
    conn.commit()
    cur.close()
    return count


def insert_nodes(conn, nodes, dry_run=False):
    """插入nodes到chain_nodes表."""
    if dry_run:
        print("\n[DRY-RUN] 将插入以下nodes到chain_nodes表:")
        for n in nodes:
            print(f"  - node_id: {n['node_id']}, node_name: {n['node_name']}, layer: {n['layer']}, parent: {n.get('parent_node_id')}")
        return len(nodes)

    cur = conn.cursor()
    count = 0

    # 先插入没有parent的根节点
    root_nodes = [n for n in nodes if not n.get("parent_node_id")]
    child_nodes = [n for n in nodes if n.get("parent_node_id")]

    for n in root_nodes:
        cur.execute("""
            INSERT INTO chain_nodes (node_id, theme_id, node_name, layer, parent_node_id,
                                     upstream_nodes, downstream_nodes, value_chain, competition)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id = EXCLUDED.theme_id,
                node_name = EXCLUDED.node_name,
                layer = EXCLUDED.layer,
                parent_node_id = EXCLUDED.parent_node_id,
                value_chain = EXCLUDED.value_chain
        """, (n["node_id"], n["theme_id"], n["node_name"], n["layer"], n["parent_node_id"],
              n["upstream_nodes"], n["downstream_nodes"], n["value_chain"], n["competition"]))
        count += 1
    conn.commit()

    # 再插入有parent的子节点 (此时parent已存在,FK约束满足)
    for n in child_nodes:
        cur.execute("""
            INSERT INTO chain_nodes (node_id, theme_id, node_name, layer, parent_node_id,
                                     upstream_nodes, downstream_nodes, value_chain, competition)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id = EXCLUDED.theme_id,
                node_name = EXCLUDED.node_name,
                layer = EXCLUDED.layer,
                parent_node_id = EXCLUDED.parent_node_id,
                value_chain = EXCLUDED.value_chain
        """, (n["node_id"], n["theme_id"], n["node_name"], n["layer"], n["parent_node_id"],
              n["upstream_nodes"], n["downstream_nodes"], n["value_chain"], n["competition"]))
        count += 1
    conn.commit()
    cur.close()
    return count


def verify_migration(conn):
    """验证迁移结果."""
    cur = conn.cursor()

    # 检查industry_themes行数
    cur.execute("SELECT COUNT(*) FROM industry_themes")
    themes_count = cur.fetchone()[0]

    # 检查chain_nodes行数
    cur.execute("SELECT COUNT(*) FROM chain_nodes")
    nodes_count = cur.fetchone()[0]

    # 检查FK一致性: 所有chain_nodes的theme_id都存在于industry_themes
    cur.execute("""
        SELECT cn.node_id, cn.theme_id
        FROM chain_nodes cn
        WHERE cn.theme_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM industry_themes it WHERE it.theme_id = cn.theme_id)
    """)
    fk_errors = cur.fetchall()

    # 检查FK一致性: 所有parent_node_id都存在
    cur.execute("""
        SELECT cn.node_id, cn.parent_node_id
        FROM chain_nodes cn
        WHERE cn.parent_node_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM chain_nodes pn WHERE pn.node_id = cn.parent_node_id)
    """)
    parent_errors = cur.fetchall()

    cur.close()

    return {
        "themes_count": themes_count,
        "nodes_count": nodes_count,
        "fk_theme_errors": fk_errors,
        "fk_parent_errors": parent_errors,
    }


def write_log(log_content):
    """写入迁移日志."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write(log_content)


def main():
    args = parse_args()

    # 初始化日志
    log_lines = []
    log_lines.append(f"=== V4节点迁移日志 ===")
    log_lines.append(f"时间: {datetime.now().isoformat()}")
    log_lines.append(f"dry_run: {args.dry_run}")
    log_lines.append(f"")

    # 连接数据库
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    conn = psycopg2.connect(pg_url)

    # 1. 加载V4 JSON配置
    log_lines.append("[AC-1] 加载V4 JSON配置...")
    try:
        v4_config = load_v4_json_config()
        log_lines.append(f"  - JSON配置加载成功: {len(v4_config.get('themes', []))} themes, {len(v4_config.get('nodes', []))} nodes")
        print(f"[AC-1] 加载V4 JSON配置: {len(v4_config.get('nodes', []))} nodes from {V4_CONFIG_PATH}")
    except FileNotFoundError as e:
        log_lines.append(f"  - 错误: {e}")
        print(f"[ERROR] {e}")
        sys.exit(1)

    # 2. 读取PG V4表数据
    log_lines.append("[AC-1] 读取PG supply_chain_bom_nodes表...")
    pg_nodes_raw = fetch_pg_v4_nodes(conn)
    log_lines.append(f"  - PG表读取成功: {len(pg_nodes_raw)} rows")
    print(f"[AC-1] 读取PG supply_chain_bom_nodes: {len(pg_nodes_raw)} rows")

    # 3. 准备themes数据
    themes = prepare_themes_from_json(v4_config)
    log_lines.append(f"[准备] themes数据: {len(themes)} 条")
    print(f"[准备] themes数据: {len(themes)} 条")

    # 4. 准备nodes数据
    json_nodes = prepare_nodes_from_json(v4_config)
    pg_nodes = prepare_nodes_from_pg(pg_nodes_raw)

    if args.force_json:
        final_nodes = json_nodes
        log_lines.append(f"  - 强制JSON模式: 只使用JSON配置 ({len(json_nodes)} nodes)")
    elif args.force_pg:
        final_nodes = pg_nodes
        log_lines.append(f"  - 强制PG模式: 只使用PG表数据 ({len(pg_nodes)} nodes)")
    else:
        final_nodes = merge_nodes(json_nodes, pg_nodes)
        log_lines.append(f"  - 合并模式: JSON {len(json_nodes)} + PG {len(pg_nodes)} → 合并后 {len(final_nodes)} nodes (去重)")

    print(f"[准备] nodes数据: {len(final_nodes)} 条")

    # AC-2验证: 检查所有节点都有chokepoint_level
    for n in final_nodes:
        vc = json.loads(n["value_chain"])
        assert vc.get("chokepoint_level") == "普通", f"[AC-2 FAIL] {n['node_id']} 缺少chokepoint_level"
    log_lines.append(f"[AC-2] 所有节点已补充chokepoint_level='普通'")
    print(f"[AC-2] 所有节点已补充chokepoint_level='普通'")

    # AC-3验证: 检查节点数>=4
    assert len(final_nodes) >= 4, f"[AC-3 FAIL] 节点数 {len(final_nodes)} < 4"
    log_lines.append(f"[AC-3] 节点数 {len(final_nodes)} >= 4 ✓")
    print(f"[AC-3] 节点数 {len(final_nodes)} >= 4 ✓")

    # 5. 插入themes (先满足FK依赖)
    themes_inserted = insert_themes(conn, themes, dry_run=args.dry_run)
    log_lines.append(f"[插入] industry_themes: {themes_inserted} 条")
    print(f"[插入] industry_themes: {themes_inserted} 条")

    # 6. 插入nodes
    nodes_inserted = insert_nodes(conn, final_nodes, dry_run=args.dry_run)
    log_lines.append(f"[插入] chain_nodes: {nodes_inserted} 条")
    print(f"[插入] chain_nodes: {nodes_inserted} 条")

    # 7. 验证迁移结果
    if not args.dry_run:
        log_lines.append(f"[验证] 开始验证...")
        result = verify_migration(conn)
        log_lines.append(f"  - industry_themes行数: {result['themes_count']}")
        log_lines.append(f"  - chain_nodes行数: {result['nodes_count']}")
        log_lines.append(f"  - FK theme_id错误: {len(result['fk_theme_errors'])}")
        log_lines.append(f"  - FK parent_node_id错误: {len(result['fk_parent_errors'])}")

        print(f"\n[验证结果]")
        print(f"  - industry_themes: {result['themes_count']} rows")
        print(f"  - chain_nodes: {result['nodes_count']} rows")

        # AC-4验证: FK一致性
        if result['fk_theme_errors']:
            log_lines.append(f"[AC-4 FAIL] FK theme_id不一致: {result['fk_theme_errors']}")
            print(f"[AC-4 FAIL] FK theme_id不一致: {result['fk_theme_errors']}")
            sys.exit(1)
        else:
            log_lines.append(f"[AC-4] FK theme_id一致性验证通过 ✓")
            print(f"[AC-4] FK theme_id一致性验证通过 ✓")

        if result['fk_parent_errors']:
            log_lines.append(f"[AC-4 FAIL] FK parent_node_id不一致: {result['fk_parent_errors']}")
            print(f"[AC-4 FAIL] FK parent_node_id不一致: {result['fk_parent_errors']}")
            sys.exit(1)
        else:
            log_lines.append(f"[AC-4] FK parent_node_id一致性验证通过 ✓")
            print(f"[AC-4] FK parent_node_id一致性验证通过 ✓")
    else:
        log_lines.append(f"[DRY-RUN] 跳过验证 (未写入数据库)")
        print(f"\n[DRY-RUN] 跳过验证 - 使用 --dry-run 模式未写入数据库")

    # 8. 写入日志
    log_lines.append(f"\n迁移完成.")
    write_log("\n".join(log_lines))
    print(f"\n日志已写入: {LOG_PATH}")

    conn.close()

    # AC-5: 支持dry-run模式
    print(f"[AC-5] dry-run模式支持 ✓")


if __name__ == "__main__":
    main()