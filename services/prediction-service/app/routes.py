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


def _model_metadata(inference_mode: str) -> dict:
    """Stable model contract consumed by new UI pages and downstream services."""
    checkpoint_status = getattr(_m, "_model_checkpoint_status", "not_loaded")
    loaded = bool(getattr(_m, "_model_loaded", False) and getattr(_m, "_predictor", None) is not None)
    return {
        "name": "Kronos-mini",
        "version": "kronos-mini",
        "provider": "prediction-service",
        "inference_mode": inference_mode,
        "checkpoint_status": checkpoint_status,
        "loaded": loaded,
    }


def _data_freshness(x_ts, data_source: str = "postgresql.daily_kline") -> dict:
    if x_ts is None or len(x_ts) == 0:
        return {
            "status": "missing",
            "as_of": None,
            "source": data_source,
            "quality_score": 0,
        }

    last_ts = pd.to_datetime(x_ts.iloc[-1])
    as_of = last_ts.date().isoformat()
    lag_days = max(0, (pd.Timestamp.utcnow().tz_localize(None).date() - last_ts.date()).days)
    if lag_days <= 10:
        status, quality_score = "fresh", 96
    elif lag_days <= 30:
        status, quality_score = "stale", 72
    else:
        status, quality_score = "outdated", 35
    return {
        "status": status,
        "as_of": as_of,
        "source": data_source,
        "quality_score": quality_score,
    }


def _latest_daily_kline_timestamp() -> pd.Series | None:
    """Return the actual latest trading date for overview-level freshness."""
    try:
        import psycopg2

        with psycopg2.connect(os.environ.get("KRONOS_PG_URL"), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT MAX(trade_date) FROM daily_kline")
                row = cur.fetchone()
        return pd.Series([row[0]]) if row and row[0] is not None else None
    except Exception as exc:
        logger.warning("prediction overview freshness unavailable: %s", exc)
        return None


def _prediction_fallback_reason(used_baseline: bool) -> str | None:
    if not used_baseline:
        return None
    if not bool(getattr(_m, "_model_loaded", False)):
        return "model checkpoint unavailable; using baseline predictor"
    return "model inference unavailable; using baseline predictor"


def _require_real_model() -> None:
    """Fail closed in production instead of emitting a synthetic baseline path."""
    if os.environ.get("KRONOS_ENV", "development").lower() == "production" and (
        not getattr(_m, "_model_loaded", False) or getattr(_m, "_predictor", None) is None
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "result_status": "unavailable",
                "fallback_reason": "model checkpoint unavailable; production prediction is blocked",
            },
        )


def _with_prediction_contract(
    payload: dict,
    *,
    code: str,
    mode: str,
    x_ts,
    used_baseline: bool,
    data_source: str = "postgresql.daily_kline",
) -> dict:
    enriched = dict(payload)
    enriched.setdefault("code", code)
    enriched["model_metadata"] = _model_metadata(mode)
    enriched["data_freshness"] = _data_freshness(x_ts, data_source)
    enriched["fallback_reason"] = _prediction_fallback_reason(used_baseline)
    return enriched


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
    """Get K-line data from PostgreSQL first, then optional legacy SQLite."""
    pg_url = os.environ.get("KRONOS_PG_URL")
    if pg_url:
        try:
            import psycopg2
            conn = psycopg2.connect(pg_url, connect_timeout=5)
            cur = conn.cursor()
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=%s ORDER BY trade_date DESC LIMIT %s",
                (code, lookback),
            )
            rows = cur.fetchall()
            conn.close()
            if len(rows) >= 30:
                df = pd.DataFrame([
                    {"open": r[1], "high": r[2], "low": r[3], "close": r[4],
                     "volume": r[5], "amount": r[6]}
                    for r in reversed(rows)
                ])
                dates = pd.to_datetime([r[0] for r in reversed(rows)])
                return df, pd.Series(dates)
            logger.info("Insufficient PG K-line data for %s: %d rows (need ≥30)", code, len(rows))
        except Exception as e:
            logger.warning("PG K-line error for %s: %s", code, e)

    if os.environ.get("DATA_SQLITE_FALLBACK", "true").lower() in ("0", "false", "no"):
        return None

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


def _baseline_predict(df: pd.DataFrame, pred_days: int) -> pd.DataFrame:
    """Lightweight local fallback when Kronos weights/runtime are unavailable."""
    recent = df.tail(min(len(df), 20)).copy()
    returns = recent["close"].pct_change().dropna()
    drift = float(returns.mean()) if len(returns) else 0.0
    vol = float(returns.std()) if len(returns) else 0.01
    drift = float(np.clip(drift, -0.03, 0.03))
    vol = float(np.clip(vol, 0.002, 0.05))

    prev_close = float(df["close"].iloc[-1])
    rows = []
    for i in range(pred_days):
        close = prev_close * ((1 + drift) ** (i + 1))
        open_ = prev_close if i == 0 else rows[-1]["close"]
        high = max(open_, close) * (1 + vol * 0.7)
        low = min(open_, close) * (1 - vol * 0.7)
        rows.append({"open": open_, "high": high, "low": low, "close": close})
    return pd.DataFrame(rows)


