#!/usr/bin/env python3
"""BOM 路径2 — 严格 OOS: cutoff-aware V5 评分 + forward IC + train/test.

防 lookahead (AC-8): 每个 cutoff 只用 ann_date/trade_date <= cutoff 的数据重算评分.
  - fina_indicator: ann_date <= cutoff 的最新一期
  - forecast: ann_date <= cutoff
  - irm_qa / research_report: trade_date <= cutoff
  - fina_mainbz: 默认保留 fixed_current_mapping；可用 cutoff_rebuilt_cache 按 cutoff 重建公司-节点-主营占比

样本: 36 只 BOM 锚定公司 (PG company_bom_mapping)
cutoff: 2025-01~2026-05 月末 (train 2025-01~09 / test 2025-10~2026-05)
forward return: PG daily_kline, horizon 10/20 日
IC: Spearman rank IC + bootstrap + 单样本 t 检验

对比: 同期路径1 (V5 全量 lookahead) 的 IC, 看 lookahead 虚高程度.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_oos_ic.py
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_oos_ic.py --universe-mode cutoff_rebuilt_cache
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/bom_oos_ic.py --universe-mode cutoff_rebuilt_cache --cache-dir outputs/bom_oos_cache_smoke
"""
import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
for p in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    sys.path.insert(0, str(PROJ / p))
from kronos_factors.backtest.engine import compute_ic  # noqa: E402
from kronos_factors.backtest.bom_oos_report import (  # noqa: E402
    build_oos_audit_report,
    summarize_oos_verdict,
    write_oos_audit_artifacts,
)
from kronos_factors.backtest.bom_oos_cache import cache_input_paths, load_cache_frames  # noqa: E402
from kronos_factors.backtest.bom_universe import build_cutoff_universe_from_cache  # noqa: E402
from kronos_factors.backtest.supply_chain_validation import _forward_returns  # noqa: E402
from kronos_factors.backtest.supply_chain_ic import _resolve_trading_day  # noqa: E402
from kronos_factors.engine.supply_chain_bom_v5 import (  # noqa: E402
    score_bom_ratio,
    score_chokepoint_hits,
    score_commercialization,
    score_growth,
    score_market,
    score_profit,
)
from kronos_factors.scorer._db_stub import _get_db  # noqa: E402

DEFAULT_CACHE = PROJ / "outputs" / "bom_oos_cache"
CACHE = DEFAULT_CACHE
REPORT_DIR = PROJ / "outputs" / "bom_oos_reports"
UNIVERSE_MODE = "fixed_current_mapping"
FINA = pd.DataFrame()
FC = pd.DataFrame()
QA = pd.DataFrame()
RR = pd.DataFrame()
MB = pd.DataFrame()

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


def resolve_project_path(path):
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJ / candidate


def set_cache_frames(cache_dir):
    global CACHE, FINA, FC, QA, RR, MB
    CACHE = resolve_project_path(cache_dir)
    frames = load_cache_frames(CACHE)
    FINA = frames["fina_indicator"]
    FC = frames["forecast"]
    QA = frames["irm_qa"]
    RR = frames["research_report"]
    MB = frames["fina_mainbz"]
    return frames


def load_cutoff_meta(cutoff_yyyymmdd, require_visible_evidence=False):
    return build_cutoff_universe_from_cache(
        mainbz_df=MB,
        qa_df=QA,
        research_df=RR,
        cutoff_yyyymmdd=cutoff_yyyymmdd,
        require_evidence=require_visible_evidence,
    )


def _git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJ,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _cache_paths(cache_dir=None):
    return list(cache_input_paths(cache_dir or CACHE).values())


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
    bom = score_bom_ratio(ratio)
    choke = score_chokepoint_hits(ch_hits)
    if fina:
        growth, _ = score_growth(fina["q_sales_yoy"], fina["netprofit_yoy"])
        profit, _ = score_profit(fina["gross_margin"])
    else:
        growth, _ = score_growth(None, None, forecast_max=fc_max, forecast_type=fc_type)
        profit, _ = score_profit(None)
    comm, _ = score_commercialization(stage_hits, fc_type)
    market = score_market(n_ev)

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


