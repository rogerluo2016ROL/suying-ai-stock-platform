import json
import sys
from datetime import datetime

from app import scheduled_research as scheduled


def test_config_registers_four_requested_tasks():
    config = scheduled.load_scheduled_research_config()

    assert [
        (item["id"], item["cron"], item["model"], item.get("time_slot"))
        for item in config["tasks"]
    ] == [
        ("cb_auction_t0_0925", "25 9 * * 1-5", "cb_auction_t0", None),
        ("bi_shifu_trend_0930", "30 9 * * 1-5", "bi_shifu_trend", None),
        ("qishen_afternoon_1400", "0 14 * * 1-5", "qishen_afternoon", "14:00"),
        ("qishen_afternoon_1430", "30 14 * * 1-5", "qishen_afternoon", "14:30"),
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
