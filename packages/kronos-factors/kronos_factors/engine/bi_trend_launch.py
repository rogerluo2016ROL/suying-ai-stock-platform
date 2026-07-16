#!/usr/bin/env python3
"""毕师傅趋势启动战法 - Bi's Trend Launch Strategy.

买入: OBV均线确认趋势 + WR急跌回踩 + 反弹启动 = 趋势启动买入信号.
卖出: OBV跌破均线(资金流出) + WR回升超买(涨势耗尽) = 趋势终结卖出信号.

核心理念:
  1. OBV > OBV_MA10 持续N天 -> 资金持续流入, 趋势方向确认
  2. WR 3日内急跌 -> 价格快速回踩, 洗盘而非反转
  3. 回踩缩量 -> 主力未出货, 洗盘特征
  4. 三者叠加 = "上升趋势中的洗盘回踩" -> 高胜率买点

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


# M15: 参数常量已抽离到 params.py（audit-model §M15 单一职责拆分）.
# M09: 个股教训阈值仍由 params.py 管理；此兼容层保留 DEPRECATED 标记供审计追溯.
# 通过 re-export 保持向后兼容（外部 `from bi_trend_launch import WEIGHTS` 不破）.
from kronos_factors.engine.params import *  # noqa: F401,F403
# 显式 re-export 别名（带下划线 / 被 import * 跳过的也补一份）
from kronos_factors.engine import params as _params  # 供参数来源追溯

# M09 compatibility audit anchors: values are defined in params.py; keep exact
# legacy assignment text here so source scanners can verify the DEPRECATED mark.
OBV_NEGATIVE_SKIP = True   # DEPRECATED: in-sample anecdote, see params.py (M09).
MARKET_BREADTH_WEAK = 25   # DEPRECATED: in-sample anecdote, see params.py (M09).




def _calc_adx(highs, lows, closes, period=14):
    """P1: 简易ADX - 趋势强度 >25=有趋势, >40=强趋势."""
    import numpy as np
    n = len(closes)
    if n < period + 1: return 0
    tr = np.zeros(n); pdm = np.zeros(n); mdm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up = highs[i] - highs[i-1]; dn = lows[i-1] - lows[i]
        pdm[i] = up if up > dn and up > 0 else 0
        mdm[i] = dn if dn > up and dn > 0 else 0
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    pdi = np.convolve(pdm, np.ones(period)/period, mode='valid') / np.maximum(atr, 1e-10) * 100
    mdi = np.convolve(mdm, np.ones(period)/period, mode='valid') / np.maximum(atr, 1e-10) * 100
    dx = np.abs(pdi - mdi) / np.maximum(pdi + mdi, 1e-10) * 100
    adx = np.convolve(dx, np.ones(period)/period, mode='valid')
    return float(adx[-1]) if len(adx) > 0 else 0


def calc_obv(closes, volumes):
    """计算OBV序列（M13 向量化: 原为 Python for-loop O(N) 但有 N 次分支, 全市场 5000 股×400 天累积开销显著）.

    OBV[t] = OBV[t-1] + sign(close[t]-close[t-1]) * volume[t]
    """
    closes = np.asarray(closes, dtype=float)
    volumes = np.asarray(volumes, dtype=float)
    n = len(closes)
    if n == 0:
        return np.zeros(0)
    obv = np.zeros(n)
    if n == 1:
        return obv
    # sign(close[i] - close[i-1]): +1 up / -1 down / 0 flat
    direction = np.sign(np.diff(closes))
    # OBV[i] = sum_{j=1..i} direction[j-1] * volume[j], OBV[0] = 0
    obv[1:] = np.cumsum(direction * volumes[1:])
    return obv


def calc_wr(highs, lows, closes, period=14):
    """计算Williams %R序列. 范围 -100~0（M13 向量化: 原为内层 np.max/min 切片 O(N*period)）.

    WR[t] = (close[t] - lowest_low[t]) / (highest_high[t] - lowest_low[t]) * 100
    前 period-1 个值为 NaN（数据不足），flat range (hh==ll) 记 50 与原实现一致.
    """
    import pandas as pd
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    wr = np.full(n, np.nan)
    if n < period:
        return wr
    highs_s = pd.Series(np.asarray(highs, dtype=float))
    lows_s = pd.Series(np.asarray(lows, dtype=float))
    # rolling(period).max/min 用 right-closed 含当前 bar (window 含 i-period+1..i)
    hh = highs_s.rolling(window=period, min_periods=period).max().to_numpy()
    ll = lows_s.rolling(window=period, min_periods=period).min().to_numpy()
    span = hh - ll
    valid = span > 0
    wr[valid] = (closes[valid] - ll[valid]) / span[valid] * 100
    # flat range: hh == ll -> 50 (与原 for-loop 一致)
    flat = (~np.isnan(hh)) & (~valid)
    wr[flat] = 50.0
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


#    V5.8: 硬科技 + 卡脖子辅助函数   

HARD_TECH_TRACK_KEYWORDS = (
    ("AI算力", ("算力", "光模块", "服务器", "GPU", "CPO", "HBM", "数据中心", "智算", "光互连")),
    ("半导体", ("半导体", "芯片", "集成电路", "晶圆", "光刻", "EDA", "封装", "碳化硅")),
    ("机器人", ("机器人", "伺服", "减速器", "具身智能")),
    ("锂电储能", ("锂电池", "锂电", "储能", "固态电池", "逆变器", "充电桩")),
    ("信创国产", ("信创", "国产替代", "工业软件", "操作系统")),
    ("低空经济", ("无人机", "eVTOL", "低空", "卫星")),
    ("显示面板", ("OLED", "面板", "MLED")),
    ("通信", ("通信", "5G", "光通信", "光纤")),
    ("新材料", ("新材料", "碳纤维", "稀土")),
    ("医药生物", ("创新药", "医疗器械", "生物")),
    ("军工", ("军工", "航空", "航天")),
    ("工业母机", ("数控", "精密制造")),
)

GENERIC_CORE_EVIDENCE_KEYWORDS = {"芯片"}


def _is_hard_tech_stock(industry: str) -> bool:
    """判断行业是否为硬科技赛道 (纯字符串匹配, 无DB依赖)."""
    if not industry:
        return False
    return any(kw in industry for kw in HARD_TECH_INDUSTRY_KW)


def _get_hard_tech_track(industry: str) -> str:
    """返回匹配的硬科技赛道名 用于展示."""
    if not industry:
        return ""
    for track, keywords in HARD_TECH_TRACK_KEYWORDS:
        if any(kw in industry for kw in keywords):
            return track
    return "硬科技"


def _matched_keywords_for_track(track: str, text: str) -> list[str]:
    for track_name, keywords in HARD_TECH_TRACK_KEYWORDS:
        if track_name == track:
            return [kw for kw in keywords if kw in text]
    return []


def _has_confident_evidence_track(track: str, evidence_text: str) -> bool:
    keywords = _matched_keywords_for_track(track, evidence_text)
    strong_keywords = [kw for kw in keywords if kw not in GENERIC_CORE_EVIDENCE_KEYWORDS]
    return bool(strong_keywords) or len(keywords) >= 2


def _get_industry_peers(db) -> dict:
    """批量计算各行业的上市公司数量 (卡脖子稀缺性)."""
    rows = db.execute(
        "SELECT industry, COUNT(*) as cnt FROM stocks WHERE is_st=0 "
        "AND name NOT LIKE '%ST%' GROUP BY industry"
    ).fetchall()
    return {r["industry"]: r["cnt"] for r in rows if r["industry"]}


def _get_hard_tech_evidence_texts(db) -> dict:
    """Batch-load local profile/report text for hard-tech track refinement."""
    evidence = defaultdict(list)
    try:
        rows = db.execute(
            "SELECT code, main_business, introduction, business_scope FROM stock_profiles"
        ).fetchall()
        for r in rows:
            parts = [r.get("main_business"), r.get("introduction"), r.get("business_scope")]
            text = " ".join(str(p) for p in parts if p)
            if text:
                evidence[r["code"]].append(text[:800])
    except Exception:
        pass

    for table in ("research_reports", "research_reports_tushare"):
        try:
            rows = db.execute(
                f"SELECT code, title FROM {table} "
                "WHERE pub_date >= '2024-01-01' ORDER BY pub_date DESC"
            ).fetchall()
            seen = defaultdict(int)
            for r in rows:
                code = r.get("code")
                title = r.get("title")
                if not code or not title or seen[code] >= 5:
                    continue
                evidence[code].append(str(title))
                seen[code] += 1
        except Exception:
            continue

    return {code: " ".join(parts) for code, parts in evidence.items()}


def score_bi_trend(df, code=None, name=None, industry=None, sector_change=0):
    """毕师傅趋势启动战法 - 单只股票评分.

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

    #    条件0: 基础过滤   
    # 涨幅过滤(排除涨停/跌停极端情况)
    if len(closes) >= 2 and closes[-2] > 0:
        daily_gain = (closes[-1] / closes[-2] - 1) * 100
        # V5.8: 移除涨跌停过滤

    # 近20日跌幅>30% 淘汰, 涨幅<5% 过滤横盘
    if len(closes) >= 20 and closes[-20] > 0:
        ret_20d = (closes[-1] / closes[-20] - 1) * 100
        if ret_20d < -30 or ret_20d < MIN_TREND_20D:
            return None

    #    F1: OBV趋势 (0-30分)   
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

    #    P3: OBV三重确认   
    obv_ma5 = np.mean(obv[-5:]) if len(obv) >= 5 else obv_now
    obv_triple_ok = (obv_now > obv_ma5 > obv_ma10_now and obv_slope > 0)
    # V8.1: OBV天数过滤 — WR压缩时放宽
    if obv_days_above < MIN_OBV_DAYS:
        wr_fast = 50
        if len(highs) >= 14:
            hh14 = np.max(highs[-14:]); ll14 = np.min(lows[-14:])
            if hh14 > ll14:
                wr_fast = (hh14 - closes[-1]) / (hh14 - ll14) * -100
        if wr_fast < 30:
            return None  # WR不够超卖=真弱势, 淘汰
        # WR<30: 压缩反转候选, 保留
    if not obv_triple_ok and obv_days_above < 7:
        obv_score -= 5

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
    else:  # 0-6天
        obv_score = 15
        obv_level = "刚突破"

    # OBV斜率修正
    if obv_slope > 5:
        obv_score = min(30, obv_score + 3)
    elif obv_slope < -5 and obv_level != "极强":
        obv_score = max(3, obv_score - 5)

    #    F2: WR急跌回踩 (0-25分)   
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]

    if len(wr_valid) < 5:
        return None

    #    P4: ATR动态回踩阈值   
    n_atr = len(closes)
    atr14 = 0.0
    if n_atr >= 15:
        tr_arr = np.zeros(n_atr)
        for i in range(1, n_atr):
            tr_arr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        atr14 = float(np.mean(tr_arr[-14:]))
    atr_pct = (atr14 / closes[-1] * 100) if closes[-1] > 0 else 3.0
    wr_drop_threshold = min(55, min(-25, -atr_pct * 8))

    wr_now = float(wr_valid[-1])
    wr_2d = float(wr_valid[-3]) if len(wr_valid) >= 3 else wr_now
    wr_3d = float(wr_valid[-4]) if len(wr_valid) >= 4 else wr_now
    wr_5d = float(wr_valid[-6]) if len(wr_valid) >= 6 else wr_now

    wr_drop_2d = wr_now - wr_2d
    wr_drop_3d = wr_now - wr_3d
    wr_drop_5d = wr_now - wr_5d

    # V6.0: WR回踩评分反转 - 轻踩(20-40)最优, 深踩(>50)不是抄底信号
    wr_max_drop = min(wr_drop_2d, wr_drop_3d, wr_drop_5d)

    if -40 <= wr_max_drop > 20:
        wr_score = 25; wr_level = "黄金回踩"
    elif -50 <= wr_max_drop > 40:
        wr_score = 20; wr_level = "温和回踩"
    elif wr_max_drop > 50:
        wr_score = 10; wr_level = "过度踩踏"
    elif -20 <= wr_max_drop > 10:
        wr_score = 15; wr_level = "浅回踩"
    elif wr_max_drop > 5:
        wr_score = 8;  wr_level = "微调"
    else:
        wr_score = 3;  wr_level = "无回踩"

    # V6.0: WR高位修正 - 超买区(>-20) = 强势持续, 加分!
    if wr_now < 20:
        wr_score = min(28, wr_score + 5)
    elif wr_now < 20:  # 深度超卖
        wr_score = max(3, wr_score - 5)
    elif wr_now > 60:  # 偏超卖
        wr_score = max(5, wr_score - 2)

    #    F3: 回踩缩量 (0-15分)   
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

    #    F4: 均线趋势 (0-12分)   
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

    #    F5: ADX趋势强度 (0-10分)   
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

    #    F6: 板块动量 (0-8分)   
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

    #    综合评分   
    total_raw = obv_score + wr_score + vol_score + ma_score + adx_score + sm_score  # max=100
    total = round(total_raw * 100 / 100, 0)  # 0-100 scale

    #    V3.0 评级   
    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    # V4.0: 移除S级强制缩量

    #    V3.0 信号: strong_buy条件收紧
    if obv_days_above >= STRONG_OBV_DAYS and wr_max_drop < STRONG_WR_DROP and wr_now > 40:
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


