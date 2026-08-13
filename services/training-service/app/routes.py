"""Training Service API Routes — 12 endpoints covering AC-6.1~6.9.

All endpoints require `admin` role (AC-6.9).

Endpoints:
  1. POST /api/v1/training/run           — Trigger training (AC-6.1)
  2. GET  /api/v1/training/status/{id}   — Training status + SSE streaming (AC-6.3)
  3. GET  /api/v1/training/models        — Model registry list
  4. GET  /api/v1/training/models/{id}   — Model detail
  5. POST /api/v1/training/models/{id}/deploy    — Deploy model (AC-6.5)
  6. POST /api/v1/training/models/{id}/rollback  — Rollback model (AC-6.6)
  7. GET  /api/v1/training/models/{id}/compare   — Compare new vs old (AC-6.4)
  8. POST /api/v1/training/schedule      — Configure auto schedule (AC-6.2)
  9. GET  /api/v1/training/schedule      — View schedule status (AC-6.2)
  10. GET  /api/v1/training/history      — Training history (AC-6.8)
  11. POST /api/v1/training/calibrate    — Factor weight calibration (AC-6.7)
  12. GET  /api/v1/training/factors/ic   — IC/ICIR rolling analysis (AC-5.6)
"""

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_role
from app.mlflow_client import get_mlflow_client, get_production_model, set_production_model
from app.schemas import (
    ArchiveRequest,
    CalibrateRequest,
    CalibrateResponse,
    CompareResult,
    DeployRequest,
    DeployResponse,
    ErrorResponse,
    FactorICResponse,
    JobStatus,
    JobStatusResponse,
    ModelCompareResponse,
    ModelRecord,
    ModelStage,
    ModelType,
    PaginatedHistoryResponse,
    PaginatedModelsResponse,
    RollbackRequest,
    RollbackResponse,
    ScheduleConfig,
    ScheduleStatusResponse,
    ScheduleUpdateResponse,
    TrainingHistoryItem,
    TrainingJob,
    TrainRequest,
    TrainResponse,
)
from app.training_engine import (
    _job_lock,
    _jobs,
    _publish_progress,
    _save_job,
    check_active_job,
    get_job,
    list_jobs,
    run_training,
)

logger = logging.getLogger("training-service.routes")

router = APIRouter(prefix="/api/v1/training", tags=["training"])

REQUIRED_COMPARE_METRICS = (
    "ic",
    "icir",
    "sharpe",
    "max_drawdown",
    "annual_return",
    "win_rate",
    "profit_loss_ratio",
)
COMPARE_CONFIGURATION = (
    ("sharpe", 0.05, True),
    ("icir", 0.02, True),
    ("ic", 0.002, True),
    ("max_drawdown", 0.01, True),
    ("annual_return", 0.02, True),
    ("win_rate", 0.02, True),
    ("profit_loss_ratio", 0.05, True),
)


def _has_real_metric(metrics: dict, key: str) -> bool:
    value = metrics.get(key)
    if value is None or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _compare_complete_metric_sets(
    new_metrics: dict,
    old_metrics: dict,
) -> tuple[list[CompareResult], str, str]:
    def make_compare(
        metric: str,
        threshold: float,
        higher_better: bool,
    ) -> CompareResult:
        new_value = float(new_metrics[metric])
        old_value = float(old_metrics[metric])
        delta = new_value - old_value
        delta_pct = (delta / abs(old_value) * 100) if old_value != 0 else 0.0
        better = (
            delta > threshold if higher_better else delta < -threshold
        )
        return CompareResult(
            metric=metric,
            new_value=round(new_value, 4),
            old_value=round(old_value, 4),
            delta=round(delta, 4),
            delta_pct=round(delta_pct, 1),
            better=better,
            threshold=threshold,
        )

    comparisons = [
        make_compare(metric, threshold, higher_better)
        for metric, threshold, higher_better in COMPARE_CONFIGURATION
    ]
    better_count = sum(1 for comparison in comparisons if comparison.better)
    worse_count = len(comparisons) - better_count
    if better_count >= 5:
        return (
            comparisons,
            "new_better",
            f"建议上线。新模型在 {better_count}/{len(comparisons)} 项指标上优于旧模型。",
        )
    if worse_count >= 5:
        return (
            comparisons,
            "old_better",
            "建议保留旧模型。新模型在多数指标上未超过旧模型。",
        )
    return comparisons, "inconclusive", "需人工判断。新旧模型各有优劣。"


