#!/usr/bin/env python3
"""SQLite → PostgreSQL 数据迁移工具

用法:
    # 1. 先创建 PG 表结构
    psql -U kronos -d kronos -f services/sql/init_postgres.sql

    # 2. 迁移数据
    python services/sql/migrate_data.py \
        --sqlite Kronos/data/kronos.db \
        --pg postgresql://kronos:kronos@localhost:5432/kronos

    # 3. 只迁移特定表
    python services/sql/migrate_data.py --tables stocks,daily_kline
"""

import argparse
import sqlite3
import sys
import os
from datetime import datetime

# 48 张表，按依赖顺序排列 (先迁移被引用的表)
TABLE_ORDER = [
    # 基础信息 (无外键依赖)
    "stocks", "stock_profiles", "index_basic", "watchlist",
    # 行情数据
    "daily_kline", "weekly_kline", "monthly_kline",
    "adj_factor", "daily_basic", "stk_limit",
    "index_daily", "sw_daily", "rt_sw_k",
    # 资金面
    "moneyflow", "moneyflow_hsgt", "hk_holdings",
    "margin_detail", "margin_summary", "top_list", "top_inst",
    "block_trade_data",
    # 基本面
    "financial_income", "financial_balance", "financial_cashflow",
    "financial_indicator", "financial_abstracts",
    "forecast_data", "profit_forecasts", "dividend_data",
    "fina_mainbz",
    # 机构与股东
    "stk_holdertrade", "stk_holdernumber", "share_float",
    "pledge_detail", "repurchase", "cyq_chips",
    # 研究与新闻
    "research_reports", "research_reports_tushare",
    "stock_news", "stock_news_tushare",
    "broker_recommend", "announcements",
    # 应用层
    "screening_scores", "screening_batches",
    "predictions", "prediction_versions", "prediction_details",
    "backtest_records",
]


def migrate_table(sqlite_conn, pg_conn, table: str, batch_size: int = 5000) -> dict:
    """Migrate a single table from SQLite to PostgreSQL."""
    import psycopg2
    import psycopg2.extras

    # Read PG columns (only migrate columns that exist in both)
    pg_cur = pg_conn.cursor()
    pg_cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
    pg_cols = {r[0] for r in pg_cur.fetchall()}

    # Read from SQLite
    cur = sqlite_conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    total = cur.fetchone()[0]
    if total == 0:
        return {"table": table, "rows": 0, "status": "empty"}

    cur.execute(f"SELECT * FROM {table}")
    all_columns = [desc[0] for desc in cur.description]
    # Only keep columns that exist in PG
    columns = [c for c in all_columns if c in pg_cols]
    skipped_cols = [c for c in all_columns if c not in pg_cols]
    if skipped_cols:
        print(f"  {table}: skipping columns {skipped_cols}")

    col_names = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    written = 0
    batch = []
    col_indices = [all_columns.index(c) for c in columns]
    for row in cur:
        # Clean null bytes and extract only matching columns
        clean_row = tuple(
            (row[i].replace('\x00', '').replace('\0', '') if isinstance(row[i], str) else row[i])
            for i in col_indices
        )
        batch.append(clean_row)
        if len(batch) >= batch_size:
            psycopg2.extras.execute_batch(pg_cur, insert_sql, batch)
            pg_conn.commit()
            written += len(batch)
            print(f"  {table}: {written}/{total}")
            batch = []

    if batch:
        psycopg2.extras.execute_batch(pg_cur, insert_sql, batch)
        pg_conn.commit()
        written += len(batch)

    return {"table": table, "rows": written, "total": total, "status": "ok"}


def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 数据迁移")
    parser.add_argument("--sqlite", required=True, help="SQLite 数据库路径")
    parser.add_argument("--pg", default="postgresql://kronos:kronos@localhost:5432/kronos",
                        help="PostgreSQL 连接字符串")
    parser.add_argument("--tables", help="要迁移的表 (逗号分隔), 默认全部 48 张")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()

    if not os.path.exists(args.sqlite):
        print(f"❌ SQLite 文件不存在: {args.sqlite}")
        sys.exit(1)

    tables = args.tables.split(",") if args.tables else TABLE_ORDER

    # Connect
    print(f"📂 SQLite: {args.sqlite}")
    sqlite_conn = sqlite3.connect(args.sqlite)
    sqlite_conn.row_factory = sqlite3.Row

    print(f"🐘 PostgreSQL: {args.pg}")
    try:
        import psycopg2
        pg_conn = psycopg2.connect(args.pg)
    except ImportError:
        print("❌ 需要安装 psycopg2: pip install psycopg2-binary")
        sys.exit(1)
    except Exception as e:
        print(f"❌ PostgreSQL 连接失败: {e}")
        sys.exit(1)

    # Migrate
    t0 = datetime.now()
    results = []
    for table in tables:
        if table not in TABLE_ORDER:
            print(f"  ⚠️ 未知表 {table}, 跳过")
            continue
        try:
            r = migrate_table(sqlite_conn, pg_conn, table, args.batch_size)
            results.append(r)
        except Exception as e:
            print(f"  ❌ {table} 迁移失败: {e}")
            results.append({"table": table, "rows": 0, "status": f"error: {e}"})

    # Summary
    elapsed = (datetime.now() - t0).total_seconds()
    total_rows = sum(r["rows"] for r in results)
    ok_tables = sum(1 for r in results if r["status"] == "ok")
    print(f"\n✅ 迁移完成: {ok_tables}/{len(results)} 表, "
          f"{total_rows} 行, 耗时 {elapsed:.1f}s")

    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
