import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel

REQUIRED_GATES = ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]

class AdmissionDecision(BaseModel):
    allowed: bool
    target_stage: Literal["candidate", "paper", "production"]
    passed_gates: list[str]
    failed_gates: list[str]
    evidence_run_ids: list[str]


class MlflowPromotionError(RuntimeError):
    pass

def evaluate_admission(evidence: dict, target_stage: str = "candidate", *,
                       manual_approval: bool = False, baseline_exists: bool = True,
                       production_thresholds_approved: bool = False) -> AdmissionDecision:
    passed=[]; failed=[]; runs=[]
    for gate in REQUIRED_GATES:
        item = evidence.get(gate, {})
        if item.get("status") == "passed" and item.get("evidence_run_id"):
            passed.append(gate)
            if item.get("evidence_run_id"): runs.append(item["evidence_run_id"])
        else: failed.append(gate)
    if target_stage in {"paper", "production"} and not baseline_exists:
        failed.append("baseline")
    if target_stage == "production" and not manual_approval:
        failed.append("manual_approval")
    if target_stage == "production" and not production_thresholds_approved:
        failed.append("production_thresholds_not_approved")
    return AdmissionDecision(allowed=not failed, target_stage=target_stage, passed_gates=passed, failed_gates=failed, evidence_run_ids=runs)


async def promote_after_mlflow_alias(*, mlflow_client, model_name: str, model_version: int,
                                     target_stage: str, commit_pg):
    """Update MLflow first; PostgreSQL mutation is never attempted on alias failure."""
    try:
        mlflow_client.set_model_alias(model_name, target_stage, model_version)
    except Exception as exc:
        raise MlflowPromotionError(str(exc)) from exc
    return await commit_pg()
