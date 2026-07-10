import pytest
from app.admission import evaluate_admission

@pytest.mark.parametrize("failed_gate", ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"])
def test_each_required_gate_blocks_promotion(failed_gate):
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    evidence[failed_gate] = {"status": "failed"}
    decision = evaluate_admission(evidence, target_stage="paper")
    assert decision.allowed is False and failed_gate in decision.failed_gates

def test_production_requires_manual_approval():
    evidence = {gate: {"status": "passed"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    assert evaluate_admission(evidence, "production").allowed is False
