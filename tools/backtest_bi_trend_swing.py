#!/usr/bin/env python3
"""毕师傅趋势启动战法 — 买卖双向回测 (Buy-Sell Swing Backtest).

模拟: T日买入 → 持有到卖出信号触发 → 记录收益率和持有天数.

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    python tools/backtest_bi_trend_swing.py --month 2026-06 --top-n 15
"""

import argparse, json, os, sys, time
from collections import defaultdict
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
    y, m = month_prefix.split("-")
    start = f"{y}-{m}-01"
    nm = int(m) + 1; ny = int(y)
    if nm > 12: nm = 1; ny += 1
    end = f"{ny}-{nm:02d}-01"
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date < ? ORDER BY trade_date",
        (start, end)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def get_all_trading_days_after(db, start_date, limit=60):
    """获取 start_date 之后的所有交易日."""
    rows = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= ? ORDER BY trade_date LIMIT ?",
        (start_date, limit)
    ).fetchall()
    return [r["trade_date"] for r in rows]


def fetch_stock_data(db, code, trade_date, lookback=60):
    """获取某股票到指定日期的K线."""
    rows = db.execute(
        "SELECT open, high, low, close, volume FROM daily_kline "
        "WHERE code=? AND trade_date<=? ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    if len(rows) < 40:
        return None
    return {
        "closes": np.array([float(r["close"]) for r in rows], dtype=np.float64),
        "highs": np.array([float(r["high"]) for r in rows], dtype=np.float64),
        "lows": np.array([float(r["low"]) for r in rows], dtype=np.float64),
        "volumes": np.array([float(r["volume"]) for r in rows], dtype=np.float64),
        "last_date": trade_date,
    }


def simulate_trade(db, code, entry_date, entry_price, signal_type, all_dates):
    """模拟买入后持有到卖出的全过程.

    Returns: {exit_date, exit_price, return_pct, hold_days, exit_reason, exit_signal}
    """
    from kronos_factors.engine.bi_trend_launch import check_sell_signal

    try:
        entry_idx = all_dates.index(entry_date)
    except ValueError:
        return None

    highest_price = entry_price  # 跟踪入场以来最高价

    for i in range(entry_idx + 1, len(all_dates)):
        exit_date = all_dates[i]
        data = fetch_stock_data(db, code, exit_date)
        if data is None:
            continue

        current_price = float(data["closes"][-1])
        if current_price > highest_price:
            highest_price = current_price

        hold_days = i - entry_idx

        result = check_sell_signal(
            data["closes"], data["highs"], data["lows"], data["volumes"],
            entry_price=entry_price,
            highest_since_entry=highest_price,
            hold_days=hold_days
        )

        sell_signals = ("strong_sell", "sell", "stop_loss", "trailing_stop")
        if result["signal"] in sell_signals:
            return {
                "code": code,
                "entry_date": entry_date,
                "entry_price": entry_price,
                "entry_signal": signal_type,
                "exit_date": exit_date,
                "exit_price": current_price,
                "exit_signal": result["signal"],
                "exit_reason": result["reason"],
                "return_pct": result["current_return_pct"],
                "hold_days": hold_days,
                "highest_return_pct": round((highest_price/entry_price-1)*100, 1),
            }

    # 到数据末尾仍未卖出 → 以最后一天收盘价平仓
    last_date = all_dates[-1]
    data = fetch_stock_data(db, code, last_date)
    if data:
        exit_price = float(data["closes"][-1])
        return_pct = (exit_price / entry_price - 1) * 100
        return {
            "code": code,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "entry_signal": signal_type,
            "exit_date": last_date,
            "exit_price": exit_price,
            "exit_signal": "eod",
            "exit_reason": "期末强平",
            "return_pct": round(return_pct, 2),
            "hold_days": len(all_dates) - entry_idx - 1,
        }
    return None


def run_swing_backtest(db, month, top_n=15):
    """买卖双向回测主流程."""
    from kronos_factors.engine.bi_trend_launch import run_bi_screening

    trading_days = get_trading_days(db, month)
    # 获取后续交易日(用于模拟卖出)
    all_dates = get_all_trading_days_after(db, trading_days[0], limit=120)

    print(f"📅 {month}: {len(trading_days)} 个买入日, 卖出跟踪到 {all_dates[-1]}")
    print()

    all_trades = []
    skipped_days = 0

    for i, td in enumerate(trading_days):
        t0 = time.time()
        print(f"[{i+1}/{len(trading_days)}] {td} 买入...", end=" ", flush=True)

        try:
            top, scores, info = run_bi_screening(db, td, top_n=top_n)
        except Exception as e:
            print(f"❌ 选股失败: {e}")
            continue

        if not top:
            print(f"⏭️ 空仓 ({info.get('env','?')})")
            skipped_days += 1
            continue

        # 对每只入选股票模拟卖出(过滤退市股)
        day_trades = []
        for s in top:
            # 过滤退市/ST股票
            if '退市' in s.get("name", "") or 'ST' in s.get("name", "").upper():
                continue
            trade = simulate_trade(db, s["code"], td, s["close"],
                                   s.get("signal", "buy"), all_dates)
            if trade:
                trade["name"] = s["name"]
                trade["industry"] = s["industry"]
                trade["grade"] = s["grade"]
                trade["buy_score"] = s["total_score"]
                day_trades.append(trade)

        all_trades.extend(day_trades)

        # 当日统计
        if day_trades:
            returns = [t["return_pct"] for t in day_trades]
            win = sum(1 for r in returns if r > 0)
            avg_ret = sum(returns) / len(returns)
            avg_days = sum(t["hold_days"] for t in day_trades) / len(day_trades)
            strong = sum(1 for t in day_trades if t["entry_signal"] == "strong_buy")
            print(f"✅ {len(day_trades)}笔 | 胜{win}/{len(day_trades)} | "
                  f"均{avg_ret:+.1f}% | 持{avg_days:.0f}天 | 🔥{strong} | {time.time()-t0:.0f}s")
        else:
            print(f"⏭️ 无成交 | {time.time()-t0:.0f}s")

    return all_trades, skipped_days


def analyze_swing_results(trades):
    """分析买卖双向回测结果."""
    if not trades:
        print("⚠️ 无交易数据")
        return

    returns = np.array([t["return_pct"] for t in trades])
    hold_days = np.array([t["hold_days"] for t in trades])
    win_mask = returns > 0
    win_count = win_mask.sum()
    total = len(trades)

    print(f"\n{'=' * 80}")
    print(f"  毕师傅趋势启动战法 — 买卖双向回测")
    print(f"  {total} 笔完整交易")
    print(f"{'=' * 80}")

    # ── V4.3: 仓位加权 ──
    from kronos_factors.engine.bi_trend_launch import POSITION
    for t in trades:
        key = f"{t.get('entry_signal','buy')}_{t.get('grade','A')}"
        if t.get('entry_signal') == 'watch':
            key = 'watch'
        t['_weight'] = POSITION.get(key, POSITION.get(f"buy_A", 0.08))
    weighted_returns = np.array([t["return_pct"] * t["_weight"] * 100 for t in trades])

    # ── 总体 ──
    print(f"\n  📊 总体统计 (V4.3 仓位加权):")
    print(f"    胜率:      {win_count}/{total} = {win_count/total*100:.1f}%")
    print(f"    均值收益:  {returns.mean():+.2f}%")
    print(f"    仓位加权累计: {weighted_returns.sum():+.1f}% (假设本金100, 每笔按仓位分配)")
    print(f"    中位数:    {np.median(returns):+.2f}%")
    print(f"    最大盈利:  {returns.max():+.2f}%")
    print(f"    最大亏损:  {returns.min():+.2f}%")
    print(f"    盈亏比:    {returns[win_mask].mean():+.2f}% / {returns[~win_mask].mean():+.2f}%")
    print(f"    均持有天数: {hold_days.mean():.1f}天 (中位{np.median(hold_days):.0f}天)")

    # ── 按买入信号分组 ──
    print(f"\n  📊 按买入信号:")
    print(f"  {'信号':<14} {'笔数':<6} {'胜率':<8} {'均值':<8} {'均持天':<6} {'盈亏比':<14}")
    print(f"  {'-' * 60}")
    for sig in ["strong_buy", "buy", "watch"]:
        g = [t for t in trades if t["entry_signal"] == sig]
        if not g: continue
        gr = np.array([t["return_pct"] for t in g])
        gd = np.array([t["hold_days"] for t in g])
        gw = (gr > 0).sum()
        pw = gr[gr > 0].mean() if (gr > 0).any() else 0
        nw = gr[gr <= 0].mean() if (gr <= 0).any() else 0
        print(f"  {sig:<14} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{gd.mean():>5.0f}天 {pw:>+6.2f}/{nw:>+6.2f}")

    # ── 按卖出信号分组 ──
    print(f"\n  📊 按卖出信号:")
    print(f"  {'信号':<14} {'笔数':<6} {'胜率':<8} {'均值':<8} {'均持天':<6}")
    print(f"  {'-' * 50}")
    for sig in ["strong_sell", "sell", "stop_loss", "trailing_stop", "eod"]:
        g = [t for t in trades if t["exit_signal"] == sig]
        if not g: continue
        gr = np.array([t["return_pct"] for t in g])
        gd = np.array([t["hold_days"] for t in g])
        gw = (gr > 0).sum()
        print(f"  {sig:<14} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}% "
              f"{gd.mean():>5.0f}天")

    # ── 按持有天数分组 ──
    print(f"\n  📊 按持有天数:")
    print(f"  {'持有':<10} {'笔数':<6} {'胜率':<8} {'均值':<8}")
    print(f"  {'-' * 40}")
    for lo, hi, label in [(1, 3, "1-2天"), (3, 6, "3-5天"), (6, 11, "6-10天"), (11, 21, "11-20天"), (21, 99, ">20天")]:
        g = [t for t in trades if lo <= t["hold_days"] < hi]
        if not g: continue
        gr = np.array([t["return_pct"] for t in g])
        gw = (gr > 0).sum()
        print(f"  {label:<10} {len(g):<6} {gw/len(g)*100:>6.1f}% {gr.mean():>+7.2f}%")

    # ── Top/Bottom ──
    sorted_trades = sorted(trades, key=lambda x: -(x["return_pct"]))
    print(f"\n  🏆 最佳5笔:")
    for t in sorted_trades[:5]:
        hi = f" 最高{t.get('highest_return_pct',0):+.0f}%" if t.get('highest_return_pct') else ""
        print(f"    {t['entry_date']}→{t['exit_date']} {t['code']} {t['name']:<8} "
              f"持{t['hold_days']}天 {t['return_pct']:>+6.2f}%{hi} "
              f"({t['entry_signal']}→{t['exit_signal']}: {t['exit_reason']})")

    print(f"\n  💀 最差5笔:")
    for t in sorted_trades[-5:]:
        hi = f" 最高{t.get('highest_return_pct',0):+.0f}%" if t.get('highest_return_pct') else ""
        print(f"    {t['entry_date']}→{t['exit_date']} {t['code']} {t['name']:<8} "
              f"持{t['hold_days']}天 {t['return_pct']:>+6.2f}%{hi} "
              f"({t['entry_signal']}→{t['exit_signal']}: {t['exit_reason']})")


def main():
    parser = argparse.ArgumentParser(description="毕师傅趋势启动战法 — 买卖双向回测")
    parser.add_argument("--month", type=str, default="2026-06")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--export", type=str, default=None)
    args = parser.parse_args()

    adapter = setup_db()
    from kronos_factors.scorer._db_stub import _get_db

    with _get_db() as db:
        trades, skipped = run_swing_backtest(db, args.month, args.top_n)

    analyze_swing_results(trades)

    # 导出
    if args.export or True:
        path = args.export or f"outputs/backtest_bi_swing_{args.month}.json"
        os.makedirs(os.path.dirname(path) or "outputs", exist_ok=True)
        with open(path, 'w') as f:
            json.dump(trades, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n📁 结果: {path}")

    if hasattr(adapter, 'close'):
        adapter.close()


if __name__ == "__main__":
    main()
