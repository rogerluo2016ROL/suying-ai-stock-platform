"""Data Service REST API — 手动触发 + 状态查询."""

import logging
from datetime import date
from fastapi import APIRouter, Query, HTTPException

from app.scheduler import get_job_status
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext

logger = logging.getLogger("data-service.api")
router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/status")
async def data_status():
    """获取所有定时任务状态 + 下次执行时间."""
    return get_job_status()


@router.post("/sync/rt_min")
async def trigger_rt_min():
    """手动触发实时分钟线采集."""
    try:
        result = collect_rt_min()
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sync/auction")
async def trigger_auction():
    """手动触发竞价快照."""
    try:
        result = collect_rt_min()
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sync/post_market")
async def trigger_post_market(date_param: str = Query(None, alias="date")):
    """手动触发盘后同步 (P0+P1)."""
    trade_date = date_param or date.today().strftime("%Y-%m-%d")
    try:
        core = sync_post_market_core(trade_date)
        ext = sync_post_market_ext(trade_date)
        return {"status": "ok", "core": core, "ext": ext}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "data-service"}