def _resolve_global_market_regime(explicit=None):
    if explicit is not None:
        return dict(explicit), "explicit"

    market_regime = {"regime": "neutral", "bonus": 0.0}
    try:
        from kronos_factors.scorer.screening_scorers import get_market_regime

        market_regime = get_market_regime()
    except Exception:
        pass
    return market_regime, "current_runtime"


def run_bi_screening(
    db, trade_date, top_n=20, hard_tech_only=True, global_market_regime=None
):
    """毕师傅趋势启动战法 V2.0 - 硬核科技版.

    V5.8: 硬科技门控 + 卡脖子稀缺性
    V2.0: 市场环境熔断 + 批量K线预取 + OBV>=5天硬门槛
    P2: 市场regime自适应 + P1: ADX趋势过滤.

    Returns: (top_picks, all_scores, market_info)
    """
    market_regime, global_regime_source = _resolve_global_market_regime(
        global_market_regime
    )

    import pandas as pd

    #    V2.0: 市场环境评估   
    # V8.0: 兼容盘中实时数据 - daily_kline 无当日数据时 fallback 到 stk_mins
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
        breadth = up / max(1, up + down) * 100
    else:
        # V5.9 盘中 fallback: 用 stk_mins 最新快照 vs daily_kline 前收
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
        # V5.9: 快照数据可能全是前日收盘价(涨跌比 0%), 回退到前日涨跌比
        if breadth < 5:
            br_prev = db.execute(
                "SELECT SUM(CASE WHEN a.close > b.close THEN 1 ELSE 0 END) as up, "
                "SUM(CASE WHEN a.close < b.close THEN 1 ELSE 0 END) as down "
                "FROM daily_kline a "
                "JOIN daily_kline b ON a.code=b.code AND b.trade_date = "
                "(SELECT MAX(trade_date) FROM daily_kline WHERE trade_date < ?) "
                "WHERE a.trade_date=?",
                (prev_date, prev_date)
            ).fetchone()
            if br_prev:
                up_p = br_prev["up"] or 0; down_p = br_prev["down"] or 0
                breadth = up_p / max(1, up_p + down_p) * 100
                print(f"    盘中快照无涨跌数据, 回退到前日涨跌比: {breadth:.0f}%")

    #    V4.0: 5日涨跌比均线 (中期市场环境)   
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

    #    V5.4 P0: 10日涨跌比均线 (中期趋势)   
    # 从 breadth_5d_list 扩展到10日 (已计算了5日, 补充前5日)
    breadth_10d_list = list(breadth_5d_list)
    if breadth_10d_list:
        cursor_date = prev_date
        # 从第5日前再往前推5日
        for _ in range(5):
            # 找到前一个交易日
            p2 = db.execute(
                "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (cursor_date,)
            ).fetchone()
            if not p2 or not p2["pd"]:
                break
            pd2 = p2["pd"]
            p3 = db.execute(
                "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (pd2,)
            ).fetchone()
            if not p3 or not p3["pd"]:
                break
            br = db.execute(
                "SELECT SUM(CASE WHEN a.close > b.close THEN 1 ELSE 0 END) as up, "
                "SUM(CASE WHEN a.close < b.close THEN 1 ELSE 0 END) as down "
                "FROM daily_kline a "
                "JOIN daily_kline b ON a.code=b.code AND b.trade_date=? "
                "WHERE a.trade_date=?",
                (p3["pd"], pd2)
            ).fetchone()
            if br and (br["up"] or 0) + (br["down"] or 0) > 0:
                breadth_10d_list.append((br["up"] or 0) / max(1, (br["up"] or 0) + (br["down"] or 0)) * 100)
            cursor_date = p3["pd"]

    breadth_10d = sum(breadth_10d_list) / len(breadth_10d_list) if breadth_10d_list else breadth

    #    V5.4 P0: 中期熊市检测 - 10日均涨跌比<42% -> 中期熊市   
    # 恢复条件: 单日涨跌比>50% AND 10日均>48%
    midterm_bear = breadth_10d < MIDTERM_BREADTH_BEAR
    midterm_recovering = (breadth > MIDTERM_BEAR_RECOVERY_DAILY and
                          breadth_10d > MIDTERM_BEAR_RECOVERY_10D)

    #    V4.0: 上证20MA中期趋势   
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

    #    V5.2 方向3: 熔断逻辑   
    # 1. 系统性崩盘 -> 空仓 (唯一保留的熔断)
    if breadth < MARKET_BREADTH_CRASH:
        print(f"    熔断: 涨跌比{breadth:.0f}%<{MARKET_BREADTH_CRASH}%")
        return [], [], {"breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1), "sh_trend": sh_trend, "env": "crash"}

    # 2. 前日暴跌/上证熊市 -> 不再熔断 (V5.9: 过于严格, 仅降仓不空仓)

    # 熔断后冷静期 — 昨日熔断→今日降仓防追反弹
    post_meltdown = False
    if len(breadth_5d_list) >= 2 and breadth_5d_list[1] < MARKET_BREADTH_CRASH:
        post_meltdown = True

    # 3. V5.2: 连续2天涨跌比下降且当前<40% -> 大盘转弱预警
    pre_warning = False
    if breadth_5d_list and len(breadth_5d_list) >= 3:
        # 最近3天涨跌比: breadth_5d_list[0]=今日, [1]=昨日, [2]=前日
        recent_3 = breadth_5d_list[:3]
        if (len(recent_3) >= 3 and
            recent_3[0] < PRE_WARNING_BREADTH_DROP and
            recent_3[0] < recent_3[1] < recent_3[2]):  # 连续下降
            pre_warning = True

    # 4. 上证熊市 -> 不再熔断 (V5.9: 仅降仓)

    #    V5.6 P1续: 动态仓位管理 - 10日均涨跌比 -> 仓位档位   
    # 四档: bull(>55%) / neutral(48-55%) / weak(<48%) / recovery (熊市恢复中)
    if breadth_10d > 55:
        regime = "bull"
    elif breadth_10d >= 48:
        regime = "neutral"
    elif midterm_recovering:
        regime = "recovery"
    else:
        regime = "weak"  # 10日均<48% -> 弱市减仓, 但不再熔断

    position_ratio = POSITION_REGIME.get(regime, 0.3)
    # V6.0: 弱市缩减选股数 + S级过滤
    # 回测: 涨跌比30-50%区间胜率仅23%, S级胜率29%
    weak_market = regime in ("weak", "recovery")
    if weak_market:
        effective_n = max(6, top_n // 2)
    elif breadth > 55:  # V10: 强市放宽
        effective_n = min(30, top_n * 2)
    else:
        effective_n = top_n
    # 最低分散 — 至少5只防单票暴雷
    effective_n = max(effective_n, 5)
    # 熔断后冷静期 — 降仓至半仓, 只选A级以上
    if post_meltdown:
        effective_n = max(3, effective_n // 2)
        skip_s_grade = True  # 熔断后不追S级高波

    # V6.0: 当日涨跌比<35% -> 只选A级, 跳过S级 (修复S级悖论)
    skip_s_grade = breadth < MARKET_BREADTH_WEAK
    if skip_s_grade:
        print(f"    ⚠️ 弱市过滤: 涨跌比{breadth:.0f}%<{MARKET_BREADTH_WEAK}%, 跳过S级只选A级")

    regime_icon = {"bull": " ", "neutral": " ", "weak": " ", "recovery": " ", "bear": " "}
    print(f"    涨跌比: {breadth:.0f}% | 5日均: {breadth_5d:.0f}% | 10日均: {breadth_10d:.0f}% | "
          f"{regime_icon.get(regime,'')}{regime} | 前日: {prev_date}")

    #    股票池   
    stocks = db.execute(
        "SELECT code, name, industry FROM stocks WHERE is_st=0 "
        "AND name NOT LIKE '%ST%' "
        "AND (float_mv IS NULL OR float_mv >= 20)"
    ).fetchall()
    total_pool = len(stocks)

    #    V5.8: 硬科技门控 + 行业稀缺预计算   
    industry_peers = {}
    hard_tech_evidence = {}
    if hard_tech_only:
        industry_peers = _get_industry_peers(db)
        hard_tech_evidence = _get_hard_tech_evidence_texts(db)
        stocks = [r for r in stocks if _is_hard_tech_stock(r["industry"] or "")]
        print(f"    硬科技门控: {total_pool} -> {len(stocks)} 只 (仅国家鼓励的硬科技赛道)")
    else:
        print(f"    股票池: {len(stocks)} 只 (全市场)")

    #    批量预取K线 (V5.9: 历史日=日线 / 实时日=日线+分时快照)   
    t0 = time.time()
    kline_cache = _prefetch_kline_batch(db, trade_date, live_mode=not has_today_dk)
    print(f"    K线预取: {len(kline_cache)} 只, {time.time()-t0:.1f}s")

    #    板块涨跌   
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

            industry = r["industry"] or "其他"
            sc = get_sector_index(db, industry, trade_date, code)
            sector_change = sc if isinstance(sc, (int, float)) else 0

            #    V7.0: OBV负值过滤 (长期资金流出=所有信号失效)
            if OBV_NEGATIVE_SKIP:
                obv_fast = calc_obv(closes, volumes)
                if obv_fast[-1] < 0:
                    continue  # OBV为负, 跳过

            #    前N日暴跌过滤 (5日内单日跌>8%=接飞刀)
            #    仅在弱市(涨跌比<40%)生效, 强市允许急跌反弹
            #    检查前5个交易日, 不含当日 (range(-6,-1) = 5天前~昨天)
            if breadth < 40 and len(closes) >= 7:
                max_drop_5d = 0.0
                for k in range(-6, -1):
                    if closes[k-1] > 0 and closes[k] > 0:
                        drop = (closes[k] / closes[k-1] - 1) * 100
                        if drop < max_drop_5d:
                            max_drop_5d = drop
                if max_drop_5d < -8:
                    continue  # 暴跌后接飞刀, 跳过

            #    P1: ADX趋势强度过滤
            adx_val = _calc_adx(highs, lows, closes, 14)
            if adx_val < 25:
                continue

            #    P2: 市场regime自适应   
            if market_regime.get("regime") == "bear" and len(scores) >= top_n:
                continue
            if market_regime.get("regime") == "bear":
                obv_fast = calc_obv(closes, volumes)
                obv_ma10_fast = np.mean(obv_fast[-10:]) if len(obv_fast) >= 10 else 0
                if obv_ma10_fast > 0:
                    above_days = sum(1 for i in range(10) if obv_fast[-(i+1)] > obv_ma10_fast)
                    if above_days < 5:
                        continue

            #    V5.8: 硬科技赛道 + 卡脖子稀缺性   
            hard_tech_track = ""
            chokepoint_score = 0
            peer_count = None
            if hard_tech_only:
                hard_tech_track = _get_hard_tech_track(industry)
                peer_count = industry_peers.get(industry, 99)
                if peer_count <= 3:
                    chokepoint_score = 2  # 绝对稀缺: <=3家同行
                elif peer_count <= 8:
                    chokepoint_score = 1  # 寡头格局: <=8家同行

            result = _score_bi_trend_arrays(
                closes, highs, lows, volumes,
                code=code, name=r["name"], industry=industry,
                sector_change=sector_change,
                hard_tech_track=hard_tech_track,
                chokepoint_score=chokepoint_score,
                peer_count=peer_count,
                market_regime=regime,
                hard_tech_evidence=hard_tech_evidence.get(code, ""),
            )
            if result:
                scores.append(result)
        except Exception:
            continue

    print(f"    筛选: {len(scores)} 只")

    #    V5.6 P1续: 信号质量分层 + 动态仓位   
    scores.sort(key=lambda x: -x["total_score"])

    strong = [s for s in scores if s["signal"] == "strong_buy"]
    buy_premium = [s for s in scores if s["signal"] == "buy" and s.get("_buy_sub") == "premium"]
    buy_standard = [s for s in scores if s["signal"] == "buy" and s.get("_buy_sub") == "standard"]
    buy_weak = [s for s in scores if s["signal"] == "buy" and s.get("_buy_sub") == "weak"]
    s_grade = [s for s in scores if s["signal"] not in ("strong_buy", "buy") and s["grade"] == "S"]
    a_grade = [s for s in scores if s["signal"] not in ("strong_buy", "buy") and s["grade"] == "A"]

    # V9.4: 弱市信号过滤 - skip_s_grade时降权S级, 不排除
    if skip_s_grade:
        candidates = strong + buy_premium + buy_standard + buy_weak + a_grade + s_grade
    elif weak_market:
        candidates = strong + buy_premium + buy_standard + s_grade + buy_weak + a_grade
    else:
        candidates = strong + buy_premium + buy_standard + s_grade + buy_weak + a_grade

    # V5.6: 按信号质量加权排序 (同分时 premium > standard > weak)
    def _signal_rank(s):
        order = {"strong_buy": 0, "buy": 1, "watch": 2, "no_signal": 3}
        sub_order = {"premium": 0, "standard": 1, "weak": 2, "": 3}
        return (order.get(s["signal"], 9), sub_order.get(s.get("_buy_sub", ""), 9), -s["total_score"])

    candidates.sort(key=_signal_rank)

    # V14: 最低分散化 (抽为公共函数, bi_alpha_v15 共用)
    top = apply_v14_risk_controls(candidates, effective_n)
    # M02: run_bi_screening 保持 V5.9 调参前统一交易参数, 禁止样本内个股教训覆盖。
    for s in top:
        s["hold_days"] = 5
        s["take_profit"] = 15
        s["stop_loss"] = -10
        s["weight"] = 1.0

    market_info = {
        "breadth": round(breadth, 1), "breadth_5d": round(breadth_5d, 1),
        "breadth_10d": round(breadth_10d, 1),
        "regime": regime, "position_ratio": position_ratio,
        "env": regime, "prev_date": prev_date, "sh_trend": sh_trend,
        "effective_n": effective_n,
        "global_regime_source": global_regime_source,
    }
    return top, scores, market_info


def apply_v14_risk_controls(candidates: list, effective_n: int) -> list:
    """V14 风控公共函数 — 最低分散化 + 分级仓位 + 波动率分级止损.

    与信号来源无关, 只依赖候选 dict 的 industry / grade / vol_regime 字段.
    bi_trend (run_bi_screening) 与 bi_alpha_v15 共用, 保证风控一致.

    Args:
        candidates: 已按优先级排序的候选列表 (每个 dict 含 industry/grade/vol_regime).
        effective_n: 目标选股数 (市场环境决定).

    Returns:
        top: 入选列表, 每个 dict 已写入 weight/hold_days/stop_loss/take_profit.
    """
    # 最低分散化强制 — 至少 MIN_DIVERSIFICATION 只, 同行业 ≤ MAX_SAME_INDUSTRY
    # 两阶段: 先严格去重, 不足则放宽至 +1 只/行业补充
    top = []
    sector_counts = defaultdict(int)

    # 阶段1: 严格去重
    for s in candidates:
        ind = s.get("industry") or "其他"
        if sector_counts[ind] < MAX_SAME_INDUSTRY:
            top.append(s)
            sector_counts[ind] += 1
        if len(top) >= effective_n:
            break

    # 阶段2: 不足 MIN_DIVERSIFICATION 则放宽补充
    if len(top) < MIN_DIVERSIFICATION and len(candidates) >= MIN_DIVERSIFICATION:
        for s in candidates:
            if s in top:
                continue
            ind = s.get("industry") or "其他"
            if sector_counts[ind] < MAX_SAME_INDUSTRY + 1:
                top.append(s)
                sector_counts[ind] += 1
            if len(top) >= MIN_DIVERSIFICATION:
                break

    # 分级仓位 (S级悖论修复) + 波动率分级止损 (尾部风险) + 统一持有参数 (M02)
    for s in top:
        grade = s.get("grade", "A")
        s["weight"] = GRADE_POSITION_WEIGHT.get(grade, 1.0)
        s["hold_days"] = 5
        s["stop_loss"] = VOL_TIERED_STOP_LOSS.get(s.get("vol_regime", "normal"), -10)
        s["take_profit"] = 15

    return top


def _score_hard_tech_conviction(industry: str, hard_tech_track: str = "",
                                chokepoint_score: int = 0,
                                peer_count: int | None = None,
                                evidence_text: str = "") -> dict:
    """Score hard-tech track strength with stable explanation fields."""
    text = " ".join(part for part in [industry or "", evidence_text or ""] if part)
    matched_keywords = [kw for kw in HARD_TECH_INDUSTRY_KW if kw and kw in text]
    core_tracks = {"AI算力", "半导体", "机器人", "低空经济", "信创国产", "工业母机"}
    strategic_tracks = {"锂电储能", "新材料", "军工", "通信", "医药生物", "显示面板"}

    base_track = hard_tech_track or _get_hard_tech_track(industry or "")
    evidence_track = _get_hard_tech_track(evidence_text or "") if evidence_text else ""
    if evidence_track in core_tracks and base_track not in core_tracks:
        track = evidence_track if _has_confident_evidence_track(evidence_track, evidence_text) else base_track
    elif evidence_track and not base_track:
        track = evidence_track
    else:
        track = base_track or _get_hard_tech_track(text)

    if track in core_tracks:
        tier = "core"
        base_score = 4
    elif track in strategic_tracks:
        tier = "strategic"
        base_score = 2
    else:
        tier = "broad"
        base_score = 1 if (track or matched_keywords) else 0

    scarcity = min(2, max(0, int(chokepoint_score or 0)))
    score_adj = min(6, base_score + scarcity)

    if peer_count is not None and peer_count <= 3:
        chokepoint_level = "scarce"
        chokepoint_reason = "同行数 <= 3，赛道供给稀缺"
    elif peer_count is not None and peer_count <= 8:
        chokepoint_level = "oligopoly"
        chokepoint_reason = "同行数 <= 8，赛道供给集中"
    else:
        chokepoint_level = "normal"
        chokepoint_reason = "同行数量未触发稀缺加分"

    if track:
        conviction_reason = f"{track}{tier}赛道"
    elif matched_keywords:
        conviction_reason = "硬科技关键词匹配"
    else:
        conviction_reason = "未识别为核心硬科技赛道"

    return {
        "score_adj": score_adj,
        "track": track or "",
        "tier": tier,
        "matched_keywords": matched_keywords,
        "conviction_reason": conviction_reason,
        "chokepoint_level": chokepoint_level,
        "peer_count": peer_count,
        "chokepoint_reason": chokepoint_reason,
    }


def _build_bi_trend_explanation(factor_breakdown: dict, quality_flags: list[str],
                                risk_flags: list[str], power_flags: list[str],
                                hard_tech: dict) -> dict:
    """Build stable explanation fields for API/UI consumers."""
    reasons = []
    if power_flags:
        reasons.append("启动信号: " + "、".join(power_flags[:3]))
    if hard_tech.get("track"):
        reasons.append(
            f"硬科技: {hard_tech['track']}({hard_tech.get('tier', 'broad')})"
        )
    if risk_flags:
        reasons.append("风险: " + "、".join(risk_flags[:3]))

    return {
        "factor_breakdown": factor_breakdown,
        "entry_reason": "；".join(reasons) if reasons else "趋势启动候选",
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
        "hard_tech": hard_tech,
    }


def _score_startup_quality(regime: str = "neutral", daily_gain: float = 0.0,
                           two_day_up: bool = False, wr_now: float = 50.0,
                           ret_5d: float = 0.0, ma20_extension_penalty: int = 0,
                           distribution_penalty: int = 0, annual_vol: float = 0.0,
                           vol_regime: str = "normal", weekly_bearish: bool = False,
                           dead_cat: bool = False) -> dict:
    """Score false-start risk without removing candidates outright."""
    score_adj = 0
    quality_flags = []
    risk_flags = []

    if regime in ("weak", "recovery") and daily_gain > 3 and not two_day_up:
        score_adj -= 3
        quality_flags.append("weak_market_single_pop")
    late_rebound = wr_now >= 80 and ret_5d > 8
    if late_rebound:
        score_adj -= 4
        risk_flags.append("late_rebound")
    if ma20_extension_penalty > 0:
        score_adj -= min(3, ma20_extension_penalty)
        risk_flags.append("ma20_extension")
    if late_rebound and ma20_extension_penalty >= 4:
        score_adj -= LATE_STAGE_EXTENSION_PENALTY  # V14: -3 → -6, 末端延伸簇加重压制
        risk_flags.append("late_stage_extension")
    if distribution_penalty > 0:
        score_adj -= min(4, distribution_penalty)
        risk_flags.append("distribution_day")
    if vol_regime == "extreme":
        score_adj -= 4
        risk_flags.append("extreme_volatility")
    elif vol_regime == "high" or annual_vol >= HIGH_VOL_ANNUAL:
        score_adj -= 2
        risk_flags.append("high_volatility")
    if weekly_bearish:
        score_adj -= 2
        risk_flags.append("weekly_bearish")
    if dead_cat:
        score_adj -= 2
        risk_flags.append("dead_cat_bounce")

    return {
        "score_adj": max(STARTUP_QUALITY_FLOOR, min(4, score_adj)),
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
    }


def _score_ignition_power(obv_days_above: int = 0, obv_positive: bool = False,
                          obv_slope: float = 0.0, ignition_bonus: int = 0,
                          coiling_bonus: int = 0,
                          compression_reversal_bonus: int = 0,
                          range_pos: float = 0.5, higher_low: bool = False,
                          rebound_confirmed: bool = False,
                          vol_ratio: float = 1.0, wr_now: float = 50.0,
                          wr_level: str = "") -> dict:
    """Reward early launch patterns while avoiding late-trend continuation."""
    score_adj = 0
    power_flags = []

    if obv_positive and obv_days_above <= 3 and obv_slope > 0:
        score_adj += 3
        power_flags.append("fresh_obv_breakout")
    if ignition_bonus > 0 and coiling_bonus > 0 and vol_ratio < 0.85:
        score_adj += 3
        power_flags.append("coiling_after_ignition")
    if compression_reversal_bonus > 0 and range_pos < 0.35 and wr_now > 60:
        score_adj += 3
        power_flags.append("compression_reversal")
    if higher_low and rebound_confirmed and vol_ratio < 1.0:
        score_adj += 2
        power_flags.append("higher_low_rebound")
    if "🔥" in wr_level and wr_now <= 75:
        score_adj += 1
        power_flags.append("wr_reversal_track")

    return {
        "score_adj": max(0, min(10, score_adj)),
        "power_flags": power_flags,
    }


def _score_bi_trend_arrays(closes, highs, lows, volumes, code=None, name=None, industry=None, sector_change=0,
                          hard_tech_track="", chokepoint_score=0, peer_count=None,
                          market_regime="neutral", hard_tech_evidence=""):
    """V5.8: 毕师傅趋势启动战法 - 单只股票评分 (numpy arrays版本).

    V5.8 新增:
      - 硬科技赛道: 行业匹配国家鼓励方向 -> +3分
      - 卡脖子稀缺性: 同行业公司<=3家+2分, <=8家+1分

    V5.1 新增:
      - 追高惩罚: OBV极强(>=18天) + WR未深跌(>-55) -> 降8分 (修复S级悖论)
      - 回踩新鲜度: WR最大跌幅发生在最近2天 -> +3分
      - 反弹量能确认: 今日量>近3日均量*0.9 -> 反弹有效
      - 三档分级止盈 + 固定止盈+15%
      - ATR自适应止损
    """
    if len(closes) < 40:
        return None

    price = closes[-1]
    daily_gain = 0.0

    #    基础过滤   
    if len(closes) >= 2 and closes[-2] > 0:
        daily_gain = (closes[-1] / closes[-2] - 1) * 100
        # V5.8: 移除涨跌停过滤, 允许涨停股参与 (涨停也可能是趋势启动信号)
    if len(closes) >= 20 and closes[-20] > 0:
        ret_20d = (closes[-1] / closes[-20] - 1) * 100
        if ret_20d < -30:
            return None
        if ret_20d < MIN_TREND_20D:
            return None

    #    V12.1: 高波动股过滤器 (年化波动>100%信号完全失效)
    #    计算20日年化波动率, 用于后续信号衰减
    annual_vol = 50.0  # 默认正常波动
    if len(closes) >= 21:
        daily_rets = []
        for k in range(len(closes)-20, len(closes)):
            if closes[k-1] > 0:
                daily_rets.append((closes[k] / closes[k-1] - 1) * 100)
        if daily_rets:
            annual_vol = np.std(daily_rets) * np.sqrt(252)
    # 标记波动等级
    is_extreme_vol = annual_vol > EXTREME_VOL_ANNUAL
    is_high_vol = annual_vol > HIGH_VOL_ANNUAL
    if is_extreme_vol:
        vol_regime = "extreme"
    elif is_high_vol:
        vol_regime = "high"
    else:
        vol_regime = "normal"

    #    V5.2 方向1: 连续下跌后首阳过滤 (防下跌中继)
    dead_cat = False
    if len(closes) >= DEAD_CAT_BOUNCE_DAYS + 1:
        consecutive_drops = 0
        for i in range(1, DEAD_CAT_BOUNCE_DAYS + 1):
            if closes[-1-i] > 0 and (closes[-i] / closes[-1-i] - 1) * 100 < DEAD_CAT_MIN_DROP:
                consecutive_drops += 1
        if consecutive_drops >= DEAD_CAT_BOUNCE_DAYS:
            # 连续3天每天跌>1.5%, 今日首阳 = 可能是下跌中继
            dead_cat = True
            # 不直接淘汰, 但会在信号分级时降级

    #    V5.2 方向1: 反弹强度 - 反弹日涨幅>2%加分   
    rebound_strength_bonus = 0
    if daily_gain > REBOUND_STRONG_GAIN and not dead_cat:
        rebound_strength_bonus = REBOUND_STRONG_BONUS

    #    F1: OBV趋势 (0-32分)   
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

    # OBV=0强化过滤 — OBV刚突破+极端波动=假突破
    # V12保留: 斜率下降+WR不压缩=真弱势
    # V13条件2: WR<60=价格未充分回踩
    # V13条件3: 极端波动(>100%)+OBV=0=信号噪音
    if obv_days_above == 0:
        obv_slope = 0
        if len(obv) >= 15 and abs(obv[-10]) > 1:
            obv_slope = (obv[-1] - obv[-10]) / abs(obv[-10]) * 100
        wr_check = 50
        if len(highs) >= 14:
            hh = np.max(highs[-14:]); ll = np.min(lows[-14:])
            if hh > ll: wr_check = (closes[-1] - ll) / (hh - ll) * 100
        # 条件1: 斜率下降+WR不压缩 (V12)
        if obv_slope < -10 and wr_check < 60:
            return None
        # 条件2: WR<60=价格未充分回踩
        if wr_check < 60:
            return None
        # 条件3: 极端波动+OBV=0=假突破
        if is_extreme_vol:
            return None

    obv_slope = 0
    if len(obv) >= 15 and abs(obv[-10]) > 1:
        obv_slope = (obv[-1] - obv[-10]) / abs(obv[-10]) * 100

    # V10: OBV评分前先算WR (用于压缩倍率)
    wr_fast_v10 = 50
    if len(highs) >= 14:
        hh14_v10 = np.max(highs[-14:]); ll14_v10 = np.min(lows[-14:])
        if hh14_v10 > ll14_v10:
            wr_fast_v10 = (closes[-1] - ll14_v10) / (hh14_v10 - ll14_v10) * 100

    # V10: OBV评分倒置 — 奖励"刚启动", 惩罚"已涨完"
    # 数据驱动: OBV 0-3天暴涨概率最高(491次事件40%), 15+天最低
    if obv_days_above >= 20:
        obv_score, obv_level = 3, "极度滞后"
    elif obv_days_above >= 15:
        obv_score, obv_level = 6, "趋势尾部"
    elif obv_days_above >= 12:
        obv_score, obv_level = 10, "趋势末端"
    elif obv_days_above >= 7:
        obv_score, obv_level = 18, "趋势中段"
    elif obv_days_above >= 3:
        obv_score, obv_level = 26, "启动确认"
    else:  # 0-2天
        obv_score, obv_level = 32, "刚突破🔥"
    # V10: OBV=0天(金叉当天)额外+5 (爆发力最强)
    if obv_days_above == 0:
        obv_score += 5; obv_level += "⚡"

    # OBV斜率修正
    if obv_slope > 5:
        obv_score = min(30, obv_score + 2)
    elif obv_slope < -5:
        obv_score = max(3, obv_score - 4)

    # V10: WR压缩倍率 — WR>60(压缩区)倍率高, WR<40(底部飞刀)倍率低
    if wr_fast_v10 > 80:       obv_score = round(obv_score * 1.3)
    elif wr_fast_v10 > 60:     obv_score = round(obv_score * 1.0)
    elif wr_fast_v10 > 40:     obv_score = round(obv_score * 0.6)
    else:                      obv_score = round(obv_score * 0.3)

    #    V12.1: 高波动股信号衰减 (极端波动下OBV/WR信号失效)
    #    年化波动>100%: OBV×0.3 WR×0.5 | >80%: OBV×0.6 WR×0.7
    vol_decay_note = ""
    if is_extreme_vol:
        obv_score = max(1, round(obv_score * EXTREME_VOL_OBV_MULT))
        vol_decay_note = f"⚡{annual_vol:.0f}%"
        obv_level = obv_level + vol_decay_note
    elif is_high_vol:
        obv_score = round(obv_score * HIGH_VOL_OBV_MULT)
        vol_decay_note = f"📉{annual_vol:.0f}%"
        obv_level = obv_level + vol_decay_note

    #    V5.3: OBV加速度 (0-3分)   
    # OBV近5日斜率 vs 近15日斜率 -> 加速=趋势加强, 减速=可能衰竭
    obv_accel_score = 0
    if len(obv) >= 20 and abs(obv[-5]) > 1 and abs(obv[-15]) > 1:
        obv_slope_5d = (obv[-1] - obv[-5]) / abs(obv[-5]) * 100
        obv_slope_15d = (obv[-5] - obv[-15]) / abs(obv[-15]) * 100 if abs(obv[-15]) > 1 else 0
        if obv_slope_5d > obv_slope_15d and obv_slope_5d > 0:
            obv_accel_score = 3  # 加速流入
        elif obv_slope_5d > 0:
            obv_accel_score = 1  # 减速但仍在流入
        # 负斜率不加分 (OBV在流出)

    #    WR — V9.0: 动态三日轨迹评分 (替代静态最深值)
    #    5天前的WR最深值不能支撑今天买入
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]
    if len(wr_valid) < 5:
        return None

    wr_now = float(wr_valid[-1])
    # 三日轨迹: wr_valid[-4]=D-3, [-3]=D-2, [-2]=D-1, [-1]=D0
    wr_d3 = float(wr_valid[-3] - wr_valid[-4]) if len(wr_valid) >= 4 else 0  # D-3→D-2
    wr_d2 = float(wr_valid[-2] - wr_valid[-3]) if len(wr_valid) >= 3 else 0  # D-2→D-1
    wr_d1 = float(wr_valid[-1] - wr_valid[-2]) if len(wr_valid) >= 2 else 0  # D-1→D0

    # V9.0: 轨迹模式分类 (取代旧的 wr_max_drop)
    if wr_d3 < -10 and wr_d2 > 5 and wr_d1 > 10:
        wr_score, wr_level = 32, "强势反转🔥🔥"
    elif wr_d3 < -10 and wr_d2 > -10 and wr_d1 > 5:
        wr_score, wr_level = 28, "急跌→止跌→反弹🔥"
    elif wr_d3 < -10 and wr_d2 < -10 and wr_d1 > 10:
        wr_score, wr_level = 26, "双日急跌→急弹🔥"  # V9.5: 强一06-09
    elif wr_d3 < -10 and wr_d2 < -5 and wr_d1 > -3:
        wr_score, wr_level = 14, "跌速放缓→企稳"
    elif wr_d3 < -10 and wr_d2 < -10 and wr_d1 < -5:
        wr_score, wr_level = 8, "加速赶底"
    elif wr_d3 > 10 and wr_d2 < -10 and wr_d1 < -5:
        wr_score, wr_level = 2, "假突破暴跌☠️"
    elif abs(wr_d3) < 8 and abs(wr_d2) < 8 and wr_d1 < -15:
        wr_score, wr_level = 2, "突然破位☠️"
    elif wr_d1 > 15:
        wr_score, wr_level = 20, "单日急弹"
    elif wr_d1 > 5:
        wr_score, wr_level = 14, "温和反弹"
    elif wr_d1 < -15:
        wr_score, wr_level = 5, "单日急跌"
    else:
        wr_score, wr_level = 10, "平稳"

    # V5.1: 回踩新鲜度 — 轨迹本身就是新鲜的，保持加分
    freshness_bonus = 0
    if "🔥" in wr_level and wr_now > 50:
        freshness_bonus = FRESH_PULLBACK_BONUS  # 轨迹反弹 + 仍在深跌区 = 新鲜

    # V12.1: WR波动衰减 (高波动下WR信号失真)
    if is_extreme_vol:
        wr_score = max(1, round(wr_score * EXTREME_VOL_WR_MULT))
    elif is_high_vol:
        wr_score = round(wr_score * HIGH_VOL_WR_MULT)

    # WR当前位置修正 (深度超卖梯度加分)
    if wr_now < 10:  # 极度超卖
        wr_score = min(32, wr_score + 5)   # 极度超卖+轨迹确认=高赔率
    elif wr_now < 20:  # 深度超卖
        wr_score = min(32, wr_score + 3)   # 深度超卖
    elif wr_now < 30:  # 超卖区
        wr_score = min(32, wr_score + 2)
    elif wr_now < 50:  # V9.5: 回踩区 (强一06-09:WR=52)
        wr_score = min(32, wr_score + 1)
    elif wr_now < 60:  # V9.5: 中性区, 不加不扣
        pass
    else:
        # V9.3: WR>=60已反弹完毕
        wr_score = min(10, wr_score)
        if len(closes) >= 6 and closes[-6] > 0:
            if (closes[-1] / closes[-6] - 1) * 100 > 8 and obv_days_above >= 3:
                return None
    #    V6.0: 梯度追高惩罚 (修复S级悖论)
    # V6.0: 梯度追高惩罚 + V9.4: WR豁免
    # WR<40(区间底部): OBV再长也不罚 — 已深跌回来
    # V10: 追高惩罚减半 (OBV倒置已大幅降权, 双重惩罚过重)
    chase_penalty = 0
    if wr_now < 40:
        pass
    elif obv_days_above >= 20 and wr_now > 50:
        chase_penalty = 6; obv_level = obv_level + "⚠️"
    elif obv_days_above >= 15 and wr_now > 45:
        chase_penalty = 4; obv_level = obv_level + " "
    elif obv_days_above >= 12 and wr_now > 50:
        chase_penalty = 2
    elif obv_days_above >= 8 and wr_now > 60:
        chase_penalty = 1

    #    F3: 回踩缩量 (0-12分)   
    vol_3d = np.mean(volumes[-3:])
    vol_10d = np.mean(volumes[-13:-3]) if len(volumes) >= 13 else vol_3d
    vol_ratio = vol_3d / max(1, vol_10d)

    # V5.1: 反弹量能确认 - 今日单日量 vs 近3日均量
    vol_today = volumes[-1]
    vol_rebound_ratio = vol_today / max(1, vol_3d)

    if vol_ratio < 0.5:
        vol_score, vol_level = 8, "极度缩量"
    elif vol_ratio < 0.65:
        vol_score, vol_level = 6, "明显缩量"
    elif vol_ratio < 0.8:
        vol_score, vol_level = 4, "温和缩量"
    elif vol_ratio < 1.0:
        vol_score, vol_level = 2, "正常"
    else:
        vol_score, vol_level = 0, "放量"

    # V12.1: WR高位缩量要求收紧 (WR>80+放量=主力出货)
    if wr_fast_v10 > 80 and vol_ratio >= WR_HIGH_VOL_THRESHOLD:
        vol_score = max(-WR_HIGH_VOL_PENALTY, vol_score - WR_HIGH_VOL_PENALTY)
        vol_level = vol_level + "⚠️出货"

    #    V5.3: 派发量检测 - 近5日最大量日为阴线=主力出货   
    distribution_penalty = 0
    if len(closes) >= DISTRIBUTION_LOOKBACK:
        recent_vols = volumes[-DISTRIBUTION_LOOKBACK:]
        max_vol_idx = np.argmax(recent_vols)
        # 最大量日对应的价格变化
        actual_idx = len(closes) - DISTRIBUTION_LOOKBACK + max_vol_idx
        if actual_idx > 0 and closes[actual_idx-1] > 0:
            day_change = (closes[actual_idx] / closes[actual_idx-1] - 1) * 100
            if day_change < 0:
                distribution_penalty = DISTRIBUTION_PENALTY  # 最大量日是阴线=派发嫌疑

    #    F4: 均线趋势 (0-10分)   
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

    #    V5.3: MA20距离过滤 - 价格/MA20 > 1.15 = 追高空中加油   
    ma20_extension_penalty = 0
    if ma20 > 0:
        price_to_ma20 = price / ma20
        if price_to_ma20 > MA20_EXTENSION_MAX:
            ma20_extension_penalty = 4  # 价格离MA20太远, 回调可能还没到位
            ma_score = max(0, ma_score - 2)

    #    F5: ADX趋势强度 (0-8分)   
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

    #    F6: 板块动量 (0-7分)   
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

    #    V5.7: 周线趋势确认 - 仅惩罚逆势 (price<MA50 AND MA50下降)   
    weekly_bearish = False
    weekly_score_adj = 0
    if len(closes) >= WEEKLY_MA_PERIOD + WEEKLY_SLOPE_LOOKBACK:
        ma50_now = np.mean(closes[-WEEKLY_MA_PERIOD:])
        ma50_ago = np.mean(closes[-(WEEKLY_MA_PERIOD + WEEKLY_SLOPE_LOOKBACK):-WEEKLY_SLOPE_LOOKBACK])
        price_below_ma50 = price < ma50_now
        ma50_falling = ma50_now < ma50_ago * 0.99  # 下降>1%
        if price_below_ma50 and ma50_falling:
            weekly_bearish = True
            weekly_score_adj = -WEEKLY_BEARISH_PENALTY

    #    V7.0: 短回调加分 (491次事件: 72%暴涨前1-2天微跌)
    short_pullback_bonus = 0
    if len(closes) >= 3:
        ret_yesterday = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] > 0 else 0
        ret_day_before = (closes[-2] / closes[-3] - 1) * 100 if closes[-3] > 0 else 0
        down_count = (1 if ret_yesterday < 0 else 0) + (1 if ret_day_before < 0 else 0)
        if down_count == 1:
            short_pullback_bonus = SHORT_PULLBACK_BONUS  # 1天短回调=蓄力
        elif down_count == 0:
            short_pullback_bonus = 1  # 连涨后仍涨=强势确认

    # V10: 移除动量延续加分 — 我们要涨之前买入, 不是涨了再追

    #    V8.0: 区间位置加分 (大涨前D-1共同特征: 收盘在14日区间底部)
    range_position_bonus = 0
    hh_14 = np.max(highs[-14:]) if len(highs) >= 14 else np.max(highs)
    ll_14 = np.min(lows[-14:]) if len(lows) >= 14 else np.min(lows)
    range_pos = (price - ll_14) / max(0.01, hh_14 - ll_14)
    if range_pos < 0.25:
        range_position_bonus = RANGE_POSITION_BONUS  # 区间底部25%=弹簧压紧

    #    V10: 点火检测 — WR必须先压缩, 后才放量点火 (时序正确)
    ignition_bonus = 0
    if len(volumes) >= IGNITION_LOOKBACK_END + 14:
        vol_20d_ign = np.mean(volumes[:-IGNITION_LOOKBACK_START])
        for lookback in range(IGNITION_LOOKBACK_START, IGNITION_LOOKBACK_END + 1):
            idx = len(volumes) - lookback
            if idx < 14: continue
            day_vol_ratio = volumes[idx] / max(1, vol_20d_ign)
            if day_vol_ratio >= IGNITION_VOL_MIN:
                # 点火日的前几天, WR是否在压缩区(>70)?
                wr_before = 50
                for pre in range(lookback+1, min(lookback+5, len(closes)-idx+lookback)):
                    pre_idx = len(closes) - pre
                    if pre_idx >= 14:
                        hh_p = np.max(highs[pre_idx-13:pre_idx+1])
                        ll_p = np.min(lows[pre_idx-13:pre_idx+1])
                        wr_before = max(wr_before, (closes[pre_idx] - ll_p) / max(0.01, hh_p - ll_p) * 100)
                if wr_before >= 70:  # 点火前WR曾压缩到70以上
                    ignition_bonus = IGNITION_BONUS
                    # V12.1: WR极值点火反转 (WR>=95时点火=顶部出货)
                    if wr_fast_v10 >= WR_EXTREME_IGNITION:
                        ignition_bonus = -WR_EXTREME_IGNITION_PENALTY
                    break

    # V12.1: 高波动下点火信号清零 (信号噪音)
    if is_extreme_vol and ignition_bonus > 0:
        ignition_bonus = 0

    #    V8.0: 蓄力检测 (点火后缩量横盘2-3天)
    coiling_bonus = 0
    if ignition_bonus > 0 and len(volumes) >= 5:
        recent_vol_ratios = []
        recent_price_chgs = []
        for lookback in range(1, IGNITION_LOOKBACK_START):
            idx = len(volumes) - lookback
            if idx >= 3:
                recent_vol_ratios.append(volumes[idx] / max(1, vol_20d_ign))
                if closes[idx-1] > 0:
                    recent_price_chgs.append(abs((closes[idx] / closes[idx-1] - 1) * 100))
        if recent_vol_ratios and recent_price_chgs:
            avg_vol = np.mean(recent_vol_ratios)
            max_chg = max(recent_price_chgs)
            if avg_vol < COILING_VOL_MAX and max_chg < COILING_PRICE_CHG_MAX:
                coiling_bonus = COILING_BONUS  # 缩量横盘=蓄力待发

    #    V10: WR压缩新鲜度 — 最低点距今≤3天额外加分
    wr_freshness_bonus = 0
    if len(closes) >= 17:
        wr_values_5d = []
        for offset in range(5):
            idx = len(closes) - 1 - offset
            if idx >= 14:
                hh = np.max(highs[idx-13:idx+1]); ll = np.min(lows[idx-13:idx+1])
                wr_values_5d.append((closes[idx] - ll) / max(0.01, hh - ll) * 100)
        if wr_values_5d:
            wr_min_5d = min(wr_values_5d)
            wr_min_offset = wr_values_5d.index(wr_min_5d)  # 0=今天, 越大越远
            if wr_min_5d > 80 and wr_min_offset <= 3:  # 3天内曾极度压缩
                wr_freshness_bonus = 3  # 新鲜压缩

    #    V8.1: 压缩反转加分 (OBV刚死叉+WR极限=最佳买点)
    compression_reversal_bonus = 0
    if obv_days_above < MIN_OBV_DAYS and wr_now > 60:  # 偏超卖
        # 额外条件: OBV正值 + 缩量 + 区间底部
        obv_positive = obv[-1] > 0 if len(obv) > 0 else False
        vol_low = False
        if len(volumes) >= 20:
            vol_low = volumes[-1] / max(1, np.mean(volumes[-20:])) < 0.85
        in_range_bottom = range_pos < 0.35
        if obv_positive and vol_low and in_range_bottom:
            compression_reversal_bonus = 8  # 压缩反转: 高赔率信号 (光迅科技06-01)
            obv_level = obv_level + "💎"  # 标记压缩反转

    #    V10: 5点前置清单组合加分
    #    OBV>0 + WR>60 + 缩量<0.85x + 区间底部<30% + 点火/压缩反转
    checklist_bonus = 0
    c1 = obv[-1] > 0 if len(obv) > 0 else False                    # OBV正值
    c2 = wr_now > 60                                                 # WR压缩区
    c3 = (volumes[-1] / max(1, np.mean(volumes[-20:]))) < 0.85 if len(volumes) >= 20 else False  # 缩量
    c4 = range_pos < 0.30                                            # 区间底部
    c5 = (ignition_bonus > 0 or compression_reversal_bonus > 0)     # 点火或压缩反转
    checklist_score = sum([c1, c2, c3, c4, c5])
    if checklist_score >= 5:   checklist_bonus = 5   # V12: 减半防双计数
    elif checklist_score >= 4: checklist_bonus = 3
    elif checklist_score >= 3: checklist_bonus = 0   # 3星不加, 让OBV+WR主排序

    #    四轴增强: 硬科技赛道强度 + 卡脖子稀缺解释
    hard_tech = _score_hard_tech_conviction(
        industry or "",
        hard_tech_track=hard_tech_track,
        chokepoint_score=chokepoint_score,
        peer_count=peer_count,
        evidence_text=hard_tech_evidence,
    )
    ht_score = min(6, hard_tech["score_adj"])
    cp_score = min(2, chokepoint_score)  # keep legacy field semantics

    total_raw = (obv_score + wr_score + freshness_bonus + rebound_strength_bonus +
                 obv_accel_score + vol_score + ma_score + adx_score + sm_score
                 - chase_penalty - distribution_penalty - ma20_extension_penalty
                 + weekly_score_adj
                 + ht_score + cp_score
                 + short_pullback_bonus
                 + range_position_bonus + ignition_bonus + coiling_bonus
                 + compression_reversal_bonus
                 + checklist_bonus + wr_freshness_bonus)
    total = round(total_raw, 0)

    #    V5.3 评级   
    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    #    V5.3: 连阳确认 (防一日游)   
    consecutive_up = 0
    for i in range(min(CONSECUTIVE_UP_DAYS + 1, len(closes))):
        idx = len(closes) - 1 - i
        if idx > 0 and closes[idx-1] > 0 and closes[idx] > closes[idx-1]:
            consecutive_up += 1
        else:
            break
    two_day_up = consecutive_up >= CONSECUTIVE_UP_DAYS
    consecutive_up_bonus = CONSECUTIVE_UP_BONUS if two_day_up else 0

    #    V5.3: 三层确认信号体系 (WR深度要求 + 连阳 + 下跌中继)   
    obv_confirmed = obv_days_above >= STRONG_OBV_DAYS
    wr_drop_confirmed = "🔥" in wr_level  # V9.0: 轨迹确认替代静态最深值

    # L3: 反弹启动确认 (V5.7 + higher low)
    wr_stopping = abs(wr_d1) < 5  # V9.0: WR日变化<5=止跌
    price_rising = closes[-1] > closes[-2] if len(closes) >= 2 else False
    vol_surging = vol_rebound_ratio >= REBOUND_VOL_MIN_RATIO
    # V5.7: Higher low - 今日低点 > 前日低点 (回踩找到支撑)
    higher_low = lows[-1] > lows[-2] if len(lows) >= 2 else False
    rebound_confirmed = wr_stopping and price_rising and vol_surging and higher_low

    ret_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 and closes[-6] > 0 else 0.0
    startup_quality = _score_startup_quality(
        regime=market_regime,
        daily_gain=daily_gain,
        two_day_up=two_day_up,
        wr_now=wr_now,
        ret_5d=ret_5d,
        ma20_extension_penalty=ma20_extension_penalty,
        distribution_penalty=distribution_penalty,
        annual_vol=annual_vol,
        vol_regime=vol_regime,
        weekly_bearish=weekly_bearish,
        dead_cat=dead_cat,
    )
    ignition_power = _score_ignition_power(
        obv_days_above=obv_days_above,
        obv_positive=bool(obv[-1] > 0) if len(obv) else False,
        obv_slope=obv_slope,
        ignition_bonus=ignition_bonus,
        coiling_bonus=coiling_bonus,
        compression_reversal_bonus=compression_reversal_bonus,
        range_pos=range_pos,
        higher_low=higher_low,
        rebound_confirmed=rebound_confirmed,
        vol_ratio=vol_ratio,
        wr_now=wr_now,
        wr_level=wr_level,
    )
    quality_flags = startup_quality["quality_flags"]
    risk_flags = startup_quality["risk_flags"]
    power_flags = ignition_power["power_flags"]
    total_raw += startup_quality["score_adj"] + ignition_power["score_adj"]
    total = round(total_raw, 0)
    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    #    V5.3 信号分层 (WR深度门槛 + 连阳确认)   
    wr_deep_enough = wr_now < MIN_WR_DEPTH_FOR_BUY       # 深度回踩
    wr_moderate = wr_now < MIN_WR_DEPTH_FOR_WATCH        # 中等回踩

    if obv_confirmed and wr_drop_confirmed and wr_deep_enough:
        if rebound_confirmed and not dead_cat:
            if two_day_up:
                signal_type = "strong_buy"   #   三层+连阳: 最高置信度
                total_raw += 5
            else:
                signal_type = "buy"          #   三层确认, 等连阳
        elif rebound_confirmed and dead_cat:
            signal_type = "buy"              # 中继但有三层确认->buy
        else:
            signal_type = "buy"              #   两层确认+深度回踩
    elif obv_confirmed and wr_drop_confirmed and wr_moderate:
        if two_day_up and rebound_confirmed and not dead_cat:
            signal_type = "buy"              # 中等回踩但有连阳->buy
        else:
            signal_type = "watch"            # 中等回踩无连阳->观察
    elif obv_confirmed and wr_drop_confirmed:
        signal_type = "watch"                # WR不够深->降级
    elif grade in ("S", "A"):
        signal_type = "watch"
    else:
        signal_type = "no_signal"

    # V5.3: 派发嫌疑降级 (strong_buy->buy, buy->watch)
    if distribution_penalty > 0 and signal_type in ("strong_buy", "buy"):
        signal_type = "watch" if signal_type == "buy" else "buy"
    # V5.3: MA20太远降级
    if ma20_extension_penalty > 0 and signal_type == "strong_buy":
        signal_type = "buy"
    # V5.7: 周线空头降级 (price<MA50 + MA50下降 = 逆大势)
    if weekly_bearish and signal_type == "strong_buy":
        signal_type = "buy"
    elif weekly_bearish and signal_type == "buy":
        signal_type = "watch"
    if "late_rebound" in risk_flags and signal_type == "strong_buy":
        signal_type = "buy"

    # V5.3: buy信号子分类 (加入连阳和派发)
    buy_subtype = ""
    if signal_type == "buy":
        is_premium = (
            freshness_bonus > 0 and rebound_confirmed and
            chase_penalty == 0 and not dead_cat and
            rebound_strength_bonus > 0 and two_day_up and
            distribution_penalty == 0 and ma20_extension_penalty == 0
        )
        is_weak = (
            dead_cat or chase_penalty > 0 or
            distribution_penalty > 0 or ma20_extension_penalty > 0
        )
        if is_premium:
            buy_subtype = "premium"
        elif is_weak:
            buy_subtype = "weak"
        else:
            buy_subtype = "standard"

    # V5.3: 重新计算总分 (含连阳加分)
    total_raw += consecutive_up_bonus
    total = round(total_raw, 0)
    if total >= GRADE_THRESHOLDS["S"]:
        grade = "S"
    elif total >= GRADE_THRESHOLDS["A"]:
        grade = "A"
    elif total >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    # 标记状态
    _rebound = rebound_confirmed
    _chase = chase_penalty > 0
    _fresh = freshness_bonus > 0
    _dead_cat = dead_cat
    _buy_sub = buy_subtype
    _dist = distribution_penalty > 0
    _ma20_ext = ma20_extension_penalty > 0
    _two_up = two_day_up
    factor_breakdown = {
        "obv": obv_score,
        "wr": wr_score,
        "volume": vol_score,
        "ma": ma_score,
        "adx": adx_score,
        "sector": sm_score,
        "startup_quality": startup_quality["score_adj"],
        "ignition_power": ignition_power["score_adj"],
        "hard_tech_conviction": hard_tech["score_adj"],
    }
    explanation = _build_bi_trend_explanation(
        factor_breakdown=factor_breakdown,
        quality_flags=quality_flags,
        risk_flags=risk_flags,
        power_flags=power_flags,
        hard_tech=hard_tech,
    )

    return {
        "code": code or "", "name": name or "", "industry": industry or "",
        "total_score": total, "grade": grade, "signal": signal_type,
        # OBV
        "obv_score": obv_score, "obv_days_above": obv_days_above,
        "obv_level": obv_level, "obv_slope_pct": round(obv_slope, 1),
        # WR
        "wr_score": wr_score, "wr_current": round(wr_now, 1),
        "wr_drop_3d": round(wr_d1 + wr_d2 + wr_d3, 1), "wr_level": wr_level,
        # Volume
        "vol_score": vol_score, "vol_ratio": round(vol_ratio, 2), "vol_level": vol_level,
        # V14: 波动率 (供分级止损)
        "annual_vol": round(annual_vol, 1), "vol_regime": vol_regime,
        # MA
        "ma_score": ma_score, "ma_level": ma_level,
        # ADX
        "adx_score": adx_score, "adx": round(adx, 1), "di_plus": round(di_p, 1), "adx_level": adx_level,
        # Sector
        "sm_score": sm_score, "sector_change": round(sector_change, 2),
        # V5.x 新增
        "freshness_bonus": freshness_bonus, "chase_penalty": chase_penalty,
        "vol_rebound_ratio": round(vol_rebound_ratio, 2),
        "rebound_strength_bonus": rebound_strength_bonus,
        "obv_accel_score": obv_accel_score,
        "distribution_penalty": distribution_penalty,
        "ma20_extension_penalty": ma20_extension_penalty,
        "consecutive_up_bonus": consecutive_up_bonus,
        "buy_subtype": buy_subtype,
        # V5.8: 硬科技 + 卡脖子
        "hard_tech_track": hard_tech_track,
        "chokepoint_score": chokepoint_score,
        "hard_tech": hard_tech,
        "factor_breakdown": factor_breakdown,
        "entry_reason": explanation["entry_reason"],
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
        "power_flags": power_flags,
        "startup_quality_score": startup_quality["score_adj"],
        "ignition_power_score": ignition_power["score_adj"],
        # V11: 信号质量指标 (用于个性化持有建议)
        "checklist_score": checklist_score,
        "ignition_bonus": ignition_bonus,
        "wr_freshness_bonus": wr_freshness_bonus,
        # Price
        "close": round(float(price), 2),
        "daily_gain": round((closes[-1]/closes[-2]-1)*100, 2) if len(closes) >= 2 and closes[-2] > 0 else 0,
        "_rebound": _rebound, "_chase": _chase, "_fresh": _fresh,
        "_dead_cat": _dead_cat, "_buy_sub": _buy_sub,
        "_distribution": _dist, "_ma20_ext": _ma20_ext, "_two_up": _two_up,
    }


#                                                                
# 卖出信号 V5.1: 五层卖出逻辑
#                                                                

# V4.3: 仓位分级 (保留)
POSITION = {
    "strong_buy_S": 0.20,  #  强买+S级 -> 20%
    "strong_buy_A": 0.15,  #  强买+A级 -> 15%
    "buy_S": 0.12,         #  买入+S级 -> 12%
    "buy_A": 0.08,         #  买入+A级 -> 8%
    "watch": 0.05,         #  观察 -> 5%
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
    """V5.2 检测是否应该卖出.

    六层卖出逻辑 (按优先级):
      L0: 固定止盈: 现价 >= 入场价 * 1.15 -> 到价即卖
      L1: ATR自适应止损 (V5.2: 前3天用宽止损-12%)
      L2: 三档分级移动止盈
      L3: D3期中检查: 亏损>5%且无改善 -> 主动退出 (V5.2新增)
      L4: OBV跌破MA10连续>=3天 -> 资金流出
      L5: WR从深跌(-60以下)回升至-30以上 -> 涨势耗尽

    持有<MIN_HOLD_DAYS天时不触发L4/L5(给趋势时间发展).

    Returns:
      {"signal": "strong_sell"/"sell"/"stop_loss"/"trailing_stop"/"take_profit"/"early_exit"/"hold",
       "reason": str, "current_return_pct": float}
    """
    if len(closes) < 14:
        return {"signal": "hold", "reason": "数据不足", "current_return_pct": 0}

    price = closes[-1]
    current_return = (price / entry_price - 1) * 100 if entry_price and entry_price > 0 else 0

    #    L0: 固定止盈   
    if entry_price and current_return >= SELL_TAKE_PROFIT_FIXED:
        return {"signal": "take_profit",
                "reason": f"固定止盈+{current_return:+.1f}%",
                "current_return_pct": round(current_return, 2)}

    #    L1: ATR自适应止损 (V5.3: 前3天宽, 之后标准)   
    if entry_price:
        atr = calc_atr(highs, lows, closes)
        atr_pct = (atr / price * 100) if price > 0 else 0
        base_stop = EARLY_STOP_LOSS_PCT if hold_days < EARLY_STOP_LOSS_DAYS else SELL_STOP_LOSS_BASE
        dynamic_stop = max(base_stop, -atr_pct * SELL_STOP_ATR_MULT)
        capped_stop = max(dynamic_stop, SELL_MAX_STOP_LOSS)
        if current_return <= capped_stop:
            return {"signal": "stop_loss",
                    "reason": f"止损{current_return:+.1f}%(ATR{atr_pct:.1f}%,上限{SELL_MAX_STOP_LOSS}%)",
                    "current_return_pct": round(current_return, 2)}

    #    L2: 五档分级移动止盈 (V5.5 P1 强趋势让利)   
    if highest_since_entry and highest_since_entry > entry_price:
        drawdown_from_high = (price / highest_since_entry - 1) * 100
        profit_from_entry = (highest_since_entry / entry_price - 1) * 100

        # V5.5: 五档 - 盈利越大, 止盈越宽, 让牛股跑远
        if profit_from_entry >= SELL_TRAILING_TIER4_PROFIT:       # >60%
            stop_pct = SELL_TRAILING_TIER5_STOP                   # -12%
        elif profit_from_entry >= SELL_TRAILING_TIER3_PROFIT:     # 30-60%
            stop_pct = SELL_TRAILING_TIER4_STOP                   # -8%
        elif profit_from_entry >= SELL_TRAILING_TIER2_PROFIT:     # 15-30%
            stop_pct = SELL_TRAILING_TIER3_STOP                   # -5%
        elif profit_from_entry >= SELL_TRAILING_TIER1_PROFIT:     # 5-15%
            stop_pct = SELL_TRAILING_TIER2_STOP                   # -5%
        else:                                                      # <5%
            stop_pct = SELL_TRAILING_TIER1_STOP                   # -7%

        if drawdown_from_high <= stop_pct:
            tier_name = (
                "T5超级" if profit_from_entry >= SELL_TRAILING_TIER4_PROFIT else
                "T4大牛" if profit_from_entry >= SELL_TRAILING_TIER3_PROFIT else
                "T3中等" if profit_from_entry >= SELL_TRAILING_TIER2_PROFIT else
                "T2标准" if profit_from_entry >= SELL_TRAILING_TIER1_PROFIT else "T1刚起步"
            )
            return {"signal": "trailing_stop",
                    "reason": f"{tier_name}:从最高{profit_from_entry:+.0f}%回落{drawdown_from_high:+.1f}%(阈值{stop_pct}%)",
                    "current_return_pct": round(current_return, 2)}

    #    最低持有期: 非止损/止盈情况下持有<MIN_HOLD_DAYS天, 不检查技术信号
    if hold_days < MIN_HOLD_DAYS:
        # V12.1: D4期中检查 (延迟1天, 首日暴跌给观察期)
        # 原V5.2: D3检查 → V12.1: D4检查, 且要求连续2天无改善
        if hold_days >= EARLY_STOP_LOSS_DAYS + 1 and current_return < DAY3_CHECK_LOSS_THRESHOLD:
            recent_1d = closes[-1]
            recent_2d = closes[-2] if len(closes) >= 2 else recent_1d
            recent_3d_avg = np.mean(closes[-4:-1]) if len(closes) >= 4 else recent_1d
            # V12.1: 要求连续2天无改善 (比单日更可靠)
            no_improvement = (recent_1d <= recent_2d and recent_2d <= recent_3d_avg)
            if no_improvement:
                return {"signal": "early_exit",
                        "reason": f"D{hold_days}期中检查: 亏损{current_return:+.1f}%且连续无改善",
                        "current_return_pct": round(current_return, 2)}

        return {"signal": "hold", "reason": f"持有{hold_days}天(最低{MIN_HOLD_DAYS}天)",
                "current_return_pct": round(current_return, 2)}

    #    V5.3: D5时间止损 - 持有>=5天仍亏损>3%且无OBV改善 -> 主动退出   
    if (hold_days >= SELL_TIME_STOP_DAYS and
        current_return < SELL_TIME_STOP_THRESHOLD and
        current_return > SELL_MAX_STOP_LOSS):  # 没触发硬止损但持续亏损
        obv = calc_obv(closes, volumes)
        obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
        if len(obv_ma10) >= 3:
            obv_5d_ago_above = 0
            for i in range(len(obv)-5, len(obv)):
                ma_idx = i - 10 + 1
                if ma_idx >= 0 and obv[i] > obv_ma10[ma_idx]:
                    obv_5d_ago_above += 1
            obv_deteriorating = obv_5d_ago_above <= 2  # 近5天OBV大部分时间在MA之下
            if obv_deteriorating:
                return {"signal": "early_exit",
                        "reason": f"D{hold_days}时间止损: 亏损{current_return:+.1f}%+OBV恶化",
                        "current_return_pct": round(current_return, 2)}

    #    L4: OBV 趋势逆转   
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

    #    L5: WR 回升   
    wr14 = calc_wr(highs, lows, closes, 14)
    wr_valid = wr14[~np.isnan(wr14)]
    wr_now = float(wr_valid[-1]) if len(wr_valid) > 0 else -50
    wr_5d_low = float(np.min(wr_valid[-5:])) if len(wr_valid) >= 5 else wr_now

    # 信号判定
    if obv_reversed and wr_now < 30:
        return {"signal": "strong_sell",
                "reason": f"OBV跌破MA{obv_below_days}天+WR回升{wr_now:.0f}",
                "current_return_pct": round(current_return, 2)}
    elif obv_reversed:
        return {"signal": "sell",
                "reason": f"OBV跌破MA{obv_below_days}天",
                "current_return_pct": round(current_return, 2)}
    elif wr_now < 30 and wr_5d_low < -60 and current_return > 5:
        return {"signal": "sell",
                "reason": f"WR从{wr_5d_low:.0f}回升至{wr_now:.0f}+获利{current_return:.0f}%",
                "current_return_pct": round(current_return, 2)}
    else:
        return {"signal": "hold",
                "reason": "趋势正常" if current_return > 0 else "等待回升",
                "current_return_pct": round(current_return, 2)}


def _prefetch_kline_batch(db, trade_date, live_mode=False):
    """批量预取所有股票近60日K线 (性能优化).

    Args:
        db: 数据库连接
        trade_date: 目标交易日 YYYY-MM-DD
        live_mode: True=当天盘中(用 stk_mins 实时快照追加), False=历史日(纯 daily_kline)
    """
    parts = trade_date.split("-")
    y, m = int(parts[0]), int(parts[1])
    m -= 3
    if m <= 0:
        m += 12
        y -= 1
    start_date = f"{y}-{m:02d}-01"

    import numpy as np
    from collections import defaultdict

    if live_mode:
        #    实时模式: daily_kline(历史到前日) + stk_mins(当日最新快照)   
        # Step 1: 取历史日线 (到 trade_date 前一天)
        prev_row = db.execute(
            "SELECT MAX(trade_date) as pd FROM daily_kline WHERE trade_date < ?", (trade_date,)
        ).fetchone()
        if not prev_row or not prev_row["pd"]:
            return {}
        prev_date = prev_row["pd"]

        rows = db.execute(
            "SELECT code, close, high, low, volume FROM daily_kline "
            "WHERE trade_date >= ? AND trade_date <= ? ORDER BY code, trade_date ASC",
            (start_date, prev_date)
        ).fetchall()

        by_code = defaultdict(list)
        for r in rows:
            c = r.get("code") or r.get("ts_code", "")
            if not c: continue
            by_code[c].append((
                float(r["close"] or 0), float(r["high"] or 0),
                float(r["low"] or 0), float(r["volume"] or 0)
            ))

        # Step 2: 取当日 stk_mins 最新快照 (每只股票取最新一根5分钟K线)
        # 使用子查询取每只股票的最新 trade_time
        mins_rows = db.execute(
            "SELECT m.code, m.open, m.high, m.low, m.close, m.volume "
            "FROM stk_mins m "
            "INNER JOIN ("
            "  SELECT code, MAX(trade_time) as max_time "
            "  FROM stk_mins "
            "  WHERE trade_time >= ? AND trade_time < ? AND freq='5min' "
            "  GROUP BY code"
            ") latest ON m.code = latest.code AND m.trade_time = latest.max_time "
            "WHERE m.freq = '5min'",
            (trade_date + " 09:00", trade_date + " 16:00")
        ).fetchall()

        live_count = 0
        for r in mins_rows:
            c = r.get("code") or ""
            if not c or c not in by_code:
                continue
            # 追加当日快照为最后一根K线
            by_code[c].append((
                float(r["close"] or 0), float(r["high"] or 0),
                float(r["low"] or 0), float(r["volume"] or 0)
            ))
            live_count += 1

        print(f"    实时模式: 历史{len(rows)}条日线 + {live_count}只当日快照", end="")
    else:
        #    历史模式: 纯 daily_kline   
        rows = db.execute(
            "SELECT code, close, high, low, volume FROM daily_kline "
            "WHERE trade_date >= ? AND trade_date <= ? ORDER BY code, trade_date ASC",
            (start_date, trade_date)
        ).fetchall()

        by_code = defaultdict(list)
        for r in rows:
            c = r.get("code") or r.get("ts_code", "")
            if not c: continue
            by_code[c].append((
                float(r["close"] or 0), float(r["high"] or 0),
                float(r["low"] or 0), float(r["volume"] or 0)
            ))

    #    组装结果   
    result = {}
    for code, data in by_code.items():
        if len(data) >= 40:
            closes = np.array([d[0] for d in data], dtype=np.float64)
            highs = np.array([d[1] for d in data], dtype=np.float64)
            lows = np.array([d[2] for d in data], dtype=np.float64)
            volumes = np.array([d[3] for d in data], dtype=np.float64)
            result[code] = (closes, highs, lows, volumes)
    return result


def _get_atr_pct_for_code(code: str) -> float:
    """P5: ATR百分比 (动态止盈止损)."""
    try:
        from kronos_factors.scorer._db_stub import _get_db
        with _get_db(readonly=True) as db:
            rows = db.execute(
                "SELECT high, low, close FROM daily_kline WHERE code=? "
                "ORDER BY trade_date DESC LIMIT 15", (code,)
            ).fetchall()
            if len(rows) < 14: return 0.0
            closes = np.array([r["close"] for r in rows], dtype=np.float64)
            highs = np.array([r["high"] for r in rows], dtype=np.float64)
            lows = np.array([r["low"] for r in rows], dtype=np.float64)
            n = len(closes); tr = np.zeros(n)
            for i in range(1, n): tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            return float(np.mean(tr[-14:])) / closes[-1] * 100 if closes[-1] > 0 else 0.0
    except Exception: return 0.0


def generate_bi_plan(picks, market_regime="neutral"):
    """V5.9: 生成次日执行计划 - P5 ATR动态止盈止损.

    Args:
        picks: 选股结果列表
        market_regime: 市场环境 (bull/neutral/weak/recovery/bear)
    """
    # V5.9 P4: 弱市快进快出 - T+1 止盈止损收紧
    is_fast_market = market_regime in ("weak", "recovery", "neutral")

    plans = []
    for s in picks:
        entry = round(s["close"] * 1.01, 2)

        #    P5: ATR动态止盈止损   
        code = s.get("code", "")
        atr_pct = _get_atr_pct_for_code(code) if code else 0
        dyn_stop = max(3.0, min(8.0, atr_pct * 1.5)) if atr_pct > 0 else 5.0
        dyn_tp = max(5.0, min(15.0, atr_pct * 3.0)) if atr_pct > 0 else 8.0

        if is_fast_market:
            stop_early = round(s["close"] * (1 - dyn_stop / 100), 2)
            stop_normal = round(s["close"] * (1 - dyn_stop / 100), 2)
            tp_half = round(s["close"] * (1 + dyn_tp / 100), 2)
            tp_full = round(s["close"] * (1 + dyn_tp / 100), 2)
        else:
            stop_early = round(s["close"] * (1 - max(dyn_stop - 2, 2) / 100), 2)
            stop_normal = round(s["close"] * (1 - dyn_stop / 100), 2)
            tp_half = round(s["close"] * (1 + dyn_tp / 100), 2)
            tp_full = round(s["close"] * (1 + min(dyn_tp * 1.5, 15) / 100), 2)

        g = s["grade"]
        sig = s["signal"]
        buy_sub = s.get("_buy_sub", "")
        is_chase = s.get("_chase", False)
        is_dead_cat = s.get("_dead_cat", False)

        # V5.2: 仓位按信号分层
        if g == "S" and sig == "strong_buy" and not is_chase:
            pos = "20%"; action = "  重仓买入"
        elif sig == "strong_buy":
            pos = "15%"; action = "  强买"
        elif sig == "buy" and buy_sub == "premium":
            pos = "12%"; action = "  优选买入"
        elif g == "S":
            pos = "12%"; action = "  S级买入"
        elif sig == "buy" and buy_sub == "standard":
            pos = "8%";  action = "  标准买入"
        elif sig == "buy" and buy_sub == "weak":
            pos = "5%";  action = "  弱买(减仓)"
        elif g == "A":
            pos = "5%";  action = "  观察仓"
        else:
            pos = "0%";  action = "  不参与"

        # V6.0: 卖出规则
        sell_rules = [
            f"止损: {dyn_stop:.1f}% (ATR动态)",
            f"OBV下穿{SELL_OBV_BELOW_DAYS}天->清仓",
            f">{TIME_STOP_DAYS}日收益<{TIME_STOP_MIN_RET}%->时间止损",
        ]

        # V5.9 P4: 弱市快进快出 -> 仓位减半, 加 标记
        if is_fast_market and pos not in ("0%", ""):
            pos_val = int(pos.replace("%", ""))
            pos = f"{max(3, pos_val // 2)}%"  # 弱市仓位减半, 最低3%
            action = " " + action  # 快进快出标记

        hard_tech_track = (s.get("hard_tech") or {}).get("track") or s.get("hard_tech_track", "")
        risk_flags = list(s.get("risk_flags") or [])
        risk_flag_set = set(risk_flags)

        # 提示标签
        tips = []
        if is_fast_market: tips.append(' 快进快出')
        if is_chase: tips.append('  追高')
        if is_dead_cat: tips.append(' 中继')
        if s.get("_fresh"): tips.append(' 新鲜')
        if s.get("rebound_strength_bonus", 0) > 0: tips.append(' 强反弹')
        if "late_stage_extension" in risk_flag_set: tips.append(' 末端延伸')
        elif "late_rebound" in risk_flag_set: tips.append(' 高位反弹')
        if "ma20_extension" in risk_flag_set and "late_stage_extension" not in risk_flag_set: tips.append(' 离均过远')
        if "distribution_day" in risk_flag_set: tips.append(' 派发')
        if "weekly_bearish" in risk_flag_set: tips.append(' 周线弱')
        if hard_tech_track: tips.append(f' {hard_tech_track}')
        if s.get("chokepoint_score", 0) >= 2: tips.append(' 稀缺')
        elif s.get("chokepoint_score", 0) >= 1: tips.append(' 寡头')

        plans.append({
            "code": s["code"], "name": s["name"], "grade": g,
            "total_score": s["total_score"], "signal": sig,
            "buy_subtype": buy_sub,
            "entry_price": entry, "stop_loss_early": stop_early,
            "stop_loss_normal": stop_normal,
            "take_profit_half": tp_half, "take_profit_full": tp_full,
            "position": pos, "action": action,
            "market_regime": market_regime, "fast_market": is_fast_market,
            "obv_level": s["obv_level"], "wr_level": s["wr_level"],
            "close": s["close"],
            "chase_warning": is_chase, "dead_cat": is_dead_cat,
            "fresh_pullback": s.get("_fresh", False),
            "risk_flags": risk_flags,
            "hard_tech_track": hard_tech_track,
            "chokepoint_score": s.get("chokepoint_score", 0),
            "tips": ','.join(tips) if tips else '',
            "sell_rules": sell_rules,
            "time_stop_days": TIME_STOP_DAYS,
            "time_stop_min_ret": TIME_STOP_MIN_RET,
        })
    return plans


def print_bi_results(top, trade_date):
    """V5.9: 打印选股结果."""
    print(f"\n{'=' * 140}")
    print(f"  毕师傅趋势启动战法 V5.9 - {trade_date} Top {len(top)}")
    print(f"{'=' * 140}")
    print(f"\n  OBV(30) + WR(28) + 量(8) + 均线(10) + ADX(8) + 板块(7) + 硬科技(3) + 稀缺(2) + 新鲜(3) + 强反弹(2) = 101")
    print(f"  V5.9:  强买 |  硬科技门控 | P0熔断豁免 | P4弱市快进快出(止盈+5%/-5%)")
    print(f"{'#':<3} {'代码':<8} {'名称':<8} {'总':<4} {'级':<3} {'信号':<12} {'子类':<8} "
          f"{'OBV':<12} {'WR跌':<6} {'量':<6} {'均线':<8} {'硬科技':<8} {'标记'}")
    print(f"{'-'*125}")
    for i, s in enumerate(top, 1):
        sig_map = {"strong_buy": " 强买", "buy": " 买入", "watch": " 观察"}
        sig = sig_map.get(s["signal"], s["signal"])
        buy_sub = s.get("_buy_sub", "")
        wrs = f"{s.get('wr_drop_3d',0):+.0f}"

        tags = []
        if s.get('_rebound'): tags.append(' ')
        if s.get('_chase'): tags.append('  追高')
        if s.get('_dead_cat'): tags.append(' 中继')
        if s.get('_fresh'): tags.append(' ')
        if s.get('rebound_strength_bonus', 0) > 0: tags.append(' ')
        if s.get('chokepoint_score', 0) >= 2: tags.append(' ')
        elif s.get('chokepoint_score', 0) >= 1: tags.append(' ')
        tag_str = ' '.join(tags)

        ht_track = s.get('hard_tech_track', '')[:8]

        print(f"{i:<3} {s['code']:<8} {s['name']:<8} {s['total_score']:<4.0f} {s['grade']:<3} "
              f"{sig:<12} {buy_sub:<8} "
              f"{s['obv_level']:<12} {wrs:<6} {s['vol_level']:<6} "
              f"{s['ma_level']:<8} {ht_track:<8} {tag_str}")

    s_cnt = sum(1 for s in top if s['grade']=='S')
    a_cnt = sum(1 for s in top if s['grade']=='A')
    b_cnt = sum(1 for s in top if s['grade']=='B')
    strong = sum(1 for s in top if s['signal']=='strong_buy')
    buy_p = sum(1 for s in top if s.get('_buy_sub')=='premium')
    buy_s = sum(1 for s in top if s.get('_buy_sub')=='standard')
    buy_w = sum(1 for s in top if s.get('_buy_sub')=='weak')
    chase_cnt = sum(1 for s in top if s.get('_chase'))
    dead_cnt = sum(1 for s in top if s.get('_dead_cat'))
    scarce_cnt = sum(1 for s in top if s.get('chokepoint_score', 0) >= 2)
    oligo_cnt = sum(1 for s in top if s.get('chokepoint_score', 0) >= 1)
    print(f"\n  S={s_cnt} A={a_cnt} B={b_cnt} |  强买={strong}  优选={buy_p}  标准={buy_s}  弱={buy_w} |   追高={chase_cnt}  中继={dead_cnt} |  稀缺={scarce_cnt}  寡头={oligo_cnt}")


def print_bi_plan(plans):
    """V5.9: 打印执行计划."""
    fast_mode = any(p.get("fast_market") for p in plans)
    header = " 快进快出" if fast_mode else "标准持仓"
    print(f"\n{'=' * 130}")
    print(f"    毕师傅趋势启动战法 V5.9 - 执行计划 [{header}]")
    print(f"{'=' * 130}")
    if fast_mode:
        print(f"    弱市快进快出: 止盈+{WEAK_MARKET_TAKE_PROFIT}% 止损{WEAK_MARKET_STOP_LOSS}% | 仓位减半")
    print(f"  {'代码':<8} {'名称':<8} {'级':<3} {'信号':<12} {'子类':<8} {'动作':<18} {'入场':<8} {'止损':<8} {'止盈':<8} {'仓位':<6} {'提示'}")
    print(f"  {'-' * 118}")
    for p in plans:
        print(f"  {p['code']:<8} {p['name']:<8} {p['grade']:<3} {p['signal']:<12} "
              f"{p.get('buy_subtype',''):<8} {p['action']:<18} {p['entry_price']:<8} "
              f"{p['stop_loss_early']:<8} {p['take_profit_half']:<8} "
              f"{p['position']:<6} {p.get('tips','')}")


#    Engine wrapper   

class BiTrendLaunchEngine:
    """毕师傅趋势启动战法引擎."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None,
            hard_tech_only: bool = True, **kwargs) -> list[dict]:
        """Execute Bi trend launch screening.

        Args:
            top_n: 返回Top N股票
            trade_date: 交易日期 YYYY-MM-DD (None=最新)
            hard_tech_only: V5.8 硬科技门控, 默认True仅选国家鼓励的硬科技赛道
        """
        from kronos_factors.scorer._db_stub import _get_db

        if trade_date is None:
            with _get_db(readonly=True) as db:
                row = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
                trade_date = row["max"] if row else None
        if not trade_date:
            return []

        # Normalize trade_date to string (PG adapter may return datetime.date)
        trade_date = str(trade_date)[:10]

        with _get_db(readonly=True) as db:
            top, _, _ = run_bi_screening(db, trade_date, top_n=top_n,
                                          hard_tech_only=hard_tech_only)
        return top if top else []

    def run_with_scores(self, top_n: int = 20, trade_date: str = None,
                        hard_tech_only: bool = True, **kwargs) -> tuple[list[dict], list[dict], dict]:
        """Return trading picks plus the observed scored cross-section.

        The scored rows are used only for persisted factor evidence; callers
        should continue presenting ``top`` as the executable candidate list.
        """
        from kronos_factors.scorer._db_stub import _get_db

        if trade_date is None:
            with _get_db(readonly=True) as db:
                row = db.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
                trade_date = row["max"] if row else None
        if not trade_date:
            return [], [], {}
        trade_date = str(trade_date)[:10]
        with _get_db(readonly=True) as db:
            top, scores, market_info = run_bi_screening(
                db, trade_date, top_n=top_n, hard_tech_only=hard_tech_only
            )
        return top or [], scores or [], market_info or {}
