"""Data Service REST API — 手动触发 + 状态查询."""

import logging
from datetime import date, timedelta
from fastapi import APIRouter, Query, HTTPException

from app.scheduler import (
    get_job_status,
    _run_job,
    _job_status,
    _BACKFILL_MAP,
    _extract_pg_status,
    collect_auction_snapshot,
)
from app.sync.rt_min import collect_rt_min
from app.sync.tushare import sync_post_market_core, sync_post_market_ext
from app.sync.stocks import sync_stock_list
from app.sync.rate_limiter import get_rate_limit_status
from app.sync.pg_writer import PG_URL
from app.config import get_runtime_config_status
from app import inventory
from app.quality.readiness import evaluate
from app.quality.evaluator import ReadinessEvaluator
from app.quality.contracts import SourceState
from app.quality.repository import save, get

logger = logging.getLogger("data-service.api")
router = APIRouter(prefix="/api/v1/data", tags=["data"])

_STOCKS_REQUIRED_BACKFILLS = {"daily_kline", "weekly_kline", "monthly_kline"}


def _latest_completed_weekday() -> date:
    day = date.today() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def _sync_required_dependencies(table_key: str) -> dict | None:
    if table_key not in _STOCKS_REQUIRED_BACKFILLS:
        return None

    result = sync_stock_list()
    if result.get("status") == "error":
        raise HTTPException(
            502,
            {
                "detail": "stocks dependency sync failed",
                "dependency": "stocks",
                "result": result,
            },
        )
    return {"dependency": "stocks", **result}


def _has_latest_completed_trade_day(table_key: str) -> bool:
    if table_key not in _STOCKS_REQUIRED_BACKFILLS:
        return False

    try:
        import psycopg2

        conn = psycopg2.connect(PG_URL, connect_timeout=3)
        cur = conn.cursor()
        try:
            cur.execute("SELECT MAX(cal_date) FROM trade_cal WHERE is_open=1 AND cal_date < CURRENT_DATE")
            expected = cur.fetchone()[0] or _latest_completed_weekday()
        except Exception:
            conn.rollback()
            expected = _latest_completed_weekday()
        cur.execute(f"SELECT MAX(trade_date) FROM {table_key}")
        actual = cur.fetchone()[0]
        conn.close()
        return bool(expected and actual and actual >= expected)
    except Exception as e:
        logger.debug("latest completed trade day check failed for %s: %s", table_key, e)
        return False


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

@router.get("/inventory")
async def data_inventory():
    return inventory.inventory()

@router.get("/jobs")
async def data_jobs():
    return get_job_status()

@router.get("/schedules")
async def data_schedules():
    return {"schedules": [{"id": j.get("id"), "cron": j.get("cron"), "name": j.get("name")} for j in get_job_status().get("jobs", [])]}

@router.get("/readiness")
async def data_readiness():
    # readiness 与兼容 status 使用同一套组件判定，避免“未配 Tushare 仍 ready”。
    return _build_readiness_status()

@router.post('/readiness/evaluate')
async def evaluate_readiness(profile: str, target_trade_date: date, cutoff_time=None):
    def loader(source):
        try:
            import psycopg2
            conn = psycopg2.connect(PG_URL, connect_timeout=2); cur = conn.cursor()
            cur.execute(f'SELECT MAX(trade_date) FROM "{source}"')
            value = cur.fetchone()[0]; conn.close()
            return SourceState(value, 1.0)
        except Exception:
            return SourceState(None, 0.0)
    result = ReadinessEvaluator(loader).evaluate(profile, target_trade_date, cutoff_time)
    return save(result)

@router.get('/readiness/snapshots/{snapshot_id}')
async def readiness_snapshot(snapshot_id: str):
    result = get(snapshot_id)
    if result is None: raise HTTPException(404, 'snapshot not found')
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


@router.post("/sync/backfill")
async def trigger_table_backfill(
    table_key: str = Query(..., description="Backfill table key, e.g. top_list, daily_kline"),
    days: int = Query(30, ge=1, le=3650, description="Days back to sync"),
):
    """手动触发指定数据表回补，复用 scheduler 的真实回补函数表."""
    fn = _BACKFILL_MAP.get(table_key)
    if fn is None:
        raise HTTPException(
            400,
            {
                "detail": f"不支持的表: {table_key}",
                "supported": sorted(_BACKFILL_MAP.keys()),
            },
        )

    try:
        dependency_sync = _sync_required_dependencies(table_key)
        result = fn(days_back=days)
        pg_status, pg_written = _extract_pg_status(result)
        result_status = result.get("status") if isinstance(result, dict) else None
        status = result_status if result_status in {"ok", "skipped", "error"} else "ok"
        noop_reason = None
        if status == "ok" and pg_status == "partial" and _has_latest_completed_trade_day(table_key):
            pg_status = "ok"
            noop_reason = "already_up_to_date"
        payload = {
            "status": "error" if status in {"skipped", "error"} else "ok",
            "table_key": table_key,
            "days": days,
            "result": result,
            "pg_write_status": pg_status,
            "pg_written": pg_written,
            "written": int((result or {}).get("pg_written") or (result or {}).get("written") or pg_written)
            if isinstance(result, dict) else pg_written,
        }
        if dependency_sync is not None:
            payload["dependency_sync"] = dependency_sync
        if noop_reason is not None:
            payload["noop_reason"] = noop_reason
        if status in {"skipped", "error"} and isinstance(result, dict):
            payload["message"] = result.get("reason") or result.get("message") or status
        _job_status[f"manual_backfill:{table_key}"] = {
            "last_run": date.today().isoformat(),
            "last_status": status,
            "result": str(result)[:300],
            "pg_write_status": pg_status,
            "pg_written": pg_written,
        }
        return payload
    except Exception as e:
        logger.exception("Manual backfill failed for %s", table_key)
        raise HTTPException(500, str(e))


@router.get("/health")
async def health():
    return {"status": "healthy", "service": "data-service"}


@router.get("/readiness")
async def readiness():
    return _build_readiness_status()
