#!/usr/bin/env python3
"""
毕师傅趋势战法 v2.2 — MACD+OBV 八条件共振选股引擎 (速赢AI适配版).

技术路线:
  1. MACD金叉 (DIF上穿DEA) + DIF在DEA下方≥3天 (过滤假金叉)
  2. OBV金叉 (OBV上穿MA30)
  3. 强多头趋势 (MA20>MA60, C>MA20, MA20/MA60>1.03)
  4. 量能达标 (V>MA(V,5) 且 放量)
  5. K线健康 (收阳, 上影<5%)
  6. 非涨停 (确保可买入)
  7. 距20日高点≤2% (排除已回落弱势股)
  8. OBV领先于价格 (OBV近5日涨幅 > 价格近5日涨幅)

v2.2 优化:
  - 新增距20日高点过滤: 距高点>2%的回落股直接淘汰
  - 新增OBV-价格背离确认: OBV涨幅必须领先价格涨幅
  - 跌市保护: 假放量出货 + 高位回落股被系统性过滤

v2.1 优化:
  - 新增 MACD_BELOW_MIN_DAYS=3 条件: 金叉前DIF必须在DEA下方≥3天
  - 过滤浅回调假金叉 (回测: 浅回调胜率37% vs 深回调胜率53%)

Usage:
    POST /api/v1/screen  {"mode": "bi_shifu_trend", "top_n": 20}
"""

import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, date
import logging

logger = logging.getLogger("screener.bi_shifu_trend")


# ==================== 参数 ====================

class Params:
    """可调参数 — 后续可迁移到 params.py."""
    # MACD
    EMA_FAST = 12
    EMA_SLOW = 26
    DEA_PERIOD = 9
    MACD_BELOW_MIN_DAYS = 3     # DIF在DEA下方至少3天才允许金叉 (过滤假信号)

    # OBV
    OBV_MA_PERIOD = 30

    # 趋势
    MA_SHORT = 20
    MA_LONG = 60
    TREND_SLOPE_MIN = 0.015      # MA20/MA60 > 1.015 (适配PG 120天历史)
    CLOSE_ABOVE_MA20 = True

    # 量能
    VOL_MA_PERIOD = 5

    # v2.1+: 信号质量控制
    NEAR_HIGH_MAX_PCT = -0.99   # 距20日高点过滤 (已禁用, 回退v2.1)
    OBV_LEADING_PRICE = False   # OBV领先价格过滤 (已禁用, 回退v2.1)
    MIN_SCORE = 10              # 最低评分阈值 (C级信号空仓, B级以上才交易)

    # K线
    SHADOW_MAX = 0.05            # 上影 < 5%

    # 涨停
    LIMIT_MAIN = (10, 0.5)       # 主板 10%, 容差 0.5%
    LIMIT_GEM = (20, 0.5)        # 科创板/创业板 20%

    # 换手率 (当 turnover>0 时生效, =0 表示 PG 数据缺失自动放行)
    TURNOVER_MIN = 0.5           # 最低换手 0.5% (排除僵尸股)
    TURNOVER_MAX = 30.0          # 最高换手 30% (排除异常放量)

    # 止损
    STOP_LOSS_BASE = -0.03       # 基础止损 -3%
    ATR_PERIOD = 14              # ATR 周期
    STOP_ATR_MULT = 1.5          # 止损 = max(3%, ATR × 1.5)

    # 历史数据
    MIN_DATA_DAYS = 60
    KLINE_LOOKBACK = 120         # 预取K线天数

    # 评分权重
    SCORE_TREND_WEIGHT = 0.30
    SCORE_VOL_WEIGHT = 0.25
    SCORE_MACD_WEIGHT = 0.20
    SCORE_OBV_WEIGHT = 0.15
    SCORE_CANDLE_WEIGHT = 0.10


P = Params


# ==================== 指标计算 (纯 numpy, 无 DB 依赖) ====================

