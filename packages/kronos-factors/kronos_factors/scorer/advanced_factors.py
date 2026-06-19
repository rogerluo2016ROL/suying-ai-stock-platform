"""Advanced stock selection models — all computed from OHLCV, no external API.

Models:
  1. MoneyFlowModel  — 资金流向 (MFI + OBV trend + volume-price divergence)
  2. MeanReversionModel — 均值回归 (Bollinger %B + RSI extreme + MA deviation)
  3. TrendStrengthModel — 趋势强度 (ADX + DI + MA divergence)
  4. TrendLaunchModel — 趋势启动 (OBV均线确认 + WR急跌回踩)
"""
import math
import numpy as np
import pandas as pd


# ═══════════════════════════════════════════════════════════════
# Model 1: 资金流向
# ═══════════════════════════════════════════════════════════════

def score_money_flow(df: pd.DataFrame) -> dict:
    """Compute money flow score (0~10).

    Components:
      - MFI (Money Flow Index): volume-weighted RSI
      - OBV trend: On-Balance Volume slope
      - Volume-Price Divergence: price up + vol down = bearish

    Returns:
      {"score": 0~10, "signal": "inflow"/"neutral"/"outflow",
       "mfi": float, "obv_trend": str, "divergence": str}
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    if len(closes) < 20:
        return {"score": 5.0, "signal": "neutral", "mfi": 50,
                "obv_trend": "数据不足", "divergence": "数据不足"}

    score = 5.0  # baseline

    # --- MFI (14-period) ---
    typical = (highs + lows + closes) / 3
    money_flow = typical * volumes
    mfi_period = 14
    pos_flow = np.zeros(len(closes))
    neg_flow = np.zeros(len(closes))

    for i in range(1, len(closes)):
        if typical[i] > typical[i-1]:
            pos_flow[i] = money_flow[i]
        else:
            neg_flow[i] = money_flow[i]

    mfi_values = []
    for i in range(mfi_period, len(closes)):
        pos_sum = pos_flow[i-mfi_period+1:i+1].sum()
        neg_sum = neg_flow[i-mfi_period+1:i+1].sum()
        mfi = 100 - (100 / (1 + pos_sum/(neg_sum + 1e-10)))
        mfi_values.append(mfi)

    mfi = float(np.mean(mfi_values[-5:])) if mfi_values else 50.0

    if mfi > 80:
        score -= 2.0  # overbought outflow signal
        mfi_signal = "超买流出"
    elif mfi > 60:
        score += 1.5  # strong inflow
        mfi_signal = "资金流入"
    elif mfi < 20:
        score += 2.5  # oversold accumulation
        mfi_signal = "超卖吸筹"
    elif mfi < 40:
        score -= 1.5  # weak outflow
        mfi_signal = "资金流出"
    else:
        mfi_signal = "平衡"

    # --- OBV Trend ---
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]

    # OBV 10-day slope
    if len(obv) >= 15:
        obv_slope = (obv[-1] - obv[-10]) / (abs(obv[-10]) + 1)
        if obv_slope > 0.02:
            obv_trend = "↑ 持续流入"
            score += 1.5
        elif obv_slope < -0.02:
            obv_trend = "↓ 持续流出"
            score -= 1.5
        else:
            obv_trend = "→ 持平"
    else:
        obv_trend = "数据不足"

    # --- Volume-Price Divergence ---
    if len(closes) >= 5:
        price_chg_5 = (closes[-1] / closes[-5] - 1) * 100
        vol_chg_5 = (volumes[-5:].mean() / volumes[-10:-5].mean() - 1) * 100 if len(volumes) >= 10 else 0

        if price_chg_5 > 3 and vol_chg_5 < -20:
            divergence = "⚠️ 价涨量缩 (背离)"
            score -= 1.5
        elif price_chg_5 < -3 and vol_chg_5 > 20:
            divergence = "💡 价跌量增 (承接)"
            score += 1.5
        elif price_chg_5 > 0 and vol_chg_5 > 0:
            divergence = "✅ 量价配合"
            score += 1.0
        else:
            divergence = "正常"
    else:
        divergence = "数据不足"

    score = max(0, min(10, round(score, 1)))

    if score >= 7:
        signal = "inflow"
    elif score <= 3:
        signal = "outflow"
    else:
        signal = "neutral"

    return {"score": score, "signal": signal, "mfi": round(mfi, 1),
            "obv_trend": obv_trend, "divergence": divergence}


# ═══════════════════════════════════════════════════════════════
# Model 2: 均值回归
# ═══════════════════════════════════════════════════════════════

def score_mean_reversion(df: pd.DataFrame) -> dict:
    """Compute mean reversion score (0~10). Higher = oversold, likely to revert up.

    Components:
      - Bollinger %B: position within Bollinger Bands
      - RSI extreme: extremely oversold = bullish reversal signal
      - MA20 deviation: how far below MA20

    Returns:
      {"score": 0~10, "signal": "oversold"/"neutral"/"overbought",
       "bb_pct_b": float, "rsi": float, "ma20_deviation_pct": float}
    """
    closes = df["close"].values
    if len(closes) < 30:
        return {"score": 5.0, "signal": "neutral",
                "bb_pct_b": 0.5, "rsi": 50, "ma20_deviation_pct": 0}

    price = closes[-1]

    # --- Bollinger %B ---
    ma20 = np.mean(closes[-20:])
    std20 = np.std(closes[-20:])
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    bb_pct_b = (price - bb_lower) / (bb_upper - bb_lower + 1e-10)
    bb_pct_b = max(0, min(1, bb_pct_b))

    # --- RSI-14 ---
    deltas = np.diff(closes[-15:])
    gains = np.maximum(deltas, 0).sum()
    losses = -np.minimum(deltas, 0).sum()
    rsi = float(100 - 100 / (1 + gains/(losses + 1e-10)))

    # --- MA20 Deviation ---
    ma20_dev = (price / ma20 - 1) * 100

    # Scoring
    score = 5.0

    # Bollinger: low %B = oversold = bullish reversal chance
    if bb_pct_b < 0.1:
        score += 3.0
        bb_signal = "下轨超卖"
    elif bb_pct_b < 0.3:
        score += 1.5
        bb_signal = "偏低"
    elif bb_pct_b > 0.9:
        score -= 2.0
        bb_signal = "上轨超买"
    elif bb_pct_b > 0.7:
        score -= 1.0
        bb_signal = "偏高"
    else:
        bb_signal = "中位"

    # RSI extreme
    if rsi < 25:
        score += 3.0
        rsi_signal = "超卖"
    elif rsi < 35:
        score += 1.5
        rsi_signal = "偏弱"
    elif rsi > 75:
        score -= 2.5
        rsi_signal = "超买"
    elif rsi > 65:
        score -= 1.0
        rsi_signal = "偏强"
    else:
        rsi_signal = "正常"

    # MA20 deviation: far below MA = mean reversion potential
    if ma20_dev < -15:
        score += 2.0
    elif ma20_dev < -8:
        score += 1.0
    elif ma20_dev > 15:
        score -= 2.0
    elif ma20_dev > 8:
        score -= 1.0

    score = max(0, min(10, round(score, 1)))

    if score >= 7:
        signal = "oversold"
    elif score <= 3:
        signal = "overbought"
    else:
        signal = "neutral"

    return {"score": score, "signal": signal,
            "bb_pct_b": round(bb_pct_b, 2),
            "rsi": round(rsi, 1),
            "ma20_deviation_pct": round(ma20_dev, 1)}


# ═══════════════════════════════════════════════════════════════
# Model 3: 趋势强度
# ═══════════════════════════════════════════════════════════════

def score_trend_strength(df: pd.DataFrame) -> dict:
    """Compute trend strength score (0~10). Higher = stronger uptrend.

    Components:
      - ADX (Average Directional Index): trend strength regardless of direction
      - +DI / -DI: directional indicators
      - MA divergence: how spread apart are MAs (trend strength proxy)
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    if len(closes) < 30:
        return {"score": 5.0, "signal": "neutral",
                "adx": 0, "di_plus": 0, "di_minus": 0, "trend_dir": "数据不足"}

    price = closes[-1]
    period = 14

    # --- ADX Calculation ---
    tr = np.zeros(len(closes))
    plus_dm = np.zeros(len(closes))
    minus_dm = np.zeros(len(closes))

    for i in range(1, len(closes)):
        tr[i] = max(highs[i]-lows[i],
                     abs(highs[i]-closes[i-1]),
                     abs(lows[i]-closes[i-1]))
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0

    # Smooth with Wilder's method
    atr = np.zeros(len(closes))
    atr[period] = tr[1:period+1].mean()
    for i in range(period+1, len(closes)):
        atr[i] = (atr[i-1] * (period-1) + tr[i]) / period

    smooth_pdm = np.zeros(len(closes))
    smooth_mdm = np.zeros(len(closes))
    smooth_pdm[period] = plus_dm[1:period+1].sum()
    smooth_mdm[period] = minus_dm[1:period+1].sum()
    for i in range(period+1, len(closes)):
        smooth_pdm[i] = (smooth_pdm[i-1] * (period-1) + plus_dm[i]) / period
        smooth_mdm[i] = (smooth_mdm[i-1] * (period-1) + minus_dm[i]) / period

    di_plus = np.zeros(len(closes))
    di_minus = np.zeros(len(closes))
    adx = np.zeros(len(closes))

    for i in range(period, len(closes)):
        if atr[i] > 0:
            di_plus[i] = 100 * smooth_pdm[i] / atr[i]
            di_minus[i] = 100 * smooth_mdm[i] / atr[i]
        dx = 100 * abs(di_plus[i] - di_minus[i]) / (di_plus[i] + di_minus[i] + 1e-10)
        if i == period:
            adx[i] = dx
        else:
            adx[i] = (adx[i-1] * (period-1) + dx) / period

    adx_val = float(adx[-1]) if adx[-1] > 0 else float(np.mean(adx[-5:]))
    di_p = float(di_plus[-1])
    di_m = float(di_minus[-1])

    # --- MA Divergence (trend strength proxy) ---
    ma5 = np.mean(closes[-5:])
    ma10 = np.mean(closes[-10:])
    ma20 = np.mean(closes[-20:])
    ma_divergence = (max(ma5, ma10, ma20) / min(ma5, ma10, ma20) - 1) * 100

    # --- Scoring ---
    score = 5.0

    # ADX: trend strength
    if adx_val > 40:
        score += 1.5 if di_p > di_m else -0.5  # strong trend, reward uptrend
    elif adx_val > 25:
        score += 1.0 if di_p > di_m else -0.5
    elif adx_val < 20:
        score -= 1.0  # no trend = sideways risk

    # Directional: DI+ vs DI-
    if di_p > di_m:
        trend_dir = "up"
        di_ratio = di_p / (di_m + 1e-10)
        if di_ratio > 2:
            score += 2.0  # strong upward bias
        elif di_ratio > 1.3:
            score += 1.0
    else:
        trend_dir = "down"
        di_ratio = di_m / (di_p + 1e-10)
        if di_ratio > 2:
            score -= 2.0
        elif di_ratio > 1.3:
            score -= 1.0

    # MA divergence: wider spread = stronger trend
    if ma_divergence > 10:
        score += 1.0 if di_p > di_m else -1.5
    elif ma_divergence > 5:
        score += 0.5 if di_p > di_m else -0.5

    # Price vs MA20: basic trend filter
    if price > ma20:
        score += 1.0
    else:
        score -= 1.5
    if price > ma10:
        score += 0.5

    score = max(0, min(10, round(score, 1)))

    if score >= 7:
        signal = "strong_uptrend"
    elif score >= 5:
        signal = "uptrend"
    elif score <= 3:
        signal = "downtrend"
    else:
        signal = "neutral"

    return {"score": score, "signal": signal,
            "adx": round(adx_val, 1),
            "di_plus": round(di_p, 1),
            "di_minus": round(di_m, 1),
            "trend_dir": trend_dir}