def _build_truthful_comparison(
    new_metrics: dict,
    old_metrics: dict | None,
) -> tuple[list[CompareResult], str, str]:
    missing_new = [
        key for key in REQUIRED_COMPARE_METRICS
        if not _has_real_metric(new_metrics, key)
    ]
    missing_old = (
        list(REQUIRED_COMPARE_METRICS)
        if old_metrics is None
        else [
            key for key in REQUIRED_COMPARE_METRICS
            if not _has_real_metric(old_metrics, key)
        ]
    )
    if missing_new or missing_old:
        missing = sorted(set(missing_new + missing_old))
        return (
            [],
            "insufficient_evidence",
            "缺少真实回测指标：" + ", ".join(missing) + "；不能生成上线建议。",
        )
    return _compare_complete_metric_sets(new_metrics, old_metrics)


# ═══════════════════════════════════════════════════════════════════════════
# 1. POST /api/v1/training/run — Trigger training (AC-6.1)
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/run",
    response_model=TrainResponse,
    status_code=202,
    responses={
        409: {"model": ErrorResponse, "description": "Training already running"},
        400: {"model": ErrorResponse, "description": "Invalid params"},
    },
)
async def api_run_training(
    body: TrainRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Manually trigger model training (AC-6.1).

    Returns job_id immediately. Training executes in background.
    Progress available via GET /status/{job_id} (SSE).
    """
    # Check for conflicts
    active = await check_active_job(body.params.model_type.value)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "training_already_running",
                "message": f"已有训练任务 {active.job_id} 正在运行中 ({active.model_type.value}, status={active.status.value})",
                "active_job_id": active.job_id,
            },
        )

    try:
        job_id = await run_training(
            params=body.params,
            created_by=current_user.get("name", "admin"),
            auto_deploy=body.auto_deploy,
        )

        job = get_job(job_id)
        return TrainResponse(
            job_id=job_id,
            status=job.status if job else JobStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "invalid_params", "message": str(e)})
    except Exception as e:
        logger.exception("Failed to start training")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET /api/v1/training/status/{job_id} — Status + SSE streaming (AC-6.3)
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/status/{job_id}",
    response_model=JobStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
async def api_job_status(
    job_id: str,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    """Get training job status.

    Returns JSON snapshot by default.
    When Accept: text/event-stream, returns SSE stream of training progress.
    """
    accept = request.headers.get("accept", "")

    if "text/event-stream" in accept:
        return await _sse_status_stream(job_id)

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "message": f"Job {job_id} not found"})

    return JobStatusResponse(
        job_id=job.job_id,
        model_type=job.model_type,
        status=job.status,
        params=job.params,
        current_metrics=job.metrics[-1] if job.metrics else None,
        best_params=job.best_params,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


async def _sse_status_stream(job_id: str):
    """Server-Sent Events stream for real-time training progress."""
    job = get_job(job_id)
    if not job:
        async def not_found():
            yield f"event: error\ndata: {json.dumps({'error': 'job_not_found'})}\n\n"
        return StreamingResponse(not_found(), media_type="text/event-stream")

    async def event_generator():
        # Send current status snapshot first
        yield f"event: status\ndata: {json.dumps({'job_id': job_id, 'status': job.status.value}, default=str)}\n\n"

        # Subscribe to Redis Pub/Sub
        try:
            import redis.asyncio as redis
            from app.config import REDIS_URL

            r = redis.from_url(REDIS_URL)
            pubsub = r.pubsub()
            await pubsub.subscribe(f"training:{job_id}")

            # Send existing metrics
            for metric in job.metrics:
                yield f"event: metric\ndata: {json.dumps(metric.model_dump(), default=str)}\n\n"

            # Listen for new events
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    event_type = data.pop("type", "metric")
                    yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"

                    if event_type in ("complete", "error"):
                        await pubsub.unsubscribe(f"training:{job_id}")
                        break

            await r.close()
        except Exception as e:
            logger.warning("Redis SSE stream failed: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2b. POST /api/v1/training/status/{job_id}/cancel — Cancel training job
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/status/{job_id}/cancel")
async def api_cancel_job(
    job_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Cancel a running training job (PENDING/PREPARING/RUNNING/EVALUATING).

    Sets the job status to CANCELLED, persists, and publishes to Redis.
    """
    job = None
    with _job_lock:
        job = _jobs.get(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail={"error": "job_not_found", "message": f"Job {job_id} not found"},
        )

    cancellable = {JobStatus.PENDING, JobStatus.PREPARING, JobStatus.RUNNING, JobStatus.EVALUATING}
    if job.status not in cancellable:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "cannot_cancel",
                "message": "只能取消进行中的任务 (status={})".format(job.status.value),
            },
        )

    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.now(timezone.utc)
    await _save_job(job)
    await _publish_progress(job_id, "cancelled", {
        "job_id": job_id,
        "status": "cancelled",
        "message": "任务已取消",
    })

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "任务已取消",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. GET /api/v1/training/models — Model registry list
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/models", response_model=PaginatedModelsResponse)
async def api_list_models(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    stage: Optional[str] = Query(None, description="Filter by stage"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(require_role("admin")),
):
    """List all registered models with optional filters."""
    mlflow_client = get_mlflow_client()

    # Get models from MLflow
    mlflow_models = mlflow_client.list_models(name=None)

    # Transform to ModelRecord
    records = []
    for mv in mlflow_models:
        # Determine model_type from name
        mt = ModelType.LIGHTGBM
        if "catboost" in mv.get("name", ""):
            mt = ModelType.CATBOOST
        elif "kronos" in mv.get("name", ""):
            mt = ModelType.KRONOS_FINETUNE

        records.append(ModelRecord(
            id=f"mdl-{mv.get('name', 'unknown')}-v{mv.get('version', 0)}",
            name=mv.get("name", "unknown"),
            version=mv.get("version", 1),
            model_type=mt,
            stage=ModelStage(mv.get("stage", "none")),
            run_id=mv.get("run_id"),
            params=mv.get("params"),
            metrics=mv.get("metrics"),
            deployed_at=mv.get("deployed_at"),
            created_by="system",
            created_at=mv.get("created_at", datetime.now(timezone.utc)),
        ))

    # Filter
    if model_type:
        records = [r for r in records if r.model_type.value == model_type]
    if stage:
        records = [r for r in records if r.stage.value == stage]

    # Also query from PostgreSQL for any models not in MLflow
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM model_registry ORDER BY created_at DESC")
            )
            for row in result.fetchall():
                d = dict(row._mapping)
                if not any(r.run_id == d.get("run_id") for r in records if r.run_id):
                    records.append(ModelRecord(
                        id=d["id"],
                        name=d["name"],
                        version=d["version"],
                        model_type=ModelType(d["model_type"]),
                        stage=ModelStage(d["stage"]),
                        run_id=d.get("run_id"),
                        params=json.loads(d["params"]) if d.get("params") and isinstance(d["params"], str) else d.get("params"),
                        metrics=json.loads(d["metrics"]) if d.get("metrics") and isinstance(d["metrics"], str) else d.get("metrics"),
                        artifact_uri=d.get("artifact_uri"),
                        deployed_at=d.get("deployed_at"),
                        deployed_by=d.get("deployed_by"),
                        created_by=d.get("created_by", "unknown"),
                        created_at=d["created_at"],
                        updated_at=d.get("updated_at"),
                        notes=d.get("notes"),
                    ))
    except Exception as exc:
        logger.warning("Failed to query model registry from DB: %s", exc)

    total = len(records)
    start = (page - 1) * page_size
    end = start + page_size
    paged = records[start:end]

    return PaginatedModelsResponse(
        models=paged,
        total=total,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. GET /api/v1/training/models/{id} — Model detail
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/models/{model_id}", response_model=ModelRecord)
async def api_model_detail(
    model_id: str,
    current_user: dict = Depends(require_role("admin")),
):
    """Get full model record details."""
    # Try PostgreSQL first
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM model_registry WHERE id = :id"),
                {"id": model_id},
            )
            row = result.fetchone()
            if row:
                d = dict(row._mapping)
                return ModelRecord(
                    id=d["id"],
                    name=d["name"],
                    version=d["version"],
                    model_type=ModelType(d["model_type"]),
                    stage=ModelStage(d["stage"]),
                    run_id=d.get("run_id"),
                    experiment_id=d.get("experiment_id"),
                    params=json.loads(d["params"]) if d.get("params") and isinstance(d["params"], str) else d.get("params"),
                    metrics=json.loads(d["metrics"]) if d.get("metrics") and isinstance(d["metrics"], str) else d.get("metrics"),
                    artifact_uri=d.get("artifact_uri"),
                    deployed_at=d.get("deployed_at"),
                    deployed_by=d.get("deployed_by"),
                    created_by=d.get("created_by", "unknown"),
                    created_at=d["created_at"],
                    updated_at=d.get("updated_at"),
                    notes=d.get("notes"),
                )
    except Exception as e:
        logger.warning("Failed to query model from DB: %s", e)

    mlflow_record = _find_mlflow_model_record(model_id, get_mlflow_client())
    if mlflow_record:
        return mlflow_record

    raise HTTPException(
        status_code=404,
        detail={"error": "model_not_found", "message": f"Model {model_id} not found"},
    )


