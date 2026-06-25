#!/usr/bin/env python3
"""三因子共振 V6 IC 验证脚本 — cutoff-aware OOS forward IC + threshold tuning.

三因子:
  1. 产业周期 (industry_cycle): 产业化阶段评分 — 从 QA/研报文本抽取
  2. 政策强度 (policy_intensity): BOM 节点所属主题的 policy_weight × relevance
  3. 业绩兑现 (performance_yield): 收入/利润同比评分

共振判定:
  - 三因子均过阈值 → "强启动"
  - 两因子过阈值 → "启动"
  - 一因子过阈值 → "关注"
  - 零因子过阈值 → "观察"

阈值调参目标: test_h20 IC ≥ +0.10

防 lookahead (同 bom_oos_ic.py):
  - fina_indicator: ann_date <= cutoff 的最新一期
  - forecast: ann_date <= cutoff
  - irm_qa / research_report: trade_date <= cutoff
  - policy_weight: 使用固定配置(非时间序列), 不存在 lookahead

样本: 36 只 BOM 锚定公司 (PG company_bom_mapping) 或 cutoff_rebuilt_cache
cutoff: 2025-01~2026-05 月末 (train 2025-01~09 / test 2025-10~2026-05)
forward return: PG daily_kline, horizon 10/20 日
IC: Spearman rank IC + 单样本 t 检验

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/resonance_ic_validation.py
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/resonance_ic_validation.py --scan-thresholds
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos python tools/resonance_ic_validation.py --cache-dir outputs/bom_oos_cache_smoke
"""
import argparse
import datetime
import json
import os
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
from kronos_factors.backtest.bom_oos_cache import cache_input_paths, load_cache_frames  # noqa: E402
from kronos_factors.backtest.bom_universe import build_cutoff_universe_from_cache  # noqa: E402
from kronos_factors.backtest.supply_chain_validation import _forward_returns  # noqa: E402
from kronos_factors.backtest.supply_chain_ic import _resolve_trading_day  # noqa: E402
from kronos_factors.engine.supply_chain_bom import load_bom_config  # noqa: E402
from kronos_factors.engine.supply_chain_bom_v5 import (  # noqa: E402
    INDUSTRY_CYCLE_SCORE,
    PERFORMANCE_YIELD_SCORE,
    COMMERCIALIZATION_RANK,
    COMMERCIALIZATION_SCORE,
    derive_resonance_v6,
    _score_industry_cycle,
    _score_policy_intensity,
    _score_performance_yield,
)
from kronos_factors.scorer._db_stub import _get_db  # noqa: E402

DEFAULT_CACHE = PROJ / "outputs" / "bom_oos_cache"
CACHE = DEFAULT_CACHE
REPORT_DIR = PROJ / "outputs" / "resonance_ic_reports"

# Cache frames (global, set by set_cache_frames)
FINA = pd.DataFrame()
FC = pd.DataFrame()
QA = pd.DataFrame()
RR = pd.DataFrame()
MB = pd.DataFrame()

# BOM config (policy weights)
BOM_CONFIG = None
NODE_POLICY_WEIGHTS = {}  # node_id -> policy_weight

# Commercialization keywords (from supply_chain_bom_v5)
COMM_KW = {
    "放量/订单": ["订单", "产能释放", "扩产", "放量", "满产", "需求旺盛", "供不应求"],
    "量产": ["量产", "批量生产", "规模化", "批量交付"],
    "小批量": ["小批量", "小批", "试产", "中试"],
    "样品/研发": ["样品", "试制", "研发中", "预研", "送样", "打样"],
}

NODE_ID_MAP = {"bom_reducer": "reducer", "bom_motor": "motor",
               "bom_bearing": "bearing", "bom_controller": "controller"}

# Default thresholds for resonance
DEFAULT_THRESHOLDS = {
    "industry_cycle": 9.0,  # 量产及以上
    "policy_intensity": 9.0,
    "performance_yield": 15.0,  # yoy >= 50%
}


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


def load_bom_policy_weights():
    """Load policy weights from BOM config file."""
    global BOM_CONFIG, NODE_POLICY_WEIGHTS
    BOM_CONFIG = load_bom_config()

    # Build theme_id -> policy_weight mapping
    theme_weights = {}
    for theme in BOM_CONFIG.get("themes", []):
        theme_id = theme.get("theme_id", "")
        weight = float(theme.get("policy_weight", 1.0))
        theme_weights[theme_id] = weight

    # Build node_id -> policy_weight mapping (inherit from parent theme)
    for node in BOM_CONFIG.get("nodes", []):
        node_id = node.get("node_id", "")
        theme_id = node.get("theme_id", "")
        # Map node to policy weight from its theme
        NODE_POLICY_WEIGHTS[node_id] = theme_weights.get(theme_id, 1.0)

    return NODE_POLICY_WEIGHTS