# ═══════════════════════════════════════════════════════════════
# Model 3.5: 趋势启动检测 (OBV 均线确认 + WR 急跌回踩)
# ═══════════════════════════════════════════════════════════════

def score_trend_launch(df: pd.DataFrame) -> dict:
    """Detect trend initiation — OBV above MA confirms uptrend, WR sudden drop = pullback entry.

    核心逻辑:
      1. OBV > OBV_MA (10日): 资金持续流入, 趋势方向确认
      2. WR 急跌 (1-3日从 -20→-60 以下): 价格快速回踩, 洗盘非反转
      3. 两者叠加 = "上升趋势中的洗盘回踩" → 高胜率买入信号

    Components:
      - OBV vs OBV_10MA: 资金方向确认
      - OBV 持续天数: 趋势稳固度
      - WR 急跌幅度: 回踩深度
      - 量价配合: 回踩是否缩量 (洗盘特征)

    Returns:
      {"score": 0~10, "signal": "strong_buy"/"buy"/"watch"/"no_signal",
       "obv_above_ma": bool, "obv_days_above": int,
       "wr_current": float, "wr_drop_pct": float, "volume_contract": bool}
    """
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    if len(closes) < 30:
        return {"score": 5.0, "signal": "no_signal",
                "obv_above_ma": False, "obv_days_above": 0,
                "wr_current": -50, "wr_drop_pct": 0, "volume_contract": False}

    # ── 1. OBV 计算 ──
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv[i] = obv[i-1] + volumes[i]
        elif closes[i] < closes[i-1]:
            obv[i] = obv[i-1] - volumes[i]
        else:
            obv[i] = obv[i-1]

    # OBV 10日/20日均线
    obv_ma10 = np.convolve(obv, np.ones(10)/10, mode='valid')
    obv_ma20 = np.convolve(obv, np.ones(20)/20, mode='valid')

    if len(obv_ma10) < 5:
        return {"score": 5.0, "signal": "no_signal",
                "obv_above_ma": False, "obv_days_above": 0,
                "wr_current": -50, "wr_drop_pct": 0, "volume_contract": False}

    # OBV 是否高于 MA10
    obv_now = obv[-1]
    obv_ma10_now = obv_ma10[-1]
    obv_above = obv_now > obv_ma10_now

    # OBV 持续高于 MA 的天数 (趋势稳固度)
    obv_days_above = 0
    for i in range(len(obv)-1, -1, -1):
        ma_idx = i - 10 + 1
        if ma_idx >= 0 and obv[i] > obv_ma10[ma_idx]:
            obv_days_above += 1
        else:
            break

    # ── 2. WR (威廉指标) 计算 ──
    def calc_wr(period=14):
        """Williams %R: (highest_high - close) / (highest_high - lowest_low) * -100"""
        wr_values = []
        for i in range(period-1, len(closes)):
            hh = np.max(highs[i-period+1:i+1])
            ll = np.min(lows[i-period+1:i+1])
            if hh - ll > 0:
                wr = (hh - closes[i]) / (hh - ll) * -100
            else:
                wr = -50
            wr_values.append(wr)
        return np.array(wr_values)

    wr14 = calc_wr(14)

    if len(wr14) < 5:
        return {"score": 5.0, "signal": "no_signal",
                "obv_above_ma": obv_above, "obv_days_above": obv_days_above,
                "wr_current": -50, "wr_drop_pct": 0, "volume_contract": False}

    wr_now = float(wr14[-1])
    wr_3d_ago = float(wr14[-4]) if len(wr14) >= 4 else wr_now
    wr_5d_ago = float(wr14[-6]) if len(wr14) >= 6 else wr_now

    # WR 急跌幅度: 3日内从高位跌了多少
    wr_drop_3d = wr_now - wr_3d_ago  # 负数 = 急跌
    wr_drop_5d = wr_now - wr_5d_ago

    # ── 3. 量价配合: 回踩是否缩量 ──
    vol_recent_3 = np.mean(volumes[-3:]) if len(volumes) >= 3 else volumes[-1]
    vol_prev_10 = np.mean(volumes[-13:-3]) if len(volumes) >= 13 else vol_recent_3
    vol_contract = vol_recent_3 < vol_prev_10 * 0.8  # 缩量20%+

    # ── 4. 综合评分 ──
    score = 5.0

    # OBV 趋势得分
    if obv_above:
        if obv_days_above >= 15:
            score += 2.5   # OBV 持续15天+高于均线 → 趋势非常稳固
            obv_strength = "极强"
        elif obv_days_above >= 10:
            score += 2.0
            obv_strength = "强"
        elif obv_days_above >= 5:
            score += 1.5
            obv_strength = "中等"
        else:
            score += 0.5
            obv_strength = "刚突破"
    else:
        score -= 1.0       # OBV 低于均线 → 资金未确认流入
        obv_strength = "弱势"

    # WR 急跌得分 (核心信号)
    if wr_drop_3d < -30:
        score += 2.5       # 3日急跌30%+ → 深度回踩, 洗盘充分
        wr_signal = "深度洗盘"
    elif wr_drop_3d < -20:
        score += 2.0       # 3日跌20-30% → 明显回踩
        wr_signal = "明显回踩"
    elif wr_drop_3d < -10:
        score += 1.5       # 温和回踩
        wr_signal = "温和回踩"
    elif wr_drop_5d < -15:
        score += 1.0       # 5日级别缓跌 → 慢洗
        wr_signal = "缓跌洗盘"
    else:
        wr_signal = "无急跌"

    # WR 当前位置得分
    if wr_now < -80:
        score += 1.0       # 超卖区 → 反弹概率高
        wr_zone = "超卖区"
    elif wr_now < -60:
        score += 0.5       # 偏弱区 → 回踩到位
        wr_zone = "回踩区"
    elif wr_now < -40:
        wr_zone = "中性区"
    elif wr_now < -20:
        score -= 0.5       # 仍在高位 → 可能没跌够
        wr_zone = "偏强区"
    else:
        score -= 1.0       # 超买区 → 太高了
        wr_zone = "超买区"

    # 量价配合: 缩量回踩 = 洗盘非出货
    if vol_contract and wr_drop_3d < -10:
        score += 1.0       # 缩量回踩 → 主力没走
    elif not vol_contract and wr_drop_3d < -10:
        score -= 0.5       # 放量下跌 → 可能真出货

    # 趋势 + 回踩 共振加分
    if obv_days_above >= 10 and wr_drop_3d < -20:
        score += 1.5       # 强趋势 + 深回踩 = 最佳买点
        resonance = "🟢 完美共振"
    elif obv_days_above >= 5 and wr_drop_3d < -10:
        score += 0.5
        resonance = "🟡 有效共振"
    else:
        resonance = "⚪ 无共振"

    score = max(0, min(10, round(score, 1)))

    # ── 5. 信号判定 ──
    if score >= 8:
        signal = "strong_buy"       # 趋势稳固 + 深度回踩 → 强买
    elif score >= 6.5:
        signal = "buy"              # 趋势确认 + 回踩 → 可买
    elif score >= 5:
        signal = "watch"            # 趋势或回踩单边满足 → 观望等确认
    else:
        signal = "no_signal"

    return {
        "score": score, "signal": signal,
        "obv_above_ma": obv_above, "obv_days_above": obv_days_above,
        "obv_strength": obv_strength,
        "wr_current": round(wr_now, 1), "wr_drop_3d": round(wr_drop_3d, 1),
        "wr_signal": wr_signal, "wr_zone": wr_zone,
        "volume_contract": vol_contract, "resonance": resonance,
    }


