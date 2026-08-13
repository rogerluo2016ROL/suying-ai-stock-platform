#!/usr/bin/env python3
"""
Sync push_metrics from the Feishu Base → the 妙搭 dashboard app's own DB.

Why this exists: the 妙搭 app's /api/* is gated by Feishu login at the platform
layer, so push_telemetry (a server-side writer with no user session) cannot POST
to the app's ingest endpoint. Instead push_telemetry writes the Base (works),
and THIS script mirrors Base → app DB via `lark-cli apps +db-execute` (which
runs with user auth). Run it periodically (cron / after each pipeline run) so
the dashboard stays live.

    python tools/sync_push_metrics_to_dashboard.py [--app-id app_xxx] [--environment online]
"""
from __future__ import annotations
import argparse, json, subprocess, sys, datetime, os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "push_observability.json"


def _cfg():
    c = {"base_token": "", "table_name": "push_metrics", "app_id": "", "environment": "online"}
    if CONFIG_PATH.exists():
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        c["base_token"] = raw.get("base_token", "")
        c["table_name"] = raw.get("table_name", "push_metrics")
        c["app_id"] = raw.get("dashboard_app_id", "")
        c["environment"] = raw.get("dashboard_environment", "online")
    return c


def _cli(args: list[str]) -> dict:
    cmd = ["lark-cli", *args, "--as", "user", "--format", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json: {(p.stdout or '')[:120]}"}


def read_base(base_token: str, table: str) -> list[dict]:
    """Read all push_metrics rows from the Base."""
    fields = ["task", "date", "task_label", "push_count", "success", "failure",
              "delivery_confirmed", "delivery_unconfirmed", "retries",
              "latency_ms_p50", "latency_ms_p95", "target_chats",
              "health_score", "status", "failure_reasons", "data_updated_at", "run_id"]
    d = _cli(["base", "+record-search", "--base-token", base_token, "--table-id", table,
              "--keyword", "20", "--search-field", "date",
              *[a for f in fields for a in ("--field-id", f)], "--limit", "200"])
    if not d.get("ok"):
        print(f"[sync] base read failed: {d.get('error')}", file=sys.stderr)
        return []
    data = d.get("data") or {}
    ids = data.get("record_id_list") or []
    rows = data.get("data") or []
    out = []
    for row in rows:
        rec = {name: (row[i] if i < len(row) else None) for i, name in enumerate(fields)}
        # status comes back as ["healthy"]; normalize
        if isinstance(rec.get("status"), list):
            rec["status"] = rec["status"][0] if rec["status"] else "down"
        out.append(rec)
    return out


def _sqlval(v) -> str:
    if v is None or v == "":
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


def build_upsert(rows: list[dict]) -> str:
    cols = ["task", "date", "task_label", "push_count", "success", "failure",
            "delivery_confirmed", "delivery_unconfirmed", "retries",
            "latency_ms_p50", "latency_ms_p95", "target_chats",
            "health_score", "status", "failure_reasons", "data_updated_at", "run_id"]
    if not rows:
        return "-- no rows"
    values = []
    for r in rows:
        values.append("(" + ",".join(_sqlval(r.get(c)) for c in cols) + ")")
    set_clause = ",".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("task", "date"))
    return (
        f"INSERT INTO push_metric ({','.join(cols)}) VALUES\n"
        + ",\n".join(values)
        + f"\nON CONFLICT (task,date) DO UPDATE SET {set_clause};"
    )


def write_app_db(app_id: str, env: str, sql: str) -> dict:
    sql_file = Path("./_sync_push_metrics.sql")
    sql_file.write_text(sql, encoding="utf-8")
    try:
        return _cli(["apps", "+db-execute", "--app-id", app_id, "--environment", env,
                     "--yes", "--file", "./_sync_push_metrics.sql"])
    finally:
        try:
            sql_file.unlink()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-id", default=None)
    ap.add_argument("--environment", default=None)
    args = ap.parse_args()
    cfg = _cfg()
    app_id = args.app_id or cfg["app_id"]
    env = args.environment or cfg["environment"]
    if not cfg["base_token"] or not app_id:
        print("[sync] missing base_token or app_id in config", file=sys.stderr)
        return 1
    rows = read_base(cfg["base_token"], cfg["table_name"])
    print(f"[sync] read {len(rows)} rows from Base")
    sql = build_upsert(rows)
    res = write_app_db(app_id, env, sql)
    ok = bool(res.get("ok"))
    print(f"[sync] app DB write ({env}): ok={ok} {(res.get('error') or '')[:120]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
