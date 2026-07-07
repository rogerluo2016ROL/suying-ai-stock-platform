#!/usr/bin/env python3
"""TrendLaunchEngine Walk-Forward 回测 (严格杜绝数据泄露).

每月月末选股 → 持有一个月 → 记录次月收益 → 更新链历史。
链动量只用已发生的过去3个月数据, 绝不偷看未来。

Usage:
    KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
    PYTHONPATH=packages/kronos-factors \
    python tools/backtest_trend_launch.py
"""
import os, sys, time, json
from collections import defaultdict
from datetime import datetime, timedelta
import numpy as np
import psycopg2

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages/kronos-factors"))

from kronos_factors.engine.supply_chain_trend import TrendLaunchEngine
from kronos_factors.engine.supply_chain import CHAINS as ALL_CHAINS_CONFIG
from kronos_factors.scorer._db_stub import _get_db

ALL_CHAINS = [
    '半导体', '华为韬定律_先进封装', '光通信', '存储芯片', '华为终端', 'EDA工业软件',
    'AI算力', '机器人', '新能源', '新能源车', '创新药',
    '高端制造', '国防军工', '消费升级', '周期资源',
]

# ── Chain → industry mapping (from CHAINS config) ──
CHAIN_INDUSTRIES = {}
for ck, cd in ALL_CHAINS_CONFIG.items():
    CHAIN_INDUSTRIES[ck] = cd.get("industries", [])

def get_monthly_dates(pg_url, start="2016-01-01", end="2026-07-01"):
    """Get list of month-end trade dates."""
    pg = psycopg2.connect(pg_url, connect_timeout=10)
    cur = pg.cursor()
    cur.execute(
        "SELECT DISTINCT trade_date FROM daily_kline "
        "WHERE trade_date >= %s AND trade_date <= %s ORDER BY trade_date",
        (start, end)
    )
    all_dates = [str(r[0]) for r in cur.fetchall()]
    pg.close()

    # Group by month, take last trading day
    months = {}
    for d in all_dates:
        m = d[:7]  # YYYY-MM
        months[m] = d
    return sorted(months.values())


def compute_chain_monthly_return(pg_url, chain_name, month_date):
    """Compute equal-weight return for a chain's stocks during a month.

    Uses stocks in the chain's industries, weighted equally.
    month_date = month-end date. Returns the total return for that month.
    """
    industries = CHAIN_INDUSTRIES.get(chain_name, [])
    if not industries:
        return 0.0

    pg = psycopg2.connect(pg_url, connect_timeout=10)
    cur = pg.cursor()

    # Get first and last trading day of the month
    month_start = month_date[:7] + "-01"
    cur.execute(
        "SELECT MIN(trade_date), MAX(trade_date) FROM daily_kline "
        "WHERE trade_date >= %s AND trade_date <= %s",
        (month_start, month_date)
    )
    first_day, last_day = cur.fetchone()

    # Get chain stocks
    like_clauses = " OR ".join(["s.industry LIKE %s"] * len(industries))
    params = [f"%{ind}%" for ind in industries]
    cur.execute(
        f"SELECT DISTINCT s.code FROM stocks s WHERE s.is_st=0 AND ({like_clauses})",
        params
    )
    chain_codes = set(r[0] for r in cur.fetchall())

    if not chain_codes:
        pg.close()
        return 0.0

    # Get first-day and last-day closes for chain stocks
    placeholders = ",".join(["%s"] * len(chain_codes))
    cur.execute(
        f"SELECT code, close FROM daily_kline WHERE trade_date=%s AND code IN ({placeholders})",
        [str(first_day)] + list(chain_codes)
    )
    first_closes = {r[0]: float(r[1]) for r in cur.fetchall()}

    cur.execute(
        f"SELECT code, close FROM daily_kline WHERE trade_date=%s AND code IN ({placeholders})",
        [str(last_day)] + list(chain_codes)
    )
    last_closes = {r[0]: float(r[1]) for r in cur.fetchall()}

    # Equal-weight return
    returns = []
    for c in chain_codes:
        if c in first_closes and c in last_closes and first_closes[c] > 0:
            returns.append((last_closes[c] - first_closes[c]) / first_closes[c])

    pg.close()
    return np.mean(returns) if returns else 0.0


def compute_stock_monthly_return(pg_url, code, month_date):
    """Compute a stock's return from month-end to next month-end."""
    pg = psycopg2.connect(pg_url, connect_timeout=10)
    cur = pg.cursor()

    # Get the close on month_date
    cur.execute(
        "SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s "
        "ORDER BY trade_date DESC LIMIT 1",
        (code, month_date)
    )
    r = cur.fetchone()
    if not r:
        pg.close()
        return 0.0
    entry_price = float(r[0])

    # Get next month's end date
    dt = datetime.strptime(month_date, "%Y-%m-%d")
    # Approximate next month end
    if dt.month == 12:
        next_month = dt.replace(year=dt.year+1, month=1, day=1)
    else:
        next_month = dt.replace(month=dt.month+1, day=1)

    cur.execute(
        "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date > %s AND trade_date <= %s",
        (month_date, next_month.strftime("%Y-%m-") + "28")
    )
    nr = cur.fetchone()
    if not nr or not nr[0]:
        # Try wider window
        cur.execute(
            "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date > %s",
            (month_date,)
        )
        nr = cur.fetchone()

    if not nr or not nr[0]:
        pg.close()
        return 0.0

    next_date = str(nr[0])
    cur.execute(
        "SELECT close FROM daily_kline WHERE code=%s AND trade_date=%s",
        (code, next_date)
    )
    er = cur.fetchone()
    pg.close()

    if not er:
        return 0.0
    exit_price = float(er[0])
    return (exit_price - entry_price) / entry_price if entry_price > 0 else 0.0


