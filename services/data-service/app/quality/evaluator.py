"""Profile-driven data readiness evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Callable

@dataclass(frozen=True)
class SourceState:
    actual_as_of: date | None
    coverage_ratio: float

@dataclass(frozen=True)
class SourceResult:
    source: str
    status: str
    actual_as_of: date | None
    coverage_ratio: float
    reason: str | None = None

@dataclass(frozen=True)
class DataReadiness:
    profile: str
    target_trade_date: date
    status: str
    sources: tuple[SourceResult, ...]
    checked_at: datetime

PROFILES = {
    "backtest_v1": {"required": ("daily_kline", "adj_factor"), "min_coverage": 0.99},
    "daily_screening_v1": {"required": ("daily_kline", "daily_basic"), "min_coverage": 0.95},
    "intraday_screening_v1": {"required": ("daily_kline",), "min_coverage": 0.95},
    "training_v1": {"required": ("daily_kline", "adj_factor"), "min_coverage": 0.99},
    "cb_auction_v1": {"required": ("daily_kline",), "min_coverage": 0.95},
}

class ReadinessEvaluator:
    def __init__(self, source_loader: Callable[[str], SourceState]):
        self.source_loader = source_loader

    def evaluate(self, profile: str, target_trade_date: date, cutoff_time: time | None) -> DataReadiness:
        config = PROFILES.get(profile)
        if config is None:
            raise ValueError(f"unknown readiness profile: {profile}")
        results = []
        for source in config["required"]:
            state = self.source_loader(source)
            status = "ready"
            reason = None
            if state.actual_as_of is None or state.actual_as_of < target_trade_date:
                status, reason = "stale", "source is behind target trade date"
            elif state.coverage_ratio < config["min_coverage"]:
                status, reason = "insufficient", "coverage below profile threshold"
            results.append(SourceResult(source, status, state.actual_as_of, state.coverage_ratio, reason))
        overall = "ready" if all(item.status == "ready" for item in results) else "blocked"
        return DataReadiness(profile, target_trade_date, overall, tuple(results), datetime.now(timezone.utc))