# Need this import for the models endpoint
from app.database import AsyncSessionLocal


def _model_type_from_name(name: str) -> ModelType:
    if "catboost" in name:
        return ModelType.CATBOOST
    if "kronos" in name:
        return ModelType.KRONOS_FINETUNE
    return ModelType.LIGHTGBM


def _model_record_from_mlflow(mv: dict) -> ModelRecord:
    name = mv.get("name", "unknown")
    version = int(mv.get("version", 1))
    return ModelRecord(
        id=f"mdl-{name}-v{version}",
        name=name,
        version=version,
        model_type=_model_type_from_name(name),
        stage=ModelStage(mv.get("stage", "none")),
        run_id=mv.get("run_id"),
        params=mv.get("params") or {},
        metrics=mv.get("metrics") or {},
        deployed_at=mv.get("deployed_at"),
        created_by="system",
        created_at=mv.get("created_at", datetime.now(timezone.utc)),
    )


def _find_mlflow_model_record(model_id: str, mlflow_client) -> ModelRecord | None:
    if not model_id.startswith("mdl-") or "-v" not in model_id:
        return None
    name_part, version_part = model_id[4:].rsplit("-v", 1)
    try:
        version = int(version_part)
    except ValueError:
        return None
    for mv in mlflow_client.list_models(name_part):
        if int(mv.get("version", 0)) == version:
            return _model_record_from_mlflow(mv)
    mv = mlflow_client.get_model_version(name_part, version)
    if not mv:
        return None
    return _model_record_from_mlflow(mv)


