#!/usr/bin/env python3
"""秋神龙头战法-午后选股模型 — Afternoon Leader Picking Model.

基于尾盘战法 (leader_scalp.py) 改造，14:30 盘中选股，当日尾盘买入，次日套利。

方案B改造要点:
  1. 今日数据: daily_kline → stk_mins (14:30 快照)
  2. 涨停检测: limit_list_d → stk_mins.close ≈ stk_limit.up_limit
  3. 封板质量: 降级评分 (只知是否涨停, 不知封板时间/开板次数/封单量)
  4. resilience: 用 14:30 日内OHLC 近似计算
  5. 成交额: 14:30 累计 / 0.78 预估全天

Usage:
    python tools/backtest_afternoon.py --month 2026-06 --top-n 20 --time 14:30
"""

import os, sys, time
from collections import defaultdict
from datetime import datetime
from enum import Enum

import numpy as np

_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TUSHARE_TOKEN", os.environ.get("TUSHARE_TOKEN", ""))

from kronos_factors.scorer._db_stub import _get_db

# ── 午后完成度 (14:00→65%, 14:30→78%) ──
TIME_COMPLETION = {
    "10:00": 0.15, "10:30": 0.25, "11:00": 0.35, "11:30": 0.45,
    "13:00": 0.48, "13:30": 0.55, "14:00": 0.65, "14:30": 0.78,
    "14:40": 0.85, "15:00": 1.00,
}

# ── 市场环境枚举 ──
class MarketEnv(Enum):
    BULL = "bull"
    NEUTRAL = "neutral"
    BEAR = "bear"
    CRASH = "crash"

# ── 午后选股权重 (复制尾盘战法, 封板质量降权 5→3, 分歧不死保持 5) ──
WEIGHTS = {
    "gain_quality": 20,
    "sector_leader": 28,
    "ma_trend": 3,
    "turnover": 10,
    "sector_resonance": 8,
    "capital_flow": 22,
    "sector_momentum": 15,
    "seal_quality": 3,       # 降权: 无封板细节
    "resilience": 5,         # 保持: 14:30 日内数据可用
}
TOTAL_WEIGHT = sum(WEIGHTS.values())

# 回测 2026-03-24~2026-06-24 的轻量行业校准。
# 只做小幅加减分，避免把三个月样本过拟合成硬名单。
AFTERNOON_WEAK_INDUSTRIES = {"建筑工程", "矿物制品", "通信设备", "软件服务"}
AFTERNOON_SUPPORTIVE_INDUSTRIES = {"汽车配件", "生物制药", "元器件"}


def _afternoon_grade(total_score):
    """Map afternoon model score to grade."""
    if total_score >= 85:
        return "S"
    if total_score >= 72:
        return "A"
    if total_score >= 60:
        return "B"
    return "C"


def apply_afternoon_optimization(score):
    """Apply post-backtest crowding and industry calibration to one pick."""
    optimised = dict(score)
    raw_total = float(optimised.get("total_score", 0) or 0)
    gain_pct = float(optimised.get("gain_pct", 0) or 0)
    dist_to_limit = float(optimised.get("dist_to_limit", 99) or 99)
    amount_yi = float(optimised.get("amount_yi_est", 0) or 0)
    volume_score = float(optimised.get("volume_score", 0) or 0)
    capital_score = float(optimised.get("capital_score", 0) or 0)
    code = str(optimised.get("code", ""))
    industry = optimised.get("industry", "")
    is_20cm = code.startswith(("300", "301", "688"))

    penalty = 0
    bonus = 0
    flags = []

    high_gain = gain_pct >= (17.0 if is_20cm else 8.8)
    if high_gain and dist_to_limit <= 1.2:
        penalty += 8
        flags.append("crowded_breakout")

    if amount_yi >= 15 and volume_score >= 10:
        penalty += 4
        flags.append("high_turnover_crowding")

    if amount_yi >= 10 and gain_pct >= 8 and capital_score <= 10:
        penalty += 3
        flags.append("weak_capital_confirmation")

    if industry in AFTERNOON_WEAK_INDUSTRIES:
        penalty += 6
        flags.append("weak_industry")
    elif industry in AFTERNOON_SUPPORTIVE_INDUSTRIES:
        bonus += 2
        flags.append("supportive_industry")

    total = max(0, raw_total - penalty + bonus)
    optimised["raw_total_score"] = raw_total
    optimised["total_score"] = total
    optimised["grade"] = _afternoon_grade(total)
    optimised["optimization_penalty"] = penalty
    optimised["optimization_bonus"] = bonus
    optimised["optimization_flags"] = flags
    return optimised


def filter_tradeable_afternoon_picks(picks, top_n=None, drop_no_trade=True):
    """Return picks eligible for trading after market-regime filters."""
    tradeable = [
        dict(p)
        for p in picks
        if not (drop_no_trade and p.get("_no_trade"))
    ]
    tradeable.sort(key=lambda x: -float(x.get("total_score", 0) or 0))
    return tradeable[:top_n] if top_n else tradeable


def build_sector_resonance_summary(picks, limit=10):
    """Aggregate pick-level sector resonance into a compact sector table."""
    grouped = {}
    for pick in picks:
        sector = pick.get("industry") or "其他"
        item = grouped.setdefault(
            sector,
            {
                "sector": sector,
                "pick_count": 0,
                "resonance_scores": [],
                "sector_changes": [],
                "peer_counts": [],
                "representatives": [],
            },
        )
        item["pick_count"] += 1
        item["resonance_scores"].append(float(pick.get("resonance_score", 0) or 0))
        item["sector_changes"].append(float(pick.get("sector_change", 0) or 0))
        item["peer_counts"].append(int(pick.get("peer_count", 0) or 0))
        if len(item["representatives"]) < 3:
            item["representatives"].append(pick.get("name") or pick.get("code"))

    summary = []
    for item in grouped.values():
        resonance_scores = item.pop("resonance_scores")
        sector_changes = item.pop("sector_changes")
        peer_counts = item.pop("peer_counts")
        item["avg_resonance_score"] = round(float(np.mean(resonance_scores)), 1) if resonance_scores else 0
        item["avg_sector_change"] = round(float(np.mean(sector_changes)), 2) if sector_changes else 0
        item["max_peer_count"] = max(peer_counts) if peer_counts else 0
        summary.append(item)

    summary.sort(key=lambda x: (x["pick_count"], x["avg_resonance_score"]), reverse=True)
    return summary[:limit]


