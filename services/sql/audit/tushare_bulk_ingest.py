#!/usr/bin/env python3
"""Bulk ingest every uncovered Tushare API into raw PostgreSQL tables.

This is intentionally a raw landing layer:
- one table per API: ts_raw_<api>
- columns are discovered from the real Tushare response
- values are stored as TEXT to avoid guessing field types
- _row_hash is the primary key for idempotent reruns
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
DEFAULT_STATUS_TABLE = "tushare_api_ingest_status"
DEFAULT_REPORT = ROOT / "docs/data-governance/tushare-bulk-ingest-current.md"
RAW_METADATA_COLUMNS = (
    "_tushare_update_time",
    "_tushare_update_frequency",
    "_tushare_doc_url",
    "_tushare_metadata_updated_at",
)


@dataclass(frozen=True)
class ApiIngestResult:
    api: str
    title: str
    category: str
    table_name: str
    status: str
    rows_fetched: int
    rows_inserted: int
    windows_attempted: int
    columns: tuple[str, ...]
    error: str = ""


def raw_table_name(api_name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", api_name.strip()).strip("_").lower()
    if not safe:
        safe = "unknown"
    if safe[0].isdigit():
        safe = f"api_{safe}"
    return f"ts_raw_{safe}"


def safe_column_name(column: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_]+", "_", str(column).strip()).strip("_").lower()
    if not safe:
        safe = "field"
    if safe[0].isdigit():
        safe = f"field_{safe}"
    if safe in {"select", "from", "where", "table", "group", "order", "limit"}:
        safe = f"{safe}_field"
    return safe


def pg_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def build_date_windows(end_date: str | None = None, years: int = 10) -> list[tuple[str, str]]:
    end = datetime.strptime(end_date, "%Y%m%d").date() if end_date else date.today()
    start = end - timedelta(days=365 * years)
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        year_end = min(date(cursor.year, 12, 31), end)
        windows.append((cursor.strftime("%Y%m%d"), year_end.strftime("%Y%m%d")))
        cursor = year_end + timedelta(days=1)
    return windows


def request_attempts_for_window(api: str, start_date: str, end_date: str) -> list[dict[str, str]]:
    return [
        {"start_date": start_date, "end_date": end_date},
        {"trade_date": end_date},
        {"end_date": end_date},
        {"ann_date": end_date},
        {},
    ]


def row_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_records(api: str, records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for source in records:
        base: dict[str, str] = {}
        for key, value in source.items():
            if value is None:
                base[str(key)] = ""
            elif isinstance(value, float) and str(value) == "nan":
                base[str(key)] = ""
            else:
                base[str(key)] = str(value)
        hashed = row_hash(base)
        base["_source_api"] = api
        base["_row_hash"] = hashed
        normalized.append(base)
    return normalized


def ensure_control_table(conn, status_table: str = DEFAULT_STATUS_TABLE) -> None:
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {pg_ident(status_table)} (
            api TEXT PRIMARY KEY,
            title TEXT,
            category TEXT,
            table_name TEXT NOT NULL,
            status TEXT NOT NULL,
            rows_fetched BIGINT NOT NULL DEFAULT 0,
            rows_inserted BIGINT NOT NULL DEFAULT 0,
            windows_attempted INTEGER NOT NULL DEFAULT 0,
            columns JSONB NOT NULL DEFAULT '[]'::jsonb,
            update_time TEXT,
            update_frequency TEXT,
            doc_url TEXT,
            update_metadata_status TEXT,
            error TEXT,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.commit()


def upsert_status(conn, result: ApiIngestResult, status_table: str = DEFAULT_STATUS_TABLE) -> None:
    cur = conn.cursor()
    cur.execute(
        f"""
        INSERT INTO {pg_ident(status_table)} (
            api, title, category, table_name, status, rows_fetched, rows_inserted,
            windows_attempted, columns, error, started_at, finished_at, updated_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,NOW(),NOW(),NOW())
        ON CONFLICT (api) DO UPDATE SET
            title=EXCLUDED.title,
            category=EXCLUDED.category,
            table_name=EXCLUDED.table_name,
            status=EXCLUDED.status,
            rows_fetched=EXCLUDED.rows_fetched,
            rows_inserted=EXCLUDED.rows_inserted,
            windows_attempted=EXCLUDED.windows_attempted,
            columns=EXCLUDED.columns,
            error=EXCLUDED.error,
            finished_at=EXCLUDED.finished_at,
            updated_at=NOW()
        """,
        (
            result.api,
            result.title,
            result.category,
            result.table_name,
            result.status,
            result.rows_fetched,
            result.rows_inserted,
            result.windows_attempted,
            json.dumps(list(result.columns), ensure_ascii=False),
            result.error[:2000] if result.error else None,
        ),
    )
    conn.commit()


def ensure_raw_table(conn, table_name: str, columns: Iterable[str]) -> tuple[str, ...]:
    data_columns = tuple(dict.fromkeys(safe_column_name(c) for c in columns if not str(c).startswith("_")))
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {pg_ident(table_name)} (
            _row_hash TEXT PRIMARY KEY,
            _source_api TEXT NOT NULL,
            _ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            _tushare_update_time TEXT,
            _tushare_update_frequency TEXT,
            _tushare_doc_url TEXT,
            _tushare_metadata_updated_at TIMESTAMPTZ
        )
        """
    )
    for column in data_columns:
        cur.execute(f"ALTER TABLE {pg_ident(table_name)} ADD COLUMN IF NOT EXISTS {pg_ident(column)} TEXT")
    conn.commit()
    return data_columns


