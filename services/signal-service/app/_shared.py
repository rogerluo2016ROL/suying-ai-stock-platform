"""Shared routers, store, cross-service HTTP helpers and signal contract helpers.

拆分自原 app/routes.py：这里只放被多个路由域复用的装配对象与纯函数，
路由实现见 app/routers/{dashboard,analysis,data}.py。
"""

import os, logging, asyncio
from datetime import datetime, timezone
from fastapi import APIRouter
from app.signal_store import get_store

logger = logging.getLogger("signal-service.routes")

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])
dashboard_router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])
data_router = APIRouter(prefix="/api/v1/data", tags=["data"])
store = get_store()


def _service_url(env_key: str, container: str, port: int, path: str = "") -> str:
    """跨服务 URL: env 优先, Docker 内用容器名, 否则 localhost."""
    if os.environ.get(env_key):
        return os.environ[env_key].rstrip("/")
    if os.path.exists("/.dockerenv"):
        return f"http://{container}:{port}{path}"
    return f"http://localhost:{port}{path}"


def _service_auth_headers() -> dict:
    """X-Service-Auth header for internal service-to-service calls.

    未配置 KRONOS_SERVICE_SECRET 时不发头（本地 dev 行为不变）。
    """
    secret = os.environ.get("KRONOS_SERVICE_SECRET", "")
    return {"X-Service-Auth": secret} if secret else {}


async def _http_post_json(url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    """async 包装同步 urllib POST, 避免阻塞事件循环 (P0-1)."""
    import json as _json
    import urllib.request

    def _call() -> dict:
        data = _json.dumps(payload).encode() if payload else None
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json", **_service_auth_headers()}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _json.loads(resp.read())

    return await asyncio.to_thread(_call)


DIAGNOSIS_ANALYZE_URL = _service_url(
    "DIAGNOSIS_SERVICE_URL", "diagnosis-service", 8009, "/api/v1/diagnosis/analyze"
)
SCREENER_RUN_URL = _service_url(
    "SCREENER_SERVICE_URL", "screener-service", 8001, "/api/v1/screener/run"
)


def _signal_model_metadata(mode: str) -> dict:
    return {
        "name": "signal-six-dimension-v2",
        "version": "signal-v2.0",
        "provider": "signal-service",
        "inference_mode": mode,
    }


_SIGNAL_DIMENSION_WEIGHTS = {
    "kronos": 0.20, "technical": 0.20, "money_flow": 0.12,
    "fundamental": 0.15, "event_risk": 0.13, "market": 0.20,
}


def _combine_signal_dimensions(dimensions: dict) -> dict:
    """Combine only observed dimensions; never turn missing data into 50."""
    normalized = {name: dimensions.get(name) for name in _SIGNAL_DIMENSION_WEIGHTS}
    unavailable = [name for name, value in normalized.items() if value is None]
    available_weight = sum(_SIGNAL_DIMENSION_WEIGHTS[name] for name, value in normalized.items() if value is not None)
    score = None if not available_weight else round(sum(float(normalized[name]) * _SIGNAL_DIMENSION_WEIGHTS[name] for name in normalized if normalized[name] is not None) / available_weight, 1)
    return {
        "dimensions": normalized,
        "coverage": round(available_weight, 3),
        "unavailable_dimensions": unavailable,
        "result_status": "insufficient_data" if unavailable else "ok",
        "score": score,
    }


def _coerce_iso_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date().isoformat()
    text = str(value)
    if not text:
        return None
    return text[:10]


def _signal_data_freshness(data=None, source: str = "daily_kline") -> dict:
    as_of = None
    try:
        if isinstance(data, dict):
            as_of = _coerce_iso_date(data.get("trade_date") or data.get("as_of") or data.get("date"))
        elif data is not None and len(data) > 0:
            if hasattr(data, "columns") and "trade_date" in data.columns:
                as_of = _coerce_iso_date(data["trade_date"].iloc[-1])
            elif hasattr(data, "index") and len(data.index) > 0:
                as_of = _coerce_iso_date(data.index[-1])
            elif isinstance(data, (list, tuple)) and isinstance(data[-1], dict):
                as_of = _coerce_iso_date(data[-1].get("trade_date") or data[-1].get("as_of") or data[-1].get("date"))
    except Exception:
        as_of = None

    if not as_of:
        return {
            "status": "unknown",
            "as_of": None,
            "source": source,
            "quality_score": 0,
        }

    try:
        as_date = datetime.fromisoformat(as_of).date()
        lag_days = max(0, (datetime.now(timezone.utc).date() - as_date).days)
    except Exception:
        lag_days = 999

    if lag_days <= 10:
        status, quality_score = "fresh", 96
    elif lag_days <= 30:
        status, quality_score = "stale", 72
    else:
        status, quality_score = "outdated", 35
    return {
        "status": status,
        "as_of": as_of,
        "source": source,
        "quality_score": quality_score,
    }


def _with_signal_contract(
    payload: dict,
    *,
    mode: str,
    data=None,
    fallback_reason: str | None = None,
    source: str = "daily_kline",
) -> dict:
    enriched = dict(payload)
    enriched["model_metadata"] = _signal_model_metadata(mode)
    enriched["data_freshness"] = _signal_data_freshness(data, source)
    enriched["fallback_reason"] = fallback_reason
    return enriched


def _dashboard_row_change_pct(row: dict) -> float:
    value = row.get("change_pct")
    if value is None:
        value = row.get("pct_chg")
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
