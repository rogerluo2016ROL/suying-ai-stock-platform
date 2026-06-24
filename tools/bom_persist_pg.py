#!/usr/bin/env python3
"""具身智能链 BOM — 第6步: 落 PG (migration 012 八张表).

把第1-5步成果写入 BOM V4 八张表:
  policy_themes         ← 未来产业主攻方向 (具身智能链)
  supply_chain_bom_nodes ← 4 节点 (reducer/motor/bearing/controller)
  policy_sources        ← 数据来源 (tushare_research/irm_qa/forecast)
  company_bom_mapping   ← 19 只公司节点锚定 + 主营产品
  company_evidence      ← 221 条证据
  supply_chain_scores   ← V5 评分 (trade_date=今天, 非回测时点)
  supply_chain_bom_edges / manual_overrides: 本期空 (留扩展)

⚠️ supply_chain_scores 的 trade_date 用今天 (2026-06-24), 这是"当前评分快照",
   非回测时点. 回测时须按 ann_date 卡 trade_date (PRD AC-8).

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_persist_pg.py
"""
import ast
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")

# ── 静态: 主题 + 节点 ──
THEME = {
    "theme_id": "future_industry_core",
    "name": "未来产业主攻方向",
    "policy_weight": 1.5,
    "keywords": ["量子科技", "生物制造", "氢能", "核聚变能", "脑机接口", "具身智能", "第六代移动通信"],
    "source_ids": [],
}
NODES = [
    {"node_id": "embodied_ai_core", "theme_id": "future_industry_core", "chain_id": "embodied_ai",
     "parent_node_id": None, "level": "chain", "name": "具身智能", "node_type": "industry",
     "keywords": ["具身智能", "机器人", "伺服", "减速器", "控制器"], "policy_weight": 1.5},
    {"node_id": "bom_reducer", "theme_id": "future_industry_core", "chain_id": "embodied_ai",
     "parent_node_id": "embodied_ai_core", "level": "component", "name": "减速器", "node_type": "component",
     "keywords": ["减速器", "谐波减速", "行星减速", "RV减速"], "policy_weight": 1.5},
    {"node_id": "bom_motor", "theme_id": "future_industry_core", "chain_id": "embodied_ai",
     "parent_node_id": "embodied_ai_core", "level": "component", "name": "电机", "node_type": "component",
     "keywords": ["电机", "空心杯", "伺服电机", "步进电机"], "policy_weight": 1.5},
    {"node_id": "bom_bearing", "theme_id": "future_industry_core", "chain_id": "embodied_ai",
     "parent_node_id": "embodied_ai_core", "level": "component", "name": "轴承", "node_type": "component",
     "keywords": ["轴承", "精密轴承"], "policy_weight": 1.5},
    {"node_id": "bom_controller", "theme_id": "future_industry_core", "chain_id": "embodied_ai",
     "parent_node_id": "embodied_ai_core", "level": "component", "name": "控制器", "node_type": "component",
     "keywords": ["控制器", "运动控制", "控制系统"], "policy_weight": 1.5},
]
NODE_ID_MAP = {"reducer": "bom_reducer", "motor": "bom_motor",
               "bearing": "bom_bearing", "controller": "bom_controller"}

# 来源 → source_id 映射
SOURCES = {
    "research_report": ("src_research_report", "tushare_research", "Tushare 研报"),
    "irm_qa_sh": ("src_irm_qa_sh", "tushare_irm_qa", "Tushare 沪市互动问答"),
    "irm_qa_sz": ("src_irm_qa_sz", "tushare_irm_qa", "Tushare 深市互动问答"),
    "forecast": ("src_forecast", "tushare_forecast", "Tushare 业绩预告"),
}


def _pl(s):
    if isinstance(s, list): return s
    try:
        v = ast.literal_eval(str(s)); return v if isinstance(v, list) else []
    except Exception: return []


