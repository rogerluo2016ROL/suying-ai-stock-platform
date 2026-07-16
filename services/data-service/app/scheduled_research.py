"""交易日模型定时任务编排。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = ROOT / "configs" / "scheduled_research.json"
DEFAULT_STATE_ROOT = ROOT / "outputs" / "scheduled_research"
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
TERMINAL_STATUSES = {
    "success",
    "partial_delivery",
    "failed_delivery",
    "data_success_delivery_incomplete",
    "skipped_non_trading_day",
}


def load_scheduled_research_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    return json.loads(config_path.read_text(encoding="utf-8"))


def is_open_trading_day(trade_date: str, pg_url: str) -> bool:
    import psycopg2

    with psycopg2.connect(pg_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_open FROM trade_cal WHERE cal_date = %s::date LIMIT 1",
                (trade_date,),
            )
            row = cursor.fetchone()
    if row is None:
        raise RuntimeError("交易日历缺少目标日期")
    return bool(row[0])


def build_pipeline_command(
    task: dict[str, Any],
    trade_date: str,
    chat_ids: list[str],
) -> list[str]:
    if task.get("runner") == "embodied_refresh":
        command = [
            sys.executable,
            str(ROOT / "tools" / "run_embodied_daily_refresh.py"),
            "--mode", str(task["mode"]),
            "--as-of-date", trade_date,
        ]
        if task.get("send_feishu"):
            command.append("--send-feishu")
        return command
    command = [
        sys.executable,
        str(ROOT / "tools" / "run_research_pipeline.py"),
        "--model",
        str(task["model"]),
        "--date",
        trade_date,
        "--sync-doc",
        "--send-feishu",
    ]
    time_slot = task.get("time_slot") or task.get("market_time_slot")
    if time_slot:
        command.extend(["--time-slot", str(time_slot)])
    if task.get("trigger_auction"):
        command.append("--trigger-auction")
    if task.get("eastmoney_fallback"):
        command.append("--eastmoney-fallback")
    for chat_id in chat_ids:
        command.extend(["--chat-id", chat_id])
    return command


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _default_executor(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=1800,
        check=False,
    )


def _pipeline_summary(execution: Any) -> dict[str, Any]:
    if isinstance(execution, dict):
        return execution
    stdout = str(getattr(execution, "stdout", "") or "").strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        start = stdout.rfind("\n{")
        return json.loads(stdout[start + 1 :]) if start >= 0 else {}


def _load_run_result(summary: dict[str, Any]) -> dict[str, Any]:
    run_dir = summary.get("run_dir")
    if not run_dir:
        return {}
    path = Path(str(run_dir)) / "result.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def run_scheduled_research_task(
    task_id: str,
    *,
    now: datetime | None = None,
    executor: Callable[[list[str]], Any] | None = None,
    state_root: str | Path = DEFAULT_STATE_ROOT,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    started = now or datetime.now()
    trade_date = started.date().isoformat()
    config = load_scheduled_research_config(config_path)
    task = next((item for item in config["tasks"] if item["id"] == task_id), None)
    if task is None:
        raise ValueError(f"未知定时研究任务: {task_id}")

    state_path = Path(state_root) / trade_date / f"{task_id}.json"
    if state_path.exists() and not task.get("repeatable", False):
        previous = json.loads(state_path.read_text(encoding="utf-8"))
        if previous.get("status") in TERMINAL_STATUSES:
            return {**previous, "status": "skipped_duplicate"}

    base_state = {
        "task_id": task_id,
        "model": task["model"],
        "trade_date": trade_date,
        "planned_time": task.get("time_slot") or task.get("market_time_slot") or task["cron"],
        "started_at": started.isoformat(timespec="seconds"),
    }
    pg_url = os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL)
    if task.get("calendar_scope", "trading_days") == "trading_days":
        try:
            open_day = is_open_trading_day(trade_date, pg_url)
        except Exception as exc:
            state = {
                **base_state,
                "status": "failed_trade_calendar",
                "error": f"{type(exc).__name__}: 交易日历查询失败",
            }
            _write_state(state_path, state)
            return state
        if not open_day:
            state = {**base_state, "status": "skipped_non_trading_day"}
            _write_state(state_path, state)
            return state

    targets = config.get("chat_targets") or []
    chat_ids = [str(item.get("chat_id")) for item in targets if item.get("chat_id")]
    command = build_pipeline_command(task, trade_date, chat_ids)
    run = executor or _default_executor
    try:
        execution = run(command)
    except Exception as exc:
        state = {
            **base_state,
            "status": "failed",
            "error": f"{type(exc).__name__}: 流水线执行失败",
        }
        _write_state(state_path, state)
        return state

    return_code = int(getattr(execution, "returncode", 0) or 0)
    summary = _pipeline_summary(execution)
    if task.get("runner") == "embodied_refresh":
        status = summary.get("status") or ("success" if return_code == 0 else "failed")
        state = {
            **base_state,
            "status": status,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "run_id": summary.get("run_id"),
            "delivery_summary": summary.get("delivery_summary"),
        }
        if return_code != 0:
            state["error"] = "具身智能刷新 CLI 返回非零状态"
        _write_state(state_path, state)
        return state
    run_result = _load_run_result(summary)
    delivery = (run_result.get("pipeline") or {}).get("feishu_delivery") or {}
    status = delivery.get("status") or ("success" if return_code == 0 else "failed")
    state = {
        **base_state,
        "status": status,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": summary.get("run_dir"),
        "report_path": summary.get("report_path"),
        "market_snapshot_time": (run_result.get("market_strength") or {}).get("snapshot_time"),
        "data_source": ((run_result.get("pipeline") or {}).get("data_source")),
        "feishu_deliveries": delivery.get("deliveries") or [],
    }
    if return_code != 0:
        state["error"] = "统一研究流水线返回非零状态"
    _write_state(state_path, state)
    return state


def build_scheduled_research_jobs() -> list[dict[str, Any]]:
    config = load_scheduled_research_config()
    jobs = []
    for task in config["tasks"]:
        task_id = str(task["id"])
        jobs.append(
            {
                "id": task_id,
                "name": f"[研究]{task['name']}",
                "cron": task["cron"],
                "fn": lambda task_id=task_id: run_scheduled_research_task(task_id),
            }
        )
    return jobs
