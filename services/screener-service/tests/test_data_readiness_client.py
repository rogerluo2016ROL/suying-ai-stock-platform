import asyncio

from app import data_readiness_client


def test_screening_blocks_when_data_service_reports_stale(monkeypatch):
    async def blocked(*_args, **_kwargs):
        return {"status": "blocked", "sources": [{"source": "daily_kline", "status": "stale"}]}
    monkeypatch.setattr(data_readiness_client, "fetch_readiness", blocked)
    result = asyncio.run(data_readiness_client.require_ready("daily_screening_v1", "2026-07-10"))
    assert result["result_status"] == "blocked"
    assert result["fallback_reason"] == "required data is stale or incomplete"
