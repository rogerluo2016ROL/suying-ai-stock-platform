from datetime import datetime, timezone

from app.schemas import (
    JobStatus,
    JobStatusResponse,
    ModelRecord,
    ModelStage,
    ModelType,
    PaginatedModelsResponse,
    TrainResponse,
    TrainingParams,
)


def test_train_response_has_new_ui_contract_fields():
    response = TrainResponse(
        job_id="job-1",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )

    assert response.model_metadata["name"] == "training-orchestrator"
    assert response.data_freshness["source"] == "training.dataset"
    assert response.fallback_reason is None


def test_job_status_response_has_new_ui_contract_fields():
    response = JobStatusResponse(
        job_id="job-1",
        model_type=ModelType.LIGHTGBM,
        status=JobStatus.RUNNING,
        params=TrainingParams(model_type=ModelType.LIGHTGBM),
    )

    assert response.model_metadata["provider"] == "training-service"
    assert response.data_freshness["status"] == "unknown"


def test_model_registry_response_has_model_metadata_and_release_gate():
    record = ModelRecord(
        id="mdl-lightgbm-v1",
        name="lightgbm-ranker",
        version=1,
        model_type=ModelType.LIGHTGBM,
        stage=ModelStage.STAGING,
        created_by="system",
        created_at=datetime.now(timezone.utc),
    )
    response = PaginatedModelsResponse(models=[record], total=1, page=1, page_size=20)

    assert record.model_metadata["name"] == "model-registry"
    assert record.fallback_reason is None
    assert response.model_metadata["name"] == "model-registry"
    assert response.data_freshness["source"] == "model_registry"
