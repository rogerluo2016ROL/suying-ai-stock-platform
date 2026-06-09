#!/usr/bin/env python3
"""Factor weight calibration via rolling-window forward IC analysis.

Computes IC/ICIR for each factor using historical forward returns,
then suggests optimized weights. Can auto-apply to screening_top50.py.

Usage:
    python tools/calibrate_weights.py              # Analyze, show IC stats
    python tools/calibrate_weights.py --apply       # Auto-update ALL mode weights
    python tools/calibrate_weights.py --mode short  # Analyze short mode factors
"""

import argparse, json, os, sys, re, time
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "src"))
sys.path.insert(0, _PROJ)

from webui.services.database import get_db
from webui.services.market_data_service import MarketDataService
from webui.services.screener_service import score_five_factor
from webui.services.advanced_models import (
    score_money_flow, score_mean_reversion, score_trend_strength,
    score_reversal, score_liquidity, get_tushare_scores, score_hard_tech,
)

# ── Factor definitions ──
ALL_FACTORS = [
    ("quality",      "五因子-质量"),
    ("volume",       "五因子-量能"),
    ("composite",    "综合评分"),
    ("technical",    "五因子-技术"),
    ("momentum",     "五因子-动量"),
    ("margin",       "融资融券(负)"),
    ("moneyflow",    "资金流向(负)"),
    ("daily_basic",  "每日指标"),
    ("financial",    "财报质量"),
    ("hard_tech",    "硬科技"),
    ("growth",       "成长性"),
    ("short_term",   "短线技术"),
    ("long_term",    "长线价值"),
    ("por",          "POR估值"),
]


def compute_factor_scores(code, df):
    """Compute all factor scores for a single stock. Returns dict."""
    try:
        ff = score_five_factor(df)
        mf = score_money_flow(df)
        ts_ = score_trend_strength(df)
        gr_obj = None
        lt_obj = None
        from tools.screening_top50 import score_short_term, score_long_term, score_growth
        st = score_short_term(df)
        lt = score_long_term(code)
        gr = score_growth(code)
        ht = score_hard_tech(code)

        # Tushare scores (cached per stock)
        ts_scores = get_tushare_scores(code) if os.environ.get("TUSHARE_TOKEN") else {}

        return {
            "quality":     ff["quality"],
            "volume":      ff["volume_factor"],
            "composite":   ff["score"] / 25 * 10,
            "technical":   ff["technical"],
            "momentum":    ff["momentum"],
            "margin":      ts_scores.get("tushare_margin", {}).get("score", 5),
            "moneyflow":   ts_scores.get("tushare_moneyflow", {}).get("score", 5),
            "daily_basic": ts_scores.get("tushare_daily_basic", {}).get("score", 5),
            "financial":   ts_scores.get("tushare_financial", {}).get("score", 5),
            "hard_tech":   ht["score"] * 2,
            "growth":      gr["score"],
            "short_term":  st["score"],
            "long_term":   lt["score"],
            "por":         ts_scores.get("tushare_por", {}).get("score", 5),
        }
    except:
        return None


