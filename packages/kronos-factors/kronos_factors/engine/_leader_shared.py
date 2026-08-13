"""龙头战法共享工具函数 — leader_intraday / leader_closing 复用。

从 leader_intraday.py 抽出的逐字节相同函数（依赖闭包干净，不触碰两文件
策略核心差异）。改此处即同时影响 intraday 与 closing。
"""
import numpy as np

TIME_COMPLETION = {
    "10:00": 0.15, "10:30": 0.25, "11:00": 0.35, "11:30": 0.45,
    "13:00": 0.48, "13:30": 0.55, "14:00": 0.65, "14:30": 0.78,
    "14:40": 0.85, "15:00": 1.00,
}

DEFAULT_PM_RATIO = 0.20

def get_adjusted_completion(db, code, trade_date, time_slot, cum_amount):
    """V4.3: adaptive completion ratio.

    With morning data -> standard TIME_COMPLETION.
    Afternoon-only -> pm_completion * stock_pm_ratio.
    """
    am_cnt = db.execute(
        "SELECT COUNT(*) as c FROM stk_mins WHERE ts_code LIKE ? "
        "AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:30", f"{trade_date} 11:30")
    ).fetchone()["c"]

    if am_cnt >= 5:
        return TIME_COMPLETION.get(time_slot, 0.65)

    # Afternoon-only: calculate pm bar completion
    pm_total_bars = 24  # 13:05-15:00
    hour = int(time_slot.split(":")[0])
    minute = int(time_slot.split(":")[1])
    pm_bars_done = max(1, ((hour - 13) * 12 + max(0, minute - 5) // 5))
    pm_completion = min(1.0, pm_bars_done / pm_total_bars)
    return pm_completion * DEFAULT_PM_RATIO

def get_cumulative_amount(db, code, trade_date, time_slot="14:00"):
    """获取当日截至指定时点的累计成交额和成交量.

    rt_min 返回的是单根K线数据, 需要累加当日所有K线得到累计值.
    用于修正预估全天成交额的计算.
    """
    row = db.execute(
        "SELECT SUM(amount) as total_amount, SUM(volume) as total_volume "
        "FROM stk_mins WHERE ts_code LIKE ? AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:00:00", f"{trade_date} {time_slot}:59")
    ).fetchone()
    if row and row["total_amount"]:
        return (float(row["total_amount"]), float(row["total_volume"] or 0))
    return (0, 0)

def get_day_range(db, code, trade_date, time_slot="14:00"):
    """获取当日截至指定时点的最高价和最低价."""
    row = db.execute(
        "SELECT MAX(high) as day_high, MIN(low) as day_low "
        "FROM stk_mins WHERE ts_code LIKE ? AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:00:00", f"{trade_date} {time_slot}:59")
    ).fetchone()
    if row:
        return (float(row["day_high"] or 0), float(row["day_low"] or 0))
    return (0, 0)

def get_baseline_stats(db, code, trade_date):
    """获取上午均价作为基准 (优先上午, 无上午数据则用当日最早3根K线).

    解决盘中首次启动时缺少上午数据的退化问题.
    """
    # 1. Try morning session (9:30-11:30)
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount FROM stk_mins "
        "WHERE ts_code LIKE ? AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:30", f"{trade_date} 11:30")
    ).fetchall()
    if rows and len(rows) >= 3:
        total_amount = sum(float(r["amount"] or 0) for r in rows)
        total_volume = sum(float(r["volume"] or 0) for r in rows)
        high = max(float(r["high"] or 0) for r in rows)
        low = min(float(r["low"] or 0) for r in rows)
        vwap = total_amount / total_volume if total_volume > 0 else 0
        return (vwap, total_volume, high, low, True)  # True = full data

    # 2. Fallback: use first 3 available bars of the day as baseline
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount FROM stk_mins "
        "WHERE ts_code LIKE ? AND trade_time LIKE ? AND freq='5min' "
        "ORDER BY trade_time ASC LIMIT 3",
        (f"{code}%", f"{trade_date}%")
    ).fetchall()
    if rows and len(rows) >= 2:
        total_amount = sum(float(r["amount"] or 0) for r in rows)
        total_volume = sum(float(r["volume"] or 0) for r in rows)
        high = max(float(r["high"] or 0) for r in rows)
        low = min(float(r["low"] or 0) for r in rows)
        vwap = total_amount / total_volume if total_volume > 0 else 0
        return (vwap, total_volume, high, low, False)  # False = partial data
    return (0, 0, 0, 0, False)

