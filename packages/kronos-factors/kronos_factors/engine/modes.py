"""Multi-factor mode engines — SHORT / LONG / ALL / Chokepoint.

Each mode is a StrategyEngine subclass with mode-specific factor weights,
hard filters, and scoring logic. Extracted from Kronos/tools/screening_top50.py
"""

import os, time
import numpy as np
import pandas as pd

from kronos_factors.base import StrategyEngine, ScreeningResult
from kronos_factors.scorer._db_stub import _get_db, _get_market_data
from kronos_factors.scorer.five_factor import score_five_factor
from kronos_factors.scorer.advanced_factors import (
    score_money_flow, score_mean_reversion, score_trend_strength,
    score_reversal, score_liquidity, score_hard_tech, get_tushare_scores,
)
from kronos_factors.scorer.screening_scorers import (
    score_short_term, score_long_term, score_growth,
    score_identifiability, score_margin_momentum, score_chokepoint,
    get_stock_themes, check_multi_timeframe_trend,
    check_institutional_funds, get_market_regime, get_sector_momentum,
    assess_risk, build_rationale, compute_trade_levels,
    should_exclude, generate_devils_advocate,
)


# ── Shared factor computation (used by all multi-factor modes) ──

def _compute_shared_factors(code: str, df: pd.DataFrame):
    """Compute all shared factors for a single stock. Called by every mode."""
    ff = score_five_factor(df)
    mf = score_money_flow(df)
    mr = score_mean_reversion(df)
    ts_ = score_trend_strength(df)
    rev = score_reversal(df)
    liq = score_liquidity(df)
    st = score_short_term(df)
    lt = score_long_term(code)
    gr = score_growth(code)
    ht = score_hard_tech(code)
    ts_scores = get_tushare_scores(code) if os.environ.get("TUSHARE_TOKEN") else {}
    th = get_stock_themes(code, df, ht)
    return ff, mf, mr, ts_, rev, liq, st, lt, gr, ht, ts_scores, th


# ═══════════════════════════════════════════════════════════════
# Chokepoint Engine
# ═══════════════════════════════════════════════════════════════

class ChokepointEngine(StrategyEngine):
    """Supply chain chokepoint / 卡脖子 technology screening."""

    mode = "chokepoint"

    def get_factor_weights(self) -> dict[str, float]:
        return {"chokepoint": 1.0}

    def run(self, top_n: int = 30, **kwargs) -> ScreeningResult:
        t0 = time.time()
        picks = []
        excluded = 0

        with _get_db(readonly=True) as db:
            codes = [r["code"] for r in db.execute(
                "SELECT code FROM stocks WHERE is_st=0 ORDER BY code").fetchall()]
            names = {r["code"]: r["name"] for r in db.execute(
                "SELECT code, name FROM stocks").fetchall()}

        for code in codes:
            try:
                df = _get_market_data().get_kline_df(code, lookback=400)
                if df is None or len(df) < 30:
                    continue
                if should_exclude(code, df):
                    excluded += 1; continue

                cp = score_chokepoint(code)
                if cp["score"] < 6.0:
                    excluded += 1; continue

                price = float(df["close"].values[-1])
                cp_score = cp["score"]
                idf = score_identifiability(code, df)
                _, _, _, _, _, _, _, _, _, ht, _, th = _compute_shared_factors(code, df)
                devils = generate_devils_advocate(code, cp, df)

                picks.append({
                    "code": code, "name": names.get(code, "?"),
                    "price": round(price, 2),
                    "score": round(cp_score * 2.5, 1),
                    "grade": "S" if cp_score > 8 else ("A" if cp_score > 6 else "B"),
                    "cp_score": cp_score, "devils": devils,
                    "cp_signals": cp.get("signals", []),
                })
            except Exception:
                excluded += 1

        picks.sort(key=lambda x: x["score"], reverse=True)
        picks = picks[:top_n]

        return ScreeningResult(
            mode=self.mode,
            picks=picks,
            total_scored=len(picks),
            total_excluded=excluded,
            elapsed=time.time() - t0,
        )


