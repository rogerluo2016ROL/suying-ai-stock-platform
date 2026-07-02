#!/usr/bin/env python3
"""Monitor when limit-board data sources become available intraday.

This is a read-only probe. It checks Tushare from the running data-service
container, checks local PostgreSQL, and appends one CSV/JSONL row per run.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:16432/kronos"


def compact_date(value: str) -> str:
    return value.replace("-", "")


def dashed_date(value: str) -> str:
    raw = compact_date(value)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def run_cmd(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def probe_tushare(trade_date: str, container: str) -> dict[str, Any]:
    code = f"""
from app.config import TUSHARE_TOKEN
import json
import tushare as ts

trade_date = {trade_date!r}
result = {{"ok": True, "errors": []}}
try:
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    for api in ("limit_list_d", "kpl_list"):
        try:
            df = pro.query(api, trade_date=trade_date)
            result[f"{{api}}_rows"] = 0 if df is None else int(len(df))
            result[f"{{api}}_columns"] = [] if df is None else list(df.columns)
        except Exception as exc:
            result[f"{{api}}_rows"] = None
            result["errors"].append(f"{{api}}: {{type(exc).__name__}} {{str(exc)[:160]}}")
    try:
        df = pro.query("kpl_list")
        result["kpl_list_latest_date"] = None if df is None or df.empty else str(df["trade_date"].max())
    except Exception as exc:
        result["kpl_list_latest_date"] = None
        result["errors"].append(f"kpl_list_latest: {{type(exc).__name__}} {{str(exc)[:160]}}")
except Exception as exc:
    result = {{"ok": False, "errors": [f"init: {{type(exc).__name__}} {{str(exc)[:160]}}"]}}
print(json.dumps(result, ensure_ascii=False))
"""
    rc, stdout, stderr = run_cmd(["docker", "exec", container, "python", "-c", code], timeout=90)
    if rc != 0:
        return {"ok": False, "errors": [stderr or stdout or f"docker exec failed rc={rc}"]}
    try:
        return json.loads(stdout.splitlines()[-1])
    except Exception as exc:
        return {"ok": False, "errors": [f"parse: {type(exc).__name__} {str(exc)[:160]}", stdout]}


def probe_pg(trade_date: str, pg_url: str) -> dict[str, Any]:
    dash = dashed_date(trade_date)
    compact = compact_date(trade_date)
    sql = f"""
SELECT json_build_object(
  'ok', true,
  'limit_list_d_rows', (
    SELECT COUNT(*) FROM limit_list_d
    WHERE trade_date::text IN ('{dash}', '{compact}')
  ),
  'limit_list_d_u_rows', (
    SELECT COUNT(*) FROM limit_list_d
    WHERE trade_date::text IN ('{dash}', '{compact}') AND limit_type = 'U'
  ),
  'kpl_list_table', to_regclass('public.kpl_list')::text
)::text;
"""
    rc, stdout, stderr = run_cmd(["psql", pg_url, "-At", "-c", sql], timeout=30)
    if rc != 0:
        return {"ok": False, "errors": [stderr or stdout or f"psql failed rc={rc}"]}
    try:
        result = json.loads(stdout.splitlines()[-1])
    except Exception as exc:
        return {"ok": False, "errors": [f"parse: {type(exc).__name__} {str(exc)[:160]}", stdout]}
    if result.get("kpl_list_table"):
        kpl_sql = (
            "SELECT COUNT(*) FROM kpl_list "
            f"WHERE trade_date::text IN ('{dash}', '{compact}');"
        )
        rc, stdout, stderr = run_cmd(["psql", pg_url, "-At", "-c", kpl_sql], timeout=30)
        if rc == 0:
            try:
                result["kpl_list_rows"] = int(stdout.splitlines()[-1])
            except Exception:
                result["kpl_list_rows"] = None
        else:
            result["kpl_list_rows"] = None
            result.setdefault("errors", []).append(stderr or stdout or f"kpl psql failed rc={rc}")
    else:
        result["kpl_list_rows"] = None
    return result


def append_outputs(record: dict[str, Any], output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trade_date = record["trade_date"]
    csv_path = output_dir / f"{trade_date}_limit_source_availability.csv"
    jsonl_path = output_dir / f"{trade_date}_limit_source_availability.jsonl"
    first_path = output_dir / f"{trade_date}_first_available.json"

    fields = [
        "observed_at",
        "trade_date",
        "tushare_limit_list_d_rows",
        "tushare_kpl_list_rows",
        "tushare_kpl_list_latest_date",
        "pg_limit_list_d_rows",
        "pg_limit_list_d_u_rows",
        "pg_kpl_list_table",
        "pg_kpl_list_rows",
        "limit_list_d_available",
        "kpl_list_available",
    ]
    write_header = not csv_path.exists()
    with csv_path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if write_header:
            writer.writeheader()
        writer.writerow({key: record.get(key) for key in fields})

    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    first: dict[str, Any] = {}
    if first_path.exists():
        try:
            first = json.loads(first_path.read_text(encoding="utf-8"))
        except Exception:
            first = {}
    for key in ("limit_list_d_available", "kpl_list_available"):
        if record.get(key) and key not in first:
            first[key] = {
                "first_observed_at": record["observed_at"],
                "trade_date": trade_date,
                "record": record,
            }
    first_path.write_text(json.dumps(first, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return csv_path, jsonl_path, first_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    parser.add_argument("--container", default="data-service")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "data_source_monitor"),
    )
    args = parser.parse_args(argv)

    trade_date = compact_date(args.trade_date)
    observed_at = datetime.now().isoformat(timespec="seconds")
    tushare_result = probe_tushare(trade_date, args.container)
    pg_result = probe_pg(trade_date, args.pg_url)

    record = {
        "observed_at": observed_at,
        "trade_date": trade_date,
        "tushare": tushare_result,
        "pg": pg_result,
        "tushare_limit_list_d_rows": tushare_result.get("limit_list_d_rows"),
        "tushare_kpl_list_rows": tushare_result.get("kpl_list_rows"),
        "tushare_kpl_list_latest_date": tushare_result.get("kpl_list_latest_date"),
        "pg_limit_list_d_rows": pg_result.get("limit_list_d_rows"),
        "pg_limit_list_d_u_rows": pg_result.get("limit_list_d_u_rows"),
        "pg_kpl_list_table": pg_result.get("kpl_list_table"),
        "pg_kpl_list_rows": pg_result.get("kpl_list_rows"),
    }
    record["limit_list_d_available"] = bool(
        (record.get("tushare_limit_list_d_rows") or 0) > 0
        or (record.get("pg_limit_list_d_rows") or 0) > 0
    )
    record["kpl_list_available"] = bool(
        (record.get("tushare_kpl_list_rows") or 0) > 0
        or (record.get("pg_kpl_list_rows") or 0) > 0
    )

    csv_path, jsonl_path, first_path = append_outputs(record, Path(args.output_dir))
    print(json.dumps(record, ensure_ascii=False, indent=2, default=str))
    print(f"CSV: {csv_path}")
    print(f"JSONL: {jsonl_path}")
    print(f"FIRST: {first_path}")
    return 0 if tushare_result.get("ok") or pg_result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
