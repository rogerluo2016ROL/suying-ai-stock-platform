#!/usr/bin/env python3
"""
构建商业航天复杂产业链 (8层复杂产业链模型)

链结构:
  L1 需求层    → 卫星互联网/遥感/太空旅游/国防航天
  L2 任务层    → 星座组网/火箭发射/卫星制造/地面运营
  L3 核心产品层 → 运载火箭/通信卫星/遥感卫星/地面终端
  L4 底层支撑层 → 火箭发动机/星载芯片/相控阵天线/能源系统
  L5 集成层    → 火箭总装/卫星平台/发射服务/测控系统
  L6 配套层    → 燃料/碳纤维/连接器/测试设备/精密加工
  L7 基础设施层 → 发射场/测控站/卫星地面站/在轨服务
  L8 商业变现层 → 发射服务收入/卫星数据/通信运营/遥感应用
"""

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'packages', 'kronos-factors'))
os.environ.setdefault('KRONOS_PG_URL', 'postgresql://kronos:kronos@localhost:6432/kronos')

import psycopg2
import psycopg2.extras
import json

THEME_ID = "future_industry_commercial_aerospace"
CHAIN_ID = "commercial_aerospace_complex_8layer"

# ═══ 8层节点定义 ═══
LAYERS = [
    {
        "level": "L1", "name": "需求层",
        "node_id": f"{CHAIN_ID}_demand",
        "keywords": ["卫星互联网", "遥感观测", "太空旅游", "国防航天", "低轨星座", "手机直连卫星"],
        "policy_weight": 5,
    },
    {
        "level": "L2", "name": "任务层",
        "node_id": f"{CHAIN_ID}_task",
        "keywords": ["星座组网", "火箭发射", "卫星制造", "地面运营", "频率申请", "轨道资源"],
        "policy_weight": 5,
    },
    {
        "level": "L3", "name": "核心产品层",
        "node_id": f"{CHAIN_ID}_core_product",
        "keywords": ["运载火箭", "通信卫星", "遥感卫星", "导航卫星", "地面终端", "卫星物联网终端"],
        "policy_weight": 8,
    },
    {
        "level": "L4", "name": "底层支撑层",
        "node_id": f"{CHAIN_ID}_foundation",
        "keywords": ["液体火箭发动机", "星载AI芯片", "相控阵天线", "星敏感器", "太阳能帆板", "星载计算机", "推进系统"],
        "policy_weight": 8,
    },
    {
        "level": "L5", "name": "集成层",
        "node_id": f"{CHAIN_ID}_integration",
        "keywords": ["火箭总装", "卫星平台集成", "发射服务", "测控系统", "一箭多星", "回收复用"],
        "policy_weight": 7,
    },
    {
        "level": "L6", "name": "配套层",
        "node_id": f"{CHAIN_ID}_supporting",
        "keywords": ["液体燃料", "碳纤维复合材料", "宇航级连接器", "测试设备", "精密加工", "热控材料", "密封件"],
        "policy_weight": 5,
    },
    {
        "level": "L7", "name": "基础设施层",
        "node_id": f"{CHAIN_ID}_infrastructure",
        "keywords": ["商业发射场", "测控站", "卫星地面站", "在轨服务", "空间站", "太空数据中心"],
        "policy_weight": 6,
    },
    {
        "level": "L8", "name": "商业变现层",
        "node_id": f"{CHAIN_ID}_commercialization",
        "keywords": ["发射服务收入", "卫星数据销售", "通信运营", "遥感应用", "太空旅游票务", "在轨服务费"],
        "policy_weight": 9,
    },
]