def insert_records(conn, table_name: str, records: list[dict[str, str]]) -> int:
    if not records:
        return 0
    import psycopg2.extras

    columns = ["_row_hash", "_source_api"] + sorted(
        {safe_column_name(k) for record in records for k in record if not k.startswith("_")}
    )
    ensure_raw_table(conn, table_name, columns)
    rows = []
    for record in records:
        row = []
        for column in columns:
            if column == "_row_hash":
                row.append(record["_row_hash"])
            elif column == "_source_api":
                row.append(record["_source_api"])
            else:
                row.append(record.get(column) or record.get(_original_key_for_safe_column(record, column)) or None)
        rows.append(tuple(row))

    cur = conn.cursor()
    col_sql = ", ".join(pg_ident(c) for c in columns)
    sql = (
        f"INSERT INTO {pg_ident(table_name)} ({col_sql}) VALUES %s "
        "ON CONFLICT (_row_hash) DO NOTHING RETURNING 1"
    )
    inserted = psycopg2.extras.execute_values(cur, sql, rows, page_size=1000, fetch=True)
    written = len(inserted)
    conn.commit()
    return written


def classify_error(exc: Exception) -> str:
    text = str(exc)
    lower = text.lower()
    if "请指定正确的接口名" in text:
        return "unsupported_api"
    if any(token in text for token in ("必填参数", "参数校验失败", "至少填写", "至少输入")):
        return "requires_params"
    if any(token in lower for token in ("permission", "access", "积分", "权限", "抱歉")):
        return "no_permission"
    if any(token in lower for token in ("timeout", "timed out", "connection")):
        return "failed"
    return "failed"


def fetch_dataframe(pro: Any, api: str, params: dict[str, str]):
    if hasattr(pro, "query"):
        try:
            return pro.query(api, **params)
        except Exception as exc:  # noqa: BLE001 - SDK method fallback below records final error
            if "请指定正确的接口名" not in str(exc) or not hasattr(pro, api):
                raise
    method = getattr(pro, api)
    return method(**params)


def dataframe_to_records(df: Any) -> list[dict[str, Any]]:
    if df is None:
        return []
    if hasattr(df, "empty") and df.empty:
        return []
    if hasattr(df, "to_dict"):
        return list(df.to_dict(orient="records"))
    return []


