#!/usr/bin/env python3
"""秋神龙头战法-尾盘顺势选股 — Closing Trend-Following Strategy. V7.0+V8.0最优组合.

14:40 尾盘顺势选股，当日 14:40-15:00 买入，次日套利。V7.0过滤+V8.0入场规则.

核心差异 (vs leader_scalp.py):
  - 数据源: stk_mins (5分钟K线) 代替 daily_kline
  - 涨幅: 14:00 实时涨幅 5-10% (vs 收盘 7-12%)
  - 成交额: 14:00 累计值 /0.65 预估全天
  - 封板: 实时状态 (已封/炸板中/拉升中)
  - 新增3因子: 午后强势度 + 封板可买性 + 盘中资金强度

Usage:
    python tools/leader_closing.py --date 2026-06-05
    python tools/leader_scalp_intraday.py --date 2026-06-05 --time 13:30
    python tools/leader_scalp_intraday.py --date 2026-06-05 --top-n 15 --export /tmp/picks.json
"""
import argparse, json, os, sys, time
from collections import defaultdict
from datetime import datetime

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from kronos_factors.scorer._db_stub import _get_db

# ── Intraday scoring weights (9因子 V6.3 优化) ──
# 尾盘V3.0: +O1恢复P9 +O2共振±5 +O3评级降门槛
INTRA_WEIGHTS = {
    "gain_quality": 18,              # 14:00涨幅质量 (≥7%)
    "afternoon_strength": 12,        # 午后强势度 D:10→12
    "intraday_leadership": 22,       # 分时引领性 (含leadership_bonus)
    "sector_leader": 24,             # 板块龙头 (最重要)
    "sector_momentum": 8,            # 板块动量
    "turnover": 10,                  # 预估成交额
    "resonance": 8,                  # 板块共振
    "volume_surge": 7,               # 集中放量
    "ma_trend": 6,                   # 均线趋势
    "sector_climax_penalty": 12,     # P0: 板块高潮次日惩罚
}

