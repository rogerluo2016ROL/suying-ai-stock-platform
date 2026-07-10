"""Fail-closed readiness client for screening runs."""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://data-service:8010")


async def fetch_readiness(profile: str, trade_date: str | None) -> dict:
    params = {"profile": profile}
    if trade_date:
        params["trade_date"] = trade_date
    url = f"{DATA_SERVICE_URL}/api/v1/data/readiness?{urlencode(params)}"
    def request() -> dict:
        with urlopen(url, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    return await asyncio.get_running_loop().run_in_executor(None, request)


async def require_ready(profile: str, trade_date: str | None) -> dict | None:
    try:
        snapshot = await fetch_readiness(profile, trade_date)
    except Exception as exc:
        return {
            "result_status": "blocked",
            "fallback_reason": "data readiness service is unavailable",
            "data_readiness": {"status": "unavailable", "reason": str(exc)},
        }
    if snapshot.get("status") != "ready":
        return {
            "result_status": "blocked",
            "fallback_reason": "required data is stale or incomplete",
            "data_readiness": snapshot,
        }
    return None
