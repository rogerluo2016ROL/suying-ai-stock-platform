#!/usr/bin/env python3
"""盘中龙头短线战法 — Intraday Leader Scalp Strategy.

14:00 盘中选股，当日 14:00-15:00 买入，次日套利。

核心差异 (vs leader_scalp.py):
  - 数据源: stk_mins (5分钟K线) 代替 daily_kline
  - 涨幅: 14:00 实时涨幅 5-10% (vs 收盘 7-12%)
  - 成交额: 14:00 累计值 /0.65 预估全天
  - 封板: 实时状态 (已封/炸板中/拉升中)
  - 新增3因子: 午后强势度 + 封板可买性 + 盘中资金强度

Usage:
    python tools/leader_scalp_intraday.py --date 2026-06-05
    python tools/leader_scalp_intraday.py --date 2026-06-05 --time 13:30
    python tools/leader_scalp_intraday.py --date 2026-06-05 --top-n 15 --export /tmp/picks.json
"""
import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from kronos_factors.scorer._db_stub import _get_db

# ── Intraday scoring weights (9因子 V5.3 THS数据驱动) ──
# V5.3: THS概念数据已同步, sector_momentum/resonance 升权
INTRA_WEIGHTS = {
    "gain_quality": 20,              # 14:00涨幅质量
    "afternoon_strength": 20,        # 午后强势度
    "intraday_leadership": 12,       # 分时引领性
    "sector_leader": 14,             # 板块龙头
    "sector_momentum": 12,           # V5.3: 6→12, THS数据100%覆盖
    "turnover": 12,                  # 预估成交额
    "resonance": 10,                 # V5.3: 8→10, 板块+大盘共振
    "volume_surge": 8,               # 集中放量
    "ma_trend": 6,                   # 均线趋势
    "sector_climax_penalty": 12,     # P0: 板块高潮次日惩罚
}

# Full-day completion ratios for different time slots
# (assumes data from 9:30 onwards)
TIME_COMPLETION = {
    "10:00": 0.15, "10:30": 0.25, "11:00": 0.35, "11:30": 0.45,
    "13:00": 0.48, "13:30": 0.55, "14:00": 0.65, "14:30": 0.78,
    "15:00": 1.00,
}

# V4.3: conservative afternoon share for leader stocks (backtest: 9-16%)
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


def get_intraday_snapshot(db, trade_date, time_slot="14:00"):
    """从 stk_mins 获取 ≤ 指定时刻的最新全市场快照。

    由于 RT 数据增量同步，每个时段只有最新一根K线。
    使用子查询取每个 ts_code 在目标时间前的最新一条记录。
    """
    time_cutoff = f"{trade_date} {time_slot}:59"  # Include bars up to XX:59
    rows = db.execute(
        "SELECT m.ts_code, m.open, m.high, m.low, m.close, m.volume, m.amount "
        "FROM stk_mins m "
        "INNER JOIN (SELECT ts_code, MAX(trade_time) as max_time FROM stk_mins "
        "            WHERE trade_time >= ? AND trade_time <= ? AND freq='5min' "
        "            GROUP BY ts_code) latest "
        "ON m.ts_code=latest.ts_code AND m.trade_time=latest.max_time",
        (f"{trade_date} 09:00:00", time_cutoff)
    ).fetchall()
    snapshot = {}
    for r in rows:
        raw_code = r.get("code") or r.get("ts_code","")
        code = raw_code.split('.')[0] if '.' in str(raw_code) else str(raw_code)
        snapshot[code] = {
            "open": float(r["open"] or 0), "high": float(r["high"] or 0),
            "low": float(r["low"] or 0), "close": float(r["close"] or 0),
            "volume": float(r["volume"] or 0), "amount": float(r["amount"] or 0),
        }
    return snapshot


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


def get_pre_close_map(db, trade_date):
    """Get pre_close from daily_kline (stk_limit.pre_close is often NULL).

    Uses the close price from the most recent trading day before trade_date.
    """
    result = {}
    # Subquery: for each stock, get the previous trading day's close
    rows = db.execute(
        "SELECT a.code, a.close FROM daily_kline a "
        "JOIN (SELECT code, MAX(trade_date) as prev_date FROM daily_kline "
        "      WHERE trade_date < ? GROUP BY code) b "
        "ON a.code=b.code AND a.trade_date=b.prev_date "
        "WHERE a.close > 0",
        (trade_date,)
    ).fetchall()
    return {r["code"]: r["close"] for r in rows}


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


