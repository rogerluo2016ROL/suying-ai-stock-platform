"""Base interfaces and protocols for Kronos Factors package.

All modules depend on these abstractions, not on concrete implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol, Optional
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# Factor Scorer Protocol
# ═══════════════════════════════════════════════════════════════

@dataclass
class FactorScore:
    """Standardized factor score output."""
    score: float          # 0-10 or 0-25 depending on factor
    name: str             # factor name
    signals: list[str] = field(default_factory=list)  # signal tags
    detail: dict = field(default_factory=dict)        # optional detail


class FactorScorer(Protocol):
    """Protocol for all factor scoring functions.

    Every scorer must accept a kline DataFrame and return a dict with at least a 'score' key.
    """

    def __call__(self, kline_df: pd.DataFrame, **kwargs) -> dict:
        """Score a single stock.

        Args:
            kline_df: DataFrame with columns [open, high, low, close, volume, amount]
            **kwargs: Optional additional parameters

        Returns:
            Dict with at least {'score': float}
        """
        ...


# ═══════════════════════════════════════════════════════════════
# Data Adapter Protocols
# ═══════════════════════════════════════════════════════════════

class DBAdapter(ABC):
    """Abstract database adapter — decouples scoring from concrete DB implementations."""

    @abstractmethod
    def execute(self, sql: str, params: tuple = None) -> list[dict]:
        """Execute a read-only SQL query and return rows as dicts."""
        ...

    @abstractmethod
    def get_kline(self, code: str, lookback: int = 400,
                  end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Get K-line data for a single stock.

        M03: `end_date` bounds the result to `trade_date <= end_date` so
        historical backtests do not see future K-line. Adapters without an
        historical-bound mode may ignore it.
        """
        ...

    @abstractmethod
    def get_stock_info(self, code: str) -> Optional[dict]:
        """Get stock basic info (PE, PB, market cap, industry, etc.)."""
        ...

    @abstractmethod
    def get_all_codes(self, exclude_st: bool = True) -> list[str]:
        """Get all stock codes in the universe."""
        ...


class MarketDataAdapter(ABC):
    """Abstract market data adapter."""

    @abstractmethod
    def get_kline_df(self, code: str, lookback: int = 400,
                     end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Get K-line DataFrame for a single stock.

        M03: `end_date` propagated to underlying get_kline to prevent
        future-K-line leakage in historical backtests.
        """
        ...

    @abstractmethod
    def sync_stock_list(self) -> int:
        """Sync full stock list. Returns count."""
        ...

    @abstractmethod
    def update_daily_kline(self, from_date: str) -> int:
        """Update daily K-line data. Returns updated count."""
        ...


# ═══════════════════════════════════════════════════════════════
# Strategy Engine ABC
# ═══════════════════════════════════════════════════════════════

@dataclass
class ScreeningResult:
    """Standardized screening result from any strategy engine."""
    mode: str                    # strategy mode identifier
    picks: list[dict]            # ranked stock picks
    total_scored: int            # total stocks scored
    total_excluded: int = 0      # stocks excluded by filters
    market_env: str = "NEUTRAL"  # BULL / NEUTRAL / BEAR / CRASH
    elapsed: float = 0.0         # seconds
    metadata: dict = field(default_factory=dict)


class StrategyEngine(ABC):
    """Abstract base class for all strategy engines.

    Every strategy engine must implement run() and return ScreeningResult.
    """

    mode: str = "base"

    @abstractmethod
    def run(self, top_n: int = 20, **kwargs) -> ScreeningResult:
        """Execute the strategy and return ranked picks."""
        ...

    @abstractmethod
    def get_factor_weights(self) -> dict[str, float]:
        """Return the factor weight configuration for this strategy."""
        ...


# ═══════════════════════════════════════════════════════════════
# Backtest Engine ABC
# ═══════════════════════════════════════════════════════════════

@dataclass
class BacktestResult:
    """Standardized backtest result."""
    strategy_id: str
    start_date: str
    end_date: str
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_loss_ratio: float
    ic_mean: float = 0.0
    icir: float = 0.0
    factor_analysis: dict = field(default_factory=dict)
    daily_returns: list[float] = field(default_factory=list)
