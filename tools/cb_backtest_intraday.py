#!/usr/bin/env python3
"""可转债日内选债回测 — 入场竞价开盘 + 出场分时 VWAP/KDJ 信号.

与 cb_backtest.py 的区别:
  - 入场: cb_daily.open (竞价开盘价)
  - 出场: 正股 stk_mins 分时信号 (close > VWAP AND KDJ_J > 90)
  - 收益: 日内 (出场价 - 入场价) / 入场价
  - 时间: 不超过当日收盘

Usage:
    KRONOS_PG_URL="postgresql://..." python3 tools/cb_backtest_intraday.py --days 10 --top-n 10
"""

import argparse, os, sys, time, pickle
import numpy as np
from collections import defaultdict
from datetime import date, datetime, timedelta

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ, "packages", "kronos-factors"))
sys.path.insert(0, _PROJ)

import psycopg2
from tools.cb_intraday_exit import (find_exit_signal, estimate_cb_exit_price,
    find_exit_info, find_stop_loss, find_take_profit, check_entry_quality,
    find_trailing_stop, adaptive_take_profit_target, generate_trade_signals)

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def get_trade_dates(conn, days_back: int) -> list[str]:
    """Get last N trading dates that have both cb_daily AND stk_mins data."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT d.trade_date
        FROM cb_daily d
        WHERE EXISTS (
            SELECT 1 FROM stk_mins m
            WHERE DATE(m.trade_time) = d.trade_date AND m.freq = '5min'
        )
        ORDER BY d.trade_date DESC
        LIMIT %s
    """, (days_back,))
    return [str(r[0]) for r in cur.fetchall()]


def load_stock_mins(conn, stock_code: str, trade_date: str) -> list[dict]:
    """Load 5-min bars for a stock on a given date."""
    cur = conn.cursor()
    cur.execute("""
        SELECT trade_time, open, high, low, close, volume, amount
        FROM stk_mins
        WHERE code = %s AND DATE(trade_time) = %s AND freq = '5min'
        ORDER BY trade_time
    """, (stock_code, trade_date))
    rows = cur.fetchall()
    if not rows:
        return []
    return [
        {
            "time": str(r[0])[-8:],
            "open": float(r[1] or 0),
            "high": float(r[2] or 0),
            "low": float(r[3] or 0),
            "close": float(r[4] or 0),
            "volume": float(r[5] or 0),
            "amount": float(r[6] or 0),
        }
        for r in rows
    ]


def get_cb_open_and_stock(conn, ts_code: str, stk_code: str, trade_date: str) -> dict:
    """Get CB opening price and underlying stock open from cb_daily + daily_kline."""
    cur = conn.cursor()
    # CB open
    cur.execute(
        "SELECT open FROM cb_daily WHERE ts_code = %s AND trade_date = %s",
        (ts_code, trade_date),
    )
    row = cur.fetchone()
    cb_open = float(row[0]) if row and row[0] else None

    # Stock open
    cur.execute(
        "SELECT open FROM daily_kline WHERE code = %s AND trade_date = %s",
        (stk_code, trade_date),
    )
    row = cur.fetchone()
    stock_open = float(row[0]) if row and row[0] else None

    return {"cb_open": cb_open, "stock_open": stock_open}