def select_afternoon_top(scores, market_env, top_n=20, full_output=False):
    """Select final afternoon picks with either strict or full-observation rules."""
    if full_output:
        return list(scores[:top_n])

    if market_env == MarketEnv.BULL:
        max_per_sector = 3; min_grade = "B"
    elif market_env == MarketEnv.NEUTRAL:
        max_per_sector = 2; min_grade = "A"
    else:
        max_per_sector = 1; min_grade = "S"

    grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
    top = []
    sector_counts = {}
    for s in scores:
        ind = s.get("industry", "其他")
        cnt = sector_counts.get(ind, 0)
        if grade_order.get(s.get("grade", "C"), 3) > grade_order.get(min_grade, 2):
            continue
        if cnt < max_per_sector:
            top.append(s)
            sector_counts[ind] = cnt + 1
        if len(top) >= top_n:
            break
    return top


# ═══════════════════════ 数据获取 (stk_mins 版本) ═══════════════════════

def get_intraday_ohlc(db, code, trade_date, time_slot="14:30"):
    """从 stk_mins 获取14:30的日内OHLC (替代 daily_kline 今日数据)."""
    row = db.execute(
        "SELECT open, high, low, close, volume, amount FROM stk_mins "
        "WHERE ts_code LIKE ? AND trade_time <= ? AND freq='5min' "
        "ORDER BY trade_time DESC LIMIT 1",
        (f"{code}%", f"{trade_date} {time_slot}:59")
    ).fetchone()
    if not row or not row["close"]:
        return None
    return {
        "open": float(row["open"] or 0),
        "high": float(row["high"] or 0),
        "low": float(row["low"] or 0),
        "close": float(row["close"] or 0),
        "volume": float(row["volume"] or 0),
        "amount": float(row["amount"] or 0),
    }


def get_intraday_cumulative(db, code, trade_date, time_slot="14:30"):
    """获取当日截至指定时点的累计成交额和日内最高/最低."""
    rows = db.execute(
        "SELECT MAX(high) as day_high, MIN(low) as day_low, "
        "SUM(amount) as total_amount, SUM(volume) as total_volume "
        "FROM stk_mins WHERE ts_code LIKE ? "
        "AND trade_time >= ? AND trade_time <= ? AND freq='5min'",
        (f"{code}%", f"{trade_date} 09:00:00", f"{trade_date} {time_slot}:59")
    ).fetchone()
    if rows:
        return {
            "day_high": float(rows["day_high"] or 0),
            "day_low": float(rows["day_low"] or 0),
            "total_amount": float(rows["total_amount"] or 0),
            "total_volume": float(rows["total_volume"] or 0),
        }
    return {"day_high": 0, "day_low": 0, "total_amount": 0, "total_volume": 0}


def estimate_full_day_amount(intraday_amount, time_slot="14:30"):
    """预估全天成交额."""
    ratio = TIME_COMPLETION.get(time_slot, 0.78)
    return intraday_amount / max(0.01, ratio)


def get_intraday_snapshot(db, trade_date, time_slot="14:30"):
    """14:30 全市场快照."""
    time_cutoff = f"{trade_date} {time_slot}:59"
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
        raw_code = r.get("code") or r.get("ts_code", "")
        code = raw_code.split('.')[0] if '.' in str(raw_code) else str(raw_code)
        snapshot[code] = {
            "open": float(r["open"] or 0), "high": float(r["high"] or 0),
            "low": float(r["low"] or 0), "close": float(r["close"] or 0),
            "volume": float(r["volume"] or 0), "amount": float(r["amount"] or 0),
        }
    return snapshot


def get_historical_snapshot(db, trade_date):
    """回测模式: 用 daily_kline 日线数据模拟14:30快照.

    历史日期没有 stk_mins，用当日日线OHLC作为快照数据。
    amount 为全天成交额（回测中无法区分14:30累计）。
    """
    rows = db.execute(
        "SELECT code, open, high, low, close, volume, amount "
        "FROM daily_kline WHERE trade_date=? AND volume > 0",
        (trade_date,)
    ).fetchall()
    snapshot = {}
    for r in rows:
        code = r.get("code") or r.get("ts_code", "")
        if not code:
            continue
        snapshot[code] = {
            "open": float(r["open"] or 0), "high": float(r["high"] or 0),
            "low": float(r["low"] or 0), "close": float(r["close"] or 0),
            "volume": float(r["volume"] or 0), "amount": float(r["amount"] or 0),
        }
    return snapshot


def get_unified_snapshot(db, trade_date, time_slot="14:30"):
    """统一快照: 实时用 stk_mins, 历史用 daily_kline. 自动检测."""
    from datetime import date
    today = date.today().strftime("%Y-%m-%d")

    if trade_date == today:
        # Try stk_mins first
        snap = get_intraday_snapshot(db, trade_date, time_slot)
        if len(snap) > 100:
            return snap, "live"

    # Fallback: daily_kline for historical dates or if stk_mins empty
    snap = get_historical_snapshot(db, trade_date)
    return snap, "historical" if snap else "empty"


# ── 保留的原始函数 (不依赖 daily_kline 今日数据) ──

