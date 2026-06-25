import asyncio
import importlib
import sys
import types
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _reload_config(monkeypatch, token: str | None):
    if token is None:
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    else:
        monkeypatch.setenv("TUSHARE_TOKEN", token)
    sys.modules.pop("app.config", None)
    return importlib.import_module("app.config")


def test_runtime_config_status_marks_tushare_missing(monkeypatch):
    config = _reload_config(monkeypatch, None)

    status = config.get_runtime_config_status()

    assert status["tushare"]["configured"] is False
    assert status["tushare"]["env"] == "TUSHARE_TOKEN"
    assert status["tushare"]["action"] == "set TUSHARE_TOKEN before enabling market-data jobs"
    assert status["sqlite_fallback"]["enabled"] is False


def test_collect_rt_min_skips_before_opening_data_source_when_tushare_missing(monkeypatch):
    _reload_config(monkeypatch, None)
    sys.modules.pop("app.sync.rt_min", None)

    fake_etl = types.ModuleType("kronos_data.etl")

    def fail_if_called():
        raise AssertionError("_get_etl_db should not be opened when TUSHARE_TOKEN is missing")

    fake_etl._get_etl_db = fail_if_called
    monkeypatch.setitem(sys.modules, "kronos_data", types.ModuleType("kronos_data"))
    monkeypatch.setitem(sys.modules, "kronos_data.etl", fake_etl)
    rt_min = importlib.import_module("app.sync.rt_min")

    result = rt_min.collect_rt_min()

    assert result == {
        "status": "skipped",
        "reason": "TUSHARE_TOKEN not configured",
        "requires": "TUSHARE_TOKEN",
        "pg_written": 0,
        "sqlite_written": 0,
    }


def test_run_job_records_skipped_status(monkeypatch):
    scheduler = importlib.import_module("app.scheduler")
    scheduler._job_status.clear()

    def skipped_job():
        return {
            "status": "skipped",
            "reason": "TUSHARE_TOKEN not configured",
            "pg_written": 0,
        }

    asyncio.run(scheduler._run_job({"id": "rt_min", "name": "rt", "fn": skipped_job}))

    assert scheduler._job_status["rt_min"]["last_status"] == "skipped"
    assert scheduler._job_status["rt_min"]["pg_write_status"] == "skipped"
    assert scheduler._job_status["rt_min"]["pg_written"] == 0
    assert "TUSHARE_TOKEN not configured" in scheduler._job_status["rt_min"]["result"]


def test_collect_auction_snapshot_skips_before_tushare_call_when_token_missing(monkeypatch):
    _reload_config(monkeypatch, None)
    scheduler = importlib.import_module("app.scheduler")

    def fail_if_called(**_kwargs):
        raise AssertionError("sync_stk_auction_o should not run without TUSHARE_TOKEN")

    monkeypatch.setattr(scheduler, "sync_stk_auction_o", fail_if_called)

    result = scheduler.collect_auction_snapshot()

    assert result["status"] == "skipped"
    assert result["source"] == "tushare_stk_auction"
    assert result["reason"] == "TUSHARE_TOKEN not configured"


def test_readiness_reports_components_and_latest_auction(monkeypatch):
    _reload_config(monkeypatch, None)
    router = importlib.import_module("app.routers.data")

    monkeypatch.setattr(
        router,
        "get_job_status",
        lambda: {
            "scheduler_running": True,
            "jobs": [
                {
                    "id": "auction",
                    "last_run": "2026-06-25T09:25:00",
                    "last_status": "skipped",
                    "last_result": "{'reason': 'TUSHARE_TOKEN not configured'}",
                }
            ],
        },
    )
    monkeypatch.setattr(
        router,
        "_check_pg_connection",
        lambda: {"url": "localhost:6432/kronos", "ok": True},
        raising=False,
    )

    result = asyncio.run(router.readiness())

    assert result["ready"] is False
    assert result["components"]["service_alive"] is True
    assert result["components"]["scheduler_running"] is True
    assert result["components"]["pg_ok"] is True
    assert result["components"]["tushare_configured"] is False
    assert result["last_auction_status"]["last_status"] == "skipped"
    assert result["runtime_config"]["tushare"]["env"] == "TUSHARE_TOKEN"