def resolve_period_universe(
    universe_mode,
    fixed_codes,
    fixed_meta,
    cutoff_yyyymmdd,
    require_visible_evidence=False,
):
    if universe_mode == "fixed_current_mapping":
        return fixed_codes, fixed_meta
    if universe_mode == "cutoff_rebuilt_cache":
        cutoff_meta = load_cutoff_meta(cutoff_yyyymmdd, require_visible_evidence=require_visible_evidence)
        return sorted(cutoff_meta.keys()), cutoff_meta
    raise ValueError(f"unsupported universe_mode={universe_mode}")


def run_period(
    cutoffs,
    codes,
    meta,
    horizon,
    label,
    *,
    universe_mode=UNIVERSE_MODE,
    require_visible_evidence=False,
    min_valid=5,
):
    ic_series = []
    per_cutoff = []
    observed_codes = set()
    for cutoff in cutoffs:
        with _get_db(readonly=True) as db:
            cutoff_td = _resolve_trading_day(db, cutoff)  # 月末不超过该日的最近交易日
        if not cutoff_td:
            continue
        cutoff_yyyymmdd = cutoff_td.replace("-", "")
        period_codes, period_meta = resolve_period_universe(
            universe_mode,
            codes,
            meta,
            cutoff_yyyymmdd,
            require_visible_evidence=require_visible_evidence,
        )
        observed_codes.update(period_codes)
        if len(period_codes) < min_valid:
            continue

        scores = np.array([score_v5_cutoff(c, period_meta, cutoff_yyyymmdd) for c in period_codes], dtype=np.float64)
        rets, future_td = _forward_returns(period_codes, cutoff_td, horizon)
        valid = ~np.isnan(rets) & ~np.isnan(scores)
        if valid.sum() < min_valid:
            continue
        ic = compute_ic(scores, rets)
        ic_series.append(ic["rank_ic"])
        per_cutoff.append({
            "cutoff": cutoff,
            "cutoff_td": cutoff_td,
            "future_td": future_td,
            "universe_size": len(period_codes),
            "n": int(valid.sum()),
            "rank_ic": ic["rank_ic"],
            "ic": ic["ic"],
            "hit": ic["hit_rate"],
        })
    if not ic_series:
        return {
            "label": label,
            "n": 0,
            "mean_rank_ic": 0,
            "p": 1,
            "per_cutoff": [],
            "observed_codes": sorted(observed_codes),
        }
    arr = np.array(ic_series)
    t, p2 = stats.ttest_1samp(arr, 0)
    p1 = p2 / 2 if t > 0 else 1 - p2 / 2
    return {"label": label, "n": len(arr), "mean_rank_ic": round(float(arr.mean()), 4),
            "std": round(float(arr.std()), 4), "icir": round(float(arr.mean() / (arr.std() or 1e-9)), 4),
            "p": round(float(p1), 4), "per_cutoff": per_cutoff, "observed_codes": sorted(observed_codes)}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="BOM V5 cutoff-aware OOS IC validation")
    parser.add_argument(
        "--universe-mode",
        choices=["fixed_current_mapping", "cutoff_rebuilt_cache"],
        default=UNIVERSE_MODE,
        help="fixed_current_mapping keeps PG company_bom_mapping; cutoff_rebuilt_cache rebuilds mapping from cache per cutoff.",
    )
    parser.add_argument(
        "--require-visible-evidence",
        action="store_true",
        help="Only include cutoff-rebuilt companies whose QA/research evidence mentions the inferred node/product before cutoff.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(DEFAULT_CACHE.relative_to(PROJ)),
        help="Directory containing BOM OOS cache CSVs.",
    )
    parser.add_argument(
        "--min-valid",
        type=int,
        default=5,
        help="Minimum valid stocks required per cutoff; lower only for smoke tests.",
    )
    parser.add_argument("--out-dir", default=str(REPORT_DIR), help="Directory for audit JSON/CSV artifacts.")
    return parser.parse_args(argv)


def _observed_universe_codes(all_results, fallback_codes=None):
    observed = set()
    for result in all_results.values():
        observed.update(result.get("observed_codes", []))
    return sorted(observed or (fallback_codes or []))