def run_intraday_backtest(days_back: int = 10, top_n: int = 10):
    """Run intraday backtest for CB screening."""
    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)

    print(f"回测模式: cb_intraday V4 日内交易")
    print(f"回测天数: {len(trade_dates)} 个交易日 (含 stk_mins 数据)")
    print(f"每期选债: Top {top_n}")
    print(f"出场策略: stop_loss(VWAP下30min) > KDJ_J>95 > 收盘")
    print(f"仓位倾斜: A级2x / B级1x / C级0.5x")
    print(f"{'='*80}")

    from kronos_factors.engine.cb_intraday import CbIntradayEngine

    all_trades = []
    stats = {
        "days": 0, "total_picks": 0, "trades_with_signal": 0,
        "trades_no_signal": 0, "trades_no_data": 0,
        "returns": [], "signal_returns": [], "close_returns": [],
        "hold_minutes": [],
    }

    for td in trade_dates:
        # ── Morning: run engine to select CBs ──
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(trade_date=td, top_n=top_n)
        engine.close()

        if not picks:
            continue

        stats["days"] += 1
        stats["total_picks"] += len(picks)

        # Opt 3: Get market environment once per date
        try:
            market_cur = conn.cursor()
            market_drop = get_market_drop(market_cur, td)
            market_cur.close()
        except Exception:
            market_drop = None
        finally:
            try: conn.rollback()
            except: pass

        for p in picks:
            ts_code = p["code"]
            stk_code = p["stk_code"]
            name = p.get("name", ts_code)

            # ── Get CB open price ──
            try:
                price_info = get_cb_open_and_stock(conn, ts_code, stk_code, td)
                cb_open = price_info["cb_open"]
            except Exception:
                try: conn.rollback()
                except: pass
                stats["trades_no_data"] += 1
                continue
            stock_open = price_info["stock_open"]

            if cb_open is None or cb_open <= 0:
                stats["trades_no_data"] += 1
                continue

            # ── Load intraday data and find exit signal ──
            bars = load_stock_mins(conn, stk_code, td)

            if len(bars) < 10:
                stats["trades_no_data"] += 1
                continue

            # ── Entry quality filter ──
            if not check_entry_quality(bars, min_bars=3):
                stats["trades_no_data"] += 1
                continue

            # Adaptive take-profit target
            stock_atr_pct = get_stock_atr_pct(conn, stk_code, td)
            try: conn.rollback()
            except: pass
            tp_target = adaptive_take_profit_target(stock_atr_pct)

            # Opt 1: Take-profit (highest priority)
            take_profit = find_take_profit(bars, cb_open, stock_open or 0, target_pct=tp_target, skip_bars=3) if stock_open else None

            # Opt: Trailing stop (percentage-based, faster than VWAP time stop)
            trailing_stop = find_trailing_stop(bars, pct_from_high=2.0, skip_bars=6)

            # Opt 3: VWAP time stop (fallback)
            market_weak = market_drop is not None and market_drop < -1.0
            sl_minutes = 30 if market_weak else 45
            stop_loss = find_stop_loss(bars, below_vwap_minutes=sl_minutes, skip_bars=6, min_pct_below=0.5)

            # Opt 3+4: Stricter J when market weak / early session
            j_base = 100 if market_weak else 95
            exit_info = find_exit_info(bars)
            if exit_info["signal"]:
                bar_i = exit_info["signal"]["bar_index"]
                early_threshold = 105 if market_weak else 100
                j_min = early_threshold if bar_i < 12 else j_base
                if exit_info["signal"]["kdj_j"] <= j_min:
                    exit_info["signal"] = None

            # Priority: take_profit > trailing_stop > stop_loss > KDJ signal > close
            if take_profit:
                sig = take_profit
            elif trailing_stop:
                sig = trailing_stop
            elif stop_loss:
                sig = stop_loss
            else:
                sig = exit_info["signal"]

            if sig:
                # Opt 2: Dynamic delta based on premium rate
                premium_rate = p.get("premium_rate")
                cb_exit = estimate_cb_exit_price(cb_open, stock_open or 0, sig["close"], premium_rate)
                intraday_ret = (cb_exit - cb_open) / cb_open * 100
                hold_min = sig["bar_index"] * 5

                exit_type = sig.get("type", "signal")
                if exit_type == "take_profit":
                    exit_method = f"take_profit@{sig['time']}"
                elif exit_type == "trailing_stop":
                    exit_method = f"trailing_stop@{sig['time']}"
                elif exit_type == "stop_loss":
                    exit_method = f"stop_loss@{sig['time']}"
                else:
                    exit_method = f"signal@{sig['time']}"

                stats["trades_with_signal"] += 1
                stats["signal_returns"].append(intraday_ret)
                stats["returns"].append(intraday_ret)
                stats["hold_minutes"].append(hold_min)
            else:
                cb_close = get_cb_close(conn, ts_code, td)
                if cb_close is None:
                    stats["trades_no_data"] += 1
                    continue

                intraday_ret = (cb_close - cb_open) / cb_open * 100
                hold_min = len(bars) * 5

                stats["trades_no_signal"] += 1
                stats["returns"].append(intraday_ret)
                exit_method = "close"

            # Opt 4: Grade-weighted position
            grade_weight = {"S": 2.0, "A": 2.0, "B": 1.0, "C": 0.5}.get(p["grade"], 1.0)

            all_trades.append({
                "date": td, "code": ts_code, "name": name, "stk_code": stk_code,
                "score": p["total_score"], "grade": p["grade"],
                "grade_weight": grade_weight,
                "sector": p["sector"], "premium_rate": p["premium_rate"],
                "cb_open": round(cb_open, 2),
                "cb_exit": round(cb_exit if sig else (cb_close or cb_open), 2),
                "intraday_return": round(intraday_ret, 2),
                "weighted_return": round(intraday_ret * grade_weight, 2),
                "exit_method": exit_method,
                "signal_j": sig.get("kdj_j") if sig and "kdj_j" in sig else None,
                "tp_target": tp_target, "atr_pct": stock_atr_pct,
                "hold_min": hold_min,
            })

    conn.close()

    # ── Results ──
    print(f"\n{'='*80}")
    print(f"回测结果汇总")
    print(f"{'='*80}")
    print(f"有效交易日: {stats['days']}")
    print(f"总选债次数: {stats['total_picks']}")
    print(f"有信号出场: {stats['trades_with_signal']} ({stats['trades_with_signal']/max(1,stats['trades_with_signal']+stats['trades_no_signal'])*100:.0f}%)")
    print(f"无信号(收盘): {stats['trades_no_signal']}")
    print(f"数据缺失: {stats['trades_no_data']}")

    def _stats(name, values):
        if not values:
            return f"{name}: 无数据"
        avg = sum(values) / len(values)
        win = sum(1 for v in values if v > 0) / len(values) * 100
        pos = [v for v in values if v > 0]
        neg = [v for v in values if v <= 0]
        return (f"{name}: 均值={avg:+.2f}%  胜率={win:.1f}%  "
                f"最大={max(values):+.2f}%  最小={min(values):+.2f}%  "
                f"样本={len(values)}")

    print(f"\n{'─'*60}")
    print("全部交易 (等权):")
    print(_stats("日内收益", stats["returns"]))
    weighted_rets = [t["weighted_return"] / t["grade_weight"] for t in all_trades]
    weighted_total = [t["weighted_return"] for t in all_trades]
    if weighted_total:
        print(f"\nOpt4 仓位倾斜后 (A:2x B:1x C:0.5x):")
        print(_stats("加权日内收益", weighted_total))

    if stats["signal_returns"]:
        print(f"\n有信号出场 (含止损):")
        print(_stats("日内收益", stats["signal_returns"]))
        # Split by type
        tp_rets = [t["intraday_return"] for t in all_trades if t["exit_method"].startswith("take_profit")]
        ts_rets = [t["intraday_return"] for t in all_trades if t["exit_method"].startswith("trailing_stop")]
        kdj_rets = [t["intraday_return"] for t in all_trades if t["exit_method"].startswith("signal@")]
        sl_rets = [t["intraday_return"] for t in all_trades if t["exit_method"].startswith("stop_loss")]
        if tp_rets:
            # Show adaptive take-profit distribution
            tp_targets = set(t.get("tp_target", 3.0) for t in all_trades if t["exit_method"].startswith("take_profit"))
            tp_desc = f"自适应止盈({','.join(f'{x:.0f}%' for x in sorted(tp_targets))})"
            print(f"  其中{tp_desc}: {_stats('收益', tp_rets)}")
        if ts_rets:
            print(f"  其中回撤止损(-2%): {_stats('收益', ts_rets)}")
        if kdj_rets:
            print(f"  其中KDJ信号: {_stats('收益', kdj_rets)}")
        if sl_rets:
            print(f"  其中VWAP止损: {_stats('收益', sl_rets)}")
        if stats["hold_minutes"]:
            avg_hold = sum(stats["hold_minutes"]) / len(stats["hold_minutes"])
            print(f"平均持仓: {avg_hold:.0f} 分钟")

    if stats["trades_no_signal"] > 0:
        close_rets = [t["intraday_return"] for t in all_trades if t["exit_method"] == "close"]
        if close_rets:
            print(f"\n无信号(持有到收盘):")
            print(_stats("日内收益", close_rets))

    # ── Grade breakdown ──
    print(f"\n{'─'*60}")
    print("按等级分布:")
    grade_stats = defaultdict(list)
    for t in all_trades:
        grade_stats[t["grade"]].append(t["intraday_return"])

    for g in ["S", "A", "B", "C"]:
        if g not in grade_stats:
            continue
        vals = grade_stats[g]
        avg = sum(vals) / len(vals)
        win = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(f"  {g}级: {len(vals)}只  均值={avg:+.2f}%  胜率={win:.1f}%")

    # ── Detail: latest day ──
    print(f"\n{'─'*60}")
    print("最近一期交易明细:")
    last_date = max(t["date"] for t in all_trades) if all_trades else ""
    last_trades = [t for t in all_trades if t["date"] == last_date]
    for i, t in enumerate(last_trades[:top_n], 1):
        sig_str = f"J={t['signal_j']}" if t["signal_j"] else "收盘"
        print(f"  {i}. {t['name']}({t['code']})  "
              f"入场:{t['cb_open']}→出场:{t['cb_exit']}  "
              f"收益:{t['intraday_return']:+.2f}%  "
              f"出场:{t['exit_method']}  {sig_str}  "
              f"{t['grade']}级")

    # ── Sector analysis ──
    print(f"\n{'─'*60}")
    print("按板块分析 (signal trades only):")
    sector_stats = defaultdict(list)
    for t in all_trades:
        if t["exit_method"] != "close":
            sector_stats[t["sector"]].append(t["intraday_return"])
    for sec, vals in sorted(sector_stats.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)[:10]:
        avg = sum(vals) / len(vals)
        win = sum(1 for v in vals if v > 0) / len(vals) * 100
        print(f"  {sec}: {len(vals)}次  均值={avg:+.2f}%  胜率={win:.0f}%")