# Full-day completion ratios for different time slots
# (assumes data from 9:30 onwards)
TIME_COMPLETION = {
    "10:00": 0.15, "10:30": 0.25, "11:00": 0.35, "11:30": 0.45,
    "13:00": 0.48, "13:30": 0.55, "14:00": 0.65, "14:30": 0.78,
    "14:40": 0.85, "15:00": 1.00,
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
        "SELECT m.code, m.open, m.high, m.low, m.close, m.volume, m.amount "
        "FROM stk_mins m "
        "INNER JOIN (SELECT code, MAX(trade_time) as max_time FROM stk_mins "
        "            WHERE trade_time >= ? AND trade_time <= ? AND freq='5min' "
        "            GROUP BY code) latest "
        "ON m.code=latest.code AND m.trade_time=latest.max_time",
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
    """Get adjusted pre_close. Priority: stk_limit(复权价) > daily_kline.close."""
    result = {}
    rows = db.execute(
        "SELECT a.code, a.close FROM daily_kline a "
        "JOIN (SELECT code, MAX(trade_date) as prev_date FROM daily_kline "
        "      WHERE trade_date < ? GROUP BY code) b "
        "ON a.code=b.code AND a.trade_date=b.prev_date "
        "WHERE a.close > 0",
        (trade_date,)
    ).fetchall()
    result = {r["code"]: r["close"] for r in rows}
    try:
        limit_rows = db.execute(
            "SELECT code, up_limit FROM stk_limit WHERE trade_date=? AND up_limit>0",
            (trade_date,)
        ).fetchall()
        for r in limit_rows:
            code = r["code"]; up = float(r["up_limit"])
            if code.startswith('688'): pc = up / 1.20
            elif code.startswith(('300','301')): pc = up / 1.20
            else: pc = up / 1.10
            if pc > 0: result[code] = pc
    except Exception: pass
    return result


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
    """获取板块指数涨跌幅 (V6.8: THS概念优先 → index_basic fallback).

    V6.8: 修复 ths_daily.code 格式不一致 (700001 vs 700001.TI),
    新增 ths_index 概念名称关联, 今日无数据时回退到最近交易日.
    注: 绕过 PG adapter 的 ts_code→code 误翻译, 直接用 psycopg2 查询.
    """
    # 1. THS概念路径 (psycopg2 raw query — 避免 adapter 把 m.ts_code 错译成 m.code)
    if code:
        raw_conn = None
        try:
            raw_conn = db._get_conn()
            cur = raw_conn.cursor()
            # V6.8: (1) 修复 code 格式: d.code 可能是 '700001' 或 '700001.TI'
            #       (2) 今日无数据时回退到最近交易日
            #       (3) JOIN ths_index 取概念名称
            cur.execute(
                "SELECT d.change_pct FROM ths_daily d "
                "JOIN ths_member m ON (m.ts_code = d.code OR m.ts_code = d.code || '.TI') "
                "WHERE m.con_code LIKE %s AND d.trade_date = %s "
                "ORDER BY ABS(d.change_pct) DESC LIMIT 1",
                (f"{code}%", trade_date)
            )
            r = cur.fetchone()
            # Fallback: 今日无数据 → 取最近交易日
            if not r:
                cur.execute(
                    "SELECT d.change_pct FROM ths_daily d "
                    "JOIN ths_member m ON (m.ts_code = d.code OR m.ts_code = d.code || '.TI') "
                    "WHERE m.con_code LIKE %s "
                    "ORDER BY d.trade_date DESC, ABS(d.change_pct) DESC LIMIT 1",
                    (f"{code}%",)
                )
                r = cur.fetchone()
            if r and r[0] is not None:
                return float(r[0])
        except Exception:
            pass
        finally:
            if raw_conn:
                try:
                    db._put_conn(raw_conn)
                except Exception:
                    pass

    # 2. index_basic → index_daily fallback (via adapter, no ts_code issue)
    keyword = industry[-2:] if len(industry) >= 2 else industry
    row = db.execute(
        "SELECT d.pct_chg FROM index_daily d "
        "JOIN index_basic b ON d.code=b.code "
        "WHERE b.name LIKE ? AND d.trade_date=? "
        "ORDER BY d.pct_chg DESC LIMIT 1",
        (f"%{keyword}%", trade_date)
    ).fetchone()
    # Fallback: 今日无数据 → 最近交易日
    if (not row or row["pct_chg"] is None):
        row = db.execute(
            "SELECT d.pct_chg FROM index_daily d "
            "JOIN index_basic b ON d.code=b.code "
            "WHERE b.name LIKE ? "
            "ORDER BY d.trade_date DESC, d.pct_chg DESC LIMIT 1",
            (f"%{keyword}%",)
        ).fetchone()
    if row and row["pct_chg"] is not None:
        return float(row["pct_chg"])

    return 0


def get_shanghai_index(db, trade_date):
    # PG index_daily.code stores bare '000001'; inline literal isn't translated by pg_adapter.
    row = db.execute(
        "SELECT pct_chg FROM index_daily WHERE ts_code='000001' AND trade_date=?", (trade_date,)
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
                          time_slot="14:00", limit_map=None,
                          industry_stats=None, kline_cache=None,
                          mins_agg_cache=None):
    """盘中选股评分 (V5.4: 9因子 + P0高潮检测 + P1独立过滤 + 预计算加速)."""
    close_14 = snap["close"]
    amount_14 = snap["amount"]
    volume_14 = snap["volume"]
    if close_14 <= 0 or pre_close <= 0:
        return None

    # ── 条件1: V5.9 涨幅过滤 (8-12%, 排除 9-9.5% 涨停阻力区) ──
    gain_14 = (close_14 / pre_close - 1) * 100
    if gain_14 < 8.0 or gain_14 > 12.0:
        return None
    # 尾盘V3 O1: 恢复9-9.5%淘汰(52笔/40%胜率/-0.11%)
    if 9.0 <= gain_14 < 9.5:
        return None
    if code.startswith(('92', '83', '87', '4')):
        return None
    if 'ST' in name.upper():
        return None

    # ── V6.2 P16: 距涨停<2%淘汰 — 封板率80%, 真实交易-0.33%均值 ──
    # 计算涨停价 (A股10%, 科创板20%, 北交所30%)
    if code.startswith(('8','9','4')): limit_pct = 1.30
    elif code.startswith('688'): limit_pct = 1.20
    else: limit_pct = 1.10
    limit_price = pre_close * limit_pct
    dist_to_limit = (limit_price / close_14 - 1) * 100  # 正数=还有空间, 0=已到涨停
    if dist_to_limit < 0.5:  # 距涨停不足2%, 随时封板或已近封板
        return None  # 🔴 封板风险过高, 不可交易

    # ── V6.2 P17: 创业板(300/301)淘汰 — 封板率极高(81%), 真实可买仅19% ──
    if code.startswith(('300','301')):
        return None  # 🔴 创业板封板率过高, 无法判断可买性

    if gain_14 >= 10.0: gain_score = 18
    elif gain_14 >= 9.5: gain_score = 16
    elif gain_14 >= 9.0: gain_score = 14
    elif gain_14 >= 8.5: gain_score = 12
    else: gain_score = 10                        # 尾盘V1.0: 8.0-8.5%

    # ── V5.8 P5: 涨停阻力区惩罚 — 9.5~10%接近涨停但封不住,次日低开概率大(回测44%胜率) ──
    limit_resistance_penalty = 0
    if 9.5 <= gain_14 < 10.0:
        limit_resistance_penalty = 3  # 涨停阻力扣3分

    day_range = snap["high"] - snap["low"]
    if day_range > 0 and (close_14 - snap["low"]) / day_range > 0.9:
        gain_score += 2
    gain_score = min(18, gain_score)

    # ── I1: 封板可买性 (0-8) + V5.7 涨停板不可买过滤 ──
    seal_score = 0; seal_status = "拉升中"; seal_buyable = True
    if limit_map and code in limit_map:
        lim = limit_map[code]
        if lim["is_sealed_by_14"]:
            if lim["open_times"] == 0 and lim["fd_amount_yi"] >= 3:
                seal_score = 8; seal_status = "封死可排"
                seal_buyable = False  # V5.7: 封死涨停, 买不到
            elif lim["open_times"] <= 1 and lim["fd_amount_yi"] >= 1:
                seal_score = 6; seal_status = "封板可排"
                seal_buyable = False  # V5.7: 封板涨停, 排板困难
            elif lim["open_times"] <= 2:
                seal_score = 4; seal_status = "炸板回封"
                seal_buyable = True   # V5.7: 炸开过, 有机会买入
            else:
                seal_score = 1; seal_status = "多次炸板"
                seal_buyable = True
        else:
            seal_score = 3; seal_status = "尾盘封板"
            seal_buyable = True
    else:
        seal_score = 6  # 拉升中可买
        seal_buyable = True

    # ── V5.7: 涨停板不可买 — 封死/封板的股票直接淘汰 ──
    if not seal_buyable:
        return None  # limit_list_d: 已封死涨停, 当日无法买入

    # ── V5.4 I2+I3+条件4: stk_mins 聚合 — 优先从预计算缓存取 ──
    if mins_agg_cache and code in mins_agg_cache:
        ma = mins_agg_cache[code]
        vwap = ma["vwap"]
        has_full = ma["has_full"]
        day_high, day_low = ma["day_high"], ma["day_low"]
        cum_amount, cum_volume = ma["cum_amount"], ma["cum_volume"]
        # Volume surge: afternoon avg / morning avg
        vol_surge = ma["pm_avg_vol"] / ma["am_avg_vol"] if ma["am_avg_vol"] > 0 else 1.0
    else:
        vwap, baseline_vol, _, _, has_full = get_baseline_stats(db, code, trade_date)
        day_high, day_low = get_day_range(db, code, trade_date, time_slot)
        cum_amount, cum_volume = get_cumulative_amount(db, code, trade_date, time_slot)
        vol_surge = get_recent_volume_surge(db, code, trade_date, time_slot)

    # ── V6.1 P15: 实时封板检测 — 不依赖limit_list_d, day_high已就绪 ──
    # A股10%涨停价, 北交所30%
    if code.startswith(('8','9','4')):  # 北交所
        limit_price = pre_close * 1.30
    elif code.startswith('688'):  # 科创板
        limit_price = pre_close * 1.20
    else:
        limit_price = pre_close * 1.10

    # 14:40现价 ≥ 涨停价的99.5% 且 等于日内最高 → 已封死, 无法买入
    if close_14 >= limit_price * 0.995 and close_14 >= day_high * 0.999:
        return None  # 🔴 实时封死涨停: 14:40已到涨停价且无更高成交

    afternoon_str = (close_14 / vwap - 1) * 100 if vwap > 0 else 0

    # ── V5.6 P3: 午后VWAP趋势过滤 — 现价跌穿分时均线=午后主力撤退, 淘汰 ──
    if close_14 < vwap and vwap > 0:
        return None  # 跌穿分时成交均线, 午后走弱

    day_range = day_high - day_low if day_high > 0 else (snap["high"] - snap["low"])
    pos_in_day = (close_14 - day_low) / max(0.01, day_range) if day_range > 0 else 0.5

    max_afternoon = 12 if has_full else 10  # V5.9: 午后回升权重
    if afternoon_str > 2.5: afternoon_score = max_afternoon
    elif afternoon_str > 1.5: afternoon_score = max_afternoon - 2
    elif afternoon_str > 0.5: afternoon_score = max_afternoon - 5
    elif afternoon_str > 0: afternoon_score = max_afternoon - 7
    else: afternoon_score = 0
    if pos_in_day > 0.85 and afternoon_str > 0:
        afternoon_score += 1
    afternoon_score = min(max_afternoon, max(0, afternoon_score))

    # I3: 盘中资金强度
    if vol_surge > 3.0: money_score = 10
    elif vol_surge > 2.0: money_score = 7
    elif vol_surge > 1.5: money_score = 4
    elif vol_surge > 1.0: money_score = 2
    else: money_score = 0

    # 条件4: 预估成交额
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

    # ── V5.4 条件5: 均线趋势 (0-5) — 从预取缓存取K线 ──
    if kline_cache and code in kline_cache:
        closes, vols, _amounts = kline_cache[code]
    else:
        klines = get_kline_data(db, code, trade_date, 60)
        if len(klines) < 20: return None
        closes = np.array([r["close"] for r in klines], dtype=np.float64)
        vols = np.array([r["volume"] for r in klines], dtype=np.float64)

    if len(closes) < 20: return None
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
    vol_ma5 = np.mean(vols[-6:-1]) if len(vols) >= 6 else np.mean(vols[:-1])
    vol_ratio = est_day_vol / vol_ma5 if vol_ma5 > 0 else 1.0
    if vol_ratio >= 3.0: volume_score = 7
    elif vol_ratio >= 2.0: volume_score = 5
    elif vol_ratio >= 1.5: volume_score = 3
    elif vol_ratio >= 1.0: volume_score = 1
    else: volume_score = 0

    # ── V5.4 P1: 板块龙头 (0-14) — 从预计算表取, 无预计算时 fallback 查询 ──
    if industry_stats and industry in industry_stats:
        peer_n = industry_stats[industry]["peer_count"]
    else:
        peer_cnt = db.execute(
            "SELECT COUNT(DISTINCT SUBSTR(m.ts_code,1,6)) as cnt "
            "FROM stk_mins m JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
            "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
            "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
            "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100>=5",
            (trade_date, f"{trade_date} {time_slot}%", industry)
        ).fetchone()
        peer_n = peer_cnt["cnt"] if peer_cnt else 0
    if peer_n >= 5: sl_score = 24      # V5.5: 升权 14→24, 板块龙头最重要
    elif peer_n >= 3: sl_score = 18     # V5.5: 11→18
    elif peer_n >= 2: sl_score = 12     # V5.5: 7→12
    elif peer_n == 1: sl_score = 6      # V5.5: 3→6, 独苗仍给基础分
    else: sl_score = 0

    # ── V6.3 P21: 科创板龙头分折扣 ──
    if code.startswith('688') and sl_score >= 18:
        sl_score = int(sl_score * 0.5)

    # ── V6.7 R1: 板块联动加分 — 同概念多股共振=行情确认(秋神方法论) ──
    sector_resonance_bonus = 0
    if peer_n >= 5:
        sector_resonance_bonus = 5   # 强板块联动: 行情级别确认
    elif peer_n >= 3:
        sector_resonance_bonus = 3   # 中等联动: 有跟风效应

    # ── V5.4: 板块内涨幅排名 (总龙加分, 跟风减分) — 预计算加速 ──
    if peer_n >= 2 and industry_stats and industry in industry_stats:
        # 从预计算的 max_gain 快速估算排名: gain_14 >= max_gain → rank=1
        max_g = industry_stats[industry].get("max_gain", 0)
        intra_rank = 1 if gain_14 >= max_g - 0.01 else 2  # 简化排名估算
    elif peer_n >= 2:
        rank_row = db.execute(
            "SELECT COUNT(*) as higher FROM stk_mins m "
            "JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
            "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
            "WHERE m.trade_time LIKE ? AND m.freq='5min' AND s.industry=? "
            "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100 > ?",
            (trade_date, f"{trade_date} {time_slot}%", industry, gain_14)
        ).fetchone()
        intra_rank = (rank_row["higher"] if rank_row else 0) + 1
    else:
        intra_rank = 1

    # 板块内排名加分: V5.5 总龙(第1)+12, 前排(2-3)+6, 中游+0, 后排(>5)-3
    if intra_rank == 1 and peer_n >= 3:
        leadership_bonus = 12  # V5.5: +6→+12, 🟢 板块总龙头, 最强辨识度
    elif intra_rank <= 3 and peer_n >= 3:
        leadership_bonus = 6   # V5.5: +3→+6, 🟡 板块前排
    elif intra_rank > 5 and peer_n >= 5:
        leadership_bonus = -3  # 🔴 板块跟风, 次日最先被淘汰
    else:
        leadership_bonus = 0

    # ── V6.7 R2: 零板块支撑保留但降低惩罚(V6.6回退) ──
    if peer_n == 0:
        independent_penalty = 10  # 零板块支撑: 中等惩罚(非淘汰)
    elif peer_n == 1:
        independent_penalty = 3   # 独苗: 轻罚
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

    # ── 板块共振 (V5.9: 0-8, 回测验证最优区间) ──
    sh = get_shanghai_index(db, trade_date)
    if sp > 2 and sh > 0:
        res_score = 0   # 板块+大盘双强 → 过热, 次日回调
    elif sp > 0 and sh < 0:
        res_score = 5   # 板块逆市走强(已涨过)
    elif sp < 0 and sh < 0 and sp > sh:
        res_score = 8   # 板块抗跌, 最佳共振
    elif sp < -1:
        res_score = 8   # 板块超跌, 次日反弹
    else:
        res_score = 5

    # ── V5.8 P6: 行业5日动量黑名单 — 板块近5日累计<0扣8分 ──
    sector_blacklist_penalty = 0
    try:
        td8 = trade_date.replace('-', '')
        # Get 5-day sector return from ths_daily or sw_daily
        sector_5d = db.execute(
            "SELECT SUM(change_pct) as sum5d FROM ("
            "SELECT change_pct FROM ths_daily WHERE name LIKE ? AND trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT 5"
            ") t",
            (f"%{industry}%", td8)
        ).fetchone()
        s5d = sector_5d["sum5d"] if sector_5d and sector_5d["sum5d"] else None
        if s5d is None:
            sector_5d = db.execute(
                "SELECT SUM(change_pct) as sum5d FROM ("
                "SELECT change_pct FROM sw_daily WHERE name LIKE ? AND trade_date <= ? "
                "ORDER BY trade_date DESC LIMIT 5"
                ") t",
                (f"%{industry}%", trade_date)
            ).fetchone()
            s5d = sector_5d["sum5d"] if sector_5d and sector_5d["sum5d"] else 0
        if s5d and s5d < 0:
            sector_blacklist_penalty = 8  # 板块5日趋势向下
    except Exception:
        pass

    # ── V6.2 P19: 距涨停距离因子 (0-10) — 距离越远可交易性越好 ──
    # dist_to_limit already computed in P16
    if dist_to_limit >= 10: dist_score = 10       # 充足空间, 完全可交易
    elif dist_to_limit >= 7: dist_score = 8        # 较好空间
    elif dist_to_limit >= 5: dist_score = 6        # 中等空间
    elif dist_to_limit >= 3: dist_score = 4        # 偏近
    else: dist_score = 2                           # 临界(2-3%, P16已淘汰<2%)

    # ── V6.2 P18: 满分龙头 × 远离涨停加成 — 11笔+4.45%, 确定性最高 ──
    leader_distance_bonus = 0
    if sl_score >= 24 and dist_to_limit >= 5:
        leader_distance_bonus = 8  # 🔥 满分龙头+足够空间=高确定性盈利

    # ── 尾盘V3 O2: 共振信号强化(±5, 共振=8→50%胜率+1.33%最强信号) ──
    resonance_bonus = 0
    if res_score >= 8:
        resonance_bonus = 5
    elif res_score <= 5:
        resonance_bonus = -5

    # 将成龙: 午后稳步走强 + 量能放大 + 涨幅8-10%(非涨停板)
    if 0 < afternoon_str <= 2.5 and vol_surge >= 2.0 and 8 <= gain_14 < 10.5:
        rhythm_bonus = 4; rhythm_label = "将成龙"
    # 惯性套利: 已高位 + 板块过热(sp>2) + 涨幅>10.5%
    elif gain_14 > 10.5 and sp > 2:
        rhythm_bonus = -3; rhythm_label = "惯性套利"
    # 强分: 默认, 不强不弱=中等
    else:
        rhythm_bonus = 0; rhythm_label = "强分"

    # ── V6.6 O4: 融资融券信号 — 前日融资变化反映杠杆资金方向 ──
    margin_bonus = 0
    try:
        # Get previous 2 trading days' margin balances
        margin_rows = db.execute(
            "SELECT rzye, trade_date FROM margin_detail WHERE code=? AND trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT 2",
            (code, trade_date)
        ).fetchall()
        if len(margin_rows) >= 2 and margin_rows[0]["rzye"] and margin_rows[1]["rzye"]:
            today_rzye = float(margin_rows[0]["rzye"])
            prev_rzye = float(margin_rows[1]["rzye"])
            if prev_rzye > 0:
                rzye_chg = (today_rzye - prev_rzye) / prev_rzye * 100
                if rzye_chg > 2:       # 融资显著增加(>2%)→杠杆资金强烈看多
                    margin_bonus = 4
                elif rzye_chg > 0:     # 融资微增→温和看多
                    margin_bonus = 2
                elif rzye_chg < -3:    # 融资显著减少(<-3%)→杠杆资金撤离
                    margin_bonus = -4
                elif rzye_chg < 0:     # 融资微减→温和看空
                    margin_bonus = -1
    except Exception:
        pass  # 无融资数据时不影响评分

    # ── V6.7 综合 (9因子) ──
    total_complex = (gain_score + seal_score + afternoon_score +
             turnover_score + ma_score + volume_score + sl_score + sm_score + res_score
             + dist_score + leadership_bonus + leader_distance_bonus
             + resonance_bonus + margin_bonus
             + sector_resonance_bonus
             - independent_penalty - climax_penalty - overheat_penalty
             - limit_resistance_penalty - sector_blacklist_penalty)

    # ── V7.0 S1: 简化三因子评分 — 数据驱动(AUC验证), 去噪声 ──
    # gain(AUC=0.49逆): 涨幅越低越好 | dist(AUC=0.51): 距涨停越远越好 | res(AUC=0.52): 共振越高越好
    simple_score = (-gain_14 * 0.5 + dist_to_limit * 0.3 + res_score * 2) * 5 + 50
    # 50% 复杂模型 + 50% 简化模型 → 取长补短
    total = int(total_complex * 0.5 + simple_score * 0.5)
    grade = "S" if total >= 65 else ("A" if total >= 50 else ("B" if total >= 35 else "C"))  # 尾盘V3: 降门槛修复倒挂

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
        "dist_to_limit": round(dist_to_limit, 2),            # V6.2: 距涨停距离
        "dist_score": dist_score,                            # V6.2: 距离因子分
        "independent_penalty": independent_penalty,         # V5.1 P1
        "climax_penalty": climax_penalty,                   # V5.1 P0
        "overheat_penalty": overheat_penalty,               # V5.1 P0b
    }


