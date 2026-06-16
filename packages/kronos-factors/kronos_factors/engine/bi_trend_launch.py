#!/usr/bin/env python3
"""毕师傅趋势启动战法 — Bi's Trend Launch Strategy.

买入: OBV均线确认趋势 + WR急跌回踩 + 反弹启动 = 趋势启动买入信号.
卖出: OBV跌破均线(资金流出) + WR回升超买(涨势耗尽) = 趋势终结卖出信号.

核心理念:
  1. OBV > OBV_MA10 持续N天 → 资金持续流入, 趋势方向确认
  2. WR 3日内急跌 → 价格快速回踩, 洗盘而非反转
  3. 回踩缩量 → 主力未出货, 洗盘特征
  4. 三者叠加 = "上升趋势中的洗盘回踩" → 高胜率买点

与现有模型互补:
  - leader_scalp/closing: 龙头战法(板块龙头+涨幅筛选)
  - bi_trend_launch: 趋势战法(OBV+WR技术信号, 不依赖板块)
  - MoneyFlowModel: 资金流向评分(可组合使用)

Usage:
    python tools/backtest_bi_trend.py --month 2026-06 --top-n 20
"""

import numpy as np
from collections import defaultdict
from datetime import datetime
import time


# ── V4.0: 结构级重构 ──
WEIGHTS = {
    "obv_trend": 35,
    "wr_pullback": 28,
    "volume_contract": 12,
    "ma_trend": 10,
    "trend_strength": 8,
    "sector_momentum": 7,
}

GRADE_THRESHOLDS = {"S": 88, "A": 75, "B": 62}
MIN_OBV_DAYS = 2              # OBV≥2天高于MA即可 (放宽, 捕捉早期趋势)
MIN_TREND_20D = 5.0          # V4.4: 近20日涨幅≥5%, 过滤横盘震荡股
STRONG_WR_DROP = -25
STRONG_OBV_DAYS = 10

# V5.0: 近三月回测优化
MARKET_BREADTH_CRASH = 18       # 单日涨跌比<18% → 系统性崩盘
POST_CRASH_SKIP_BREADTH = 20    # 前日涨跌比<20% → 次日空仓
SH_INDEX_MA_DAYS = 20           # 上证20日均线判断中期趋势
WEAK_BREADTH_5D = 35            # 5日涨跌比均线<35% → 半仓
BEAR_BREADTH_5D = 30            # V5.0: 25→30 (上证<20MA AND 5日<30% → 空仓)
MIN_HOLD_DAYS = 5               # V5.0: 最低持有5天(非止损), 消除1-2天止损

# V5.0: 卖出优化
SELL_STOP_LOSS = -10            # 硬止损 -10%
SELL_TRAILING_STOP = -5         # 移动止盈: 从最高点回落-5%
SELL_TRAILING_STOP_TIGHT = -3   # V5.0: 盈利>20%时收紧到-3%
TRAILING_PROFIT_THRESHOLD = 20  # V5.0: 盈利>此值触发收紧止盈

# V5.0: 弱市精选
WEAK_MARKET_S_ONLY = True       # V5.0: 弱市(上证weak+5日<35%)仅选strong_buy+S级


def calc_obv(closes, volumes):
    """计算OBV序列."""
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]
    return obv


def calc_wr(highs, lows, closes, period=14):
    """计算Williams %R序列. 范围 -100~0."""
    wr = np.full(len(closes), np.nan)
    for i in range(period-1, len(closes)):
        hh = np.max(highs[i-period+1:i+1])
        ll = np.min(lows[i-period+1:i+1])
        if hh - ll > 0:
            wr[i] = (hh - closes[i]) / (hh - ll) * -100
        else:
            wr[i] = -50
    return wr


def calc_adx(highs, lows, closes, period=14):
    """简化的ADX计算."""
    n = len(closes)
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)

    for i in range(1, n):
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0
        minus_dm[i] = down if down > up and down > 0 else 0

    atr = np.zeros(n)
    sm_pdm = np.zeros(n)
    sm_mdm = np.zeros(n)
    atr[period] = tr[1:period+1].mean()
    sm_pdm[period] = plus_dm[1:period+1].sum()
    sm_mdm[period] = minus_dm[1:period+1].sum()

    for i in range(period+1, n):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
        sm_pdm[i] = (sm_pdm[i-1]*(period-1) + plus_dm[i]) / period
        sm_mdm[i] = (sm_mdm[i-1]*(period-1) + minus_dm[i]) / period

    di_plus = np.zeros(n)
    di_minus = np.zeros(n)
    adx = np.zeros(n)
    for i in range(period, n):
        if atr[i] > 0:
            di_plus[i] = 100 * sm_pdm[i] / atr[i]
            di_minus[i] = 100 * sm_mdm[i] / atr[i]
        dx = 100 * abs(di_plus[i]-di_minus[i]) / (di_plus[i]+di_minus[i]+1e-10)
        adx[i] = dx if i == period else (adx[i-1]*(period-1) + dx) / period

    return float(adx[-1]), float(di_plus[-1]), float(di_minus[-1])