# ═══ 公司映射 ═══
# (code, node_id, product_name, confidence, status)
COMPANIES = [
    # ── L3 核心产品层 ──
    # 火箭
    ("600343", f"{CHAIN_ID}_core_product", "液体火箭发动机", 0.85, "verified"),
    ("003009", f"{CHAIN_ID}_core_product", "固体运载火箭", 0.85, "verified"),
    ("600879", f"{CHAIN_ID}_core_product", "航天电子/火箭配套", 0.80, "pending_review"),
    # 卫星
    ("600118", f"{CHAIN_ID}_core_product", "小卫星制造", 0.85, "verified"),
    ("603131", f"{CHAIN_ID}_core_product", "卫星结构件", 0.80, "pending_review"),
    # 地面终端
    ("002465", f"{CHAIN_ID}_core_product", "卫星通信终端", 0.85, "verified"),
    ("688311", f"{CHAIN_ID}_core_product", "卫星导航终端", 0.80, "pending_review"),
    ("300045", f"{CHAIN_ID}_core_product", "卫星应用终端", 0.80, "pending_review"),

    # ── L4 底层支撑层 ──
    ("001270", f"{CHAIN_ID}_foundation", "相控阵T/R芯片", 0.85, "verified"),
    ("688270", f"{CHAIN_ID}_foundation", "射频前端芯片", 0.80, "pending_review"),
    ("301050", f"{CHAIN_ID}_foundation", "毫米波相控阵天线", 0.85, "verified"),
    ("600562", f"{CHAIN_ID}_foundation", "相控阵天线系统", 0.80, "pending_review"),
    ("300762", f"{CHAIN_ID}_foundation", "星载电源管理", 0.80, "pending_review"),
    ("300456", f"{CHAIN_ID}_foundation", "MEMS陀螺/星敏感器", 0.85, "verified"),
    ("688002", f"{CHAIN_ID}_foundation", "红外探测器/星载光电", 0.80, "pending_review"),
    ("300627", f"{CHAIN_ID}_foundation", "高精度导航芯片", 0.80, "pending_review"),

    # ── L5 集成层 ──
    ("000901", f"{CHAIN_ID}_integration", "火箭总装/航天系统集成", 0.85, "verified"),
    ("600118", f"{CHAIN_ID}_integration", "卫星平台集成", 0.85, "verified"),
    ("600879", f"{CHAIN_ID}_integration", "航天电子系统集成", 0.80, "pending_review"),

    # ── L6 配套层 ──
    ("300699", f"{CHAIN_ID}_supporting", "碳纤维复合材料", 0.85, "verified"),
    ("688295", f"{CHAIN_ID}_supporting", "宇航级碳纤维", 0.85, "verified"),
    ("002025", f"{CHAIN_ID}_supporting", "宇航级连接器", 0.85, "verified"),
    ("300034", f"{CHAIN_ID}_supporting", "高温合金/精密铸造", 0.80, "pending_review"),
    ("002149", f"{CHAIN_ID}_supporting", "钛合金/航天材料", 0.85, "verified"),
    ("300855", f"{CHAIN_ID}_supporting", "高温合金精密铸造", 0.80, "pending_review"),
    ("688333", f"{CHAIN_ID}_supporting", "3D打印/航天零部件", 0.80, "pending_review"),
    ("300489", f"{CHAIN_ID}_supporting", "精密光学加工", 0.80, "pending_review"),

    # ── L7 基础设施层 ──
    ("601698", f"{CHAIN_ID}_infrastructure", "卫星地面站/测控", 0.85, "verified"),
    ("600118", f"{CHAIN_ID}_infrastructure", "卫星地面应用系统", 0.80, "pending_review"),
    ("600879", f"{CHAIN_ID}_infrastructure", "航天测控系统", 0.80, "pending_review"),

    # ── L8 商业变现层 ──
    ("601698", f"{CHAIN_ID}_commercialization", "卫星通信运营", 0.85, "verified"),
    ("688066", f"{CHAIN_ID}_commercialization", "遥感数据服务", 0.85, "verified"),
    ("688568", f"{CHAIN_ID}_commercialization", "数字地球/遥感平台", 0.85, "verified"),
    ("300342", f"{CHAIN_ID}_commercialization", "卫星互联网终端", 0.80, "pending_review"),
    ("002465", f"{CHAIN_ID}_commercialization", "卫星通信服务", 0.80, "pending_review"),
]