def collect_one_api(
    conn,
    pro: Any,
    api_ref: Any,
    years: int,
    end_date: str,
    sleep_seconds: float = 0.25,
    max_windows: int | None = None,
) -> ApiIngestResult:
    api = api_ref.name
    table_name = raw_table_name(api)
    ensure_raw_table(conn, table_name, ())
    rows_fetched = 0
    rows_inserted = 0
    windows_attempted = 0
    discovered_columns: set[str] = set()
    last_error = ""
    no_param_attempted = False

    for start, end in build_date_windows(end_date=end_date, years=years):
        if max_windows is not None and windows_attempted >= max_windows:
            break
        fetched_this_window = False
        for params in request_attempts_for_window(api, start, end):
            if not params and no_param_attempted:
                continue
            if not params:
                no_param_attempted = True
            try:
                df = fetch_dataframe(pro, api, params)
                windows_attempted += 1
                records = dataframe_to_records(df)
                if not records:
                    fetched_this_window = True
                    break
                normalized = normalize_records(api, records)
                for record in normalized:
                    discovered_columns.update(k for k in record if not k.startswith("_"))
                rows_fetched += len(normalized)
                rows_inserted += insert_records(conn, table_name, normalized)
                fetched_this_window = True
                time.sleep(sleep_seconds)
                break
            except Exception as exc:  # noqa: BLE001 - record per-API failure reason
                last_error = str(exc)
                status = classify_error(exc)
                if status == "no_permission":
                    result = ApiIngestResult(
                        api=api,
                        title=api_ref.title,
                        category=api_ref.category,
                        table_name=table_name,
                        status=status,
                        rows_fetched=rows_fetched,
                        rows_inserted=rows_inserted,
                        windows_attempted=windows_attempted,
                        columns=tuple(sorted(discovered_columns)),
                        error=last_error,
                    )
                    upsert_status(conn, result)
                    return result
                continue
        if not fetched_this_window and last_error:
            break

    if rows_fetched > 0:
        status = "collected"
    elif no_param_attempted and not last_error:
        status = "no_data"
    elif last_error:
        status = classify_error(Exception(last_error))
    else:
        status = "no_data"
    result = ApiIngestResult(
        api=api,
        title=api_ref.title,
        category=api_ref.category,
        table_name=table_name,
        status=status,
        rows_fetched=rows_fetched,
        rows_inserted=rows_inserted,
        windows_attempted=windows_attempted,
        columns=tuple(sorted(discovered_columns)),
        error=last_error,
    )
    upsert_status(conn, result)
    return result


def render_report(results: list[ApiIngestResult], output: Path = DEFAULT_REPORT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Tushare 批量接入结果",
        "",
        f"> 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 汇总",
        "",
    ]
    by_status: dict[str, int] = {}
    for result in results:
        by_status[result.status] = by_status.get(result.status, 0) + 1
    lines.extend(f"- {status}: {count}" for status, count in sorted(by_status.items()))
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| API | 标题 | 分类 | 表 | 状态 | 拉取行数 | 入库行数 | 字段数 | 错误 |",
            "|---|---|---|---|---|---:|---:|---:|---|",
        ]
    )
    for result in results:
        error = result.error.replace("\n", " ")[:180] if result.error else ""
        lines.append(
            f"| {result.api} | {result.title} | {result.category} | {result.table_name} | "
            f"{result.status} | {result.rows_fetched} | {result.rows_inserted} | {len(result.columns)} | {error} |"
        )
    output.write_text("\n".join(lines) + "\n", "utf-8")


def load_uncovered_api_refs(pg_url: str) -> list[Any]:
    catalog_path = Path(__file__).with_name("tushare_data_catalog.py")
    spec = importlib.util.spec_from_file_location("tushare_data_catalog", catalog_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _rows, _reference_apis, uncovered = module.build_catalog(pg_url=pg_url)
    return uncovered


def create_pro_client():
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is missing")
    ts.set_token(token)
    return ts.pro_api()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bulk ingest uncovered Tushare APIs into raw PG tables")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    parser.add_argument("--years", type=int, default=10)
    parser.add_argument("--end-date", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--max-apis", type=int, default=None)
    parser.add_argument("--max-windows", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.25)
    parser.add_argument("--only", nargs="*", default=None, help="Only ingest these API names")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    import psycopg2

    refs = load_uncovered_api_refs(args.pg_url)
    if args.only:
        wanted = set(args.only)
        refs = [ref for ref in refs if ref.name in wanted]
    if args.max_apis is not None:
        refs = refs[: args.max_apis]

    conn = psycopg2.connect(args.pg_url, connect_timeout=10)
    ensure_control_table(conn)
    pro = create_pro_client()
    results: list[ApiIngestResult] = []
    for index, ref in enumerate(refs, 1):
        print(f"[{index}/{len(refs)}] ingest {ref.name} -> {raw_table_name(ref.name)}", flush=True)
        result = collect_one_api(
            conn,
            pro,
            ref,
            years=args.years,
            end_date=args.end_date,
            sleep_seconds=args.sleep_seconds,
            max_windows=args.max_windows,
        )
        print(
            f"  {result.status}: fetched={result.rows_fetched} inserted={result.rows_inserted} "
            f"cols={len(result.columns)}",
            flush=True,
        )
        results.append(result)
    conn.close()
    render_report(results, args.report)
    print(f"OK {args.report} | apis={len(results)}")
    return 0


def _original_key_for_safe_column(record: dict[str, str], safe_column: str) -> str:
    for key in record:
        if safe_column_name(key) == safe_column:
            return key
    return safe_column


if __name__ == "__main__":
    raise SystemExit(main())