# ── V5.4 性能优化: 批量预计算 ──

def _precompute_industry_stats(db, trade_date, time_slot):
    """批量预计算每个行业的 peer_count 和涨幅排名.

    替代 score_intraday_stock 中 per-stock 的 peer_count + intra_rank 查询.
    1 次查询覆盖所有行业, 节省 ~90ms × N 只股票.
    """
    rows = db.execute(
        "SELECT s.industry, COUNT(DISTINCT SUBSTR(m.ts_code,1,6)) as peer_cnt, "
        "MAX((m.close/l.pre_close-1)*100) as max_gain "
        "FROM stk_mins m "
        "JOIN stocks s ON s.code=SUBSTR(m.ts_code,1,6) "
        "JOIN stk_limit l ON s.code=l.code AND l.trade_date=? "
        "WHERE m.trade_time LIKE ? AND m.freq='5min' "
        "AND l.pre_close>0 AND (m.close/l.pre_close-1)*100>=5 "
        "GROUP BY s.industry",
        (trade_date, f"{trade_date} {time_slot}%")
    ).fetchall()

    result = {}
    for r in rows:
        ind = r["industry"] or "其他"
        result[ind] = {"peer_count": r["peer_cnt"] or 0, "max_gain": float(r["max_gain"] or 0)}
    return result