def get_sector_index(db, industry, trade_date, code=None):
    """获取板块指数涨跌幅 (V5.3: THS概念优先 → index_basic fallback).

    V5.3: 通过 ths_member + ths_daily 获取股票所属概念的实时涨跌幅.
    注: 绕过 PG adapter 的 ts_code→code 误翻译, 直接用 psycopg2 查询.
    """
    # 1. THS概念路径 (psycopg2 raw query — 避免 adapter 把 m.ts_code 错译成 m.code)
    if code:
        try:
            raw_conn = db._get_conn()
            cur = raw_conn.cursor()
            cur.execute(
                "SELECT d.change_pct FROM ths_daily d "
                "JOIN ths_member m ON m.ts_code = d.code "
                "WHERE m.con_code LIKE %s AND d.trade_date = %s "
                "ORDER BY ABS(d.change_pct) DESC LIMIT 1",
                (f"{code}%", trade_date)
            )
            r = cur.fetchone()
            if r and r[0] is not None:
                return float(r[0])
        except Exception:
            pass  # fall through to index_basic

    # 2. index_basic → index_daily fallback (via adapter, no ts_code issue)
    keyword = industry[-2:] if len(industry) >= 2 else industry
    row = db.execute(
        "SELECT d.pct_chg FROM index_daily d "
        "JOIN index_basic b ON d.code=b.code "
        "WHERE b.name LIKE ? AND d.trade_date=? "
        "ORDER BY d.pct_chg DESC LIMIT 1",
        (f"%{keyword}%", trade_date)
    ).fetchone()
    if row and row["pct_chg"] is not None:
        return float(row["pct_chg"])

    return 0


def get_shanghai_index(db, trade_date):
    row = db.execute(
        "SELECT pct_chg FROM index_daily WHERE ts_code='000001.SH' AND trade_date=?", (trade_date,)
    ).fetchone()
    return row["pct_chg"] if row else 0


# ── V5.1 P0: 板块高潮次日检测缓存 ──
_sector_climax_cache = {}

def get_sector_climax_penalty(db, industry, trade_date):
    """V5.1 P0: 检测板块昨日是否高潮加速, 返回今日惩罚分 (0-20).

    复盘证据: 六氟化钨板块昨日高潮→今日中船特气(-7%)+中巨芯(-6%)
    机制: 昨日板块涨幅≥5% OR 板块内涨停≥3家 → 今日获利回吐概率高

    Returns: penalty score (0-20), higher = more penalty for today's picks
    """
    cache_key = (industry, trade_date)
    if cache_key in _sector_climax_cache:
        return _sector_climax_cache[cache_key]

    # 1. 获取前一个交易日
    prev_row = db.execute(
        "SELECT trade_date FROM daily_kline WHERE trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (trade_date,)
    ).fetchone()
    if not prev_row:
        _sector_climax_cache[cache_key] = 0
        return 0
    prev_date = prev_row["trade_date"]

    # 2. 昨日板块涨幅 (index_basic → index_daily, 用最后2字关键词匹配)
    keyword = industry[-2:] if len(industry) >= 2 else industry
    td_prev = str(prev_date)
    sector_row = db.execute(
        "SELECT d.pct_chg FROM index_daily d "
        "JOIN index_basic b ON d.code=b.code "
        "WHERE b.name LIKE ? AND d.trade_date=? "
        "ORDER BY d.pct_chg DESC LIMIT 1",
        (f"%{keyword}%", td_prev)
    ).fetchone()
    yesterday_sector_pct = float(sector_row["pct_chg"] or 0) if sector_row else 0

    # 2b. Fallback: broader match with full industry name
    if yesterday_sector_pct == 0:
        sector_row = db.execute(
            "SELECT d.pct_chg FROM index_daily d "
            "JOIN index_basic b ON d.code=b.code "
            "WHERE b.name LIKE ? AND d.trade_date=? "
            "ORDER BY d.pct_chg DESC LIMIT 1",
            (f"%{industry}%", td_prev)
        ).fetchone()
        yesterday_sector_pct = float(sector_row["pct_chg"] or 0) if sector_row else 0

    # 3. 昨日板块内涨停家数 (limit_list_d 用 YYYYMMDD 格式)
    td_prev_short = td_prev.replace('-', '')
    limit_row = db.execute(
        "SELECT COUNT(*) as cnt FROM limit_list_d l "
        "JOIN stocks s ON s.code=SUBSTR(l.ts_code,1,6) "
        "WHERE l.trade_date=? AND l.pct_chg > 0 AND s.industry=?",
        (td_prev_short, industry)
    ).fetchone()
    yesterday_limit_count = limit_row["cnt"] if limit_row else 0

    # 4. 判定惩罚等级
    if yesterday_sector_pct >= 5 or yesterday_limit_count >= 3:
        penalty = 20   # 🔴 重度高潮: 板块涨>5%或涨停≥3家 → 次日大概率分歧
    elif yesterday_sector_pct >= 3 or yesterday_limit_count >= 2:
        penalty = 12   # 🟡 中度高潮: 板块涨>3%或涨停≥2家 → 适度谨慎
    elif yesterday_sector_pct >= 1.5:
        penalty = 5    # 🟠 轻度热度: 板块涨>1.5% → 小幅减持
    else:
        penalty = 0    # 🟢 正常: 昨日板块温和, 无高潮风险

    _sector_climax_cache[cache_key] = penalty
    return penalty


