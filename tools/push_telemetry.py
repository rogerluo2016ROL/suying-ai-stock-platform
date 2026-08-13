#!/usr/bin/env python3
"""
Unified push-task telemetry → Feishu Base (push_metrics).

All four Feishu push tasks (research_pipeline / embodied_refresh / screener /
alert) call ``record()`` to accumulate daily metrics keyed by ``(date, task)``.
Tasks that fire many times per day (screener, alert) delta-merge into a single
daily row; status / health_score are recomputed on every write and
``data_updated_at`` is always refreshed.

Transport: prefers ``lark-cli`` (subprocess); falls back to Feishu OpenAPI
(``LARK_APP_ID`` / ``LARK_APP_SECRET``) so containerised services without
lark-cli on PATH still report. Telemetry NEVER raises — a failure is logged to
stderr and swallowed so it can never break the push path itself.

CLI (manual / cron / smoke test):
    python tools/push_telemetry.py record --task research_pipeline --push 1 --success 1
    python tools/push_telemetry.py show   --task research_pipeline --date 2026-08-12
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "push_observability.json"
TZ_CST = datetime.timezone(datetime.timedelta(hours=8))  # Asia/Shanghai

_ADDITIVE = ["push_count", "success", "failure", "delivery_confirmed", "delivery_unconfirmed", "retries"]
_LATEST = ["latency_ms_p50", "latency_ms_p95", "target_chats"]
# fields pulled back when reading an existing row for delta-merge
_READ_FIELDS = _ADDITIVE + _LATEST + ["failure_reasons", "health_score", "status", "run_id"]

_DEFAULT_LABELS = {
    "research_pipeline": "研究管线推送",
    "embodied_refresh": "具身智能每日刷新",
    "screener": "选股机器人响应",
    "alert": "告警推送",
}


# --------------------------------------------------------------------------- #
# config / time helpers
# --------------------------------------------------------------------------- #
def _load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "base_token": os.environ.get("PUSH_METRICS_BASE_TOKEN", ""),
        "table_id": os.environ.get("PUSH_METRICS_TABLE_ID", ""),
        "table_name": os.environ.get("PUSH_METRICS_TABLE", "push_metrics"),
        "tasks": dict(_DEFAULT_LABELS),
    }
    try:
        if CONFIG_PATH.exists():
            file_cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k in ("base_token", "table_id", "table_name", "wiki_space_id",
                      "base_url", "dashboard_url", "daily_card_chat_id"):
                if file_cfg.get(k):
                    cfg[k] = file_cfg[k]
            if file_cfg.get("tasks"):
                cfg["tasks"] = file_cfg["tasks"]
    except Exception as exc:  # pragma: no cover - config best-effort
        print(f"[push_telemetry] config load failed: {exc}", file=sys.stderr)
    return cfg


CONFIG = _load_config()
BASE_TOKEN: str = CONFIG["base_token"]
TABLE_ID: str = CONFIG["table_id"]
TABLE_NAME: str = CONFIG["table_name"]
TASK_LABELS: dict[str, str] = CONFIG.get("tasks") or _DEFAULT_LABELS


def _now_iso() -> str:
    return datetime.datetime.now(TZ_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def _today() -> str:
    return datetime.datetime.now(TZ_CST).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# status / health
# --------------------------------------------------------------------------- #
def compute_status_health(metrics: dict[str, Any]) -> tuple[str, int]:
    """Map a merged metric snapshot to (status, health_score 0..100).

    Score is anchored on success_rate (the dominant signal) then nudged by
    delivery confirmation, retries and latency, so a well-behaved task
    (≥99% success, ≥95% delivery, few retries) lands in the 88–97 band.

    healthy  : success_rate >= 99% AND (uninstrumented OR delivery_rate >= 95%)
    warning  : success_rate >= 90%
    degraded : success_rate < 90%
    down     : push_count == 0 (a task that should have pushed but didn't)
    """
    push = int(metrics.get("push_count") or 0)
    success = int(metrics.get("success") or 0)
    retries = int(metrics.get("retries") or 0)
    dconf = int(metrics.get("delivery_confirmed") or 0)
    dunconf = int(metrics.get("delivery_unconfirmed") or 0)
    lat_p95 = metrics.get("latency_ms_p95") or 0
    try:
        lat_p95 = float(lat_p95)
    except (TypeError, ValueError):
        lat_p95 = 0.0

    if push == 0:
        return ("down", 0)

    success_rate = success / push
    delivery_rate = (dconf / (dconf + dunconf)) if (dconf + dunconf) > 0 else None

    score = 100.0
    score -= (1.0 - success_rate) * 200.0                      # success is dominant: 1% failure ≈ -2
    if delivery_rate is not None:
        score -= (1.0 - delivery_rate) * 50.0                  # unconfirmed delivery penalty
    else:
        score -= 5.0                                           # small penalty when confirmation uninstrumented
    score -= min(10.0, retries * 1.5)                          # retry churn
    if lat_p95 > 1500:
        score -= min(10.0, (lat_p95 - 1500) / 300.0)           # slow sends
    score = max(0.0, min(100.0, round(score)))

    if success_rate >= 0.99 and (delivery_rate is None or delivery_rate >= 0.95):
        status = "healthy"
    elif success_rate >= 0.90:
        status = "warning"
    else:
        status = "degraded"
    return (status, int(score))


# --------------------------------------------------------------------------- #
# transport: lark-cli adapter (preferred)
# --------------------------------------------------------------------------- #
def _cli(args: list[str]) -> dict[str, Any]:
    cmd = ["lark-cli", *args, "--as", "user", "--format", "json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as exc:  # lark-cli missing / timeout
        return {"ok": False, "error": f"lark-cli invocation failed: {exc}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-json stdout: {(proc.stdout or '')[:160]} | stderr: {(proc.stderr or '')[:160]}"}


def _cli_fetch(task: str, date: str) -> tuple[Optional[str], dict[str, Any]]:
    """Return (record_id, current_field_values) for (task, date) or (None, {})."""
    if not BASE_TOKEN:
        return (None, {})
    select = ["task", "date", *_READ_FIELDS]
    d = _cli([
        "base", "+record-search",
        "--base-token", BASE_TOKEN, "--table-id", TABLE_NAME,
        "--keyword", task, "--search-field", "task",
        *[a for f in select for a in ("--field-id", f)],
        "--limit", "100",
    ])
    if not d.get("ok"):
        return (None, {})
    data = d.get("data") or {}
    ids = data.get("record_id_list") or []
    rows = data.get("data") or []
    for rid, row in zip(ids, rows):
        # row aligns to `select`: [task, date, push_count, ...]
        if len(row) >= 2 and str(row[1]) == date:
            values = {name: row[i + 2] for i, name in enumerate(_READ_FIELDS) if (i + 2) < len(row)}
            return (rid, values)
    return (None, {})


def _cli_upsert(rid: Optional[str], fields: dict[str, Any]) -> dict[str, Any]:
    if rid:
        return _cli([
            "base", "+record-batch-update",
            "--base-token", BASE_TOKEN, "--table-id", TABLE_NAME,
            "--json", json.dumps({"update_records": {rid: fields}}, ensure_ascii=False),
        ])
    return _cli([
        "base", "+record-batch-create",
        "--base-token", BASE_TOKEN, "--table-id", TABLE_NAME,
        "--json", json.dumps({"create_records": [fields]}, ensure_ascii=False),
    ])


# --------------------------------------------------------------------------- #
# transport: OpenAPI adapter (fallback for containers w/o lark-cli)
# --------------------------------------------------------------------------- #
_API = "https://open.feishu.cn/open-apis"


def _http(method: str, url: str, body: Any = None, token: Optional[str] = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        except Exception:
            return {"code": exc.code, "msg": str(exc)}
    except Exception as exc:
        return {"code": -1, "msg": str(exc)}


def _tenant_token() -> Optional[str]:
    app_id = os.environ.get("LARK_APP_ID")
    app_secret = os.environ.get("LARK_APP_SECRET")
    if not app_id or not app_secret or not BASE_TOKEN or not TABLE_ID:
        return None
    d = _http("POST", f"{_API}/auth/v3/tenant_access_token/internal",
              {"app_id": app_id, "app_secret": app_secret})
    return d.get("tenant_access_token")


def _api_fetch(task: str, date: str, token: str) -> tuple[Optional[str], dict[str, Any]]:
    url = f"{_API}/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/search?page_size=50"
    body = {"filter": {"conjunction": "and", "conditions": [
        {"field_name": "task", "operator": "is", "value": [task]},
        {"field_name": "date", "operator": "is", "value": [date]},
    ]}}
    d = _http("POST", url, body, token)
    if d.get("code") != 0:
        return (None, {})
    for item in (d.get("data") or {}).get("items", []) or []:
        return (item.get("record_id"), item.get("fields") or {})
    return (None, {})


def _api_upsert(rid: Optional[str], fields: dict[str, Any], token: str) -> dict[str, Any]:
    base = f"{_API}/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records"
    if rid:
        return _http("PUT", f"{base}/{rid}", {"fields": fields}, token)
    return _http("POST", f"{base}/batch_create", {"records": [{"fields": fields}]}, token)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def _merge(existing: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for k in _ADDITIVE:
        try:
            base_v = float(existing.get(k) or 0)
        except (TypeError, ValueError):
            base_v = 0.0
        try:
            add_v = float(delta.get(k) or 0)
        except (TypeError, ValueError):
            add_v = 0.0
        merged[k] = int(base_v + add_v)
    for k in _LATEST:
        if delta.get(k) is not None:
            merged[k] = delta[k]
        elif existing.get(k) is not None:
            merged[k] = existing[k]
        else:
            merged[k] = None
    # failure_reasons: merge unique, preserve order, cap 5
    seen: set[str] = set()
    reasons: list[str] = []
    raw_existing = existing.get("failure_reasons")
    if isinstance(raw_existing, str) and raw_existing.strip():
        for r in raw_existing.split(";"):
            r = r.strip()
            if r and r not in seen:
                seen.add(r)
                reasons.append(r)
    for r in (delta.get("failure_reasons") or []):
        if isinstance(r, str) and r.strip() and r.strip() not in seen:
            seen.add(r.strip())
            reasons.append(r.strip())
    merged["failure_reasons"] = "; ".join(reasons[:5])
    return merged


def record(
    task: str,
    *,
    date: Optional[str] = None,
    push: int = 0,
    success: int = 0,
    failure: int = 0,
    delivery_confirmed: int = 0,
    delivery_unconfirmed: int = 0,
    retries: int = 0,
    latency_ms_p50: Optional[float] = None,
    latency_ms_p95: Optional[float] = None,
    target_chats: Optional[int] = None,
    failure_reasons: Optional[list[str]] = None,
    run_id: Optional[str] = None,
) -> dict[str, Any]:
    """Accumulate a delta into the (date, task) daily row. Never raises.

    Additive fields (push/success/failure/delivery_*/retries) sum across calls.
    latency_*/target_chats take the latest non-null value. status/health_score
    recompute from the merged snapshot. data_updated_at refreshes on every write.
    """
    date = date or _today()
    delta = {
        "push_count": push, "success": success, "failure": failure,
        "delivery_confirmed": delivery_confirmed, "delivery_unconfirmed": delivery_unconfirmed,
        "retries": retries, "latency_ms_p50": latency_ms_p50, "latency_ms_p95": latency_ms_p95,
        "target_chats": target_chats, "failure_reasons": failure_reasons or [],
    }
    label = TASK_LABELS.get(task, task)
    try:
        rid, existing = _fetch(task, date)
        merged = _merge(existing, delta)
        status, score = compute_status_health(merged)
        fields: dict[str, Any] = {
            "task_label": label, "date": date, "task": task,
            "health_score": score, "status": status,
            "failure_reasons": merged["failure_reasons"],
            "data_updated_at": _now_iso(),
        }
        for k in _ADDITIVE:
            fields[k] = merged[k]
        for k in _LATEST:
            if merged.get(k) is not None:
                fields[k] = merged[k]
        if run_id or existing.get("run_id"):
            fields["run_id"] = run_id or existing.get("run_id")

        result = _upsert(rid, fields)
        ok = bool(result.get("ok"))
        return {"ok": ok, "task": task, "date": date, "record_id": rid,
                "status": status, "health_score": score,
                "merged": {k: merged[k] for k in _ADDITIVE},
                "error": (result.get("error") or result.get("msg")) if not ok else None}
    except Exception as exc:  # telemetry must never break the caller
        print(f"[push_telemetry] record failed task={task} date={date}: {exc}", file=sys.stderr)
        return {"ok": False, "task": task, "date": date, "error": str(exc)}


def _fetch(task: str, date: str) -> tuple[Optional[str], dict[str, Any]]:
    """Try lark-cli first, then OpenAPI."""
    rid, values = _cli_fetch(task, date)
    if rid is not None or BASE_TOKEN:
        if rid is not None:
            return rid, values
        # lark-cli returned no row but didn't error → fall through to API only if cli absent
    if not _lark_cli_available():
        token = _tenant_token()
        if token:
            return _api_fetch(task, date, token)
    return (None, {})


def _upsert(rid: Optional[str], fields: dict[str, Any]) -> dict[str, Any]:
    if _lark_cli_available():
        return _cli_upsert(rid, fields)
    token = _tenant_token()
    if token:
        return _api_upsert(rid, fields, token)
    return {"ok": False, "error": "no transport: lark-cli missing and LARK_APP_ID/SECRET unset"}


_LARK_CLI_OK: Optional[bool] = None


def _lark_cli_available() -> bool:
    global _LARK_CLI_OK
    if _LARK_CLI_OK is None:
        try:
            subprocess.run(["lark-cli", "--version"], capture_output=True, timeout=10)
            _LARK_CLI_OK = True
        except Exception:
            _LARK_CLI_OK = False
    return _LARK_CLI_OK


def show(task: str, date: Optional[str] = None) -> dict[str, Any]:
    """Read the current daily row for a task (debug / dashboard helper)."""
    date = date or _today()
    rid, values = _fetch(task, date)
    return {"ok": rid is not None, "task": task, "date": date, "record_id": rid, "fields": values}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _main() -> int:
    parser = argparse.ArgumentParser(description="Push-task telemetry → Feishu Base")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("record", help="accumulate a metric delta")
    r.add_argument("--task", required=True)
    r.add_argument("--date", default=None)
    r.add_argument("--push", type=int, default=0)
    r.add_argument("--success", type=int, default=0)
    r.add_argument("--failure", type=int, default=0)
    r.add_argument("--delivery-confirmed", type=int, default=0, dest="delivery_confirmed")
    r.add_argument("--delivery-unconfirmed", type=int, default=0, dest="delivery_unconfirmed")
    r.add_argument("--retries", type=int, default=0)
    r.add_argument("--latency-p50", type=float, default=None, dest="latency_ms_p50")
    r.add_argument("--latency-p95", type=float, default=None, dest="latency_ms_p95")
    r.add_argument("--target-chats", type=int, default=None, dest="target_chats")
    r.add_argument("--failure-reason", action="append", default=None, dest="failure_reasons")
    r.add_argument("--run-id", default=None, dest="run_id")

    s = sub.add_parser("show", help="read current daily row")
    s.add_argument("--task", required=True)
    s.add_argument("--date", default=None)

    args = parser.parse_args()
    if args.cmd == "record":
        out = record(
            args.task, date=args.date, push=args.push, success=args.success, failure=args.failure,
            delivery_confirmed=args.delivery_confirmed, delivery_unconfirmed=args.delivery_unconfirmed,
            retries=args.retries, latency_ms_p50=args.latency_ms_p50, latency_ms_p95=args.latency_ms_p95,
            target_chats=args.target_chats, failure_reasons=args.failure_reasons, run_id=args.run_id,
        )
    else:
        out = show(args.task, args.date)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
