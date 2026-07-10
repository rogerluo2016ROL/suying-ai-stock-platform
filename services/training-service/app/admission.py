import json
from pathlib import Path
from pydantic import BaseModel

REQUIRED_GATES = ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]

class AdmissionDecision(BaseModel):
    allowed: bool
    target_stage: str
    passed_gates: list[str]
    failed_gates: list[str]
    evidence_run_ids: list[str]

def evaluate_admission(evidence: dict, target_stage: str = "candidate") -> AdmissionDecision:
    passed=[]; failed=[]; runs=[]
    for gate in REQUIRED_GATES:
        item = evidence.get(gate, {})
        if item.get("status") == "passed":
            passed.append(gate)
            if item.get("evidence_run_id"): runs.append(item["evidence_run_id"])
        else: failed.append(gate)
    if target_stage == "production":
        failed.append("manual_approval")
    return AdmissionDecision(allowed=not failed, target_stage=target_stage, passed_gates=passed, failed_gates=failed, evidence_run_ids=runs)
