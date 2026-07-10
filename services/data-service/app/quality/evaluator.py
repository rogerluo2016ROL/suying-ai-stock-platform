import json
from datetime import date, datetime, timedelta
from pathlib import Path
from .contracts import DataReadiness, SourceReadiness, SourceState

def _profiles():
    p = Path(__file__).parents[4] / 'configs/data_readiness_profiles.json'
    return json.loads(p.read_text())

class ReadinessEvaluator:
    def __init__(self, source_loader): self.source_loader = source_loader
    def evaluate(self, profile, target_trade_date, cutoff_time=None):
        specs = _profiles().get(profile)
        if not specs: raise ValueError(f'unknown readiness profile: {profile}')
        out=[]
        for spec in specs['sources']:
            name=spec['source']; state=self.source_loader(name)
            actual=state.actual_as_of
            if isinstance(actual, datetime):
                limit = cutoff_time or datetime.combine(target_trade_date, datetime.min.time())
                stale = actual < limit - timedelta(minutes=spec.get('max_lag_minutes', 0)) if 'max_lag_minutes' in spec else actual.date() < target_trade_date - timedelta(days=spec.get('max_lag_days', 0))
            else:
                stale = actual is None or actual < target_trade_date - timedelta(days=spec.get('max_lag_days', 0))
            status = 'ready' if not stale and state.coverage_ratio >= 0.99 else 'stale'
            out.append(SourceReadiness(name,status,actual.isoformat() if actual else None,state.coverage_ratio))
        blocked = any(s.status != 'ready' and spec.get('required', True) for s,spec in zip(out,specs['sources']))
        return DataReadiness(profile,target_trade_date,cutoff_time,'blocked' if blocked else 'ready',out)