# ═══════════════════════════════════════════════════════════════
# Model 4: 反转效应 (Reversal Factor)
# ═══════════════════════════════════════════════════════════════

def score_reversal(df: pd.DataFrame) -> dict:
    """Compute short-term reversal score (0~10). Higher = stronger reversal signal.

    A-share specific: stocks with large 5-day drops tend to rebound.
    Behavioral finance: overreaction → mean reversion in 5-10 days.

    Components:
      - 5-day return: most negative = strongest reversal signal
      - 10-day return with 5-day filter: if 10d down but 5d stabilizing
      - Intraday reversal: open low but close high = bullish reversal
    """
    closes = df["close"].values
    opens = df["open"].values

    if len(closes) < 10:
        return {"score": 5.0, "signal": "neutral", "ret_5d": 0, "ret_10d": 0}

    price = closes[-1]
    ret_5d = (closes[-1] / closes[-5] - 1) * 100 if closes[-5] > 0 else 0
    ret_10d = (closes[-1] / closes[-10] - 1) * 100 if closes[-10] > 0 else 0
    ret_20d = (closes[-1] / closes[-20] - 1) * 100 if len(closes) >= 20 and closes[-20] > 0 else 0

    # Intraday reversal: today's open→close direction
    intraday = ((closes[-1] / opens[-1] - 1) * 100) if opens[-1] > 0 else 0

    score = 5.0

    # Strong 5-day drop → strong reversal signal
    if ret_5d < -15:
        score += 3.5
        signal = "深度超跌"
    elif ret_5d < -10:
        score += 2.5
        signal = "超跌"
    elif ret_5d < -5:
        score += 1.5
        signal = "偏弱"
    elif ret_5d < -2:
        score += 0.5
        signal = "小幅回调"
    elif ret_5d > 15:
        score -= 3.0
        signal = "极度超买"
    elif ret_5d > 10:
        score -= 2.0
        signal = "超买"
    elif ret_5d > 5:
        score -= 1.0
        signal = "偏强"
    else:
        signal = "正常"
        score += 1.0  # slight baseline lift for normal-range stocks

    # 10-day vs 5-day: stabilizing after big drop = extra bullish
    if ret_10d < -15 and ret_5d > -5:
        score += 2.0  # was crashing, now stabilizing

    # Intraday reversal: down premarket but strong recovery during day
    if intraday > 2 and ret_5d < -3:
        score += 1.5  # strong intraday reversal after recent weakness

    # 20-day context: falling into support zone
    if ret_20d < -20:
        score += 1.0  # extremely oversold on longer timeframe

    score = max(0, min(10, round(score, 1)))

    return {
        "score": score, "signal": signal,
        "ret_5d": round(ret_5d, 1), "ret_10d": round(ret_10d, 1),
        "intraday_chg": round(intraday, 2),
    }


