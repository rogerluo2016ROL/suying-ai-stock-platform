import json
import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel

_DEFAULT_GATES = ["data_readiness", "strict_timeline", "cost_model", "oos_report", "drawdown_sample"]


def _load_gates_config() -> dict:
    """读取 configs/model_admission_gates.json（ADR-019 准入门禁 config 驱动）。

    查找顺序: $MODEL_ADMISSION_GATES_PATH → 容器 /app/configs/ → 仓库根 configs/。
    缺文件/解析失败回退内置默认（与历史硬编码一致，行为不变）。
    """
    candidates = []
    env_path = os.environ.get("MODEL_ADMISSION_GATES_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path("/app/configs/model_admission_gates.json"))
    candidates.append(Path(__file__).resolve().parents[3] / "configs" / "model_admission_gates.json")
    for p in candidates:
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


_CFG = _load_gates_config()
REQUIRED_GATES = _CFG.get("required_gates", _DEFAULT_GATES)
PAPER_REQUIRES_BASELINE = _CFG.get("paper_requires_baseline", True)
PRODUCTION_REQUIRES_MANUAL_APPROVAL = _CFG.get("production_requires_manual_approval", True)

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
    if target_stage in {"paper", "production"} and PAPER_REQUIRES_BASELINE and not baseline_exists:
        failed.append("baseline")
    if target_stage == "production" and PRODUCTION_REQUIRES_MANUAL_APPROVAL and not manual_approval:
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
