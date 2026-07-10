import numpy as np
import pytest
from kronos_factors.evaluation.factor_ic import compute_cross_section_ic, evaluate_factor_rows

def test_monotonic_scores_have_positive_rank_ic():
    result = compute_cross_section_ic(np.array([1,2,3,4,5]), np.array([-.02,-.01,0,.01,.02]))
    assert result.rank_ic == pytest.approx(1.0)

def test_shuffled_returns_do_not_create_stable_ic():
    rng = np.random.default_rng(42); scores = np.arange(100, dtype=float)
    values = [compute_cross_section_ic(scores, rng.permutation(scores)).rank_ic for _ in range(60)]
    assert abs(float(np.mean(values))) < .10

def test_factor_rows_require_period_and_observation_floors():
    rows = [{"trade_date": "2026-01-01", "factors": {"score": i}, "future_return": i / 100}
            for i in range(30)]
    assert evaluate_factor_rows(rows)["status"] == "insufficient_data"

def test_factor_rows_compute_period_ic_and_deciles():
    rows = []
    for day in range(20):
        rows.extend({"trade_date": f"2026-01-{day + 1:02d}", "factors": {"score": i},
                     "future_return": i / 1000} for i in range(30))
    report = evaluate_factor_rows(rows)
    assert report["status"] == "ready"
    assert report["factors"][0]["rank_ic"] == pytest.approx(1.0)
    assert len(report["factors"][0]["deciles"]) == 10
    assert report["deciles"][0]["factor_name"] == "score"
