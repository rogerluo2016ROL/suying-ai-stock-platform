"""Data Service REST API — 手动触发 + 状态查询."""

import logging
from datetime import date
from fastapi import APIRouter, Query, HTTPException

from app.scheduler import get_job_status, _run_job, _job_status, collect_auction_snapshot
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.stocks import sync_stock_list
from app.sync.rate_limiter import get_rate_limit_status
from app.sync.pg_writer import PG_URL
from app.config import get_runtime_config_status

logger = logging.getLogger("data-service.api")
router = APIRouter(prefix="/api/v1/data", tags=["data"])


def _check_pg_connection() -> dict:
    """Return a non-secret PG connectivity status for readiness endpoints."""
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
    return {"url": PG_URL.split("@")[-1] if "@" in PG_URL else PG_URL, "ok": pg_ok}


def _find_job_status(status: dict, job_id: str) -> dict:
    for job in status.get("jobs", []):
        if job.get("id") == job_id:
            return job
    return {"id": job_id, "last_status": "unknown", "last_run": None, "last_result": ""}


def _build_readiness_status() -> dict:
    job_status = get_job_status()
    pg_connection = _check_pg_connection()
    runtime_config = get_runtime_config_status()
    components = {
        "service_alive": True,
        "scheduler_running": bool(job_status.get("scheduler_running")),
        "pg_ok": bool(pg_connection.get("ok")),
        "tushare_configured": bool(runtime_config["tushare"]["configured"]),
    }
    return {
        "ready": all(components.values()),
        "components": components,
        "pg_connection": pg_connection,
        "runtime_config": runtime_config,
        "last_auction_status": _find_job_status(job_status, "auction"),
    }


@router.get("/status")
async def data_status():
    """获取所有定时任务状态 + PG 写入状态 + API 限频状态."""
    result = get_job_status()

    # 附加 PG 连接状态 (ADR-006)
    result["pg_connection"] = _check_pg_connection()
    result["runtime_config"] = get_runtime_config_status()
    result["readiness"] = _build_readiness_status()

    # 附加限频状态 (ADR-006)
    result["rate_limiter"] = get_rate_limit_status()

    # 汇总 PG 写入统计
    pg_totals = {}
    for job in result.get("jobs", []):
        job_id = job.get("id", "")
        pg_count = job.get("pg_written", 0)
        if pg_count:
            pg_totals[job_id] = pg_count
    result["pg_write_summary"] = pg_totals

    # 兼容前端 DataUpdate 页面格式
    result["sources"] = [
        {"key": j["id"], "name": j["name"], "category": j["id"].split("_")[0] if "_" in j["id"] else "L2",
         "source": "Tushare", "update": j["cron"], "note": "",
         "rows": j.get("pg_written", 0), "min_date": "", "max_date": "",
         "status": "active" if j.get("last_status") == "ok" else "pending"}
        for j in result.get("jobs", [])
    ]
    result["sync_map"] = {
        j["id"]: {"mode": j["id"], "days_default": 30, "desc": j["name"]}
        for j in result.get("jobs", [])
    }
    result["total_tables"] = len(result.get("jobs", []))
    result["active_tables"] = sum(1 for j in result.get("jobs", []) if j.get("last_status") == "ok")
    result["total_rows"] = sum(j.get("pg_written", 0) for j in result.get("jobs", []))

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
    """手动触发竞价快照 (Tushare stk_auction → PG, B2 后不再走 SQLite mootdx fallback)."""
    try:
        result = collect_auction_snapshot()
        return {"status": "ok", **result}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/sync/post_market")
async def trigger_post_market(date_param: str = Query(None, alias="date")):
    """手动触发盘后同步 (P0+P1) — 经 _run_job 更新 _job_status."""
    trade_date = date_param or date.today().strftime("%Y-%m-%d")
    try:
        core_job = {"id": "post_market_core", "fn": sync_post_market_core,
                    "args": (trade_date,)}
        ext_job = {"id": "post_market_ext", "fn": sync_post_market_ext,
                   "args": (trade_date,)}
        await _run_job(core_job)
        await _run_job(ext_job)
        return {"status": "ok",
                "core": _job_status.get("post_market_core", {}),
                "ext": _job_status.get("post_market_ext", {})}
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


@router.get("/readiness")
async def readiness():
    return _build_readiness_status()