# ═══════════════════════════════════════════════════════════════
# Model 5: 流动性因子 (Liquidity Factor)
# ═══════════════════════════════════════════════════════════════

def score_liquidity(df: pd.DataFrame) -> dict:
    """Compute liquidity score (0~10). Higher = healthier liquidity.

    Components:
      - Amihud illiquidity: |return| / amount → lower = more liquid
      - Turnover stability: CV of turnover over 20 days
      - Volume consistency: avoid "zombie stocks" with erratic volume

    A-share specific: filter out extreme low-liquidity (illiquid) AND
    extreme high-liquidity (pump-and-dump) stocks.
    """
    closes = df["close"].values
    volumes = df["volume"].values
    amounts = df["amount"].values if "amount" in df.columns else volumes * closes

    if len(closes) < 20:
        return {"score": 5.0, "signal": "neutral", "amihud": 0}

    # Amihud illiquidity (daily avg over 20 days, normalized)
    illiq_values = []
    for i in range(max(1, len(closes)-20), len(closes)):
        ret = abs((closes[i] / closes[i-1] - 1)) if closes[i-1] > 0 else 0
        amt = amounts[i] if amounts[i] > 0 else 1e8  # raw amount in yuan
        illiq_values.append(ret / (amt + 1) * 1e8)  # Amihud × 10^8 for readability

    amihud = float(np.mean(illiq_values))  # higher = less liquid

    # Turnover stability
    turnover_vals = []
    for i in range(max(1, len(closes)-20), len(closes)):
        t = volumes[i] / 1e8 if volumes[i] > 0 else 0.01  # rough turnover proxy
        turnover_vals.append(t)

    turnover_mean = np.mean(turnover_vals)
    turnover_std = np.std(turnover_vals)
    turnover_cv = turnover_std / (turnover_mean + 1e-10)  # coefficient of variation

    # Recent volume vs historical average
    recent_vol = np.mean(volumes[-5:])
    hist_vol = np.mean(volumes[-20:])
    vol_ratio = recent_vol / (hist_vol + 1)

    score = 5.0

    # Amihud: lower = more liquid. Values ~1-100 for liquid, 100-1000 normal, >5000 illiquid
    log_a = math.log(max(amihud, 0.1))
    if log_a < 2:        # amihud < 7: very liquid
        score += 3.0
    elif log_a < 3.5:    # amihud < 33: liquid
        score += 2.0
    elif log_a < 5:      # amihud < 148: normal
        score += 1.0
    elif log_a > 8:      # amihud > 2980: extremely illiquid
        score -= 3.0
    elif log_a > 7:      # amihud > 1096: very illiquid
        score -= 2.0
    elif log_a > 6:      # amihud > 403: illiquid
        score -= 1.0

    # Turnover stability
    if turnover_cv < 0.3:
        score += 1.5  # very stable
    elif turnover_cv < 0.6:
        score += 0.5
    elif turnover_cv > 1.5:
        score -= 1.5  # erratic = pump-and-dump risk

    # Recent volume: active but not crazy
    if 0.8 <= vol_ratio <= 1.5:
        score += 1.0
    elif vol_ratio > 3:
        score -= 2.0  # sudden volume spike
    elif vol_ratio < 0.3:
        score -= 2.0  # volume dried up

    score = max(0, min(10, round(score, 1)))

    if score >= 7:
        signal = "liquid"
    elif score <= 3:
        signal = "illiquid"
    else:
        signal = "normal"

    return {
        "score": score, "signal": signal,
        "amihud": round(amihud, 4),
        "turnover_cv": round(turnover_cv, 2),
        "vol_ratio": round(vol_ratio, 2),
    }


# ═══════════════════════════════════════════════════════════════
# Multi-Model Voting
# ═══════════════════════════════════════════════════════════════

def run_multi_model(df: pd.DataFrame, code: str,
                    nlp_result: dict = None) -> dict:
    """Run all 6 models on a single stock and return voting result.

    Returns:
      {"models": {name: score}, "buy_votes": int, "total_votes": int,
       "signal": str, "confidence": str}
    """
    ff = score_five_factor(df)
    mr = score_mean_reversion(df)
    mf = score_money_flow(df)
    ts = score_trend_strength(df)

    # NLP if available
    nlp_impact = 0
    if nlp_result and nlp_result.get("has_news"):
        nlp_impact = nlp_result.get("impact_score", 0)

    # Kronos placeholder (computed separately)
    kronos_bull = 0  # set by caller

    models = {
        "五因子综合": ff["score"],
        "均值回归": mr["score"],
        "资金流向": mf["score"],
        "趋势强度": ts["score"],
    }

    # Voting: each model votes buy if score > 6 (out of 10)
    buy_votes = sum(1 for s in models.values() if s > 6)
    total_votes = len(models)

    # NLP bonus vote
    if nlp_impact >= 5:
        buy_votes += 1
        total_votes += 1
        models["NLP语义"] = 8.0
    elif nlp_impact <= -5:
        total_votes += 1
        models["NLP语义"] = 2.0

    vote_ratio = buy_votes / total_votes

    if vote_ratio >= 0.8:
        signal = "🔥 强烈买入"
        confidence = "高"
    elif vote_ratio >= 0.6:
        signal = "✔️ 买入"
        confidence = "中"
    elif vote_ratio >= 0.4:
        signal = "⏳ 观望"
        confidence = "低"
    else:
        signal = "❌ 规避"
        confidence = "高"

    return {
        "models": models,
        "details": {
            "five_factor": ff,
            "mean_reversion": mr,
            "money_flow": mf,
            "trend_strength": ts,
        },
        "buy_votes": buy_votes,
        "total_votes": total_votes,
        "vote_ratio": round(vote_ratio, 2),
        "signal": signal,
        "confidence": confidence,
    }


# Import five-factor (avoid circular) — uses local package import
from kronos_factors.scorer.five_factor import score_five_factor  # noqa: E402


# ═══════════════════════════════════════════════════════════════
# Tushare-powered scoring models
# ═══════════════════════════════════════════════════════════════

from datetime import datetime

HARD_TECH_KEYWORDS = {
    "AI算力": ["光模块", "算力", "服务器", "AI芯片", "数据中心", "GPU", "CPO", "HBM",
              "人工智能", "大模型", "智算", "云计算", "DeepSeek", "国产算力", "算力链"],
    "机器人": ["人形机器人", "伺服电机", "减速器", "具身智能", "机器视觉", "传感器",
              "丝杠", "灵巧手", "执行器"],
    "半导体": ["晶圆", "EDA", "光刻", "封装", "测试", "芯片", "半导体", "集成电路",
              "存储", "FPGA", "RISC", "碳化硅", "氮化镓"],
    "锂电储能": ["锂电", "锂电池", "储能", "正极", "负极", "隔膜", "电池", "固态电解质",
               "复合集流体", "逆变器", "充电桩", "新能源车"],
    "资源品涨价": ["有色", "铜", "铝", "稀土", "小金属", "化工", "化学", "煤炭",
                 "石油", "石化", "能源金属", "工业金属"],
    "低空经济": ["无人机", "eVTOL", "空管", "低空", "通航", "飞行汽车", "商业航天",
               "航天", "卫星"],
    "信创国产": ["国产OS", "数据库", "工业软件", "信创", "国产替代", "操作系统",
               "中间件", "办公软件"],
    "显示面板": ["OLED", "MLED", "MiniLED", "MicroLED", "面板", "显示屏", "液晶",
               "玻璃基板", "偏光片", "柔性屏", "折叠屏", "触控",
               "京东方", "TCL科技", "深天马", "维信诺", "彩虹股份", "龙腾光电",
               "光电", "显示", "背光", "彩膜"],
}
HARD_TECH_BONUS = {"AI算力": 3.0, "机器人": 2.0, "半导体": 2.0, "锂电储能": 2.0,
                    "资源品涨价": 1.5, "低空经济": 1.5, "信创国产": 1.0, "显示面板": 1.0}

