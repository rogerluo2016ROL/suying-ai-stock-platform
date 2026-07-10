"""Backtest API routes — PG 直读, 滚动窗口前向回测 + 龙头战法 + 可转债."""

import logging
import os
import sys
from datetime import date, timedelta

import numpy as np
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])
logger = logging.getLogger("backtest-service")

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

# Ensure kronos-factors is importable
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages"))
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)

# ── Factor definitions (from screening_top50.py) ──
FACTORS = {
    "momentum": "五因子-动量",
    "volume": "五因子-量能",
    "quality": "五因子-质量",
    "composite": "综合评分",
    "technical": "五因子-技术",
    "margin": "融资融券",
    "moneyflow": "资金流向",
    "daily_basic": "每日指标",
    "financial": "财报质量",
    "hard_tech": "硬科技",
    "growth": "成长性",
    "short_term": "短线技术",
    "long_term": "长线价值",
    "por": "POR估值",
}


def _get_pg():
    """Get sync PG connection."""
    import psycopg2
    return psycopg2.connect(PG_URL)


def _compute_ic(predictions, actuals):
    """Spearman rank IC."""
    from scipy import stats
    valid = ~(np.isnan(predictions) | np.isnan(actuals))
    if valid.sum() < 10:
        return 0.0
    ic, _ = stats.spearmanr(predictions[valid], actuals[valid])
    return 0.0 if np.isnan(ic) else float(ic)


@router.get("/factors")
async def list_factors():
    """List available factors."""
    return {
        "factors": [{"id": k, "name": v} for k, v in FACTORS.items()],
        "count": len(FACTORS),
    }


@router.post("/run")
async def run_backtest(
    mode: str = Query("all", description="long/short/all"),
    windows: int = Query(3, ge=1, le=12),
    top_n: int = Query(30, ge=10, le=100),
    forward_days: int = Query(60, ge=20, le=252),
):
    """Fail closed until evidence adapters are implemented."""
    raise HTTPException(status_code=409, detail={"code": "MODEL_BACKTEST_NOT_IMPLEMENTED", "message": "真实因子快照与复权未来收益适配器尚未完成"})


@router.post("/calibrate")
async def calibrate_weights(mode: str = Query("all")):
    """基于近期 IC 校准因子权重."""
    raise HTTPException(status_code=409, detail={"code": "MODEL_CALIBRATION_NOT_IMPLEMENTED", "message": "缺少真实观测证据，未写入 factor_weights"})
@router.get("/factor-evidence")
async def factor_evidence(model_key: str = Query(...)):
    return {"status": "unsupported", "observations": 0, "factors": [], "correlations": [], "deciles": [],
            "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"]}

@router.post("/compare")
async def compare_strategies(strategy_ids: list[str] = Query(default=["momentum", "quality"]), start_date: str = Query(default=None), end_date: str = Query(default=None)):
    raise HTTPException(status_code=422, detail={"code": "INSUFFICIENT_EVIDENCE", "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"]})
