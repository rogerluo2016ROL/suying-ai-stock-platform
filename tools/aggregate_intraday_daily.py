#!/usr/bin/env python3
"""用实时5分钟K线(stk_mins)聚合出当日日线, 落库到 daily_kline_intraday.

用途: 盘中 daily_kline 今日为空(收盘后才写), 用 stk_mins 聚合补出今日日线,
供选股/诊断在盘中读到"今日OHLCV"。与权威 daily_kline 物理隔离, 收盘后 data-service
仍写真实 daily_kline, 互不污染。

聚合规则(per code):
  open=首bar.open, high=MAX(high), low=MIN(low), close=末bar.close,
  volume=SUM(volume), amount=SUM(amount), bars=COUNT(*)
单位: stk_mins 与 daily_kline 的 amount/volume 均为 Tushare 原值(元/手), SUM 无需换算.
写入: kronos_data.etl._insert_rows (ADR-012/015 单一主干), conflict_action="update"
      盘中可反复刷新当日 intraday 行(每次聚合覆盖更新).

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/aggregate_intraday_daily.py --date 2026-06-23
"""
import argparse, os, sys, time
from collections import defaultdict

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


def aggregate_stk_mins(db, trade_date):
    """拉 stk_mins 今日全量, Python 聚合成日线. 返回 {code: {open,high,low,close,volume,amount,bars}}."""
    rows = db.execute(
        "SELECT code,trade_time,open,high,low,close,volume,amount "
        "FROM stk_mins WHERE trade_time::text LIKE ? AND freq='5min' "
        "ORDER BY code, trade_time",
        (f"{trade_date}%",)
    ).fetchall()

    g = defaultdict(lambda: {"open": 0.0, "high": 0.0, "low": 1e18, "close": 0.0,
                             "volume": 0.0, "amount": 0.0, "bars": 0, "ft": None, "lt": None})
    for r in rows:
        c = r["code"]; a = g[c]; t = str(r["trade_time"])
        o = float(r["open"] or 0); h = float(r["high"] or 0); l = float(r["low"] or 0)
        cl = float(r["close"] or 0); v = float(r["volume"] or 0); am = float(r["amount"] or 0)
        if a["ft"] is None or t < a["ft"]:
            a["ft"] = t; a["open"] = o
        if a["lt"] is None or t > a["lt"]:
            a["lt"] = t; a["close"] = cl
        if h > a["high"]:
            a["high"] = h
        if l < a["low"]:
            a["low"] = l
        a["volume"] += v; a["amount"] += am; a["bars"] += 1

    out = {}
    for c, a in g.items():
        if a["bars"] > 0 and a["close"] > 0 and a["low"] < 1e18:
            out[c] = {k: a[k] for k in ("open", "high", "low", "close", "volume", "amount", "bars")}
    return out


def main():
    parser = argparse.ArgumentParser(description="聚合 stk_mins → daily_kline_intraday")
    parser.add_argument("--date", default=None, help="交易日 YYYY-MM-DD (默认: stk_mins 最新日期)")
    parser.add_argument("--dry-run", action="store_true", help="只聚合不写库")
    args = parser.parse_args()

    from kronos_factors.scorer._db_stub import _get_db

    t0 = time.time()
    with _get_db(readonly=True) as db:
        trade_date = args.date
        if trade_date is None:
            row = db.execute(
                "SELECT MAX(trade_time)::text mt FROM stk_mins WHERE freq='5min'"
            ).fetchone()
            trade_date = (row["mt"] or "")[:10] if row else None
        if not trade_date:
            print("⚠️ stk_mins 无数据"); return

        snap = aggregate_stk_mins(db, trade_date)
        total_amt = sum(s["amount"] for s in snap.values()) / 1e8
        avg_bars = sum(s["bars"] for s in snap.values()) / max(1, len(snap))

    print("=" * 92)
    print(f"  聚合 stk_mins → daily_kline_intraday | {trade_date}")
    print("=" * 92)
    print(f"  聚合股票: {len(snap)} 只 | 平均bars: {avg_bars:.1f} | 全市场成交: {total_amt:.0f}亿")

    if args.dry_run or not snap:
        print(f"  {'(dry-run, 不写库)' if args.dry_run else '(无数据)'}  ⏱️ {time.time()-t0:.1f}s")
        return

    # 写入 daily_kline_intraday (UPSERT, 盘中可反复刷新)
    from kronos_data.etl import _insert_rows, _get_etl_db
    rows = [(c, trade_date, s["open"], s["high"], s["low"], s["close"],
             s["volume"], s["amount"], s["bars"])
            for c, s in snap.items()]
    wdb = _get_etl_db()
    try:
        n = _insert_rows(wdb, "daily_kline_intraday",
                         ["code", "trade_date", "open", "high", "low", "close",
                          "volume", "amount", "bars"],
                         rows, retries=3,
                         conflict_action="update",
                         conflict_cols=["code", "trade_date"],
                         update_cols=["open", "high", "low", "close", "volume", "amount", "bars"],
                         now_cols=["updated_at"])
    finally:
        try:
            wdb.close()
        except Exception:
            pass

    # _insert_rows 在 executemany + ON CONFLICT DO UPDATE 下 rowcount 口径不可靠(返回值偏小),
    # 回查真实落库数.
    with _get_db(readonly=True) as vdb:
        r = vdb.execute("SELECT count(*) c FROM daily_kline_intraday WHERE trade_date=?",
                        (trade_date,)).fetchone()
        actual = r["c"] if r else 0
    print(f"  ✅ 写入完成: 实际落库 {actual} 行 (trade_date={trade_date})")
    print(f"     (_insert_rows 返回 {n} 为 executemany rowcount 口径, 非真实行数)")
    print(f"  ⏱️ 总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
