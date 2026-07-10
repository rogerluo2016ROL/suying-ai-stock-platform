import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.admission import admission_from_metrics


def test_missing_admission_evidence_is_blocked():
    result = admission_from_metrics({"ic": 0.1})
    assert result.status == "blocked"
    assert result.failed_gates == ("data_readiness", "out_of_sample", "drawdown", "costs", "timeline")


def test_all_admission_evidence_allows_promotion():
    result = admission_from_metrics({
        "admission_gates": {"data_readiness": True, "out_of_sample": True, "drawdown": True, "costs": True, "timeline": True}
    })
    assert result.status == "ready"
