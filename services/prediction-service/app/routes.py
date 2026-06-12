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

    return {
        "code": code, "mode": "fast",
        "current_price": round(current_price, 2),
        "pred_days": pred_days,
        "pred_last_close": round(pred_close, 2),
        "pred_return_pct": pred_return,
        "trend": "📈 上升" if pred_close > current_price else "📉 下降",
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

    return {
        "code": code,
        "current_price": round(current_price, 2),
        "pred_days": pred_days,
        "pred_last_close": round(pred_close, 2),
        "pred_return_pct": pred_return,
        "pred_high": pred_high,
        "pred_low": pred_low,
        "max_drawdown_pct": max_dd,
        "trend": trend,
        "pred_trajectory": [
            {"day": i + 1, "open": round(float(pred_df["open"].iloc[i]), 2),
             "high": round(float(pred_df["high"].iloc[i]), 2),
             "low": round(float(pred_df["low"].iloc[i]), 2),
             "close": round(float(pred_df["close"].iloc[i]), 2)}
            for i in range(min(pred_days, len(pred_df)))
        ],
    }
