import json
import subprocess
import sys
from datetime import datetime

from app import scheduled_research as scheduled


def test_config_registers_requested_tasks():
    config = scheduled.load_scheduled_research_config()

    assert [
        (item["id"], item["cron"], item["model"], item.get("time_slot"))
        for item in config["tasks"]
    ] == [
        ("cb_auction_t0_0925", "25 9 * * 1-5", "cb_auction_t0", None),
        ("bi_shifu_trend_0930", "30 9 * * 1-5", "bi_shifu_trend", None),
        ("qishen_afternoon_1400", "0 14 * * 1-5", "qishen_afternoon", "14:00"),
        ("qishen_afternoon_1430", "30 14 * * 1-5", "qishen_afternoon", "14:30"),
        ("us_morning_brief_0800", "0 8 * * 1-5", "us_morning_brief", None),
        ("kr_morning_brief_0905", "5 9 * * 1-5", "kr_morning_brief", None),
    ]
    assert len(config["chat_targets"]) == 3
    # 海外市场早报不受 A 股交易日历限制
    brief_flags = {item["id"]: item.get("skip_trade_cal_check")
                   for item in config["tasks"]}
    assert brief_flags["us_morning_brief_0800"] is True
    assert brief_flags["kr_morning_brief_0905"] is True


def test_skip_trade_cal_check_bypasses_calendar(monkeypatch, tmp_path):
    """skip_trade_cal_check=true 的任务在 A 股休市日照常执行 (海外市场照常交易)."""
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_args: False)
    called = []

    result = scheduled.run_scheduled_research_task(
        "us_morning_brief_0800",
        now=datetime(2026, 10, 2, 8, 0),  # 国庆假期 (A 股休市)
        executor=lambda cmd: called.append(cmd),
        state_root=tmp_path,
    )

    assert called, "executor 应被调用 (不查交易日历)"
    assert result["status"] != "skipped_non_trading_day"


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


def test_failed_pipeline_preserves_subprocess_error(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduled, "is_open_trading_day", lambda *_args: True)

    result = scheduled.run_scheduled_research_task(
        "qishen_afternoon_1400",
        now=datetime(2026, 7, 14, 14, 0),
        executor=lambda _cmd: subprocess.CompletedProcess(
            args=[], returncode=2, stdout="partial output", stderr="lark doc denied"
        ),
        state_root=tmp_path,
    )

    assert result["return_code"] == 2
    assert result["stderr_tail"] == "lark doc denied"
    assert result["stdout_tail"] == "partial output"


def test_startup_catchup_only_runs_tasks_inside_their_grace_window(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(
        scheduled,
        "run_scheduled_research_task",
        lambda task_id, **kwargs: called.append(task_id) or {"task_id": task_id, "status": "success"},
    )

    results = scheduled.run_missed_scheduled_research_tasks(
        now=datetime(2026, 7, 14, 9, 35),
        state_root=tmp_path,
    )

    # bi_shifu (9:30+20min) 与 kr_morning_brief (9:05+30min) 均在宽限窗口内
    assert called == ["bi_shifu_trend_0930", "kr_morning_brief_0905"]
    assert results[0]["status"] == "success"


def test_startup_catchup_never_runs_auction_after_0929(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(
        scheduled,
        "run_scheduled_research_task",
        lambda task_id, **kwargs: called.append(task_id) or {"task_id": task_id},
    )

    scheduled.run_missed_scheduled_research_tasks(
        now=datetime(2026, 7, 14, 9, 30),
        state_root=tmp_path,
    )

    assert "cb_auction_t0_0925" not in called