def run_calibration(codes, cutoff_date, forward_days=60) -> dict:
    """For each stock, compute factor scores at cutoff and forward return."""
    results = {name: {"scores": [], "returns": []} for _, name in ALL_FACTORS}

    cutoff_str = cutoff_date.strftime("%Y-%m-%d")
    t0 = time.time()
    valid = 0

    for i, code in enumerate(codes):
        try:
            df = MarketDataService.get_kline_df(code, lookback=400)
            if df is None or len(df) < 80:
                continue

            ts_col = 'timestamps' if 'timestamps' in df.columns else 'trade_date'
            df_hist = df[df[ts_col] <= cutoff_str]
            df_future = df[df[ts_col] > cutoff_str]

            if len(df_hist) < 60 or len(df_future) < 20:
                continue

            prices_hist = df_hist['close'].values
            prices_fwd = df_future['close'].values
            forward_ret = (prices_fwd[-1] / prices_hist[-1] - 1) * 100

            scores = compute_factor_scores(code, df_hist)
            if scores is None:
                continue

            for key, name in ALL_FACTORS:
                if key in scores:
                    results[name]["scores"].append(scores[key])
                    results[name]["returns"].append(forward_ret)

            valid += 1
            if (i+1) % 100 == 0:
                elapsed = time.time() - t0
                print(f"  {valid} valid ({i+1}/{len(codes)} scanned, {elapsed:.0f}s)")
        except:
            pass

    # Compute IC for each factor
    ic_stats = {}
    for name, data in results.items():
        if len(data["scores"]) >= 30:
            scores_arr = np.array(data["scores"])
            rets_arr = np.array(data["returns"])
            if np.std(scores_arr) > 0:
                ic = np.corrcoef(scores_arr, rets_arr)[0, 1]
                ic = 0.0 if np.isnan(ic) else ic

                # ICIR: IC / std(IC) — simulated as single-point estimate
                ic_stats[name] = {
                    "ic": round(float(ic), 4),
                    "n": len(data["scores"]),
                }

    return ic_stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Auto-apply weights to screening_top50.py")
    parser.add_argument("--mode", default="all", choices=["short","all"])
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--n-stocks", type=int, default=500, help="Sample size per window")
    args = parser.parse_args()
    os.chdir(_PROJ)

    with get_db(readonly=True) as db:
        max_date = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()[0]
    max_dt = datetime.strptime(max_date, "%Y-%m-%d")

    # 3 windows: 2mo, 4mo, 6mo ago
    windows = []
    for months_back in [2, 4, 6]:
        cutoff = max_dt - timedelta(days=months_back * 30)
        windows.append(cutoff)

    print(f"校准窗口: {[w.strftime('%Y-%m-%d') for w in windows]}")
    print(f"每窗口采样: {args.n_stocks} 只\n")

    # Get stock sample
    with get_db(readonly=True) as db:
        codes = [r['code'] for r in db.execute(
            f"SELECT code FROM stocks WHERE is_st=0 ORDER BY RANDOM() LIMIT {args.n_stocks}"
        ).fetchall()]

    all_ics = defaultdict(list)
    for w, cutoff in enumerate(windows):
        print(f"{'='*50}")
        print(f"Window {w+1}: cutoff={cutoff.strftime('%Y-%m-%d')}")
        print(f"{'='*50}")
        ic_stats = run_calibration(codes, cutoff)

        for name, stats in ic_stats.items():
            all_ics[name].append(stats["ic"])

        # Show top factors this window
        sorted_factors = sorted(ic_stats.items(), key=lambda x: -abs(x[1]["ic"]))
        print(f"  Top 5 IC:")
        for name, stats in sorted_factors[:5]:
            sign = "+" if stats["ic"] > 0 else ""
            print(f"    {name:<18} IC={sign}{stats['ic']:.4f} (n={stats['n']})")
        print()

    # Aggregate across windows
    print(f"\n{'='*60}")
    print(f"  跨窗口 IC 汇总 ({args.mode}模式)")
    print(f"{'='*60}")
    print(f"{'因子':<18} {'IC均值':>8} {'IC标准差':>8} {'ICIR':>8} {'建议权重':>8}")
    print(f"{'-'*55}")

    recommendations = []
    for _, name in ALL_FACTORS:
        if name in all_ics and len(all_ics[name]) >= 2:
            ic_vals = all_ics[name]
            ic_mean = np.mean(ic_vals)
            ic_std = np.std(ic_vals) if len(ic_vals) > 1 else 0.01
            icir = ic_mean / ic_std if ic_std > 0 else 0

            # Suggested weight: proportional to |ICIR|, maintain negative for short factors
            w = abs(icir) * 0.08
            if ic_mean < 0:
                w = -w  # keep negative for short factors

            recommendations.append((name, ic_mean, ic_std, icir, w))
            print(f"  {name:<18} {ic_mean:>+7.4f} {ic_std:>8.4f} {icir:>+7.3f} {w:>+7.3f}")

    # Normalize weights
    if recommendations:
        weights = [(name, w) for name, _, _, _, w in recommendations]
        abs_sum = sum(abs(w) for _, w in weights)
        if abs_sum > 0:
            norm_weights = [(name, w/abs_sum) for name, w in weights]
            print(f"\n  归一化权重:")
            for name, w in sorted(norm_weights, key=lambda x: -x[1]):
                print(f"    {name:<18} {w:+.4f}")

    # Auto-apply
    if args.apply:
        print(f"\n  ⚠️ --apply 功能待实现 (需解析screening_top50.py并替换权重)")

    # Save
    out_path = f"outputs/calibration_{args.mode}_{datetime.now().strftime('%Y%m%d-%H%M')}.json"
    with open(out_path, 'w') as f:
        json.dump({name: {"ics": all_ics[name]} for name in all_ics}, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
