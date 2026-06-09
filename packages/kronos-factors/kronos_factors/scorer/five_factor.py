"""Five-factor scoring model: M/V/T/Q/R.

Extracted from Kronos/webui/services/screener_service.py
"""

import numpy as np
import pandas as pd


def _calc_rsi(closes: np.ndarray, period: int = 14) -> float:
    """Calculate RSI for the given period."""
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period + 1):])
    gains = np.maximum(deltas, 0)
    losses = np.maximum(-deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    alpha = 2.0 / (period + 1)
    result = np.zeros_like(data)
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _calc_macd_signal(closes: np.ndarray) -> str:
    """Calculate MACD signal: 金叉/死叉/多头/空头."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12 - ema26
    dea = _ema(dif, 9)
    macd_bar = 2 * (dif - dea)

    if dif[-1] > dea[-1] and dif[-2] <= dea[-2]:
        return "金叉"
    elif dif[-1] < dea[-1] and dif[-2] >= dea[-2]:
        return "死叉"
    elif dif[-1] > dea[-1]:
        return "多头"
    else:
        return "空头"


def _empty_scores() -> dict:
    """Return empty/neutral scores."""
    return {
        "momentum": 0, "volume_factor": 0, "technical": 0,
        "quality": 0, "risk": 0, "score": 0, "grade": "C",
    }


def score_five_factor(kline_df: pd.DataFrame) -> dict:
    """Calculate M/V/T/Q/R five-factor scores for a single stock.

    Args:
        kline_df: DataFrame with columns [open, high, low, close,
                  volume, amount]. Must have ≥ 20 rows.

    Returns:
        {"momentum": float, "volume_factor": float, "technical": float,
         "quality": float, "risk": float, "score": float, "grade": str}
    """
    closes = kline_df["close"].values
    volumes = kline_df["volume"].values
    if len(closes) < 5:
        return _empty_scores()

    price = closes[-1]
    prev_close = closes[-2] if len(closes) >= 2 else price
    daily = (price / prev_close - 1) * 100 if prev_close > 0 else 0

    # -- M: Momentum (0~8) --
    momentum = 0.0
    if daily > 0:
        momentum += min(3.0, daily / 2)
    if len(closes) >= 5:
        chg_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0
        if chg_5d > 0:
            momentum += min(2.0, chg_5d / 3)
    if len(closes) >= 10:
        chg_10d = (closes[-1] / closes[-10] - 1) * 100 if closes[-10] > 0 else 0
        if chg_10d > 0:
            momentum += min(1.5, chg_10d / 5)
    if len(closes) >= 60:
        ma5 = np.mean(closes[-5:])
        ma10 = np.mean(closes[-10:])
        ma20 = np.mean(closes[-20:])
        if ma5 > ma10 > ma20:
            momentum += 2.0
        elif ma5 < ma10 < ma20:
            momentum -= 1.0
    momentum = max(0, min(8, round(momentum, 1)))

    # -- V: Volume (0~7) --
    volume_score = 0.0
    amount = kline_df["amount"].values[-1] if "amount" in kline_df.columns else 0
    turnover = 0.0
    if "turnover_rate" not in kline_df.columns:
        turnover = volumes[-1] / 5e9 * 100 if volumes[-1] > 0 else 1.0
        turnover = min(30, max(0.1, turnover))
    else:
        turnover = kline_df["turnover_rate"].values[-1]

    if 3 <= turnover <= 15:
        volume_score += 2
    elif turnover > 15:
        volume_score += 1
    if amount >= 1e9:
        volume_score += 2
    elif amount >= 2e8:
        volume_score += 1
    if len(volumes) >= 10:
        vol_ma5 = np.mean(volumes[-5:])
        vol_ma10 = np.mean(volumes[-10:])
        if vol_ma5 > vol_ma10 * 1.2 and daily >= 0:
            volume_score += 2
        elif vol_ma5 > vol_ma10 * 1.2 and daily < 0:
            volume_score -= 1
    volume_score = max(0, min(7, round(volume_score, 1)))

    # -- T: Technical (0~5) --
    technical = 0.0
    if len(closes) >= 15:
        rsi14 = _calc_rsi(closes, 14)
        if 35 <= rsi14 <= 65:
            technical += 1.5
        elif rsi14 >= 75 or rsi14 <= 25:
            technical -= 1.0
    if len(closes) >= 20:
        support = np.min(closes[-20:])
        resistance = np.max(closes[-20:])
        if price > support:
            technical += 1.0
        if resistance > 0 and price >= resistance * 0.98:
            technical -= 0.5
    if len(closes) >= 35:
        macd_sig = _calc_macd_signal(closes)
        if macd_sig in ("金叉", "多头"):
            technical += 2.0
        elif macd_sig in ("死叉", "空头"):
            technical -= 1.0
    if len(kline_df) >= 2:
        amp = (kline_df["high"].values[-1] / kline_df["low"].values[-1] - 1) * 100
        if 2 <= amp <= 6:
            technical += 0.5
    technical = max(0, min(5, round(technical, 1)))

    # -- Q: Quality (0~3) --
    quality = 0.0
    if len(closes) >= 100:
        percentile = (closes[-1] - np.min(closes[-100:])) / (
            np.max(closes[-100:]) - np.min(closes[-100:]) + 1e-8
        )
        if 0.2 <= percentile <= 0.8:
            quality += 1.0
    if amount > 0 and daily != 0:
        efficiency = abs(daily) / (amount / 1e9 + 1) * 100
        if efficiency > 0.5:
            quality += 1.0
    quality = max(0, min(3, round(quality, 1)))

    # -- R: Risk (-3~0) --
    risk = 0.0
    if len(kline_df) >= 2:
        amp = (kline_df["high"].values[-1] / kline_df["low"].values[-1] - 1) * 100
        if amp > 10:
            risk -= 1.5
        elif amp <= 6:
            risk += 0.5
    if turnover > 25:
        risk -= 1.0
    if len(closes) >= 15:
        rsi14 = _calc_rsi(closes, 14)
        if rsi14 >= 75:
            risk -= 1.0
    risk = max(-3, min(0, round(risk, 1)))

    score = round(momentum + volume_score + technical + quality + risk, 1)
    score = max(0, min(25, score))
    grade = "S" if score >= 16 else ("A" if score >= 12 else ("B" if score >= 7 else "C"))

    return {
        "momentum": momentum,
        "volume_factor": volume_score,
        "technical": technical,
        "quality": quality,
        "risk": risk,
        "score": score,
        "grade": grade,
    }