def get_recent_volume_surge(db, code, trade_date, time_slot="14:00"):
    """获取最近5根5分钟K线量 vs 基准均量.

    优先用上午均量, 无上午数据则用当日所有可用K线的均量.
    """
    # Baseline: try morning first
    am_bars = db.execute(
        "SELECT volume FROM stk_mins WHERE ts_code LIKE ? "
        "AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:30", f"{trade_date} 11:30")
    ).fetchall()

    if am_bars and len(am_bars) >= 3:
        baseline_vol = np.mean([float(r["volume"] or 0) for r in am_bars])
    else:
        # Fallback: use all today's bars as baseline
        all_bars = db.execute(
            "SELECT volume FROM stk_mins WHERE ts_code LIKE ? "
            "AND trade_time LIKE ? AND freq='5min'",
            (f"{code}%", f"{trade_date}%")
        ).fetchall()
        if all_bars and len(all_bars) >= 2:
            baseline_vol = np.mean([float(r["volume"] or 0) for r in all_bars])
        else:
            return 1.0

    if baseline_vol == 0:
        return 1.0

    # Recent bars (afternoon)
    recent = db.execute(
        "SELECT volume FROM stk_mins WHERE ts_code LIKE ? "
        "AND trade_time >= ? AND trade_time <= ? AND freq='5min' ORDER BY trade_time DESC LIMIT 5",
        (f"{code}%", f"{trade_date} 13:00", f"{trade_date} {time_slot}")
    ).fetchall()
    if not recent or len(recent) == 0:
        return 1.0
    recent_avg = np.mean([float(r["volume"] or 0) for r in recent])
    return recent_avg / baseline_vol

def estimate_full_day_amount(intraday_amount, time_slot="14:00"):
    ratio = TIME_COMPLETION.get(time_slot, 0.65)
    return intraday_amount / max(0.01, ratio)

def get_intraday_limit_status(db, trade_date):
    """获取当日涨停板列表."""
    td = trade_date.replace('-', '')
    rows = db.execute(
        "SELECT ts_code, first_time, fd_amount, open_times, up_stat "
        "FROM limit_list_d WHERE trade_date=? AND pct_chg > 0", (td,)
    ).fetchall()
    limit_map = {}
    for r in rows:
        code = (r.get("code") or r.get("ts_code","")).split('.')[0]
        ft = r["first_time"] or ""
        limit_map[code] = {
            "first_time": ft,
            "fd_amount_yi": (r["fd_amount"] or 0) / 1e8,
            "open_times": r["open_times"] or 0,
            "up_stat": r["up_stat"] or "",
            "is_sealed_by_14": ft and ft <= "140000",
        }
    return limit_map

def compute_ma(closes, period):
    if len(closes) < period: return None
    return float(np.mean(closes[-period:]))

def get_kline_data(db, code, trade_date, lookback=60):
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount, trade_date "
        "FROM daily_kline WHERE code=? AND trade_date<=? ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    return rows

def get_shanghai_index(db, trade_date):
    # PG index_daily.code stores bare '000001'; inline literal isn't translated by pg_adapter.
    row = db.execute(
        "SELECT pct_chg FROM index_daily WHERE ts_code='000001' AND trade_date=?", (trade_date,)
    ).fetchone()
    return row["pct_chg"] if row else 0

