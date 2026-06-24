#!/usr/bin/env python3
"""BOM 路径2 — 严格 OOS: cutoff-aware V5 评分 + forward IC + train/test.

防 lookahead (AC-8): 每个 cutoff 只用 ann_date/trade_date <= cutoff 的数据重算评分.
  - fina_indicator: ann_date <= cutoff 的最新一期
  - forecast: ann_date <= cutoff
  - irm_qa / research_report: trade_date <= cutoff
  - fina_mainbz (主营占比, 静态): 用最新一期 (主营结构变化慢, 可接受)

样本: 36 只 BOM 锚定公司 (PG company_bom_mapping)
cutoff: 2025-01~2026-05 月末 (train 2025-01~09 / test 2025-10~2026-05)
forward return: PG daily_kline, horizon 10/20 日
IC: Spearman rank IC + bootstrap + 单样本 t 检验

对比: 同期路径1 (V5 全量 lookahead) 的 IC, 看 lookahead 虚高程度.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_oos_ic.py
"""
import ast
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
for p in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    sys.path.insert(0, str(PROJ / p))
from kronos_factors.backtest.engine import compute_ic  # noqa: E402
from kronos_factors.backtest.supply_chain_validation import _forward_returns  # noqa: E402
from kronos_factors.backtest.supply_chain_ic import _resolve_trading_day  # noqa: E402
from kronos_factors.scorer._db_stub import _get_db  # noqa: E402

CACHE = PROJ / "outputs" / "bom_oos_cache"
FINA = pd.read_csv(CACHE / "fina_indicator.csv", dtype={"code6": str})
FC = pd.read_csv(CACHE / "forecast.csv", dtype={"code6": str})
QA = pd.read_csv(CACHE / "irm_qa.csv", dtype={"code6": str})
RR = pd.read_csv(CACHE / "research_report.csv", dtype={"code6": str})
MB = pd.read_csv(CACHE / "fina_mainbz.csv", dtype={"code6": str})

# 补前导零
for df in [FINA, FC, QA, RR, MB]:
    df["code6"] = df["code6"].astype(str).str.zfill(6)

NODE_POLICY = {"reducer": 12, "motor": 12, "bearing": 11, "controller": 12}
NODE_ID_MAP = {"bom_reducer": "reducer", "bom_motor": "motor",
               "bom_bearing": "bearing", "bom_controller": "controller"}

CHOKEPOINT_KW = {
    "垄断": 5, "独家": 5, "首家": 5, "稀缺": 5, "寡头": 5, "唯一": 5,
    "国产替代": 4, "进口替代": 4, "自主可控": 4, "打破垄断": 5, "卡脖子": 4,
    "客户验证": 3, "认证": 3, "供应商": 3, "定点": 3, "进入供应链": 3,
}
COMM_KW = {"放量/订单": ["订单", "产能释放", "扩产", "放量", "满产", "需求旺盛", "供不应求"],
           "量产": ["量产", "批量生产", "规模化", "批量交付"],
           "小批量": ["小批量", "小批", "试产", "中试"],
           "样品/研发": ["样品", "试制", "研发中", "预研", "送样", "打样"]}


def load_meta():
    """{code6: (node, name, product, main_ratio)} from PG."""
    import psycopg2
    conn = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    cur = conn.cursor()
    cur.execute("SELECT code, node_id, product_name FROM company_bom_mapping")
    meta = {}
    for code, node_id, product in cur.fetchall():
        node = NODE_ID_MAP.get(node_id, "?")
        # 主营占比从 fina_mainbz 最新一期算
        mb = MB[MB["code6"] == code]
        ratio = 0
        if len(mb):
            latest = mb.sort_values("end_date", ascending=False).iloc[0]
            ratio = float(latest.get("bz_sales", 0) or 0)
        meta[code] = (node, product or "", ratio)
    conn.close()
    return meta


