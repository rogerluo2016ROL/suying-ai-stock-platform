from datetime import date, datetime, timezone
from app.quality.contracts import SourceState
from app.quality.evaluator import ReadinessEvaluator

def test_backtest_profile_blocks_lagging_adjustment_factor():
    states={'daily_kline':SourceState(date(2026,7,10),.999),'adj_factor':SourceState(date(2026,7,7),.999)}
    result=ReadinessEvaluator(lambda t: states[t]).evaluate('backtest_v1',date(2026,7,10))
    assert result.status=='blocked'; assert next(s for s in result.sources if s.source=='adj_factor').status=='stale'

def test_intraday_cutoff_and_optional_source():
    states={'daily_kline':SourceState(date(2026,7,10),1),'auction':SourceState(datetime(2026,7,10,14,20,tzinfo=timezone.utc),1),'cb_basic':SourceState(None,0)}
    result=ReadinessEvaluator(lambda t: states[t]).evaluate('cb_auction_v1',date(2026,7,10),datetime(2026,7,10,14,27,tzinfo=timezone.utc))
    assert result.status=='blocked'; assert next(s for s in result.sources if s.source=='auction').status=='stale'
