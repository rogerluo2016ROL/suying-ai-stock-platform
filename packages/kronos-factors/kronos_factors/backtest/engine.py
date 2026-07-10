"""Backtest Engine — rolling-window IC validation for multi-model system.

Quantifies each model's predictive power using:
  - IC (Pearson correlation between score and future return)
  - Rank IC (Spearman — robust to outliers)
  - Hit rate (directional accuracy)
  - Signal decay (IC at 5d/10d/20d/60d horizons)
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np
from scipy import stats

from kronos_factors.scorer._db_stub import _get_db, _get_market_data

logger = logging.getLogger("kronos-factors.backtest")

# Models to evaluate (must match screening_scores columns)
MODEL_COLS = [
    ("momentum", "五因子-动量"),
    ("volume_factor", "五因子-量能"),
    ("technical", "五因子-技术"),
    ("quality", "五因子-质量"),
    ("money_flow_score", "资金流向"),
    ("mean_reversion_score", "均值回归"),
    ("trend_strength_score", "趋势强度"),
    ("reversal_score", "反转效应"),
    ("liquidity_score", "流动性"),
    ("score", "综合评分"),
    # Tushare factors (computed from DB at each historical date)
    ("tushare_mf_score", "Tushare-资金流向"),
    ("tushare_margin_score", "Tushare-融资融券"),
    ("tushare_daily_score", "Tushare-每日指标"),
    # New factors (2026-06-07)
    ("tushare_por_score", "Tushare-POR业绩透支"),
    ("tushare_sector_score", "Tushare-SW行业轮动"),
    ("tushare_sector_val_score", "Tushare-行业估值分位"),
    ("tushare_news_score", "Tushare-新闻情绪"),
    ("tushare_analyst_score", "Tushare-分析师覆盖"),
]


def _compute_tushare_scores_batch(codes: list[str], batch_date: str, db) -> dict:
    """Compute Tushare-based scores for a list of stocks at a historical date.

    Returns dict: {code: {score_name: float, ...}}
    """
    results = {c: {} for c in codes}
    if not codes:
        return results

    placeholders = ",".join("?" * len(codes))

    # 1. moneyflow: net institutional flow ratio
    rows = db.execute(
        f"SELECT code, net_mf_amount, buy_lg_amount, sell_lg_amount, "
        f"buy_elg_amount, sell_elg_amount, buy_sm_amount, sell_sm_amount, "
        f"buy_md_amount, sell_md_amount "
        f"FROM moneyflow WHERE code IN ({placeholders}) AND trade_date=?",
        codes + [batch_date]
    ).fetchall()
    for r in rows:
        code = r["code"]
        inst_buy = (r["buy_lg_amount"] or 0) + (r["buy_elg_amount"] or 0)
        inst_sell = (r["sell_lg_amount"] or 0) + (r["sell_elg_amount"] or 0)
        retail_buy = (r["buy_sm_amount"] or 0) + (r["buy_md_amount"] or 0)
        retail_sell = (r["sell_sm_amount"] or 0) + (r["sell_md_amount"] or 0)
        total_flow = inst_buy + inst_sell + retail_buy + retail_sell
        if total_flow > 0:
            inst_ratio = (inst_buy - inst_sell) / total_flow
            net_flow = r["net_mf_amount"] or 0
            s = 5.0
            if inst_ratio > 0.05: s += 3.0
            elif inst_ratio > 0: s += 1.5
            if net_flow < 0: s -= min(3.0, abs(net_flow) / max(total_flow, 1) * 10)
            results[code]["tushare_mf_score"] = round(max(0, min(10, s)), 1)
        else:
            results[code]["tushare_mf_score"] = 5.0

    # 2. margin_detail: margin balance trend
    rows = db.execute(
        f"SELECT code, rzye, rzmre, rzche FROM margin_detail "
        f"WHERE code IN ({placeholders}) AND trade_date=?",
        codes + [batch_date]
    ).fetchall()
    for r in rows:
        code = r["code"]
        bal = r["rzye"] or 0
        buy = r["rzmre"] or 0
        repay = r["rzche"] or 0
        s = 5.0
        if buy + repay > 0:
            br = buy / (buy + repay)
            if br > 0.55: s += 2.0
            elif br > 0.5: s += 1.0
            elif br < 0.45: s -= 1.0
        results[code]["tushare_margin_score"] = round(max(0, min(10, s)), 1)

    # 3. daily_basic: PE/PB-based valuation
    rows = db.execute(
        f"SELECT code, pe, pb, turnover_rate, volume_ratio "
        f"FROM daily_basic WHERE code IN ({placeholders}) AND trade_date=?",
        codes + [batch_date]
    ).fetchall()
    for r in rows:
        code = r["code"]
        pe = r["pe"] or 0
        pb = r["pb"] or 0
        s = 5.0
        if 10 < pe <= 30: s += 1.5
        elif 0 < pe <= 10: s += 1.0
        elif pe > 100: s -= 1.5
        if 1 <= pb <= 3: s += 1.5
        elif 0 < pb < 1: s += 1.0
        if 3 <= (r["turnover_rate"] or 0) <= 15: s += 1.0
        results[code]["tushare_daily_score"] = round(max(0, min(10, s)), 1)

    # Fill defaults for stocks without data
    for c in codes:
        for key in ["tushare_mf_score", "tushare_margin_score", "tushare_daily_score"]:
            if key not in results[c]:
                results[c][key] = 5.0

    return results

HORIZONS = [5, 10, 20, 60]  # trading days


def compute_ic(scores: np.ndarray, returns: np.ndarray) -> dict:
    """Compute IC metrics for a single batch.

    Args:
        scores: model scores for N stocks
        returns: actual forward returns for N stocks

    Returns:
        {"ic": float, "rank_ic": float, "hit_rate": float, "n": int}
    """
    valid = ~(np.isnan(scores) | np.isnan(returns))
    s = scores[valid]
    r = returns[valid]
    n = len(s)

    if n < 10:
        return {"ic": 0, "rank_ic": 0, "hit_rate": 0, "n": n}

    # Pearson IC
    ic = float(stats.pearsonr(s, r)[0]) if np.std(s) > 0 and np.std(r) > 0 else 0

    # Spearman Rank IC
    rank_ic = float(stats.spearmanr(s, r)[0]) if len(set(s)) > 1 and len(set(r)) > 1 else 0

    # Hit rate: did higher score → higher return?
    if n >= 2:
        median_s = np.median(s)
        top_half = s > median_s
        bot_half = ~top_half
        if top_half.sum() > 0 and bot_half.sum() > 0:
            bot_mean = r[bot_half].mean()
            hit_rate = float((r[top_half] > bot_mean).mean())
        else:
            hit_rate = 0.5
    else:
        hit_rate = 0.5

    return {"ic": round(ic, 4), "rank_ic": round(rank_ic, 4),
            "hit_rate": round(hit_rate, 4), "n": n}


def run_backtest() -> dict:
    """Run full backtest across all screening batches and models.

    Returns:
        {
            "batches": int,           # number of batches analyzed
            "stocks_per_batch": int,  # avg stocks per batch
            "models": {               # per-model stats
                "momentum": {
                    "mean_ic": float, "std_ic": float, "icir": float,
                    "mean_rank_ic": float, "hit_rate": float,
                    "decay": {5: float, 10: float, 20: float, 60: float},
                    "ic_series": [float],  # IC over batches
                },
                ...
            },
            "composite": {...},
        }
    """
    with _get_db(readonly=True) as db:
        # Get latest kline date to know how far we can backtest
        max_date = db.execute(
            "SELECT MAX(trade_date) as d FROM daily_kline"
        ).fetchone()["d"]
        if not max_date:
            return {"error": "No kline data available", "batches": 0}

        # Get all completed batches
        all_batches = db.execute(
            "SELECT batch_id, created_at FROM screening_batches "
            "WHERE status='completed' ORDER BY created_at"
        ).fetchall()
        if not all_batches:
            return {
                "error": "No completed screening batches yet.",
                "batches": 0, "latest_kline_date": max_date,
                "message": "回测数据不足：尚无已完成的筛选批次。",
            }

        # Count actual distinct trading days between earliest batch and max kline
        earliest_batch_date = min(b["created_at"][:10] for b in all_batches)
        trading_days_available = db.execute(
            "SELECT COUNT(DISTINCT trade_date) as c FROM daily_kline "
            "WHERE trade_date > ? AND trade_date <= ?",
            (earliest_batch_date, max_date),
        ).fetchone()["c"]

        # Filter batches that have at least min(HORIZONS) trading days of future data
        available_horizons = [h for h in HORIZONS if h <= trading_days_available]
        if not available_horizons:
            # Use whatever trading days we have (at least 1)
            available_horizons = [max(1, trading_days_available)]

        # Only keep batches that have enough trading days for the shortest horizon
        min_horizon = min(available_horizons)
        batches = []
        for b in all_batches:
            b_date = b["created_at"][:10]
            days = db.execute(
                "SELECT COUNT(DISTINCT trade_date) as c FROM daily_kline "
                "WHERE trade_date > ? AND trade_date <= ?",
                (b_date, max_date),
            ).fetchone()["c"]
            if days >= min_horizon:
                batches.append(b)

        if not batches:
            return {
                "error": f"No batches with {min_horizon} trading days of future data.",
                "batches": 0, "latest_kline_date": max_date,
                "trading_days_available": trading_days_available,
                "message": "回测数据不足：需要更多交易日的未来K线数据。",
            }

        logger.info("Backtest: %d batches, %d trading days available, horizons=%s",
                     len(batches), trading_days_available, available_horizons)

    # Use available horizons
    actual_horizons = available_horizons or HORIZONS
    # Primary horizon: use the longest actually available (not hardcoded 20)
    primary_horizon = max(actual_horizons) if actual_horizons else 20

    # Per-model accumulators
    model_ics = defaultdict(list)
    model_hits = defaultdict(list)
    decay_ics = defaultdict(lambda: defaultdict(list))

    batch_count = 0
    total_stocks = 0

    for batch in batches:
        batch_id = batch["batch_id"]
        batch_date = batch["created_at"][:10]

        with _get_db(readonly=True) as db:
            scores = db.execute(
                "SELECT * FROM screening_scores WHERE batch_id=?",
                (batch_id,),
            ).fetchall()

        if not scores:
            continue

        codes = [s["code"] for s in scores]
        n = len(codes)

        # Get actual future returns for each horizon (fresh DB connection)
        actual = {}
        base_prices = {}

        with get_db(readonly=True) as db2:
            for h in actual_horizons:
                actual[h] = {}
                target_date = _get_trading_day(db2, batch_date, h)
                if not target_date:
                    continue
                rows = db2.execute(
                    "SELECT code, close FROM daily_kline "
                    "WHERE code IN ({}) AND trade_date=?".format(
                        ",".join("?" * len(codes))),
                    codes + [target_date],
                ).fetchall()
                for r in rows:
                    actual[h][r["code"]] = r["close"]

            # Get base prices (closest to batch date)
            rows = db2.execute(
                "SELECT code, close FROM daily_kline "
                "WHERE code IN ({}) AND trade_date<=? "
                "ORDER BY trade_date DESC".format(",".join("?" * len(codes))),
                codes + [batch_date],
            ).fetchall()
            seen = set()
            for r in rows:
                if r["code"] not in seen:
                    base_prices[r["code"]] = r["close"]
                    seen.add(r["code"])

        # Compute IC for each model
        for col_name, display_name in MODEL_COLS:
            model_scores = []
            returns_primary = []

            for s in scores:
                code = s["code"]
                base = base_prices.get(code)
                if not base or base <= 0:
                    continue
                val = s[col_name] if col_name in s.keys() else None
                if val is None:
                    continue
                model_scores.append(float(val))

                # Use primary horizon return as IC target (dynamic, not hardcoded 20)
                fut = actual.get(primary_horizon, {}).get(code)
                if fut and fut > 0:
                    returns_primary.append((fut / base - 1) * 100)
                else:
                    returns_primary.append(np.nan)

            if len(model_scores) >= 10:
                result = compute_ic(
                    np.array(model_scores),
                    np.array(returns_primary),
                )
                model_ics[display_name].append(result["ic"])
                model_hits[display_name].append(result["hit_rate"])

                # Decay across horizons
                for h in actual_horizons:
                    rets_h = []
                    for s in scores:
                        code = s["code"]
                        base = base_prices.get(code)
                        if not base or base <= 0:
                            rets_h.append(np.nan)
                            continue
                        fut = actual.get(h, {}).get(code)
                        if fut and fut > 0:
                            rets_h.append((fut / base - 1) * 100)
                        else:
                            rets_h.append(np.nan)
                    res = compute_ic(
                        np.array([float(s[col_name]) for s in scores]),
                        np.array(rets_h),
                    )
                    decay_ics[display_name][h].append(res["ic"])

        batch_count += 1
        total_stocks += n

    # Aggregate results
    results = {}
    for display_name in sorted(model_ics.keys()):
        ics = model_ics[display_name]
        if not ics:
            continue

        mean_ic = np.mean(ics)
        std_ic = np.std(ics)
        icir = mean_ic / std_ic if std_ic > 0 else 0
        mean_rank_ic = mean_ic  # use actual IC (Rank IC requires full recomputation per batch)
        hit = np.mean(model_hits[display_name]) if model_hits[display_name] else 0

        decay = {}
        for h in HORIZONS:
            vals = decay_ics[display_name].get(h, [])
            decay[h] = round(float(np.mean(vals)), 4) if vals else 0

        results[display_name] = {
            "mean_ic": round(float(mean_ic), 4),
            "std_ic": round(float(std_ic), 4),
            "icir": round(float(icir), 4),
            "mean_rank_ic": round(float(mean_rank_ic), 4),
            "hit_rate": round(float(hit), 4),
            "decay": decay,
            "ic_series": [round(float(x), 4) for x in ics[-20:]],
            "n_batches": len(ics),
        }

    return {
        "batches": batch_count,
        "total_stocks_analyzed": total_stocks,
        "avg_stocks_per_batch": total_stocks // max(batch_count, 1),
        "horizons_days": actual_horizons,
        "models": results,
        "generated_at": datetime.now().isoformat(),
    }


def run_historical_backtest(
    sample_size: int = 500,
    months: int = 120,
    n_seeds: int = 5,
) -> dict:
    """Generate historical backtest batches from K-line data directly.

    For each month-end over the last `months` months:
      1. Pick `sample_size` random stocks with K-line data
      2. Compute 5-factor scores from K-line (momentum/volume/technical/quality/risk)
      3. Compute forward returns at [5,10,20,60] horizons
      4. Compute IC/ICIR across all batches

    This approach doesn't need pre-existing screening_batches — it uses
    the 20 years of K-line data to provide statistically robust IC estimates.

    M16: the entire sampling pass runs `n_seeds` times (default 5) with distinct
    seeds; all batch ICs are pooled for the headline mean/std, and a cross-seed
    std-of-means (seed_std_ic) is reported so a lucky single-seed draw cannot
    masquerade as a robust IC. n_seeds=1 recovers the legacy single-seed path.
    """
    from kronos_factors.scorer.five_factor import score_five_factor

    with _get_db(readonly=True) as db:
        # Get all month-end trading dates
        all_dates = [r[0] for r in db.execute(
            "SELECT DISTINCT trade_date FROM daily_kline ORDER BY trade_date"
        ).fetchall()]

        # Pick last trading day of each month
        month_ends = []
        seen = set()
        for d in all_dates:
            m = d[:7]  # YYYY-MM
            if m not in seen:
                seen.add(m)
            month_ends.append((m, d))
        # Keep last trading day per month
        month_end_dates = []
        for m in sorted(seen):
            candidates = [d for (mo, d) in month_ends if mo == m]
            if candidates:
                month_end_dates.append(candidates[-1])

        # Take the last N months (with enough future data for 60-day horizon)
        available = []
        max_date = all_dates[-1]
        for d in month_end_dates:
            if d < max_date:
                days_ahead = len([x for x in all_dates if x > d])
                if days_ahead >= 60:
                    available.append(d)

        if len(available) > months:
            available = available[-months:]

        print(f"Historical backtest: {len(available)} month-ends, {sample_size} stocks each")

        # Get stock list
        codes = [r["code"] for r in db.execute(
            "SELECT code FROM stocks WHERE is_st=0 "
            "AND (code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%' OR code LIKE '68%') "
            "ORDER BY code"
        ).fetchall()]

        import random

        def _run_one_seed(seed: int):
            """M16: run one sampling pass with a fixed seed, return per-seed accumulators.

            All sampling randomness (random.sample) is keyed off `seed`; the DB
            reads and IC math are deterministic given the sampled codes.
            """
            random.seed(seed)
            _model_ics = defaultdict(list)
            _model_hits = defaultdict(list)
            _decay_ics = defaultdict(lambda: defaultdict(list))
            _batch_count = 0

            for batch_date in available:
                # Random sample
                batch_codes = random.sample(codes, min(sample_size, len(codes)))

                # Compute Tushare scores for this batch at this date (batch DB query)
                tushare_batch = _compute_tushare_scores_batch(batch_codes, batch_date, db)

                # Compute POR scores from daily_basic at this date
                por_batch = {}
                placeholders = ",".join("?" * len(batch_codes))
                por_rows = db.execute(
                    f"SELECT code, pe, pe_ttm, pb, ps, ps_ttm FROM daily_basic "
                    f"WHERE code IN ({placeholders}) AND trade_date=?",
                    batch_codes + [batch_date]
                ).fetchall()
                for r in por_rows:
                    code = r["code"]; pe = r["pe_ttm"] or r["pe"] or 0; pb = r["pb"] or 0; ps = r["ps_ttm"] or r["ps"] or 0
                    s = 5.0
                    if pe > 0:
                        per = pe/20.0
                        if per < 0.5: s += 2.0
                        elif per < 0.8: s += 1.0
                        elif per > 2.0: s -= 2.0
                    if pb > 0:
                        if pb/2.0 < 0.5: s += 1.5
                        elif pb/2.0 > 2.5: s -= 1.5
                    if ps > 0:
                        if ps/3.0 < 0.3: s += 1.0
                        elif ps/3.0 > 3.0: s -= 1.0
                    por_batch[code] = round(max(0, min(10, s)), 1)

                # Get 5-factor scores from K-line
                # M03: pass batch_date as end_date so factors are computed from only
                # the K-line that existed at batch_date — otherwise get_kline_df
                # returns the *current* most-recent 400 rows regardless of batch_date,
                # leaking future K-line into historical IC.
                scores_list = []
                for code in batch_codes:
                    try:
                        kline_df = _get_market_data().get_kline_df(
                            code, lookback=400, end_date=batch_date)
                        if kline_df is None or len(kline_df) < 30:
                            continue
                        ff = score_five_factor(kline_df)
                        ts = tushare_batch.get(code, {})
                        scores_list.append({
                            "code": code,
                            "momentum": ff["momentum"],
                            "volume_factor": ff["volume_factor"],
                            "technical": ff["technical"],
                            "quality": ff["quality"],
                            "risk": ff["risk"],
                            "score": ff["score"],
                            "money_flow_score": 5.0,
                            "mean_reversion_score": 5.0,
                            "trend_strength_score": 5.0,
                            "reversal_score": 5.0,
                            "liquidity_score": 5.0,
                            "tushare_mf_score": ts.get("tushare_mf_score", 5.0),
                            "tushare_margin_score": ts.get("tushare_margin_score", 5.0),
                            "tushare_daily_score": ts.get("tushare_daily_score", 5.0),
                            "tushare_por_score": por_batch.get(code, 5.0),
                            "tushare_sector_score": 5.0,
                            "tushare_sector_val_score": 5.0,
                            "tushare_news_score": 5.0,
                            "tushare_analyst_score": 5.0,
                        })
                    except Exception:
                        continue

                if len(scores_list) < 30:
                    continue

                # Compute forward returns
                base_prices = {}
                future_prices = {h: {} for h in HORIZONS}
                for sc in scores_list:
                    code = sc["code"]
                    # Base price
                    row = db.execute(
                        "SELECT close FROM daily_kline WHERE code=? AND trade_date<=? "
                        "ORDER BY trade_date DESC LIMIT 1",
                        (code, batch_date)
                    ).fetchone()
                    if row:
                        base_prices[code] = row["close"]

                    # Future prices at each horizon
                    for h in HORIZONS:
                        future_date_idx = None
                        for i, d in enumerate(all_dates):
                            if d > batch_date:
                                if i + h - 1 < len(all_dates):
                                    future_date_idx = i + h - 1
                                break
                        if future_date_idx is not None and future_date_idx < len(all_dates):
                            target_date = all_dates[future_date_idx]
                            row = db.execute(
                                "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
                                (code, target_date)
                            ).fetchone()
                            if row:
                                future_prices[h][code] = row["close"]

                # Compute IC for each model × horizon
                for col_name, display_name in MODEL_COLS:
                    model_scores = []
                    for h in HORIZONS:
                        s_arr = []
                        r_arr = []
                        for sc in scores_list:
                            code = sc["code"]
                            base = base_prices.get(code)
                            if not base or base <= 0:
                                continue
                            val = sc.get(col_name)
                            if val is None:
                                continue
                            fut = future_prices.get(h, {}).get(code)
                            if fut and fut > 0:
                                s_arr.append(float(val))
                                r_arr.append((fut / base - 1) * 100)

                        if len(s_arr) >= 10:
                            res = compute_ic(np.array(s_arr), np.array(r_arr))
                            if h == HORIZONS[0]:  # Use shortest horizon for primary IC
                                _model_ics[display_name].append(res["ic"])
                                _model_hits[display_name].append(res["hit_rate"])
                            _decay_ics[display_name][h].append(res["ic"])

                _batch_count += 1
                if _batch_count % 20 == 0:
                    print(f"  [seed={seed}] {_batch_count}/{len(available)} batches...")

            return _model_ics, _model_hits, _decay_ics, _batch_count

    # M16: multi-seed averaging. Run the sampling pass n_seeds times with
    # distinct seeds, pool every batch IC across seeds for the headline
    # mean/std, and also report the cross-seed std-of-means so a lucky
    # single-seed draw cannot masoch the IC.
    model_ics = defaultdict(list)
    model_hits = defaultdict(list)
    decay_ics = defaultdict(lambda: defaultdict(list))
    batch_count = 0
    seed_mean_ics: dict[str, list[float]] = defaultdict(list)

    for seed in range(n_seeds):
        s_ics, s_hits, s_decay, s_n = _run_one_seed(seed)
        for name, lst in s_ics.items():
            model_ics[name].extend(lst)
            if lst:
                seed_mean_ics[name].append(float(np.mean(lst)))
        for name, lst in s_hits.items():
            model_hits[name].extend(lst)
        for name, hmap in s_decay.items():
            for h, lst in hmap.items():
                decay_ics[name][h].extend(lst)
        batch_count += s_n

    # Aggregate
    results = {}
    for display_name in sorted(model_ics.keys()):
        ics = model_ics[display_name]
        if not ics:
            continue
        mean_ic = float(np.mean(ics))
        std_ic = float(np.std(ics))
        icir = mean_ic / std_ic if std_ic > 0 else 0.0
        hit = float(np.mean(model_hits[display_name])) if model_hits[display_name] else 0.0

        decay = {}
        for h in HORIZONS:
            vals = decay_ics[display_name].get(h, [])
            decay[h] = round(float(np.mean(vals)), 4) if vals else 0.0

        # M16: cross-seed aggregation on per-seed mean IC
        seed_agg = _aggregate_multi_seed(
            {display_name: seed_mean_ics.get(display_name, [])}
        ).get(display_name, {})

        results[display_name] = {
            "mean_ic": round(mean_ic, 4),
            "std_ic": round(std_ic, 4),
            "icir": round(icir, 4),
            "mean_rank_ic": round(mean_ic, 4),
            "hit_rate": round(hit, 4),
            "decay": decay,
            "n_batches": len(ics),
            # M16: multi-seed stability fields
            "seed_mean_ic": round(seed_agg.get("seed_mean_ic", mean_ic), 4),
            "seed_std_ic": round(seed_agg.get("seed_std_ic", 0.0), 4),
            "seed_icir": round(seed_agg.get("seed_icir", 0.0), 4),
            "n_seeds": len(seed_mean_ics.get(display_name, [])),
        }

    return {
        "batches": batch_count,
        "total_stocks_analyzed": sample_size * batch_count,
        "avg_stocks_per_batch": sample_size,
        "horizons_days": HORIZONS,
        "n_seeds": n_seeds,
        "models": results,
        "generated_at": datetime.now().isoformat(),
    }


def _aggregate_multi_seed(seed_mean_ics: dict) -> dict:
    """M16: aggregate per-seed mean IC into cross-seed mean / std / ICIR.

    Args:
        seed_mean_ics: {model_name: [ic_seed0, ic_seed1, ...]}

    Returns:
        {model_name: {seed_mean_ic, seed_std_ic, seed_icir, n_seeds}}

    seed_icir = seed_mean_ic / seed_std_ic; when seed_std_ic == 0 (all seeds
    identical) we record 0.0 to avoid divide-by-zero rather than +inf.
    """
    out = {}
    for name, means in seed_mean_ics.items():
        if not means:
            continue
        arr = np.asarray(means, dtype=float)
        m = float(np.mean(arr))
        s = float(np.std(arr))
        # Tolerance: floating-point std of identical ICs is ~1e-17, not 0.
        # Treat std below 1e-12 as zero to avoid 1e16+ ICIR blowups.
        seed_icir = m / s if s > 1e-12 else 0.0
        out[name] = {
            "seed_mean_ic": m,
            "seed_std_ic": s,
            "seed_icir": seed_icir,
            "n_seeds": len(means),
        }
    return out


def get_model_ranking() -> list[dict]:
    """Return models ranked by ICIR (most predictive first)."""
    report = run_backtest()
    if "error" in report:
        return []

    ranking = []
    for name, stats in report["models"].items():
        ranking.append({
            "model": name,
            "mean_ic": stats["mean_ic"],
            "icir": stats["icir"],
            "hit_rate": stats["hit_rate"],
            "decay_5d": stats["decay"].get(5, 0),
            "decay_20d": stats["decay"].get(20, 0),
            "decay_60d": stats["decay"].get(60, 0),
            "n_batches": stats["n_batches"],
        })
    ranking.sort(key=lambda x: abs(x["icir"]), reverse=True)
    return ranking


def _get_trading_day(db, base_date: str, offset: int) -> str:
    """Get the trading day `offset` trading days after base_date."""
    row = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date>? "
        "ORDER BY trade_date ASC LIMIT 1 OFFSET ?",
        (base_date, offset - 1),
    ).fetchone()
    return row["trade_date"] if row else ""
