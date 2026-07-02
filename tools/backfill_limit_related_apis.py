#!/usr/bin/env python3
"""Backfill limit-board related Tushare APIs into PostgreSQL.

This script is intentionally separate from the regular scheduler because it
does long-range, date-by-date replacement writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import psycopg2
import tushare as ts
from psycopg2.extras import execute_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "kronos-data"))


DEFAULT_APIS = (
    "limit_list_d",
    "limit_list_ths",
    "limit_step",
    "limit_cpt_list",
    "kpl_list",
    "kpl_concept_cons",
    "dc_index",
    "dc_member",
    "dc_hot",
    "top_list",
    "top_inst",
    "ths_hot",
    "stk_limit",
)

RAW_TABLES = {
    "limit_list_ths": "ts_raw_limit_list_ths",
    "limit_step": "ts_raw_limit_step",
    "limit_cpt_list": "ts_raw_limit_cpt_list",
    "kpl_list": "kpl_list",
    "kpl_concept_cons": "kpl_concept_cons",
    "dc_index": "dc_concept",
    "dc_member": "dc_member",
    "dc_hot": "dc_hot",
    "ths_hot": "ts_raw_ths_hot",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill limit-board related APIs")
    parser.add_argument("--start", help="YYYY-MM-DD, default 10 years ago")
    parser.add_argument("--end", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--apis", default=",".join(DEFAULT_APIS))
    parser.add_argument("--sleep", type=float, default=0.14, help="seconds between API calls")
    parser.add_argument("--max-days", type=int, default=None, help="debug limit")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def pg_url() -> str:
    return os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def ymd_dash(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}" if "-" not in value else value


def ymd_compact(value: str) -> str:
    return value.replace("-", "")


def get_trade_dates(conn, start: str, end: str) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cal_date::text
        FROM trade_cal
        WHERE is_open = 1
          AND cal_date BETWEEN %s AND %s
        ORDER BY cal_date
        """,
        (start, end),
    )
    rows = [ymd_compact(r[0]) for r in cur.fetchall()]
    cur.close()
    return rows


def init_tushare():
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not set")
    ts.set_token(token)
    return ts.pro_api()


def safe_float(value):
    if value is None:
        return None
    try:
        if value != value:
            return None
        return float(value)
    except Exception:
        return None


def safe_int(value):
    if value is None:
        return None
    try:
        if value != value:
            return None
        return int(value)
    except Exception:
        return None


