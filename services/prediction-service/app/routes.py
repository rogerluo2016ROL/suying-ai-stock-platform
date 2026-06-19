"""Prediction API — real Kronos K-line forecasting."""

import os, logging
from fastapi import APIRouter, Query, HTTPException
import pandas as pd
import numpy as np

import app.main as _m

logger = logging.getLogger("prediction-service.routes")
router = APIRouter(prefix="/api/v1/prediction", tags=["prediction"])

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _resolve_db_path() -> str:
    """Resolve DB path with fallback search."""
    # 1) explicit env var
    env_path = os.environ.get("KRONOS_DB_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2) relative to project root
    candidates = [
        os.path.join(_ROOT, "Kronos", "webui", "stock_screening.db"),
        os.path.join(_ROOT, "..", "Kronos", "webui", "stock_screening.db"),
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Kronos", "webui", "stock_screening.db"),
    ]
    for c in candidates:
        abs_c = os.path.abspath(c)
        if os.path.isfile(abs_c):
            return abs_c

    logger.warning("stock_screening.db not found, tried: %s", candidates)
    return ""  # let sqlite3.connect fail with clear error


DB_PATH = _resolve_db_path()


# ── P3: 辅助特征 (多模态后处理) ──

def _get_auxiliary_features(code: str) -> dict | None:
    """Fetch auxiliary features from PG for post-prediction adjustment.

    Data sources: moneyflow (fund flow), daily_basic (valuation/activity),
    stk_factor_pro (technical indicators).
    """
    try:
        import psycopg2
        pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
        conn = psycopg2.connect(pg_url, connect_timeout=3)
        cur = conn.cursor()

        feats = {}

        # 1. Moneyflow — last 10 days
        cur.execute(
            "SELECT net_mf_amount, buy_lg_amount, sell_lg_amount, "
            "buy_elg_amount, sell_elg_amount FROM moneyflow "
            "WHERE code=%s ORDER BY trade_date DESC LIMIT 10",
            (code,))
        mf_rows = cur.fetchall()
        if mf_rows:
            net_flows = [r[0] or 0 for r in mf_rows]
            lg_buys = sum(r[1] or 0 for r in mf_rows)
            lg_sells = sum(r[2] or 0 for r in mf_rows)
            elg_buys = sum(r[3] or 0 for r in mf_rows)
            elg_sells = sum(r[4] or 0 for r in mf_rows)
            feats["net_mf_10d"] = sum(net_flows)
            feats["lg_net"] = lg_buys - lg_sells
            feats["elg_net"] = elg_buys - elg_sells
            # Flow momentum: recent 5d vs previous 5d
            if len(mf_rows) >= 10:
                recent = sum(r[0] or 0 for r in mf_rows[:5])
                prev = sum(r[0] or 0 for r in mf_rows[5:10])
                feats["flow_momentum"] = recent - prev

        # 2. daily_basic — latest day
        cur.execute(
            "SELECT pe, pb, turnover_rate, volume_ratio, total_mv "
            "FROM daily_basic WHERE code=%s ORDER BY trade_date DESC LIMIT 1",
            (code,))
        db_row = cur.fetchone()
        if db_row:
            feats["pe"] = db_row[0] or 0
            feats["pb"] = db_row[1] or 0
            feats["turnover_rate"] = db_row[2] or 0
            feats["volume_ratio"] = db_row[3] or 0
            feats["total_mv"] = db_row[4] or 0

        # 3. stk_factor_pro — latest day
        cur.execute(
            "SELECT macd, macd_dif, macd_dea, rsi_6, rsi_12, rsi_24, "
            "kdj_k, kdj_d, kdj_j FROM stk_factor_pro "
            "WHERE ts_code LIKE %s ORDER BY trade_date DESC LIMIT 1",
            (f"{code}%",))
        tf_row = cur.fetchone()
        if tf_row:
            feats["macd"] = tf_row[0] or 0
            feats["macd_dif"] = tf_row[1] or 0
            feats["rsi_6"] = tf_row[3] or 50
            feats["rsi_12"] = tf_row[4] or 50
            feats["kdj_k"] = tf_row[6] or 50
            feats["kdj_d"] = tf_row[7] or 50
            feats["kdj_j"] = tf_row[8] or 50
            # MACD golden cross
            if tf_row[1] and tf_row[2]:
                feats["macd_golden"] = 1 if tf_row[1] > tf_row[2] else -1

        conn.close()
        return feats if feats else None
    except Exception:
        return None


def _compute_auxiliary_score(feats: dict) -> dict:
    """Compute auxiliary score (0-10) from multi-modal features.

    Scoring model:
      - Fund flow (35%): net inflow + large/extra-large buyer dominance
      - Technical (40%): RSI optimal zone + MACD golden + KDJ momentum
      - Valuation (25%): PE/PB reasonable + volume activity normal
    """
    score = 5.0  # neutral start
    signals = []

    # ── Fund Flow (0-3.5 points) ──
    net_mf = feats.get("net_mf_10d", 0)
    lg_net = feats.get("lg_net", 0)
    flow_mom = feats.get("flow_momentum", 0)

    if net_mf > 1e8: score += 2.0; signals.append("主力净流入")
    elif net_mf > 0: score += 1.0
    elif net_mf < -1e8: score -= 2.0; signals.append("主力净流出")
    elif net_mf < 0: score -= 1.0

    if lg_net > 0: score += 1.0  # 大单净买入
    if flow_mom > 0 and net_mf > 0: score += 0.5  # 流入加速

    # ── Technical (0-4.0 points) ──
    rsi6 = feats.get("rsi_6", 50)
    macd_golden = feats.get("macd_golden", 0)
    kdj_j = feats.get("kdj_j", 50)

    if 30 <= rsi6 <= 70: score += 1.0  # RSI healthy zone
    elif rsi6 < 25: score += 1.5; signals.append("RSI超卖反弹")
    elif rsi6 > 80: score -= 1.5; signals.append("RSI超买风险")

    if macd_golden == 1: score += 1.5; signals.append("MACD金叉")
    elif macd_golden == -1: score -= 1.0

    if kdj_j < 20: score += 1.0; signals.append("KDJ超卖")
    elif kdj_j > 100: score -= 1.0; signals.append("KDJ超买")

    # ── Valuation (0-2.5 points) ──
    pe = feats.get("pe", 0)
    pb = feats.get("pb", 0)
    vol_ratio = feats.get("volume_ratio", 1)
    turnover = feats.get("turnover_rate", 0)

    if 10 <= pe <= 30: score += 1.0
    elif 0 < pe <= 10: score += 0.5; signals.append("低估值")
    elif pe > 100: score -= 1.0

    if 1 <= pb <= 3: score += 0.5
    if 0.8 <= vol_ratio <= 2.0: score += 0.5
    if 3 <= turnover <= 15: score += 0.5

    score = max(0, min(10, round(score, 1)))
    return {"score": score, "signals": signals}


def _get_kline(code: str, lookback: int = 400):
    """Get K-line data from SQLite DB (column: code, not ts_code)."""
    import sqlite3
    if not DB_PATH:
        logger.error("No database available — set KRONOS_DB_PATH env var")
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # daily_kline uses 'code' column (not 'ts_code')
        c.execute("SELECT trade_date, open, high, low, close, volume, amount "
                  "FROM daily_kline WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                  (code, lookback))
        rows = c.fetchall()
        conn.close()
        if len(rows) < 30:
            logger.info("Insufficient K-line data for %s: %d rows (need ≥30)", code, len(rows))
            return None
        df = pd.DataFrame([{"open": r[1], "high": r[2], "low": r[3], "close": r[4],
                            "volume": r[5], "amount": r[6]} for r in reversed(rows)])
        dates = pd.to_datetime([r[0] for r in reversed(rows)])
        return df, pd.Series(dates)
    except Exception as e:
        logger.warning("DB error for %s: %s", code, e)
        return None


@router.get("/status")
async def model_status():
    return {"model_loaded": _m._model_loaded, "model": "Kronos-small", "device": "cpu"}


@router.post("/{code}/fast")
async def predict_stock_fast(
    code: str,
    pred_days: int = Query(15, ge=5, le=30),
):
    """🔥 V2 快速预测: 单样本+低延迟，适合实时诊断 (延迟 ~300ms vs 标准 ~1s)。"""
    if not _m._model_loaded or _m._predictor is None:
        raise HTTPException(503, "Kronos model not loaded")

    kline = _get_kline(code)
    if kline is None:
        raise HTTPException(404, f"No K-line data for {code} (need ≥30 rows)")

    df, x_ts = kline
    lookback = min(len(df), 400)
    x_df = df.iloc[-lookback:]
    x_timestamp = x_ts.iloc[-lookback:].reset_index(drop=True)

    last_date = x_timestamp.iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_days)
    y_timestamp = pd.Series(y_ts)

    try:
        pred_df = _m._predictor.predict_fast(
            df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
            pred_len=pred_days, verbose=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Prediction failed: {e}")

    current_price = float(df["close"].iloc[-1])
    pred_close = float(pred_df["close"].iloc[-1])
    pred_return = round((pred_close / current_price - 1) * 100, 2)

    # ── P3: 多模态辅助评分 (后处理) ──
    auxiliary = None
    adjusted_return = pred_return
    try:
        feats = _get_auxiliary_features(code)
        if feats:
            auxiliary = _compute_auxiliary_score(feats)
            # Adjustment: ±2% max based on auxiliary score deviation from 5
            bonus = (auxiliary["score"] - 5) * 0.4
            adjusted_return = round(pred_return + bonus, 2)
    except Exception:
        pass

    return {
        "code": code, "mode": "fast",
        "current_price": round(current_price, 2),
        "pred_days": pred_days,
        "pred_last_close": round(pred_close, 2),
        "pred_return_pct": pred_return,
        "adjusted_return_pct": adjusted_return,
        "trend": "📈 上升" if pred_close > current_price else "📉 下降",
        "auxiliary": auxiliary,
        "pred_trajectory": [
            {"day": i + 1, "open": round(float(pred_df["open"].iloc[i]), 2),
             "high": round(float(pred_df["high"].iloc[i]), 2),
             "low": round(float(pred_df["low"].iloc[i]), 2),
             "close": round(float(pred_df["close"].iloc[i]), 2)}
            for i in range(min(pred_days, len(pred_df)))
        ],
    }


@router.post("/{code}")
async def predict_stock(
    code: str,
    pred_days: int = Query(20, ge=5, le=30),
):
    """Run real Kronos prediction for a single stock."""
    if not _m._model_loaded or _m._predictor is None:
        raise HTTPException(503, "Kronos model not loaded")

    kline = _get_kline(code)
    if kline is None:
        raise HTTPException(404, f"No K-line data for {code} (need ≥30 rows)")

    df, x_ts = kline
    lookback = min(len(df), 400)
    x_df = df.iloc[-lookback:]
    x_timestamp = x_ts.iloc[-lookback:].reset_index(drop=True)

    # Future timestamps
    last_date = x_timestamp.iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_days)
    y_timestamp = pd.Series(y_ts)

    try:
        pred_df = _m._predictor.predict(
            df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
            pred_len=pred_days, T=0.7, top_k=10, top_p=0.95, sample_count=3,
            verbose=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Prediction failed: {e}")

    current_price = float(df["close"].iloc[-1])
    pred_close = float(pred_df["close"].iloc[-1])
    pred_return = round((pred_close / current_price - 1) * 100, 2)
    pred_high = round(float(pred_df["high"].max()), 2)
    pred_low = round(float(pred_df["low"].min()), 2)
    max_dd = round((pred_low / current_price - 1) * 100, 2)
    trend = "📈 上升" if pred_close > current_price else "📉 下降"

    # ── P3: 多模态辅助评分 (后处理) ──
    auxiliary = None
    adjusted_return = pred_return
    try:
        feats = _get_auxiliary_features(code)
        if feats:
            auxiliary = _compute_auxiliary_score(feats)
            bonus = (auxiliary["score"] - 5) * 0.4
            adjusted_return = round(pred_return + bonus, 2)
    except Exception:
        pass

    return {
        "code": code,
        "current_price": round(current_price, 2),
        "pred_days": pred_days,
        "pred_last_close": round(pred_close, 2),
        "pred_return_pct": pred_return,
        "adjusted_return_pct": adjusted_return,
        "pred_high": pred_high,
        "pred_low": pred_low,
        "max_drawdown_pct": max_dd,
        "trend": trend,
        "auxiliary": auxiliary,
        "pred_trajectory": [
            {"day": i + 1, "open": round(float(pred_df["open"].iloc[i]), 2),
             "high": round(float(pred_df["high"].iloc[i]), 2),
             "low": round(float(pred_df["low"].iloc[i]), 2),
             "close": round(float(pred_df["close"].iloc[i]), 2)}
            for i in range(min(pred_days, len(pred_df)))
        ],
    }


# ═══════════════════════════════════════════════════════════════
# P4: Kronos 元模型 (Kronos 60% + Aux 25% + Valuation 15%)
# ═══════════════════════════════════════════════════════════════

@router.post("/{code}/meta")
async def predict_stock_meta(code: str, pred_days: int = Query(20, ge=5, le=30)):
    """P4: Kronos 元模型融合 — 20维辅助特征加权."""
    if not _m._model_loaded: raise HTTPException(503, "Model not loaded")
    kline = _get_kline(code)
    if kline is None: raise HTTPException(404, f"No data for {code}")
    df, x_ts = kline
    x_df = df.iloc[-min(len(df),400):]
    x_ts2 = x_ts.iloc[-min(len(df),400):].reset_index(drop=True)
    y_ts = pd.bdate_range(start=x_ts2.iloc[-1]+pd.Timedelta(days=1), periods=pred_days)
    try:
        pred_df = _m._predictor.predict_fast(df=x_df, x_timestamp=x_ts2,
            y_timestamp=pd.Series(y_ts), pred_len=pred_days, verbose=False)
    except Exception as e: raise HTTPException(500, str(e))
    cp = float(df["close"].iloc[-1])
    pc = float(pred_df["close"].iloc[-1])
    pr = round((pc/cp-1)*100, 2)
    feats = _get_auxiliary_features(code) or {}
    aux = _compute_auxiliary_score(feats) if feats else {"score":5,"signals":[]}
    vb = 2.0 if (5<(feats.get("pe",0)<25) and (feats.get("pb",0)<3)) else (-2.0 if feats.get("pe",0)>100 else 0)
    mr = round(pr*0.60 + (aux["score"]-5)*0.5*0.25 + vb*0.15, 2)
    return {"code":code,"mode":"meta","current_price":round(cp,2),
        "kronos_return_pct":pr,"meta_return_pct":mr,"auxiliary":aux}
