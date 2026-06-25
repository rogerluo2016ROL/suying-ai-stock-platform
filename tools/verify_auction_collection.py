#!/usr/bin/env python3
"""Verify data-service auction collection after the 09:25 window."""

from __future__ import annotations

import argparse
import ast
import json
import sys
import urllib.request
from datetime import date
from typing import Any


def _parse_last_result(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        return {"raw": str(value)}
    return parsed if isinstance(parsed, dict) else {"raw": str(value)}


def _find_job(status: dict, job_id: str) -> dict:
    for job in status.get("jobs", []):
        if job.get("id") == job_id:
            return job
    return {"id": job_id, "last_status": "missing", "last_run": None, "last_result": ""}


def evaluate_auction_status(readiness: dict, status: dict, target_date: str) -> dict:
    components = readiness.get("components", {})
    if not components.get("service_alive"):
        return {"ok": False, "exit_code": 2, "blocker": "data-service is not alive"}
    if not components.get("scheduler_running"):
        return {"ok": False, "exit_code": 2, "blocker": "scheduler is not running"}
    if not components.get("pg_ok"):
        return {"ok": False, "exit_code": 2, "blocker": "PostgreSQL connection is not ok"}
    if not components.get("tushare_configured"):
        return {"ok": False, "exit_code": 2, "blocker": "TUSHARE_TOKEN not configured"}

    auction = _find_job(status, "auction")
    last_run = str(auction.get("last_run") or "")
    parsed_result = _parse_last_result(auction.get("last_result"))
    stocks = int(parsed_result.get("stocks") or parsed_result.get("fetched") or 0)
    pg_written = int(auction.get("pg_written") or parsed_result.get("pg_written") or 0)

    summary = {
        "id": "auction",
        "last_run": auction.get("last_run"),
        "last_status": auction.get("last_status"),
        "source": parsed_result.get("source"),
        "stocks": stocks,
        "pg_written": pg_written,
    }

    if not last_run.startswith(target_date):
        return {
            "ok": False,
            "exit_code": 3,
            "blocker": "auction job has not run for target date",
            "auction": summary,
        }
    if auction.get("last_status") != "ok":
        return {
            "ok": False,
            "exit_code": 3,
            "blocker": f"auction job status is {auction.get('last_status')}",
            "auction": summary,
        }
    if stocks <= 0 and pg_written <= 0:
        return {
            "ok": False,
            "exit_code": 3,
            "blocker": "auction job ran but produced zero rows",
            "auction": summary,
        }

    return {"ok": True, "exit_code": 0, "auction": summary}


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args(argv)

    base_url = args.base_url.rstrip("/")
    readiness = _get_json(f"{base_url}/api/v1/data/readiness")
    status = _get_json(f"{base_url}/api/v1/data/status")
    result = evaluate_auction_status(readiness, status, args.date)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
