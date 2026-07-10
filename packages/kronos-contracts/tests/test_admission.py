from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from kronos_contracts.admission import evaluate_admission


def test_admission_blocks_when_any_required_gate_fails():
    result = evaluate_admission({"data_readiness": True, "out_of_sample": False, "drawdown": True, "costs": True, "timeline": True})
    assert result.status == "blocked"
    assert result.failed_gates == ("out_of_sample",)
