#!/usr/bin/env python3
"""Run incremental source refresh and 18-chain evidence decomposition.

The script only uses configured data APIs and existing local PostgreSQL tables.
If a source is unavailable, it records the error and continues; it does not
fabricate replacement evidence.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


@dataclass(frozen=True)
class PipelineStep:
    name: str
    runner: Callable[[], dict[str, Any]]


def _add_import_paths() -> None:
    os.environ.setdefault("DATA_SQLITE_FALLBACK", "false")
    paths = [
        PROJECT_ROOT / "packages" / "kronos-data",
        PROJECT_ROOT / "services" / "data-service",
        PROJECT_ROOT / "tools",
    ]
    for path in paths:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def run_callable_with_captured_output(fn: Callable[[], dict[str, Any]], tail_chars: int = 4000) -> dict[str, Any]:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        payload = fn()
    if payload is None:
        payload = {}
    stdout = stdout_buffer.getvalue()
    stderr = stderr_buffer.getvalue()
    if stdout:
        payload["stdout_tail"] = stdout[-tail_chars:]
    if stderr:
        payload["stderr_tail"] = stderr[-tail_chars:]
    return payload


def _load_evidence_pipeline():
    path = PROJECT_ROOT / "tools" / "supply_chain_evidence_pipeline.py"
    spec = importlib.util.spec_from_file_location("supply_chain_evidence_pipeline_runtime", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tushare_step(mode: str, days: int) -> Callable[[], dict[str, Any]]:
    def runner() -> dict[str, Any]:
        _add_import_paths()
        from kronos_data.etl import sync_tushare_data

        return run_callable_with_captured_output(lambda: sync_tushare_data(mode=mode, days=days))

    return runner


def _coerce_date(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text[:10], "%Y-%m-%d").date()


def expected_financial_period(today: str | date | datetime | None = None, lag_days: int = 75) -> date:
    base = _coerce_date(today) or date.today()
    cutoff = base - timedelta(days=lag_days)
    candidates = [
        date(cutoff.year, 12, 31),
        date(cutoff.year, 9, 30),
        date(cutoff.year, 6, 30),
        date(cutoff.year, 3, 31),
        date(cutoff.year - 1, 12, 31),
    ]
    return max(item for item in candidates if item <= cutoff)


def should_skip_finance_sync(latest_period: str | date | datetime | None, today: str | date | datetime | None = None) -> bool:
    latest = _coerce_date(latest_period)
    return bool(latest and latest >= expected_financial_period(today))


def _table_max_date(pg_url: str, table: str, date_col: str) -> str | None:
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT max({date_col})::text FROM {table}")
            row = cur.fetchone()
            return row[0] if row else None


def _finance_tushare_step(mode: str, days: int, pg_url: str, table: str, date_col: str = "end_date") -> Callable[[], dict[str, Any]]:
    def runner() -> dict[str, Any]:
        latest = _table_max_date(pg_url, table, date_col)
        expected = expected_financial_period()
        if should_skip_finance_sync(latest):
            return {
                "status": "skipped",
                "reason": "financial_table_current_for_reporting_lag",
                "table": table,
                "latest_period": latest,
                "expected_period": str(expected),
            }
        return _tushare_step(mode, days)()

    return runner


def _data_service_step(module_name: str, function_name: str, days: int) -> Callable[[], dict[str, Any]]:
    def runner() -> dict[str, Any]:
        _add_import_paths()
        module = __import__(f"app.sync.{module_name}", fromlist=[function_name])
        fn = getattr(module, function_name)
        return run_callable_with_captured_output(lambda: fn(days_back=days))

    return runner


def _command_step(command: list[str], env: dict[str, str] | None = None) -> Callable[[], dict[str, Any]]:
    def runner() -> dict[str, Any]:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        proc = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        payload: dict[str, Any]
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            payload = {"stdout": proc.stdout[-4000:]}
        payload["returncode"] = proc.returncode
        if proc.stderr.strip():
            payload["stderr_tail"] = proc.stderr[-4000:]
        if proc.returncode != 0:
            raise RuntimeError(json.dumps(payload, ensure_ascii=False))
        return payload

    return runner


def build_pipeline_steps(days: int, pg_url: str) -> list[PipelineStep]:
    data_days = max(1, int(days or 30))
    finance_days = max(365, data_days)
    mainbz_days = max(540, data_days)
    python = sys.executable or "python3"
    env = {"KRONOS_PG_URL": pg_url}
    return [
        PipelineStep("sync_tushare_daily_kline", _tushare_step("daily_kline", data_days)),
        PipelineStep("sync_tushare_daily_basic", _tushare_step("daily_basic", data_days)),
        PipelineStep("sync_tushare_moneyflow", _tushare_step("moneyflow", data_days)),
        PipelineStep("sync_tushare_income", _finance_tushare_step("income", finance_days, pg_url, "financial_income")),
        PipelineStep("sync_tushare_fina_indicator", _finance_tushare_step("fina_indicator", finance_days, pg_url, "financial_indicator")),
        PipelineStep("sync_tushare_forecast", _tushare_step("forecast", finance_days)),
        PipelineStep("sync_tushare_broker_recommend", _tushare_step("broker_recommend", finance_days)),
        PipelineStep("sync_tushare_research_report", _tushare_step("research_report", finance_days)),
        PipelineStep("sync_stock_profiles", _data_service_step("stock_profiles", "sync_stock_profiles", data_days)),
        PipelineStep("sync_fina_mainbz", _data_service_step("fina_mainbz", "sync_fina_mainbz", mainbz_days)),
        PipelineStep("sync_announcements", _data_service_step("announcements", "sync_announcements", data_days)),
        PipelineStep("sync_interact_qa", _data_service_step("interact", "sync_interact_qa", data_days)),
        PipelineStep("seed_evidence_source_catalog", lambda: _load_evidence_pipeline().seed_source_catalog(pg_url)),
        PipelineStep(
            "backfill_all_business_tag_mappings",
            _command_step([python, "tools/backfill_ai_compute_all_mapped.py"], env=env),
        ),
        PipelineStep(
            "backfill_existing_evidence_events",
            lambda: _load_evidence_pipeline().backfill_existing_events(pg_url=pg_url, run_prefix=None, limit=50000),
        ),
        PipelineStep(
            "refresh_stage_transitions",
            lambda: _load_evidence_pipeline().refresh_stage_transitions(pg_url=pg_url, run_prefix=None, limit=50000),
        ),
        PipelineStep(
            "refresh_expectation_monitor",
            lambda: _load_evidence_pipeline().refresh_expectation_monitor(pg_url=pg_url, run_prefix=None, limit=50000),
        ),
    ]


def run_steps(steps: list[PipelineStep]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for step in steps:
        started = time.time()
        try:
            payload = step.runner()
            status = payload.get("status") or ("error" if payload.get("returncode", 0) else "ok")
            results.append({
                "name": step.name,
                "status": status,
                "elapsed": round(time.time() - started, 2),
                "result": payload,
            })
        except Exception as exc:
            results.append({
                "name": step.name,
                "status": "error",
                "elapsed": round(time.time() - started, 2),
                "error": str(exc)[:4000],
            })
    return results


def collect_db_stats(pg_url: str) -> dict[str, Any]:
    queries = {
        "mapping_count": "SELECT count(*) FROM business_tag_mapping",
        "chain_count": "SELECT count(DISTINCT chain_id) FROM business_tag_mapping",
        "raw_docs": "SELECT count(*) FROM raw_evidence_documents",
        "facts": "SELECT count(*) FROM evidence_extracted_facts",
        "legacy_events": "SELECT count(*) FROM business_tag_evidence_events",
        "freshness": "SELECT count(*) FROM business_tag_evidence_freshness",
        "l8_status": "SELECT count(*) FROM business_tag_l8_evidence_status",
        "stage_rows": "SELECT count(*) FROM business_tag_stage_tracking",
        "score_rows": "SELECT count(*) FROM business_tag_three_high_scores",
        "gap_rows": "SELECT count(*) FROM business_tag_expectation_gap_scores",
    }
    stats: dict[str, Any] = {}
    with psycopg2.connect(pg_url) as conn:
        with conn.cursor() as cur:
            for key, sql in queries.items():
                cur.execute(sql)
                stats[key] = int(cur.fetchone()[0] or 0)
            cur.execute(
                """
                SELECT chain_id, count(*) AS mappings
                FROM business_tag_mapping
                GROUP BY chain_id
                ORDER BY chain_id
                """
            )
            stats["chains"] = [{"chain_id": row[0], "mappings": int(row[1] or 0)} for row in cur.fetchall()]
            cur.execute(
                """
                SELECT freshness_status, count(*)
                FROM business_tag_evidence_freshness
                GROUP BY freshness_status
                ORDER BY freshness_status
                """
            )
            stats["freshness_distribution"] = {str(row[0]): int(row[1] or 0) for row in cur.fetchall()}
    return stats


def build_acceptance_summary(stats: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "chain_count": {"actual": stats.get("chain_count", 0), "expected_min": 18},
        "mapping_count": {"actual": stats.get("mapping_count", 0), "expected_min": 1},
        "raw_docs": {"actual": stats.get("raw_docs", 0), "expected_min": 1},
        "facts": {"actual": stats.get("facts", 0), "expected_min": 1},
        "l8_status": {"actual": stats.get("l8_status", 0), "expected_min": 1},
        "score_rows": {"actual": stats.get("score_rows", 0), "expected_min": 1},
    }
    for item in checks.values():
        item["pass"] = int(item["actual"] or 0) >= int(item["expected_min"])
    return {"accepted": all(item["pass"] for item in checks.values()), "checks": checks}


def write_report(output_dir: Path, run_id: str, results: list[dict[str, Any]], stats: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "run_id": run_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "steps": results,
        "db_stats": stats,
        "acceptance": build_acceptance_summary(stats),
    }
    path = output_dir / f"{run_id}_acceptance_report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 18-chain incremental refresh and acceptance")
    parser.add_argument("--pg-url", default=DEFAULT_PG_URL)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "eighteen_chains_incremental_refresh_20260703"))
    parser.add_argument("--skip-source-sync", action="store_true", help="Only run decomposition and acceptance from local DB")
    args = parser.parse_args()

    run_id = f"18chains-incremental-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    steps = build_pipeline_steps(days=args.days, pg_url=args.pg_url)
    if args.skip_source_sync:
        steps = [step for step in steps if not step.name.startswith("sync_")]
    results = run_steps(steps)
    stats = collect_db_stats(args.pg_url)
    report_path = write_report(Path(args.output_dir), run_id, results, stats)
    payload = {
        "run_id": run_id,
        "report_path": str(report_path),
        "accepted": build_acceptance_summary(stats)["accepted"],
        "db_stats": stats,
        "step_status": {item["name"]: item["status"] for item in results},
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
