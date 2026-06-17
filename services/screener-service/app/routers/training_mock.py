"""Minimal training endpoints — enables ModelRegistry page to load without training-service."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/training", tags=["training"])


@router.get("/models")
async def list_models(page: int = 1, page_size: int = 50):
    """Return empty model list when training-service is not running."""
    return {
        "models": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    return {"detail": "训练服务未启动，模型数据不可用"}


@router.get("/models/{model_id}/compare")
async def compare_model(model_id: str):
    return {"detail": "训练服务未启动"}


@router.post("/models/{model_id}/deploy")
async def deploy_model(model_id: str):
    return {"detail": "训练服务未启动"}


@router.post("/models/{model_id}/rollback")
async def rollback_model(model_id: str):
    return {"detail": "训练服务未启动"}


@router.post("/models/{model_id}/archive")
async def archive_model(model_id: str):
    return {"detail": "训练服务未启动"}


@router.get("/factors/ic")
async def factors_ic(window_days: int = 120):
    return {"factors": [], "period": f"{window_days}d"}


@router.post("/calibrate")
async def calibrate():
    return {"detail": "训练服务未启动"}


@router.get("/schedule")
async def schedule_status():
    return {"jobs": [], "scheduler_running": False}


@router.get("/history")
async def training_history(page: int = 1, page_size: int = 50):
    return {"items": [], "total": 0}
