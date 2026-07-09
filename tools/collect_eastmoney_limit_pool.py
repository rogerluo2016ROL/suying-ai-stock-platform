#!/usr/bin/env python3
"""Collect Eastmoney limit-up pool as a seal-amount fallback.

Eastmoney exposes limit-up pool data through getTopicZTPool. The `fund`
field is used here as the fallback seal/order fund amount when the primary
Tushare `limit_list_d.fd_amount` and `kpl_list.limit_order` are unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json, execute_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
EASTMONEY_URL = "https://push2ex.eastmoney.com/getTopicZTPool"
EASTMONEY_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _to_float(value: Any, scale: float = 1.0) -> float | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return float(value) / scale
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value in (None, "", "-", "--"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _format_hhmmss(value: Any) -> str | None:
    if value in (None, "", "-", "--"):
        return None
    text = str(value).strip()
    if ":" in text:
        return text
    text = text.zfill(6)
    if len(text) != 6 or not text.isdigit():
        return None
    return f"{text[:2]}:{text[2:4]}:{text[4:6]}"


def _fetch_page(trade_date: str, page: int, page_size: int, timeout: int) -> dict[str, Any]:
    params = {
        "ut": EASTMONEY_UT,
        "dpt": "wz.ztzt",
        "Pageindex": page,
        "pagesize": page_size,
        "sort": "fbt:asc",
        "date": trade_date.replace("-", ""),
        "_": int(time.time() * 1000),
    }
    url = EASTMONEY_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/126 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/ztb/",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_limit_pool(trade_date: str, page_size: int, timeout: int) -> list[dict[str, Any]]:
    page_size = max(1, min(int(page_size), 200))
    first = _fetch_page(trade_date, 0, page_size, timeout)
    if int(first.get("rc") or 0) != 0:
        raise RuntimeError(f"Eastmoney rc={first.get('rc')} rt={first.get('rt')}")
    data = first.get("data") or {}
    rows = list(data.get("pool") or [])
    total = int(data.get("tc") or len(rows))
    pages = max(1, (total + page_size - 1) // page_size)
    for page in range(1, pages):
        payload = _fetch_page(trade_date, page, page_size, timeout)
        rows.extend((payload.get("data") or {}).get("pool") or [])

    rows_by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("c") or "").strip()
        if len(code) == 6 and code.isdigit():
            rows_by_code[code] = row
    return list(rows_by_code.values())


def build_db_rows(raw_rows: list[dict[str, Any]], trade_date: str) -> list[tuple[Any, ...]]:
    compact_date = trade_date.replace("-", "")
    rows: list[tuple[Any, ...]] = []
    for item in raw_rows:
        zttj = item.get("zttj") or {}
        rows.append(
            (
                str(item.get("c") or "").strip(),
                compact_date,
                item.get("n"),
                _to_float(item.get("p"), scale=1000.0),
                _to_float(item.get("zdp")),
                _to_float(item.get("amount")),
                _to_float(item.get("ltsz")),
                _to_float(item.get("tshare")),
                _to_float(item.get("hs")),
                _to_float(item.get("fund")),
                _format_hhmmss(item.get("fbt")),
                _format_hhmmss(item.get("lbt")),
                _to_int(item.get("zbc")),
                _to_int(item.get("lbc")),
                _to_int(item.get("lbc")),
                item.get("hybk"),
                _to_int(zttj.get("days")),
                _to_int(zttj.get("ct")),
                Json(item),
            )
        )
    return rows


def ensure_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS eastmoney_limit_pool (
            code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            name TEXT,
            price DOUBLE PRECISION,
            pct_chg DOUBLE PRECISION,
            amount DOUBLE PRECISION,
            float_mv DOUBLE PRECISION,
            total_mv DOUBLE PRECISION,
            turnover_ratio DOUBLE PRECISION,
            fd_amount DOUBLE PRECISION,
            first_time TEXT,
            last_time TEXT,
            open_times INTEGER,
            limit_times INTEGER,
            consecutive_boards INTEGER,
            industry TEXT,
            limit_stat_days INTEGER,
            limit_stat_count INTEGER,
            raw JSONB,
            source TEXT DEFAULT 'eastmoney_zt_pool',
            updated_at TIMESTAMP DEFAULT now(),
            PRIMARY KEY (code, trade_date)
        )
        """
    )


def write_limit_pool(pg_url: str, rows: list[tuple[Any, ...]], overwrite: bool) -> int:
    if not rows:
        return 0
    conn = psycopg2.connect(pg_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            ensure_table(cur)
            sql = """
                INSERT INTO eastmoney_limit_pool
                    (
                        code, trade_date, name, price, pct_chg, amount,
                        float_mv, total_mv, turnover_ratio, fd_amount,
                        first_time, last_time, open_times, limit_times,
                        consecutive_boards, industry, limit_stat_days,
                        limit_stat_count, raw
                    )
                VALUES %s
                ON CONFLICT (code, trade_date) DO {action}
            """.format(
                action=(
                    "UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price, "
                    "pct_chg = EXCLUDED.pct_chg, amount = EXCLUDED.amount, "
                    "float_mv = EXCLUDED.float_mv, total_mv = EXCLUDED.total_mv, "
                    "turnover_ratio = EXCLUDED.turnover_ratio, fd_amount = EXCLUDED.fd_amount, "
                    "first_time = EXCLUDED.first_time, last_time = EXCLUDED.last_time, "
                    "open_times = EXCLUDED.open_times, limit_times = EXCLUDED.limit_times, "
                    "consecutive_boards = EXCLUDED.consecutive_boards, industry = EXCLUDED.industry, "
                    "limit_stat_days = EXCLUDED.limit_stat_days, limit_stat_count = EXCLUDED.limit_stat_count, "
                    "raw = EXCLUDED.raw, source = 'eastmoney_zt_pool', updated_at = now()"
                    if overwrite
                    else "NOTHING"
                )
            )
            execute_values(cur, sql, rows, page_size=500)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="东方财富涨停池封单金额备用采集")
    parser.add_argument("--trade-date", default=date.today().isoformat())
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    started_at = datetime.now().isoformat(timespec="seconds")
    raw_rows = fetch_limit_pool(args.trade_date, args.page_size, args.timeout)
    rows = build_db_rows(raw_rows, args.trade_date)
    written = write_limit_pool(args.pg_url, rows, args.overwrite)
    result = {
        "status": "ok" if rows else "empty",
        "source": "eastmoney_zt_pool",
        "trade_date": args.trade_date,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "fetched": len(raw_rows),
        "usable_rows": len(rows),
        "written": written,
        "note": "备用口径：使用东方财富涨停池 fund 字段作为封单资金，主链路仍优先使用 limit_list_d.fd_amount。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
