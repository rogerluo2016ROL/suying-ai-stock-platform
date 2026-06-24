#!/usr/bin/env python3
"""BOM 路径2 — 数据缓存: 拉 36 只公司全期财务/预告/问答/研报, 落本地 parquet/csv.

cutoff-aware 评分需要逐 cutoff 切片 (ann_date<=cutoff), 逐 cutoff 实时拉 Tushare 太慢.
本脚本一次拉全期 (2024-01~2026-06), 落本地, 路径2 评分脚本读本地切片.

拉取: fina_indicator (财务) + forecast (预告) + irm_qa (问答) + research_report (研报)
      + fina_mainbz_vip type=P (主营产品, 静态, 一次即可)

Usage:
    TUSHARE_TOKEN=xxx python tools/bom_oos_cache.py
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts

PROJ = Path("/Users/rogerluo/程序目录/K线大模型")
CACHE = PROJ / "outputs" / "bom_oos_cache"
CACHE.mkdir(parents=True, exist_ok=True)

START, END = "20240101", "20260615"


def load_36():
    import psycopg2
    conn = psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    cur = conn.cursor()
    cur.execute("SELECT code FROM company_bom_mapping ORDER BY code")
    codes = [r[0] for r in cur.fetchall()]
    conn.close()
    def to_ts(c):
        if c.startswith(("6", "5")): return c + ".SH"
        if c.startswith(("0", "3")): return c + ".SZ"
        return c + ".BJ"
    return [(c, to_ts(c)) for c in codes]


def main():
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("❌ TUSHARE_TOKEN 未设置"); sys.exit(1)
    ts.set_token(token)
    pro = ts.pro_api()

    codes = load_36()
    print(f"拉取 {len(codes)} 只公司全期数据 ({START}~{END}) → {CACHE}")

    fina_all, fc_all, qa_all, rr_all, mb_all = [], [], [], [], []
    for i, (code6, ts_code) in enumerate(codes):
        print(f"  [{i+1}/{len(codes)}] {ts_code}", end=" ", flush=True)
        # 财务
        try:
            df = pro.fina_indicator(ts_code=ts_code, start_date=START, end_date=END)
            if df is not None and len(df):
                df["code6"] = code6; fina_all.append(df)
        except Exception as e:
            print(f"fina_err:{str(e)[:30]}", end=" ")
        # 预告
        try:
            df = pro.forecast(ts_code=ts_code, start_date=START, end_date=END)
            if df is not None and len(df):
                df["code6"] = code6; fc_all.append(df)
        except Exception: pass
        # 互动问答
        api = "irm_qa_sh" if ts_code.endswith(".SH") else "irm_qa_sz"
        try:
            df = getattr(pro, api)(ts_code=ts_code, start_date=START, end_date=END)
            if df is not None and len(df):
                df["code6"] = code6; qa_all.append(df)
        except Exception: pass
        # 研报
        try:
            df = pro.research_report(ts_code=ts_code, start_date=START, end_date=END)
            if df is not None and len(df):
                df["code6"] = code6; rr_all.append(df)
        except Exception: pass
        # 主营产品 (静态)
        try:
            df = pro.fina_mainbz_vip(ts_code=ts_code, type="P")
            if df is not None and len(df):
                df["code6"] = code6; mb_all.append(df)
        except Exception: pass
        print()
        time.sleep(0.3)

    def save(name, frames):
        if not frames: print(f"  {name}: 0 行"); return
        df = pd.concat(frames, ignore_index=True)
        path = CACHE / f"{name}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"  {name}: {len(df)} 行 × {df['code6'].nunique()} 公司 → {path.name}")

    save("fina_indicator", fina_all)
    save("forecast", fc_all)
    save("irm_qa", qa_all)
    save("research_report", rr_all)
    save("fina_mainbz", mb_all)
    print("\n✅ 缓存完成, 路径2 评分脚本可读本地切片")


if __name__ == "__main__":
    main()