def get_stock_atr_pct(conn, stk_code: str, trade_date: str) -> float or None:
    """计算正股近5日平均振幅(ATR%)作为波动率代理."""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT AVG(range_pct) FROM (
                SELECT (high - low) / NULLIF(close, 0) * 100 as range_pct
                FROM daily_kline
                WHERE code = %s AND trade_date < %s
                ORDER BY trade_date DESC LIMIT 5
            ) sub
        """, (stk_code, trade_date))
        row = cur.fetchone()
        cur.close()
        return float(row[0]) if row and row[0] else None
    except Exception:
        try: conn.rollback()
        except: pass
        return None


def get_market_drop(cur, trade_date: str) -> float or None:
    """获取上证指数当日涨跌幅."""
    try:
        cur.execute(
            "SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=%s",
            (trade_date,),
        )
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        cur.execute("ROLLBACK")
        return None


def get_cb_close(conn, ts_code: str, trade_date: str) -> float:
    """Get CB closing price."""
    cur = conn.cursor()
    cur.execute(
        "SELECT close FROM cb_daily WHERE ts_code = %s AND trade_date = %s",
        (ts_code, trade_date),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] else None


def run_grid_search(days_back: int = 10, top_n: int = 10):
    """网格搜索最优因子权重.

    基于实际日内收益, 遍历权重组合, 按加权评分重新排序后计算收益.
    """
    print(f"\n{'='*80}")
    print(f"因子权重网格搜索 (基于日内实际收益)")
    print(f"{'='*80}")

    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)
    conn.close()

    # ── Step 1: Collect all raw picks with factor scores across all dates ──
    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    all_raw = []  # [(date, code, {factor_scores}, actual_return)]

    for td in trade_dates:
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(trade_date=td, top_n=50)  # get more picks for re-ranking
        engine.close()
        if not picks:
            continue
        for p in picks:
            d = p.get("details", {})
            all_raw.append({
                "date": td,
                "code": p["code"],
                "stk_code": p.get("stk_code", ""),
                "sector_score": d.get("sector_score", 50),
                "premium_score": d.get("premium_score", 50),
                "momentum_score": d.get("momentum_score", 50),
                "liquidity_score": d.get("liquidity_score", 50),
                "rev_bonus": d.get("rev_bonus", 0),
                "call_penalty": d.get("call_penalty", 0),
                "price": p.get("price"),
            })

    if len(all_raw) < 50:
        print("Not enough raw data for grid search")
        return

    # ── Step 2: Get actual intraday returns for all picks ──
    conn = psycopg2.connect(PG_URL)
    for item in all_raw:
        td = item["date"]
        code = item["stk_code"]
        # Get stock open and close
        cur = conn.cursor()
        cur.execute("SELECT open FROM daily_kline WHERE code=%s AND trade_date=%s", (code, td))
        row = cur.fetchone()
        stock_open = float(row[0]) if row and row[0] else None

        # Get CB open
        cur.execute("SELECT open FROM cb_daily WHERE ts_code=%s AND trade_date=%s", (item["code"], td))
        row = cur.fetchone()
        cb_open = float(row[0]) if row and row[0] else None

        if cb_open and cb_open > 0 and stock_open and stock_open > 0:
            # Load stk_mins and find exit
            bars = load_stock_mins(conn, code, td)
            if len(bars) >= 10:
                stop_loss = find_stop_loss(bars, below_vwap_minutes=45, skip_bars=6, min_pct_below=0.5)
                exit_info = find_exit_info(bars)
                sig = exit_info["signal"]
                if sig and sig.get("kdj_j", 0) <= 95:
                    sig = None
                if stop_loss:
                    sig = stop_loss
                if sig:
                    cb_exit = estimate_cb_exit_price(cb_open, stock_open, sig["close"])
                else:
                    cur.execute("SELECT close FROM cb_daily WHERE ts_code=%s AND trade_date=%s", (item["code"], td))
                    row = cur.fetchone()
                    cb_exit = float(row[0]) if row and row[0] else cb_open
                item["actual_return"] = (cb_exit - cb_open) / cb_open * 100
            else:
                item["actual_return"] = None
        else:
            item["actual_return"] = None
    conn.close()

    # ── Step 3: Grid search over weights ──
    weight_combos = []
    for s in range(20, 50, 5):
        for p in range(15, 40, 5):
            for m in range(10, 35, 5):
                l = 100 - s - p - m
                if 10 <= l <= 35:
                    weight_combos.append((s, p, m, l))

    print(f"测试 {len(weight_combos)} 组权重, {len(all_raw)} 个原始 pick...")

    best = {"mean_ret": -999, "win_rate": 0, "weights": None}
    results = []

    for wi, (ws, wp, wm, wl) in enumerate(weight_combos):
        # Re-score and re-rank within each date
        date_picks = defaultdict(list)
        for item in all_raw:
            new_score = (item["sector_score"] * ws / 100.0
                         + item["premium_score"] * wp / 100.0
                         + item["momentum_score"] * wm / 100.0
                         + item["liquidity_score"] * wl / 100.0
                         + item["rev_bonus"]
                         + item["call_penalty"])
            item["new_score"] = new_score
            date_picks[item["date"]].append(item)

        # Take top-N by new score per date
        returns = []
        for td, items in date_picks.items():
            items.sort(key=lambda x: x["new_score"], reverse=True)
            for item in items[:top_n]:
                if item["actual_return"] is not None:
                    returns.append(item["actual_return"])

        if len(returns) >= 20:
            avg_ret = sum(returns) / len(returns)
            win = sum(1 for r in returns if r > 0) / len(returns) * 100
            results.append({"weights": (ws, wp, wm, wl), "mean": avg_ret, "win": win, "n": len(returns)})
            if avg_ret > best["mean_ret"]:
                best = {"mean_ret": avg_ret, "win_rate": win, "weights": (ws, wp, wm, wl)}

        if (wi + 1) % 30 == 0:
            print(f"  {wi+1}/{len(weight_combos)}... current best: {best['weights']} "
                  f"mean={best['mean_ret']:+.2f}% win={best['win_rate']:.1f}%")

    # ── Print top results ──
    results.sort(key=lambda x: x["mean"], reverse=True)
    print(f"\n最优权重组合 (Top 10):")
    print(f"{'排名':<5} {'sector':<8} {'premium':<8} {'momentum':<9} {'liquidity':<9} {'均值':<8} {'胜率':<6} {'样本':<5}")
    for i, r in enumerate(results[:10], 1):
        ws, wp, wm, wl = r["weights"]
        print(f"  {i:<3} {ws}%{'':<3} {wp}%{'':<3} {wm}%{'':<4} {wl}%{'':<4} "
              f"{r['mean']:+.2f}%  {r['win']:.1f}%  {r['n']}")

    # Current weights for comparison
    print(f"\n当前权重 (35/25/20/20) 对比:")
    for r in results:
        if r["weights"] == (35, 25, 20, 20):
            print(f"  sector=35% premium=25% momentum=20% liquidity=20%: "
                  f"mean={r['mean']:+.2f}% win={r['win']:.1f}% n={r['n']}")
            break


def generate_live_signals(top_n: int = 15, trade_date: str = None):
    """生成实时交易信号 — 用于开盘后执行."""
    from kronos_factors.engine.cb_intraday import CbIntradayEngine

    conn = psycopg2.connect(PG_URL)
    engine = CbIntradayEngine(pg_url=PG_URL)
    picks = engine.run(trade_date=trade_date, top_n=top_n)
    engine.close()

    if not picks:
        print("无选股结果")
        conn.close()
        return

    # Resolve effective date (use cb_daily latest date for daily data)
    cur = conn.cursor()
    cur.execute("SELECT MAX(trade_date) FROM cb_daily")
    row = cur.fetchone()
    effective_date = trade_date or (str(row[0]) if row and row[0] else "")
    cur.close()

    # Pre-fetch ATR and today's open for each pick
    atr_map = {}
    entry_prices = {}
    for p in picks:
        stk = p.get("stk_code", "")
        if stk:
            atr_map[stk] = get_stock_atr_pct(conn, stk, effective_date)
            # Get latest CB open as entry proxy (live would use auction)
            cur2 = conn.cursor()
            cur2.execute("SELECT open FROM cb_daily WHERE ts_code=%s AND trade_date=%s",
                         (p["code"], effective_date))
            row = cur2.fetchone()
            entry_prices[p["code"]] = float(row[0]) if row and row[0] else p.get("price")
            cur2.close()
            try: conn.rollback()
            except: pass

    conn.close()

    # Patch entry prices from cb_daily.open
    for p in picks:
        if p["code"] in entry_prices and entry_prices[p["code"]]:
            p["price"] = entry_prices[p["code"]]

    # Generate signals
    signals = generate_trade_signals(picks[:top_n], atr_map)

    # ── Output ──
    print(f"\n{'='*90}")
    print(f"📊 匪爷可转债日内交易信号  |  {effective_date or '最新交易日'}")
    print(f"{'='*90}")
    print(f"{'#':<3} {'转债':<10} {'正股':<7} {'入场':<9} {'止盈价':<10} {'止损价':<9} "
          f"{'ATR%':<5} {'溢价%':<6} {'板块':<6} {'得分':<5} {'等级':<3}")
    print(f"{'-'*90}")

    for i, s in enumerate(signals[:top_n], 1):
        tp_str = f"{s['take_profit_price']}" if s['take_profit_price'] else "N/A"
        sl_str = f"{s['stop_loss_price']}" if s['stop_loss_price'] else "N/A"
        sec = (s.get('sector', '') or '')[:6]
        print(f"{i:<3} {s['name']:<10} {s['stk_code']:<7} {s['entry_price']:<9} "
              f"{tp_str:<10} {sl_str:<9} {s['atr_pct'] or 'N/A':<5} "
              f"{s['premium_rate'] or 'N/A':<6} {sec:<6} {s.get('total_score',0):<5.0f} {s['grade']:<3}")

    print(f"{'-'*90}")
    print(f"出场规则: ①止盈价触发 → 马上卖  ②回撤-2%从高点 → 马上卖  ③KDJ_J>95+VWAP上方 → 卖  ④14:30前未触发 → 尾盘平仓")
    print(f"风险控制: 单日累计亏损3%停止交易 | 连续3笔止损停止交易 | A级最多15%仓位")

    return signals


def run_ml_backtest(days_back: int = 35, top_n: int = 15):
    """ML 模型回测 — 用 LightGBM 替代线性评分排序."""
    print(f"回测模式: cb_intraday V5 (ML内置)")
    print(f"回测天数: {days_back} 个交易日")
    print(f"每期选债: Top {top_n} (引擎已含ML排序+阈值过滤)")
    print(f"{'='*80}")

    from kronos_factors.engine.cb_intraday import CbIntradayEngine
    conn = psycopg2.connect(PG_URL)
    trade_dates = get_trade_dates(conn, days_back)

    all_trades = []
    stats = {"days": 0, "total_picks": 0, "trades_with_signal": 0,
             "trades_no_signal": 0, "trades_no_data": 0,
             "returns": [], "signal_returns": [], "close_returns": [],
             "hold_minutes": []}

    for td in trade_dates:
        # V5: engine handles ML re-ranking + threshold internally
        engine = CbIntradayEngine(pg_url=PG_URL)
        picks = engine.run(trade_date=td, top_n=top_n, use_ml=True)
        engine.close()
        if not picks:
            continue

        # Rest of backtest identical to original...
        stats["days"] += 1
        stats["total_picks"] += len(picks)

        try:
            market_cur = conn.cursor()
            market_drop = get_market_drop(market_cur, td)
            market_cur.close()
        except Exception:
            market_drop = None
        finally:
            try: conn.rollback()
            except: pass

        for p in picks:
            ts_code = p["code"]; stk_code = p["stk_code"]; name = p.get("name", ts_code)
            try:
                price_info = get_cb_open_and_stock(conn, ts_code, stk_code, td)
                cb_open = price_info["cb_open"]
            except Exception:
                try: conn.rollback()
                except: pass
                stats["trades_no_data"] += 1; continue

            stock_open = price_info["stock_open"]
            if not cb_open or cb_open <= 0:
                stats["trades_no_data"] += 1; continue

            bars = load_stock_mins(conn, stk_code, td)
            if len(bars) < 10:
                stats["trades_no_data"] += 1; continue
            if not check_entry_quality(bars, min_bars=3):
                stats["trades_no_data"] += 1; continue

            stock_atr_pct = get_stock_atr_pct(conn, stk_code, td)
            try: conn.rollback()
            except: pass
            tp_target = adaptive_take_profit_target(stock_atr_pct)

            take_profit = find_take_profit(bars, cb_open, stock_open or 0, target_pct=tp_target, skip_bars=3) if stock_open else None
            trailing_stop = find_trailing_stop(bars, pct_from_high=2.0, skip_bars=6)
            market_weak = market_drop is not None and market_drop < -1.0
            sl_minutes = 30 if market_weak else 45
            stop_loss = find_stop_loss(bars, below_vwap_minutes=sl_minutes, skip_bars=6, min_pct_below=0.5)
            j_base = 100 if market_weak else 95
            exit_info = find_exit_info(bars)
            if exit_info["signal"]:
                bar_i = exit_info["signal"]["bar_index"]
                early_threshold = 105 if market_weak else 100
                j_min = early_threshold if bar_i < 12 else j_base
                if exit_info["signal"]["kdj_j"] <= j_min:
                    exit_info["signal"] = None

            if take_profit: sig = take_profit
            elif trailing_stop: sig = trailing_stop
            elif stop_loss: sig = stop_loss
            else: sig = exit_info["signal"]

            if sig:
                premium_rate = p.get("premium_rate")
                cb_exit = estimate_cb_exit_price(cb_open, stock_open or 0, sig["close"], premium_rate)
                intraday_ret = (cb_exit - cb_open) / cb_open * 100
                hold_min = sig["bar_index"] * 5
                exit_type = sig.get("type", "signal")
                exit_method = f"{exit_type}@{sig['time']}" if exit_type != "signal" else f"signal@{sig['time']}"
                stats["trades_with_signal"] += 1
                stats["signal_returns"].append(intraday_ret)
                stats["returns"].append(intraday_ret)
                stats["hold_minutes"].append(hold_min)
            else:
                cur = conn.cursor()
                cur.execute("SELECT close FROM cb_daily WHERE ts_code=%s AND trade_date=%s", (ts_code, td))
                row = cur.fetchone(); cur.close()
                cb_close = float(row[0]) if row and row[0] else None
                if cb_close is None:
                    stats["trades_no_data"] += 1; continue
                intraday_ret = (cb_close - cb_open) / cb_open * 100
                hold_min = len(bars) * 5
                stats["trades_no_signal"] += 1
                stats["returns"].append(intraday_ret)
                exit_method = "close"
                cb_exit = cb_close

            grade_weight = {"S": 2.0, "A": 2.0, "B": 1.0, "C": 0.5}.get(p.get("grade", "B"), 1.0)
            all_trades.append({
                "date": td, "code": ts_code, "name": name, "stk_code": stk_code,
                "score": p.get("total_score", 0), "ml_score": p.get("ml_score", 0) or 0,
                "grade": p.get("grade", "B"), "grade_weight": grade_weight,
                "sector": p.get("sector", ""), "premium_rate": p.get("premium_rate"),
                "cb_open": round(cb_open, 2), "cb_exit": round(cb_exit, 2),
                "intraday_return": round(intraday_ret, 2),
                "weighted_return": round(intraday_ret * grade_weight, 2),
                "exit_method": exit_method,
                "signal_j": sig.get("kdj_j") if sig and "kdj_j" in sig else None,
                "tp_target": tp_target, "atr_pct": stock_atr_pct,
                "hold_min": hold_min,
            })

    conn.close()

    # ── Results ──
    print(f"\n{'='*80}")
    print(f"ML 回测结果汇总")
    print(f"{'='*80}")
    print(f"有效交易日: {stats['days']}  总选债: {stats['total_picks']}")
    print(f"有信号: {stats['trades_with_signal']}  无信号: {stats['trades_no_signal']}  数据缺失: {stats['trades_no_data']}")

    def _s(name, vals):
        if not vals: return f"{name}: 无数据"
        return f"{name}: mean={np.mean(vals):+.2f}% win={sum(1 for v in vals if v>0)/len(vals)*100:.1f}% max={max(vals):+.2f}% min={min(vals):+.2f}% n={len(vals)}"

    print(f"\n全部交易:")
    print(_s("日内收益", stats["returns"]))
    weighted = [t["weighted_return"] for t in all_trades]
    if weighted:
        print(f"仓位加权: mean={np.mean(weighted):+.2f}% win={sum(1 for v in weighted if v>0)/len(weighted)*100:.1f}%")

    tp_rets = [t["intraday_return"] for t in all_trades if "take_profit" in t["exit_method"]]
    ts_rets = [t["intraday_return"] for t in all_trades if "trailing_stop" in t["exit_method"]]
    kdj_rets = [t["intraday_return"] for t in all_trades if t["exit_method"].startswith("signal@")]
    sl_rets = [t["intraday_return"] for t in all_trades if "stop_loss" in t["exit_method"] and "trailing" not in t["exit_method"]]
    print(f"\n出场分布:")
    if tp_rets: print(f"  止盈: {_s('', tp_rets)}")
    if ts_rets: print(f"  回撤止损: {_s('', ts_rets)}")
    if kdj_rets: print(f"  KDJ信号: {_s('', kdj_rets)}")
    if sl_rets: print(f"  VWAP止损: {_s('', sl_rets)}")

    # Grade breakdown
    gs = defaultdict(list)
    for t in all_trades: gs[t["grade"]].append(t["intraday_return"])
    print(f"\n按等级:")
    for g in ["A", "B", "C"]:
        if g in gs and gs[g]:
            print(f"  {g}级: {len(gs[g])}只 mean={np.mean(gs[g]):+.2f}% win={sum(1 for v in gs[g] if v>0)/len(gs[g])*100:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CB intraday backtest")
    parser.add_argument("--days", type=int, default=10, help="回测天数")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--grid-search", action="store_true", help="网格搜索最优权重")
    parser.add_argument("--signals", action="store_true", help="生成实时交易信号")
    parser.add_argument("--ml", action="store_true", help="用 ML 模型评分回测")
    parser.add_argument("--date", type=str, default=None, help="交易日期 YYYY-MM-DD")
    args = parser.parse_args()

    if args.signals:
        generate_live_signals(args.top_n, args.date)
    elif args.ml:
        run_ml_backtest(args.days, args.top_n)
    elif args.grid_search:
        run_grid_search(args.days, args.top_n)
    else:
        run_intraday_backtest(args.days, args.top_n)
