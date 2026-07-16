import json
import sys
from datetime import datetime

import pytest

from app import scheduled_research as scheduled


def test_config_keeps_four_trading_tasks_and_registers_three_embodied_tasks():
    config = scheduled.load_scheduled_research_config()

    assert [
        (item["id"], item["cron"], item["model"], item.get("time_slot"))
        for item in config["tasks"][:4]
    ] == [
        ("cb_auction_t0_0925", "25 9 * * 1-5", "cb_auction_t0", None),
        ("bi_shifu_trend_0930", "30 9 * * 1-5", "bi_shifu_trend", None),
        ("qishen_afternoon_1400", "0 14 * * 1-5", "qishen_afternoon", "14:00"),
        ("qishen_afternoon_1430", "30 14 * * 1-5", "qishen_afternoon", "14:30"),
    ]
    assert [
        (item["id"], item["cron"], item["model"])
        for item in config["tasks"][4:]
    ] == [
        ("embodied_daily_refresh_1930", "30 19 * * *", "embodied_daily_refresh"),
        ("embodied_weekly_audit_2030", "30 20 * * 0", "embodied_weekly_audit"),
        ("embodied_delivery_retry_5m", "*/5 * * * *", "embodied_delivery_retry"),
    ]
    assert len(config["chat_targets"]) == 3


def test_non_trading_day_skips_without_executor(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_args: False)
    called = []

    result = scheduled.run_scheduled_research_task(
        "bi_shifu_trend_0930",
        now=datetime(2026, 7, 18, 9, 30),
        executor=lambda cmd: called.append(cmd),
        state_root=tmp_path,
    )

    assert result["status"] == "skipped_non_trading_day"
    assert called == []


def test_all_days_task_bypasses_trade_calendar_and_uses_embodied_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_: pytest.fail("calendar queried"))
    commands = []

    result = scheduled.run_scheduled_research_task(
        "embodied_daily_refresh_1930",
        now=datetime(2026, 7, 18, 19, 30),
        executor=lambda command: commands.append(command) or {"status": "success"},
        state_root=tmp_path,
    )

    assert result["status"] == "success"
    assert commands[0][1].endswith("tools/run_embodied_daily_refresh.py")
    assert commands[0][commands[0].index("--mode") + 1] == "apply"


def test_retry_schedule_routes_to_retry_delivery_mode():
    config = scheduled.load_scheduled_research_config()
    task = next(item for item in config["tasks"] if item["id"] == "embodied_delivery_retry_5m")

    command = scheduled.build_pipeline_command(task, "2026-07-16", ["oc_a"])

    assert command[command.index("--mode") + 1] == "retry-delivery"


def test_retry_task_is_not_suppressed_by_a_previous_same_day_run(tmp_path):
    state = tmp_path / "2026-07-16" / "embodied_delivery_retry_5m.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "success"}), encoding="utf-8")
    calls = []

    result = scheduled.run_scheduled_research_task(
        "embodied_delivery_retry_5m",
        now=datetime(2026, 7, 16, 20, 5),
        executor=lambda command: calls.append(command) or {"status": "success"},
        state_root=tmp_path,
    )

    assert result["status"] == "success"
    assert len(calls) == 1


def test_trade_calendar_failure_is_not_guessed_as_open_day(monkeypatch, tmp_path):
    def fail(*_args):
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(scheduled, "is_open_trading_day", fail)
    result = scheduled.run_scheduled_research_task(
        "bi_shifu_trend_0930",
        now=datetime(2026, 7, 14, 9, 30),
        executor=lambda _cmd: None,
        state_root=tmp_path,
    )

    assert result["status"] == "failed_trade_calendar"


def test_auction_command_enables_primary_and_eastmoney_fallback():
    task = {
        "model": "cb_auction_t0",
        "trigger_auction": True,
        "eastmoney_fallback": True,
    }
    cmd = scheduled.build_pipeline_command(task, "2026-07-14", ["oc_a", "oc_b", "oc_c"])

    assert "--trigger-auction" in cmd
    assert "--eastmoney-fallback" in cmd
    assert cmd.count("--chat-id") == 3
    assert cmd[0] == sys.executable


def test_afternoon_command_pins_time_slot():
    cmd = scheduled.build_pipeline_command(
        {"model": "qishen_afternoon", "time_slot": "14:00"},
        "2026-07-14",
        ["oc_a"],
    )

    assert cmd[cmd.index("--time-slot") + 1] == "14:00"


def test_bi_shifu_command_pins_0930_market_snapshot():
    config = scheduled.load_scheduled_research_config()
    task = next(item for item in config["tasks"] if item["id"] == "bi_shifu_trend_0930")

    cmd = scheduled.build_pipeline_command(task, "2026-07-14", ["oc_a"])

    assert cmd[cmd.index("--model") + 1] == "bi_shifu_trend"
    assert cmd[cmd.index("--time-slot") + 1] == "09:30"


def test_completed_task_is_idempotent(monkeypatch, tmp_path):
    state_path = tmp_path / "2026-07-14" / "bi_shifu_trend_0930.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({"status": "success"}), encoding="utf-8")
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_args: True)
    called = []

    result = scheduled.run_scheduled_research_task(
        "bi_shifu_trend_0930",
        now=datetime(2026, 7, 14, 9, 30),
        executor=lambda cmd: called.append(cmd),
        state_root=tmp_path,
    )

    assert result["status"] == "skipped_duplicate"
    assert called == []