def _sanitize_prediction_df(
    pred_df: pd.DataFrame,
    current_price: float,
    max_step_pct: float = 0.12,
) -> pd.DataFrame:
    """Repair model-generated OHLC rows into valid, bounded K-line candles."""
    rows = []
    previous_close = float(current_price)
    required = ["open", "high", "low", "close"]
    numeric = pred_df.copy()
    for col in required:
        if col not in numeric:
            numeric[col] = previous_close
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce")

    for _, raw in numeric.iterrows():
        raw_lower_bound = previous_close * (1 - max_step_pct)
        raw_upper_bound = previous_close * (1 + max_step_pct)
        display_rounding_guard = 0.005
        if raw_upper_bound - raw_lower_bound > display_rounding_guard * 2:
            lower_bound = raw_lower_bound + display_rounding_guard
            upper_bound = raw_upper_bound - display_rounding_guard
        else:
            lower_bound = raw_lower_bound
            upper_bound = raw_upper_bound

        open_ = float(raw["open"]) if np.isfinite(raw["open"]) else previous_close
        close = float(raw["close"]) if np.isfinite(raw["close"]) else previous_close
        open_ = float(np.clip(open_, lower_bound, upper_bound))
        close = float(np.clip(close, lower_bound, upper_bound))

        candle_top = max(open_, close)
        candle_bottom = min(open_, close)
        high_raw = float(raw["high"]) if np.isfinite(raw["high"]) else candle_top
        low_raw = float(raw["low"]) if np.isfinite(raw["low"]) else candle_bottom
        high = max(candle_top, min(high_raw, candle_top * (1 + max_step_pct)))
        low = min(candle_bottom, max(low_raw, candle_bottom * (1 - max_step_pct)))

        open_ = round(open_, 2)
        close = round(close, 2)
        high = round(max(high, open_, close), 2)
        low = round(min(low, open_, close), 2)

        rows.append({"open": open_, "high": high, "low": low, "close": close})
        previous_close = close

    return pd.DataFrame(rows)


@router.get("/status")
async def model_status():
    return {
        "model_loaded": bool(getattr(_m, "_model_loaded", False)),
        "model": "Kronos-mini",
        "device": "cpu",
        "model_metadata": _model_metadata("status"),
    }


@router.get("/overview")
async def prediction_overview():
    latest_ts = _latest_daily_kline_timestamp()
    return {
        "page": {"module": "prediction", "view": "overview", "title": "K线预测 - 预测总览"},
        "model_metadata": _model_metadata("overview"),
        "data_freshness": _data_freshness(latest_ts),
        "fallback_reason": _prediction_fallback_reason(not bool(getattr(_m, "_model_loaded", False))),
        "sections": [
            {"id": "forecast-market", "title": "预测市场", "endpoint": "/api/v1/prediction/{code}"},
            {"id": "model-health", "title": "模型健康", "endpoint": "/api/v1/prediction/status"},
            {"id": "accuracy-backtest", "title": "准确率回测", "endpoint": "/api/v1/prediction/accuracy-backtest"},
        ],
    }


@router.post("/single/{code}")
async def prediction_single_stock(
    code: str,
    pred_days: int = Query(20, ge=5, le=30),
):
    return await predict_stock(code, pred_days)


@router.post("/compare")
async def prediction_compare(
    codes: list[str],
    pred_days: int = Query(20, ge=5, le=30),
):
    if not codes:
        raise HTTPException(400, "codes is required")
    results = []
    for code in codes[:10]:
        try:
            item = await predict_stock_fast(code, min(pred_days, 30))
            results.append(item)
        except HTTPException as e:
            results.append({
                "code": code,
                "error": e.detail,
                "model_metadata": _model_metadata("compare"),
                "data_freshness": _data_freshness(None),
                "fallback_reason": "source data missing or prediction failed",
            })
    return {
        "mode": "multi_compare",
        "pred_days": pred_days,
        "model_metadata": _model_metadata("compare"),
        "items": results,
    }


@router.get("/accuracy-backtest")
async def prediction_accuracy_backtest():
    return {
        "mode": "accuracy_backtest",
        "model_metadata": _model_metadata("accuracy-backtest"),
        "data_freshness": {
            "status": "unknown",
            "as_of": None,
            "source": "backtest.prediction_accuracy",
            "quality_score": 0,
        },
        "fallback_reason": "accuracy backtest awaits persisted prediction labels",
        "metrics": [
            {"window": "近30日", "direction_accuracy": 0.0, "sample_size": 0},
            {"window": "近90日", "direction_accuracy": 0.0, "sample_size": 0},
        ],
    }