# ═══════════════════════════════════════════════════════════════
# SHORT Mode Engine
# ═══════════════════════════════════════════════════════════════

class ShortModeEngine(StrategyEngine):
    """Short-term multi-factor screening — 14-factor ICIR-weighted.

    Hard filter: weekly + monthly MA must be bullish.
    """

    mode = "short"

    def get_factor_weights(self) -> dict[str, float]:
        return {
            "short_term": 0.30, "volume_factor": 0.10, "trend_strength": 0.08,
            "five_factor_composite": 0.07, "momentum_inverted": 0.06,
            "money_flow": 0.05, "margin_momentum": 0.07,
            "top_list": 0.08, "top_inst": 0.06,
            "analyst": 0.03, "hk_hold": 0.03, "identifiability": 0.07,
        }

    def run(self, top_n: int = 30, **kwargs) -> ScreeningResult:
        t0 = time.time()
        regime = get_market_regime()
        picks = []
        excluded = 0
        scored = 0

        with _get_db(readonly=True) as db:
            codes = [r["code"] for r in db.execute(
                "SELECT code FROM stocks WHERE is_st=0 ORDER BY code").fetchall()]
            names = {r["code"]: r["name"] for r in db.execute(
                "SELECT code, name FROM stocks").fetchall()}

        for code in codes:
            try:
                df = _get_market_data().get_kline_df(code, lookback=400)
                if df is None or len(df) < 30:
                    continue
                if should_exclude(code, df):
                    excluded += 1; continue

                # Hard filter: weekly + monthly bull
                mtf = check_multi_timeframe_trend(code)
                if not mtf.get("weekly_ok") or not mtf.get("monthly_ok"):
                    excluded += 1; continue

                ff, mf, mr, ts_, rev, liq, st, lt, gr, ht, ts_scores, th = (
                    _compute_shared_factors(code, df))
                mg = score_margin_momentum(code)
                idf = score_identifiability(code, df)

                models = [
                    (st["score"], 0.30),
                    (ff["volume_factor"], 0.10),
                    (ts_["score"], 0.08),
                    (ff["score"] / 25 * 10, 0.07),
                    ((8.0 - ff["momentum"]), 0.06),
                    (mf["score"], 0.05),
                    (mg["score"], 0.07),
                    (ts_scores.get("tushare_top_list", {}).get("score", 5), 0.08),
                    (ts_scores.get("tushare_top_inst", {}).get("score", 5), 0.06),
                    (ts_scores.get("tushare_analyst", {}).get("score", 5), 0.03),
                    (ts_scores.get("tushare_hk_hold", {}).get("score", 5), 0.03),
                    (idf["score"], 0.07),
                ]

                # Regime-adaptive adjustment
                hint = regime.get("factor_hint", "")
                if hint == "quality_defensive":
                    models = [(s, w * 0.7 if i == 0 else w) for i, (s, w) in enumerate(models)]
                    models.append((ff["quality"], 0.03))
                    models.append((abs(ff["risk"]), 0.02))
                elif hint == "momentum_weighted":
                    models = [(s, w * 1.15 if i < 3 else w) for i, (s, w) in enumerate(models)]

                # Multi-timeframe bonus
                mtf_bonus = 0.0
                if mtf.get("weekly_ok"): mtf_bonus += 0.3
                if mtf.get("monthly_ok"): mtf_bonus += 0.2

                sector_score = get_sector_momentum(code)
                tw = sum(w for _, w in models) + 0.03
                composite = sum(s * w for s, w in models) / tw
                composite += regime.get("bonus", 0) + mtf_bonus + sector_score * 0.03 / tw

                score_25 = max(0, min(25, composite * 2.5))
                price = float(df["close"].values[-1])
                levels = compute_trade_levels(df, mode="short")
                risk = assess_risk(code, df, {}, mode="short")
                rationale = build_rationale(code, names.get(code, "?"), df, {}, mode="short", levels=levels)

                picks.append({
                    "code": code, "name": names.get(code, "?"),
                    "price": round(price, 2), "score": round(score_25, 1),
                    "grade": "S" if score_25 >= 16 else ("A" if score_25 >= 12 else (
                        "B" if score_25 >= 7 else "C")),
                    "entry_price": levels.get("entry"), "stop_loss": levels.get("stop"),
                    "target_price": levels.get("target"), "rationale": rationale,
                    "risk_level": risk.get("risk_level"),
                })
                scored += 1
            except Exception:
                excluded += 1

        picks.sort(key=lambda x: x["score"], reverse=True)
        picks = picks[:top_n]

        return ScreeningResult(
            mode=self.mode, picks=picks, total_scored=scored,
            total_excluded=excluded, market_env=regime.get("label", "NEUTRAL"),
            elapsed=time.time() - t0,
        )