# ═══════════════════════════════════════════════════════════════════════════
# 5. POST /api/v1/training/models/{id}/deploy — Deploy model (AC-6.5)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/models/{model_id}/deploy", response_model=DeployResponse)
async def api_deploy_model(
    model_id: str,
    body: DeployRequest = DeployRequest(),
    current_user: dict = Depends(require_role("admin")),
):
    """Promote a model only after evidence gates and MLflow alias succeed."""
    from app.admission import MlflowPromotionError, evaluate_admission, promote_after_mlflow_alias

    decision = evaluate_admission(
        body.evidence, body.target_stage, manual_approval=body.manual_approval,
        baseline_exists=body.baseline_exists, production_thresholds_approved=False,
    )
    if not decision.allowed:
        raise HTTPException(status_code=409, detail={
            "code": "MODEL_ADMISSION_BLOCKED", "failed_gates": decision.failed_gates,
            "passed_gates": decision.passed_gates,
        })

    mlflow_client = get_mlflow_client()
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM model_registry WHERE id = :id"),
                {"id": model_id},
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "model_not_found", "message": f"Model {model_id} not found"},
                )
            d = dict(row._mapping)

            model_name = d["name"]
            model_version = d["version"]
            model_stage = d["stage"]

            if model_stage == body.target_stage and not body.force:
                raise HTTPException(
                    status_code=409,
                    detail={"error": "deploy_conflict", "message": f"Model is already in {body.target_stage}"},
                )

            prev_version = None
            if body.target_stage == "production":
                result2 = await db.execute(sa_text(
                    "SELECT version FROM model_registry WHERE name=:name AND stage='production' AND id!=:id"
                ), {"name": model_name, "id": model_id})
                prev_row = result2.fetchone()
                prev_version = prev_row[0] if prev_row else None

            async def commit_pg():
                if body.target_stage == "production":
                    await db.execute(sa_text(
                        "UPDATE model_registry SET stage='archived',updated_at=NOW() "
                        "WHERE name=:name AND stage='production' AND id!=:id"
                    ), {"name": model_name, "id": model_id})
                await db.execute(sa_text(
                    "UPDATE model_registry SET stage=:stage,deployed_at=NOW(),deployed_by=:user,"
                    "updated_at=NOW(),notes=:notes WHERE id=:id"
                ), {"stage": body.target_stage, "id": model_id,
                    "user": current_user.get("name", "admin"), "notes": body.notes or ""})
                await db.commit()

            await promote_after_mlflow_alias(
                mlflow_client=mlflow_client, model_name=model_name, model_version=model_version,
                target_stage=body.target_stage, commit_pg=commit_pg,
            )
    except HTTPException:
        raise
    except MlflowPromotionError as e:
        logger.exception("MLflow promotion failed")
        raise HTTPException(status_code=503, detail={
            "code": "MLFLOW_PROMOTION_FAILED", "message": str(e),
        })
    except Exception as e:
        logger.exception("Failed to deploy model")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})

    return DeployResponse(
        model_id=model_id,
        stage=body.target_stage,
        deployed_at=datetime.now(timezone.utc),
        previous_production_version=prev_version,
        message=f"模型 {model_name} v{model_version} 已晋级至 {body.target_stage}"
        + (f" (替换 v{prev_version})" if prev_version else ""),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. POST /api/v1/training/models/{id}/rollback — Rollback model (AC-6.6)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/models/{model_id}/rollback", response_model=RollbackResponse)
async def api_rollback_model(
    model_id: str,
    body: RollbackRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Rollback to a previous model version.

    Per AC-6.6:
    1. Archive current production
    2. Record failure reason
    3. Restore target version to production
    """
    mlflow_client = get_mlflow_client()

    try:
        async with AsyncSessionLocal() as db:
            # Get current production
            result = await db.execute(
                sa_text(
                    "SELECT * FROM model_registry WHERE id = :id OR "
                    "(name = (SELECT name FROM model_registry WHERE id = :id2) AND stage = 'production')"
                ),
                {"id": model_id, "id2": model_id},
            )
            rows = result.fetchall()
            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "model_not_found", "message": f"Model {model_id} not found"},
                )

            target_model = None
            production_model = None
            for row in rows:
                d = dict(row._mapping)
                if d["id"] == model_id:
                    target_model = d
                elif d["stage"] == "production":
                    production_model = d

            if not target_model:
                target_model = production_model

            model_name = target_model["name"]

            # Get target version
            result2 = await db.execute(
                sa_text(
                    "SELECT * FROM model_registry WHERE name = :name AND version = :version"
                ),
                {"name": model_name, "version": body.target_version},
            )
            target_row = result2.fetchone()
            if not target_row:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "model_not_found", "message": f"Version {body.target_version} not found for {model_name}"},
                )
            target = dict(target_row._mapping)

            # Archive current production
            await db.execute(
                sa_text(
                    "UPDATE model_registry SET stage = 'archived', "
                    "updated_at = NOW(), notes = :reason WHERE stage = 'production' AND name = :name"
                ),
                {"name": model_name, "reason": body.reason},
            )

            # Promote target
            await db.execute(
                sa_text(
                    "UPDATE model_registry SET stage = 'production', "
                    "deployed_at = NOW(), deployed_by = :user, updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {"id": target["id"], "user": current_user.get("name", "admin")},
            )
            await db.commit()

            current_version = production_model["version"] if production_model else target_model["version"]
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to rollback model")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})

    # Sync MLflow
    try:
        mlflow_client.set_production_model(model_name, body.target_version)
    except Exception as e:
        logger.warning("MLflow sync failed: %s", e)

    return RollbackResponse(
        model_id=target["id"],
        new_production_version=body.target_version,
        rolled_back_from=current_version,
        reason=body.reason,
        message=f"已回滚到 {model_name} v{body.target_version}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6b. POST /api/v1/training/models/{id}/archive — Archive model
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/models/{model_id}/archive")
async def api_archive_model(
    model_id: str,
    body: ArchiveRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Archive a model (set stage to 'archived' with reason notes).

    Used when A/B comparison shows the new model is worse than the
    production model — the new staging model is archived and the
    old production model is kept.
    """
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM model_registry WHERE id = :id"),
                {"id": model_id},
            )
            row = result.fetchone()
            if not row:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "model_not_found", "message": f"Model {model_id} not found"},
                )
            d = dict(row._mapping)

            # Only archive staging models (production should use rollback)
            if d["stage"] == "production":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "cannot_archive",
                        "message": "线上模型不支持直接归档，请使用回滚功能",
                    },
                )

            await db.execute(
                sa_text(
                    "UPDATE model_registry SET stage = 'archived', "
                    "updated_at = NOW(), notes = :reason WHERE id = :id"
                ),
                {"id": model_id, "reason": body.reason},
            )
            await db.commit()

        return {
            "model_id": model_id,
            "stage": "archived",
            "reason": body.reason,
            "message": f"模型 {d['name']} v{d['version']} 已归档",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to archive model")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})


# ═══════════════════════════════════════════════════════════════════════════
# 7. GET /api/v1/training/models/{id}/compare — Compare models (AC-6.4)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/models/{model_id}/compare", response_model=ModelCompareResponse)
async def api_compare_models(
    model_id: str,
    backtest_start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    backtest_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    top_k: int = Query(50, ge=10, le=200, description="Backtest top K"),
    current_user: dict = Depends(require_role("admin")),
):
    """Compare new model vs current production model (AC-6.4).

    Runs backtest on same dataset and compares key metrics:
    IC, ICIR, Sharpe, max drawdown, annual return, win rate, profit-loss ratio.
    """
    mlflow_client = get_mlflow_client()

    # Get target model
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                sa_text("SELECT * FROM model_registry WHERE id = :id"),
                {"id": model_id},
            )
            row = result.fetchone()
            if not row:
                mlflow_record = _find_mlflow_model_record(model_id, mlflow_client)
                if not mlflow_record:
                    raise HTTPException(
                        status_code=404,
                        detail={"error": "model_not_found", "message": f"Model {model_id} not found"},
                    )
                new_model_data = mlflow_record.model_dump()
                old_model_data = None
            else:
                new_model_data = dict(row._mapping)
                model_name = new_model_data["name"]

                # Get production model (for comparison)
                result2 = await db.execute(
                    sa_text(
                        "SELECT * FROM model_registry WHERE name = :name "
                        "AND stage = 'production' AND id != :id"
                    ),
                    {"name": model_name, "id": model_id},
                )
                old_row = result2.fetchone()
                old_model_data = dict(old_row._mapping) if old_row else None
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to load models for comparison")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})

    # Parse metrics
    new_metrics = new_model_data.get("metrics", {})
    if isinstance(new_metrics, str):
        new_metrics = json.loads(new_metrics)
    new_metrics = new_metrics or {}

    old_metrics = {}
    if old_model_data:
        old_metrics = old_model_data.get("metrics", {})
        if isinstance(old_metrics, str):
            old_metrics = json.loads(old_metrics)
        old_metrics = old_metrics or {}

    comparisons, verdict, recommendation = _build_truthful_comparison(
        new_metrics,
        old_metrics if old_model_data else None,
    )

    # Build response model records
    new_record = ModelRecord(
        id=new_model_data["id"],
        name=new_model_data["name"],
        version=new_model_data["version"],
        model_type=ModelType(new_model_data["model_type"]),
        stage=ModelStage(new_model_data["stage"]),
        run_id=new_model_data.get("run_id"),
        metrics=new_metrics,
        created_by=new_model_data.get("created_by", "unknown"),
        created_at=new_model_data["created_at"],
    )

    old_record = None
    if old_model_data:
        old_record = ModelRecord(
            id=old_model_data["id"],
            name=old_model_data["name"],
            version=old_model_data["version"],
            model_type=ModelType(old_model_data["model_type"]),
            stage=ModelStage(old_model_data["stage"]),
            run_id=old_model_data.get("run_id"),
            metrics=old_metrics,
            created_by=old_model_data.get("created_by", "unknown"),
            created_at=old_model_data["created_at"],
        )

    return ModelCompareResponse(
        new_model=new_record,
        old_model=old_record,
        comparison=comparisons,
        verdict=verdict,
        recommendation=recommendation,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. POST /api/v1/training/schedule — Configure auto schedule (AC-6.2)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/schedule", response_model=ScheduleUpdateResponse)
async def api_configure_schedule(
    body: ScheduleConfig,
    current_user: dict = Depends(require_role("admin")),
):
    """Configure automatic training schedule (AC-6.2).

    Persists schedule to DB and updates APScheduler.
    """
    from app.scheduler import update_schedule

    try:
        result = await update_schedule(body)
        return ScheduleUpdateResponse(
            enabled=result["enabled"],
            cron=result["cron"],
            next_run=result.get("next_run"),
            message=result["message"],
        )
    except Exception as e:
        logger.exception("Failed to update schedule")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})