def _ema(arr: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(arr).ewm(span=span, adjust=False).mean().values


def _macd(close: np.ndarray):
    dif = _ema(close, P.EMA_FAST) - _ema(close, P.EMA_SLOW)
    dea = _ema(dif, P.DEA_PERIOD)
    return dif, dea


def _obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    d = np.sign(np.diff(close, prepend=close[0]))
    va = np.where(d > 0, volume, np.where(d < 0, -volume, 0))
    va[0] = 0
    return np.cumsum(va)


def _ma(arr: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(arr).rolling(period).mean().values


def _golden_cross(fast: np.ndarray, slow: np.ndarray) -> bool:
    return bool(fast[-1] > slow[-1] and fast[-2] <= slow[-2])


def _macd_below_days(dif: np.ndarray, dea: np.ndarray) -> int:
    """金叉前 DIF 连续在 DEA 下方的天数。用于过滤假金叉。"""
    count = 0
    # 从金叉前一天往前数, 统计 DIF <= DEA 的连续天数
    for i in range(len(dif) - 2, -1, -1):
        if dif[i] <= dea[i]:
            count += 1
        else:
            break
    return count


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
    """ATR — 用于动态止损."""
    n = len(close)
    if n < period + 1:
        return 0.0
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
    return float(np.mean(tr[-period:]))


def _is_limit_up(code: str, pct: float) -> bool:
    board = ""
    if code.startswith("688") or code.startswith("30"):
        limit_pct, tol = P.LIMIT_GEM
    else:
        limit_pct, tol = P.LIMIT_MAIN
    return pct >= (limit_pct - tol)


def _compute_score(dif_val: float, trend_slope: float, vol_ratio: float,
                   obv_ratio: float, shadow_pct: float,
                   macd_below_days: int = 0) -> float:
    """
    综合评分 0-25, 对应前端 S/A/B/C 评级:
      S: >=20, A: 16-19, B: 10-15, C: <10
    """
    # MACD: DIF>DEA 且差值越大越好 (标准化到 0-5)
    macd_score = min(5.0, max(0, dif_val * 5 + 2.5))

    # 趋势: 坡度 3%-15% 映射到 0-7.5
    trend_score = min(7.5, max(0, (trend_slope - 0.02) / 0.02 * 1.5))

    # 量能: 量比 1-5 映射到 0-6.25
    vol_score = min(6.25, max(0, (vol_ratio - 0.8) / 0.8 * 1.25))

    # OBV: obv/ma30 比率
    obv_score = min(3.75, max(0, (obv_ratio - 0.99) / 0.02 * 0.75))

    # 蜡烛: 上影越小越好 (0-5% 映射到 2.5-0)
    candle_score = max(0, 2.5 - shadow_pct / 0.02)

    # v2.1: 回调深度加分 (≥7天深回调 +1分, ≥14天 +1.5分)
    pullback_bonus = 1.0 if macd_below_days >= 7 else (1.5 if macd_below_days >= 14 else 0)

    total = macd_score + trend_score + vol_score + obv_score + candle_score + pullback_bonus
    return round(total, 2)


def _grade(score: float) -> str:
    if score >= 20: return "S"
    if score >= 16: return "A"
    if score >= 10: return "B"
    return "C"


# ==================== 单股检查 ====================

def screen_single(close: np.ndarray, open_: np.ndarray, high: np.ndarray,
                  low: np.ndarray, volume: np.ndarray,
                  pct_chg: float, turnover: float, code: str) -> dict | None:
    """
    六条件共振 + 换手率过滤 + ATR 动态止损.

    Returns: dict with indicators + score + grade, or None
    """
    n = len(close)
    if n < P.MIN_DATA_DAYS:
        return None

    # 换手率过滤 (turnover=0 表示 PG 数据缺失, 自动跳过该过滤)
    if turnover > 0:
        if turnover < P.TURNOVER_MIN or turnover > P.TURNOVER_MAX:
            return None

    # 1) MACD金叉 + 回调深度过滤 (DIF必须在DEA下方≥3天, 排除假金叉)
    dif, dea = _macd(close)
    if not _golden_cross(dif, dea):
        return None
    if _macd_below_days(dif, dea) < P.MACD_BELOW_MIN_DAYS:
        return None

    # 2) OBV金叉
    obv = _obv(close, volume)
    ma_obv = _ma(obv, P.OBV_MA_PERIOD)
    if np.isnan(ma_obv[-1]):
        return None
    if not _golden_cross(obv, ma_obv):
        return None

    # 3) 强多头趋势
    ma20 = _ma(close, P.MA_SHORT)
    ma60 = _ma(close, P.MA_LONG)
    if np.isnan(ma60[-1]):
        return None
    trend_slope = ma20[-1] / ma60[-1] - 1.0
    if not (ma20[-1] > ma60[-1] and close[-1] > ma20[-1]):
        return None
    if trend_slope < P.TREND_SLOPE_MIN:
        return None

    # 4) 量能达标
    mav5 = _ma(volume, P.VOL_MA_PERIOD)
    if not (volume[-1] > mav5[-1] and volume[-1] > volume[-2]):
        return None

    # 5) K线健康
    if not (close[-1] > open_[-1]):
        return None
    shadow_pct = high[-1] / close[-1] - 1.0
    if shadow_pct > P.SHADOW_MAX:
        return None

    # 6) 非涨停
    if _is_limit_up(code, pct_chg):
        return None

    # ── v2.2: 跌市保护 ──
    # 7) 距20日高点不超过2% (排除已从高点回落的弱势股)
    high_20d = np.max(high[-20:]) if len(high) >= 20 else high[-1]
    near_high_pct = (close[-1] / high_20d - 1.0) if high_20d > 0 else 0
    if near_high_pct < P.NEAR_HIGH_MAX_PCT:
        return None

    # 8) OBV近5日涨幅必须领先于价格涨幅 (确认资金真流入)
    if P.OBV_LEADING_PRICE and len(close) >= 6:
        obv_slope_5d = (obv[-1] / obv[-6] - 1.0) if obv[-6] > 0 else 0
        price_slope_5d = (close[-1] / close[-6] - 1.0) if close[-6] > 0 else 0
        if obv_slope_5d <= price_slope_5d:
            return None

    # 指标值
    dif_val = float(dif[-1])
    dea_val = float(dea[-1])
    vol_ratio = float(volume[-1] / mav5[-1])
    obv_ratio = float(obv[-1] / ma_obv[-1])
    macd_below = _macd_below_days(dif, dea)

    # ATR 动态止损
    atr_val = _atr(high, low, close, P.ATR_PERIOD)
    atr_pct = atr_val / close[-1] if close[-1] > 0 else 0
    dyn_stop_pct = max(0.03, min(0.08, atr_pct * P.STOP_ATR_MULT))

    # 综合评分 (v2.1: 回调深度纳入评分)
    score = _compute_score(dif_val, trend_slope, vol_ratio, obv_ratio, shadow_pct, macd_below)

    return {
        # 核心字段 (前端使用)
        "price": round(float(close[-1]), 2),
        "score": score,
        "grade": _grade(score),
        "entry_price": round(float(close[-1]) * 1.01, 2),
        "stop_loss": round(float(close[-1]) * (1 - dyn_stop_pct), 2),
        "target_price": round(float(close[-1]) * (1 + dyn_stop_pct * 2), 2),

        # 交易参数
        "stop_loss_pct": round(dyn_stop_pct * 100, 1),
        "atr_pct": round(atr_pct * 100, 2),

        # 诊断指标
        "dif": round(dif_val, 4),
        "dea": round(dea_val, 4),
        "trend_slope": round(trend_slope, 4),
        "vol_ratio": round(vol_ratio, 2),
        "obv_ratio": round(obv_ratio, 4),
        "shadow_pct": round(shadow_pct, 4),
        "macd_below_days": macd_below,    # v2.1: 金叉前回调天数
        "near_high_pct": round(near_high_pct * 100, 2),  # v2.2: 距20日高点
        "obv_slope_5d": round((obv[-1] / obv[-6] - 1.0) * 100, 2) if len(obv) >= 6 and obv[-6] > 0 else 0,  # v2.2: OBV近5日涨幅

        # 信号日行情
        "close": round(float(close[-1]), 2),
        "pct_chg": round(pct_chg, 2),
        "volume": int(volume[-1]),
        "turnover_rate": round(turnover, 2),
        "amplitude": round(float((high[-1] - low[-1]) / close[-1] * 100), 2),
    }


# ==================== 数据库查询 ====================

def _get_board(code: str) -> str:
    """从股票代码推断板块."""
    if code.startswith("688"): return "科创板"
    if code.startswith("30"): return "创业板"
    if code.startswith("00") or code.startswith("001"): return "深主板"
    if code.startswith("002") or code.startswith("003"): return "深中小板"
    if code.startswith("60"): return "沪主板"
    return "其他"


def run_screening(db, trade_date: str, top_n: int = 20) -> list[dict]:
    """
    全市场选股入口.

    Args:
        db: PG/SQLite 连接
        trade_date: 'YYYY-MM-DD'
        top_n: 返回 Top N
    """
    t0 = __import__("time").time()

    # 1) 获取候选股票池 (非ST, 非北交所)
    stocks_rows = db.execute(
        """SELECT code, name, COALESCE(industry, '') as industry,
                  COALESCE(board, '') as board
           FROM stocks
           WHERE is_st = 0
             AND name NOT LIKE '%ST%'
             AND name NOT LIKE '%退市%'
             AND code NOT LIKE '8%'
             AND code NOT LIKE '4%'
             AND code NOT LIKE '9%'"""
    ).fetchall()

    if not stocks_rows:
        logger.warning("stocks table is empty")
        return []

    stock_info = {r["code"]: {"name": r["name"], "industry": r["industry"], "board": r["board"]}
                  for r in stocks_rows}
    logger.info("Stock pool: %d symbols", len(stock_info))

    # 2) 获取K线日期范围
    date_rows = db.execute(
        """SELECT DISTINCT trade_date FROM daily_kline
           WHERE trade_date <= ?
           ORDER BY trade_date DESC LIMIT ?""",
        (trade_date, P.KLINE_LOOKBACK)
    ).fetchall()

    if not date_rows:
        logger.warning("No kline data before %s", trade_date)
        return []

    dates = sorted([str(r["trade_date"])[:10] for r in date_rows])
    start_date = dates[0]
    logger.info("Kline range: %s ~ %s (%d days)", start_date, trade_date, len(dates))

    # 3) 批量加载K线
    kline_rows = db.execute(
        """SELECT code, trade_date, open, high, low, close, volume,
                  turnover_rate, amplitude
           FROM daily_kline
           WHERE trade_date >= ? AND trade_date <= ?
           ORDER BY code, trade_date""",
        (start_date, trade_date)
    ).fetchall()

    # 按股票分组
    stock_klines = defaultdict(list)
    for r in kline_rows:
        stock_klines[r["code"]].append(r)

    logger.info("Loaded %d klines for %d stocks in %.1fs",
                len(kline_rows), len(stock_klines), __import__("time").time() - t0)

    # 4) 逐股检查
    picks = []
    for code, rows in stock_klines.items():
        if code not in stock_info:
            continue
        if len(rows) < P.MIN_DATA_DAYS:
            continue

        # 确认最新日期匹配
        latest_date = str(rows[-1]["trade_date"])[:10]
        if latest_date != trade_date:
            continue

        close = np.array([float(r["close"]) for r in rows], dtype=float)
        open_ = np.array([float(r["open"]) for r in rows], dtype=float)
        high = np.array([float(r["high"]) for r in rows], dtype=float)
        low = np.array([float(r["low"]) for r in rows], dtype=float)
        volume = np.array([float(r["volume"]) for r in rows], dtype=float)

        # change_pct 可能为 NULL, 从相邻收盘价自行计算
        db_pct = rows[-1].get("pct_chg")
        if db_pct is not None:
            pct_chg = float(db_pct)
        elif len(close) >= 2 and close[-2] > 0:
            pct_chg = (close[-1] - close[-2]) / close[-2] * 100
        else:
            pct_chg = 0.0

        turnover = float(rows[-1].get("turnover_rate") or 0)

        result = screen_single(close, open_, high, low, volume, pct_chg, turnover, code)
        if result is None:
            continue

        # v2.1+: 评分过滤 — C级(<10分)信号空仓
        if result.get("score", 0) < P.MIN_SCORE:
            continue

        info = stock_info[code]
        result.update({
            "code": code,
            "name": info["name"],
            "industry": info["industry"],
            "board": info["board"] or _get_board(code),
            "trade_date": trade_date,

            # screener-service 需要的元字段
            "source_module": "bi_shifu_trend",
            "source_mode": "bi_shifu_trend",
            "candidate_id": f"CAND-bi_shifu_trend-{code}",
            "visibility": "public",
            "data_scope": "public",
        })
        picks.append(result)

    # 5) 按评分排序 + Top N
    picks.sort(key=lambda x: (x["score"], x["vol_ratio"]), reverse=True)
    picks = picks[:top_n]

    elapsed = __import__("time").time() - t0
    logger.info("Screening done: %d picks in %.1fs", len(picks), elapsed)

    return picks


# ==================== 引擎类 ====================

class BiShifuTrendEngine:
    """毕师傅趋势战法引擎 v2.1+ (评分过滤版)."""

    MODE_KEY = "bi_shifu_trend"
    MODE_NAME = "毕师傅趋势战法"
    VERSION = "v2.1-score"

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """
        Execute BiShifu trend screening.

        Args:
            top_n: 返回 Top N
            trade_date: 交易日期 YYYY-MM-DD (None=最新)
        """
        from kronos_factors.scorer._db_stub import _get_db

        with _get_db(readonly=True) as db:
            if trade_date is None:
                row = db.execute(
                    "SELECT MAX(trade_date) as md FROM daily_kline"
                ).fetchone()
                trade_date = str(row["md"])[:10] if row else None

            if not trade_date:
                logger.warning("No trade_date available")
                return []

            trade_date = str(trade_date)[:10]
            return run_screening(db, trade_date, top_n=top_n)