def row_hash(api: str, row: dict) -> str:
    text = json.dumps({"api": api, "row": row}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def delete_date(cur, table: str, trade_date: str, raw_api: str | None = None) -> None:
    dash = ymd_dash(trade_date)
    compact = ymd_compact(trade_date)
    if raw_api:
        cur.execute(
            f"DELETE FROM {table} WHERE _source_api = %s AND trade_date IN (%s, %s)",
            (raw_api, dash, compact),
        )
    elif table in {"top_list", "top_inst", "stk_limit"}:
        cur.execute(f"DELETE FROM {table} WHERE trade_date = %s", (dash,))
    else:
        cur.execute(f"DELETE FROM {table} WHERE trade_date IN (%s, %s)", (dash, compact))


def insert_raw(cur, api: str, df) -> int:
    table = RAW_TABLES[api]
    if df is None or df.empty:
        return 0
    cur.execute(
        f"CREATE TABLE IF NOT EXISTS {table} "
        "(_row_hash text primary key, _source_api text, _ingested_at timestamptz default now())"
    )
    for col in [str(c) for c in df.columns]:
        safe_col = '"' + col.replace('"', '""') + '"'
        cur.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {safe_col} text")
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    table_cols = [r[0] for r in cur.fetchall()]
    data_cols = [c for c in table_cols if c not in {"_row_hash", "_source_api", "_ingested_at"}]
    cols = ["_row_hash", "_source_api"] + data_cols
    rows = []
    for _, series in df.iterrows():
        row = {str(k): (None if v != v else str(v)) for k, v in series.to_dict().items()}
        rows.append([row_hash(api, row), api] + [row.get(c) for c in data_cols])
    execute_values(
        cur,
        f"INSERT INTO {table} ({','.join(quote_ident(c) for c in cols)}) "
        "VALUES %s ON CONFLICT (_row_hash) DO NOTHING",
        rows,
        page_size=1000,
    )
    return len(rows)


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def insert_limit_list_d(cur, pro, trade_date: str) -> tuple[int, int]:
    cols = [
        "ts_code",
        "trade_date",
        "limit_type",
        "up_limit",
        "down_limit",
        "first_time",
        "last_time",
        "open_times",
        "up_stat",
        "fd_amount",
        "pct_chg",
        "pre_close",
        "close",
        "open",
        "name",
        "industry",
        "amount",
        "float_mv",
        "total_mv",
        "turnover_ratio",
        "limit_amount",
        "limit",
    ]
    rows = []
    fetched = 0
    for limit_type in ("U", "D", "Z"):
        try:
            df = pro.limit_list_d(trade_date=trade_date, limit_type=limit_type)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        fetched += len(df)
        for _, r in df.iterrows():
            rows.append(
                (
                    str(r.get("ts_code", "")),
                    str(r.get("trade_date", trade_date)),
                    limit_type,
                    safe_float(r.get("up_limit")),
                    safe_float(r.get("down_limit")),
                    r.get("first_time"),
                    r.get("last_time"),
                    safe_int(r.get("open_times")),
                    r.get("up_stat"),
                    safe_float(r.get("fd_amount")),
                    safe_float(r.get("pct_chg")),
                    safe_float(r.get("pre_close")),
                    safe_float(r.get("close")),
                    safe_float(r.get("open")),
                    r.get("name"),
                    r.get("industry"),
                    safe_float(r.get("amount")),
                    safe_float(r.get("float_mv")),
                    safe_float(r.get("total_mv")),
                    safe_float(r.get("turnover_ratio")),
                    safe_float(r.get("limit_amount")),
                    safe_float(r.get("limit")),
                )
            )
    if rows:
        col_sql = ",".join([f'"{c}"' if c == "limit" else c for c in cols])
        execute_values(
            cur,
            f"INSERT INTO limit_list_d ({col_sql}) VALUES %s ON CONFLICT (ts_code, trade_date, limit_type) DO NOTHING",
            rows,
            page_size=1000,
        )
    return fetched, len(rows)


def insert_stk_limit(cur, df, trade_date: str) -> int:
    if df is None or df.empty:
        return 0
    rows = [
        (
            str(r.get("ts_code", "")).split(".")[0],
            ymd_dash(trade_date),
            safe_float(r.get("pre_close")),
            safe_float(r.get("up_limit")),
            safe_float(r.get("down_limit")),
            None,
        )
        for _, r in df.iterrows()
    ]
    execute_values(
        cur,
        """
        INSERT INTO stk_limit(code, trade_date, pre_close, up_limit, down_limit, limit_status)
        VALUES %s
        ON CONFLICT (code, trade_date) DO UPDATE
        SET pre_close = EXCLUDED.pre_close,
            up_limit = EXCLUDED.up_limit,
            down_limit = EXCLUDED.down_limit
        """,
        rows,
        page_size=1000,
    )
    return len(rows)


def insert_top_list(cur, df, trade_date: str) -> int:
    if df is None or df.empty:
        return 0
    merged = {}
    for _, r in df.iterrows():
        key = (str(r.get("ts_code", "")).split(".")[0], ymd_dash(trade_date))
        current = merged.get(key)
        reason = str(r.get("reason") or "")
        if current is None:
            merged[key] = {
                "reason": [reason] if reason else [],
                "buy_amount": safe_float(r.get("l_buy")) or 0,
                "sell_amount": safe_float(r.get("l_sell")) or 0,
                "net_amount": safe_float(r.get("net_amount")) or 0,
                "name": r.get("name"),
                "close": safe_float(r.get("close")),
                "pct_change": safe_float(r.get("pct_change")),
                "turnover_rate": safe_float(r.get("turnover_rate")),
                "amount": safe_float(r.get("amount")),
            }
        else:
            if reason and reason not in current["reason"]:
                current["reason"].append(reason)
            current["buy_amount"] += safe_float(r.get("l_buy")) or 0
            current["sell_amount"] += safe_float(r.get("l_sell")) or 0
            current["net_amount"] += safe_float(r.get("net_amount")) or 0
    rows = [
        (
            code,
            td,
            "；".join(v["reason"]),
            v["buy_amount"],
            v["sell_amount"],
            v["net_amount"],
            v["name"],
            v["close"],
            v["pct_change"],
            v["turnover_rate"],
            v["amount"],
        )
        for (code, td), v in merged.items()
    ]
    execute_values(
        cur,
        """
        INSERT INTO top_list(code, trade_date, reason, buy_amount, sell_amount, net_amount,
                             name, close, pct_change, turnover_rate, amount)
        VALUES %s
        ON CONFLICT (code, trade_date) DO UPDATE
        SET reason = EXCLUDED.reason,
            buy_amount = EXCLUDED.buy_amount,
            sell_amount = EXCLUDED.sell_amount,
            net_amount = EXCLUDED.net_amount,
            name = EXCLUDED.name,
            close = EXCLUDED.close,
            pct_change = EXCLUDED.pct_change,
            turnover_rate = EXCLUDED.turnover_rate,
            amount = EXCLUDED.amount
        """,
        rows,
        page_size=1000,
    )
    return len(rows)


def insert_top_inst(cur, df, trade_date: str) -> int:
    if df is None or df.empty:
        return 0
    rows = [
        (
            str(r.get("ts_code", "")).split(".")[0],
            ymd_dash(trade_date),
            r.get("exalter"),
            safe_float(r.get("buy")),
            safe_float(r.get("buy_rate")),
            safe_float(r.get("sell")),
            safe_float(r.get("sell_rate")),
            safe_float(r.get("net_buy")),
        )
        for _, r in df.iterrows()
    ]
    execute_values(
        cur,
        """
        INSERT INTO top_inst(code, trade_date, exalter, buy, buy_rate, sell, sell_rate, net_buy)
        VALUES %s
        """,
        rows,
        page_size=1000,
    )
    return len(rows)


def fetch_api(pro, api: str, trade_date: str):
    if api == "limit_list_d":
        return None
    return getattr(pro, api)(trade_date=trade_date)


def backfill_day(conn, pro, trade_date: str, apis: Iterable[str], dry_run: bool) -> dict[str, dict]:
    cur = conn.cursor()
    result: dict[str, dict] = {}
    for api in apis:
        try:
            if api == "limit_list_d":
                if not dry_run:
                    delete_date(cur, "limit_list_d", trade_date)
                fetched, written = insert_limit_list_d(cur, pro, trade_date) if not dry_run else (0, 0)
            else:
                table = RAW_TABLES.get(api, api)
                if not dry_run:
                    delete_date(cur, table, trade_date, raw_api=api if api in RAW_TABLES else None)
                df = fetch_api(pro, api, trade_date)
                fetched = 0 if df is None else len(df)
                if dry_run:
                    written = 0
                elif api in RAW_TABLES:
                    written = insert_raw(cur, api, df)
                elif api == "stk_limit":
                    written = insert_stk_limit(cur, df, trade_date)
                elif api == "top_list":
                    written = insert_top_list(cur, df, trade_date)
                elif api == "top_inst":
                    written = insert_top_inst(cur, df, trade_date)
                else:
                    raise ValueError(f"Unsupported api: {api}")
            result[api] = {"status": "ok", "fetched": fetched, "written": written}
            conn.commit()
        except Exception as exc:
            conn.rollback()
            result[api] = {"status": "error", "error": str(exc)[:200], "fetched": 0, "written": 0}
        time.sleep(args.sleep)
    cur.close()
    return result


if __name__ == "__main__":
    args = parse_args()
    end = args.end
    start = args.start or (datetime.strptime(end, "%Y-%m-%d").date() - timedelta(days=args.years * 366)).isoformat()
    apis = [a.strip() for a in args.apis.split(",") if a.strip()]
    unsupported = sorted(set(apis) - set(DEFAULT_APIS))
    if unsupported:
        raise SystemExit(f"Unsupported APIs: {unsupported}")

    pro = init_tushare()
    conn = psycopg2.connect(pg_url())
    dates = get_trade_dates(conn, start, end)
    if args.max_days:
        dates = dates[-args.max_days :]
    print(f"Backfill dates={len(dates)} start={start} end={end} apis={','.join(apis)} dry_run={args.dry_run}")
    totals = {api: {"fetched": 0, "written": 0, "errors": 0} for api in apis}
    for idx, td in enumerate(dates, 1):
        result = backfill_day(conn, pro, td, apis, args.dry_run)
        for api, item in result.items():
            totals[api]["fetched"] += int(item.get("fetched") or 0)
            totals[api]["written"] += int(item.get("written") or 0)
            if item.get("status") != "ok":
                totals[api]["errors"] += 1
        if idx == 1 or idx % 20 == 0 or idx == len(dates):
            print(f"{idx}/{len(dates)} {td} {json.dumps(result, ensure_ascii=False)}", flush=True)
    conn.close()
    print("TOTALS", json.dumps(totals, ensure_ascii=False, indent=2))