# ═══════════════════════════════════════════════════════════════
# LONG Mode Engine
# ═══════════════════════════════════════════════════════════════

class LongModeEngine(StrategyEngine):
    """Long-term value screening — fundamental + institutional fund confirmation."""

    mode = "long"

    def get_factor_weights(self) -> dict[str, float]:
        return {
            "long_term_value": 0.40, "growth": 0.35, "hard_tech": 0.10,
            "financial": 0.08, "daily_basic": 0.05, "por": 0.02,
        }

    def run(self, top_n: int = 30, **kwargs) -> ScreeningResult:
        t0 = time.time()
        regime = get_market_regime()
        picks = []
        excluded = 0
        scored = 0

        with _get_db(readonly=True) as db:
            codes = [r["code"] for r in db.execute(
                "SELECT code FROM stocks WHERE is_st=0 ORDER BY code").fetchall()]
            names = {r["code"]: r["name"] for r in db.execute(
                "SELECT code, name FROM stocks").fetchall()}

        for code in codes:
            try:
                df = _get_market_data().get_kline_df(code, lookback=400)
                if df is None or len(df) < 30:
                    continue
                if should_exclude(code, df):
                    excluded += 1; continue

                ff, mf, mr, ts_, rev, liq, st, lt, gr, ht, ts_scores, th = (
                    _compute_shared_factors(code, df))

                models = [
                    (lt["score"], 0.40), (gr["score"], 0.35),
                    (ht["score"] * 2, 0.10),
                    (ts_scores.get("tushare_financial", {}).get("score", 5), 0.08),
                    (ts_scores.get("tushare_daily_basic", {}).get("score", 5), 0.05),
                    (ts_scores.get("tushare_por", {}).get("score", 5), 0.02),
                ]

                # Institutional fund bonus
                inst = check_institutional_funds(code)
                inst_bonus = 0.5 if inst.get("has_institutional") else 0.0

                tw = sum(w for _, w in models)
                composite = sum(s * w for s, w in models) / tw
                composite += regime.get("bonus", 0) + inst_bonus

                score_25 = max(0, min(25, composite * 2.5))
                price = float(df["close"].values[-1])
                levels = compute_trade_levels(df, mode="long")
                risk = assess_risk(code, df, {}, mode="long")
                rationale = build_rationale(code, names.get(code, "?"), df,
                                            {"long_term": lt, "growth": gr},
                                            mode="long", levels=levels)

                picks.append({
                    "code": code, "name": names.get(code, "?"),
                    "price": round(price, 2), "score": round(score_25, 1),
                    "grade": "S" if score_25 >= 16 else ("A" if score_25 >= 12 else (
                        "B" if score_25 >= 7 else "C")),
                    "entry_price": levels.get("entry"), "stop_loss": levels.get("stop"),
                    "target_price": levels.get("target"), "rationale": rationale,
                    "risk_level": risk.get("risk_level"),
                    "institutional_funds": inst.get("funds", []),
                })
                scored += 1
            except Exception:
                excluded += 1

        picks.sort(key=lambda x: x["score"], reverse=True)
        picks = picks[:top_n]

        return ScreeningResult(
            mode=self.mode, picks=picks, total_scored=scored,
            total_excluded=excluded, market_env=regime.get("label", "NEUTRAL"),
            elapsed=time.time() - t0,
        )


