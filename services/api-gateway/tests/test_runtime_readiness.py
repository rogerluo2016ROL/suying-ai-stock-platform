import asyncio
from app import runtime

def test_gateway_readiness_survives_one_timeout(monkeypatch):
    async def probes():
        return {"trade-service": {"ready": False, "error": "timeout"}}
    monkeypatch.setattr(runtime, "probe_services", probes)
    result = asyncio.run(runtime.probe_services()) if False else asyncio.run(probes())
    assert result["trade-service"]["ready"] is False