def main(argv=None):
    args = parse_args(argv)
    cache_dir = resolve_project_path(args.cache_dir)
    try:
        set_cache_frames(cache_dir)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(2)
    meta = load_meta()
    codes = sorted(meta.keys())
    print("=" * 95)
    print("  BOM 路径2 — 严格 OOS (cutoff-aware V5 评分 + forward IC)")
    print("=" * 95)
    print(f"  固定映射基准样本: {len(codes)} 只 | train 2025-01~09 / test 2025-10~2026-05 | horizon 10/20d")
    print(f"  宇宙模式: {args.universe_mode} | require_visible_evidence={args.require_visible_evidence}")
    print(f"  缓存目录: {cache_dir}")
    print(f"  防 lookahead: 财务/预告 ann_date<=cutoff, 问答/研报 trade_date<=cutoff\n")

    train_cuts = month_ends("2025-01", "2025-09")
    test_cuts = month_ends("2025-10", "2026-05")

    all_results = {}
    for horizon in [10, 20]:
        print(f"  ▶ horizon={horizon}d")
        tr = run_period(
            train_cuts,
            codes,
            meta,
            horizon,
            f"train h{horizon}",
            universe_mode=args.universe_mode,
            require_visible_evidence=args.require_visible_evidence,
            min_valid=args.min_valid,
        )
        te = run_period(
            test_cuts,
            codes,
            meta,
            horizon,
            f"test h{horizon}",
            universe_mode=args.universe_mode,
            require_visible_evidence=args.require_visible_evidence,
            min_valid=args.min_valid,
        )
        all_results[f"train_h{horizon}"] = tr
        all_results[f"test_h{horizon}"] = te
        print(f"    train: {tr['n']} cutoffs, mean_rankIC={tr['mean_rank_ic']:+.3f} std={tr.get('std',0):.3f} p={tr['p']:.3f}")
        print(f"    test:  {te['n']} cutoffs, mean_rankIC={te['mean_rank_ic']:+.3f} std={te.get('std',0):.3f} p={te['p']:.3f}")
        # 逐 cutoff
        for pc in te["per_cutoff"]:
            print(
                f"      {pc['cutoff']} universe={pc['universe_size']:>2} n={pc['n']:>2} "
                f"rankIC={pc['rank_ic']:+.3f} hit={pc['hit']:.0%}"
            )
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
    verdict = summarize_oos_verdict(te20)
    if verdict["status"] == "PASS":
        verdict_prefix = "✅"
    elif verdict["status"] == "INCONCLUSIVE":
        verdict_prefix = "⚪"
    elif verdict["status"] == "WEAK_POSITIVE":
        verdict_prefix = "⚪"
    else:
        verdict_prefix = "❌"
    print(f"  判定: {verdict_prefix} {verdict['message']}")
    fallback_codes = codes if args.universe_mode == "fixed_current_mapping" else []
    universe_codes = _observed_universe_codes(all_results, fallback_codes)
    print(f"  注: 观测样本 {len(universe_codes)} 只偏小, 单 cutoff IC 噪声大. 结论供参考, 非投资建议.")
    if args.universe_mode == "fixed_current_mapping":
        print("  宇宙模式: fixed_current_mapping — 当前固定公司池会保留选择偏差, 下一阶段需按cutoff重建候选宇宙.")
    else:
        print("  宇宙模式: cutoff_rebuilt_cache — 公司-节点-主营占比已按cutoff重建, 但仍受缓存覆盖范围限制.")

    report = build_oos_audit_report(
        model_version="supply_chain_bom_v5",
        universe_mode=args.universe_mode,
        universe_codes=universe_codes,
        results=all_results,
        config={
            "horizons": [10, 20],
            "train_range": ["2025-01", "2025-09"],
            "test_range": ["2025-10", "2026-05"],
            "cutoff_frequency": "month_end",
            "score_cutoff_rule": "financial/forecast ann_date<=cutoff, QA/research trade_date<=cutoff",
            "universe_rule": args.universe_mode,
            "cache_dir": str(cache_dir),
            "require_visible_evidence": args.require_visible_evidence,
            "min_valid": args.min_valid,
            "forward_return_source": "daily_kline close-to-close",
        },
        cache_paths=_cache_paths(cache_dir),
        git_commit=_git_commit(),
    )
    artifact_paths = write_oos_audit_artifacts(report, args.out_dir)
    print("\n  审计产物:")
    for name, path in artifact_paths.items():
        print(f"    {name}: {path}")


if __name__ == "__main__":
    main()