def main():
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

    print("=" * 80)
    print("  TrendLaunchEngine Walk-Forward 回测 (严格防泄露)")
    print("=" * 80)

    # Get monthly dates
    month_dates = get_monthly_dates(pg_url, start="2016-01-01", end="2026-07-01")
    print(f"  回测月份: {len(month_dates)} ({month_dates[0]} ~ {month_dates[-1]})")

    # Initialize engine with empty chain history
    engine = TrendLaunchEngine(momentum_window=3, min_chains=5, total_slots=15,
                                cross_chain_bonus=1.5, min_score=30)

    # Results tracking
    monthly_returns: list[float] = []
    all_trades: list[dict] = []
    yearly_stats: dict[str, list[float]] = defaultdict(list)

    MIN_MONTHS_BEFORE_START = 3  # Need 3 months of chain data before first pick

    for i, month_date in enumerate(month_dates):
        if i < MIN_MONTHS_BEFORE_START:
            # Build initial chain history (no picks yet)
            for ch in ALL_CHAINS:
                ret = compute_chain_monthly_return(pg_url, ch, month_date)
                engine._chain_history[ch].append(ret)
            continue

        # ── Step 1: Run screening using PAST data only ──
        try:
            result = engine.run(top_n=15, min_score=30, trade_date=month_date)
            picks = result.picks if hasattr(result, 'picks') else result.get('picks', [])
        except Exception as e:
            print(f"  ⚠️ {month_date}: engine error {e}")
            picks = []

        # ── Step 2: Compute next-month returns for picks ──
        pick_returns = []
        for p in picks:
            ret = compute_stock_monthly_return(pg_url, p['code'], month_date)
            pick_returns.append(ret)
            all_trades.append({
                "date": month_date,
                "code": p['code'],
                "name": p['name'],
                "score": p.get('total_score', 0),
                "chain": p.get('chain', ''),
                "return": ret,
            })

        # ── Step 3: Equal-weight portfolio return ──
        if pick_returns:
            month_ret = np.mean(pick_returns)
        else:
            month_ret = 0.0

        monthly_returns.append(month_ret)
        year = month_date[:4]
        yearly_stats[year].append(month_ret)

        # ── Step 4: Update chain history with ACTUAL this-month returns ──
        for ch in ALL_CHAINS:
            ret = compute_chain_monthly_return(pg_url, ch, month_date)
            engine._chain_history[ch].append(ret)

        if i % 12 == 0:
            print(f"  {month_date}: {len(picks)} picks, return={month_ret:+.2%}")

    # ── Summary stats ──
    valid_returns = [r for r in monthly_returns if r != 0]
    if not valid_returns:
        print("\n⚠️ 无有效回测数据")
        return

    n_months = len(valid_returns)
    cum_return = np.prod([1 + r for r in valid_returns])
    avg_monthly = np.mean(valid_returns)
    sharpe = avg_monthly / np.std(valid_returns) * np.sqrt(12) if np.std(valid_returns) > 0 else 0
    win_rate = sum(1 for r in valid_returns if r > 0) / n_months

    # Max drawdown
    cum_series = np.cumprod([1 + r for r in valid_returns])
    peak = np.maximum.accumulate(cum_series)
    drawdown = (cum_series - peak) / peak
    max_dd = drawdown.min()

    print(f"\n{'='*80}")
    print(f"  Walk-Forward 回测结果 ({month_dates[MIN_MONTHS_BEFORE_START]} ~ {month_dates[-1]})")
    print(f"{'='*80}")
    print(f"  有效月份: {n_months}")
    print(f"  月均收益: {avg_monthly:+.2%}")
    print(f"  累计收益: {cum_return-1:+.1%}")
    print(f"  Sharpe: {sharpe:.2f}")
    print(f"  最大回撤: {max_dd:.1%}")
    print(f"  月胜率: {win_rate:.1%}")

    # Yearly breakdown
    print(f"\n  {'─'*40}")
    print(f"  {'年份':<6s} {'月份':>5s} {'月均':>8s} {'累计':>8s} {'胜率':>6s}")
    print(f"  {'─'*40}")
    for year in sorted(yearly_stats.keys()):
        y_returns = yearly_stats[year]
        y_cum = np.prod([1 + r for r in y_returns]) - 1
        y_avg = np.mean(y_returns)
        y_win = sum(1 for r in y_returns if r > 0) / len(y_returns)
        print(f"  {year:<6s} {len(y_returns):>5d} {y_avg:>+7.1%} {y_cum:>+7.1%} {y_win:>5.0%}")

    # Save trades
    trades_file = os.path.join(_PROJ, "outputs/trend_launch_backtest_trades.json")
    os.makedirs(os.path.dirname(trades_file), exist_ok=True)
    with open(trades_file, "w") as f:
        json.dump(all_trades, f, ensure_ascii=False, indent=2)
    print(f"\n  交易明细: {trades_file}")


if __name__ == "__main__":
    main()