def cutoff_fina(code, cutoff_yyyymmdd):
    """cutoff 可见的最新财务. cutoff_yyyymmdd: '20250630'."""
    df = FINA[(FINA["code6"] == code) & (FINA["ann_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    if not len(df): return None
    r = df.sort_values("end_date", ascending=False).iloc[0]
    return {"q_sales_yoy": float(r.get("q_sales_yoy") or 0),
            "netprofit_yoy": float(r.get("netprofit_yoy") or 0),
            "gross_margin": float(r.get("grossprofit_margin") or r.get("gross_margin") or 0)}


def cutoff_forecast(code, cutoff_yyyymmdd):
    df = FC[(FC["code6"] == code) & (FC["ann_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    if not len(df): return None
    r = df.sort_values("ann_date", ascending=False).iloc[0]
    return str(r.get("type", "")), float(r.get("p_change_max") or 0)


def cutoff_evidence(code, cutoff_yyyymmdd):
    """cutoff 可见的互动问答 + 研报, 抽取 chokepoint/stage 命中."""
    qa = QA[(QA["code6"] == code) & (QA["trade_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    rr = RR[(RR["code6"] == code) & (RR["trade_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    ch_hits, stage_hits = {}, set()
    n_ev = 0
    texts = []
    for _, r in qa.iterrows():
        texts.append(str(r.get("q", "")) + " " + str(r.get("a", "")))
    for _, r in rr.iterrows():
        texts.append(str(r.get("title", "")))
    for text in texts:
        n_ev += 1
        for kw in CHOKEPOINT_KW:
            if kw in text: ch_hits[kw] = ch_hits.get(kw, 0) + 1
        for stg, kws in COMM_KW.items():
            if any(kw in text for kw in kws): stage_hits.add(stg)
    return ch_hits, stage_hits, n_ev


def score_v5_cutoff(code, meta, cutoff_yyyymmdd):
    """cutoff-aware V5 评分, 返回 total_score (无评分返回 nan)."""
    node, product, ratio = meta.get(code, ("?", "", 0))
    fina = cutoff_fina(code, cutoff_yyyymmdd)
    fc_type, fc_max = cutoff_forecast(code, cutoff_yyyymmdd) or (None, 0)
    ch_hits, stage_hits, n_ev = cutoff_evidence(code, cutoff_yyyymmdd)

    # policy
    policy = float(NODE_POLICY.get(node, 11))
    if n_ev > 0: policy = min(policy + 3, 15)
    # bom (主营占比)
    r = ratio
    bom = 15 if r >= 80 else 12 if r >= 50 else 8 if r >= 25 else 4 if r >= 10 else 2
    # chokepoint (多样性加权)
    choke = min(sum(min(c, 2) * w for kw, c in ch_hits.items() for w in [CHOKEPOINT_KW[kw]]), 20)
    # growth (财务优先, 预告兜底)
    growth = 6.0
    if fina:
        g = max(fina["q_sales_yoy"], fina["netprofit_yoy"])
        growth = 15 if g >= 100 else 12 if g >= 50 else 9 if g >= 20 else 6 if g >= 0 else 3
    elif fc_type and "预增" in fc_type:
        growth = 15 if fc_max >= 100 else 12 if fc_max >= 50 else 9
    # profit
    profit = 10 if fina and fina["gross_margin"] >= 50 else 7 if fina and fina["gross_margin"] >= 30 else 4 if fina and fina["gross_margin"] >= 15 else 2 if fina else 6
    # commercialization
    stage_order = ["放量/订单", "量产", "小批量", "样品/研发"]
    top = next((s for s in stage_order if s in stage_hits), "未识别")
    comm = {"放量/订单": 12, "量产": 9, "小批量": 6, "样品/研发": 3, "未识别": 2}[top]
    if fc_type and "预增" in fc_type and comm >= 9: comm = min(comm + 3, 15)
    # market
    market = 10 if n_ev >= 20 else 7 if n_ev >= 10 else 5 if n_ev >= 5 else 3 if n_ev >= 1 else 1

    total = policy + bom + choke + growth + profit + comm + market
    return min(round(total, 1), 100)


def month_ends(start, end):
    import datetime
    sy, sm, ey, em = int(start[:4]), int(start[5:7]), int(end[:4]), int(end[5:7])
    out, y, m = [], sy, sm
    while (y, m) <= (ey, em):
        nm, ny = m + 1, y
        if nm > 12: nm, ny = 1, y + 1
        last = datetime.date(ny, nm, 1) - datetime.timedelta(days=1)
        out.append(last.strftime("%Y-%m-%d"))
        m += 1
        if m > 12: m, y = 1, y + 1
    return out


def run_period(cutoffs, codes, meta, horizon, label):
    ic_series = []
    per_cutoff = []
    for cutoff in cutoffs:
        with _get_db(readonly=True) as db:
            cutoff_td = _resolve_trading_day(db, cutoff)  # 月末不超过该日的最近交易日
        cutoff_yyyymmdd = cutoff_td.replace("-", "")
        scores = np.array([score_v5_cutoff(c, meta, cutoff_yyyymmdd) for c in codes], dtype=np.float64)
        rets, future_td = _forward_returns(codes, cutoff_td, horizon)
        valid = ~np.isnan(rets) & ~np.isnan(scores)
        if valid.sum() < 5:
            continue
        ic = compute_ic(scores, rets)
        ic_series.append(ic["rank_ic"])
        per_cutoff.append({"cutoff": cutoff, "n": int(valid.sum()), "rank_ic": ic["rank_ic"],
                           "ic": ic["ic"], "hit": ic["hit_rate"]})
    if not ic_series:
        return {"label": label, "n": 0, "mean_rank_ic": 0, "p": 1, "per_cutoff": []}
    arr = np.array(ic_series)
    t, p2 = stats.ttest_1samp(arr, 0)
    p1 = p2 / 2 if t > 0 else 1 - p2 / 2
    return {"label": label, "n": len(arr), "mean_rank_ic": round(float(arr.mean()), 4),
            "std": round(float(arr.std()), 4), "icir": round(float(arr.mean() / (arr.std() or 1e-9)), 4),
            "p": round(float(p1), 4), "per_cutoff": per_cutoff}


def main():
    meta = load_meta()
    codes = sorted(meta.keys())
    print("=" * 95)
    print("  BOM 路径2 — 严格 OOS (cutoff-aware V5 评分 + forward IC)")
    print("=" * 95)
    print(f"  样本: {len(codes)} 只 | train 2025-01~09 / test 2025-10~2026-05 | horizon 10/20d")
    print(f"  防 lookahead: 财务/预告 ann_date<=cutoff, 问答/研报 trade_date<=cutoff\n")

    train_cuts = month_ends("2025-01", "2025-09")
    test_cuts = month_ends("2025-10", "2026-05")

    all_results = {}
    for horizon in [10, 20]:
        print(f"  ▶ horizon={horizon}d")
        tr = run_period(train_cuts, codes, meta, horizon, f"train h{horizon}")
        te = run_period(test_cuts, codes, meta, horizon, f"test h{horizon}")
        all_results[f"train_h{horizon}"] = tr
        all_results[f"test_h{horizon}"] = te
        print(f"    train: {tr['n']} cutoffs, mean_rankIC={tr['mean_rank_ic']:+.3f} std={tr.get('std',0):.3f} p={tr['p']:.3f}")
        print(f"    test:  {te['n']} cutoffs, mean_rankIC={te['mean_rank_ic']:+.3f} std={te.get('std',0):.3f} p={te['p']:.3f}")
        # 逐 cutoff
        for pc in te["per_cutoff"]:
            print(f"      {pc['cutoff']} n={pc['n']:>2} rankIC={pc['rank_ic']:+.3f} hit={pc['hit']:.0%}")
        print()

    # 结论
    print("=" * 95)
    print("  结论 (严格 OOS, 无 lookahead)")
    print("=" * 95)
    for h in [10, 20]:
        tr = all_results[f"train_h{h}"]; te = all_results[f"test_h{h}"]
        print(f"  horizon={h}d:")
        print(f"    train rankIC={tr['mean_rank_ic']:+.3f} (p={tr['p']:.3f}) | test rankIC={te['mean_rank_ic']:+.3f} (p={te['p']:.3f})")
    te20 = all_results["test_h20"]
    print()
    if te20["mean_rank_ic"] > 0.03 and te20["p"] < 0.1:
        verdict = "✅ test 期 rankIC 显著为正 — BOM 评分有真选股能力 (OOS 成立)"
    elif te20["mean_rank_ic"] > 0:
        verdict = "⚪ test 期 rankIC 弱正但不显著 — 方向对, 样本/功效不足"
    else:
        verdict = "❌ test 期 rankIC ≤ 0 — BOM 评分 OOS 无效"
    print(f"  判定: {verdict}")
    print(f"  注: 样本 {len(codes)} 只偏小, 单 cutoff IC 噪声大. 结论供参考, 非投资建议.")


if __name__ == "__main__":
    main()
