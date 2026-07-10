"""Data-service readiness gate used before training execution."""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlencode
from urllib.request import urlopen

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://data-service:8010")

async def fetch(profile: str, trade_date: str) -> dict:
    url = f"{DATA_SERVICE_URL}/api/v1/data/readiness?{urlencode({'profile': profile, 'trade_date': trade_date})}"
    def request():
        with urlopen(url, timeout=3) as response:
            return json.loads(response.read().decode())
    return await asyncio.get_running_loop().run_in_executor(None, request)

async def require(profile: str, trade_date: str) -> dict:
    try:
        snapshot = await fetch(profile, trade_date)
    except Exception:
        return {"status": "blocked", "reason": "data readiness service is unavailable"}
    if snapshot.get("status") != "ready":
        return {"status": "blocked", "reason": "required data is stale or incomplete", "snapshot": snapshot}
    return {"status": "ready", "snapshot": snapshot}
