from unittest.mock import AsyncMock
import types
import sys
import pytest
import asyncio

from app import factor_calibration as calibration
sys.modules.setdefault("croniter", types.SimpleNamespace(croniter=lambda *a, **k: None))
from app import scheduler


def test_no_observed_evidence_does_not_apply(monkeypatch):
    spy = AsyncMock()
    monkeypatch.setattr(calibration, "_apply_calibration", spy)
    result = asyncio.run(calibration.run_calibration(apply=True))
    assert result["status"] == "insufficient_data"
    assert result["missing_requirements"] == ["saved_evaluation_id"]
    spy.assert_not_awaited()


def test_saved_ready_evaluation_can_calibrate(monkeypatch):
    evidence = {"status": "ready", "window_start": "2026-01-01", "window_end": "2026-06-30",
                "factors": [{"factor_name": "quality", "factor_label": "quality", "ic": .1,
                             "icir": 1.0, "old_weight": 4.0, "new_weight": 1.0,
                             "direction": "long", "significance": "marginal"}]}
    compute = AsyncMock(return_value=evidence)
    monkeypatch.setattr(calibration, "compute_ic_from_db", compute)
    monkeypatch.setattr(calibration, "_save_calibration_history", AsyncMock())
    result = asyncio.run(calibration.run_calibration(evaluation_id="FE-1"))
    assert result["status"] == "ready"
    assert result["evaluation_id"] == "FE-1"
    compute.assert_awaited_once_with("FE-1", 90, 30)


def test_scheduler_skips_apply_when_evidence_is_insufficient(monkeypatch):
    run = AsyncMock(return_value={"status": "insufficient_data"})
    monkeypatch.setattr("app.factor_calibration.run_calibration", run)
    monkeypatch.setattr("app.factor_calibration.latest_ready_evaluation_id", AsyncMock(return_value=None))
    asyncio.run(scheduler._scheduled_calibration())
    run.assert_awaited_once()
