"""Pydantic schemas for training-service — PRD AC-6.1~6.9.

Matches the contracts defined in docs/design/model-training/api-contract.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _training_model_metadata() -> Dict[str, Any]:
    return {
        "name": "training-orchestrator",
        "version": "training-contract-v2",
        "provider": "training-service",
        "inference_mode": "run",
    }


def _model_registry_metadata() -> Dict[str, Any]:
    return {
        "name": "model-registry",
        "version": "registry-contract-v2",
        "provider": "training-service",
        "inference_mode": "registry",
    }


def _freshness(source: str) -> Dict[str, Any]:
    return {
        "status": "unknown",
        "as_of": None,
        "source": source,
        "quality_score": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class ModelType(str, Enum):
    LIGHTGBM = "lightgbm"
    CATBOOST = "catboost"
    KRONOS_FINETUNE = "kronos_finetune"


class JobStatus(str, Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    RUNNING = "running"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelStage(str, Enum):
    NONE = "none"
    RESEARCH = "research"
    CANDIDATE = "candidate"
    PAPER = "paper"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


# ═══════════════════════════════════════════════════════════════════════════
# Training Params & Metrics
# ═══════════════════════════════════════════════════════════════════════════

class TrainingParams(BaseModel):
    """Training hyperparameters (transparent to Optuna search_space or fixed)."""
    model_type: ModelType = Field(..., description="Model type")
    horizon: int = Field(default=15, ge=1, le=60, description="Forecast holding days (V2: 10→15)")
    lookback: int = Field(default=180, ge=30, le=500, description="Lookback window days (V2: 90→180)")
    n_trials: int = Field(default=50, ge=1, le=500, description="Optuna trial count")
    cv_folds: int = Field(default=5, ge=2, le=10, description="Cross-validation folds")
    early_stopping_rounds: int = Field(default=50, ge=10, le=200)
    learning_rate: Optional[float] = Field(
        default=None, ge=0.001, le=1.0,
        description="None means Optuna searches"
    )
    max_depth: Optional[int] = Field(
        default=None, ge=2, le=16,
        description="None means Optuna searches"
    )
    num_leaves: Optional[int] = Field(
        default=None, ge=8, le=512,
        description="LightGBM only; None means Optuna searches"
    )
    subsample: Optional[float] = Field(default=None, ge=0.3, le=1.0)
    colsample_bytree: Optional[float] = Field(default=None, ge=0.3, le=1.0)
    data_start_date: Optional[str] = Field(
        default=None,
        description="Training data start date (YYYY-MM-DD), None = all available"
    )
    data_end_date: Optional[str] = Field(
        default=None,
        description="Training data end date (YYYY-MM-DD), None = latest"
    )
    factor_whitelist: Optional[List[str]] = Field(
        default=None,
        description="Limit factor list; None = all 14 factors"
    )
    test_size: float = Field(
        default=0.2, ge=0.05, le=0.5,
        description="Validation set ratio"
    )


class TrainingMetrics(BaseModel):
    """Real-time metric snapshot during training."""
    trial: int = Field(..., description="Current Optuna trial number")
    epoch: Optional[int] = Field(default=None, description="Current epoch")
    train_loss: float
    valid_loss: float
    best_valid_loss: float
    ic: Optional[float] = Field(default=None, description="Validation set IC (Rank IC)")
    icir: Optional[float] = Field(default=None, description="Validation set ICIR")
    feature_importance: Optional[Dict[str, float]] = Field(
        default=None, description="Top 10 feature importance"
    )
    elapsed_seconds: float


# ═══════════════════════════════════════════════════════════════════════════
# Training Job
# ═══════════════════════════════════════════════════════════════════════════

class TrainingJob(BaseModel):
    """Complete training job record."""
    job_id: str = Field(..., description="UUID v4")
    model_type: ModelType
    status: JobStatus
    params: TrainingParams
    best_params: Optional[Dict[str, Any]] = Field(
        default=None, description="Optuna best hyperparameters"
    )
    metrics: List[TrainingMetrics] = Field(
        default_factory=list, description="Training metric sequence"
    )
    final_metrics: Optional[TrainingMetrics] = Field(
        default=None, description="Final metrics at completion"
    )
    model_uri: Optional[str] = Field(
        default=None, description="MLflow model URI"
    )
    run_id: Optional[str] = Field(default=None, description="MLflow Run ID")
    experiment_id: Optional[str] = Field(default=None, description="MLflow Experiment ID")
    created_by: str = Field(..., description="Trigger user name")
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    model_metadata: Dict[str, Any] = Field(default_factory=_training_model_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("training.dataset"))
    fallback_reason: Optional[str] = None


class TrainRequest(BaseModel):
    """POST /api/v1/training/run request body."""
    params: TrainingParams
    auto_deploy: bool = Field(
        default=False,
        description="Auto-deploy if new model beats old"
    )


class TrainResponse(BaseModel):
    """POST /api/v1/training/run response body."""
    job_id: str
    status: JobStatus
    created_at: datetime
    model_metadata: Dict[str, Any] = Field(default_factory=_training_model_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("training.dataset"))
    fallback_reason: Optional[str] = None


class JobStatusResponse(BaseModel):
    """GET /api/v1/training/status/{job_id} response."""
    job_id: str
    model_type: ModelType
    status: JobStatus
    params: TrainingParams
    current_metrics: Optional[TrainingMetrics] = None
    best_params: Optional[Dict[str, Any]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    model_metadata: Dict[str, Any] = Field(default_factory=_training_model_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("training.dataset"))
    fallback_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# Model Registry
# ═══════════════════════════════════════════════════════════════════════════

class ModelRecord(BaseModel):
    """Model registry record (maps MLflow RegisteredModel + Version)."""
    id: str = Field(..., description="Model version ID")
    name: str = Field(..., description="Registered model name, e.g. lightgbm-ranker")
    version: int = Field(..., ge=1, description="MLflow version number")
    model_type: ModelType
    stage: ModelStage
    run_id: Optional[str] = None
    experiment_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = Field(default=None, description="Training params snapshot")
    metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Model metrics (train_loss, valid_loss, ic, icir, sharpe etc.)"
    )
    artifact_uri: Optional[str] = Field(
        default=None, description="Model file path (MLflow artifact_uri)"
    )
    deployed_at: Optional[datetime] = None
    deployed_by: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, description="Notes / failure reason")
    model_metadata: Dict[str, Any] = Field(default_factory=_model_registry_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("model_registry"))
    fallback_reason: Optional[str] = None


class CompareResult(BaseModel):
    """AC-6.4: New model vs old model backtest comparison."""
    metric: str = Field(..., description="Comparison metric name")
    new_value: float
    old_value: float
    delta: float = Field(..., description="new - old")
    delta_pct: float = Field(..., description="Percent change")
    better: bool = Field(..., description="Is new model better")
    threshold: float = Field(default=0.0, description="Threshold for 'better'")


class ModelCompareResponse(BaseModel):
    """GET /models/{id}/compare response body."""
    new_model: ModelRecord
    old_model: Optional[ModelRecord] = Field(
        default=None, description="Current production model; None if no old model"
    )
    comparison: List[CompareResult]
    verdict: str = Field(
        ...,
        description="Overall verdict: 'new_better' | 'old_better' | 'inconclusive'"
    )
    recommendation: str = Field(
        ...,
        description="Action recommendation"
    )
    model_metadata: Dict[str, Any] = Field(default_factory=_model_registry_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("model_registry"))
    fallback_reason: Optional[str] = None


class DeployRequest(BaseModel):
    """POST /models/{id}/deploy request body."""
    force: bool = Field(default=False)
    notes: Optional[str] = None
    target_stage: str = Field(default="production", pattern="^(candidate|paper|production)$")
    evidence: Dict[str, Any] = Field(default_factory=dict)
    manual_approval: bool = False
    baseline_exists: bool = True


class DeployResponse(BaseModel):
    """POST /models/{id}/deploy response."""
    model_id: str
    stage: str
    deployed_at: datetime
    previous_production_version: Optional[int] = None
    message: str


class RollbackRequest(BaseModel):
    """POST /models/{id}/rollback request body."""
    target_version: int = Field(..., ge=1)
    reason: str = Field(default="", description="Rollback reason")


class RollbackResponse(BaseModel):
    """POST /models/{id}/rollback response."""
    model_id: str
    new_production_version: int
    rolled_back_from: int
    reason: str
    message: str


class ArchiveRequest(BaseModel):
    """POST /models/{id}/archive request body."""
    reason: str = Field(..., min_length=1, description="Archive reason")


class PaginatedModelsResponse(BaseModel):
    models: List[ModelRecord]
    total: int
    page: int
    page_size: int
    model_metadata: Dict[str, Any] = Field(default_factory=_model_registry_metadata)
    data_freshness: Dict[str, Any] = Field(default_factory=lambda: _freshness("model_registry"))
    fallback_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# Schedule & History
# ═══════════════════════════════════════════════════════════════════════════

class ScheduleConfig(BaseModel):
    """Auto training schedule configuration (AC-6.2)."""
    enabled: bool = Field(default=False)
    cron: str = Field(default="0 2 * * 6", description="Cron expression")
    model_type: ModelType = Field(default=ModelType.LIGHTGBM)
    params: TrainingParams
    auto_deploy: bool = Field(default=False)
    notify_on_complete: bool = Field(default=True, description="Notify admin on complete")
    notify_channels: List[str] = Field(
        default_factory=lambda: ["email", "wecom"],
        description="Notification channels"
    )


class ScheduleStatusResponse(BaseModel):
    """GET /api/v1/training/schedule response."""
    enabled: bool
    cron: str
    model_type: ModelType
    params: Optional[TrainingParams] = None
    auto_deploy: bool
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    last_job_id: Optional[str] = None
    last_job_status: Optional[str] = None


class ScheduleUpdateResponse(BaseModel):
    """POST /api/v1/training/schedule response."""
    enabled: bool
    cron: str
    next_run: Optional[str] = None
    message: str


class TrainingHistoryItem(BaseModel):
    job_id: str
    model_type: ModelType
    status: JobStatus
    params: Optional[Dict[str, Any]] = None
    final_metrics: Optional[Dict[str, Any]] = None
    model_uri: Optional[str] = None
    created_by: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None


class PaginatedHistoryResponse(BaseModel):
    jobs: List[TrainingHistoryItem]
    total: int
    page: int
    page_size: int


# ═══════════════════════════════════════════════════════════════════════════
# Factor Calibration & IC Analysis
# ═══════════════════════════════════════════════════════════════════════════

class CalibrateRequest(BaseModel):
    """POST /api/v1/training/calibrate request body (AC-6.7)."""
    mode: str = Field(default="all", description="all | short | both")
    window_days: int = Field(default=90, ge=30, le=365, description="Rolling window days")
    min_samples: int = Field(default=30, ge=10, le=200, description="Min valid samples per factor")
    apply: bool = Field(default=False, description="Auto-apply calibration results to screener")
    evaluation_id: str = Field(..., min_length=4, description="Persisted ready factor evaluation ID")


class FactorWeight(BaseModel):
    factor_name: str
    factor_label: str
    ic: float = Field(..., description="Information Coefficient (Spearman Rank IC)")
    icir: float = Field(..., description="IC Information Ratio = mean(IC) / std(IC)")
    old_weight: float
    new_weight: float
    direction: str = Field(..., description="long | short")
    significance: str = Field(..., description="t-test significance: significant | marginal | none")


class CalibrateResponse(BaseModel):
    """Factor calibration result."""
    calibrated_at: datetime
    window_start: str
    window_end: str
    factors: List[FactorWeight]
    summary: str
    evaluation_id: str


class ICWindow(BaseModel):
    """IC rolling window data point."""
    window_end: str = Field(..., description="Window end date")
    ic: float
    icir: float
    n_stocks: int


class FactorICItem(BaseModel):
    factor_name: str
    factor_label: str
    current_ic: float
    current_icir: float
    ic_mean: float
    ic_std: float
    icir_mean: float
    direction: str
    rolling: List[ICWindow] = Field(default_factory=list)


class FactorICResponse(BaseModel):
    """GET /api/v1/training/factors/ic response."""
    window_days: int
    date_range: str
    factors: List[FactorICItem]


# ═══════════════════════════════════════════════════════════════════════════
# Error responses
# ═══════════════════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    error: str
    message: str
    detail: Optional[Any] = None
