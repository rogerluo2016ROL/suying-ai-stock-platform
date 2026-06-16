#!/usr/bin/env python3
"""秋神龙头战法-午后选股模型 — 回测脚本.

模拟每日14:30运行午后模型, T日尾盘买入, T+1日收盘卖出.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_afternoon.py --month 2026-06 --top-n 20

    也可指定回测时间:
    python tools/backtest_afternoon.py --month 2026-06 --time 14:00
    python tools/backtest_afternoon.py --month 2026-06 --time 14:30
"""

import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import numpy as np


def setup_db():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    from kronos_factors.pg_adapter import create_pg_adapter
    from kronos_factors.scorer._db_stub import set_db_adapter, set_market_data_adapter
    adapter = create_pg_adapter(pg_url)
    if adapter is None:
        raise RuntimeError(f"无法连接数据库: {pg_url}")
    set_db_adapter(adapter)
    set_market_data_adapter(adapter)
    return adapter


def get_trading_days(db, month_prefix="2026-06"):
    """获取有 stk_mins 数据的交易日."""
    rows = db.execute(
        "SELECT DISTINCT SUBSTR(trade_time,1,10) as trade_date "
        "FROM stk_mins WHERE trade_time LIKE ? AND freq='5min' "
        "AND trade_time LIKE '%14:%' "
        "ORDER BY trade_date",
        (f"{month_prefix}%",)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_next_day_return(db, code, trade_date):
    """T+1日收盘收益."""
    entry_row = db.execute(
        "SELECT close FROM stk_mins WHERE ts_code LIKE ? AND trade_time LIKE ? AND freq='5min' "
        "ORDER BY trade_time DESC LIMIT 1",
        (f"{code}%", f"{trade_date} 15:%")
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        entry_row = db.execute(
            "SELECT close FROM daily_kline WHERE code=? AND trade_date=?", (code, trade_date)
        ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None
    entry_price = float(entry_row["close"])

    exit_row = db.execute(
        "SELECT close, trade_date FROM daily_kline WHERE code=? AND trade_date > ? "
        "ORDER BY trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not exit_row or not exit_row["close"]:
        return None

    return (float(exit_row["close"]) / entry_price - 1) * 100


def run_backtest_day(db, trade_date, time_slot, top_n=20):
    """单日回测."""
    from kronos_factors.engine.leader_afternoon import run_afternoon_screening

    top, all_scores = run_afternoon_screening(trade_date, time_slot=time_slot, top_n=top_n)
    return {"trade_date": trade_date, "top_picks": top, "total_qualified": len(all_scores)}


def analyze_results(results, db):
    """分析回测结果."""
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for s in r["top_picks"]:
            ret = get_next_day_return(db, s["code"], td)
            all_picks.append({
                "trade_date": td,
                "code": s["code"], "name": s["name"], "industry": s["industry"],
                "grade": s["grade"], "total_score": s["total_score"],
                "gain_14": s["gain_pct"], "peer_count": s.get("peer_count", 0),
                "resilience_score": s.get("resilience_score", 0),
                "is_at_limit": s.get("is_at_limit", False),
                "next_day_return": ret,
            })

    valid = [p for p in all_picks if p["next_day_return"] is not None]
    pending = len(all_picks) - len(valid)

    if not valid:
        print("⚠️ 无有效次日收益数据")
        return all_picks

    returns = np.array([p["next_day_return"] for p in valid])
    win_mask = returns > 0
    win_count = win_mask.sum()
    total = len(valid)

    print(f"\n{'=' * 80}")
    print(f"  秋神午后选股 — 回测汇总")
    print(f"  {len(results)} 交易日 | {total} 笔交易 | pending={pending}")
    print(f"{'=' * 80}")
    print(f"  📊 总体统计:")
    print(f"    胜率:      {win_count}/{total} = {win_count/total*100:.1f}%")
    print(f"    均值收益:  {returns.mean():+.2f}%")
    print(f"    中位数:    {np.median(returns):+.2f}%")
    print(f"    最大盈利:  {returns.max():+.2f}%")
    print(f"    最大亏损:  {returns.min():+.2f}%")
    print(f"    累计收益:  {returns.sum():+.2f}%")
    print(f"    标准差:    {returns.std():.2f}%")
    pw = returns[win_mask].mean() if win_mask.any() else 0
    nw = returns[~win_mask].mean() if (~win_mask).any() else 0
    print(f"    盈亏比:    {pw:+.2f}% / {nw:+.2f}%")

    # ── 按评级 ──
    print(f"\n  📊 按评级分组:")
    print(f"  {'评级':<6} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<12} {'最大盈':<8} {'最大亏':<8}")
    print(f"  {'-' * 78}")
    for grade in ["S", "A", "B", "C"]:
        g = [p for p in valid if p["grade"] == grade]
        if not g:
            continue
        gr = np.array([p["next_day_return"] for p in g])
        gw = (gr > 0).sum()
        pw_g = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw_g = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {grade:<6} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{np.median(gr):>+7.2f}% {pw_g:>+6.2f}/{nw_g:>+6.2f} {gr.max():>+7.2f}% {gr.min():>+7.2f}%")

    # ── 按涨停状态 ──
    print(f"\n  📊 按14:30涨停状态:")
    lim_picks = [p for p in valid if p.get("is_at_limit")]
    nonlim_picks = [p for p in valid if not p.get("is_at_limit")]
    for label, group in [("已涨停", lim_picks), ("未涨停", nonlim_picks)]:
        if group:
            gr = np.array([p["next_day_return"] for p in group])
            gw = (gr > 0).sum()
            print(f"  {label}: n={len(group)}, avg={gr.mean():+.2f}%, med={np.median(gr):+.2f}%, win={gw/len(group)*100:.0f}%")

    # ── 按分歧不死 ──
    print(f"\n  📊 按分歧不死(resilience):")
    for level in [(0, "无分歧"), (1, "深度分歧"), (2, "中度分歧"), (3, "轻微分歧"), (4, "零分歧")]:
        r_picks = [p for p in valid if p.get("resilience_score") == level[0]]
        if r_picks:
            gr = np.array([p["next_day_return"] for p in r_picks])
            gw = (gr > 0).sum()
            print(f"  {level[1]}({level[0]}): n={len(r_picks)}, avg={gr.mean():+.2f}%, win={gw/len(r_picks)*100:.0f}%")

    # ── 每日汇总 ──
    print(f"\n  📊 每日汇总:")
    print(f"  {'日期':<12} {'笔数':<5} {'胜率':<8} {'均值':<8} {'S/A级':<6} {'涨停':<5}")
    print(f"  {'-' * 50}")
    for r in results:
        td = r["trade_date"]
        day_picks = [p for p in valid if p["trade_date"] == td]
        if not day_picks:
            continue
        dr = np.array([p["next_day_return"] for p in day_picks])
        dw = (dr > 0).sum()
        sa = sum(1 for p in day_picks if p["grade"] in ("S", "A"))
        lim = sum(1 for p in day_picks if p.get("is_at_limit"))
        print(f"  {td:<12} {len(day_picks):<5} {dw/len(day_picks)*100:>6.1f}% "
              f"{dr.mean():>+7.2f}% {sa:<6} {lim:<5}")

    # ── Top Winners & Losers ──
    print(f"\n  🏆 最佳10笔:")
    for p in sorted(valid, key=lambda x: -(x["next_day_return"] or -999))[:10]:
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"gain14={p.get('gain_14',0):+.1f}% res={p.get('resilience_score',0)} "
              f"→ 次日 {p['next_day_return']:>+6.2f}%")

    print(f"\n  💀 最差10笔:")
    for p in sorted(valid, key=lambda x: (x["next_day_return"] or 999))[:10]:
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"gain14={p.get('gain_14',0):+.1f}% res={p.get('resilience_score',0)} "
              f"→ 次日 {p['next_day_return']:>+6.2f}%")

    return all_picks


def main():
    parser = argparse.ArgumentParser(description="秋神午后选股回测")
    parser.add_argument("--month", type=str, default="2026-06", help="回测月份 YYYY-MM")
    parser.add_argument("--top-n", type=int, default=20, help="每日选股数")
    parser.add_argument("--time", type=str, default="14:30", help="回测时间点 (14:00/14:30/14:40)")
    parser.add_argument("--export", type=str, default=None, help="导出JSON路径")
    args = parser.parse_args()

    adapter = setup_db()

    from kronos_factors.scorer._db_stub import _get_db
    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 交易日 (有{args.time} stk_mins数据): {len(trading_days)} 天")
        for td in trading_days:
            print(f"   {td}")
        print()

    if not trading_days:
        print("❌ 无可用交易日, 检查 stk_mins 数据")
        return

    results = []
    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} {args.time} ...", end=" ", flush=True)
        try:
            with _get_db() as db:
                r = run_backtest_day(db, td, args.time, args.top_n)
            elapsed = time.time() - t0
            top_n_count = len(r["top_picks"])
            grades = f"S={sum(1 for s in r['top_picks'] if s['grade']=='S')} " \
                     f"A={sum(1 for s in r['top_picks'] if s['grade']=='A')}"
            lim_n = sum(1 for s in r['top_picks'] if s.get("is_at_limit"))
            print(f"✅ {top_n_count}只/{r['total_qualified']}入选 {grades} 🔒涨停={lim_n} {elapsed:.1f}s")
            results.append(r)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"❌ {elapsed:.1f}s - {e}")
            import traceback
            traceback.print_exc()

    # ── 分析 ──
    with _get_db() as db:
        all_picks = analyze_results(results, db)

    # ── 导出 ──
    export_path = args.export or f"outputs/backtest_afternoon_{args.month}.json"
    os.makedirs(os.path.dirname(export_path) or "outputs", exist_ok=True)
    serializable = []
    for p in all_picks:
        d = {}
        for k, v in p.items():
            if isinstance(v, (np.floating,)):
                d[k] = float(v)
            elif isinstance(v, bool):
                d[k] = v
            else:
                d[k] = v
        serializable.append(d)

    with open(export_path, 'w') as f:
        json.dump({
            "month": args.month,
            "time_slot": args.time,
            "total_picks": len(all_picks),
            "picks": serializable,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 结果导出: {export_path}")

    if hasattr(adapter, 'close'):
        try:
            adapter.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
