import numpy as np
import pytest
from kronos_factors.evaluation.factor_ic import compute_cross_section_ic

def test_monotonic_scores_have_positive_rank_ic():
    result = compute_cross_section_ic(np.array([1,2,3,4,5]), np.array([-.02,-.01,0,.01,.02]))
    assert result.rank_ic == pytest.approx(1.0)

def test_shuffled_returns_do_not_create_stable_ic():
    rng = np.random.default_rng(42); scores = np.arange(100, dtype=float)
    values = [compute_cross_section_ic(scores, rng.permutation(scores)).rank_ic for _ in range(60)]
    assert abs(float(np.mean(values))) < .10
