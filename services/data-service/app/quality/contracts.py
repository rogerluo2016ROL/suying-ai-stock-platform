from dataclasses import dataclass, asdict
from datetime import date, datetime

@dataclass
class SourceState:
    actual_as_of: date | datetime | None = None
    coverage_ratio: float = 1.0

@dataclass
class SourceReadiness:
    source: str
    status: str
    actual_as_of: str | None = None
    coverage_ratio: float = 0.0
    reason: str | None = None

@dataclass
class DataReadiness:
    profile: str
    target_trade_date: date
    cutoff_time: datetime | None
    status: str
    sources: list[SourceReadiness]
    def to_dict(self):
        d = asdict(self); d['target_trade_date'] = self.target_trade_date.isoformat(); d['cutoff_time'] = self.cutoff_time.isoformat() if self.cutoff_time else None; return d
