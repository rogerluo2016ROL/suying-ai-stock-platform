"""Signal API routes — real-time signal generation powered by kronos-factors.

装配入口：router 对象与共享 helpers 在 app/_shared.py，路由实现按域拆分在
app/routers/{dashboard,analysis,data}.py。本模块保留：
- router 装配（import 子模块触发路由注册）
- /signal/trigger-sync 端点及其代理函数（与测试 monkeypatch 耦合，须留在本模块全局命名空间）
- 对既有 `from app import routes` 使用方的兼容 re-export
"""

import asyncio
import os, logging
from fastapi import Depends, Query
from kronos_auth import require_role

from app._shared import (  # noqa: F401 — re-export 兼容层
    router, dashboard_router, data_router, store,
    _service_url, _service_auth_headers, _http_post_json,
    DIAGNOSIS_ANALYZE_URL, SCREENER_RUN_URL,
    _signal_model_metadata, _SIGNAL_DIMENSION_WEIGHTS, _combine_signal_dimensions,
    _coerce_iso_date, _signal_data_freshness, _with_signal_contract,
    _dashboard_row_change_pct,
)

logger = logging.getLogger("signal-service.routes")


# ── 路由域子模块：import 即注册到共享 router 对象 ──
from app.routers.analysis import (  # noqa: E402,F401 — re-export 兼容层
    super_signal, auction_intent, signal_levels, analyze_signal,
    batch_signals, signal_history, limit_list, update_signal_rules, signal_live,
    _signal_live_sql,
)
from app.routers.dashboard import (  # noqa: E402,F401 — re-export 兼容层
    dashboard_summary, dashboard_screening_summary, dashboard_auction, dashboard_run_pipeline,
    _DASHBOARD_SERVICES,
    _dashboard_market_sentiment_sql, _dashboard_signal_movers_sql, _dashboard_auction_sql,
    _dashboard_volume_alerts_sql, _dashboard_limit_alerts_sql,
    _dashboard_pg_url, _fetch_dashboard_auction_rows,
)
from app.routers.data import (  # noqa: E402,F401 — re-export 兼容层
    data_status, get_sync_schedules, save_sync_schedule, delete_sync_schedule,
    data_status_endpoint, data_sync, data_save_schedule, data_delete_schedule,
    _DATA_SOURCES, _SYNC_MAP,
    DATA_STATUS_DATE_COLUMNS, DATA_STATUS_FALLBACK_DATE_COLUMNS,
    _default_sync_schedules,
)
from app.routers.sentiment import (  # noqa: E402,F401 — re-export 兼容层
    sentiment_index, sentiment_history, sentiment_alerts,
)


def _trigger_sync_via_data_service(table_key: str, days: int) -> dict | None:
    """Proxy manual sync to data-service so Tushare/PG runtime env stays single-source."""
    import json
    import urllib.parse
    import urllib.request

    base = os.environ.get("DATA_SERVICE_URL", "http://127.0.0.1:8010/api/v1/data").rstrip("/")
    if table_key == "stocks":
        req = urllib.request.Request(f"{base}/sync/stocks", method="POST",
                                     headers=_service_auth_headers())
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    query = urllib.parse.urlencode({"table_key": table_key, "days": days})
    req = urllib.request.Request(f"{base}/sync/backfill?{query}", method="POST",
                                 headers=_service_auth_headers())
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


@router.post("/trigger-sync")
async def trigger_sync(
    table_key: str = Query(..., description="Table key e.g. moneyflow, daily_kline"),
    days: int = Query(30, ge=1, le=3650, description="Days back to sync"),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Trigger a Tushare data sync for a specific table.

    Calls the corresponding kronos-data ETL sync function via subprocess.
    Returns status, rows fetched, and rows written.
    """
    if table_key not in _SYNC_MAP:
        return {"status": "error", "message": f"不支持的表: {table_key}, 可选: {list(_SYNC_MAP.keys())}"}

    mode, _, desc = _SYNC_MAP[table_key]
    logger.info("Trigger sync: %s (mode=%s, days=%d)", table_key, mode, days)

    try:
        # 同步 urllib (timeout=300s) 包到线程，避免阻塞事件循环 (原 P1)
        proxied = await asyncio.to_thread(_trigger_sync_via_data_service, table_key, days)
        if proxied is not None:
            return {
                **proxied,
                "table_key": table_key,
                "mode": mode,
                "desc": desc,
                "days": days,
                "source": "data-service",
            }
    except Exception as e:
        return {"status": "error", "table_key": table_key, "message": str(e)[:200]}
