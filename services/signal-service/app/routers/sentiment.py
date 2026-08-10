"""Market sentiment routes — /signal/sentiment-{index,history,alerts}.

设计依据: docs/design/New design/01 PRD 文档/1.1 智能看板-市场情绪详细设计.md
- 评分/等级/预警纯逻辑在 app/sentiment.py (无 IO, 可单测)
- 数据来源优先级:
  1. kronos_factors market_regime_v2 八维模型 (PG, 真实)
  2. daily_kline / stk_limit / stocks 聚合推导 (PG, 真实)
  3. 确定性 mock (无 DB 时兜底, 标 TODO)
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Query
from kronos_auth import get_current_user_jwt

from app._shared import router
from app.sentiment import (
    ALERT_THRESHOLDS,
    DIMENSION_DEFS,
    build_alerts,
    clamp_score,
    combine_dimensions,
    derive_daily_score,
    level_label,
    operation_hint,
    score_to_level,
)

logger = logging.getLogger("signal-service.routes")

_MOCK_HINT = "mock (TODO: 无 PG 数据时的确定性兜底, 接入 sentiment_snapshots 快照表后移除)"


# ── 数据采集 (PG via kronos-factors _get_db, 失败返回 None/[]) ──

def _fetch_daily_stats(days: int) -> list[dict]:
    """逐日全市场聚合: trade_date / avg_chg / up_count / down_count / total (倒序)."""
    from kronos_factors.scorer._db_stub import _get_db

    sql = f"""
        SELECT trade_date,
               AVG(change_pct) AS avg_chg,
               SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) AS up_count,
               SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) AS down_count,
               COUNT(*) AS total
        FROM daily_kline
        WHERE change_pct IS NOT NULL
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT {int(days)}
    """
    try:
        with _get_db() as d:
            return [dict(r) for r in d.execute(sql).fetchall()]
    except Exception as e:
        logger.warning("sentiment daily stats query failed: %s", e)
        return []


def _fetch_limit_counts() -> dict:
    """最新交易日涨跌停统计 (stk_limit). 炸板数据无源, 置 0 并标 TODO."""
    from kronos_factors.scorer._db_stub import _get_db

    sql = """
        SELECT MAX(trade_date) AS trade_date,
               SUM(CASE WHEN LOWER(COALESCE(limit_status,'')) LIKE '%up%' THEN 1 ELSE 0 END) AS up_count,
               SUM(CASE WHEN LOWER(COALESCE(limit_status,'')) LIKE '%down%' THEN 1 ELSE 0 END) AS down_count
        FROM stk_limit
        WHERE trade_date = (SELECT MAX(trade_date) FROM stk_limit)
    """
    try:
        with _get_db() as d:
            row = d.execute(sql).fetchone()
            if row:
                return {
                    "trade_date": str(row.get("trade_date") or ""),
                    "up_count": int(row.get("up_count") or 0),
                    "down_count": int(row.get("down_count") or 0),
                }
    except Exception as e:
        logger.warning("sentiment limit stats query failed: %s", e)
    return {"trade_date": "", "up_count": 0, "down_count": 0}


def _fetch_sector_sentiment() -> list[dict]:
    """板块情绪: daily_kline 按 stocks.industry 聚合 (PRD §2 板块热力图)."""
    from kronos_factors.scorer._db_stub import _get_db

    sql = """
        SELECT COALESCE(s.industry, '其他') AS sector,
               COUNT(*) AS total,
               SUM(CASE WHEN d.change_pct > 0 THEN 1 ELSE 0 END) AS up_count,
               AVG(d.change_pct) AS avg_chg
        FROM daily_kline d
        JOIN stocks s ON s.code = d.code
        WHERE d.trade_date = (SELECT MAX(trade_date) FROM daily_kline WHERE close IS NOT NULL)
          AND d.change_pct IS NOT NULL
        GROUP BY COALESCE(s.industry, '其他')
        ORDER BY AVG(d.change_pct) DESC
        LIMIT 30
    """
    try:
        with _get_db() as d:
            rows = d.execute(sql).fetchall()
        sectors = []
        for r in rows:
            total = int(r.get("total") or 0)
            up = int(r.get("up_count") or 0)
            avg_chg = float(r.get("avg_chg") or 0)
            sectors.append({
                "sector": r.get("sector") or "其他",
                "score": clamp_score((avg_chg + 3.0) / 6.0 * 100.0),
                "up_pct": round(up / total * 100.0, 1) if total else 0.0,
                "avg_chg": round(avg_chg, 2),
            })
        return sectors
    except Exception as e:
        logger.warning("sentiment sector query failed: %s", e)
        return []


# ── 当前情绪分计算 (index / alerts 共用) ──

def _current_sentiment() -> dict:
    """返回 {score, change, trade_date, risk_score, dimensions, data_source}.

    dimensions: 8 维 {score, label, weight}, 无数据维度 score=None.
    """
    dimensions = {key: {"score": None, "label": label, "weight": weight}
                  for key, (label, weight) in DIMENSION_DEFS.items()}
    score, risk_score, data_source = None, None, None

    # 1) 真实: market_regime_v2 八维模型
    try:
        from kronos_factors.scorer.market_regime import get_market_regime_v2
        regime = get_market_regime_v2()
        regime_dims = regime.get("dimensions") or {}
        for key in DIMENSION_DEFS:
            entry = regime_dims.get(key)
            if isinstance(entry, dict) and entry.get("score") is not None:
                dimensions[key]["score"] = clamp_score(entry["score"])
        risk_entry = regime_dims.get("risk_events") or {}
        risk_score = risk_entry.get("score")
        if regime_dims:
            score = regime.get("score")
            data_source = "market_regime_v2 (kronos-factors 八维风向感知)"
    except Exception as e:
        logger.warning("market_regime_v2 unavailable: %s", e)

    # 2) 推导: daily_kline 当日聚合
    stats = _fetch_daily_stats(2)
    trade_date = str(stats[0]["trade_date"])[:10] if stats else ""
    change = 0.0
    if score is None and stats:
        limits = _fetch_limit_counts()
        score = derive_daily_score(
            float(stats[0].get("avg_chg") or 0),
            int(stats[0].get("up_count") or 0),
            int(stats[0].get("down_count") or 0),
            int(stats[0].get("total") or 0),
            limits["up_count"], limits["down_count"],
        )
        data_source = "derived: PG daily_kline 全市场聚合推导"
    if score is not None and len(stats) > 1:
        prev = derive_daily_score(
            float(stats[1].get("avg_chg") or 0),
            int(stats[1].get("up_count") or 0),
            int(stats[1].get("down_count") or 0),
            int(stats[1].get("total") or 0),
        )
        change = round(score - prev, 1)

    # 3) mock 兜底 (无 DB)
    if score is None:
        score = 50.0
        data_source = _MOCK_HINT

    return {
        "score": clamp_score(score),
        "change": change,
        "trade_date": trade_date,
        "risk_score": risk_score,
        "dimensions": dimensions,
        "data_source": data_source,
    }


def _mock_history(days: int) -> list[dict]:
    """确定性历史序列兜底 (TODO: 接入 sentiment_snapshots 快照表后由真实历史替换)."""
    today = datetime.now(timezone.utc).date()
    points = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        digest = hashlib.sha256(f"sentiment:{day}".encode()).digest()
        score = clamp_score(25.0 + digest[0] / 255.0 * 50.0)  # 25-75 区间伪随机
        level = score_to_level(score)
        points.append({"date": day, "trade_date": day, "score": score,
                       "label": level_label(level), "level": level})
    return points


# ── 端点 ──

@router.get("/sentiment-index")
async def sentiment_index(user: dict = Depends(get_current_user_jwt)):
    """综合情绪指数: score/label/八维分项/板块情绪/涨跌停统计/操作基调."""
    cur = _current_sentiment()
    score, change = cur["score"], cur["change"]
    level = score_to_level(score, cur["risk_score"])

    limits = _fetch_limit_counts()
    stats = _fetch_daily_stats(1)
    up_stocks = int(stats[0].get("up_count") or 0) if stats else 0
    down_stocks = int(stats[0].get("down_count") or 0) if stats else 0

    change_direction = "up" if change > 0.5 else ("down" if change < -0.5 else "flat")
    hint = operation_hint(level)

    return {
        "trade_date": cur["trade_date"],
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "score": score,
        "label": level_label(level),
        "level": level,
        "change": change,
        "change_direction": change_direction,
        "confidence": round(min(100, max(20, abs(score - 50) * 2)), 1),
        "dimensions": cur["dimensions"],
        "sector_sentiment": _fetch_sector_sentiment(),
        "limit_stats": {
            "up_count": limits["up_count"],
            "down_count": limits["down_count"],
            # TODO: 炸板数/炸板率需要盘中炸板数据源, 暂置 0
            "blow_count": 0,
            "blow_rate": 0.0,
            # TODO: 盘中涨停数变化趋势需要分钟级数据, 暂空
            "up_count_trend": [],
            "down_count_trend": [],
            "up_stocks": up_stocks,
            "down_stocks": down_stocks,
        },
        "operation_hint": hint["hint"],
        "position_hint": hint["position"],
        "alerts": build_alerts(score, change, cur["trade_date"]),
        "data_source": cur["data_source"],
        "disclaimer": "市场情绪指数为量化模型计算结果，反映历史统计规律，不构成投资建议。极端情绪区间不代表市场必然反转。",
    }


@router.get("/sentiment-history")
async def sentiment_history(
    days: int = Query(30, ge=1, le=120, description="回溯天数 (1-120)"),
    user: dict = Depends(get_current_user_jwt),
):
    """历史情绪序列: date + score + label (升序)."""
    stats = _fetch_daily_stats(days)
    if stats:
        points = []
        for row in reversed(stats):  # 倒序 → 升序
            day = str(row.get("trade_date"))[:10]
            score = derive_daily_score(
                float(row.get("avg_chg") or 0),
                int(row.get("up_count") or 0),
                int(row.get("down_count") or 0),
                int(row.get("total") or 0),
            )
            level = score_to_level(score)
            points.append({"date": day, "trade_date": day, "score": score,
                           "label": level_label(level), "level": level})
        data_source = "derived: PG daily_kline 逐日聚合 (TODO: 迁移至 sentiment_snapshots 快照表)"
    else:
        points = _mock_history(days)
        data_source = _MOCK_HINT

    return {"days": days, "count": len(points), "history": points, "data_source": data_source}


@router.get("/sentiment-alerts")
async def sentiment_alerts(user: dict = Depends(get_current_user_jwt)):
    """情绪预警: 过热 / 冰点 / 急转三类规则评估."""
    cur = _current_sentiment()
    alerts = build_alerts(cur["score"], cur["change"], cur["trade_date"])
    return {
        "trade_date": cur["trade_date"],
        "score": cur["score"],
        "change": cur["change"],
        "thresholds": ALERT_THRESHOLDS,
        "triggered_count": sum(1 for a in alerts if a["triggered"]),
        "alerts": alerts,
        "data_source": cur["data_source"],
    }
