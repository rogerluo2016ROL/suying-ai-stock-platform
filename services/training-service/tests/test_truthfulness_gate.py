from unittest.mock import AsyncMock
import types
import sys
import pytest
import asyncio

from app import factor_calibration as calibration
sys.modules.setdefault("croniter", types.SimpleNamespace(croniter=lambda *a, **k: None))
from app import scheduler


def test_no_observed_evidence_does_not_apply(monkeypatch):
    monkeypatch.setattr(calibration, "compute_ic_from_db", AsyncMock(return_value={"factors": [], "window_start": "2026-04-01", "window_end": "2026-07-10"}))
    spy = AsyncMock()
    monkeypatch.setattr(calibration, "_apply_calibration", spy)
    result = asyncio.run(calibration.run_calibration(apply=True))
    assert result["status"] == "insufficient_data"
    spy.assert_not_awaited()


def test_scheduler_skips_apply_when_evidence_is_insufficient(monkeypatch):
    run = AsyncMock(return_value={"status": "insufficient_data"})
    monkeypatch.setattr("app.factor_calibration.run_calibration", run)
    asyncio.run(scheduler._scheduled_calibration())
    run.assert_awaited_once()