POSITIVE_WORDS = ["增长", "突破", "超预期", "创新高", "利好", "涨停", "大增", "翻倍",
    "扩产", "订单", "中标", "签约", "获批", "上市", "回购", "增持",
    "扭亏", "盈利", "分红", "高增长", "景气", "回暖", "复苏", "升级",
    "领先", "优势", "龙头", "核心技术", "自主研发", "国产替代"]
NEGATIVE_WORDS = ["下跌", "亏损", "减持", "爆雷", "违约", "退市", "跌停", "暴跌",
    "下滑", "萎缩", "风险", "预警", "诉讼", "处罚", "调查", "停产",
    "裁员", "减值", "债务", "逾期", "失控", "纠纷", "造假", "退潮",
    "过剩", "价格战", "内卷", "关税", "制裁"]


def score_hard_tech(code: str) -> dict:
    from kronos_factors.scorer._db_stub import _get_db
    try:
        with _get_db(readonly=True) as db:
            row = db.execute("SELECT name, industry FROM stocks WHERE code=?", (code,)).fetchone()
            if not row: return {"score": 0.0, "signal": "no_data", "source": "hard_tech"}
            name = (row["name"] or "") + (row["industry"] or "")
            br = db.execute("SELECT COUNT(DISTINCT broker) as c FROM broker_recommend WHERE code=? AND month >= ?",
                (code, (datetime.now().replace(day=1) - __import__("datetime").timedelta(days=90)).strftime("%Y%m"))).fetchone()
            broker_count = br["c"] if br else 0
    except Exception: return {"score": 0.0, "signal": "neutral", "source": "hard_tech"}
    score = 0.0; matched = []
    for track, keywords in HARD_TECH_KEYWORDS.items():
        for kw in keywords:
            if kw in name: score += HARD_TECH_BONUS[track]; matched.append(track); break
    if broker_count >= 5: score += 1.0
    elif broker_count >= 3: score += 1.5
    elif broker_count <= 2 and broker_count >= 1: score += 2.0 if broker_count == 1 else 1.5
    signal = "hard_tech" if score >= 2.0 else "normal"
    return {"score": round(min(5.0, score), 1), "signal": signal, "source": "hard_tech",
            "tracks": ",".join(matched) if matched else "none", "broker_consensus": broker_count}