def score_intraday_stock(code, name, industry, snap, pre_close, db, trade_date,
                          time_slot="14:00", limit_map=None):
    """盘中选股评分 (V5.1: 9因子 + P0高潮检测 + P1独立过滤)."""
    close_14 = snap["close"]
    amount_14 = snap["amount"]
    volume_14 = snap["volume"]
    if close_14 <= 0 or pre_close <= 0:
        return None

    # ── 条件1: 14:00涨幅 (0-18) — 对齐盘后模型 7-12% ──
    gain_14 = (close_14 / pre_close - 1) * 100
    if gain_14 < 7.0 or gain_14 > 12.0:
        return None
    if code.startswith(('92', '83', '87', '4')):
        return None
    if 'ST' in name.upper():
        return None

    if gain_14 >= 10.0: gain_score = 18
    elif gain_14 >= 9.5: gain_score = 16
    elif gain_14 >= 9.0: gain_score = 14
    elif gain_14 >= 8.5: gain_score = 12
    elif gain_14 >= 8.0: gain_score = 10
    elif gain_14 >= 7.5: gain_score = 9
    else: gain_score = 8

    day_range = snap["high"] - snap["low"]
    if day_range > 0 and (close_14 - snap["low"]) / day_range > 0.9:
        gain_score += 2
    gain_score = min(18, gain_score)

    # ── I1: 封板可买性 (0-8) — V4.2降权 15→8 ──
    seal_score = 0; seal_status = "拉升中"
    if limit_map and code in limit_map:
        lim = limit_map[code]
        if lim["is_sealed_by_14"]:
            if lim["open_times"] == 0 and lim["fd_amount_yi"] >= 3:
                seal_score = 8; seal_status = "封死可排"
            elif lim["open_times"] <= 1 and lim["fd_amount_yi"] >= 1:
                seal_score = 6; seal_status = "封板可排"
            elif lim["open_times"] <= 2:
                seal_score = 4; seal_status = "炸板回封"
            else:
                seal_score = 1; seal_status = "多次炸板"
        else:
            seal_score = 3; seal_status = "尾盘封板"
    else:
        seal_score = 6  # 拉升中可买 (降权后)

    # ── I2: 午后强势度 (0-15) ──
    vwap, baseline_vol, _, _, has_full = get_baseline_stats(db, code, trade_date)
    afternoon_str = (close_14 / vwap - 1) * 100 if vwap > 0 else 0
    # 使用当日累计最高/最低 (修正单根K线bug)
    day_high, day_low = get_day_range(db, code, trade_date, time_slot)
    day_range = day_high - day_low if day_high > 0 else (snap["high"] - snap["low"])
    pos_in_day = (close_14 - day_low) / max(0.01, day_range) if day_range > 0 else 0.5

    # V4.2: 午后强度升权 15→20 (IC=+0.23, 最强正向因子)
    max_afternoon = 20 if has_full else 16  # 部分数据降权
    if afternoon_str > 2.5: afternoon_score = max_afternoon
    elif afternoon_str > 1.5: afternoon_score = max_afternoon - 4
    elif afternoon_str > 0.5: afternoon_score = max_afternoon - 10
    elif afternoon_str > 0: afternoon_score = max_afternoon - 14
    else: afternoon_score = 0
    if pos_in_day > 0.85 and afternoon_str > 0:
        afternoon_score += 2
    afternoon_score = min(max_afternoon, max(0, afternoon_score))

    # ── I3: 盘中资金强度 (0-10) ──
    vol_surge = get_recent_volume_surge(db, code, trade_date, time_slot)
    if vol_surge > 3.0: money_score = 10
    elif vol_surge > 2.0: money_score = 7
    elif vol_surge > 1.5: money_score = 4
    elif vol_surge > 1.0: money_score = 2
    else: money_score = 0

    # ── 条件4: 预估成交额 (0-10) — 自适应completion ratio ──
    cum_amount, cum_volume = get_cumulative_amount(db, code, trade_date, time_slot)
    amount_14 = cum_amount if cum_amount > 0 else amount_14
    adj_ratio = get_adjusted_completion(db, code, trade_date, time_slot, cum_amount)
    amount_yi = (amount_14 / adj_ratio) / 1e8 if adj_ratio > 0 else amount_14 / 1e8
    if amount_yi >= 50: turnover_score = 10
    elif amount_yi >= 30: turnover_score = 8
    elif amount_yi >= 20: turnover_score = 6
    elif amount_yi >= 15: turnover_score = 4
    elif amount_yi >= 6: turnover_score = 2
    elif amount_yi >= 2: turnover_score = 1
    else: return None

    # ── 条件5: 均线趋势 (0-5) ──
    klines = get_kline_data(db, code, trade_date, 60)
    if len(klines) < 20: return None
    closes = np.array([r["close"] for r in klines], dtype=np.float64)
    ma5, ma10, ma20 = compute_ma(closes, 5), compute_ma(closes, 10), compute_ma(closes, 20)
    if ma5 is None or ma10 is None: return None
    if ma20 and ma5 > ma10 > ma20: ma_score = 5
    elif ma5 > ma10: ma_score = 3
    else: ma_score = 0
    if len(closes) >= 20 and (closes[-1] / closes[-20] - 1) * 100 < -30:
        return None

    # ── 条件7: 集中放量 (0-7) — 自适应completion ──
    cum_vol = cum_volume if cum_volume > 0 else volume_14
    adj_ratio_v = get_adjusted_completion(db, code, trade_date, time_slot, cum_volume)
    est_day_vol = cum_vol / adj_ratio_v if adj_ratio_v > 0 else cum_vol
    vols = np.array([r["volume"] for r in klines], dtype=np.float64)
    vol_ma5 = np.mean(vols[-6:-1]) if len(vols) >= 6 else np.mean(vols[:-1])
    vol_ratio = est_day_vol / vol_ma5 if vol_ma5 > 0 else 1.0
    if vol_ratio >= 3.0: volume_score = 7
    elif vol_ratio >= 2.0: volume_score = 5
    elif vol_ratio >= 1.5: volume_score = 3
    elif vol_ratio >= 1.0: volume_score = 1
    else: volume_score = 0

    # ── V5.1 P1: 板块龙头 (0-14) + 独立标的强化过滤 ──
    peer_cnt = db.execute(
        "SELECT COUNT(DISTINCT SUBSTR(m.ts_code,1,6)) as cnt "
        "FROM stk_mins m JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
        "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
        "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
        "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100>=5",
        (trade_date, f"{trade_date} {time_slot}%", industry)
    ).fetchone()
    peer_n = peer_cnt["cnt"] if peer_cnt else 0
    if peer_n >= 5: sl_score = 14      # V5.1: 升权 12→14, 板块集群最强
    elif peer_n >= 3: sl_score = 11
    elif peer_n >= 2: sl_score = 7
    elif peer_n == 1: sl_score = 3     # V5.1: 独苗弱化
    else: sl_score = 0                 # V5.1: 无同板块→0分

    # ── V5.2: 板块内涨幅排名 (总龙加分, 跟风减分) ──
    # 6/5回测: 赢家与输家peer_count均值相同(15 vs 16), 需要板块内排名区分
    if peer_n >= 2:
        rank_row = db.execute(
            "SELECT COUNT(*) as higher FROM stk_mins m "
            "JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
            "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
            "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
            "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100 > ?",
            (trade_date, f"{trade_date} {time_slot}%", industry, gain_14)
        ).fetchone()
        intra_rank = (rank_row["higher"] if rank_row else 0) + 1  # 1 = 涨幅最高(总龙)
    else:
        intra_rank = 1  # 独苗, 无排名意义

    # 板块内排名加分: 总龙(第1)+6, 前排(2-3)+3, 中游+0, 后排(>5)-3
    if intra_rank == 1 and peer_n >= 3:
        leadership_bonus = 6   # 🟢 板块总龙头, 最强辨识度
    elif intra_rank <= 3 and peer_n >= 3:
        leadership_bonus = 3   # 🟡 板块前排
    elif intra_rank > 5 and peer_n >= 5:
        leadership_bonus = -3  # 🔴 板块跟风, 次日最先被淘汰
    else:
        leadership_bonus = 0

    # V5.1 P1: 独立标的强化惩罚 (复盘: 粤桂股份-7% 偏独立)
    if peer_n == 0:
        independent_penalty = 12       # 🔴 零板块支撑: 重罚
    elif peer_n == 1:
        independent_penalty = 4        # 🟡 独苗: 轻罚
    else:
        independent_penalty = 0

    # ── V5.1 P0: 板块高潮次日检测 (index_basic→index_daily) ──
    climax_penalty = get_sector_climax_penalty(db, industry, trade_date)

    # ── V5.2 P0b: 板块日内过热检测 (提升权重 8→10, 15→18) ──
    if peer_n >= 30:
        overheat_penalty = 18   # 🔴 极度拥挤, 即使龙头也要谨慎
    elif peer_n >= 20:
        overheat_penalty = 10   # 🟡 板块过热
    else:
        overheat_penalty = 0

    # ── 板块动量 (V5.1: 维持反转逻辑, 降权 8→6) ──
    sp = get_sector_index(db, industry, trade_date, code)
    if sp > 3: sm_score = 0   # 过热, 次日大概率回调
    elif sp > 1: sm_score = 2  # 偏热
    elif sp > 0: sm_score = 5  # 温和, OK
    elif sp > -2: sm_score = 7 # 适度回调, 次日反弹概率高
    else: sm_score = 8         # 深跌板块, 次日反弹最强

    # ── 板块共振 (V5.1: 维持反转逻辑) ──
    sh = get_shanghai_index(db, trade_date)
    if sp > 2 and sh > 0:
        res_score = 0  # 板块+大盘双强 → 过热, 次日回调
    elif sp > 0 and sh < 0:
        res_score = 3  # 板块逆市走强(已涨过), 次日动力不足
    elif sp < 0 and sh < 0 and sp > sh:
        res_score = 5  # 板块抗跌, OK
    elif sp < -1:
        res_score = 5  # 板块超跌, 次日反弹
    else:
        res_score = 3

    # ── V5.2 综合 (P0高潮惩罚 + P0b过热惩罚 + P1独立过滤 + 板块排名) ──
    total = (gain_score + seal_score + afternoon_score +
             turnover_score + ma_score + volume_score + sl_score + sm_score + res_score
             + leadership_bonus
             - independent_penalty - climax_penalty - overheat_penalty)
    grade = "S" if total >= 75 else ("A" if total >= 60 else ("B" if total >= 45 else "C"))

    return {
        "code": code, "name": name, "industry": industry,
        "gain_14": round(gain_14, 2), "close_14": close_14, "pre_close": pre_close,
        "amount_yi_est": round(amount_yi, 1), "amount_14_yi": round(amount_14/1e5, 1),
        "vol_surge": round(vol_surge, 2), "afternoon_strength": round(afternoon_str, 2),
        "seal_status": seal_status, "total_score": total, "grade": grade,
        "gain_score": gain_score, "seal_score": seal_score,
        "afternoon_score": afternoon_score, "money_score": 0,  # V4.2: removed
        "turnover_score": turnover_score, "ma_score": ma_score,
        "volume_score": volume_score, "sector_leader_score": sl_score,
        "sector_momentum_score": sm_score, "resonance_score": res_score,
        "sector_change": round(sp, 2),
        "peer_count": peer_n,                              # V5.1: 同板块强势股数
        "intra_rank": intra_rank,                           # V5.2: 板块内涨幅排名
        "leadership_bonus": leadership_bonus,               # V5.2: 板块龙头加分
        "independent_penalty": independent_penalty,         # V5.1 P1
        "climax_penalty": climax_penalty,                   # V5.1 P0
        "overheat_penalty": overheat_penalty,               # V5.1 P0b
    }