def _eid(code, source, date_str, text):
    raw = f"{code}|{source}|{date_str}|{text[:60]}"
    return "ev_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def _short_code(code: str) -> str:
    """Tushare ts_code (688017.SH) → 6位 (688017), 与 stocks 表对齐 (项目命名规范)."""
    return code.split(".")[0] if code else code


def main():
    anchored = pd.read_csv(PROJ / "outputs" / "bom_embodied_reducer_anchored.csv")
    ev_all = pd.read_csv(PROJ / "outputs" / "bom_embodied_evidence_all.csv")
    scores = pd.read_csv(PROJ / "outputs" / "bom_embodied_score_v5.csv")

    # 公司 → (node, name, product, ratio) 主营最高节点
    anchored = anchored.sort_values("bz_sales", ascending=False).drop_duplicates("code")
    code_meta = {r["code"]: (r["node"], r["name"], r["bz_item"], r["ratio_pct"])
                 for _, r in anchored.iterrows()}

    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    cur = conn.cursor()

    written = {"policy_themes": 0, "supply_chain_bom_nodes": 0, "policy_sources": 0,
               "company_bom_mapping": 0, "company_evidence": 0, "supply_chain_scores": 0}

    try:
        # 1) policy_themes
        cur.execute("""
            INSERT INTO policy_themes(theme_id, name, policy_weight, keywords, source_ids)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (theme_id) DO NOTHING
        """, (THEME["theme_id"], THEME["name"], THEME["policy_weight"],
              json.dumps(THEME["keywords"], ensure_ascii=False), json.dumps([], ensure_ascii=False)))
        written["policy_themes"] = cur.rowcount

        # 2) supply_chain_bom_nodes
        for n in NODES:
            cur.execute("""
                INSERT INTO supply_chain_bom_nodes(node_id, theme_id, chain_id, parent_node_id, level, name, node_type, keywords, policy_weight)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (node_id) DO NOTHING
            """, (n["node_id"], n["theme_id"], n["chain_id"], n["parent_node_id"],
                  n["level"], n["name"], n["node_type"],
                  json.dumps(n["keywords"], ensure_ascii=False), n["policy_weight"]))
            written["supply_chain_bom_nodes"] += cur.rowcount

        # 3) policy_sources
        for sid, stype, title in SOURCES.values():
            cur.execute("""
                INSERT INTO policy_sources(source_id, source_type, title, source_url, published_at, content_hash, raw_text)
                VALUES (%s,%s,%s,NULL,NULL,NULL,'') ON CONFLICT (source_id) DO NOTHING
            """, (sid, stype, title))
            written["policy_sources"] += cur.rowcount

        # 4) company_bom_mapping + 5) company_evidence (同事务)
        # code 统一转 6 位 (与 stocks 表对齐, 项目命名规范)
        evidence_ids_by_code = {}
        for ts_code, (node, name, product, ratio) in code_meta.items():
            code = _short_code(ts_code)
            node_id = NODE_ID_MAP.get(node)
            if not node_id:
                continue
            ev_df = ev_all[ev_all["code"] == ts_code]
            ev_ids = []
            for _, r in ev_df.iterrows():
                src = r["source"]
                sid = SOURCES.get(src, (f"src_{src}", "tushare", src))[0]
                eid = _eid(code, src, str(r.get("date", "")), str(r.get("text", "")))
                chk = _pl(r.get("chokepoint"))
                stg = _pl(r.get("stage"))
                # evidence_type: 卡脖子命中→chokepoint, 商业化命中→commercialization, 预告→forecast
                etype = "forecast" if src == "forecast" else ("chokepoint" if chk else ("commercialization" if stg else "mention"))
                summary = str(r.get("text", ""))[:300]
                conf = 0.9 if (chk or stg) else 0.5
                cur.execute("""
                    INSERT INTO company_evidence(evidence_id, code, node_id, source_id, evidence_type, summary, excerpt, confidence, evidence_date, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending_review') ON CONFLICT (evidence_id) DO NOTHING
                """, (eid, code, node_id, sid, etype, summary, summary, conf,
                      str(r.get("date", "")) or None))
                if cur.rowcount:
                    written["company_evidence"] += 1
                ev_ids.append(eid)
            evidence_ids_by_code[code] = ev_ids

            mapping_id = "map_" + hashlib.sha1(f"{code}|{node_id}".encode()).hexdigest()[:16]
            confidence = min(0.5 + len(ev_ids) * 0.03, 1.0)
            cur.execute("""
                INSERT INTO company_bom_mapping(mapping_id, code, node_id, product_name, material_name, evidence_ids, confidence, status, updated_at)
                VALUES (%s,%s,%s,%s,NULL,%s,%s,'pending_review',%s) ON CONFLICT (mapping_id) DO NOTHING
            """, (mapping_id, code, node_id, str(product)[:100],
                  json.dumps(ev_ids, ensure_ascii=False), confidence, date.today().isoformat()))
            if cur.rowcount:
                written["company_bom_mapping"] += 1

        # 6) supply_chain_scores (V5, trade_date=今天)
        today = date.today().isoformat()
        for _, s in scores.iterrows():
            code = _short_code(s["code"])
            node_id = NODE_ID_MAP.get(s["node"])
            score_id = "sc_" + hashlib.sha1(f"{code}|{today}".encode()).hexdigest()[:16]
            dims = {
                "policy": float(s["policy"]), "bom": float(s["bom"]),
                "chokepoint": float(s["chokepoint"]), "growth": float(s["growth"]),
                "profit": float(s["profit"]), "commercialization": float(s["comm"]),
                "market": float(s["market"]), "risk": 0.0,
            }
            ev_ids = evidence_ids_by_code.get(code, [])
            cur.execute("""
                INSERT INTO supply_chain_scores(score_id, code, trade_date, node_id, total_score, rating, trade_signal, dimension_scores, evidence_ids)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (score_id) DO NOTHING
            """, (score_id, code, today, node_id, float(s["total"]),
                  s["rating"], s["trade_signal"],
                  json.dumps(dims, ensure_ascii=False),
                  json.dumps(ev_ids, ensure_ascii=False)))
            if cur.rowcount:
                written["supply_chain_scores"] += 1

        conn.commit()
        print("=" * 70)
        print("  BOM 落库完成 (migration 012 八张表)")
        print("=" * 70)
        for k, v in written.items():
            print(f"  {k:<28} {v} 行")
        print()
        # 验证查询
        cur.execute("""SELECT n.name, count(m.code) companies, count(e.evidence_id) evidence
            FROM supply_chain_bom_nodes n
            LEFT JOIN company_bom_mapping m ON m.node_id=n.node_id
            LEFT JOIN company_evidence e ON e.node_id=n.node_id
            WHERE n.level='component' GROUP BY n.name ORDER BY n.name""")
        print("  按节点:")
        print(f"  {'节点':<10} {'公司':>5} {'证据':>5}")
        for name, c, e in cur.fetchall():
            print(f"  {name:<10} {c:>5} {e:>5}")
        cur.execute("""SELECT rating, trade_signal, count(*) FROM supply_chain_scores GROUP BY rating, trade_signal ORDER BY rating""")
        print("\n  评分分布:")
        for rating, sig, n in cur.fetchall():
            print(f"  {rating}级 {sig:<8} {n} 只")
        cur.execute("""SELECT code, total_score, rating, trade_signal FROM supply_chain_scores ORDER BY total_score DESC LIMIT 5""")
        print("\n  Top5:")
        for code, sc, rt, sig in cur.fetchall():
            print(f"  {code}  {sc:.0f}分 {rt}级 {sig}")

    except Exception as e:
        conn.rollback()
        print(f"❌ 落库失败, 已回滚: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