def load_meta():
    """{code6: (node, name, product, main_ratio)} from PG."""
    import psycopg2
    conn = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    cur = conn.cursor()
    cur.execute("SELECT code, node_id, product_name FROM company_bom_mapping")
    meta = {}
    for code, node_id, product in cur.fetchall():
        node = NODE_ID_MAP.get(node_id, node_id)  # normalize node_id
        # 主营占比从 fina_mainbz 最新一期算
        mb = MB[MB["code6"] == code]
        ratio = 0
        if len(mb):
            latest = mb.sort_values("end_date", ascending=False).iloc[0]
            ratio = float(latest.get("bz_sales", 0) or 0)
        meta[code] = (node, product or "", ratio)
    conn.close()
    return meta


def load_cutoff_meta(cutoff_yyyymmdd, require_visible_evidence=False):
    return build_cutoff_universe_from_cache(
        mainbz_df=MB,
        qa_df=QA,
        research_df=RR,
        cutoff_yyyymmdd=cutoff_yyyymmdd,
        require_evidence=require_visible_evidence,
    )


def cutoff_fina(code, cutoff_yyyymmdd):
    """cutoff 可见的最新财务. cutoff_yyyymmdd: '20250630'."""
    df = FINA[(FINA["code6"] == code) & (FINA["ann_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    if not len(df): return None
    r = df.sort_values("end_date", ascending=False).iloc[0]
    return {
        "q_sales_yoy": float(r.get("q_sales_yoy") or 0),
        "netprofit_yoy": float(r.get("netprofit_yoy") or 0),
        "gross_margin": float(r.get("grossprofit_margin") or r.get("gross_margin") or 0),
    }


def cutoff_forecast(code, cutoff_yyyymmdd):
    """cutoff 可见的业绩预告."""
    df = FC[(FC["code6"] == code) & (FC["ann_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    if not len(df): return None
    r = df.sort_values("ann_date", ascending=False).iloc[0]
    return str(r.get("type", "")), float(r.get("p_change_max") or 0)


def cutoff_evidence_stage(code, cutoff_yyyymmdd):
    """Extract commercialization stage from QA/research evidence before cutoff."""
    qa = QA[(QA["code6"] == code) & (QA["trade_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]
    rr = RR[(RR["code6"] == code) & (RR["trade_date"].astype(str).str[:8] <= cutoff_yyyymmdd)]

    stage_hits = set()
    texts = []
    for _, r in qa.iterrows():
        texts.append(str(r.get("q", "")) + " " + str(r.get("a", "")))
    for _, r in rr.iterrows():
        texts.append(str(r.get("title", "")))

    for text in texts:
        for stg, kws in COMM_KW.items():
            if any(kw in text for kw in kws):
                stage_hits.add(stg)

    # Return the highest stage
    for stage in COMMERCIALIZATION_RANK:
        if stage in stage_hits:
            return stage
    return None


def score_resonance_cutoff(code, meta, cutoff_yyyymmdd, thresholds=None):
    """Calculate three-factor resonance score at cutoff.

    Returns dict with:
        - resonance_score: float (sum of three factor scores, max 47)
        - resonance_factors: int (count of factors passing threshold)
        - resonance_signal: str
        - factor_scores: dict
        - factor_passed: dict
    """
    thresholds = thresholds or DEFAULT_THRESHOLDS
    node, product, ratio = meta.get(code, ("?", "", 0))

    # Factor 1: Industry cycle (产业化阶段)
    stage = cutoff_evidence_stage(code, cutoff_yyyymmdd)
    industry_cycle_score = _score_industry_cycle(stage)

    # Factor 2: Policy intensity (政策强度)
    # Use BOM node's policy_weight from config
    policy_weight = NODE_POLICY_WEIGHTS.get(node, 1.0)
    # Convert policy_weight (1.0-1.5 range) to score (max 15)
    # policy_weight 1.0 -> 10, 1.5 -> 15
    policy_intensity_score = _score_policy_intensity(policy_weight * 10, 1.0)

    # Factor 3: Performance yield (业绩兑现)
    fina = cutoff_fina(code, cutoff_yyyymmdd)
    if fina:
        best_yoy = max(fina["q_sales_yoy"], fina["netprofit_yoy"])
    else:
        # Fallback to forecast
        fc_type, fc_max = cutoff_forecast(code, cutoff_yyyymmdd) or (None, 0)
        if fc_type and "预增" in fc_type:
            best_yoy = fc_max
        else:
            best_yoy = None
    performance_yield_score = _score_performance_yield(best_yoy)

    # Count factors passing threshold
    factors_passed = [
        industry_cycle_score >= thresholds["industry_cycle"],
        policy_intensity_score >= thresholds["policy_intensity"],
        performance_yield_score >= thresholds["performance_yield"],
    ]
    resonance_count = sum(factors_passed)

    # Determine resonance signal
    if resonance_count >= 3:
        resonance_signal = "强启动"
    elif resonance_count == 2:
        resonance_signal = "启动"
    elif resonance_count == 1:
        resonance_signal = "关注"
    else:
        resonance_signal = "观察"

    return {
        "resonance_score": round(industry_cycle_score + policy_intensity_score + performance_yield_score, 1),
        "resonance_factors": resonance_count,
        "resonance_signal": resonance_signal,
        "factor_scores": {
            "industry_cycle": industry_cycle_score,
            "policy_intensity": policy_intensity_score,
            "performance_yield": performance_yield_score,
        },
        "factor_passed": {
            "industry_cycle": factors_passed[0],
            "policy_intensity": factors_passed[1],
            "performance_yield": factors_passed[2],
        },
        "stage": stage,
        "node": node,
        "best_yoy": best_yoy,
    }


def month_ends(start, end):
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
    universe_mode="fixed_current_mapping",
    require_visible_evidence=False,
    min_valid=5,
    thresholds=None,
):
    """Run IC calculation for a period with given thresholds."""
    ic_series = []
    per_cutoff = []
    observed_codes = set()
    resonance_counts = {}  # Track resonance signal distribution

    for cutoff in cutoffs:
        with _get_db(readonly=True) as db:
            cutoff_td = _resolve_trading_day(db, cutoff)
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

        # Calculate resonance scores
        scores_list = []
        details_list = []
        for c in period_codes:
            det = score_resonance_cutoff(c, period_meta, cutoff_yyyymmdd, thresholds)
            scores_list.append(det["resonance_score"])
            details_list.append(det)
            # Track resonance distribution
            sig = det["resonance_signal"]
            resonance_counts[sig] = resonance_counts.get(sig, 0) + 1

        scores = np.array(scores_list, dtype=np.float64)
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
            "resonance_counts": dict(resonance_counts),
        })

    if not ic_series:
        return {
            "label": label,
            "n": 0,
            "mean_rank_ic": 0,
            "p": 1,
            "per_cutoff": [],
            "observed_codes": sorted(observed_codes),
            "resonance_counts": {},
        }

    arr = np.array(ic_series)
    t, p2 = stats.ttest_1samp(arr, 0)
    p1 = p2 / 2 if t > 0 else 1 - p2 / 2
    return {
        "label": label,
        "n": len(arr),
        "mean_rank_ic": round(float(arr.mean()), 4),
        "std": round(float(arr.std()), 4),
        "icir": round(float(arr.mean() / (arr.std() or 1e-9)), 4),
        "p": round(float(p1), 4),
        "per_cutoff": per_cutoff,
        "observed_codes": sorted(observed_codes),
        "resonance_counts": dict(resonance_counts),
    }


def scan_thresholds(cutoffs, codes, meta, horizon=20, min_valid=5):
    """Scan different threshold combinations to find optimal IC."""
    results = []

    # Threshold ranges to scan
    ic_range = [6.0, 9.0, 12.0]  # industry_cycle: 小批量/量产/放量
    pi_range = [6.0, 9.0, 12.0, 15.0]  # policy_intensity
    py_range = [5.0, 10.0, 15.0, 20.0]  # performance_yield: yoy thresholds

    for ic_th in ic_range:
        for pi_th in pi_range:
            for py_th in py_range:
                thresholds = {
                    "industry_cycle": ic_th,
                    "policy_intensity": pi_th,
                    "performance_yield": py_th,
                }
                # Run test period with these thresholds
                te = run_period(
                    cutoffs,
                    codes,
                    meta,
                    horizon,
                    f"scan_ic{ic_th}_pi{pi_th}_py{py_th}",
                    min_valid=min_valid,
                    thresholds=thresholds,
                )
                if te["n"] > 0:
                    results.append({
                        "thresholds": thresholds,
                        "mean_rank_ic": te["mean_rank_ic"],
                        "std": te["std"],
                        "icir": te["icir"],
                        "p": te["p"],
                        "n": te["n"],
                        "resonance_counts": te["resonance_counts"],
                    })

    # Sort by IC descending
    results.sort(key=lambda x: x["mean_rank_ic"], reverse=True)
    return results


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="三因子共振 V6 IC 验证")
    parser.add_argument(
        "--universe-mode",
        choices=["fixed_current_mapping", "cutoff_rebuilt_cache"],
        default="fixed_current_mapping",
        help="fixed_current_mapping keeps PG company_bom_mapping; cutoff_rebuilt_cache rebuilds mapping per cutoff.",
    )
    parser.add_argument(
        "--require-visible-evidence",
        action="store_true",
        help="Only include cutoff-rebuilt companies with visible evidence.",
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
        help="Minimum valid stocks per cutoff.",
    )
    parser.add_argument(
        "--out-dir",
        default=str(REPORT_DIR),
        help="Directory for output JSON/CSV artifacts.",
    )
    parser.add_argument(
        "--scan-thresholds",
        action="store_true",
        help="Scan multiple threshold combinations to find optimal IC.",
    )
    parser.add_argument(
        "--industry-cycle-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS["industry_cycle"],
        help="Industry cycle threshold (default 9.0 = 量产).",
    )
    parser.add_argument(
        "--policy-intensity-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS["policy_intensity"],
        help="Policy intensity threshold (default 9.0).",
    )
    parser.add_argument(
        "--performance-yield-threshold",
        type=float,
        default=DEFAULT_THRESHOLDS["performance_yield"],
        help="Performance yield threshold (default 15.0 = yoy>=50%%).",
    )
    return parser.parse_args(argv)


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


def build_report(
    model_version,
    universe_mode,
    universe_codes,
    results,
    thresholds,
    config,
    scan_results=None,
):
    """Build audit report JSON."""
    return {
        "model_version": model_version,
        "timestamp": datetime.datetime.now().isoformat(),
        "git_commit": _git_commit(),
        "universe_mode": universe_mode,
        "universe_codes": universe_codes,
        "universe_size": len(universe_codes),
        "thresholds": thresholds,
        "results": results,
        "scan_results": scan_results,
        "config": config,
        "cache_paths": [str(p) for p in _cache_paths()],
    }


def write_report(report, out_dir):
    """Write report JSON and per_cutoff CSV."""
    out = resolve_project_path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # JSON report
    json_path = out / "resonance_ic_validation.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Per-cutoff CSV for test_h20
    csv_path = out / "resonance_ic_per_cutoff.csv"
    rows = []
    for key in ["train_h10", "test_h10", "train_h20", "test_h20"]:
        if key in report["results"]:
            for pc in report["results"][key].get("per_cutoff", []):
                rows.append({
                    "period": key,
                    "cutoff": pc["cutoff"],
                    "cutoff_td": pc["cutoff_td"],
                    "universe_size": pc["universe_size"],
                    "n": pc["n"],
                    "rank_ic": pc["rank_ic"],
                    "ic": pc["ic"],
                    "hit_rate": pc["hit"],
                    "resonance_distribution": json.dumps(pc.get("resonance_counts", {})),
                })
    if rows:
        pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8")

    return {"json": json_path, "csv": csv_path}


def print_tuning_recommendations(te20, scan_results, thresholds):
    """Print tuning recommendations based on IC results."""
    print("=" * 95)
    print("  调参建议")
    print("=" * 95)

    target_ic = 0.10
    current_ic = te20["mean_rank_ic"]

    if current_ic >= target_ic:
        print(f"  ✅ 当前阈值已达标: test_h20 IC = {current_ic:+.4f} ≥ {target_ic:.2f}")
        print(f"  当前阈值: industry_cycle={thresholds['industry_cycle']}, "
              f"policy_intensity={thresholds['policy_intensity']}, "
              f"performance_yield={thresholds['performance_yield']}")
        return

    print(f"  ❌ 当前阈值未达标: test_h20 IC = {current_ic:+.4f} < {target_ic:.2f}")

    if scan_results:
        # Find best threshold combination
        best = scan_results[0]  # Already sorted by IC descending
        print(f"  扫描发现最优阈值组合:")
        print(f"    industry_cycle_threshold = {best['thresholds']['industry_cycle']}")
        print(f"    policy_intensity_threshold = {best['thresholds']['policy_intensity']}")
        print(f"    performance_yield_threshold = {best['thresholds']['performance_yield']}")
        print(f"    → test IC = {best['mean_rank_ic']:+.4f} (p={best['p']:.3f})")

        if best["mean_rank_ic"] >= target_ic:
            print(f"  ✅ 推荐采用上述阈值组合")
        else:
            print(f"  ⚠️ 最优组合仍未达标，建议:")
            print(f"    1. 扩大样本池 (当前 {te20['n']} cutoffs 噪声大)")
            print(f"    2. 检查因子构造有效性 (产业周期抽取准确性)")
            print(f"    3. 考虑增加第四因子 (如 chokepoint/市场热度)")

    # Analyze factor distribution
    rc = te20.get("resonance_counts", {})
    print(f"\n  共振信号分布 (test_h20):")
    for sig in ["强启动", "启动", "关注", "观察"]:
        cnt = rc.get(sig, 0)
        pct = cnt / sum(rc.values()) * 100 if rc else 0
        print(f"    {sig}: {cnt} ({pct:.1f}%)")

    if rc.get("观察", 0) > sum(rc.values()) * 0.5:
        print(f"  ⚠️ 超过半数样本为'观察'信号，阈值过高或因子构造问题")

    print()


def main(argv=None):
    args = parse_args(argv)
    cache_dir = resolve_project_path(args.cache_dir)

    try:
        set_cache_frames(cache_dir)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        sys.exit(2)

    load_bom_policy_weights()
    meta = load_meta()
    codes = sorted(meta.keys())

    thresholds = {
        "industry_cycle": args.industry_cycle_threshold,
        "policy_intensity": args.policy_intensity_threshold,
        "performance_yield": args.performance_yield_threshold,
    }

    print("=" * 95)
    print("  三因子共振 V6 IC 验证 — cutoff-aware OOS")
    print("=" * 95)
    print(f"  固定映射基准样本: {len(codes)} 只 | train 2025-01~09 / test 2025-10~2026-05 | horizon 10/20d")
    print(f"  宇宙模式: {args.universe_mode} | require_visible_evidence={args.require_visible_evidence}")
    print(f"  缓存目录: {cache_dir}")
    print(f"  当前阈值: industry_cycle={thresholds['industry_cycle']}, "
          f"policy_intensity={thresholds['policy_intensity']}, "
          f"performance_yield={thresholds['performance_yield']}")
    print(f"  目标: test_h20 IC ≥ +0.10\n")

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
            thresholds=thresholds,
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
            thresholds=thresholds,
        )
        all_results[f"train_h{horizon}"] = tr
        all_results[f"test_h{horizon}"] = te
        print(f"    train: {tr['n']} cutoffs, mean_rankIC={tr['mean_rank_ic']:+.3f} std={tr.get('std',0):.3f} p={tr['p']:.3f}")
        print(f"    test:  {te['n']} cutoffs, mean_rankIC={te['mean_rank_ic']:+.3f} std={te.get('std',0):.3f} p={te['p']:.3f}")
        for pc in te["per_cutoff"]:
            print(
                f"      {pc['cutoff']} universe={pc['universe_size']:>2} n={pc['n']:>2} "
                f"rankIC={pc['rank_ic']:+.3f} hit={pc['hit']:.0%}"
            )
        print()

    # Threshold scan if requested
    scan_results = None
    if args.scan_thresholds:
        print("  ▶ 阈值扫描模式")
        scan_results = scan_thresholds(test_cuts, codes, meta, horizon=20, min_valid=args.min_valid)
        print(f"    扫描了 {len(scan_results)} 种阈值组合")
        for i, sr in enumerate(scan_results[:5]):
            print(f"    #{i+1}: IC={sr['mean_rank_ic']:+.4f} thresholds={sr['thresholds']}")
        print()

    # Print tuning recommendations
    te20 = all_results["test_h20"]
    print_tuning_recommendations(te20, scan_results, thresholds)

    # Build and write report
    observed = set()
    for r in all_results.values():
        observed.update(r.get("observed_codes", []))

    report = build_report(
        model_version="resonance_v6",
        universe_mode=args.universe_mode,
        universe_codes=sorted(observed),
        results=all_results,
        thresholds=thresholds,
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
        scan_results=scan_results,
    )

    artifact_paths = write_report(report, args.out_dir)
    print("\n  审计产物:")
    for name, path in artifact_paths.items():
        print(f"    {name}: {path}")


if __name__ == "__main__":
    main()