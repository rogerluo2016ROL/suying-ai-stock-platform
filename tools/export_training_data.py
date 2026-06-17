#!/usr/bin/env python3
"""Training data exporter — 从 screening_snapshots 导出 ML 训练数据.

将历史选股快照的特征 + 多周期实际收益导出为训练管线期望的格式:
  - CSV: features + ret_1d/3d/5d/10d/20d labels
  - Pickle: {stock_code: DataFrame} dict (兼容 Kronos QlibDataset)

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/export_training_data.py --format csv --output outputs/training/

    python tools/export_training_data.py --format pickle --output Kronos/data/processed_datasets/
"""
import argparse, json, os, sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))


def get_pg_conn():
    import psycopg2
    url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn


def export_csv(conn, output_dir: str, model_key: str = None,
               start_date: str = None, end_date: str = None, min_samples: int = 50):
    """Export as flat CSV — one row per pick with features + labels."""
    cur = conn.cursor()

    where = "WHERE next_day_return IS NOT NULL"
    params = []
    if model_key:
        where += " AND model_key = %s"
        params.append(model_key)
    if start_date:
        where += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND trade_date <= %s"
        params.append(end_date)

    cur.execute(f"""
        SELECT model_key, trade_date, stock_code, time_slot,
               factors, total_score, grade, rank_in_day,
               next_day_return, is_win,
               ret_3d, is_win_3d, ret_5d, is_win_5d,
               ret_10d, is_win_10d, ret_20d
        FROM screening_snapshots
        {where}
        ORDER BY trade_date, model_key, rank_in_day
    """, tuple(params) if params else None)

    rows = cur.fetchall()
    if len(rows) < min_samples:
        print(f"  ⚠️ Only {len(rows)} samples (min={min_samples}), skipping export")
        cur.close()
        return None

    # Flatten JSONB factors into columns
    all_factor_keys = set()
    records = []
    for row in rows:
        mk, td, code, ts, factors, score, grade, rank, r1, w1, r3, w3, r5, w5, r10, w10, r20 = row
        rec = {
            "model_key": mk, "trade_date": str(td), "stock_code": code,
            "time_slot": ts, "total_score": score, "grade": grade, "rank_in_day": rank,
            "ret_1d": r1, "is_win_1d": w1,
            "ret_3d": r3, "is_win_3d": w3,
            "ret_5d": r5, "is_win_5d": w5,
            "ret_10d": r10, "is_win_10d": w10,
            "ret_20d": r20,
        }
        if factors:
            for k, v in factors.items():
                if isinstance(v, (int, float)):
                    rec[f"f_{k}"] = v
                    all_factor_keys.add(f"f_{k}")
        records.append(rec)

    df = pd.DataFrame(records)
    print(f"  📊 Exported {len(df)} rows × {len(df.columns)} cols")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"training_data_{model_key or 'all'}.csv")
    df.to_csv(path, index=False)
    print(f"  📁 CSV: {path}")

    # Also save factor key list for reference
    meta_path = os.path.join(output_dir, f"factor_keys_{model_key or 'all'}.json")
    with open(meta_path, 'w') as f:
        json.dump({"factor_keys": sorted(all_factor_keys), "total_samples": len(df),
                   "model_key": model_key, "exported_at": str(date.today())}, f, indent=2)
    print(f"  📁 Meta: {meta_path}")

    cur.close()
    return df


def export_pickle(conn, output_dir: str, model_key: str = None,
                  start_date: str = "2024-01-01", end_date: str = None):
    """Export as Qlib-compatible pickle dict — {stock_code: DataFrame}.

    Each DataFrame has:
      - DatetimeIndex
      - Feature columns from factors JSONB
      - Label columns: ret_1d, ret_3d, ret_5d, ret_10d, ret_20d
    """
    import pickle

    cur = conn.cursor()
    where = "WHERE next_day_return IS NOT NULL"
    params = []
    if model_key:
        where += " AND model_key = %s"
        params.append(model_key)
    if start_date:
        where += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND trade_date <= %s"
        params.append(end_date)

    cur.execute(f"""
        SELECT stock_code, trade_date, factors,
               next_day_return, ret_3d, ret_5d, ret_10d, ret_20d
        FROM screening_snapshots
        {where}
        ORDER BY stock_code, trade_date
    """, tuple(params) if params else None)

    # Group by stock code
    from collections import defaultdict
    stock_data = defaultdict(list)

    for row in cur.fetchall():
        code, td, factors, r1, r3, r5, r10, r20 = row
        rec = {
            "trade_date": str(td),
            "ret_1d": r1, "ret_3d": r3, "ret_5d": r5,
            "ret_10d": r10, "ret_20d": r20,
        }
        if factors:
            for k, v in factors.items():
                if isinstance(v, (int, float)):
                    rec[k] = v
        stock_data[code].append(rec)

    # Convert to DataFrames
    result = {}
    skipped = 0
    for code, records in stock_data.items():
        if len(records) < 5:  # need minimum history
            skipped += 1
            continue
        df = pd.DataFrame(records)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()
        result[code] = df

    print(f"  📊 {len(result)} stocks (skipped {skipped} with <5 samples)")

    os.makedirs(output_dir, exist_ok=True)
    fname = f"snapshot_training_{model_key or 'all'}.pkl"
    path = os.path.join(output_dir, fname)
    with open(path, 'wb') as f:
        pickle.dump(result, f)
    print(f"  📁 Pickle: {path} ({os.path.getsize(path)/1024/1024:.1f} MB)")

    cur.close()
    return result


def main():
    parser = argparse.ArgumentParser(description="Export screening snapshots as ML training data")
    parser.add_argument("--format", choices=["csv", "pickle", "both"], default="csv")
    parser.add_argument("--model", default=None, help="Model key filter (e.g. leader_intraday_v7)")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="outputs/training/", help="Output directory")
    args = parser.parse_args()

    conn = get_pg_conn()
    print(f"  📡 PG connected, exporting training data...")

    if args.format in ("csv", "both"):
        export_csv(conn, args.output, args.model, args.start, args.end)

    if args.format in ("pickle", "both"):
        export_pickle(conn, args.output, args.model, args.start, args.end)

    conn.close()
    print("  ✅ Done")


if __name__ == "__main__":
    main()