def get_tushare_scores(code: str) -> dict:
    import os
    if not os.environ.get("TUSHARE_TOKEN"): return {}
    from kronos_factors.scorer._db_stub import _get_db
    scores = {}
    try:
        with _get_db(readonly=True) as db:
            mf_rows = db.execute("SELECT * FROM moneyflow WHERE code=? ORDER BY trade_date DESC LIMIT 20", (code,)).fetchall()
            hk_rows = db.execute("SELECT * FROM hk_holdings WHERE code=? ORDER BY trade_date DESC LIMIT 20", (code,)).fetchall()
            mg_rows = db.execute("SELECT * FROM margin_detail WHERE code=? ORDER BY trade_date DESC LIMIT 10", (code,)).fetchall()
            tl_rows = db.execute("SELECT * FROM top_list WHERE code=? ORDER BY trade_date DESC LIMIT 30", (code,)).fetchall()
            ti_rows = db.execute("SELECT * FROM top_inst WHERE code=? ORDER BY trade_date DESC LIMIT 30", (code,)).fetchall()
            bt_rows = db.execute("SELECT * FROM block_trade_data WHERE code=? ORDER BY trade_date DESC LIMIT 20", (code,)).fetchall()
            db_row = db.execute("SELECT * FROM daily_basic WHERE code=? ORDER BY trade_date DESC LIMIT 1", (code,)).fetchone()
            nf_rows = db.execute("SELECT * FROM moneyflow_hsgt ORDER BY trade_date DESC LIMIT 10").fetchall()

            # moneyflow
            if len(mf_rows) >= 5:
                tn = sum(r["net_mf_amount"] or 0 for r in mf_rows)
                ib = sum((r["buy_lg_amount"] or 0)+(r["buy_elg_amount"] or 0) for r in mf_rows)
                iss = sum((r["sell_lg_amount"] or 0)+(r["sell_elg_amount"] or 0) for r in mf_rows)
                rb = sum((r["buy_sm_amount"] or 0)+(r["buy_md_amount"] or 0) for r in mf_rows)
                rs = sum((r["sell_sm_amount"] or 0)+(r["sell_md_amount"] or 0) for r in mf_rows)
                tf = ib+iss+rb+rs; inn = ib-iss; s = 5.0
                if inn > 0 and tn > 0: s += min(3.0, abs(inn)/max(tf,1)*10)
                elif inn > 0: s += 1.5
                elif tn < 0: s -= min(3.0, abs(tn)/max(tf,1)*10)
                if len(mf_rows) >= 10:
                    rn = sum(r["net_mf_amount"] or 0 for r in mf_rows[:5]); pn = sum(r["net_mf_amount"] or 0 for r in mf_rows[5:10])
                    if rn > pn and rn > 0: s += 1.0
                scores["tushare_moneyflow"] = {"score": round(max(0,min(10,s)),1), "signal": "strong_inflow" if s>=7 else "inflow" if s>=5.5 else "outflow" if s<=3 else "neutral", "source": "tushare"}
            else: scores["tushare_moneyflow"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # hk_hold
            if len(hk_rows) >= 5:
                ratios = [r["ratio"] or 0 for r in hk_rows]; s = 5.0
                if ratios[0] > 3: s += 2.0
                elif ratios[0] > 1: s += 1.0
                if len(ratios) >= 10:
                    ra = sum(ratios[:5])/5; pa = sum(ratios[5:10])/5
                    if ra > pa*1.05: s += 2.0
                    elif ra > pa: s += 1.0
                    elif ra < pa*0.95: s -= 2.0
                scores["tushare_hk_hold"] = {"score": round(max(0,min(10,s)),1), "signal": "heavy_hold" if s>=7 else "increasing" if s>=5.5 else "decreasing", "source": "tushare"}
            else: scores["tushare_hk_hold"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # margin
            if len(mg_rows) >= 3:
                balances = [r["rzye"] or 0 for r in mg_rows]; buys = [r["rzmre"] or 0 for r in mg_rows]; repays = [r["rzche"] or 0 for r in mg_rows]; s = 5.0
                if len(balances) >= 5 and balances[0] > balances[4]*1.05: s += 1.5
                elif len(balances) >= 5 and balances[0] > balances[4]: s += 0.5
                tb = sum(buys); tr = sum(repays)
                if tb+tr > 0: br = tb/(tb+tr)
                if tb+tr > 0 and br > 0.55: s += 2.0
                elif tb+tr > 0 and br > 0.5: s += 1.0
                elif tb+tr > 0 and br < 0.45: s -= 1.0
                scores["tushare_margin"] = {"score": round(max(0,min(10,s)),1), "signal": "bullish_margin" if s>=7 else "neutral" if s>=4 else "bearish_margin", "source": "tushare"}
            else: scores["tushare_margin"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # top_list
            if tl_rows:
                na = [r["net_amount"] or 0 for r in tl_rows]; tn2 = sum(na); pos = sum(1 for n in na if n>0); s = 5.0
                if pos >= len(tl_rows)*0.6 and tn2 > 0: s += 3.0
                elif tn2 > 0 and pos >= len(tl_rows)*0.5: s += 2.0
                elif tn2 < 0 and pos < len(tl_rows)*0.4: s -= 2.0
                rn = sum(r["net_amount"] or 0 for r in tl_rows[:3])
                if rn > 0: s += min(2.0, rn/max(abs(tn2),1)*2)
                scores["tushare_top_list"] = {"score": round(max(0,min(10,s)),1), "signal": "strong_net_buy" if s>=7 else "net_buy" if s>=5.5 else "net_sell", "source": "tushare"}
            else: scores["tushare_top_list"] = {"score": 5.0, "signal": "not_listed", "source": "tushare", "available": False}

            # top_inst
            if ti_rows:
                net = sum(r["net_buy"] or 0 for r in ti_rows); bt = sum(r["buy"] or 0 for r in ti_rows); st = sum(r["sell"] or 0 for r in ti_rows); total = bt+st; s = 5.0
                if total > 0 and bt > st*1.5: s += 3.0
                elif total > 0 and bt > st: s += 1.5
                elif total > 0 and st > bt*1.5: s -= 2.0
                rn = sum(r["net_buy"] or 0 for r in ti_rows[:3])
                if rn > 0: s += 1.5
                scores["tushare_top_inst"] = {"score": round(max(0,min(10,s)),1), "signal": "inst_heavy_buy" if s>=7 else "inst_buy" if s>=5.5 else "inst_sell", "source": "tushare"}
            else: scores["tushare_top_inst"] = {"score": 5.0, "signal": "not_listed", "source": "tushare", "available": False}

            # block_trade
            if bt_rows:
                cp = db_row["close"] if db_row and db_row["close"] else None; s = 5.0; pc = 0
                for r in bt_rows:
                    vol = r["vol"] or 0; price = r["price"] or 0
                    if cp and price > cp*1.05 and vol > 100: pc += 1
                    elif cp and price < cp*0.95 and vol > 100: pc -= 1
                if pc > 2: s += 2.0
                elif pc > 0: s += 1.0
                elif pc < -2: s -= 2.0
                elif pc < 0: s -= 1.0
                scores["tushare_block_trade"] = {"score": round(max(0,min(10,s)),1), "signal": "premium" if s>=7 else "discount" if s<=3 else "fair", "source": "tushare"}
            else: scores["tushare_block_trade"] = {"score": 5.0, "signal": "no_trade", "source": "tushare", "available": False}

            # daily_basic
            if db_row:
                pe = db_row["pe"] or 0; pb = db_row["pb"] or 0; turnover = db_row["turnover_rate"] or 0; vol_ratio = db_row["volume_ratio"] or 0; s = 5.0
                if 10 < pe <= 30: s += 1.5
                elif 0 < pe <= 10: s += 1.0
                elif pe > 100: s -= 1.5
                if 1 <= pb <= 3: s += 1.5
                elif 0 < pb < 1: s += 1.0
                if 3 <= turnover <= 15: s += 1.0
                elif turnover < 1: s -= 1.0
                if 0.8 <= vol_ratio <= 1.5: s += 0.5
                elif vol_ratio > 2: s += 0.5
                scores["tushare_daily_basic"] = {"score": round(max(0,min(10,s)),1), "signal": "quality" if s>=7 else "fair" if s>=4 else "expensive", "source": "tushare"}
            else: scores["tushare_daily_basic"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # financial
            fi_rows = db.execute("SELECT * FROM financial_indicator WHERE code=? ORDER BY end_date DESC LIMIT 2", (code,)).fetchall()
            fi_inc = db.execute("SELECT * FROM financial_income WHERE code=? ORDER BY end_date DESC LIMIT 2", (code,)).fetchall()
            fi_cf = db.execute("SELECT * FROM financial_cashflow WHERE code=? ORDER BY end_date DESC LIMIT 1", (code,)).fetchone()
            if fi_rows:
                latest = dict(fi_rows[0]); s = 5.0
                roe = latest.get("roe") or 0; gm = latest.get("grossprofit_margin") or 0; debt = latest.get("debt_to_assets") or 0
                if roe > 15: s += 2.0
                elif roe > 8: s += 1.0
                elif roe < 0: s -= 2.0
                if gm > 40: s += 1.5
                elif gm > 20: s += 0.5
                if debt < 40: s += 1.5
                elif debt > 70: s -= 1.5
                if len(fi_inc) >= 2:
                    rev0 = dict(fi_inc[0]).get("total_revenue") or 0; rev1 = dict(fi_inc[1]).get("total_revenue") or 0
                    if rev0 and rev1 and rev1 > 0:
                        rg = (rev0/rev1-1)*100
                        if rg > 20: s += 1.5
                        elif rg > 5: s += 0.5
                        elif rg < -10: s -= 1.0
                eps = latest.get("eps") or 0
                if fi_cf and eps > 0:
                    ocfps = latest.get("ocfps") or 0
                    if ocfps and ocfps > eps*0.8: s += 0.5
                # ── P3: 资产负债表深度 (商誉/应收/存货质量) ──
                try:
                    fi_bs = db.execute(
                        "SELECT * FROM financial_balance WHERE code=? ORDER BY end_date DESC LIMIT 1",
                        (code,)).fetchone()
                    if fi_bs:
                        bs = dict(fi_bs)
                        goodwill = bs.get("goodwill") or 0
                        equity = bs.get("total_hldr_eqy_exc_min_int") or 1
                        receivables = bs.get("notes_receiv") or 0
                        inventory = bs.get("inventories") or 0
                        revenue = latest.get("total_revenue") or dict(fi_inc[0]).get("total_revenue", 0) if fi_inc else 1
                        cash_equiv = bs.get("money_cap") or 0
                        short_debt = bs.get("short_borrow") or 0
                        if equity > 0:
                            if goodwill / equity > 0.30: s -= 2.0  # 商誉减值炸弹
                            elif goodwill / equity > 0.15: s -= 1.0
                        if revenue and revenue > 0:
                            if receivables / revenue > 0.50: s -= 1.5  # 回款风险
                            if inventory / revenue > 0.60: s -= 1.5  # 滞销风险
                        if short_debt > 0 and cash_equiv / short_debt > 2: s += 1.0  # 流动性充裕
                except Exception: pass
                scores["tushare_financial"] = {"score": round(max(0,min(10,s)),1), "signal": "quality" if s>=7 else "fair" if s>=4 else "weak", "source": "tushare"}
            else: scores["tushare_financial"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # events
            ev_holder = db.execute("SELECT in_de, change_vol, change_ratio FROM stk_holdertrade WHERE code=? ORDER BY ann_date DESC LIMIT 10", (code,)).fetchall()
            ev_sh = db.execute("SELECT holder_num FROM stk_holdernumber WHERE code=? ORDER BY end_date DESC LIMIT 2", (code,)).fetchall()
            ev_pledge = db.execute("SELECT pledge_total_ratio FROM pledge_detail WHERE code=?", (code,)).fetchall()
            ev_repo = db.execute("SELECT COUNT(*) as c FROM repurchase WHERE code=? AND ann_date>=date('now','-90 days')", (code,)).fetchone()
            ev_float = db.execute("SELECT float_ratio FROM share_float WHERE code=? AND float_date>=date('now') ORDER BY float_date LIMIT 1", (code,)).fetchone()
            s = 5.0
            if ev_holder:
                inc = sum(1 for h in ev_holder if str(h["in_de"])=="增持"); dec = sum(1 for h in ev_holder if str(h["in_de"])=="减持")
                if inc > dec: s += 2.0
                elif dec > inc: s -= 2.0
            if len(ev_sh) >= 2 and ev_sh[1]["holder_num"] and ev_sh[0]["holder_num"]:
                diff = (ev_sh[0]["holder_num"]/ev_sh[1]["holder_num"]-1)*100
                if diff < -5: s += 1.5
                elif diff > 20: s -= 1.5
            if ev_pledge:
                mp = max(p["pledge_total_ratio"] or 0 for p in ev_pledge)
                if mp > 50: s -= 3.0
                elif mp > 30: s -= 1.5
            if ev_repo and ev_repo["c"] > 0: s += 2.0
            if ev_float and ev_float["float_ratio"] and ev_float["float_ratio"] > 5: s -= 2.0
            # P3: 业绩预告 SUE 因子
            try:
                fc_row = db.execute(
                    "SELECT forecast_type, net_profit_min, net_profit_max, change_reason "
                    "FROM forecast_data WHERE code=? ORDER BY end_date DESC LIMIT 1", (code,)
                ).fetchone()
                if fc_row:
                    ftype = str(fc_row["forecast_type"] or "")
                    if any(kw in ftype for kw in ["预增", "扭亏", "续盈", "大增"]): s += 2.5
                    elif "略增" in ftype: s += 1.0
                    elif any(kw in ftype for kw in ["预减", "首亏", "续亏", "预亏"]): s -= 2.5
                    elif "略减" in ftype: s -= 1.0
                    # 净利润变动幅度 bonus
                    pmin = fc_row["net_profit_min"] or 0; pmax = fc_row["net_profit_max"] or 0
                    if pmin > 0 and pmax > pmin * 1.5: s += 0.5
            except Exception: pass
            scores["tushare_events"] = {"score": round(max(0,min(10,s)),1), "signal": "positive" if s>=7 else "negative" if s<=3 else "neutral", "source": "tushare"}

            # cyq
            cq_latest = db.execute("SELECT MAX(trade_date) FROM cyq_chips WHERE code=?", (code,)).fetchone()
            cq_rows = db.execute("SELECT price, percent FROM cyq_chips WHERE code=? AND trade_date=(SELECT MAX(trade_date) FROM cyq_chips WHERE code=?) ORDER BY price", (code, code)).fetchall() if cq_latest and cq_latest[0] else []
            if cq_rows:
                prices = [r["price"] or 0 for r in cq_rows]; percents = [r["percent"] or 0 for r in cq_rows]
                tp = sum(percents) or 1.0; avg_cost = sum(p*w/tp for p,w in zip(prices, percents))
                cumsum = 0; p5 = p95 = prices[0] if prices else 0
                for p, w in zip(prices, percents):
                    cumsum += w/tp*100
                    if cumsum >= 5 and p5 == prices[0]: p5 = p
                    if cumsum >= 95: p95 = p; break
                conc = (p95-p5)/avg_cost*100 if avg_cost > 0 else 100
                cp_val = db_row["close"] if db_row and db_row["close"] else avg_cost
                pr = cp_val/avg_cost if avg_cost > 0 else 1.0; s = 5.0
                if 0.90 <= pr <= 1.05: s += 2.5
                elif 0.80 <= pr < 0.90: s += 1.5
                elif pr < 0.70: s -= 2.0
                elif pr > 1.30: s -= 1.5
                if conc < 15: s += 2.0
                elif conc < 25: s += 1.0
                elif conc > 50: s -= 1.0
                scores["tushare_cyq"] = {"score": round(max(0,min(10,s)),1), "signal": "accumulation" if s>=7 else "distribution" if s<=3 else "neutral", "source": "tushare"}
            else: scores["tushare_cyq"] = {"score": 5.0, "signal": "no_data", "source": "tushare", "available": False}

            # broker
            br_rows = db.execute("SELECT month, broker FROM broker_recommend WHERE code=? ORDER BY month DESC LIMIT 30", (code,)).fetchall()
            if br_rows:
                bc = len(set(r["broker"] for r in br_rows)); s = 5.0
                if bc >= 5: s += 3.0
                elif bc >= 3: s += 2.0
                elif bc >= 1: s += 1.0
                tm = datetime.now().strftime("%Y%m"); recent = sum(1 for r in br_rows if r["month"] == tm)
                if recent >= 3: s += 2.0
                elif recent >= 1: s += 1.0
                scores["tushare_broker"] = {"score": round(max(0,min(10,s)),1), "signal": "strong_consensus" if s>=7 else "moderate" if s>=5.5 else "weak", "source": "tushare"}
            else: scores["tushare_broker"] = {"score": 5.0, "signal": "not_recommended", "source": "tushare", "available": False}

            # north_flow
            if nf_rows:
                rn = sum(r["north_money"] or 0 for r in nf_rows[:5]); s = 5.0
                if rn > 200: s += 3.0
                elif rn > 50: s += 1.5
                elif rn > 0: s += 0.5
                elif rn < -200: s -= 3.0
                elif rn < 0: s -= 1.0
                scores["tushare_north_flow"] = {"score": round(max(0,min(10,s)),1), "signal": "heavy_inflow" if s>=7 else "inflow" if s>=5.5 else "outflow", "source": "tushare"}
            else: scores["tushare_north_flow"] = {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False}

            # NEW: POR factor
            por_row = db.execute("SELECT pe, pe_ttm, pb, ps, ps_ttm FROM daily_basic WHERE code=? ORDER BY trade_date DESC LIMIT 1", (code,)).fetchone()
            if por_row:
                pe_val = por_row["pe_ttm"] or por_row["pe"] or 0; pb_val = por_row["pb"] or 0; ps_val = por_row["ps_ttm"] or por_row["ps"] or 0; s = 5.0
                if pe_val > 0:
                    per = pe_val/20.0
                    if per < 0.5: s += 2.0
                    elif per < 0.8: s += 1.0
                    elif per > 2.0: s -= 2.0
                    elif per > 1.5: s -= 1.0
                if pb_val > 0:
                    pbr = pb_val/2.0
                    if pbr < 0.5: s += 1.5
                    elif pbr > 2.5: s -= 1.5
                if ps_val > 0:
                    psr = ps_val/3.0
                    if psr < 0.3: s += 1.0
                    elif psr > 3.0: s -= 1.0
                scores["tushare_por"] = {"score": round(max(0,min(10,s)),1), "signal": "undervalued" if s>=7 else "overvalued" if s<=3 else "fair", "source": "por", "available": True}
            else: scores["tushare_por"] = {"score": 5.0, "signal": "neutral", "source": "por", "available": False}

            # NEW: SW sector momentum (replaces crude version)
            stock_row = db.execute("SELECT industry FROM stocks WHERE code=?", (code,)).fetchone()
            if stock_row and stock_row["industry"]:
                sw_latest = db.execute("SELECT MAX(trade_date) FROM sw_daily").fetchone()[0]
                if sw_latest:
                    sw_rows = db.execute("SELECT ts_code, close FROM sw_daily WHERE trade_date=?", (sw_latest,)).fetchall()
                    sw_20d = db.execute("SELECT ts_code, close FROM sw_daily WHERE trade_date >= date(?,'-20 days')", (sw_latest,)).fetchall()
                    if len(sw_rows) >= 10:
                        lc = {r["ts_code"]: r["close"] for r in sw_rows}; sc = {}
                        for r in sw_20d: sc.setdefault(r["ts_code"], []).append(r["close"])
                        sr = {}
                        for ts, closes in sc.items():
                            if len(closes) >= 5 and closes[0] > 0: sr[ts] = (closes[-1]/closes[0]-1)*100
                        if len(sr) >= 10:
                            rl = sorted(sr.values()); p80 = rl[int(len(rl)*0.8)]; p20 = rl[int(len(rl)*0.2)]
                            matched = next((sr.get(r["ts_code"]) for r in sw_rows if stock_row["industry"] in (r.get("name") or "")), sum(sr.values())/len(sr))
                            s = 5.0
                            if matched >= p80 and matched > 0: s += 2.5
                            elif matched >= rl[int(len(rl)*0.6)]: s += 1.5
                            elif matched >= rl[int(len(rl)*0.4)]: s += 0.5
                            elif matched < p20: s -= 1.0
                            scores["tushare_sector"] = {"score": round(max(0,min(10,s)),1), "signal": "leading" if s>=7 else "lagging" if s<=3 else "neutral", "source": "sw_sector"}
            if "tushare_sector" not in scores: scores["tushare_sector"] = {"score": 5.0, "signal": "neutral", "source": "sw_sector", "available": False}

            # NEW: news sentiment + anomaly
            stock_name = db.execute("SELECT name FROM stocks WHERE code=?", (code,)).fetchone()
            if stock_name and stock_name["name"]:
                news_rows = db.execute("SELECT title, pub_time FROM stock_news_tushare WHERE pub_time >= date('now','-30 days') ORDER BY pub_time DESC LIMIT 50").fetchall()
                relevant = [r for r in news_rows if stock_name["name"] in (r["title"] or "")]
                if relevant:
                    pos_h = sum(1 for r in relevant for w in POSITIVE_WORDS if w in (r["title"] or ""))
                    neg_h = sum(1 for r in relevant for w in NEGATIVE_WORDS if w in (r["title"] or "")); nc = len(relevant); s = 5.0
                    if pos_h > neg_h*2 and nc >= 3: s += 2.0
                    elif pos_h > neg_h: s += 1.0
                    elif neg_h > pos_h*2 and nc >= 3: s -= 2.0
                    elif neg_h > pos_h: s -= 1.0
                    hist = db.execute("SELECT COUNT(*) as total FROM stock_news_tushare WHERE pub_time >= date('now','-90 days') AND pub_time < date('now','-7 days') AND title LIKE ?", (f"%{stock_name['name']}%",)).fetchone()
                    hist_c = hist["total"] if hist else 0; avg_w = hist_c/12.0
                    if avg_w > 0 and nc > avg_w*2.5: s += 1.5
                    elif avg_w > 0 and nc > avg_w*1.5: s += 0.5
                    if nc >= 5: s += 0.5
                    scores["tushare_news"] = {"score": round(max(0,min(10,s)),1), "signal": "positive" if s>=7 else "negative" if s<=3 else "neutral", "source": "news", "news_count": nc, "available": True}
                else: scores["tushare_news"] = {"score": 5.0, "signal": "no_coverage", "source": "news", "available": False}
            else: scores["tushare_news"] = {"score": 5.0, "signal": "neutral", "source": "news", "available": False}

            # NEW: analyst coverage (enhanced with first-time detection)
            ar = db.execute("SELECT COUNT(*) as c, COUNT(DISTINCT author) as authors FROM research_reports_tushare WHERE code=? AND trade_date >= date('now','-30 days')", (code,)).fetchone()
            ar_all = db.execute("SELECT COUNT(*) as c FROM research_reports_tushare WHERE code=? AND trade_date >= date('now','-90 days')", (code,)).fetchone()
            ar_prior = db.execute("SELECT COUNT(*) as c FROM research_reports_tushare WHERE code=? AND trade_date BETWEEN date('now','-180 days') AND date('now','-91 days')", (code,)).fetchone()
            rc = ar["c"] if ar else 0; ra = ar["authors"] if ar else 0; pc = ar_prior["c"] if ar_prior else 0
            if rc > 0 or (ar_all and ar_all["c"] > 0):
                is_first = (pc == 0 and rc >= 1); cov_growth = rc/max(pc,0.01); s = 5.0
                if is_first: s += 3.0
                elif rc >= 5: s += 2.5
                elif rc >= 3: s += 2.0
                elif rc >= 1: s += 1.0
                if ra >= 3: s += 1.5
                elif ra >= 2: s += 0.5
                if cov_growth >= 3 and rc >= 2: s += 1.5
                if (ar_all["c"] if ar_all else 0) >= 10 and rc == 0: s += 0.5
                scores["tushare_analyst"] = {"score": round(max(0,min(10,s)),1), "signal": "initiation" if is_first else "hot" if s>=7 else "covered" if s>=5.5 else "uncovered", "source": "analyst", "recent_count": rc, "first_coverage": is_first, "available": True}
            else: scores["tushare_analyst"] = {"score": 5.0, "signal": "no_coverage", "source": "analyst", "available": False}

            # NEW: SW sector valuation percentile
            if stock_row and stock_row["industry"]:
                sw_pe_row = db.execute("SELECT ts_code, pe FROM sw_daily WHERE name LIKE ? ORDER BY trade_date DESC LIMIT 1", (f"%{stock_row['industry']}%",)).fetchone()
                if sw_pe_row and sw_pe_row["pe"] and sw_pe_row["pe"] > 0:
                    pe_hist = db.execute("SELECT pe FROM sw_daily WHERE ts_code=? AND pe > 0 ORDER BY trade_date DESC LIMIT 1000", (sw_pe_row["ts_code"],)).fetchall()
                    if len(pe_hist) >= 100:
                        pe_vals = sorted([r["pe"] for r in pe_hist]); pct = sum(1 for p in pe_vals if p <= sw_pe_row["pe"])/len(pe_vals)*100; s = 5.0
                        if pct < 20: s += 2.0
                        elif pct < 40: s += 1.0
                        elif pct > 80: s -= 1.5
                        elif pct > 60: s -= 0.5
                        scores["tushare_sector_val"] = {"score": round(max(0,min(10,s)),1), "signal": "undervalued" if s>=6 else "overvalued" if s<=4 else "fair", "source": "sw", "percentile": round(pct,1)}
            if "tushare_sector_val" not in scores: scores["tushare_sector_val"] = {"score": 5.0, "signal": "neutral", "source": "sw", "available": False}

    except Exception:
        for key in ["tushare_moneyflow","tushare_hk_hold","tushare_margin","tushare_top_list","tushare_top_inst","tushare_block_trade","tushare_daily_basic","tushare_financial","tushare_events","tushare_cyq","tushare_broker","tushare_north_flow","tushare_por","tushare_sector","tushare_news","tushare_analyst","tushare_sector_val"]:
            scores.setdefault(key, {"score": 5.0, "signal": "neutral", "source": "tushare", "available": False})
    return scores