def _prefetch_mins_agg_batch(db, trade_date, time_slot):
    """批量预取所有股票的 stk_mins 聚合, 替代 4 个 per-stock 查询.

    合并: baseline_stats + volume_surge + cumulative_amount + day_range
    节省 ~60ms × N 只股票 (占总耗时 60%).
    返回: {code: {vwap, am_vol, am_bars, cum_amount, cum_volume, day_high, day_low, pm_avg_vol, am_avg_vol}}
    """
    morning_end = f"{trade_date} 11:30:59"
    afternoon_start = f"{trade_date} 13:00:00"
    time_start = f"{trade_date} 09:00:00"
    time_end = f"{trade_date} {time_slot}:59"

    rows = db.execute(
        "SELECT SUBSTR(ts_code,1,6) as code, "
        "AVG(CASE WHEN trade_time <= ? THEN close END) as am_vwap, "
        "SUM(CASE WHEN trade_time <= ? THEN volume END) as am_vol, "
        "MAX(CASE WHEN trade_time <= ? THEN high END) as am_high, "
        "MIN(CASE WHEN trade_time <= ? THEN low END) as am_low, "
        "COUNT(CASE WHEN trade_time <= ? THEN 1 END) as am_bars, "
        "SUM(amount) as cum_amount, SUM(volume) as cum_volume, "
        "MAX(high) as day_high, MIN(low) as day_low, "
        "AVG(CASE WHEN trade_time >= ? THEN volume END) as pm_avg_vol, "
        "AVG(CASE WHEN trade_time <= ? THEN volume END) as am_avg_vol "
        "FROM stk_mins WHERE trade_time >= ? AND trade_time <= ? AND freq='5min' "
        "GROUP BY SUBSTR(ts_code,1,6)",
        (morning_end,) * 5 + (afternoon_start, morning_end, time_start, time_end)
    ).fetchall()

    result = {}
    for r in rows:
        code = r.get("code", "")
        if not code:
            continue
        am_bars = int(r["am_bars"] or 0)
        am_vol = float(r["am_vol"] or 0)
        result[code] = {
            "vwap": float(r["am_vwap"] or 0),
            "am_vol": am_vol,
            "am_high": float(r["am_high"] or 0),
            "am_low": float(r["am_low"] or 0),
            "am_bars": am_bars,
            "has_full": am_bars >= 5,
            "cum_amount": float(r["cum_amount"] or 0),
            "cum_volume": float(r["cum_volume"] or 0),
            "day_high": float(r["day_high"] or 0),
            "day_low": float(r["day_low"] or 0),
            "pm_avg_vol": float(r["pm_avg_vol"] or 0),
            "am_avg_vol": float(r["am_avg_vol"] or 0),
        }
    return result

def get_latest_rt_slot(db, trade_date):
    """Get the latest available time slot from RT stk_mins data.

    Returns: (time_slot_str, stock_count, slot_count)
      e.g., ("14:00", 5515, 38) means 5515 stocks at 14:00, 38/48 total slots complete.
    """
    row = db.execute(
        "SELECT SUBSTR(trade_time,12,5) as tm, COUNT(DISTINCT ts_code) as cnt "
        "FROM stk_mins WHERE trade_time LIKE ? "
        "GROUP BY tm ORDER BY tm DESC LIMIT 1",
        (f"{trade_date}%",)
    ).fetchone()
    if not row:
        return (None, 0, 0)

    latest_slot = row["tm"]
    stock_cnt = row["cnt"]

    # Count total slots available
    total_slots_row = db.execute(
        "SELECT COUNT(DISTINCT SUBSTR(trade_time,12,5)) as cnt "
        "FROM stk_mins WHERE trade_time LIKE ?",
        (f"{trade_date}%",)
    ).fetchone()
    total_slots = total_slots_row["cnt"] if total_slots_row else 0

    return (latest_slot, stock_cnt, total_slots)

def get_rt_market_breadth(db, trade_date, time_slot):
    """从 RT stk_mins + daily_kline 计算实时市场涨跌比。

    使用前日收盘价作为基准（daily_kline 前日 close）。
    """
    prev_date_row = db.execute(
        "SELECT trade_date FROM daily_kline WHERE trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 1", (trade_date,)
    ).fetchone()
    if not prev_date_row:
        return (0, 0, 0)
    prev_date = prev_date_row["trade_date"]

    row = db.execute(
        "SELECT "
        "SUM(CASE WHEN m.close > d.close THEN 1 ELSE 0 END) as up, "
        "SUM(CASE WHEN m.close < d.close THEN 1 ELSE 0 END) as down "
        "FROM stk_mins m "
        "JOIN daily_kline d ON d.code=SUBSTR(m.ts_code,1,6) AND d.trade_date=? "
        "WHERE m.trade_time LIKE ? AND d.close > 0",
        (prev_date, f"{trade_date} {time_slot}%")
    ).fetchone()
    if not row:
        return (0, 0, 0)
    up = row["up"] or 0
    down = row["down"] or 0
    total = up + down
    return (up, down, round(up/total*100, 1) if total > 0 else 0)