def build_chain():
    pg = psycopg2.connect(os.environ['KRONOS_PG_URL'])
    cur = pg.cursor()

    # ── 1. 创建 theme 级 chain_nodes (L0) ──
    print("1. 创建链主题节点...")
    cur.execute("""
        INSERT INTO chain_nodes (node_id, theme_id, node_name, layer, parent_node_id,
                                 upstream_nodes, downstream_nodes, value_chain, competition)
        VALUES (%s, %s, %s, %s, NULL, NULL, NULL, %s, %s)
        ON CONFLICT (node_id) DO UPDATE SET
            theme_id = EXCLUDED.theme_id, node_name = EXCLUDED.node_name, layer = EXCLUDED.layer,
            value_chain = EXCLUDED.value_chain, competition = EXCLUDED.competition
    """, (
        CHAIN_ID,
        THEME_ID,
        "商业航天",
        0,
        psycopg2.extras.Json({"chain_id": CHAIN_ID, "note": "商业航天复杂产业链8层节点", "theme": "商业航天/低轨星座/卫星互联网"}),
        psycopg2.extras.Json({"status": "pending_evidence_review", "note": "竞争格局需公告/研报补证"}),
    ))
    print(f"   ✅ {CHAIN_ID}")

    # ── 2. 创建 8 层 BOM 节点 ──
    print("2. 创建8层BOM节点...")
    for layer in LAYERS:
        cur.execute("""
            INSERT INTO supply_chain_bom_nodes (node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE SET
                theme_id = EXCLUDED.theme_id, parent_node_id = EXCLUDED.parent_node_id,
                level = EXCLUDED.level, name = EXCLUDED.name, node_type = EXCLUDED.node_type,
                keywords = EXCLUDED.keywords, policy_weight = EXCLUDED.policy_weight
        """, (
            layer["node_id"],
            THEME_ID,
            "aerospace",
            CHAIN_ID if layer["level"] == "L1" else LAYERS[int(layer["level"][1]) - 2]["node_id"],
            layer["level"],
            layer["name"],
            "complex_chain_layer",
            psycopg2.extras.Json(layer["keywords"]),
            layer["policy_weight"],
        ))
        print(f"   ✅ {layer['level']} {layer['name']} [{layer['node_id']}]")

    # ── 3. 创建边关系 ──
    print("3. 创建层级连接...")
    for i in range(len(LAYERS) - 1):
        # Skip existing edges
        cur.execute("SELECT 1 FROM supply_chain_bom_edges WHERE from_node_id=%s AND to_node_id=%s",
                     (LAYERS[i]["node_id"], LAYERS[i+1]["node_id"]))
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO supply_chain_bom_edges (edge_id, from_node_id, to_node_id, relation)
                VALUES (%s, %s, %s, %s)
            """, (
            f"{CHAIN_ID}_edge_L{i+1}_to_L{i+2}",
            LAYERS[i]["node_id"],
            LAYERS[i + 1]["node_id"],
            "8层复杂产业链顺序链路",
        ))
    print(f"   ✅ {len(LAYERS)-1} 条边")

    # ── 4. 映射公司 ──
    print("4. 映射公司...")
    mapped = 0
    for code, node_id, product_name, confidence, status in COMPANIES:
        # Verify stock exists
        cur.execute("SELECT name, industry FROM stocks WHERE code = %s", (code,))
        stock = cur.fetchone()
        if not stock:
            print(f"   ⚠️ {code} 未找到, 跳过")
            continue

        # Check existing
        cur.execute("SELECT mapping_id FROM company_bom_mapping WHERE code=%s AND node_id=%s", (code, node_id))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE company_bom_mapping SET product_name=%s, confidence=%s, status=%s, updated_at=NOW()
                WHERE mapping_id=%s
            """, (product_name, confidence, status, existing[0]))
        else:
            cur.execute("""
                INSERT INTO company_bom_mapping (mapping_id, code, node_id, product_name, confidence, status, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (f"{CHAIN_ID}_{code}_{node_id.split('_')[-1]}", code, node_id, product_name, confidence, status))
        mapped += 1

    # ── 5. 同步到 company_chain_mapping ──
    print("5. 同步主链映射...")
    for code, node_id, product_name, confidence, status in COMPANIES:
        if status != 'verified':
            continue
        cur.execute("SELECT 1 FROM company_chain_mapping WHERE code=%s AND node_id=%s", (code, CHAIN_ID))
        if not cur.fetchone():
            try:
                cur.execute("""
                    INSERT INTO company_chain_mapping (code, node_id, main_pct, evidence, created_at)
                    VALUES (%s, %s, 100.0, %s, NOW())
                """, (code, CHAIN_ID,
                      psycopg2.extras.Json({"source": "company_bom_mapping", "chain": CHAIN_ID, "product": product_name})))
            except Exception:
                pass  # skip if constraint violation
    print(f"   ✅ 完成")

    pg.commit()
    cur.close()
    pg.close()

    print(f"\n{'='*60}")
    print(f"  商业航天产业链构建完成!")
    print(f"{'='*60}")
    print(f"  Theme: {THEME_ID}")
    print(f"  层级: 8层 ({len(LAYERS)}个BOM节点)")
    print(f"  映射公司: {mapped}条")
    print(f"  覆盖股票: {len(set(c[0] for c in COMPANIES))}只")


if __name__ == "__main__":
    build_chain()
    print("\n验证命令:")
    print(f"  SELECT COUNT(*) FROM supply_chain_bom_nodes WHERE theme_id='{THEME_ID}';")
    print(f"  SELECT COUNT(*) FROM company_bom_mapping WHERE node_id LIKE '{CHAIN_ID}%';")
