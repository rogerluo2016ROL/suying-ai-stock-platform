"""Factor scoring functions — 25+ scorers for A-share stock evaluation."""

from kronos_factors.scorer.five_factor import score_five_factor
from kronos_factors.scorer.advanced_factors import (
    score_money_flow, score_mean_reversion, score_trend_strength,
    score_reversal, score_liquidity, score_hard_tech,
    get_tushare_scores, run_multi_model,
)
from kronos_factors.scorer.screening_scorers import (
    score_short_term, score_long_term, score_growth,
    score_identifiability, score_margin_momentum, score_chokepoint,
    get_stock_themes, check_multi_timeframe_trend,
    check_institutional_funds, compute_trade_levels,
    assess_risk, build_rationale, get_market_regime,
    get_sector_momentum, generate_devils_advocate, run_screening,
)

__all__ = [
    "score_five_factor",
    "score_money_flow", "score_mean_reversion", "score_trend_strength",
    "score_reversal", "score_liquidity", "score_hard_tech",
    "get_tushare_scores", "run_multi_model",
    "score_short_term", "score_long_term", "score_growth",
    "score_identifiability", "score_margin_momentum", "score_chokepoint",
    "get_stock_themes", "check_multi_timeframe_trend",
    "check_institutional_funds", "compute_trade_levels",
    "assess_risk", "build_rationale", "get_market_regime",
    "get_sector_momentum", "generate_devils_advocate", "run_screening",
]
