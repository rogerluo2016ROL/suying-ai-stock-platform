"""Kronos prediction factor — optional AI-powered scoring for screener engines.

Calls prediction-service (8002) to obtain Kronos 30-day K-line forecasts
and converts predicted return into a scoring factor.

Gated by USE_KRONOS_PREDICTION env var (default: false).
When prediction-service is unavailable, returns neutral scores gracefully.
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from typing import Optional

logger = logging.getLogger("kronos-factors.kronos_prediction")

# ── Configuration ──
PREDICTION_SERVICE_URL = os.environ.get(
    "PREDICTION_SERVICE_URL", "http://localhost:8002"
)
USE_KRONOS_PREDICTION = os.environ.get(
    "USE_KRONOS_PREDICTION", "false"
).lower() in ("1", "true", "yes")

# ── In-memory cache (per process, TTL = until next trading day) ──
_cache: dict[str, Optional[dict]] = {}
_cache_date: str = ""


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD for cache key."""
    import datetime
    return datetime.date.today().isoformat()


def _fetch_kronos_prediction(code: str, pred_days: int = 15) -> Optional[dict]:
    """Call prediction-service /fast endpoint for a single stock.

    Returns:
        dict with pred_return_pct, trend, current_price, pred_last_close
        or None if prediction is unavailable.
    """
    url = f"{PREDICTION_SERVICE_URL}/api/v1/prediction/{code}/fast?pred_days={pred_days}"
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data
    except urllib.error.HTTPError as e:
        if e.code == 503:
            logger.debug("Kronos model not loaded, skipping prediction for %s", code)
        elif e.code == 404:
            logger.debug("No K-line data for %s, skipping prediction", code)
        else:
            logger.debug("Prediction API error for %s: %s", code, e)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        logger.debug("Prediction service unreachable: %s", e)
    except Exception as e:
        logger.debug("Unexpected prediction error for %s: %s", code, e)
    return None


def get_kronos_prediction(code: str, force_refresh: bool = False) -> Optional[dict]:
    """Get Kronos prediction for a stock, with daily cache.

    Returns cached result if available for today; otherwise fetches from API.
    Gracefully handles all errors, returning None when unavailable.

    Args:
        code: 6-digit stock code
        force_refresh: bypass cache and force API call

    Returns:
        dict with pred_return_pct, trend, etc., or None
    """
    if not USE_KRONOS_PREDICTION:
        return None

    global _cache, _cache_date
    today = _today_str()

    # Reset cache for new trading day
    if _cache_date != today:
        _cache = {}
        _cache_date = today

    if not force_refresh and code in _cache:
        return _cache[code]

    result = _fetch_kronos_prediction(code)
    _cache[code] = result
    return result


def score_kronos_prediction(code: str) -> dict:
    """Compute Kronos prediction factor score (0-10 scale).

    Scoring logic:
      - pred_return_pct >= 10%  → score 10 (strong bullish)
      - pred_return_pct >= 5%   → score 8
      - pred_return_pct >= 2%   → score 6
      - pred_return_pct >= 0%   → score 4 (weak bullish)
      - pred_return_pct >= -2%  → score 3 (neutral)
      - pred_return_pct >= -5%  → score 2 (weak bearish)
      - pred_return_pct < -5%   → score 1 (strong bearish)
      - unavailable             → score 5 (neutral, no signal)

    Returns:
        {"score": float, "pred_return_pct": float, "trend": str, "available": bool}
    """
    pred = get_kronos_prediction(code)
    if pred is None:
        return {"score": 5.0, "pred_return_pct": 0.0, "trend": "N/A", "available": False}

    ret = pred.get("pred_return_pct", 0)
    if ret >= 10:
        score = 10.0
    elif ret >= 5:
        score = 8.0
    elif ret >= 2:
        score = 6.0
    elif ret >= 0:
        score = 4.0
    elif ret >= -2:
        score = 3.0
    elif ret >= -5:
        score = 2.0
    else:
        score = 1.0

    return {
        "score": score,
        "pred_return_pct": ret,
        "trend": pred.get("trend", "N/A"),
        "pred_last_close": pred.get("pred_last_close"),
        "current_price": pred.get("current_price"),
        "available": True,
    }


def get_kronos_prediction_batch(codes: list[str], max_concurrent: int = 5) -> dict[str, dict]:
    """Fetch Kronos predictions for a batch of stocks (sequential with delay).

    To avoid overwhelming prediction-service, fetches sequentially with a small
    delay between requests. Results are cached per stock for the day.

    Args:
        codes: list of 6-digit stock codes
        max_concurrent: unused (sequential mode for safety)

    Returns:
        {code: score_dict} mapping
    """
    results = {}
    for i, code in enumerate(codes):
        try:
            results[code] = score_kronos_prediction(code)
        except Exception as e:
            logger.debug("Batch prediction failed for %s: %s", code, e)
            results[code] = {"score": 5.0, "pred_return_pct": 0.0,
                             "trend": "N/A", "available": False}
        # Brief delay between requests to avoid overwhelming the service
        if i < len(codes) - 1:
            time.sleep(0.1)
    return results
