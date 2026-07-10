"""Fail-closed client for model-specific data readiness."""
import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen


def require_ready(profile: str, target_trade_date: str | None = None) -> dict:
    if os.environ.get("KRONOS_ENV", "development").lower() not in {"production", "official"}:
        return {"status": "bypass", "ready": True}
    base = os.environ.get("DATA_SERVICE_URL", "http://data-service:8010")
    query = {"profile": profile}
    if target_trade_date:
        query["target_trade_date"] = target_trade_date
    with urlopen(f"{base}/api/v1/data/readiness/evaluate?{urlencode(query)}", timeout=5) as response:
        payload = json.loads(response.read())
    if payload.get("status") not in {"ready", "pass"}:
        raise RuntimeError(f"DATA_NOT_READY: {payload.get('status', 'unknown')}")
    return payload