def run_intraday_screening(trade_date, time_slot="14:00", top_n=20):
    """V5.1 盘中选股主流程 (P0高潮检测 + P1独立过滤)."""
    # 每次运行清空高潮检测缓存
    _sector_climax_cache.clear()
    with _get_db(readonly=True) as db:
        print(f"  🕑 快照时间: {time_slot}")
        snapshot = get_intraday_snapshot(db, trade_date, time_slot)
        print(f"  📊 快照: {len(snapshot)} 只")
        pre_closes = get_pre_close_map(db, trade_date)
        print(f"  📊 pre_close: {len(pre_closes)} 只")
        limit_map = get_intraday_limit_status(db, trade_date)
        print(f"  🔒 已封板: {len(limit_map)} 只 (14:00前: {sum(1 for v in limit_map.values() if v['is_sealed_by_14'])})")

        stocks = db.execute(
            "SELECT code, name, industry FROM stocks WHERE is_st=0 "
            "AND name NOT LIKE '%ST%' AND (float_mv IS NULL OR float_mv >= 20)"
        ).fetchall()
        print(f"  📈 股票池: {len(stocks)} 只")

        scores = []
        for r in stocks:
            c = r["code"]
            if c not in snapshot or c not in pre_closes: continue
            try:
                res = score_intraday_stock(c, r["name"], r["industry"] or "其他",
                                            snapshot[c], pre_closes[c], db,
                                            trade_date, time_slot, limit_map)
                if res: scores.append(res)
            except Exception: continue

        print(f"  ✅ 筛选: {len(scores)} 只")

        # ── V4.2 P2: 涨跌比过滤器 (使用snapshot数据, 避免time_slot精确匹配问题) ──
        prev_date_row = db.execute(
            "SELECT MAX(trade_date) FROM daily_kline WHERE trade_date < ?", (trade_date,)
        ).fetchone()
        if prev_date_row and (list(prev_date_row.values())[0] if isinstance(prev_date_row, dict) else (prev_date_row[0] if prev_date_row else None)):
            prev_date = list(prev_date_row.values())[0] if isinstance(prev_date_row, dict) else prev_date_row[0]
            breadth_row = db.execute(
                "SELECT SUM(CASE WHEN m.close > d.close THEN 1 ELSE 0 END) as up, "
                "SUM(CASE WHEN m.close < d.close THEN 1 ELSE 0 END) as down "
                "FROM (SELECT DISTINCT ts_code, close FROM stk_mins "
                "      WHERE trade_time >= ? AND trade_time <= ? AND freq='5min') m "
                "JOIN daily_kline d ON d.code=SUBSTR(m.ts_code,1,6) AND d.trade_date=? "
                "WHERE d.close > 0",
                (f"{trade_date} 09:00:00", f"{trade_date} {time_slot}:59", prev_date)
            ).fetchone()
            if breadth_row:
                up = breadth_row["up"] or 0; down = breadth_row["down"] or 0
                breadth = up / max(1, up + down) * 100
            else:
                breadth = 50
        else:
            breadth = 50  # No previous day → assume neutral
        # ── V5.2 P2: 市场狂热日检测 ──
        # 6/9回测: 192只通过初筛(正常日60-80), 全市场板块爆发 → 次日全面回调
        # 策略: 狂热日减少选股数量, 只留最强标的
        MARKET_FRENZY_THRESHOLD = 120
        market_frenzy = len(scores) > MARKET_FRENZY_THRESHOLD
        if market_frenzy:
            frenzy_ratio = len(scores) / 80  # 正常日基准≈80只
            print(f"  🔥 市场狂热: {len(scores)}只通过初筛 ({(frenzy_ratio-1)*100:.0f}%高于正常)")

        if breadth < 40:
            effective_n = max(5, int(top_n * 0.5))
            print(f"  🌧️ 涨跌比 {breadth:.0f}% (<40%), Top-N {top_n}→{effective_n}")
        elif breadth < 55:
            effective_n = max(8, int(top_n * 0.7))
            print(f"  ⛅ 涨跌比 {breadth:.0f}% (40-55%), Top-N {top_n}→{effective_n}")
        else:
            effective_n = top_n

        # V5.2: 市场狂热日进一步收紧 (全市场板块爆发→次日全面回调)
        if market_frenzy:
            frenzy_n = max(5, int(effective_n * 0.5))  # 狂热日只选一半
            print(f"  🔥 市场狂热: effective_n {effective_n}→{frenzy_n}")
            effective_n = frenzy_n

    scores.sort(key=lambda x: -x["total_score"])
    return scores[:effective_n], scores