def get_pre_close(db, code, trade_date):
    """获取前日收盘价.

    优先级: stk_limit.pre_close > stk_auction_o.close > daily_kline.close
    stk_auction_o.close 是 Tushare 新 API 的 pre_close 字段，
    当日 9:25 即可用，比 daily_kline (T+1 盘后) 更及时。
    """
    # Path 1: stk_limit (最权威的昨收价)
    row = db.execute(
        "SELECT pre_close FROM stk_limit WHERE code=? AND trade_date=?",
        (code, trade_date)
    ).fetchone()
    if row and row["pre_close"] and float(row["pre_close"]) > 0:
        return float(row["pre_close"])
    # Path 2: stk_auction_o.close = pre_close (当日 9:25 可用，比 daily_kline 及时)
    try:
        row = db.execute(
            "SELECT close FROM stk_auction_o WHERE code=? AND trade_date=? AND close > 0",
            (code, trade_date)
        ).fetchone()
        if row and row["close"] and float(row["close"]) > 0:
            return float(row["close"])
    except Exception:
        pass
    # Path 3: daily_kline (T+1 盘后才有，可能滞后一天)
    row = db.execute(
        "SELECT close FROM daily_kline WHERE code=? AND trade_date < ? "
        "ORDER BY trade_date DESC LIMIT 1",
        (code, trade_date)
    ).fetchone()
    return float(row["close"]) if row and row["close"] else 0


def get_kline_history(db, code, trade_date, lookback=60):
    """获取历史日K线 (不含今日, 用于MA/ATR)."""
    rows = db.execute(
        "SELECT open, high, low, close, volume, amount, trade_date "
        "FROM daily_kline WHERE code=? AND trade_date<=? "
        "ORDER BY trade_date ASC",
        (code, trade_date)
    ).fetchall()
    return rows


def compute_ma(closes, period):
    if len(closes) < period:
        return None
    return float(np.mean(closes[-period:]))