@router.post("/run-leader")
async def run_leader_backtest(
    mode: str = Query("leader_scalp", description="leader_scalp/leader_intraday/leader_auction/leader_closing"),
    windows: int = Query(3, ge=1, le=12),
    top_n: int = Query(20, ge=5, le=50),
    forward_days: int = Query(5, ge=1, le=20),
):
    """龙头战法回测 — 使用 kronos-factors leader engine 进行滚动窗口前向回测。"""
    try:
        from kronos_factors.engine import run_leader_screening

        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT trade_date FROM daily_kline WHERE volume > 0 ORDER BY trade_date")
        dates = [r[0] for r in cur.fetchall()]
        conn.close()

        if len(dates) < forward_days + 20:
            return {"status": "error", "message": "Not enough trading data"}

        step = max(5, (len(dates) - forward_days - 20) // windows)
        results, all_returns = [], []

        for i in range(windows):
            idx = i * step
            if idx + forward_days + 20 >= len(dates):
                break
            sel_date = dates[idx]
            fwd_date_end = dates[min(idx + forward_days, len(dates) - 1)]

            try:
                raw = run_leader_screening(str(sel_date), top_n=top_n)
                picks = raw[0] if isinstance(raw, tuple) else raw
                if not picks:
                    continue
            except Exception as e:
                logger.debug("Leader screening failed for %s: %s", sel_date, e)
                continue

            conn2 = _get_pg()
            cur2 = conn2.cursor()
            fwd_rets = []
            for pk in picks[:top_n]:
                code = pk.get("code", "")
                if not code:
                    continue
                cur2.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (code, fwd_date_end))
                r1 = cur2.fetchone()
                cur2.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (code, sel_date))
                r2 = cur2.fetchone()
                if r1 and r2 and r2[0] > 0:
                    fwd_rets.append(float((r1[0] - r2[0]) / r2[0] * 100))
            conn2.close()

            if fwd_rets:
                results.append({
                    "window": i + 1, "sel_date": str(sel_date), "fwd_date": str(fwd_date_end),
                    "picks": len(picks), "avg_return_pct": round(float(np.mean(fwd_rets)), 2),
                    "hit_rate_pct": round(float(np.mean(np.array(fwd_rets) > 0)) * 100, 1),
                })
                all_returns.extend(fwd_rets)

        if not results:
            return {
                "status": "ok", "mode": mode, "windows": 0,
                "summary": {"avg_return": 0, "hit_rate": 0, "total_trades": 0},
                "details": [],
                "message": "No valid windows — market conditions may not yield leader picks"
            }

        return {
            "status": "ok", "mode": mode, "windows": len(results),
            "summary": {
                "avg_return": round(float(np.mean(all_returns)), 2) if all_returns else 0,
                "hit_rate": round(float(np.mean(np.array(all_returns) > 0)) * 100, 1) if all_returns else 0,
                "total_trades": len(all_returns),
            },
            "details": results,
        }
    except Exception as e:
        logger.error("Leader backtest failed: %s", e)
        raise HTTPException(500, str(e))