@router.post("/{code}/fast")
async def predict_stock_fast(
    code: str,
    pred_days: int = Query(15, ge=5, le=30),
):
    """🔥 V2 快速预测: 单样本+低延迟，适合实时诊断 (延迟 ~300ms vs 标准 ~1s)。"""
    kline = _get_kline(code)
    if kline is None:
        raise HTTPException(
            404,
            {
                "message": f"No K-line data for {code} (need ≥30 rows)",
                "fallback_reason": "source data missing: daily_kline has fewer than 30 rows",
            },
        )

    df, x_ts = kline
    lookback = min(len(df), 400)
    x_df = df.iloc[-lookback:]
    x_timestamp = x_ts.iloc[-lookback:].reset_index(drop=True)

    last_date = x_timestamp.iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_days)
    y_timestamp = pd.Series(y_ts)

    used_baseline = False
    if not getattr(_m, "_model_loaded", False) or getattr(_m, "_predictor", None) is None:
        _require_real_model()
        used_baseline = True
        pred_df = _baseline_predict(x_df, pred_days)
    else:
        try:
            pred_df = _m._predictor.predict_fast(
                df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=pred_days, verbose=False,
            )
        except Exception as e:
            raise HTTPException(500, f"Prediction failed: {e}")

    current_price = float(df["close"].iloc[-1])
    pred_df = _sanitize_prediction_df(pred_df, current_price)
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

    payload = {
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
    return _with_prediction_contract(
        payload,
        code=code,
        mode="fast",
        x_ts=x_timestamp,
        used_baseline=used_baseline,
    )


@router.post("/{code}")
async def predict_stock(
    code: str,
    pred_days: int = Query(20, ge=5, le=30),
):
    """Run real Kronos prediction for a single stock."""
    kline = _get_kline(code)
    if kline is None:
        raise HTTPException(
            404,
            {
                "message": f"No K-line data for {code} (need ≥30 rows)",
                "fallback_reason": "source data missing: daily_kline has fewer than 30 rows",
            },
        )

    df, x_ts = kline
    lookback = min(len(df), 400)
    x_df = df.iloc[-lookback:]
    x_timestamp = x_ts.iloc[-lookback:].reset_index(drop=True)

    # Future timestamps
    last_date = x_timestamp.iloc[-1]
    y_ts = pd.bdate_range(start=last_date + pd.Timedelta(days=1), periods=pred_days)
    y_timestamp = pd.Series(y_ts)

    used_baseline = False
    if not getattr(_m, "_model_loaded", False) or getattr(_m, "_predictor", None) is None:
        _require_real_model()
        used_baseline = True
        pred_df = _baseline_predict(x_df, pred_days)
    else:
        try:
            pred_df = _m._predictor.predict(
                df=x_df, x_timestamp=x_timestamp, y_timestamp=y_timestamp,
                pred_len=pred_days, T=0.7, top_k=10, top_p=0.95, sample_count=3,
                verbose=False,
            )
        except Exception as e:
            raise HTTPException(500, f"Prediction failed: {e}")

    current_price = float(df["close"].iloc[-1])
    pred_df = _sanitize_prediction_df(pred_df, current_price)
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

    payload = {
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
    return _with_prediction_contract(
        payload,
        code=code,
        mode="single",
        x_ts=x_timestamp,
        used_baseline=used_baseline,
    )


# ═══════════════════════════════════════════════════════════════
# P4: Kronos 元模型 (Kronos 60% + Aux 25% + Valuation 15%)
# ═══════════════════════════════════════════════════════════════

@router.post("/{code}/meta")
async def predict_stock_meta(code: str, pred_days: int = Query(20, ge=5, le=30)):
    """P4: Kronos 元模型融合 — 20维辅助特征加权."""
    if not _m._model_loaded: raise HTTPException(503, "Model not loaded")
    kline = _get_kline(code)
    if kline is None:
        raise HTTPException(
            404,
            {
                "message": f"No data for {code}",
                "fallback_reason": "source data missing: daily_kline has fewer than 30 rows",
            },
        )
    df, x_ts = kline
    x_df = df.iloc[-min(len(df),400):]
    x_ts2 = x_ts.iloc[-min(len(df),400):].reset_index(drop=True)
    y_ts = pd.bdate_range(start=x_ts2.iloc[-1]+pd.Timedelta(days=1), periods=pred_days)
    try:
        pred_df = _m._predictor.predict_fast(df=x_df, x_timestamp=x_ts2,
            y_timestamp=pd.Series(y_ts), pred_len=pred_days, verbose=False)
    except Exception as e: raise HTTPException(500, str(e))
    cp = float(df["close"].iloc[-1])
    pred_df = _sanitize_prediction_df(pred_df, cp)
    pc = float(pred_df["close"].iloc[-1])
    pr = round((pc/cp-1)*100, 2)
    feats = _get_auxiliary_features(code) or {}
    aux = _compute_auxiliary_score(feats) if feats else {"score":5,"signals":[]}
    vb = 2.0 if (5<(feats.get("pe",0)<25) and (feats.get("pb",0)<3)) else (-2.0 if feats.get("pe",0)>100 else 0)
    mr = round(pr*0.60 + (aux["score"]-5)*0.5*0.25 + vb*0.15, 2)
    payload = {"code":code,"mode":"meta","current_price":round(cp,2),
        "kronos_return_pct":pr,"meta_return_pct":mr,"auxiliary":aux}
    return _with_prediction_contract(
        payload,
        code=code,
        mode="meta",
        x_ts=x_ts2,
        used_baseline=False,
    )
