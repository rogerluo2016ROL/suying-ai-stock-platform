"""Data Service REST API — 手动触发 + 状态查询."""

import logging
from datetime import date
from fastapi import APIRouter, Query, HTTPException

from app.scheduler import get_job_status
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.stocks import sync_stock_list
from app.sync.rate_limiter import get_rate_limit_status
from app.sync.pg_writer import PG_URL

logger = logging.getLogger("data-service.api")
router = APIRouter(prefix="/api/v1/data", tags=["data"])


@router.get("/status")
async def data_status():
    """获取所有定时任务状态 + PG 写入状态 + API 限频状态."""
    result = get_job_status()

    # 附加 PG 连接状态 (ADR-006)
    pg_ok = False
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        pg_ok = True
        conn.close()
    except Exception:
        pass
    result["pg_connection"] = {"url": PG_URL.split("@")[-1] if "@" in PG_URL else PG_URL, "ok": pg_ok}

    # 附加限频状态 (ADR-006)
    result["rate_limiter"] = get_rate_limit_status()

    # 汇总 PG 写入统计 (直接从 scheduler 返回的 pg_write_status/pg_written 字段读取)
    pg_totals = {}
    for job in result.get("jobs", []):
        job_id = job.get("id", "")
        pg_count = job.get("pg_written", 0)
        if pg_count:
            pg_totals[job_id] = pg_count
    result["pg_write_summary"] = pg_totals

    return result


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


@router.post("/sync/stocks")
async def trigger_stocks_sync():
    """手动触发股票列表同步 (全量)."""
    try:
        result = sync_stock_list()
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "data-service"}