def calc_atr(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return 0
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_arr = np.zeros(n)
    atr_arr[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        atr_arr[i] = (atr_arr[i - 1] * (period - 1) + tr[i]) / period
    return float(atr_arr[-1]) if atr_arr[-1] > 0 else 0


def get_moneyflow(db, code, trade_date):
    """主力资金 (T+1延迟, 可能为空)."""
    row = None
    try:
        row = db.execute(
            "SELECT buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount, "
            "net_mf_amount FROM moneyflow_dc WHERE ts_code LIKE ? AND trade_date=?",
            (f"{code}%", trade_date.replace('-', ''))
        ).fetchone()
    except Exception:
        pass  # moneyflow_dc may not exist in PG, fallback to moneyflow

    if not row:
        try:
            row = db.execute(
                "SELECT buy_lg_amount, sell_lg_amount, buy_elg_amount, sell_elg_amount, "
                "net_mf_amount FROM moneyflow WHERE code=? AND trade_date=?",
                (code, trade_date)
            ).fetchone()
        except Exception:
            pass
    return row


def _row_value(row, *keys, default=None):
    """Read a value from dict-like or tuple-like DB rows."""
    if not row:
        return default
    if isinstance(row, dict):
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return default
    try:
        return row[0]
    except Exception:
        return default


def resolve_afternoon_trade_date(db):
    """Prefer today's intraday snapshot date, then fall back to latest daily date."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM stk_mins WHERE trade_time LIKE ?",
            (f"{today}%",),
        ).fetchone()
        if int(_row_value(row, "cnt", default=0) or 0) > 100:
            return today
    except Exception:
        pass

    row = db.execute("SELECT MAX(trade_date) as max_date FROM daily_kline").fetchone()
    val = _row_value(row, "max_date", "max")
    return val.strftime("%Y-%m-%d") if hasattr(val, "strftime") else str(val)[:10] if val else None


def get_shanghai_index(db, trade_date):
    """上证指数涨跌幅 — 兼容 PG adapter 的列名翻译 (change_pct→pct_chg)."""
    row = db.execute(
        "SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=?",
        (trade_date,)
    ).fetchone()
    val = _row_value(row, "pct_chg", "change_pct")
    if val is not None:
        return float(val)
    return 0.0


def assess_market_env(db, trade_date):
    """市场环境评估 (同尾盘战法)."""
    detail = {"sh_pct": 0, "limit_down_count": 0, "breadth": 0, "reason": ""}

    sh_pct = get_shanghai_index(db, trade_date)
    detail["sh_pct"] = round(sh_pct, 2)

    if sh_pct < -2:
        detail["reason"] = f"上证暴跌{sh_pct:.1f}%, 触发熔断"
        return MarketEnv.CRASH, detail

    td = trade_date.replace('-', '')
    ld_row = db.execute(
        "SELECT COUNT(*) as cnt FROM limit_list_d WHERE trade_date=? AND pct_chg < 0", (td,)
    ).fetchone()
    ld_count = ld_row["cnt"] if ld_row else 0
    detail["limit_down_count"] = ld_count

    if ld_count > 50:
        detail["reason"] = f"跌停{ld_count}家, 触发熔断"
        return MarketEnv.CRASH, detail

    prev_date_row = db.execute(
        "SELECT trade_date FROM daily_kline WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 1",
        (trade_date,)
    ).fetchone()
    if prev_date_row:
        prev_date = list(prev_date_row.values())[0] if isinstance(prev_date_row, dict) else prev_date_row[0]
        # Use stk_mins snapshot to compute breadth
        snapshot = get_intraday_snapshot(db, trade_date, "14:30")
        # Get pre_close from daily_kline (Tushare stk_limit API has no pre_close!)
        # Use the previous trading day's close for all stocks in the snapshot
        pre_closes = {}
        if prev_date:
            prev_date_str = prev_date.strftime("%Y-%m-%d") if hasattr(prev_date, 'strftime') else str(prev_date)[:10]
            # Batch lookup: get all snapshot codes' previous close in one query
            snapshot_codes = list(snapshot.keys())
            batch_size = 1000
            for i in range(0, len(snapshot_codes), batch_size):
                batch = snapshot_codes[i:i+batch_size]
                placeholders = ",".join(["?"] * len(batch))
                prev_rows = db.execute(
                    f"SELECT code, close FROM daily_kline WHERE trade_date=? AND code IN ({placeholders})",
                    [prev_date_str] + batch
                ).fetchall()
                for r in prev_rows:
                    code = r["code"] or r.get("ts_code", "")
                    if code:
                        pre_closes[code] = float(r["close"] or 0)
            print(f"  📊 pre_close from daily_kline({prev_date_str}): {len(pre_closes)} stocks")

        up_count = sum(1 for code, snap in snapshot.items()
                       if code in pre_closes and pre_closes[code] > 0
                       and snap["close"] > pre_closes[code])
        down_count = sum(1 for code, snap in snapshot.items()
                         if code in pre_closes and pre_closes[code] > 0
                         and snap["close"] < pre_closes[code])
        total = up_count + down_count
        breadth = up_count / max(1, total) * 100
    else:
        breadth = 50

    detail["breadth"] = round(breadth, 1)

    if breadth < 25:
        detail["reason"] = f"涨跌比仅{breadth:.0f}%, 极度弱势"
        return MarketEnv.BEAR, detail

    # 连续下跌
    prev_dates = db.execute(
        "SELECT DISTINCT trade_date FROM daily_kline WHERE trade_date <= ? "
        "ORDER BY trade_date DESC LIMIT 4", (trade_date,)
    ).fetchall()
    cons_drops = 0
    for i in range(len(prev_dates) - 1):
        d = list(prev_dates[i].values())[0] if isinstance(prev_dates[i], dict) else prev_dates[i][0]
        pd_row = db.execute(
            "SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=?", (d,)
        ).fetchone()
        pct = _row_value(pd_row, "pct_chg", "change_pct", default=0)
        if pct and float(pct) < 0:
            cons_drops += 1
        else:
            break

    detail["consecutive_drops"] = cons_drops

    if cons_drops >= 4:
        detail["reason"] = f"上证连续{cons_drops}日下跌, 触发观望"
        return MarketEnv.BEAR, detail
    elif cons_drops >= 3:
        detail["reason"] = f"上证连续{cons_drops}日下跌, 谨慎"
        return MarketEnv.NEUTRAL, detail
    elif breadth < 40:
        detail["reason"] = f"涨跌比{breadth:.0f}%偏低"
        return MarketEnv.NEUTRAL, detail

    return MarketEnv.BULL, detail


# ═══════════════════════ 涨停检测 (stk_mins + stk_limit 替代 limit_list_d) ═══════════════════════

def detect_intraday_limits(db, trade_date, snapshot, pre_closes):
    """从 stk_mins 14:30快照 + stk_limit 检测涨停板.

    替代 limit_list_d, 因为盘中 limit_list_d 不可用.
    Returns: {code: {"is_at_limit": bool, "dist_to_limit_pct": float}}
    """
    limit_rows = db.execute(
        "SELECT code, up_limit FROM stk_limit WHERE trade_date=?", (trade_date,)
    ).fetchall()
    limit_prices = {}
    for r in limit_rows:
        code = r["code"]
        up = r["up_limit"]
        if up and float(up) > 0:
            limit_prices[code] = float(up)

    result = {}
    for code, snap in snapshot.items():
        close_14 = snap["close"]
        up_lim = limit_prices.get(code, 99999)
        pc = pre_closes.get(code, 0)

        if pc <= 0 or close_14 <= 0:
            result[code] = {"is_at_limit": False, "dist_to_limit_pct": 99}
            continue

        is_at_limit = close_14 >= up_lim * 0.995 if up_lim < 99999 else False
        dist_pct = (up_lim / close_14 - 1) * 100 if close_14 > 0 else 99
        result[code] = {"is_at_limit": is_at_limit, "dist_to_limit_pct": dist_pct}

    return result


# ═══════════════════════ 分歧不死 (14:30 日内版) ═══════════════════════

def score_resilience_intraday(intraday_ohlc):
    """分歧不死验证 — 14:30 日内版.

    与原版差异:
      - 使用 14:30 时的日内high/low/close (非最终值)
      - 14:30 距收盘只有30分钟, high/low 接近最终, close 可能还有变化
      - 因此降权: 原版 0-5 → 日内版 0-4 (留一分给不确定性)
    """
    score = 0
    tod_open = intraday_ohlc.get("open", 0)
    tod_low = intraday_ohlc.get("low", 0)
    tod_high = intraday_ohlc.get("high", 0)
    tod_close = intraday_ohlc.get("close", 0)

    if tod_open <= 0:
        return 0

    intraday_drop = (tod_low / tod_open - 1) * 100
    high_ratio = tod_close / tod_high if tod_high > 0 else 0

    # 维度1: 日内分歧程度 (同原版)
    if tod_low >= tod_open:
        score += 3
    elif intraday_drop > -2:
        score += 2
    elif intraday_drop > -4:
        score += 1

    # 维度2: 恢复力 (14:30版 — 留一分空间, 因为尾盘可能再冲)
    if high_ratio >= 0.99:
        score += 1  # 原版+2, 日内版+1 (尾盘不确定性)
    elif high_ratio >= 0.97:
        score += 0  # 原版+1, 日内版不加 (还需尾盘确认)

    return min(4, score)


# ═══════════════════════ 核心评分函数 ═══════════════════════

def score_stock_afternoon(code, name, industry, snap, pre_close, db, trade_date,
                           time_slot="14:30", limit_info=None,
                           sector_stats=None, kline_cache=None, is_historical=False,
                           allow_at_limit=False):
    """午后选股评分 (方案B: stk_mins数据 + 降级封板 + 日内分歧不死)."""
    close_14 = snap["close"]
    amount_14 = snap["amount"]
    volume_14 = snap["volume"]

    if close_14 <= 0 or pre_close <= 0:
        return None

    # ── 北交所排除 ──
    if code.startswith(('92', '83', '87', '4')):
        return None

    gain_pct = (close_14 / pre_close - 1) * 100

    # ── 涨幅窗口: 统一 ≥7%, 无上限 (14:30放宽) ──
    # 主板: ≥7% (原版7-12%, 14:30版有尾盘冲板空间故不设上限)
    # 科创/创业板: ≥7%
    # 硬止损: >25% 淘汰 (14:30已极度拉伸, 次日大概率暴跌, 回测验证)
    board_type = 'star' if code.startswith('688') else ('gem' if code.startswith(('300','301')) else 'main')

    if gain_pct < 7.0:
        return None
    if gain_pct > 25.0:
        return None  # 14:30涨幅>25%已过度拉伸, 次日暴跌风险极高

    if board_type == 'main':
        limit_pct = 1.10
    else:
        limit_pct = 1.20

    if 'ST' in name.upper():
        return None

    # ── 距涨停距离 (仅计算, 不做硬过滤) ──
    limit_price = pre_close * limit_pct
    dist_to_limit = (limit_price / close_14 - 1) * 100

    # ── 方案B: 实时涨停检测 (stk_mins + stk_limit 替代 limit_list_d) ──
    is_at_limit = limit_info.get(code, {}).get("is_at_limit", False) if limit_info else False

    # ── V1.2: 封板不可买 — 已封板直接淘汰 ──
    # 14:00/14:30 已封板的股票当日无法买入, 排除
    # 核心逻辑: 选"将成龙"(还没封但即将封), 不选"已成龙"(已经封死的)
    # 一字板也淘汰 (开盘即封死, 全天买不到)
    if is_at_limit and not allow_at_limit:
        return None

    # ── 方案B: G1 — 涨幅不足无接力价值 ──
    # 14:30涨幅<7%已在上方过滤, 此处仅作记录

    # ── F1: 涨幅评分 (≥7%, 上限25%) ──
    if board_type == 'main':
        # 主板10%涨停, 8.5%+接近涨停
        if gain_pct >= 9.0: gain_score = 18
        elif gain_pct >= 8.5: gain_score = 16
        elif gain_pct >= 8.0: gain_score = 14
        elif gain_pct >= 7.0: gain_score = 12
        else: gain_score = 10
    else:
        # 科创/创业板20%涨停, 梯度拉宽
        if gain_pct >= 18.0: gain_score = 18
        elif gain_pct >= 14.0: gain_score = 16
        elif gain_pct >= 11.0: gain_score = 14
        elif gain_pct >= 8.5: gain_score = 12
        else: gain_score = 10

    # 形态加分
    day_range = snap["high"] - snap["low"]
    if day_range > 0 and (close_14 - snap["low"]) / day_range > 0.9:
        gain_score += 2
    gain_score = min(18, gain_score)

    # ── F2: 封板潜力 (V1.2: 已封板被淘汰, 此处评分的是"距涨停有多近") ──
    # dist_to_limit 越小 = 越接近封板 = 尾盘封板概率越高
    if dist_to_limit <= 2.0:
        seal_score = 8    # 即将封板, 尾盘30分钟大概率封死
        seal_weakness = "即将封板"
    elif dist_to_limit <= 4.0:
        seal_score = 6    # 近涨停, 有封板潜力
        seal_weakness = "接近涨停"
    elif dist_to_limit <= 7.0:
        seal_score = 4    # 有一定距离但可冲刺
        seal_weakness = "拉升中"
    else:
        seal_score = 2    # 距涨停较远, 尾盘封板概率低
        seal_weakness = "距涨停较远"

    # ── 方案B: 一字板不可买过滤 ──
    if is_at_limit and snap["open"] >= snap["high"] * 0.999 and snap["low"] >= snap["high"] * 0.999:
        # 一字板 → 降分但不淘汰 (尾盘可能开板)
        seal_score = 1

    # ── F3: 均线趋势 (同原版, 使用历史日K) ──
    if kline_cache and code in kline_cache:
        cached = kline_cache[code]
        hist_closes = cached[0]
        hist_highs = cached[1]
        hist_lows = cached[2]
    else:
        hist_klines = get_kline_history(db, code, trade_date, lookback=60)
        hist_closes = np.array([float(r["close"]) for r in hist_klines])
        hist_highs = np.array([float(r["high"]) for r in hist_klines])
        hist_lows = np.array([float(r["low"]) for r in hist_klines])

    if len(hist_closes) < 20:
        return None

    ma5 = compute_ma(hist_closes, 5)
    ma10 = compute_ma(hist_closes, 10)
    ma20 = compute_ma(hist_closes, 20)

    if ma5 is None or ma10 is None:
        return None

    if ma20 and ma5 > ma10 > ma20 and close_14 > ma20:
        ma_score = 10
    elif ma5 > ma10 and close_14 > ma20:
        ma_score = 8
    elif ma5 > ma10:
        ma_score = 6
    elif close_14 > ma20:
        ma_score = 3
    else:
        ma_score = 1

    # MA多头收紧
    if ma20 and ma20 > 0 and not (ma5 > ma10 > ma20):
        if ma5 > ma10:
            ma_score = min(ma_score, 3)
        else:
            ma_score = min(ma_score, 1)

    # 月跌幅 > 30% 淘汰
    if len(hist_closes) >= 20:
        month_ret = (hist_closes[-1] / hist_closes[-20] - 1) * 100
        if month_ret < -30:
            return None

    # ── F4: 成交额 (方案B: 14:30累计/0.78预估全天) ──
    cum_data = get_intraday_cumulative(db, code, trade_date, time_slot)
    cum_amount = max(cum_data["total_amount"], amount_14)
    # stk_mins amount 单位是元, /1e8 转为亿 (daily_kline 是千元用 /1e5)
    amount_yi = estimate_full_day_amount(cum_amount, time_slot) / 1e8

    # 14:30放宽: 预估全天≥0.5亿即可 (原版≥3亿针对收盘, stk_mins amount单位元)
    if amount_yi < 0.5:
        return None

    # 成交额分档 (stk_mins amount 元→亿, 阈值相应下调)
    if amount_yi >= 5.0:
        turnover_score = 10
    elif amount_yi >= 3.0:
        turnover_score = 8
    elif amount_yi >= 1.5:
        turnover_score = 7
    elif amount_yi >= 1.0:
        turnover_score = 6
    elif amount_yi >= 0.5:
        turnover_score = 4
    else:
        return None

    # ── F5: 量比 ──
    hist_vols = np.array([float(r["volume"]) for r in get_kline_history(db, code, trade_date, lookback=10)])
    vol_ma5 = np.mean(hist_vols[-6:-1]) if len(hist_vols) >= 6 else np.mean(hist_vols[:-1])
    vol_ratio = float(cum_data["total_volume"]) / vol_ma5 if vol_ma5 > 0 else 1.0

    if vol_ratio >= 3.0:
        volume_score = 10
    elif vol_ratio >= 2.5:
        volume_score = 8
    elif vol_ratio >= 2.0:
        volume_score = 7
    elif vol_ratio >= 1.5:
        volume_score = 5
    else:
        volume_score = 3

    # ── F6: 主力资金 (同原版 — T+1可用时) ──
    mf = get_moneyflow(db, code, trade_date)
    if mf and mf.get("net_mf_amount") is not None:
        net_inflow = float(mf["net_mf_amount"])
        lg_buy = float(mf.get("buy_lg_amount") or 0)
        lg_sell = float(mf.get("sell_lg_amount") or 0)
        elg_buy = float(mf.get("buy_elg_amount") or 0)
        elg_sell = float(mf.get("sell_elg_amount") or 0)
        total_inflow = lg_buy + elg_buy - lg_sell - elg_sell
        inflow_ratio = total_inflow / (cum_amount + 1) * 100
    else:
        net_inflow = 0
        inflow_ratio = 0

    if mf is not None and net_inflow < 0 and inflow_ratio < 0:
        return None  # 主力明确出货

    if mf is None:
        capital_score = 10
    elif inflow_ratio > 10:
        capital_score = 20
    elif inflow_ratio > 5:
        capital_score = 17
    elif inflow_ratio > 2:
        capital_score = 14
    elif inflow_ratio >= 0:
        capital_score = 10
    else:
        return None

    # ── F7: 板块共振 ──
    sector_change = sector_stats.get(industry, {}).get("pct_change", 0) if sector_stats else 0
    peer_count = sector_stats.get(industry, {}).get("peer_count", 0) if sector_stats else 0
    sh_pct = get_shanghai_index(db, trade_date)

    # F14: 板块支撑验证
    if peer_count <= 1 and sector_change <= 0:
        return None  # 孤立行情

    # 14:30版: 共振评分 + sh_pct==0兜底
    if sh_pct == 0:
        sh_pct = 0.01  # 中性, 避免除零和 else 淘汰
    if sector_change == 0:
        sector_change = 0.01  # 中性

    if sector_change > 0 and sh_pct < 0:
        resonance_score = 15
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 3:
        resonance_score = 15
    elif sector_change > 0 and sh_pct > 0 and (sector_change - sh_pct) > 1:
        resonance_score = 12
    elif sector_change > 0 and sh_pct > 0:
        resonance_score = 10
    elif sector_change < 0 and sh_pct < 0 and sector_change > sh_pct:
        resonance_score = 8
    elif sector_change < 0 and sh_pct > 0:
        resonance_score = 3
    else:
        resonance_score = 5  # 14:30兜底: 不给高分但也不淘汰

    # ── F8: 板块动量 ──
    if sector_change > 3:
        sector_momentum_score = 10
    elif sector_change > 1:
        sector_momentum_score = 7
    elif sector_change > 0:
        sector_momentum_score = 5
    elif sector_change > -1:
        sector_momentum_score = 3
    else:
        sector_momentum_score = 0

    # ── F9: 板块龙头 ──
    if peer_count >= 5: sl_score = 12
    elif peer_count >= 3: sl_score = 9
    elif peer_count >= 2: sl_score = 6
    elif peer_count == 1: sl_score = 3
    else: sl_score = 0

    # ── F10: 分歧不死 (方案B: 14:30 日内版) ──
    resilience_score = score_resilience_intraday(snap)

    # ── 综合评分 ──
    ma_adjusted = min(6, ma_score)
    sector_momentum_adjusted = min(15, sector_momentum_score * 1.5)
    capital_adjusted = min(22, capital_score)
    resilience_adjusted = resilience_score * 2  # 0-4 → 0-8

    total = (gain_score + sl_score + ma_adjusted + turnover_score +
             resonance_score + capital_adjusted + sector_momentum_adjusted +
             seal_score + resilience_adjusted)

    grade = _afternoon_grade(total)

    # ── 信号 ──
    atr_val = calc_atr(hist_highs, hist_lows, hist_closes, 14)
    atr_pct = (atr_val / close_14 * 100) if close_14 > 0 and atr_val > 0 else 0

    result = {
        "code": code, "name": name, "industry": industry,
        "gain_pct": round(gain_pct, 2), "close_14": close_14, "pre_close": pre_close,
        "amount_yi_est": round(amount_yi, 1),
        "total_score": total, "grade": grade,
        "is_at_limit": is_at_limit,
        "gain_score": gain_score, "seal_score": seal_score,
        "ma_score": ma_score, "turnover_score": turnover_score,
        "volume_score": volume_score, "capital_score": capital_score,
        "resonance_score": resonance_score, "sector_momentum_score": sector_momentum_score,
        "sector_leader_score": sl_score, "resilience_score": resilience_score,
        "sector_change": round(sector_change, 2),
        "peer_count": peer_count, "dist_to_limit": round(dist_to_limit, 2),
        "seal_weakness": seal_weakness,
        "atr_pct": round(atr_pct, 2),
    }
    result["sector_resonance"] = {
        "sector": industry,
        "sector_change": result["sector_change"],
        "peer_count": peer_count,
        "resonance_score": resonance_score,
        "sector_momentum_score": sector_momentum_score,
        "sector_leader_score": sl_score,
    }
    return apply_afternoon_optimization(result)


# ═══════════════════════ 筛选主流程 ═══════════════════════

def run_afternoon_screening(
    trade_date,
    time_slot="14:30",
    top_n=20,
    env_check=True,
    allow_at_limit=False,
    tradeable_only=True,
    full_output=False,
):
    """14:30 午后选股主流程."""
    with _get_db(readonly=True) as db:
        # ── 市场环境 ──
        market_env = MarketEnv.BULL
        env_detail = {}
        if env_check:
            market_env, env_detail = assess_market_env(db, trade_date)
            env_label = {"bull": "🟢做多", "neutral": "🟡中性", "bear": "🟠观望", "crash": "🔴熔断"}
            print(f"  市场环境: {env_label.get(market_env.value, '?')} — {env_detail.get('reason', '')}")

        if market_env == MarketEnv.CRASH:
            print(f"  ⛔ 市场熔断, 跳过选股")
            return [], []

        # ── 14:30 快照 (V1.1: 自动实时/历史切换) ──
        t0 = time.time()
        snapshot, snap_mode = get_unified_snapshot(db, trade_date, time_slot)
        mode_icon = "📡" if snap_mode == "live" else "📜"
        print(f"  {mode_icon} 快照({snap_mode}): {len(snapshot)} 只 ({time.time()-t0:.1f}s)")

        # ── pre_close: 多源回退 (stk_auction_o → daily_kline) ──
        # daily_kline 是 T+1 盘后才有，当天需从 stk_auction_o.close (即 pre_close) 获取
        pre_closes = {}
        snapshot_codes = list(snapshot.keys())
        batch_size = 1000
        for i in range(0, len(snapshot_codes), batch_size):
            batch = snapshot_codes[i:i+batch_size]
            placeholders = ",".join(["?"] * len(batch))
            # Path 1: stk_auction_o.close = 昨收价 (当日 9:25 即可用)
            try:
                a_rows = db.execute(
                    f"SELECT code, close FROM stk_auction_o WHERE trade_date=? AND code IN ({placeholders}) AND close > 0",
                    [trade_date] + batch
                ).fetchall()
                for r in a_rows:
                    code = r["code"] or r.get("ts_code", "")
                    if code and code not in pre_closes and float(r["close"] or 0) > 0:
                        pre_closes[code] = float(r["close"])
            except Exception:
                pass
        print(f"  📊 pre_close from stk_auction_o({trade_date}): {len(pre_closes)} 只")
        # Path 2: daily_kline last close (T+1 fallback for any missing codes)
        prev_row = db.execute(
            "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (trade_date,)
        ).fetchone()
        if prev_row:
            prev_d = prev_row["pd"] if isinstance(prev_row, dict) else prev_row[0]
            prev_d_str = prev_d.strftime("%Y-%m-%d") if hasattr(prev_d, 'strftime') else str(prev_d)[:10]
            for i in range(0, len(snapshot_codes), batch_size):
                batch = snapshot_codes[i:i+batch_size]
                placeholders = ",".join(["?"] * len(batch))
                missing = [c for c in batch if c not in pre_closes]
                if not missing:
                    continue
                m_placeholders = ",".join(["?"] * len(missing))
                prev_rows = db.execute(
                    f"SELECT code, close FROM daily_kline WHERE trade_date=? AND code IN ({m_placeholders})",
                    [prev_d_str] + missing
                ).fetchall()
                for r in prev_rows:
                    code = r["code"] or r.get("ts_code", "")
                    if code and code not in pre_closes:
                        pre_closes[code] = float(r["close"] or 0)
            print(f"  📊 pre_close from daily_kline({prev_d_str}): {len(pre_closes)} 只 (含回退)")

        # ── 方案B: 实时涨停检测 (替代 limit_list_d) ──
        limit_info = detect_intraday_limits(db, trade_date, snapshot, pre_closes)
        at_limit_count = sum(1 for v in limit_info.values() if v["is_at_limit"])
        print(f"  🔒 14:30涨停检测: {at_limit_count} 只 (stk_mins+stk_limit)")

        # ── 股票池 ──
        stocks = db.execute(
            "SELECT code, name, industry FROM stocks WHERE is_st=0 "
            "AND name NOT LIKE '%ST%' AND (float_mv IS NULL OR float_mv >= 20)"
        ).fetchall()
        print(f"  📈 股票池: {len(stocks)} 只")

        # ── 板块统计 (基于14:30快照, 计算真实pct_change) ──
        sector_stats = {}
        industry_gains = defaultdict(list)
        for code, snap in snapshot.items():
            if code in pre_closes and pre_closes[code] > 0:
                gain = (snap["close"] / pre_closes[code] - 1) * 100
                row = db.execute("SELECT industry FROM stocks WHERE code=?", (code,)).fetchone()
                ind = row["industry"] if row else "其他"
                industry_gains[ind].append(gain)

        for ind, gains in industry_gains.items():
            strong = [g for g in gains if g >= 5]
            avg_gain = np.mean(gains) if gains else 0
            sector_stats[ind] = {
                "peer_count": len(strong),        # ≥5%的强势股数量
                "max_gain": round(max(strong), 2) if strong else 0,
                "pct_change": round(avg_gain, 2),  # 板块平均涨幅 (真实值!)
            }

        # ── 逐股评分 ──
        scores = []
        for r in stocks:
            c = r["code"]
            if c not in snapshot or c not in pre_closes:
                continue
            try:
                res = score_stock_afternoon(
                    c, r["name"], r["industry"] or "其他",
                    snapshot[c], pre_closes[c], db, trade_date,
                    time_slot=time_slot, limit_info=limit_info,
                    sector_stats=sector_stats, is_historical=(snap_mode != "live"),
                    allow_at_limit=allow_at_limit,
                )
                if res:
                    scores.append(res)
            except Exception:
                continue  # (scoring error, stock skipped)

        print(f"  ✅ 筛选后: {len(scores)} 只 ({time.time()-t0:.1f}s)")

        # ── 排序 + Top-N ──
        scores.sort(key=lambda x: -x["total_score"])

        top = select_afternoon_top(scores, market_env, top_n=top_n, full_output=full_output)

        # 市场环境标记
        for s in top:
            s["market_env"] = market_env.value
            if market_env == MarketEnv.NEUTRAL:
                s["_env_halved"] = True
            elif market_env == MarketEnv.BEAR:
                s["_no_trade"] = True

        if tradeable_only:
            top = filter_tradeable_afternoon_picks(top, top_n=top_n)
        return top, scores


def print_results(top, trade_date, time_slot="14:30"):
    """打印选股结果."""
    env_label = {"bull": "🟢做多", "neutral": "🟡中性", "bear": "🟠观望", "crash": "🔴熔断"}
    market_env = top[0].get("market_env", "bull") if top else "bull"

    print(f"\n{'=' * 105}")
    print(f"  秋神龙头战法-午后选股 V1.0 — {trade_date} {time_slot} Top {len(top)} | 市场: {env_label.get(market_env, '?')}")
    print(f"{'=' * 105}")
    print(f"\n  因子: 涨幅({WEIGHTS['gain_quality']})+龙头({WEIGHTS['sector_leader']})+均线({WEIGHTS['ma_trend']})")
    print(f"        +成交({WEIGHTS['turnover']})+共振({WEIGHTS['sector_resonance']})+资金({WEIGHTS['capital_flow']})")
    print(f"        +板块动量({WEIGHTS['sector_momentum']})+封板({WEIGHTS['seal_quality']})+分歧({WEIGHTS['resilience']})")
    print(f"  方案B: stk_mins数据 | 14:30涨停检测 | 分歧不死日内版 | 成交额预估")
    print(f"{'#':<3} {'代码':<8} {'名称':<8} {'总分':<5} {'级':<3} {'涨':<7} {'成交':<7} {'封板':<6} {'分歧':<5} {'龙头':<5} {'板块'}")
    print(f"{'-'*95}")
    for i, s in enumerate(top, 1):
        seal_str = "✅涨停" if s.get("is_at_limit") else f"距{s.get('dist_to_limit',0):.0f}%"
        print(f"{i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<5.0f} {s['grade']:<3} "
              f"{s['gain_pct']:>+5.1f}% {s['amount_yi_est']:<5.0f}亿 {seal_str:<6} "
              f"{s['resilience_score']:<5} {s['sector_leader_score']:<5} {s['industry']}")

    s_cnt = sum(1 for s in top if s['grade'] == 'S')
    a_cnt = sum(1 for s in top if s['grade'] == 'A')
    b_cnt = sum(1 for s in top if s['grade'] == 'B')
    lim_cnt = sum(1 for s in top if s.get("is_at_limit"))
    print(f"\n  S={s_cnt} A={a_cnt} B={b_cnt} | 已涨停={lim_cnt} | 市场={env_label.get(market_env, '?')}")


# ═══════════════════════ Engine wrapper ═══════════════════════

class AfternoonLeaderEngine:
    """秋神午后选股引擎."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, time_slot: str = "14:30", **kwargs):
        if trade_date is None:
            with _get_db(readonly=True) as db:
                trade_date = resolve_afternoon_trade_date(db)
        top, all_scores = run_afternoon_screening(trade_date, time_slot=time_slot, top_n=top_n)
        return top


class AfternoonTrendFullEngine:
    """秋神趋势启动午后全量版选股引擎."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 30, trade_date: str = None, time_slot: str = "14:30", **kwargs):
        if trade_date is None:
            with _get_db(readonly=True) as db:
                trade_date = resolve_afternoon_trade_date(db)
        top, _ = run_afternoon_screening(
            trade_date,
            time_slot=time_slot,
            top_n=top_n,
            allow_at_limit=True,
            tradeable_only=False,
            full_output=True,
        )
        return top


# ═══════════════════════ CLI ═══════════════════════

def main():
    import argparse, json, os, sys
    from kronos_factors.scorer._db_stub import set_db_adapter
    from kronos_factors.pg_adapter import create_pg_adapter

    parser = argparse.ArgumentParser(description="秋神龙头战法-午后选股 V1.0")
    parser.add_argument("--date", default=None, help="Trade date YYYY-MM-DD (default: latest)")
    parser.add_argument("--time", default="14:30", help="Time slot (default: 14:30)")
    parser.add_argument("--top-n", type=int, default=20, help="Top N picks")
    parser.add_argument("--export", default=None, help="Export JSON file path")
    parser.add_argument("--db-write", action="store_true", help="Write picks to screening_snapshots PG table")
    args = parser.parse_args()

    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    adapter = create_pg_adapter(pg_url)
    if adapter:
        set_db_adapter(adapter)
        print(f"  📡 PG: {pg_url.split('@')[-1] if '@' in pg_url else pg_url}")
    else:
        print("  ⚠️ PG 连接失败, 使用 SQLite fallback")

    trade_date = args.date
    if trade_date is None:
        with _get_db(readonly=True) as db:
            trade_date = resolve_afternoon_trade_date(db)
        if not trade_date:
            print("No trade date found"); return

    top, all_scores = run_afternoon_screening(trade_date, time_slot=args.time, top_n=args.top_n)
    print_results(top, trade_date, args.time)

    if top and args.export:
        export_path = args.export
        os.makedirs(os.path.dirname(export_path) or "outputs", exist_ok=True)
        with open(export_path, 'w') as f:
            json.dump({
                "date": trade_date, "time_slot": args.time,
                "top_n": len(top), "picks": top,
            }, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  📁 Exported: {export_path}")

    if top and args.db_write:
        try:
            from kronos_factors.recorder import record_picks
            n = record_picks("leader_afternoon", trade_date, args.time, top)
            print(f"  🗄️ DB write: {n} picks → screening_snapshots")
        except Exception as e:
            print(f"  ⚠️ DB write failed: {e}")


if __name__ == "__main__":
    main()