def score_bi_trend(df, code=None, name=None, industry=None, sector_change=0):
    """毕师傅趋势启动战法 — 单只股票评分.

    Args:
        df: DataFrame with [open, high, low, close, volume]
        code, name, industry: 股票信息
        sector_change: 板块涨跌(外部传入)

    Returns:
        dict with score breakdown, or None if eliminated
    """
    closes = df["close"].values.astype(np.float64)
    highs = df["high"].values.astype(np.float64)
    lows = df["low"].values.astype(np.float64)
    volumes = df["volume"].values.astype(np.float64)

    if len(closes) < 40:
        return None

    price = closes[-1]

    # ── 条件0: 基础过滤 ──
    # 涨幅过滤(排除涨停/跌停极端情况)
    if len(closes) >= 2 and closes[-2] > 0:
        daily_gain = (closes[-1] / closes[-2] - 1) * 100
        if daily_gain > 9.5 or daily_gain < -9.5:
            return None  # 涨跌停不参与

    # 近20日跌幅>30% 淘汰, 涨幅<5% 过滤横盘
    if len(closes) >= 20 and closes[-20] > 0:
        ret_20d = (closes[-1] / closes[-20] - 1) * 100
        if ret_20d < -30 or ret_20d < MIN_TREND_20D:
            return None

    # ── F1: OBV趋势 (0-30分) ──
    obv = calc_obv(closes, volumes)
    obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
    obv_ma20 = np.convolve(obv, np.ones(20)/20, mode='valid')

    if len(obv_ma10) < 10:
        return None

    obv_now = obv[-1]
    obv_ma10_now = obv_ma10[-1]
    obv_ma20_now = obv_ma20[-1] if len(obv_ma20) > 0 else 0
    obv_above_ma10 = obv_now > obv_ma10_now
    obv_above_ma20 = obv_now > obv_ma20_now if obv_ma20_now > 0 else False

    # OBV持续高于MA10的天数
    obv_days_above = 0
    for i in range(len(obv)-1, -1, -1):
        ma_idx = i - 10 + 1
        if ma_idx >= 0 and obv[i] > obv_ma10[ma_idx]:
            obv_days_above += 1
        else:
            break

    # OBV斜率(近10日)
    if len(obv) >= 15 and abs(obv[-10]) > 1:
        obv_slope = (obv[-1] - obv[-10]) / abs(obv[-10]) * 100
    else:
        obv_slope = 0

    # V2.0: OBV必须≥MIN_OBV_DAYS天高于MA, 否则淘汰
    if obv_days_above < MIN_OBV_DAYS:
        return None

    if obv_days_above >= 20:
        obv_score = 35
        obv_level = "极强"
    elif obv_days_above >= 15:
        obv_score = 32
        obv_level = "很强"
    elif obv_days_above >= 10:
        obv_score = 28
        obv_level = "强"
    elif obv_days_above >= 7:
        obv_score = 22
        obv_level = "中等"
    else:  # 5-6天
        obv_score = 15
        obv_level = "刚突破"

    # OBV斜率修正
    if obv_slope > 5:
        obv_score = min(30, obv_score + 3)
    elif obv_slope < -5 and obv_level != "极强":
        obv_score = max(3, obv_score - 5)

    # ── F2: WR急跌回踩 (0-25分) ──
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]

    if len(wr_valid) < 5:
        return None

    wr_now = float(wr_valid[-1])
    wr_2d = float(wr_valid[-3]) if len(wr_valid) >= 3 else wr_now
    wr_3d = float(wr_valid[-4]) if len(wr_valid) >= 4 else wr_now
    wr_5d = float(wr_valid[-6]) if len(wr_valid) >= 6 else wr_now

    wr_drop_2d = wr_now - wr_2d   # 2日变化
    wr_drop_3d = wr_now - wr_3d   # 3日变化
    wr_drop_5d = wr_now - wr_5d   # 5日变化

    # WR急跌评分(取最陡的一段)
    wr_max_drop = min(wr_drop_2d, wr_drop_3d, wr_drop_5d)

    if wr_max_drop < -40:
        wr_score = 25; wr_level = "深度洗盘"
    elif wr_max_drop < -30:
        wr_score = 22; wr_level = "明显洗盘"
    elif wr_max_drop < -20:
        wr_score = 18; wr_level = "温和洗盘"
    elif wr_max_drop < -10:
        wr_score = 12; wr_level = "轻微回踩"
    elif wr_max_drop < -5:
        wr_score = 6;  wr_level = "微调"
    else:
        wr_score = 2;  wr_level = "无回踩"

    # WR当前位置修正
    if wr_now < -85:
        wr_score = min(25, wr_score + 3)   # 极度超卖→反弹力强
    elif wr_now < -70:
        wr_score = min(25, wr_score + 1)   # 超卖区
    elif wr_now > -30:
        wr_score = max(2, wr_score - 5)    # 仍在高位→没跌够
        if wr_score <= 5:
            return None  # WR高位无回踩, 不符合战法

    # ── F3: 回踩缩量 (0-15分) ──
    vol_3d = np.mean(volumes[-3:])
    vol_10d = np.mean(volumes[-13:-3]) if len(volumes) >= 13 else vol_3d
    vol_ratio = vol_3d / max(1, vol_10d)

    if vol_ratio < 0.5:
        vol_score = 15; vol_level = "极度缩量"
    elif vol_ratio < 0.65:
        vol_score = 12; vol_level = "明显缩量"
    elif vol_ratio < 0.8:
        vol_score = 9;  vol_level = "温和缩量"
    elif vol_ratio < 1.0:
        vol_score = 5;  vol_level = "正常"
    else:
        vol_score = 2;  vol_level = "放量"

    # ── F4: 均线趋势 (0-12分) ──
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20

    if ma5 > ma10 > ma20 and price > ma60:
        ma_score = 12; ma_level = "多头排列"
    elif ma5 > ma10 > ma20:
        ma_score = 10; ma_level = "短多排列"
    elif ma10 > ma20 and price > ma20:
        ma_score = 7;  ma_level = "偏多"
    elif price > ma60:
        ma_score = 4;  ma_level = "长多支撑"
    elif price > ma20:
        ma_score = 2;  ma_level = "中多支撑"
    else:
        ma_score = 0;  ma_level = "空头"

    # ── F5: ADX趋势强度 (0-10分) ──
    try:
        adx, di_p, di_m = calc_adx(highs, lows, closes)
    except Exception:
        adx, di_p, di_m = 20, 20, 20

    if adx > 40 and di_p > di_m:
        adx_score = 10; adx_level = "强趋势"
    elif adx > 30 and di_p > di_m:
        adx_score = 8;  adx_level = "趋势中"
    elif adx > 25 and di_p > di_m:
        adx_score = 6;  adx_level = "温和趋势"
    elif adx > 20:
        adx_score = 4;  adx_level = "弱趋势"
    else:
        adx_score = 2;  adx_level = "无趋势"

    # ── F6: 板块动量 (0-8分) ──
    if sector_change > 3:
        sm_score = 3    # 板块过热, 谨慎
    elif sector_change > 0:
        sm_score = 6    # 板块温和走强
    elif sector_change > -2:
        sm_score = 8    # 板块微跌, 回踩共振
    elif sector_change > -5:
        sm_score = 5    # 板块偏弱
    else:
        sm_score = 2    # 板块大跌拖累

    # ── 综合评分 ──
    total_raw = obv_score + wr_score + vol_score + ma_score + adx_score + sm_score  # max=100
    total = round(total_raw * 100 / 100, 0)  # 0-100 scale

    # ── V3.0 评级 ──
    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    # V4.0: 移除S级强制缩量

    # ── V3.0 信号: strong_buy条件收紧 ──
    if obv_days_above >= STRONG_OBV_DAYS and wr_max_drop < STRONG_WR_DROP and wr_now < -40:
        signal_type = "strong_buy"
    elif grade in ("S", "A"):
        signal_type = "watch"
    else:
        signal_type = "no_signal"

    return {
        "code": code or "", "name": name or "", "industry": industry or "",
        "total_score": total, "grade": grade, "signal": signal_type,
        # OBV
        "obv_score": obv_score, "obv_days_above": obv_days_above,
        "obv_level": obv_level, "obv_slope_pct": round(obv_slope, 1),
        # WR
        "wr_score": wr_score, "wr_current": round(wr_now, 1),
        "wr_drop_3d": round(wr_drop_3d, 1), "wr_level": wr_level,
        # Volume
        "vol_score": vol_score, "vol_ratio": round(vol_ratio, 2),
        "vol_level": vol_level,
        # MA
        "ma_score": ma_score, "ma_level": ma_level,
        # ADX
        "adx_score": adx_score, "adx": round(adx, 1),
        "di_plus": round(di_p, 1), "adx_level": adx_level,
        # Sector
        "sm_score": sm_score, "sector_change": round(sector_change, 2),
        # Price
        "close": round(float(price), 2),
        "daily_gain": round((closes[-1]/closes[-2]-1)*100, 2) if len(closes) >= 2 and closes[-2] > 0 else 0,
    }