def generate_intraday_plan(picks):
    plans = []
    for s in picks:
        entry = round(s["close_14"] * 1.01, 2)
        stop = round(s["close_14"] * 0.96, 2)
        g = s["grade"]
        pos = "20%" if g == "S" else ("15%" if g == "A" else ("10%" if g == "B" else "0%"))
        ss = s.get("seal_status", "")
        if ss in ("封死可排", "封板可排"): act = "🟢 排板买入"
        elif ss == "拉升中": act = "🟢 现价买入"
        elif ss == "炸板回封": act = "🟡 等回封确认"
        else: act = "🟠 谨慎"

        # V5.1: 高潮/独立风险标注
        risk_tags = []
        if s.get("climax_penalty", 0) >= 20:
            risk_tags.append("⚠️板块高潮次日")
            pos = "0%"
            act = "🔴 高潮次日不买"
        elif s.get("climax_penalty", 0) >= 12:
            risk_tags.append("⚡板块偏热")
        if s.get("independent_penalty", 0) >= 12:
            risk_tags.append("🔸独立标的")
        if s.get("independent_penalty", 0) >= 4:
            risk_tags.append("🔹独苗")

        plans.append({"code": s["code"], "name": s["name"], "grade": g,
                       "total_score": s["total_score"], "entry_price": entry,
                       "stop_loss": stop, "position": pos, "action": act,
                       "seal_status": ss, "gain_14": s["gain_14"],
                       "risk_tags": risk_tags})
    return plans


