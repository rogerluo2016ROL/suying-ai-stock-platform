"""Kronos Factors — A-share stock screening factor scoring, strategy engines, and backtest.

Usage:
    from kronos_factors.scorer import score_five_factor, score_money_flow
    from kronos_factors.engine import run_leader_screening
    from kronos_factors.backtest import run_backtest
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
"""

__version__ = "0.1.0"

from kronos_factors.base import (
    FactorScorer, StrategyEngine, DBAdapter, MarketDataAdapter,
    ScreeningResult, BacktestResult, FactorScore,
)
