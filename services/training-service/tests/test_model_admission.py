import pytest
from app.admission import MlflowPromotionError, evaluate_admission, promote_after_mlflow_alias
from unittest.mock import AsyncMock

@pytest.mark.parametrize("failed_gate", ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"])
def test_each_required_gate_blocks_promotion(failed_gate):
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    evidence[failed_gate] = {"status": "failed"}
    decision = evaluate_admission(evidence, target_stage="paper")
    assert decision.allowed is False and failed_gate in decision.failed_gates

def test_production_requires_manual_approval():
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    assert evaluate_admission(evidence, "production").allowed is False

def test_production_remains_blocked_until_thresholds_are_approved():
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    decision = evaluate_admission(evidence, "production", manual_approval=True)
    assert "production_thresholds_not_approved" in decision.failed_gates

def test_paper_requires_baseline():
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    assert evaluate_admission(evidence, "paper", baseline_exists=False).allowed is False

def test_passed_gate_without_evidence_id_is_blocked():
    evidence = {gate: {"status": "passed", "evidence_run_id": f"RUN-{gate}"} for gate in ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]}
    evidence["cost_model"].pop("evidence_run_id")
    assert "cost_model" in evaluate_admission(evidence, "paper").failed_gates

def test_mlflow_failure_does_not_mutate_pg():
    class FailingMlflow:
        def set_model_alias(self, *args):
            raise ConnectionError("offline")
    commit_pg = AsyncMock()
    import asyncio
    with pytest.raises(MlflowPromotionError):
        asyncio.run(promote_after_mlflow_alias(mlflow_client=FailingMlflow(), model_name="m",
                    model_version=2, target_stage="paper", commit_pg=commit_pg))
    commit_pg.assert_not_awaited()

def test_live_mlflow_failure_never_falls_back_to_mock(monkeypatch):
    from app import mlflow_client
    monkeypatch.setattr(mlflow_client, "MLFLOW_MODE", "live")
    monkeypatch.setattr(mlflow_client, "_mlflow_client", None)
    class Offline:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("offline")
    monkeypatch.setattr(mlflow_client, "LiveMlflowClient", Offline)
    with pytest.raises(RuntimeError, match="MLflow live connection failed"):
        mlflow_client.get_mlflow_client()
