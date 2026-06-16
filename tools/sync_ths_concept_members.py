#!/usr/bin/env python3
"""同步同花顺88xxxx概念成分股到 ths_member 表.

Usage:
    TUSHARE_TOKEN="your_token" KRONOS_PG_URL="postgresql://..." python3 tools/sync_ths_concept_members.py
"""
import os, time, psycopg2, tushare as ts

TOKEN = os.environ.get("TUSHARE_TOKEN", "")
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

if not TOKEN:
    print("请设置 TUSHARE_TOKEN 环境变量")
    exit(1)

pro = ts.pro_api(TOKEN)
conn = psycopg2.connect(PG_URL)
cur = conn.cursor()

# 获取所有88xxxx概念板块
cur.execute("""
    SELECT ts_code, name FROM ths_index
    WHERE LEFT(ts_code, 3) IN ('881','882','883','884','885','886')
    ORDER BY ts_code
""")
concepts = cur.fetchall()
print(f"概念板块: {len(concepts)}")

total, errors, empty = 0, 0, 0
t0 = time.time()

for i, (ts_code, name) in enumerate(concepts):
    try:
        df = pro.ths_member(ts_code=ts_code)
        if df is None or df.empty:
            empty += 1
            continue

        for _, row in df.iterrows():
            cur.execute(
                "INSERT INTO ths_member (ts_code, con_code, con_name) VALUES (%s, %s, %s) ON CONFLICT (ts_code, con_code) DO NOTHING",
                (ts_code, row["con_code"], row.get("con_name", "")),
            )
            total += 1

        if total % 5000 < len(df):
            conn.commit()

        if (i + 1) % 100 == 0:
            elapsed = time.time() - t0
            cur.execute("SELECT COUNT(*) FROM ths_member WHERE LEFT(ts_code,3) IN ('881','882','883','884','885','886')")
            print(f"  {i+1}/{len(concepts)} 概念, {total}条, DB:{cur.fetchone()[0]}条, {elapsed:.0f}s")

    except Exception as e:
        errors += 1
        conn.rollback()
        if errors <= 5:
            print(f"  {ts_code} {name}: {e}")

conn.commit()
elapsed = time.time() - t0

cur.execute("SELECT COUNT(DISTINCT ts_code), COUNT(*) FROM ths_member WHERE LEFT(ts_code,3) IN ('881','882','883','884','885','886')")
r = cur.fetchone()
print(f"\n完成: {r[0]} 概念 ({empty} 空), {r[1]} 行, {errors} 错误, {elapsed:.0f}s")
conn.close()
