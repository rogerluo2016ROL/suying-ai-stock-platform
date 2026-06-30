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
from kronos_factors.engine.bi_trend_full_market import (
    BiTrendFullMarketEngine, run_bi_screening as run_bi_full_market,
)
from kronos_factors.engine.leader_afternoon import (
    AfternoonLeaderEngine, AfternoonTrendFullEngine, run_afternoon_screening,
)
from kronos_factors.engine.modes import (
    ChokepointEngine, ShortModeEngine, LongModeEngine, AllModeEngine,
)
from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine
from kronos_factors.engine.supply_chain import (
    SupplyChainEngine,
)

__all__ = [
    # Leader Scalp (收盘后)
    "MarketEnv", "assess_market_env", "detect_extreme_loss_risk",
    "score_stock", "compute_sector_leader",
    "run_leader_screening", "generate_execution_plan",
    # Leader Intraday (盘中)
    "score_intraday_stock", "run_intraday_screening",
    "generate_intraday_plan",
    # Leader Afternoon (午后)
    "AfternoonLeaderEngine", "AfternoonTrendFullEngine", "run_afternoon_screening",
    # Bi Trend Full Market (全市场)
    "BiTrendFullMarketEngine", "run_bi_full_market",
    # Multi-factor modes
    "ChokepointEngine", "ShortModeEngine", "LongModeEngine", "AllModeEngine",
    # CB Auction T0
    "CbAuctionT0Engine",
    # Supply Chain
    "SupplyChainEngine",
]
