from datetime import date

from app.quality.evaluator import ReadinessEvaluator, SourceState


def test_backtest_profile_blocks_lagging_adjustment_factor():
    states = {
        "daily_kline": SourceState(actual_as_of=date(2026, 7, 10), coverage_ratio=0.999),
        "adj_factor": SourceState(actual_as_of=date(2026, 7, 7), coverage_ratio=0.999),
    }
    result = ReadinessEvaluator(source_loader=lambda table: states[table]).evaluate(
        "backtest_v1", date(2026, 7, 10), cutoff_time=None
    )
    assert result.status == "blocked"
    assert next(s for s in result.sources if s.source == "adj_factor").status == "stale"