def _prefetch_kline_batch(db, trade_date):
    """批量预取所有股票的近60日K线数据.

    替代 score_intraday_stock 中 per-stock 的 get_kline_data 查询.
    1 次查询, 节省 ~11ms × N 只股票.
    """
    # 计算60个交易日前的日期 (约3个月)
    parts = trade_date.split("-")
    y, m = int(parts[0]), int(parts[1])
    m -= 3
    if m <= 0:
        m += 12
        y -= 1
    start_date = f"{y}-{m:02d}-01"

    rows = db.execute(
        "SELECT code, close, volume, amount FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date <= ? ORDER BY code, trade_date ASC",
        (start_date, trade_date)
    ).fetchall()

    import numpy as np
    from collections import defaultdict
    result = {}
    by_code = defaultdict(list)
    for r in rows:
        c = r.get("code") or r.get("ts_code", "")
        if not c:
            continue
        by_code[c].append((float(r["close"] or 0), float(r["volume"] or 0), float(r["amount"] or 0)))

    for code, data in by_code.items():
        if len(data) >= 20:
            result[code] = (
                np.array([d[0] for d in data], dtype=np.float64),
                np.array([d[1] for d in data], dtype=np.float64),
                np.array([d[2] for d in data], dtype=np.float64),
            )
    return result


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


