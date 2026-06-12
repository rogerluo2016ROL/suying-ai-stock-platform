#!/usr/bin/env python3
"""同步 THS/SW 板块指数数据到 PostgreSQL.

修复 ths_daily (空表) + sw_daily (缺6/9后数据) + 创建 ths_index 映射表.
"""
import os, sys, time
import psycopg2
import tushare as ts
import numpy as np

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

if not TOKEN:
    print("❌ TUSHARE_TOKEN 未设置")
    sys.exit(1)

ts.set_token(TOKEN)
pro = ts.pro_api()
conn = psycopg2.connect(PG_URL)

def sync_ths_index():
    """同步同花顺概念指数列表 → ths_index 表."""
    cur = conn.cursor()

    # Create table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ths_index (
            ts_code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            count INTEGER,
            exchange TEXT,
            list_date TEXT,
            type TEXT
        )
    """)

    print("📥 获取 ths_index ...", end=" ", flush=True)
    df = pro.ths_index()
    if df is None or len(df) == 0:
        print("❌ 无数据")
        return 0

    written = 0
    for _, r in df.iterrows():
        try:
            cur.execute(
                "INSERT INTO ths_index (ts_code, name, count, exchange, list_date, type) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (ts_code) DO UPDATE SET name=EXCLUDED.name",
                (r.get("ts_code",""), r.get("name",""), r.get("count",0),
                 r.get("exchange",""), r.get("list_date",""), r.get("type",""))
            )
            written += 1
        except Exception:
            pass

    conn.commit()
    print(f"✅ {written} 条")
    return written


def sync_ths_daily(trade_date: str):
    """同步单日 ths_daily 数据 (带 name 映射)."""
    cur = conn.cursor()
    tushare_date = trade_date.replace("-", "")

    print(f"  📥 ths_daily {trade_date} ...", end=" ", flush=True)
    try:
        df = pro.ths_daily(trade_date=tushare_date)
    except Exception as e:
        print(f"API错误: {e}")
        return 0
    if df is None or len(df) == 0:
        print("0 rows")
        return 0

    written = 0
    for _, r in df.iterrows():
        ts_code = r.get("ts_code", "")
        if not ts_code:
            continue

        # Get name from index mapping or ths_index cache
        name = ""
        try:
            cur.execute("SELECT name FROM ths_index WHERE ts_code=%s", (ts_code,))
            nr = cur.fetchone()
            if nr:
                name = nr[0]
        except Exception:
            pass

        try:
            cur.execute(
                "INSERT INTO ths_daily (trade_date, code, name, open, high, low, close, "
                "pre_close, avg_price, change_pct, change, total_mv, float_mv) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (trade_date, ts_code, name,
                 float(r.get("open",0) or 0), float(r.get("high",0) or 0),
                 float(r.get("low",0) or 0), float(r.get("close",0) or 0),
                 float(r.get("pre_close",0) or 0), float(r.get("avg_price",0) or 0),
                 float(r.get("pct_change",0) or 0), float(r.get("change",0) or 0),
                 float(r.get("vol",0) or 0) / 1e8,  # 总市值 (approximate)
                 float(r.get("turnover_rate",0) or 0))
            )
            written += 1
        except Exception as e:
            pass

    conn.commit()
    print(f"{written} rows")
    return written


def sync_sw_daily(trade_date: str):
    """同步单日 sw_daily 数据."""
    cur = conn.cursor()

    print(f"  📥 sw_daily {trade_date} ...", end=" ", flush=True)
    df = pro.sw_daily(trade_date=trade_date)
    if df is None or len(df) == 0:
        print("0 rows")
        return 0

    written = 0
    for _, r in df.iterrows():
        try:
            cur.execute(
                "INSERT INTO sw_daily (code, trade_date, pct_chg, open, high, low, close, "
                "vol, amount) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING",
                (r.get("ts_code",""), trade_date,
                 float(r.get("pct_change",0) or 0),
                 float(r.get("open",0) or 0), float(r.get("high",0) or 0),
                 float(r.get("low",0) or 0), float(r.get("close",0) or 0),
                 float(r.get("vol",0) or 0), float(r.get("amount",0) or 0))
            )
            written += 1
        except Exception:
            pass

    conn.commit()
    print(f"{written} rows")
    return written


def get_missing_dates(table: str, month: str = "2026-06") -> list:
    """获取指定月份中指定表缺失数据的日期."""
    cur = conn.cursor()

    # Get all trading days in the month
    try:
        cur.execute(
            "SELECT DISTINCT trade_date FROM daily_kline "
            "WHERE trade_date >= %s AND trade_date < %s ORDER BY trade_date",
            (f"{month}-01", f"{month}-30")
        )
        all_dates = [r[0] for r in cur.fetchall()]
    except Exception:
        # Fallback: use index_daily
        cur.execute(
            "SELECT DISTINCT trade_date FROM index_daily "
            "WHERE trade_date >= %s AND trade_date < %s ORDER BY trade_date",
            (f"{month}-01", f"{month}-30")
        )
        all_dates = [r[0] for r in cur.fetchall()]

    # Get existing dates
    if table == "ths_daily":
        cur.execute(
            "SELECT DISTINCT trade_date FROM ths_daily "
            "WHERE trade_date >= %s AND trade_date < %s",
            (f"{month}-01", f"{month}-30")
        )
    else:
        cur.execute(
            "SELECT DISTINCT trade_date FROM sw_daily "
            "WHERE trade_date >= %s AND trade_date < %s",
            (f"{month}-01", f"{month}-30")
        )
    existing = {str(r[0]) for r in cur.fetchall()}

    return [str(d) for d in all_dates if str(d) not in existing]


# ── Main ──
print("=" * 60)
print("  板块指数数据同步")
print("=" * 60)

# 1. Sync ths_index (concept code → name mapping)
print("\n1️⃣ 同步 ths_index (概念指数列表)")
sync_ths_index()

# 2. Sync ths_daily for missing June dates
print("\n2️⃣ 同步 ths_daily (概念板块行情)")
missing_ths = get_missing_dates("ths_daily")
print(f"  缺失日期: {len(missing_ths)} 天 → {missing_ths[:5]}...")
for td in missing_ths:
    sync_ths_daily(str(td))
    time.sleep(0.3)  # rate limit

# 3. Sync sw_daily for missing June dates
print("\n3️⃣ 同步 sw_daily (申万行业行情)")
missing_sw = get_missing_dates("sw_daily")
print(f"  缺失日期: {len(missing_sw)} 天 → {missing_sw[:5]}...")
for td in missing_sw:
    sync_sw_daily(str(td))
    time.sleep(0.3)

# 4. Verify
cur = conn.cursor()
cur.execute("SELECT COUNT(*), COUNT(DISTINCT trade_date) FROM ths_daily")
ths_c = cur.fetchone()
cur.execute("SELECT COUNT(*), COUNT(DISTINCT trade_date) FROM sw_daily")
sw_c = cur.fetchone()
print(f"\n{'=' * 60}")
print(f"  ✅ ths_daily: {ths_c[0]} rows, {ths_c[1]} dates")
print(f"  ✅ sw_daily: {sw_c[0]} rows, {sw_c[1]} dates")

# 5. Show sample concept names
cur.execute("SELECT DISTINCT name FROM ths_daily WHERE name != '' LIMIT 10")
samples = cur.fetchall()
print(f"\n  THS 概念样例: {[r[0] for r in samples]}")

conn.close()
print("\n🎉 同步完成!")
