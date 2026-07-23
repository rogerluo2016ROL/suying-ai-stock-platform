"""Fail-closed client for model-specific data readiness."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _service_auth_headers() -> dict:
    """X-Service-Auth 服务间豁免头（kronos-auth 契约）；未配置 secret 时不发头。"""
    secret = os.environ.get("KRONOS_SERVICE_SECRET", "")
    return {"X-Service-Auth": secret} if secret else {}


def require_ready(profile: str, target_trade_date: str | None = None) -> dict:
    if os.environ.get("KRONOS_ENV", "development").lower() not in {"production", "official"}:
        return {"status": "bypass", "ready": True}
    base = os.environ.get("DATA_SERVICE_URL", "http://data-service:8010")
    query = {"profile": profile}
    if target_trade_date:
        query["target_trade_date"] = target_trade_date
    req = Request(
        f"{base}/api/v1/data/readiness/evaluate?{urlencode(query)}",
        headers=_service_auth_headers(),
    )
    with urlopen(req, timeout=5) as response:
        payload = json.loads(response.read())
    if payload.get("status") not in {"ready", "pass"}:
        raise RuntimeError(f"DATA_NOT_READY: {payload.get('status', 'unknown')}")
    return payload
