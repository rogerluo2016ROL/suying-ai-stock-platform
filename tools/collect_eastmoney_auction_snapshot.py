#!/usr/bin/env python3
"""Collect Eastmoney A-share spot snapshot as a last-resort fallback.

This is not the Eastmoney limit-up pool. It intentionally does not provide
seal/order fund amount, and only feeds the emergency snapshot model through
stk_auction_o when both official and limit-pool sources are unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
EASTMONEY_HOSTS = (
    "push2delay.eastmoney.com",
    "16.push2.eastmoney.com",
    "20.push2.eastmoney.com",
    "28.push2.eastmoney.com",
    "push2.eastmoney.com",
)


def _to_float(value: Any) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _fetch_page_from_host(host: str, page: int, page_size: int, timeout: int) -> dict[str, Any]:
    params = {
        "pn": page,
        "pz": page_size,
        "po": 1,
        "np": 1,
        "fltt": 2,
        "invt": 2,
        "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f12,f14,f2,f3,f5,f6,f17,f18",
        "_": int(time.time() * 1000),
    }
    url = f"https://{host}/api/qt/clist/get?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_page(page: int, page_size: int, timeout: int) -> tuple[str, dict[str, Any]]:
    errors: list[str] = []
    for host in EASTMONEY_HOSTS:
        try:
            return host, _fetch_page_from_host(host, page, page_size, timeout)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            errors.append(f"{host}: {type(exc).__name__}")
    raise RuntimeError("; ".join(errors))


def fetch_eastmoney_rows(page_size: int, timeout: int) -> tuple[str, list[dict[str, Any]]]:
    page_size = max(1, min(int(page_size), 100))
    host, first = _fetch_page(1, page_size, timeout)
    data = first.get("data") or {}
    rows = list(data.get("diff") or [])
    total = int(data.get("total") or len(rows))
    pages = max(1, (total + page_size - 1) // page_size)
    for page in range(2, pages + 1):
        payload = _fetch_page_from_host(host, page, page_size, timeout)
        rows.extend((payload.get("data") or {}).get("diff") or [])
    return host, rows


def build_stk_auction_rows(raw_rows: list[dict[str, Any]], trade_date: str) -> list[tuple]:
    rows_by_code: dict[str, tuple] = {}
    for item in raw_rows:
        code = str(item.get("f12") or "").strip()
        if len(code) != 6 or not code.isdigit():
            continue
        latest = _to_float(item.get("f2"))
        open_price = _to_float(item.get("f17")) or latest
        pre_close = _to_float(item.get("f18"))
        amount = _to_float(item.get("f6")) or 0.0
        volume = _to_float(item.get("f5")) or 0.0
        if open_price is None or pre_close is None:
            continue
        rows_by_code[code] = (
            code,
            trade_date,
            pre_close,
            open_price,
            open_price,
            open_price,
            volume,
            amount,
            open_price,
        )
    return list(rows_by_code.values())


def write_stk_auction_o(pg_url: str, rows: list[tuple], overwrite: bool) -> int:
    if not rows:
        return 0
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            sql = """
                INSERT INTO stk_auction_o
                    (code, trade_date, close, open, high, low, vol, amount, vwap)
                VALUES %s
                ON CONFLICT (code, trade_date) DO {action}
            """.format(
                action=(
                    "UPDATE SET close = EXCLUDED.close, open = EXCLUDED.open, "
                    "high = EXCLUDED.high, low = EXCLUDED.low, vol = EXCLUDED.vol, "
                    "amount = EXCLUDED.amount, vwap = EXCLUDED.vwap, updated_at = now()"
                    if overwrite
                    else "NOTHING"
                )
            )
            execute_values(cur, sql, rows, page_size=1000)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="东方财富普通行情快照最后兜底采集")
    parser.add_argument("--trade-date", default=date.today().isoformat())
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    started_at = datetime.now().isoformat(timespec="seconds")
    host, raw_rows = fetch_eastmoney_rows(args.page_size, args.timeout)
    rows = build_stk_auction_rows(raw_rows, args.trade_date)
    written = write_stk_auction_o(args.pg_url, rows, args.overwrite)
    result = {
        "status": "ok" if rows else "empty",
        "source": "eastmoney_spot_snapshot",
        "host": host,
        "trade_date": args.trade_date,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "fetched": len(raw_rows),
        "usable_rows": len(rows),
        "written": written,
        "note": "普通行情快照口径，不包含涨停池封单资金；仅在主接口和东方财富涨停池都不可用时最后兜底。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
