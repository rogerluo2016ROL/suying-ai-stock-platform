import asyncio

from app import data_readiness


def test_training_readiness_blocks_unavailable_service(monkeypatch):
    async def unavailable(*_args, **_kwargs):
        raise OSError("down")
    monkeypatch.setattr(data_readiness, "fetch", unavailable)
    result = asyncio.run(data_readiness.require("training_v1", "2026-07-10"))
    assert result["status"] == "blocked"
    assert result["reason"] == "data readiness service is unavailable"
