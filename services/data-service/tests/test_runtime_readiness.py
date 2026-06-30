import asyncio
import importlib
import sys
import types
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _reload_config(monkeypatch, token: str | None):
    monkeypatch.delenv("TUSHARE_TOKEN_FILE", raising=False)
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
    assert status["tushare"]["env"] == "TUSHARE_TOKEN_FILE or TUSHARE_TOKEN"
    assert status["tushare"]["action"] == "set TUSHARE_TOKEN_FILE or TUSHARE_TOKEN before enabling market-data jobs"
    assert status["sqlite_fallback"]["enabled"] is False


def test_runtime_config_status_accepts_tushare_token_file(monkeypatch, tmp_path):
    token_file = tmp_path / "tushare_token"
    token_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setenv("TUSHARE_TOKEN_FILE", str(token_file))
    sys.modules.pop("app.config", None)

    config = importlib.import_module("app.config")
    status = config.get_runtime_config_status()

    assert config.TUSHARE_TOKEN == "file-token"
    assert status["tushare"]["configured"] is True
    assert status["tushare"]["source"] == "file"


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
    assert result["runtime_config"]["tushare"]["env"] == "TUSHARE_TOKEN_FILE or TUSHARE_TOKEN"


def test_trigger_table_backfill_runs_registered_handler(monkeypatch):
    router = importlib.import_module("app.routers.data")
    monkeypatch.setenv("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    router._job_status.clear()

    def fake_backfill(days_back: int):
        return {"status": "ok", "table": "top_list", "written": days_back + 2}

    monkeypatch.setitem(router._BACKFILL_MAP, "top_list", fake_backfill)

    result = asyncio.run(router.trigger_table_backfill("top_list", 5))

    assert result["status"] == "ok"
    assert result["table_key"] == "top_list"
    assert result["written"] == 7
    assert result["pg_written"] == 7
    assert router._job_status["manual_backfill:top_list"]["last_status"] == "ok"


def test_trigger_table_backfill_marks_idempotent_latest_kline_ok(monkeypatch):
    router = importlib.import_module("app.routers.data")
    monkeypatch.setenv("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    router._job_status.clear()

    def fake_backfill(days_back: int):
        return {"status": "ok", "table": "daily_kline", "fetched": 5510, "written": 0}

    monkeypatch.setitem(router._BACKFILL_MAP, "daily_kline", fake_backfill)
    monkeypatch.setattr(
        router,
        "_sync_required_dependencies",
        lambda table_key: {"dependency": "stocks", "pg_written": 0},
    )
    monkeypatch.setattr(router, "_has_latest_completed_trade_day", lambda table_key: True)

    result = asyncio.run(router.trigger_table_backfill("daily_kline", 1))

    assert result["status"] == "ok"
    assert result["pg_write_status"] == "ok"
    assert result["written"] == 0
    assert result["noop_reason"] == "already_up_to_date"
