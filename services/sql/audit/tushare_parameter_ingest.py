#!/usr/bin/env python3
"""按真实参数采集 Tushare 参数型接口的 raw 数据。

该脚本不使用空参数。代码池来自已落地业务表或 raw basic 表，使用 --limit
控制单次批次，便于按配额和调度窗口持续增量执行。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PG_DEFAULT = "postgresql://kronos:kronos@localhost:6432/kronos"
BULK_PATH = Path(__file__).with_name("tushare_bulk_ingest.py")


def load_bulk():
    spec = importlib.util.spec_from_file_location("tushare_bulk_ingest", BULK_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PARAM_SOURCES = {
    "cb_price_chg": ("cb_basic", "ts_code"),
    "fina_audit": ("stocks", "code"),
    "fina_mainbz": ("stocks", "code"),
    "ft_mins": ("stocks", "code"),
    "hk_balancesheet": ("ts_raw_hk_basic", "ts_code"),
    "hk_cashflow": ("ts_raw_hk_basic", "ts_code"),
    "hk_fina_indicator": ("ts_raw_hk_basic", "ts_code"),
    "hk_income": ("ts_raw_hk_basic", "ts_code"),
    "hk_mins": ("ts_raw_hk_basic", "ts_code"),
    "rt_fut_min": ("ts_raw_fut_basic", "ts_code"),
    "fut_weekly_monthly": ("ts_raw_fut_basic", "ts_code"),
    "rt_hk_k": ("ts_raw_hk_basic", "ts_code"),
    "idx_mins": ("index_basic", "code"),
    "rt_idx_k": ("index_basic", "code"),
    "rt_idx_min": ("index_basic", "code"),
    "idx_mins": ("index_basic", "code"),
    "opt_mins": ("ts_raw_opt_basic", "ts_code"),
    "rt_etf_k": ("ts_raw_etf_basic", "ts_code"),
    "us_balancesheet": ("ts_raw_us_basic", "ts_code"),
    "us_cashflow": ("ts_raw_us_basic", "ts_code"),
    "us_income": ("ts_raw_us_basic", "ts_code"),
    "stk_rewards": ("stocks", "code"),
    "rt_k": ("stocks", "code"),
    "rt_min": ("stocks", "code"),
    "stk_week_month_adj": ("stocks", "code"),
    "stk_weekly_monthly": ("stocks", "code"),
}


def to_ts_code(code: str) -> str:
    code = str(code)
    if "." in code:
        return code
    if code and code[0].isalpha():
        return code
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    if code.startswith(("8", "4", "9")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def get_codes(conn, table: str, column: str, limit: int) -> list[str]:
    cur = conn.cursor()
    cur.execute(
        f"SELECT DISTINCT {column} FROM {table} "
        f"WHERE {column} IS NOT NULL AND {column} <> '' ORDER BY {column} LIMIT %s",
        (limit,),
    )
    return [str(row[0]) for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", nargs="+", required=True)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--freq", default="1min")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", PG_DEFAULT))
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    import psycopg2
    import tushare as ts

    bulk = load_bulk()
    catalog_path = Path(__file__).with_name("tushare_data_catalog.py")
    spec = importlib.util.spec_from_file_location("tushare_data_catalog", catalog_path)
    catalog = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = catalog
    spec.loader.exec_module(catalog)
    _, refs, _ = catalog.build_catalog(pg_url=args.pg_url)

    ts.set_token(os.environ.get("TUSHARE_TOKEN", ""))
    pro = ts.pro_api(timeout=args.timeout)
    conn = psycopg2.connect(args.pg_url, connect_timeout=10)
    bulk.ensure_control_table(conn)

    for api in args.api:
        if api not in refs:
            print(f"{api}: not in reference catalog")
            continue
        ref = refs[api]
        params_list: list[dict[str, str]] = []
        source = PARAM_SOURCES.get(api)
        if source:
            table, column = source
            codes = get_codes(conn, table, column, args.limit)
            params_list = [{"ts_code": to_ts_code(code)} for code in codes]
            if api in {"ft_mins", "fut_weekly_monthly", "hk_mins", "idx_mins", "opt_mins", "rt_fut_min",
                       "rt_idx_min", "rt_min", "rt_k", "stk_week_month_adj",
                       "stk_weekly_monthly"}:
                for params in params_list:
                    if api in {"fut_weekly_monthly", "stk_week_month_adj", "stk_weekly_monthly"}:
                        params["freq"] = "week"
                    elif api in {"rt_fut_min", "rt_min"}:
                        params["freq"] = args.freq.upper()
                    else:
                        params["freq"] = args.freq
        elif api in {"fut_weekly_monthly", "stk_week_month_adj", "stk_weekly_monthly"}:
            params_list = [{"freq": "W"}]
        elif api in {"rt_fut_min", "rt_min"}:
            freq = "week" if api in {"fut_weekly_monthly", "stk_week_month_adj", "stk_weekly_monthly"} else args.freq.upper()
            params_list = [{"freq": freq}]
        elif api == "fund_nav":
            params_list = [{"nav_date": "20260710"}]
        else:
            print(f"{api}: no parameter source configured")
            continue

        fetched = inserted = 0
        last_error = ""
        for params in params_list:
            try:
                df = bulk.fetch_dataframe(pro, api, params)
                records = bulk.dataframe_to_records(df)
                normalized = bulk.normalize_records(api, records)
                fetched += len(normalized)
                inserted += bulk.insert_records(conn, bulk.raw_table_name(api), normalized)
            except Exception as exc:  # record the API-level evidence and continue the batch
                last_error = str(exc)
        status = "collected" if fetched else (bulk.classify_error(Exception(last_error)) if last_error else "no_data")
        result = bulk.ApiIngestResult(
            api=api,
            title=ref.title,
            category=ref.category,
            table_name=bulk.raw_table_name(api),
            status=status,
            rows_fetched=fetched,
            rows_inserted=inserted,
            windows_attempted=len(params_list),
            columns=(),
            error=last_error,
        )
        bulk.upsert_status(conn, result)
        print(f"{api}: {result.status}, fetched={fetched}, inserted={inserted}", flush=True)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