@router.post("/run-cb")
async def run_cb_backtest(
    mode: str = Query("cb_floor", description="cb_floor/cb_intraday/cb_auction/cb_auction_t0/cb_auction_t0_v2/cb_auction_t0_v2_1"),
    windows: int = Query(3, ge=1, le=12),
    top_n: int = Query(20, ge=5, le=50),
    forward_days: int = Query(5, ge=1, le=20),
):
    """可转债回测 — 使用 kronos-factors CB engine 进行滚动窗口前向回测。"""
    try:
        conn = _get_pg()
        cur = conn.cursor()
        try:
            cur.execute("SELECT DISTINCT trade_date FROM cb_daily ORDER BY trade_date")
            dates = [r[0] for r in cur.fetchall()]
        except Exception:
            cur.execute("SELECT DISTINCT trade_date FROM daily_kline WHERE volume > 0 ORDER BY trade_date")
            dates = [r[0] for r in cur.fetchall()]
        conn.close()

        if len(dates) < forward_days + 20:
            return {"status": "error", "message": "Not enough CB data"}

        step = max(5, (len(dates) - forward_days - 20) // windows)
        results, all_returns = [], []

        for i in range(windows):
            idx = i * step
            if idx + forward_days + 20 >= len(dates):
                break
            sel_date = dates[idx]
            fwd_date_end = dates[min(idx + forward_days, len(dates) - 1)]

            try:
                if mode == "cb_floor":
                    from kronos_factors.engine.cb_floor import CbFloorEngine
                    engine = CbFloorEngine()
                elif mode == "cb_intraday":
                    from kronos_factors.engine.cb_intraday import CbIntradayEngine
                    engine = CbIntradayEngine()
                elif mode == "cb_auction_t0":
                    from kronos_factors.engine.cb_auction_t0 import CbAuctionT0Engine
                    engine = CbAuctionT0Engine()
                elif mode == "cb_auction_t0_v2":
                    from kronos_factors.engine.cb_auction_t0 import CbAuctionT0V2Engine
                    engine = CbAuctionT0V2Engine()
                elif mode == "cb_auction_t0_v2_1":
                    from kronos_factors.engine.cb_auction_t0 import CbAuctionT0V21Engine
                    engine = CbAuctionT0V21Engine()
                else:
                    from kronos_factors.engine.cb_auction import CbAuctionEngine
                    engine = CbAuctionEngine()
                raw_result = engine.run(trade_date=str(sel_date), top_n=top_n)
                engine.close()
                picks = raw_result.get("bonds", []) if mode in ("cb_auction_t0", "cb_auction_t0_v2", "cb_auction_t0_v2_1") and isinstance(raw_result, dict) else raw_result
                if not picks:
                    continue
            except Exception as e:
                logger.debug("CB screening failed for %s: %s", sel_date, e)
                continue

            conn2 = _get_pg()
            cur2 = conn2.cursor()
            fwd_rets = []
            for pk in picks[:top_n]:
                code = pk.get("code", "") or pk.get("ts_code", "")
                if not code:
                    continue
                for col in ("ts_code", "code"):
                    try:
                        cur2.execute(f"SELECT close FROM cb_daily WHERE {col}=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (str(code), fwd_date_end))
                        r1 = cur2.fetchone()
                        cur2.execute(f"SELECT close FROM cb_daily WHERE {col}=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (str(code), sel_date))
                        r2 = cur2.fetchone()
                        break
                    except Exception:
                        continue
                if r1 and r2 and r2[0] > 0:
                    fwd_rets.append(float((r1[0] - r2[0]) / r2[0] * 100))
            conn2.close()

            if fwd_rets:
                results.append({
                    "window": i + 1, "sel_date": str(sel_date), "fwd_date": str(fwd_date_end),
                    "picks": len(picks), "avg_return_pct": round(float(np.mean(fwd_rets)), 2),
                    "hit_rate_pct": round(float(np.mean(np.array(fwd_rets) > 0)) * 100, 1),
                })
                all_returns.extend(fwd_rets)

        if not results:
            return {
                "status": "ok", "mode": mode, "windows": 0,
                "summary": {"avg_return": 0, "hit_rate": 0, "total_trades": 0},
                "details": [],
                "message": "No valid windows for CB backtest"
            }

        return {
            "status": "ok", "mode": mode, "windows": len(results),
            "summary": {
                "avg_return": round(float(np.mean(all_returns)), 2) if all_returns else 0,
                "hit_rate": round(float(np.mean(np.array(all_returns) > 0)) * 100, 1) if all_returns else 0,
                "total_trades": len(all_returns),
            },
            "details": results,
        }
    except Exception as e:
        logger.error("CB backtest failed: %s", e)
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# 秋神午后回测 (V1.1: 历史日K线模式)
# ═══════════════════════════════════════════════════════════════

@router.post("/run-afternoon")
async def run_afternoon_backtest(
    windows: int = Query(6, ge=1, le=12),
    top_n: int = Query(15, ge=5, le=30),
    forward_days: int = Query(5, ge=1, le=20),
):
    """秋神午后回测 — 自动使用日K线历史数据."""
    try:
        from kronos_factors.engine.leader_afternoon import run_afternoon_screening

        conn = _get_pg()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT trade_date FROM daily_kline WHERE volume > 0 ORDER BY trade_date")
        all_dates = [r[0] for r in cur.fetchall()]
        conn.close()

        recent = [d for d in all_dates if d >= (all_dates[-1] - timedelta(days=365))]
        step = max(3, (len(recent) - forward_days - 5) // windows)
        results = []
        all_returns = []

        for i in range(windows):
            idx = i * step
            if idx + forward_days + 5 >= len(recent):
                break
            sel_date = recent[idx]
            fwd_date = recent[min(idx + forward_days, len(recent) - 1)]

            try:
                picks, _ = run_afternoon_screening(
                    str(sel_date)[:10], time_slot="14:30", top_n=top_n, env_check=False
                )
                if not picks:
                    continue
            except Exception as e:
                logger.debug("Afternoon failed at %s: %s", sel_date, e)
                continue

            conn2 = _get_pg()
            cur2 = conn2.cursor()
            fwd_rets = []
            for pk in picks[:top_n]:
                code = pk.get("code", "")
                if not code: continue
                cur2.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (code, fwd_date))
                r1 = cur2.fetchone()
                cur2.execute("SELECT close FROM daily_kline WHERE code=%s AND trade_date <= %s ORDER BY trade_date DESC LIMIT 1", (code, sel_date))
                r2 = cur2.fetchone()
                if r1 and r2 and r2[0] > 0:
                    fwd_rets.append(float((r1[0] - r2[0]) / r2[0] * 100))
            conn2.close()

            if fwd_rets:
                results.append({
                    "window": i + 1, "sel_date": str(sel_date)[:10], "fwd_date": str(fwd_date)[:10],
                    "picks": len(picks),
                    "avg_return_pct": round(float(np.mean(fwd_rets)), 2),
                    "hit_rate_pct": round(float(np.mean(np.array(fwd_rets) > 0)) * 100, 1),
                })
                all_returns.extend(fwd_rets)

        if not results:
            return {"status": "ok", "mode": "leader_afternoon", "windows": 0,
                    "summary": {"avg_return": 0, "hit_rate": 0, "total_trades": 0},
                    "message": "No valid windows"}

        return {
            "status": "ok", "mode": "leader_afternoon", "windows": len(results),
            "summary": {
                "avg_return": round(float(np.mean(all_returns)), 2) if all_returns else 0,
                "hit_rate": round(float(np.mean(np.array(all_returns) > 0)) * 100, 1) if all_returns else 0,
                "total_trades": len(all_returns),
            },
            "details": results,
        }
    except Exception as e:
        logger.error("Afternoon backtest failed: %s", e)
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════════════════════════════
# P4: 因子 IC 衰减追踪 — 动态权重调整
# ═══════════════════════════════════════════════════════════════

@router.get("/ic-decay")
async def ic_decay_tracking(
    lookback: int = Query(60, ge=20, le=120),
    mode: str = Query("short", description="short/all/long"),
):
    """P4: 追踪因子 IC 滚动衰减, 输出动态权重建议.

    对最近 N 个交易日的因子 IC 做滚动分析:
      - IC 连续 10 日为正 → weight ×1.2
      - IC 连续 10 日为负 → weight ×0.5 (半衰)
      - IC 波动率 > 2×历史均值 → 冻结权重

    Returns: 每个因子的当前状态和调整建议.
    """
    raise HTTPException(status_code=409, detail={"code": "MODEL_EVIDENCE_NOT_IMPLEMENTED", "message": "缺少真实因子快照与未来复权收益证据"})
    try:
        import psycopg2
        from datetime import date as dt_date
        conn = psycopg2.connect(PG_URL, connect_timeout=5)
        cur = conn.cursor()

        # Get trading dates
        cur.execute(
            "SELECT DISTINCT cal_date FROM trade_cal WHERE is_open=1 "
            "AND cal_date <= CURRENT_DATE ORDER BY cal_date DESC LIMIT %s", (lookback,))
        trade_dates = [str(r[0]) for r in cur.fetchall()]
        conn.close()

        if len(trade_dates) < 20:
            return {"status": "error", "message": "Insufficient trading days"}

        # Factor list by mode
        factors_map = {
            "short": ["momentum", "volume", "margin", "moneyflow", "top_list", "top_inst", "events"],
            "all": ["composite", "technical", "quality", "daily_basic", "financial", "growth", "events"],
            "long": ["long_term", "growth", "hard_tech", "financial", "daily_basic", "por", "events"],
        }
        factors = factors_map.get(mode, factors_map["short"])

        result = {"mode": mode, "lookback_days": lookback,
                  "latest_date": trade_dates[0], "factors": {}}

        for factor in factors:
            result["factors"][factor] = {
                "status": "unavailable",
                "recommendation": "insufficient_evidence",
                "missing_requirements": ["observed_factor_snapshots", "future_adjusted_returns"],
            }

        return result
    except Exception as e:
        raise HTTPException(500, str(e))