def print_intraday_results(top, trade_date, time_slot):
    print(f"\n{'=' * 105}")
    print(f"  秋神龙头战法-盘中 V5.1 — {trade_date} {time_slot} Top {len(top)}")
    print(f"{'=' * 105}")
    print(f"\n  V5.1: 涨幅(20)+午后(20)+龙头(14)+分时(12)+成交(12)+放量(8)+共振(8)+板块动量(6)+均线(6)")
    print(f"        +P0高潮检测(12) +P1独立过滤 | 复盘:中船特气(-7%)+中巨芯(-6%) 高潮次日分歧")
    # V5.1: 显示高潮惩罚和独立惩罚
    climax_count = sum(1 for s in top if s.get("climax_penalty", 0) > 0)
    indep_count = sum(1 for s in top if s.get("independent_penalty", 0) > 0)
    if climax_count or indep_count:
        print(f"  ⚠️ 高潮惩罚: {climax_count}只 | 独立惩罚: {indep_count}只")
    print(f"{'#':<3} {'代码':<8} {'名称':<8} {'总分':<5} {'级':<3} {'涨':<7} {'预估':<8} {'同板块':<6} {'高潮罚':<6} {'独立罚':<6} {'板块'}")
    print(f"{'-'*95}")
    for i, s in enumerate(top, 1):
        clim = f"-{s.get('climax_penalty',0)}" if s.get('climax_penalty',0) > 0 else "·"
        indp = f"-{s.get('independent_penalty',0)}" if s.get('independent_penalty',0) > 0 else "·"
        print(f"{i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<5.0f} {s['grade']:<3} "
              f"{s['gain_14']:>+5.1f}% {s['amount_yi_est']:<6.0f}亿 {s.get('peer_count',0):<6} "
              f"{clim:<6} {indp:<6} "
              f"{s.get('sector_change',0):>+5.1f}% {s['industry']}")
    sc = sum(1 for s in top if s['grade'] == 'S')
    ac = sum(1 for s in top if s['grade'] == 'A')
    print(f"\n  S级={sc} A级={ac} B级={sum(1 for s in top if s['grade']=='B')}")