# ═══════════════════════════════════════════════════════════════════════════
# 9. GET /api/v1/training/schedule — View schedule (AC-6.2)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/schedule", response_model=ScheduleStatusResponse)
async def api_get_schedule(
    current_user: dict = Depends(require_role("admin")),
):
    """Get current training schedule configuration and status."""
    from app.scheduler import get_schedule_status

    try:
        status = await get_schedule_status()
        return ScheduleStatusResponse(
            enabled=status["enabled"],
            cron=status["cron"],
            model_type=ModelType(status["model_type"]),
            params=status.get("params"),
            auto_deploy=status["auto_deploy"],
            next_run=status.get("next_run"),
            last_run=status.get("last_run"),
            last_job_id=status.get("last_job_id"),
            last_job_status=status.get("last_job_status"),
        )
    except Exception as e:
        logger.exception("Failed to get schedule")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})


# ═══════════════════════════════════════════════════════════════════════════
# 10. GET /api/v1/training/history — Training history (AC-6.8)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/history", response_model=PaginatedHistoryResponse)
async def api_training_history(
    model_type: Optional[str] = Query(None, description="Filter by model type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    created_by: Optional[str] = Query(None, description="Filter by creator"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(require_role("admin")),
):
    """List training history with filters and pagination (AC-6.8)."""
    jobs = list_jobs(
        model_type=model_type,
        status=status,
        created_by=created_by,
        start_date=start_date,
        end_date=end_date,
    )

    total = len(jobs)
    start = (page - 1) * page_size
    end = start + page_size
    paged = jobs[start:end]

    items = []
    for job in paged:
        duration = None
        if job.started_at and job.completed_at:
            duration = (job.completed_at - job.started_at).total_seconds()

        final_metrics = None
        if job.final_metrics:
            final_metrics = job.final_metrics.model_dump()

        items.append(TrainingHistoryItem(
            job_id=job.job_id,
            model_type=job.model_type,
            status=job.status,
            params=job.params.model_dump() if job.params else None,
            final_metrics=final_metrics,
            model_uri=job.model_uri,
            created_by=job.created_by,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            duration_seconds=round(duration, 1) if duration else None,
        ))

    return PaginatedHistoryResponse(
        jobs=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 11. POST /api/v1/training/calibrate — Factor calibration (AC-6.7)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/calibrate", response_model=CalibrateResponse)
async def api_calibrate_factors(
    body: CalibrateRequest,
    current_user: dict = Depends(require_role("admin")),
):
    """Run factor weight calibration (AC-6.7).

    Computes IC/ICIR for each factor and updates weights.
    If apply=true, persists new weights to factor_weights table.
    """
    from app.factor_calibration import run_calibration as do_calibrate

    try:
        result = await do_calibrate(
            mode=body.mode,
            window_days=body.window_days,
            min_samples=body.min_samples,
            apply=body.apply,
            evaluation_id=body.evaluation_id,
        )
        if result.get("status") != "ready":
            raise HTTPException(status_code=409, detail={
                "code": "INSUFFICIENT_EVALUATION_EVIDENCE",
                "missing_requirements": result.get("missing_requirements", []),
            })
        return CalibrateResponse(
            calibrated_at=result["calibrated_at"],
            window_start=result["window_start"],
            window_end=result["window_end"],
            factors=result["factors"],
            summary=result["summary"],
            evaluation_id=result["evaluation_id"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Calibration failed")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})


# ═══════════════════════════════════════════════════════════════════════════
# 12. GET /api/v1/training/factors/ic — IC/ICIR analysis (AC-5.6)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/factors/ic", response_model=FactorICResponse)
async def api_get_ic_analysis(
    factors: Optional[str] = Query(None, description="Comma-separated factor names"),
    window_days: int = Query(90, ge=30, le=365, description="Rolling window days"),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    current_user: dict = Depends(require_role("admin")),
):
    """Get IC/ICIR rolling window analysis (AC-5.6).

    Returns current IC, ICIR, rolling history for each factor.
    """
    from app.factor_calibration import get_ic_analysis

    try:
        factor_list = factors.split(",") if factors else None
        result = await get_ic_analysis(
            factors=factor_list,
            window_days=window_days,
            start_date=start_date,
            end_date=end_date,
        )
        return FactorICResponse(
            window_days=result["window_days"],
            date_range=result["date_range"],
            factors=result["factors"],
        )
    except Exception as e:
        logger.exception("IC analysis failed")
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "internal server error"})
