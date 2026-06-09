"""Strategy engines — 6 screening strategies for A-share market."""

from kronos_factors.engine.leader_scalp import (
    MarketEnv, assess_market_env, detect_extreme_loss_risk,
    score_stock, compute_sector_leader, run_leader_screening,
    generate_execution_plan,
)
from kronos_factors.engine.leader_intraday import (
    score_intraday_stock, run_intraday_screening,
    generate_intraday_plan,
)

__all__ = [
    "MarketEnv",
    "assess_market_env", "detect_extreme_loss_risk",
    "score_stock", "compute_sector_leader",
    "run_leader_screening", "generate_execution_plan",
    "score_intraday_stock", "run_intraday_screening",
    "generate_intraday_plan",
]