def print_intraday_plan(plans):
    print(f"\n{'=' * 90}")
    print(f"  📋 盘中买入执行计划 V5.1 (14:00-15:00)")
    print(f"{'=' * 90}")
    print(f"  {'代码':<8} {'名称':<8} {'级':<3} {'动作':<22} {'入场':<8} {'止损':<8} {'仓位':<6} {'风险'}")
    print(f"  {'-' * 78}")
    for p in plans:
        tags = " ".join(p.get("risk_tags", []))
        print(f"  {p['code']:<8} {p['name']:<8} {p['grade']:<3} {p['action']:<22} "
              f"{p['entry_price']:<8} {p['stop_loss']:<8} {p['position']:<6} {tags}")


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


def main():
    p = argparse.ArgumentParser(description="盘中龙头短线战法 (支持RT实时数据)")
    p.add_argument("--date", type=str, required=True, help="YYYY-MM-DD")
    p.add_argument("--time", type=str, default="14:00",
                   help="Snapshot time (default: 14:00). Use 'auto' with --rt for latest.")
    p.add_argument("--rt", action="store_true",
                   help="RT模式: 自动检测最新可用数据时点，显示数据新鲜度")
    p.add_argument("--top-n", type=int, default=15)
    p.add_argument("--export", type=str, default=None, help="Export JSON")
    args = p.parse_args()

    with _get_db(readonly=True) as db:
        # ── RT模式: 自动检测最新时点 ──
        time_slot = args.time
        if args.rt:
            latest, stock_cnt, total_slots = get_latest_rt_slot(db, args.date)
            if latest:
                time_slot = latest
                print("=" * 60)
                print(f"  📡 RT实时模式 — {args.date}")
                print(f"  最新可用时点: {time_slot} ({stock_cnt}只, {total_slots}/48时段)")
                # Market breadth
                up, down, breadth = get_rt_market_breadth(db, args.date, time_slot)
                if breadth > 0:
                    bc = "🟢" if breadth > 50 else ("🟡" if breadth > 30 else "🔴")
                    print(f"  实时涨跌比: {bc} {up}↑/{down}↓ ({breadth}%)")
                print("=" * 60)
            else:
                print(f"  ⚠️ RT模式: {args.date} 无可用数据，回退到 {args.time}")
        else:
            print("=" * 60)
            print(f"  盘中龙头短线战法 — {args.date} {args.time}")
            print("=" * 60)

    top, all_scores = run_intraday_screening(args.date, time_slot, args.top_n)
    if not top:
        print("\n  ⚠️ 无符合条件标的")
        return
    print_intraday_results(top, args.date, time_slot)
    plans = generate_intraday_plan(top)
    print_intraday_plan(plans)

    if args.export:
        os.makedirs(os.path.dirname(args.export) or "outputs", exist_ok=True)
        with open(args.export, 'w') as f:
            json.dump({"date": args.date, "time_slot": time_slot,
                       "top_n": len(top), "picks": top, "execution_plan": plans},
                      f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  📁 Exported: {args.export}")


if __name__ == "__main__":
    main()


class IntradayScalpEngine:
    """V5.2 秋神龙头战法-盘中引擎 — 14:00 选股 (板块排名+过热升级+狂热减N)."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute intraday screening."""
        picks, scores = run_intraday_screening(trade_date or "latest", top_n=top_n)
        return picks if picks else []