def run_intraday_screening(trade_date, time_slot="14:40", top_n=20):  # V5.9: 默认14:40
    """V5.4 盘中选股主流程 (P0高潮检测 + P1独立过滤 + 批量预计算)."""
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

        # ── V5.4 性能优化: 批量预计算 ──
        t_pre = time.time()
        industry_stats = _precompute_industry_stats(db, trade_date, time_slot)
        kline_cache = _prefetch_kline_batch(db, trade_date)
        mins_agg_cache = _prefetch_mins_agg_batch(db, trade_date, time_slot)
        print(f"  ⚡ 预计算: {len(industry_stats)}行业 + {len(kline_cache)}K线 + {len(mins_agg_cache)}分钟, {time.time()-t_pre:.1f}s")

        scores = []
        for r in stocks:
            c = r["code"]
            if c not in snapshot or c not in pre_closes: continue
            try:
                res = score_intraday_stock(c, r["name"], r["industry"] or "其他",
                                            snapshot[c], pre_closes[c], db,
                                            trade_date, time_slot, limit_map,
                                            industry_stats, kline_cache,
                                            mins_agg_cache)
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
                "FROM (SELECT DISTINCT code, close FROM stk_mins "
                "      WHERE trade_time >= ? AND trade_time <= ? AND freq='5min') m "
                "JOIN daily_kline d ON d.code=SUBSTR(m.code,1,6) AND d.trade_date=? "
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

        # ── V5.6 A: 弱市熔断提示 ──
        if len(scores) < 30:
            print(f"  ⚠️ 弱市预警: 仅{len(scores)}只通过初筛, 建议谨慎/减仓")

                # ── V6.3 P20: 初筛20-40熔断 — 仅对14:40生效(回测校准)
        if time_slot == '14:40' and 20 <= len(scores) < 40:
            print(f"  假活跃熔断: {len(scores)}只(20-40区间), 次日全面回调, 空仓")
            return [], [], []

        # ── V6.5 O3: 市场广度信号 — 弱市稀缺溢价, 注入个股评分 ──
        # 涨跌比越低 → 能逆市走强的个股质量越高 → 次日溢价越大
        if breadth < 30:
            market_breadth_bonus = 5   # 极弱市: 稀缺溢价最高(日均+1.12%)
            print(f"  📈 极弱市 涨跌比{breadth:.0f}%: 个股+5分(强者恒强)")
        elif breadth < 50:
            market_breadth_bonus = 3   # 弱市: 溢价(日均+0.86%)
            print(f"  📈 弱市 涨跌比{breadth:.0f}%: 个股+3分")
        elif breadth < 65:
            market_breadth_bonus = 0   # 中强市: 无溢价(日均-0.20%)
            print(f"  📉 中强市 涨跌比{breadth:.0f}%: 个股+0分(信号稀释)")
        else:
            market_breadth_bonus = -2  # 强市: 轻度惩罚(日均+0.26%)
            print(f"  📉 强市 涨跌比{breadth:.0f}%: 个股-2分")

        if breadth < 40:
            effective_n = max(5, int(top_n * 0.5))
            print(f"  🌧️ 涨跌比 {breadth:.0f}% (<40%), Top-N {top_n}→{effective_n}")
        elif breadth < 55:
            effective_n = max(8, int(top_n * 0.7))
            print(f"  ⛅ 涨跌比 {breadth:.0f}% (40-55%), Top-N {top_n}→{effective_n}")
        else:
            effective_n = top_n

        # V5.2: 市场狂热日进一步收紧
        if market_frenzy:
            frenzy_n = max(5, int(effective_n * 0.5))
            print(f"  🔥 市场狂热: effective_n {effective_n}→{frenzy_n}")
            effective_n = frenzy_n

        # ── V6.4 O1: 日级别择时 — 共振均值决定仓位 ──
        if scores:
            avg_res = sum(s.get("resonance_score", 0) for s in scores) / len(scores)
            if avg_res <= 5:
                effective_n = max(3, int(effective_n * 0.5))
                print(f"  🔻 共振弱(均{avg_res:.1f}≤5): effective_n →{effective_n} (-50%)")
            if avg_res <= 4:
                effective_n = max(1, int(effective_n * 0.3))
                print(f"  🛑 共振极弱(均{avg_res:.1f}≤4): effective_n →{effective_n} (-70%), 几乎空仓")

        # ── V5.8 P7: 周一加成+周五减仓 ──
        from datetime import datetime
        dow = datetime.strptime(trade_date, "%Y-%m-%d").weekday()
        if dow == 0:  # Monday
            effective_n = min(top_n, int(effective_n * 1.3))
            print(f"  📈 周一效应: effective_n →{effective_n} (+30%)")
        elif dow == 4:  # Friday
            effective_n = max(3, int(effective_n * 0.7))
            print(f"  📉 周五减仓: effective_n →{effective_n} (-30%)")

    scores.sort(key=lambda x: -x["total_score"])

    # ── V5.8 P8: 日内评分归一化 (≥5只启用) — 映射到0-100标准分, 跨天可比 ──
    if len(scores) >= 5:
        raw_max = scores[0]["total_score"]
        raw_min = scores[-1]["total_score"]
        score_range = raw_max - raw_min if raw_max > raw_min else 1
        for s in scores:
            s["total_score_raw"] = s["total_score"]
            s["total_score"] = round((s["total_score"] - raw_min) / score_range * 100, 1)
            # V6.5 O3: 市场广度溢价(归一化后注入, 不被吞掉)
            s["total_score"] += market_breadth_bonus
            ns = s["total_score"]
            s["grade"] = "S" if ns >= 60 else ("A" if ns >= 45 else ("B" if ns >= 30 else "C"))  # 尾盘V3: 同步降门槛

    return scores[:effective_n], scores


def generate_intraday_plan(picks):
    plans = []
    for s in picks:
        entry = round(s["close_14"], 2)          # 尾盘V1.0: 现价入场
        stop = round(s["close_14"] * 0.97, 2)     # 尾盘V1.0: 3%止损
        g = s["grade"]
        # V5.9 P11: 满分龙头(24分)仓位翻倍 — 74%胜率+3.66%均值
        is_full_leader = s.get("sector_leader_score", 0) >= 24
        if is_full_leader and g == "S":
            pos = "25%"  # 满分龙头: 重仓
        elif is_full_leader and g == "A":
            pos = "20%"  # 满分龙头A级: 加仓
        elif g == "S":
            pos = "20%"
        elif g == "A":
            pos = "15%"
        elif g == "B":
            pos = "10%"
        else:
            pos = "0%"
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
    """V5.4 秋神龙头战法-盘中引擎 — 14:00 选股 (批量预计算加速)."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute intraday screening."""
        picks, scores = run_intraday_screening(trade_date or "latest", top_n=top_n)
        return picks if picks else []
