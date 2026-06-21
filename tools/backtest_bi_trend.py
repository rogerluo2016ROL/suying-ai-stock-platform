#!/usr/bin/env python3
"""毕师傅趋势启动战法 — 回测脚本.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_bi_trend.py --month 2026-06 --top-n 20
"""

import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)


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
    """获取指定月份有 daily_kline 数据的交易日."""
    y, m = month_prefix.split("-")
    start = f"{y}-{m}-01"
    # Use next month's first day as exclusive upper bound
    nm = int(m) + 1
    ny = int(y)
    if nm > 12:
        nm = 1
        ny += 1
    end = f"{ny}-{nm:02d}-01"
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date < ? ORDER BY trade_date",
        (start, end)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_next_day_return(db, code, trade_date, stop_loss_pct=None):
    """获取次日收益率: T日收盘买入, T+1日收盘卖出 (可选止损).

    V13 P1: 支持盘中止损模拟.
    止损逻辑: 如果 T+1日最低价触及止损价, 以止损价退出; 否则以收盘价退出.
    跳空低开: 如果开盘价已低于止损价, 以开盘价退出 (模拟竞价止损).
    """
    entry_row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if not entry_row or not entry_row["close"]:
        return None, None
    entry_price = float(entry_row["close"])

    next_row = db.execute(
        "SELECT open, high, low, close FROM daily_kline WHERE code=? AND trade_date > ? "
        "ORDER BY trade_date ASC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    if not next_row or not next_row["close"]:
        return None, None

    exit_price = float(next_row["close"])
    stopped = False

    if stop_loss_pct is not None and stop_loss_pct < 0:
        stop_price = entry_price * (1 + stop_loss_pct / 100)
        next_open = float(next_row["open"] or exit_price)
        next_low = float(next_row["low"] or exit_price)

        # 跳空低开: 开盘即跌破止损
        if next_open <= stop_price:
            exit_price = next_open
            stopped = True
        # 盘中触及止损
        elif next_low <= stop_price:
            exit_price = stop_price
            stopped = True

    ret = (exit_price / entry_price - 1) * 100
    return ret, stopped


def run_backtest_day(db, trade_date, top_n=20):
    """单日回测 V2.0 — 使用优化引擎+市场熔断."""
    from kronos_factors.engine.bi_trend_launch import run_bi_screening

    top, all_scores, market_info = run_bi_screening(db, trade_date, top_n=top_n)
    return {
        "trade_date": trade_date,
        "total_qualified": len(all_scores),
        "top_picks": top,
        "market_info": market_info,
    }


def analyze_results(results, db):
    """分析回测结果 (V13 P1: 支持止损模拟)."""
    all_picks = []
    for r in results:
        td = r["trade_date"]
        for s in r["top_picks"]:
            # V13 P1: 使用 pivot 的止损价位
            sl = s.get("stop_loss")  # 负数, 如 -8 = -8%止损
            ret, stopped = get_next_day_return(db, s["code"], td, stop_loss_pct=sl)
            # V13 P1: S级仓位降权
            weight = s.get("weight", 1.0)
            all_picks.append({
                "trade_date": td,
                "code": s["code"],
                "name": s["name"],
                "industry": s["industry"],
                "grade": s["grade"],
                "total_score": s["total_score"],
                "signal": s["signal"],
                "obv_days_above": s["obv_days_above"],
                "obv_level": s["obv_level"],
                "wr_level": s["wr_level"],
                "vol_level": s["vol_level"],
                "next_day_return": ret,
                "stopped": stopped,
                "weight": weight,
                # V12.1: 个性化持有建议
                "hold_days": s.get("hold_days"),
                "stop_loss": sl,
                "take_profit": s.get("take_profit"),
                "trailing_stop": s.get("trailing_stop"),  # V12.3
                "checklist_score": s.get("checklist_score"),
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
    print(f"  毕师傅趋势启动战法 — 回测汇总")
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
    print(f"    盈亏比:    {returns[win_mask].mean():+.2f}% / {returns[~win_mask].mean():+.2f}%")

    # ── 按评级分组 ──
    print(f"\n  📊 按评级分组:")
    print(f"  {'评级':<6} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<12} {'最大盈':<8} {'最大亏':<8}")
    print(f"  {'-' * 78}")
    for grade in ["S", "A", "B", "C"]:
        g = [p for p in valid if p["grade"] == grade]
        if not g:
            continue
        gr = np.array([p["next_day_return"] for p in g])
        gw = (gr > 0).sum()
        pw = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {grade:<6} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{np.median(gr):>+7.2f}% {pw:>+6.2f}/{nw:>+6.2f} {gr.max():>+7.2f}% {gr.min():>+7.2f}%")

    # ── 按信号分组 ──
    print(f"\n  📊 按信号分组:")
    print(f"  {'信号':<14} {'笔数':<6} {'胜率':<8} {'均值':<8} {'中位数':<8} {'盈亏比':<12}")
    print(f"  {'-' * 60}")
    for sig in ["strong_buy", "buy", "watch", "no_signal"]:
        g = [p for p in valid if p["signal"] == sig]
        if not g:
            continue
        gr = np.array([p["next_day_return"] for p in g])
        gw = (gr > 0).sum()
        pw = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {sig:<14} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{np.median(gr):>+7.2f}% {pw:>+6.2f}/{nw:>+6.2f}")

    # ── V13 P1: 加权止损统计 ──
    stopped_count = sum(1 for p in valid if p.get("stopped"))
    if stopped_count > 0:
        print(f"\n  🛑 止损触发: {stopped_count}/{total} 笔 ({stopped_count/total*100:.0f}%)")
        for p in [p for p in valid if p.get("stopped")][:5]:
            print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']}级 止损{p['stop_loss']}% → {p['next_day_return']:+.2f}%")

    # ── 每日汇总 (V13 P1: 加权收益) ──
    print(f"\n  📊 每日汇总 (加权):")
    print(f"  {'日期':<12} {'笔数':<5} {'胜率':<8} {'加权均值':<10} {'S级权重':<8} {'止损':<5}")
    print(f"  {'-' * 55}")
    for r in results:
        td = r["trade_date"]
        day_picks = [p for p in valid if p["trade_date"] == td]
        if not day_picks:
            continue
        dr = np.array([p["next_day_return"] for p in day_picks])
        dw = (dr > 0).sum()
        # 加权均值: S级 0.6x, A/B级 1.0x
        weights = np.array([p.get("weight", 1.0) for p in day_picks])
        weighted_avg = np.average(dr, weights=weights) if weights.sum() > 0 else dr.mean()
        s_count = sum(1 for p in day_picks if p["grade"] == "S")
        st = sum(1 for p in day_picks if p.get("stopped"))
        print(f"  {td:<12} {len(day_picks):<5} {dw/len(day_picks)*100:>6.1f}% "
              f"{weighted_avg:>+8.2f}%  {s_count}x0.6{'':<4} {st:<5}")

    # ── Top winners & losers ──
    print(f"\n  🏆 最佳10笔:")
    top_win = sorted(valid, key=lambda x: -(x["next_day_return"] or -999))[:10]
    for p in top_win:
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"{p['signal']:<12} → 次日 {p['next_day_return']:>+6.2f}%")

    print(f"\n  💀 最差10笔:")
    top_loss = sorted(valid, key=lambda x: (x["next_day_return"] or 999))[:10]
    for p in top_loss:
        print(f"    {p['trade_date']} {p['code']} {p['name']:<8} {p['grade']} "
              f"{p['signal']:<12} → 次日 {p['next_day_return']:>+6.2f}%")

    return all_picks


def main():
    parser = argparse.ArgumentParser(description="毕师傅趋势启动战法回测")
    parser.add_argument("--month", type=str, default="2026-06", help="回测月份 YYYY-MM")
    parser.add_argument("--top-n", type=int, default=20, help="每日选股数")
    parser.add_argument("--export", type=str, default=None, help="导出JSON路径")
    args = parser.parse_args()

    adapter = setup_db()

    from kronos_factors.scorer._db_stub import _get_db
    with _get_db() as db:
        trading_days = get_trading_days(db, args.month)
        print(f"📅 {args.month} 交易日: {len(trading_days)} 天")
        for td in trading_days:
            print(f"   {td}")
        print()

    if not trading_days:
        print("❌ 无可用交易日")
        return

    results = []
    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} ...", end=" ", flush=True)
        try:
            with _get_db() as db:
                r = run_backtest_day(db, td, args.top_n)
            elapsed = time.time() - t0
            top_n = len(r["top_picks"])
            grades = f"S={sum(1 for s in r['top_picks'] if s['grade']=='S')} " \
                     f"A={sum(1 for s in r['top_picks'] if s['grade']=='A')}"
            sb = sum(1 for s in r['top_picks'] if s['signal']=='strong_buy')
            print(f"✅ {top_n}只/{r['total_qualified']}入选 {grades} 🔥{sb} {elapsed:.1f}s")
            results.append(r)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"❌ {elapsed:.1f}s - {e}")

    # ── 分析 ──
    with _get_db() as db:
        all_picks = analyze_results(results, db)

    # ── 导出 ──
    export_path = args.export or f"outputs/backtest_bi_trend_{args.month}.json"
    os.makedirs(os.path.dirname(export_path) or "outputs", exist_ok=True)
    serializable = []
    for p in all_picks:
        serializable.append({k: (float(v) if isinstance(v, (np.floating,)) else v)
                             for k, v in p.items()})
    with open(export_path, 'w') as f:
        json.dump({
            "month": args.month,
            "total_picks": len(all_picks),
            "summary": {
                "valid": sum(1 for p in all_picks if p["next_day_return"] is not None),
                "by_grade": {},
                "by_signal": {},
            },
            "picks": serializable,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 结果导出: {export_path}")

    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