def run_bi_screening(db, trade_date, top_n=20):
    """毕师傅趋势启动战法 V2.0 — 全市场选股.

    V2.0优化:
      - 市场环境熔断: 涨跌比<40%空仓
      - 批量K线预取加速
      - OBV≥5天硬门槛
      - 只保留strong_buy信号

    Args:
        db: 数据库连接
        trade_date: YYYY-MM-DD
        top_n: 返回Top N

    Returns:
        (top_picks, all_scores, market_info)
    """
    import pandas as pd

    # ── V2.0: 市场环境评估 ──
    # V8.0: 兼容盘中实时数据 — daily_kline 无当日数据时 fallback 到 stk_mins
    prev_row = db.execute(
        "SELECT MAX(trade_date) as prev_date FROM daily_kline WHERE trade_date < ?", (trade_date,)
    ).fetchone()
    if not prev_row:
        return [], [], {"breadth": 50, "env": "unknown"}
    prev_date = prev_row["prev_date"]

    # 检查当日 daily_kline 是否有数据
    today_dk = db.execute(
        "SELECT COUNT(*) as cnt FROM daily_kline WHERE trade_date=?", (trade_date,)
    ).fetchone()
    has_today_dk = today_dk and (today_dk["cnt"] or 0) > 100

    if has_today_dk:
        # 标准路径: daily_kline 已收盘, 用日线计算涨跌比
        breadth_row = db.execute(
            "SELECT SUM(CASE WHEN a.close > b.close THEN 1 ELSE 0 END) as up, "
            "SUM(CASE WHEN a.close < b.close THEN 1 ELSE 0 END) as down "
            "FROM daily_kline a "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
            "JOIN stocks s ON a.code=s.code "
            "WHERE a.trade_date=? AND s.is_st=0 AND s.name NOT LIKE '%ST%'",
            (prev_date, trade_date)
        ).fetchone()
        up = breadth_row["up"] or 0
        down = breadth_row["down"] or 0
    else:
        # 盘中 fallback: 用 stk_mins 最新快照 vs daily_kline 前收
        # 使用最新时间槽的收盘价作为当日价格
        br = db.execute(
            "SELECT SUM(CASE WHEN m.close > d.close THEN 1 ELSE 0 END) as up, "
            "SUM(CASE WHEN m.close < d.close THEN 1 ELSE 0 END) as down "
            "FROM stk_mins m "
            "JOIN daily_kline d ON d.code = m.code AND d.trade_date = ? "
            "JOIN stocks s ON m.code = s.code "
            "WHERE m.trade_time = (SELECT MAX(trade_time) FROM stk_mins "
            "                      WHERE trade_time LIKE ? AND freq='5min') "
            "  AND m.freq = '5min' "
            "  AND d.close > 0 AND s.is_st = 0 AND s.name NOT LIKE '%ST%'",
            (prev_date, f"{trade_date}%")
        ).fetchone()
        up = br["up"] or 0 if br else 0
        down = br["down"] or 0 if br else 0
    breadth = up / max(1, up + down) * 100

    # ── V4.0: 5日涨跌比均线 (中期市场环境) ──
    # 计算前5个交易日的涨跌比
    breadth_5d_list = [breadth]
    cursor_date = prev_date
    for _ in range(4):
        prev2 = db.execute(
            "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (cursor_date,)
        ).fetchone()
        if not prev2 or not prev2["pd"]:
            break
        pd2 = prev2["pd"]
        prev3 = db.execute(
            "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (pd2,)
        ).fetchone()
        if not prev3 or not prev3["pd"]:
            break
        br = db.execute(
            "SELECT SUM(CASE WHEN a.close > b.close THEN 1 ELSE 0 END) as up, "
            "SUM(CASE WHEN a.close < b.close THEN 1 ELSE 0 END) as down "
            "FROM daily_kline a "
            "JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
            "WHERE a.trade_date=?",
            (prev3["pd"], pd2)
        ).fetchone()
        if br and (br["up"] or 0) + (br["down"] or 0) > 0:
            breadth_5d_list.append((br["up"] or 0) / max(1, (br["up"] or 0) + (br["down"] or 0)) * 100)
        cursor_date = prev3["pd"]

    breadth_5d = sum(breadth_5d_list) / len(breadth_5d_list) if breadth_5d_list else breadth

    # ── V4.0: 上证20MA中期趋势 ──
    sh_trend = "up"
    try:
        sh_klines = db.execute(
            "SELECT close FROM daily_kline WHERE code='000001' AND trade_date <= ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (trade_date, SH_INDEX_MA_DAYS + 5)
        ).fetchall()
        if sh_klines and len(sh_klines) >= SH_INDEX_MA_DAYS:
            sh_closes = [float(r["close"]) for r in reversed(sh_klines)]
            sh_ma20 = sum(sh_closes[-SH_INDEX_MA_DAYS:]) / SH_INDEX_MA_DAYS
            sh_now = sh_closes[-1]
            # 判断趋势: 连续3天低于MA20 = 下跌趋势
            below_count = sum(1 for c in sh_closes[-3:] if c < sh_ma20)
            if below_count >= 3:
                sh_trend = "down"
            elif sh_now < sh_ma20:
                sh_trend = "weak"
    except Exception:
        pass  # 无法获取上证数据时跳过

    # ── V4.0: 熔断逻辑 ──
    # 1. 系统性崩盘 → 空仓
    if breadth < MARKET_BREADTH_CRASH:
        print(f"  🛑 熔断: 涨跌比{breadth:.0f}%<{MARKET_BREADTH_CRASH}%")
        return [], [], {"breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1), "sh_trend": sh_trend, "env": "crash"}

    # 2. 崩盘次日(前日涨跌比<20%) → 直接空仓
    if breadth_5d_list and len(breadth_5d_list) >= 2:
        prev_breadth = breadth_5d_list[1]  # 昨日涨跌比
        if prev_breadth < POST_CRASH_SKIP_BREADTH:
            print(f"  🛑 崩盘次日: 前日涨跌比{prev_breadth:.0f}%<{POST_CRASH_SKIP_BREADTH}% → 空仓")
            return [], [], {"breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1), "sh_trend": sh_trend, "env": "post_crash"}

    # V5.0: 3. 上证<20MA AND 5日涨跌比<30% → 熊市空仓
    is_bear = sh_trend in ("down", "weak") and breadth_5d < BEAR_BREADTH_5D
    if is_bear:
        print(f"  🛑 熊市: 上证{sh_trend} + 5日涨跌比{breadth_5d:.0f}%<{BEAR_BREADTH_5D}% → 空仓")
        return [], [], {"breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1), "sh_trend": sh_trend, "env": "bear_market"}

    # V5.0: 4. 弱市精选: 上证weak + 5日<35% → 仅选strong_buy
    weak_market = sh_trend in ("down", "weak") and breadth_5d < WEAK_BREADTH_5D
    effective_n = top_n
    if weak_market:
        effective_n = max(5, top_n // 2)
        print(f"  ⚠️ 弱市精选: 上证{sh_trend} + 5日{breadth_5d:.0f}%, 仅选🔥strong_buy, Top-N {top_n}→{effective_n}")
    elif breadth_5d < WEAK_BREADTH_5D:
        effective_n = max(5, top_n // 2)
        print(f"  ⚠️ 半仓: 5日均涨跌比{breadth_5d:.0f}%, Top-N {top_n}→{effective_n}")

    env = "bull" if breadth_5d > 55 else ("neutral" if breadth_5d > BEAR_BREADTH_5D else "bear")
    print(f"  📊 涨跌比: {breadth:.0f}% ({env}) | 前日: {prev_date}")

    # ── 股票池 ──
    stocks = db.execute(
        "SELECT code, name, industry FROM stocks WHERE is_st=0 "
        "AND name NOT LIKE '%ST%' "
        "AND (float_mv IS NULL OR float_mv >= 20)"
    ).fetchall()
    print(f"  📈 股票池: {len(stocks)} 只")

    # ── 批量预取K线 (关键性能优化) ──
    t0 = time.time()
    kline_cache = _prefetch_kline_batch(db, trade_date)
    print(f"  ⚡ K线预取: {len(kline_cache)} 只, {time.time()-t0:.1f}s")

    # ── 板块涨跌 ──
    from kronos_factors.engine.leader_intraday import get_sector_index

    scores = []
    for r in stocks:
        code = r["code"]
        if code not in kline_cache:
            continue
        try:
            closes, highs, lows, volumes = kline_cache[code]
            if len(closes) < 40:
                continue

            # 构造 mini dict (复用预取数据)
            df = type('obj', (object,), {
                'close': type('arr', (object,), {'values': closes})()
            })()
            # 简单方式: 直接传 arrays 给 score_bi_trend
            industry = r["industry"] or "其他"
            sc = get_sector_index(db, industry, trade_date, code)
            sector_change = sc if isinstance(sc, (int, float)) else 0

            result = _score_bi_trend_arrays(
                closes, highs, lows, volumes,
                code=code, name=r["name"], industry=industry,
                sector_change=sector_change
            )
            if result:
                scores.append(result)
        except Exception:
            continue

    print(f"  ✅ 筛选: {len(scores)} 只")

    # ── 排序取Top N ──
    scores.sort(key=lambda x: -x["total_score"])

    # V5.0: 弱市仅选strong_buy, 正常市strong_buy优先
    strong = [s for s in scores if s["signal"] == "strong_buy"]
    s_grade = [s for s in scores if s["signal"] != "strong_buy" and s["grade"] == "S"]
    a_grade = [s for s in scores if s["signal"] != "strong_buy" and s["grade"] == "A"]

    if weak_market:
        candidates = strong  # 仅strong_buy
    else:
        candidates = strong + s_grade + a_grade

    top = []
    sector_counts = defaultdict(int)
    for s in candidates:
        ind = s["industry"]
        if sector_counts[ind] < 2:
            top.append(s)
            sector_counts[ind] += 1
        if len(top) >= effective_n:
            break

    market_info = {
        "breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1),
        "env": env, "prev_date": prev_date, "sh_trend": sh_trend,
        "effective_n": effective_n,
    }
    return top, scores, market_info


def _score_bi_trend_arrays(closes, highs, lows, volumes, code=None, name=None, industry=None, sector_change=0):
    """Same as score_bi_trend but takes numpy arrays directly (no DataFrame)."""
    if len(closes) < 40:
        return None

    price = closes[-1]

    # 基础过滤
    if len(closes) >= 2 and closes[-2] > 0:
        daily_gain = (closes[-1] / closes[-2] - 1) * 100
        if daily_gain > 9.5 or daily_gain < -9.5:
            return None
    if len(closes) >= 20 and closes[-20] > 0:
        ret_20d = (closes[-1] / closes[-20] - 1) * 100
        if ret_20d < -30:
            return None
        # V4.4: 过滤横盘震荡股 (近20日涨幅<5%)
        if ret_20d < MIN_TREND_20D:
            return None

    # OBV
    obv = calc_obv(closes, volumes)
    obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
    if len(obv_ma10) < 10:
        return None

    obv_days_above = 0
    for i in range(len(obv)-1, -1, -1):
        ma_idx = i - 10 + 1
        if ma_idx >= 0 and obv[i] > obv_ma10[ma_idx]:
            obv_days_above += 1
        else:
            break

    if obv_days_above < MIN_OBV_DAYS:
        return None

    obv_slope = 0
    if len(obv) >= 15 and abs(obv[-10]) > 1:
        obv_slope = (obv[-1] - obv[-10]) / abs(obv[-10]) * 100

    if obv_days_above >= 20:
        obv_score, obv_level = 35, "极强"
    elif obv_days_above >= 15:
        obv_score, obv_level = 32, "很强"
    elif obv_days_above >= 10:
        obv_score, obv_level = 28, "强"
    elif obv_days_above >= 7:
        obv_score, obv_level = 22, "中等"
    else:
        obv_score, obv_level = 15, "刚突破"

    if obv_slope > 5:
        obv_score = min(35, obv_score + 3)
    elif obv_slope < -5 and obv_level != "极强":
        obv_score = max(15, obv_score - 5)

    # WR
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]
    if len(wr_valid) < 5:
        return None

    wr_now = float(wr_valid[-1])
    wr_2d = float(wr_valid[-3]) if len(wr_valid) >= 3 else wr_now
    wr_3d = float(wr_valid[-4]) if len(wr_valid) >= 4 else wr_now
    wr_5d = float(wr_valid[-6]) if len(wr_valid) >= 6 else wr_now
    wr_max_drop = min(wr_now - wr_2d, wr_now - wr_3d, wr_now - wr_5d)

    if wr_max_drop < -40:
        wr_score, wr_level = 28, "深度洗盘"
    elif wr_max_drop < -30:
        wr_score, wr_level = 25, "明显洗盘"
    elif wr_max_drop < -20:
        wr_score, wr_level = 20, "温和洗盘"
    elif wr_max_drop < -10:
        wr_score, wr_level = 13, "轻微回踩"
    elif wr_max_drop < -5:
        wr_score, wr_level = 7, "微调"
    else:
        wr_score, wr_level = 2, "无回踩"

    if wr_now < -85:
        wr_score = min(28, wr_score + 3)
    elif wr_now < -70:
        wr_score = min(28, wr_score + 1)
    elif wr_now > -30:
        wr_score = max(2, wr_score - 5)
        if wr_score <= 5:
            return None

    # Volume
    vol_3d = np.mean(volumes[-3:])
    vol_10d = np.mean(volumes[-13:-3]) if len(volumes) >= 13 else vol_3d
    vol_ratio = vol_3d / max(1, vol_10d)
    if vol_ratio < 0.5:
        vol_score, vol_level = 12, "极度缩量"
    elif vol_ratio < 0.65:
        vol_score, vol_level = 10, "明显缩量"
    elif vol_ratio < 0.8:
        vol_score, vol_level = 7, "温和缩量"
    elif vol_ratio < 1.0:
        vol_score, vol_level = 4, "正常"
    else:
        vol_score, vol_level = 1, "放量"

    # MA
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma60 = np.mean(closes[-60:]) if len(closes) >= 60 else ma20
    if ma5 > ma10 > ma20 and price > ma60:
        ma_score, ma_level = 10, "多头排列"
    elif ma5 > ma10 > ma20:
        ma_score, ma_level = 8, "短多排列"
    elif ma10 > ma20 and price > ma20:
        ma_score, ma_level = 6, "偏多"
    elif price > ma60:
        ma_score, ma_level = 3, "长多支撑"
    elif price > ma20:
        ma_score, ma_level = 1, "中多支撑"
    else:
        ma_score, ma_level = 0, "空头"

    # ADX
    try:
        adx, di_p, di_m = calc_adx(highs, lows, closes)
    except Exception:
        adx, di_p, di_m = 20, 20, 20
    if adx > 40 and di_p > di_m:
        adx_score, adx_level = 8, "强趋势"
    elif adx > 30 and di_p > di_m:
        adx_score, adx_level = 6, "趋势中"
    elif adx > 25 and di_p > di_m:
        adx_score, adx_level = 4, "温和趋势"
    elif adx > 20:
        adx_score, adx_level = 2, "弱趋势"
    else:
        adx_score, adx_level = 1, "无趋势"

    # Sector
    if sector_change > 3:
        sm_score = 2
    elif sector_change > 0:
        sm_score = 5
    elif sector_change > -2:
        sm_score = 7
    elif sector_change > -5:
        sm_score = 4
    else:
        sm_score = 1

    total_raw = obv_score + wr_score + vol_score + ma_score + adx_score + sm_score
    total = round(total_raw, 0)

    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    # V4.1: 三层确认信号体系
    # L1: OBV趋势确认 (钱在进)
    obv_confirmed = obv_days_above >= STRONG_OBV_DAYS
    # L2: WR急跌确认 (价在跌)
    wr_drop_confirmed = wr_max_drop < STRONG_WR_DROP
    # L3: 反弹启动确认 (跌完了开始涨)
    #   - WR最近2天不再创新低 (止跌)
    #   - 今日收阳 (price_rising)
    #   - 量能回升不再缩 (vol_surging)
    wr_2d_drop = wr_now - wr_2d
    wr_stopping = abs(wr_2d_drop) < 5
    price_rising = closes[-1] > closes[-2] if len(closes) >= 2 else False
    vol_surging = vol_ratio > 0.8
    rebound_confirmed = wr_stopping and price_rising and vol_surging

    # 信号分级
    if obv_confirmed and wr_drop_confirmed and wr_now < -40:
        if rebound_confirmed:
            signal_type = "strong_buy"     # 🔥 三层确认: 趋势+回踩+反弹启动
            total_raw += 5                 # 加分
        else:
            signal_type = "buy"            # 🟢 两层确认: 趋势+回踩, 等反弹确认
    elif obv_confirmed and wr_drop_confirmed:
        signal_type = "buy"
    elif grade in ("S", "A"):
        signal_type = "watch"
    else:
        signal_type = "no_signal"

    # 标记反弹状态(用于显示)
    _rebound = rebound_confirmed

    # V4.0: 移除S级强制缩量 (弱市中是反向指标)
    # 改为: 缩量加分已在 vol_score 中体现, 不单独降级

    return {
        "code": code or "", "name": name or "", "industry": industry or "",
        "total_score": total, "grade": grade, "signal": signal_type,
        "obv_score": obv_score, "obv_days_above": obv_days_above,
        "obv_level": obv_level, "obv_slope_pct": round(obv_slope, 1),
        "wr_score": wr_score, "wr_current": round(wr_now, 1),
        "wr_drop_3d": round(wr_max_drop, 1), "wr_level": wr_level,
        "vol_score": vol_score, "vol_ratio": round(vol_ratio, 2), "vol_level": vol_level,
        "ma_score": ma_score, "ma_level": ma_level,
        "adx_score": adx_score, "adx": round(adx, 1), "di_plus": round(di_p, 1), "adx_level": adx_level,
        "sm_score": sm_score, "sector_change": round(sector_change, 2),
        "close": round(float(price), 2),
        "daily_gain": round((closes[-1]/closes[-2]-1)*100, 2) if len(closes) >= 2 and closes[-2] > 0 else 0,
        "_rebound": _rebound,
    }


# ═══════════════════════════════════════════════════════════════
# 卖出信号: OBV + WR 趋势逆转检测
# ═══════════════════════════════════════════════════════════════

# 卖出阈值
# 卖出阈值 (V4.3 final: 固定止损 + 仓位分级)
SELL_STOP_LOSS = -10           # 硬止损 -10%
SELL_TRAILING_STOP = -5        # 移动止盈: 从最高点回落-5%即卖
MIN_HOLD_DAYS = 5              # 最低持有5天(非止损情况下)

# V4.3: 仓位分级
POSITION = {
    "strong_buy_S": 0.20,  # 🔥强买+S级 → 20%
    "strong_buy_A": 0.15,  # 🔥强买+A级 → 15%
    "buy_S": 0.12,         # 🟢买入+S级 → 12%
    "buy_A": 0.08,         # 🟢买入+A级 → 8%
    "watch": 0.05,         # 🟡观察 → 5%
}


def calc_atr(highs, lows, closes, period=14):
    """计算 ATR (Average True Range)."""
    n = len(closes)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    atr = np.zeros(n)
    atr[period] = np.mean(tr[1:period+1])
    for i in range(period+1, n):
        atr[i] = (atr[i-1]*(period-1) + tr[i]) / period
    return float(atr[-1]) if atr[-1] > 0 else 0


def check_sell_signal(closes, highs, lows, volumes, entry_price=None, highest_since_entry=None, hold_days=0):
    """V4.3 final 检测是否应该卖出.

    四层卖出逻辑:
      L1: 硬止损: 现价 < 入场价 * (1-10%)
      L2: 移动止盈: 从最高点回落 >= 5%
      L3: OBV跌破MA10连续≥3天 → 资金流出
      L4: WR从深跌(-60以下)回升至-30以上 → 涨势耗尽

    持有<MIN_HOLD_DAYS天时不触发L3/L4(给趋势时间发展).

    Returns:
      {"signal": "strong_sell"/"sell"/"stop_loss"/"trailing_stop"/"hold",
       "reason": str, "current_return_pct": float}
    """
    if len(closes) < 14:
        return {"signal": "hold", "reason": "数据不足", "current_return_pct": 0}

    price = closes[-1]
    current_return = (price / entry_price - 1) * 100 if entry_price and entry_price > 0 else 0

    # ── L1: 硬止损 (任何时间触发) ──
    if entry_price and current_return <= SELL_STOP_LOSS:
        return {"signal": "stop_loss", "reason": f"止损{current_return:+.1f}%",
                "current_return_pct": round(current_return, 2)}

    # ── L2: 移动止盈 (从最高点回落) ──
    if highest_since_entry and highest_since_entry > entry_price:
        drawdown_from_high = (price / highest_since_entry - 1) * 100
        profit_from_entry = (highest_since_entry / entry_price - 1) * 100
        # V5.0: 盈利>20%时收紧止盈到-3%
        stop_pct = SELL_TRAILING_STOP_TIGHT if profit_from_entry >= TRAILING_PROFIT_THRESHOLD else SELL_TRAILING_STOP
        if drawdown_from_high <= stop_pct:
            return {"signal": "trailing_stop",
                    "reason": f"从最高{profit_from_entry:+.0f}%回落{drawdown_from_high:+.1f}%",
                    "current_return_pct": round(current_return, 2)}

    # ── 最低持有期: 非止损情况下持有<MIN_HOLD_DAYS天, 不检查 ──
    if hold_days < MIN_HOLD_DAYS:
        return {"signal": "hold", "reason": f"持有{hold_days}天(最低{MIN_HOLD_DAYS}天)",
                "current_return_pct": round(current_return, 2)}

    # ── L3: OBV 趋势逆转 ──
    obv = calc_obv(closes, volumes)
    obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
    if len(obv_ma10) < 3:
        return {"signal": "hold", "reason": "数据不足", "current_return_pct": round(current_return, 2)}

    obv_below_days = 0
    for i in range(len(obv)-1, -1, -1):
        ma_idx = i - 10 + 1
        if ma_idx >= 0 and obv[i] < obv_ma10[ma_idx]:
            obv_below_days += 1
        else:
            break

    obv_reversed = obv_below_days >= 3

    # ── L4: WR 回升 ──
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]
    wr_now = float(wr_valid[-1]) if len(wr_valid) > 0 else -50
    wr_5d_low = float(np.min(wr_valid[-5:])) if len(wr_valid) >= 5 else wr_now

    # 信号判定
    if obv_reversed and wr_now > -30:
        return {"signal": "strong_sell",
                "reason": f"OBV跌破MA{obv_below_days}天+WR回升{wr_now:.0f}",
                "current_return_pct": round(current_return, 2)}
    elif obv_reversed:
        return {"signal": "sell",
                "reason": f"OBV跌破MA{obv_below_days}天",
                "current_return_pct": round(current_return, 2)}
    elif wr_now > -30 and wr_5d_low < -60 and current_return > 5:
        return {"signal": "sell",
                "reason": f"WR从{wr_5d_low:.0f}回升至{wr_now:.0f}+获利{current_return:.0f}%",
                "current_return_pct": round(current_return, 2)}
    else:
        return {"signal": "hold",
                "reason": "趋势正常" if current_return > 0 else "等待回升",
                "current_return_pct": round(current_return, 2)}


def _prefetch_kline_batch(db, trade_date):
    """批量预取所有股票近60日K线 (性能优化)."""
    parts = trade_date.split("-")
    y, m = int(parts[0]), int(parts[1])
    m -= 3
    if m <= 0:
        m += 12
        y -= 1
    start_date = f"{y}-{m:02d}-01"

    rows = db.execute(
        "SELECT code, close, high, low, volume FROM daily_kline "
        "WHERE trade_date >= ? AND trade_date <= ? ORDER BY code, trade_date ASC",
        (start_date, trade_date)
    ).fetchall()

    import numpy as np
    from collections import defaultdict
    by_code = defaultdict(list)
    for r in rows:
        c = r.get("code") or r.get("ts_code", "")
        if not c:
            continue
        by_code[c].append((
            float(r["close"] or 0), float(r["high"] or 0),
            float(r["low"] or 0), float(r["volume"] or 0)
        ))

    result = {}
    for code, data in by_code.items():
        if len(data) >= 40:
            closes = np.array([d[0] for d in data], dtype=np.float64)
            highs = np.array([d[1] for d in data], dtype=np.float64)
            lows = np.array([d[2] for d in data], dtype=np.float64)
            volumes = np.array([d[3] for d in data], dtype=np.float64)
            result[code] = (closes, highs, lows, volumes)
    return result


def generate_bi_plan(picks):
    """生成次日执行计划."""
    plans = []
    for s in picks:
        entry = round(s["close"] * 1.01, 2)
        stop = round(s["close"] * 0.93, 2)  # V4.0: -7%止损(趋势战法需要更宽)
        tp1 = round(s["close"] * 1.08, 2)   # +8%止盈一半
        tp2 = round(s["close"] * 1.15, 2)   # +15%全卖

        g = s["grade"]
        sig = s["signal"]
        if g == "S" and sig == "strong_buy":
            pos = "20%"; action = "🟢 重仓买入"
        elif g == "S":
            pos = "15%"; action = "🟢 买入"
        elif g == "A" and sig in ("strong_buy", "buy"):
            pos = "12%"; action = "🟢 买入"
        elif g == "A":
            pos = "8%";  action = "🟡 轻仓"
        elif g == "B":
            pos = "5%";  action = "🟡 观察仓"
        else:
            pos = "0%";  action = "🔴 不参与"

        plans.append({
            "code": s["code"], "name": s["name"], "grade": g,
            "total_score": s["total_score"], "signal": sig,
            "entry_price": entry, "stop_loss": stop,
            "take_profit_1": tp1, "take_profit_2": tp2,
            "position": pos, "action": action,
            "obv_level": s["obv_level"], "wr_level": s["wr_level"],
            "close": s["close"],
        })
    return plans


def print_bi_results(top, trade_date):
    """打印选股结果."""
    print(f"\n{'=' * 110}")
    print(f"  毕师傅趋势启动战法 — {trade_date} Top {len(top)}")
    print(f"{'=' * 110}")
    print(f"\n  OBV趋势(35) + WR急跌(28) + 缩量(12) + 均线(10) + ADX(8) + 板块(7) = 100")
    print(f"  V4.1 三层确认: 🔥强买=趋势+回踩+反弹 🟢买入=趋势+回踩")
    print(f"{'#':<3} {'代码':<8} {'名称':<8} {'总':<4} {'级':<3} {'信号':<10} "
          f"{'OBV':<10} {'WR跌':<6} {'反弹':<4} {'量':<6} {'均线':<8} {'板块'}")
    print(f"{'-'*95}")
    for i, s in enumerate(top, 1):
        sig_map = {"strong_buy": "🔥强买", "buy": "🟢买入", "watch": "🟡观察"}
        sig = sig_map.get(s["signal"], s["signal"])
        wrs = f"{s.get('wr_drop_3d',0):+.0f}"
        reb = "✅" if s.get('_rebound') else "—"
        print(f"{i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<4.0f} {s['grade']:<3} "
              f"{sig:<10} "
              f"{s['obv_level']:<10} {wrs:<6} {reb:<4} {s['vol_level']:<6} "
              f"{s['ma_level']:<8} {s['industry']}")

    s_cnt = sum(1 for s in top if s['grade']=='S')
    a_cnt = sum(1 for s in top if s['grade']=='A')
    b_cnt = sum(1 for s in top if s['grade']=='B')
    strong = sum(1 for s in top if s['signal']=='strong_buy')
    buy = sum(1 for s in top if s['signal']=='buy')
    print(f"\n  S={s_cnt} A={a_cnt} B={b_cnt} | 🔥强买={strong} 🟢买入={buy}")


def print_bi_plan(plans):
    """打印执行计划."""
    print(f"\n{'=' * 100}")
    print(f"  📋 毕师傅趋势启动战法 — 执行计划")
    print(f"{'=' * 100}")
    print(f"  {'代码':<8} {'名称':<8} {'级':<3} {'信号':<10} {'动作':<16} {'入场':<8} {'止损':<8} {'止盈1':<8} {'止盈2':<8} {'仓位':<6}")
    print(f"  {'-' * 90}")
    for p in plans:
        print(f"  {p['code']:<8} {p['name']:<8} {p['grade']:<3} {p['signal']:<10} "
              f"{p['action']:<16} {p['entry_price']:<8} {p['stop_loss']:<8} "
              f"{p['take_profit_1']:<8} {p['take_profit_2']:<8} {p['position']:<6}")


# ── Engine wrapper ──

class BiTrendLaunchEngine:
    """毕师傅趋势启动战法引擎."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute Bi trend launch screening."""
        from kronos_factors.scorer._db_stub import _get_db

        if trade_date is None:
            with _get_db(readonly=True) as db:
                row = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
                trade_date = row["max"] if row else None
        if not trade_date:
            return []

        with _get_db(readonly=True) as db:
            top, _, _ = run_bi_screening(db, trade_date, top_n=top_n)
        return top if top else []