# ═══════════════════════════════════════════════════════════════
# ALL Mode Engine
# ═══════════════════════════════════════════════════════════════

class AllModeEngine(StrategyEngine):
    """Comprehensive multi-factor — 14-factor ICIR-calibrated, regime-adaptive."""

    mode = "all"

    def get_factor_weights(self) -> dict[str, float]:
        return {
            "technical": 0.040, "volume_factor": 0.028, "composite": 0.027,
            "momentum_inverted": 0.025, "quality": 0.025,
            "daily_basic": 0.020, "financial": 0.010,
            "hard_tech": 0.012, "growth": 0.018,
            "short_term": 0.005, "long_term": 0.005,
            "por": 0.010, "identifiability": 0.008,
        }

    def run(self, top_n: int = 50, **kwargs) -> ScreeningResult:
        t0 = time.time()
        regime = get_market_regime()
        picks = []
        excluded = 0
        scored = 0

        with _get_db(readonly=True) as db:
            codes = [r["code"] for r in db.execute(
                "SELECT code FROM stocks WHERE is_st=0 ORDER BY code").fetchall()]
            names = {r["code"]: r["name"] for r in db.execute(
                "SELECT code, name FROM stocks").fetchall()}

        for code in codes:
            try:
                df = _get_market_data().get_kline_df(code, lookback=400)
                if df is None or len(df) < 30:
                    continue
                if should_exclude(code, df):
                    excluded += 1; continue

                ff, mf, mr, ts_, rev, liq, st, lt, gr, ht, ts_scores, th = (
                    _compute_shared_factors(code, df))
                idf_all = score_identifiability(code, df)

                models = [
                    (ff["technical"], 0.040),
                    (ff["volume_factor"], 0.028),
                    (ff["score"] / 25 * 10, 0.027),
                    ((8.0 - ff["momentum"]), 0.025),
                    (ff["quality"], 0.025),
                    (ts_scores.get("tushare_daily_basic", {}).get("score", 5), 0.020),
                    (ts_scores.get("tushare_financial", {}).get("score", 5), 0.010),
                    (ht["score"] * 2, 0.012), (gr["score"], 0.018),
                    (st["score"], 0.005), (lt["score"], 0.005),
                    (ts_scores.get("tushare_por", {}).get("score", 5), 0.010),
                    (idf_all["score"], 0.008),
                ]

                # Multi-timeframe bonus (not hard filter in ALL mode)
                mtf = check_multi_timeframe_trend(code)
                mtf_bonus = 0.0
                if mtf.get("weekly_ok"): mtf_bonus += 0.3
                if mtf.get("monthly_ok"): mtf_bonus += 0.2

                sector_score = get_sector_momentum(code)
                tw = sum(w for _, w in models) + 0.03
                composite = sum(s * w for s, w in models) / tw
                composite += regime.get("bonus", 0) + mtf_bonus + sector_score * 0.03 / tw

                score_25 = max(0, min(25, composite * 2.5))
                price = float(df["close"].values[-1])
                levels = compute_trade_levels(df, mode="all")
                risk = assess_risk(code, df, {}, mode="all")
                rationale = build_rationale(code, names.get(code, "?"), df, {},
                                            mode="all", levels=levels)

                picks.append({
                    "code": code, "name": names.get(code, "?"),
                    "price": round(price, 2), "score": round(score_25, 1),
                    "grade": "S" if score_25 >= 16 else ("A" if score_25 >= 12 else (
                        "B" if score_25 >= 7 else "C")),
                    "entry_price": levels.get("entry"), "stop_loss": levels.get("stop"),
                    "target_price": levels.get("target"), "rationale": rationale,
                    "risk_level": risk.get("risk_level"),
                    "sector_score": round(sector_score, 2),
                })
                scored += 1
            except Exception:
                excluded += 1

        picks.sort(key=lambda x: x["score"], reverse=True)
        picks = picks[:top_n]

        return ScreeningResult(
            mode=self.mode, picks=picks, total_scored=scored,
            total_excluded=excluded, market_env=regime.get("label", "NEUTRAL"),
            elapsed=time.time() - t0,
        )
