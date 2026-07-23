#!/usr/bin/env python3
"""近存计算链 — chain_nodes 8 层节点 value_chain/competition 数据驱动升级.

把 materialize 时手填的「人工估计」替换为可复算的规则化结果:

  margin        = 该层 status='verified' 映射公司最新报告期 gross_margin
                  (financial_indicator 表) 按映射 confidence 加权平均
  pricing_power = 毛利率分档 (>=50→5, 35-50→4, 20-35→3, 10-20→2, <10→1)
                  + 该层 approved 证据 >=20 条再 +1, 封顶 5
  value_added   = 50 + (margin - 8 层 margin 中位数), 截断 [5, 95]
                  (相对全链中位数的差值定位, 项目引擎按 % 消费)
  concentration = 仅 supporting 层抽到导源数字 (拓荆互动易 2026-07 引 Gartner:
                  AMAT/Lam/TEL 合计占全球 CVD 市场约 70% 份额), 其余层保留人工
                  估计值, note 标注"估计(无研报导源数据)"并附定性龙头证据
  leader_share  = 各层均未抽到可靠数字, 保留人工估计, note 同上
  barrier       = 2 + (concentration>=60) + (concentration>=85)
                  + (该层 NMC 证据中 认证/唯一/独家/进入供应链/国产替代 命中 >=3)
                  + (命中 >=10), 截断 [1,5]
  threat        = 保留人工判断文本; supporting 层补充互动易垄断证据

只 UPDATE theme_id='future_industry_near_memory_computing' 下 8 个层节点的
value_chain / competition 两个 jsonb 字段; 根节点与其他链不动。

Usage:
  python tools/near_memory_chain_node_metrics.py            # dry-run, 只打印
  python tools/near_memory_chain_node_metrics.py --apply    # 写库
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import psycopg2
import psycopg2.extras

DEFAULT_DSN = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
THEME_ID = "future_industry_near_memory_computing"
CHAIN_ID = "near_memory_computing"

LAYERS = [
    "demand", "task", "core_product", "foundation",
    "integration", "supporting", "infrastructure", "commercialization",
]
NODE = {layer: f"near_memory_computing_{layer}" for layer in LAYERS}

MOAT_KW = ["认证", "唯一", "独家", "进入供应链", "客户验证", "国产替代"]
PP_EVIDENCE_BONUS_THRESHOLD = 20

# 各层定性龙头/份额证据 (来自本地库检索, 写入 note 佐证; 具体见下方 SQL 复查)
QUALITATIVE_EVIDENCE = {
    "demand": "东莞证券2025-09-04称浪潮信息「服务器龙头地位稳固」; 中邮证券2024-06-07称工业富联「算力龙头」",
    "task": "太平洋证券2025-09-23深度报告「澜起科技: 全球内存接口芯片龙头」; 东海证券2026-05-20「全球互连芯片龙头」",
    "core_product": "太平洋证券2025-12-26称兆易「存储+MCU国内龙头」; 爱建证券2026-05-07称江波龙「国产存储模组龙头」",
    "foundation": "民生证券2025-01-24称兆易「存储龙头, 聚焦利基市场」",
    "integration": "国金证券2024-09-10称长电「国内龙头平台型封测厂」",
    "supporting": "互动易2026-07拓荆董秘引Gartner: AMAT/Lam/TEL合计占全球CVD市场约70%份额; 开源证券2024-07-17「CMP龙头(华海清科)市占率加速渗透」",
    "infrastructure": "太平洋证券2025-09-23「澜起: 全球内存接口芯片龙头」",
    "commercialization": "爱建证券2026-05-07「江波龙: 国产存储模组龙头进入业绩爆发期」; 东吴证券2025-12-02「佰维: 端侧AI存储核心标的」",
}
# supporting 层唯一抽到的导源数字 (来源见 QUALITATIVE_EVIDENCE["supporting"])
DATA_DRIVEN_CONCENTRATION = {"supporting": 70}


def pricing_power_base(margin: float) -> int:
    if margin >= 50:
        return 5
    if margin >= 35:
        return 4
    if margin >= 20:
        return 3
    if margin >= 10:
        return 2
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="近存计算链节点指标数据驱动升级")
    parser.add_argument("--pg-url", default=DEFAULT_DSN)
    parser.add_argument("--apply", action="store_true", help="实际 UPDATE (默认 dry-run)")
    args = parser.parse_args()

    conn = psycopg2.connect(args.pg_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ── 现状 SELECT (确认范围: 恰好 9 行 = 根 + 8 层) ──
    cur.execute("SELECT node_id, value_chain, competition FROM chain_nodes WHERE theme_id = %s ORDER BY node_id", (THEME_ID,))
    current = {r["node_id"]: r for r in cur.fetchall()}
    layer_ids = [NODE[l] for l in LAYERS]
    missing = [n for n in layer_ids if n not in current]
    if missing:
        print(f"❌ 缺少层节点: {missing}"); return 1
    print(f"范围确认: theme 下 {len(current)} 个节点, 将更新 8 个层节点 (根节点 {THEME_ID.split('_')[-1]} 不动)\n")

    # ── 1) 各层 verified 公司最新毛利率 (confidence 加权) ──
    cur.execute(
        """
        SELECT DISTINCT ON (m.node_id, m.code)
               m.node_id, m.code, s.name, m.confidence, f.gross_margin, f.end_date
        FROM business_tag_mapping m
        LEFT JOIN stocks s ON s.code = split_part(m.code, '.', 1)
        LEFT JOIN LATERAL (
            SELECT gross_margin, end_date FROM financial_indicator fi
            WHERE fi.code = split_part(m.code, '.', 1) AND fi.gross_margin IS NOT NULL
            ORDER BY fi.end_date DESC LIMIT 1
        ) f ON true
        WHERE m.chain_id = %s AND m.status = 'verified'
        ORDER BY m.node_id, m.code
        """,
        (CHAIN_ID,),
    )
    rows = cur.fetchall()
    layer_companies: dict[str, list[dict]] = {l: [] for l in LAYERS}
    for r in rows:
        layer = str(r["node_id"]).replace("near_memory_computing_", "")
        layer_companies.setdefault(layer, []).append(dict(r))

    # ── 2) 各层 NMC 证据统计 (approved 数 / 卡脖子词频) ──
    cur.execute(
        """
        SELECT node_id,
               count(*) FILTER (WHERE review_status='approved') AS approved,
               count(*) FILTER (WHERE strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '认证') > 0
                                  OR strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '唯一') > 0
                                  OR strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '独家') > 0
                                  OR strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '进入供应链') > 0
                                  OR strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '客户验证') > 0
                                  OR strpos(coalesce(title,'') || ' ' || coalesce(excerpt,''), '国产替代') > 0) AS moat_hits
        FROM business_tag_evidence_events
        WHERE event_id LIKE 'NMC-EV-%'
        GROUP BY node_id
        """
    )
    ev_stat = {str(r["node_id"]): {"approved": int(r["approved"]), "moat_hits": int(r["moat_hits"])} for r in cur.fetchall()}

    # ── 3) 逐层计算并打印 ──
    margins: dict[str, float] = {}
    detail: dict[str, dict] = {}
    print("═══ 毛利率计算 (financial_indicator, confidence 加权) ═══")
    for layer in LAYERS:
        comps = layer_companies.get(layer, [])
        with_data = [c for c in comps if c.get("gross_margin") is not None]
        no_data = [c for c in comps if c.get("gross_margin") is None]
        if with_data:
            wsum = sum(float(c["gross_margin"]) * float(c["confidence"]) for c in with_data)
            wtot = sum(float(c["confidence"]) for c in with_data)
            margin = round(wsum / wtot, 1)
        else:
            margin = None
        margins[layer] = margin
        sample = "/".join(f"{c['name'] or c['code']}{float(c['gross_margin']):.1f}" for c in with_data)
        periods = sorted({str(c["end_date"]) for c in with_data})
        print(f"  [{layer}] verified {len(comps)} 家, 有数据 {len(with_data)} 家 "
              f"({sample}) 报告期 {periods}"
              + (f", 缺数据: {'/'.join(c['name'] or c['code'] for c in no_data)}" if no_data else "")
              + f" → margin={margin}")
        detail[layer] = {"with_data": with_data, "no_data": no_data, "sample": sample, "periods": periods}

    valid_margins = sorted(m for m in margins.values() if m is not None)
    mid = len(valid_margins) // 2
    median = (valid_margins[mid - 1] + valid_margins[mid]) / 2 if len(valid_margins) % 2 == 0 else valid_margins[mid]
    print(f"\n全链 margin 中位数 = {median:.1f} (样本 {[round(m,1) for m in valid_margins]})\n")

    updates: dict[str, dict] = {}
    print("═══ 定价权 / 附加值 / 壁垒规则计算 ═══")
    for layer in LAYERS:
        node_id = NODE[layer]
        old_vc = current[node_id]["value_chain"] or {}
        old_comp = current[node_id]["competition"] or {}
        margin = margins[layer]
        ev = ev_stat.get(node_id, {"approved": 0, "moat_hits": 0})

        if margin is None:
            # 无数据层: 保留旧值, 只改 note
            pp, va = old_vc.get("pricing_power"), old_vc.get("value_added")
            print(f"  [{layer}] 无毛利率数据, 保留旧值")
        else:
            pp = pricing_power_base(margin)
            bonus = 1 if ev["approved"] >= PP_EVIDENCE_BONUS_THRESHOLD else 0
            pp_final = min(5, pp + bonus)
            va = max(5, min(95, round(50 + (margin - median))))
            print(f"  [{layer}] margin={margin} → pp基础档={pp}, approved={ev['approved']}"
                  f"{'(>=20,+1)' if bonus else ''} → pricing_power={pp_final}; "
                  f"value_added=50+({margin}-{median:.1f})={va}")
            pp = pp_final

        concentration = DATA_DRIVEN_CONCENTRATION.get(layer, old_comp.get("concentration"))
        leader_share = old_comp.get("leader_share")
        conc_bonus = (1 if (concentration or 0) >= 60 else 0) + (1 if (concentration or 0) >= 85 else 0)
        moat_bonus = (1 if ev["moat_hits"] >= 3 else 0) + (1 if ev["moat_hits"] >= 10 else 0)
        barrier = max(1, min(5, 2 + conc_bonus + moat_bonus))
        print(f"          concentration={concentration}"
              f"{'(数据驱动: Gartner)' if layer in DATA_DRIVEN_CONCENTRATION else '(保留估计)'}, "
              f"moat_hits={ev['moat_hits']} → barrier=2+{conc_bonus}+{moat_bonus}={barrier}")

        # note 组装
        if margin is not None:
            vc_note = (
                f"数据驱动: {len(detail[layer]['with_data'])}家公司"
                f"{'/'.join(p[:7] for p in detail[layer]['periods'])}毛利率加权均值"
                f"({detail[layer]['sample']})"
            )
            if detail[layer]["no_data"]:
                vc_note += f"; 覆盖{len(detail[layer]['with_data'])}/{len(detail[layer]['with_data']) + len(detail[layer]['no_data'])}家" \
                           f"(缺: {'/'.join(c['name'] or c['code'] for c in detail[layer]['no_data'])})"
            vc_note += (f"; 定价权=毛利率{margin}%分档"
                        f"{'+证据加成' if margin is not None and ev['approved'] >= PP_EVIDENCE_BONUS_THRESHOLD else ''}; "
                        f"附加值=相对全链中位{median:.1f}%定位")
        else:
            vc_note = "估计(financial_indicator 无该层公司数据): " + str(old_vc.get("note", "")).replace("人工估计: ", "")

        if layer in DATA_DRIVEN_CONCENTRATION:
            comp_note = "数据驱动: " + QUALITATIVE_EVIDENCE[layer]
        else:
            comp_note = f"估计(无研报导源数据); 定性证据: {QUALITATIVE_EVIDENCE[layer]}"
        comp_note += f"; 壁垒=集中度+证据词频规则(moat命中{ev['moat_hits']}条)"

        threat = str(old_comp.get("threat") or "")
        if layer == "supporting" and "互动易" not in threat:
            threat += "; 互动易2026-07拓荆称三维集成(混合键合)由EVG/TEL高度垄断"

        updates[node_id] = {
            "value_chain": {
                "margin": margin if margin is not None else old_vc.get("margin"),
                "pricing_power": pp,
                "value_added": va if margin is not None else old_vc.get("value_added"),
                "note": vc_note,
            },
            "competition": {
                "concentration": concentration,
                "leader_share": leader_share,
                "barrier": barrier,
                "threat": threat,
                "note": comp_note,
            },
        }

    print("\n═══ 最终值预览 ═══")
    for layer in LAYERS:
        node_id = NODE[layer]
        u = updates[node_id]
        print(f"  [{layer}] vc={json.dumps(u['value_chain'], ensure_ascii=False)}")
        print(f"  {' ' * (len(layer) + 3)}comp={json.dumps(u['competition'], ensure_ascii=False)}")

    if not args.apply:
        print("\ndry-run, 未写库。加 --apply 执行 UPDATE。")
        conn.close()
        return 0

    # ── 写库前再次 SELECT 确认影响行数 ──
    cur.execute(
        "SELECT count(*) AS c FROM chain_nodes WHERE theme_id = %s AND node_id = ANY(%s)",
        (THEME_ID, list(updates.keys())),
    )
    cnt = int(cur.fetchone()["c"])
    print(f"\nUPDATE 范围确认: {cnt} 行 (预期 8)")
    if cnt != 8:
        print("❌ 行数不符, 中止"); conn.close(); return 1

    for node_id, u in updates.items():
        cur.execute(
            """
            UPDATE chain_nodes
            SET value_chain = %s::jsonb, competition = %s::jsonb
            WHERE theme_id = %s AND node_id = %s
            """,
            (json.dumps(u["value_chain"], ensure_ascii=False),
             json.dumps(u["competition"], ensure_ascii=False),
             THEME_ID, node_id),
        )
    conn.commit()
    print(f"✅ 已更新 {len(updates)} 个层节点的 value_chain/competition")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
