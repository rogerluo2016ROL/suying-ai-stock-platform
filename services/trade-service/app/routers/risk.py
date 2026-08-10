"""Risk Center routes — aggregated risk dashboard + risk-control write ops.

Design source: ``docs/design/New design/01 PRD 文档/10.0 风控中心详细设计.md``
- §4.2 聚合响应 schema (RiskDashboardResponse)
- §7 风控写操作 API + risk_audit_log 审计表 + MarketRegime schema

Scope notes (minimal-change constraints):
- Audit: doc §7 defines a dedicated append-only ``risk_audit_log`` table whose
  schema (actor/role/action/object_type/object_id/detail/tenant_id) differs from
  the existing ``audit_logs`` table in ``app/audit_log.py``, and ``VALID_ACTIONS``
  there does not cover the RISK_* actions — so this module keeps its own audit
  channel: always records to a module-level in-memory list + ``logger.info``,
  and best-effort persists to ``risk_audit_log`` when the table exists.
  TODO: alembic migration ``xxx_add_risk_audit_log`` (编号预留, 见 doc §7);
  once landed, AuditSummary should aggregate from the table instead of memory.
- Strategy pause/resume: strategy lifecycle is owned by strategy-service (8003);
  trade-service has no existing client for it, so pause/resume currently only
  records an in-memory risk override + audit and returns explicit mock
  semantics. TODO: wire to strategy-service (urllib + loop.run_in_executor).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from kronos_auth import require_role
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import routes
from app.broker_interface import OrderRequest, OrderSide, OrderType
from app.circuit_breaker import get_state
from app.database import get_db
from app.engine import get_engine
from app.platform_scope import resolve_trade_scope
from app.risk_gateway import pre_check
from app.routes import _PaperEngineAdapter

logger = logging.getLogger("trade-service.risk")

router = APIRouter(prefix="/api/v1/trade", tags=["risk"])

# Paper engine singleton (shared with app.routes).
engine = get_engine()

# ── Risk audit (doc §7 — in-memory + best-effort DB persist) ───────────

VALID_RISK_ACTIONS = frozenset({
    "RISK_PAUSE_STRATEGY",
    "RISK_RESUME_STRATEGY",
    "RISK_STOP_LOSS",
    "RISK_REDUCE_POSITION",
    "RISK_LIQUIDATE_ALL",
})

_risk_audit_entries: list[dict[str, Any]] = []

# Strategy risk overrides set by pause/resume (in-memory; see module docstring).
_strategy_risk_states: dict[str, dict[str, Any]] = {}


async def _record_risk_audit(
    db: AsyncSession,
    *,
    user: dict | None,
    action: str,
    object_type: str,
    object_id: str,
    detail: dict | None = None,
    tenant_id: str = "tenant-default",
) -> dict:
    """Record one risk-control audit entry — never blocks the main operation.

    Always appends to the in-memory list + logger; best-effort INSERT into
    ``risk_audit_log`` (doc §7). On DB failure: rollback + log, never re-raise.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": str(user.get("sub") or "system") if user else "system",
        "role": (user.get("role") or "system") if user else "system",
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "detail": detail or {},
        "tenant_id": tenant_id,
    }
    _risk_audit_entries.append(entry)
    logger.info(
        "RISK AUDIT %s %s/%s by actor=%s role=%s",
        action, object_type, object_id, entry["actor"], entry["role"],
    )

    try:
        await db.execute(
            text(
                """
                INSERT INTO risk_audit_log
                    (ts, actor, role, action, object_type, object_id,
                     detail, tenant_id, owner_user_id)
                VALUES
                    (:ts, :actor, :role, :action, :object_type, :object_id,
                     CAST(:detail AS jsonb), :tenant_id, :owner_user_id)
                """
            ),
            {
                "ts": entry["ts"],
                "actor": entry["actor"],
                "role": entry["role"],
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "detail": json.dumps(entry["detail"], ensure_ascii=False),
                "tenant_id": tenant_id,
                "owner_user_id": entry["actor"],
            },
        )
        await db.commit()
    except Exception:
        # Expected until the risk_audit_log migration lands — keep non-fatal.
        try:
            await db.rollback()
        except Exception:
            pass
        logger.warning(
            "risk_audit_log persist skipped (table missing or db unavailable) action=%s",
            action,
        )

    return entry


def _audit_summary() -> dict:
    """Aggregate AuditSummary from the in-memory risk audit list.

    TODO: doc §4.2 AuditSummary 还定义 placed/confirmed/rejected/
    circuitBreakerTriggers(订单流审计口径, 数据源为 audit_logs 表); 待
    risk_audit_log 落库后合并两个口径, 目前仅统计风控干预动作。
    """
    by_action: dict[str, int] = {}
    for e in _risk_audit_entries:
        by_action[e["action"]] = by_action.get(e["action"], 0) + 1
    return {
        "total": len(_risk_audit_entries),
        "byAction": by_action,
        "recent": _risk_audit_entries[-5:][::-1],
    }


# ── Request schemas ────────────────────────────────────────────────────


class RiskActionRequest(BaseModel):
    """Optional JSON body for pause/resume/stop-loss."""

    reason: str = Field("", description="Human-readable reason (audited)")


class ReducePositionRequest(BaseModel):
    """JSON body for POST /risk/position/{code}/reduce.

    Accepts both conventions: ``0<pct<=1`` = fraction (doc §7: 0.5=减半),
    ``1<pct<=100`` = percentage (100=清仓). Outside (0,100] → 422.
    """

    pct: float = Field(..., gt=0, le=100, description="0.5=减半 or 50=减50%")
    reason: str = Field("", description="Human-readable reason (audited)")


class LiquidateAllRequest(BaseModel):
    """JSON body for POST /risk/liquidate-all (高危操作, 后端二次校验)."""

    confirm: bool = Field(False, description="Must be true — server-enforced second confirmation")
    reason: str = Field("", description="Human-readable reason (audited)")


class RiskCheckItem(BaseModel):
    """One candidate order for POST /risk/check-batch."""

    code: str = Field(..., min_length=1, description="Stock code")
    action: str = Field(..., pattern="^(?i)(buy|sell)$", description="buy | sell")
    qty: int = Field(..., gt=0, description="Shares")
    price: float = Field(0, ge=0, description="Limit price; 0 = market")


class RiskCheckBatchRequest(BaseModel):
    """JSON body for POST /risk/check-batch."""

    items: list[RiskCheckItem] = Field(..., min_length=1)


# ── Dashboard helpers ──────────────────────────────────────────────────


def _to_position_risk(p, total_assets: float) -> dict:
    """Map an engine Position to doc §4.2 PositionRisk.

    TODO: name / stopLossPrice / distanceToStopPct / riskTags 需要股票名称、
    策略止损配置与公告/审计数据源, 目前返回占位值; riskScore 按 §7 统一口径
    仅计算已可得因子 (单票仓位 >25% +15)。
    """
    market_value = p.market_value or round(p.avg_cost * p.volume, 2)
    current_price = p.current_price or p.avg_cost
    exposure_pct = round(market_value / total_assets * 100, 2) if total_assets > 0 else 0.0
    risk_score = 15 if exposure_pct > 25 else 0
    return {
        "code": p.code,
        "name": p.code,  # TODO: 股票名称数据源未接入
        "quantity": p.volume,
        "avgCost": round(p.avg_cost, 2),
        "currentPrice": round(current_price, 2),
        "marketValue": round(market_value, 2),
        "pnl": round(p.pnl, 2),
        "pnlPct": round(p.pnl_pct, 2),
        "exposurePct": exposure_pct,
        "stopLossPrice": None,
        "distanceToStopPct": None,
        "riskTags": [],
        "riskScore": risk_score,
    }


def _mock_market_regime() -> dict:
    """MarketRegime per doc §7 schema — mock fallback.

    TODO: signal-service 尚未暴露符合 §7 schema 的 /market-regime HTTP 端点,
    落地后改为 urllib + loop.run_in_executor 跨服务拉取真实数据。
    """
    return {
        "black_swan": False,
        "sentiment_score": 50,
        "dimensions": {
            "trend": 50,
            "liquidity": 50,
            "volatility": 50,
            "breadth": 50,
            "fund_flow": 50,
            "valuation": 50,
            "sentiment": 50,
            "event_risk": 50,
        },
        "sector_risks": [],
        "key_events": [],
        "data_source": "mock",
    }


def _strategy_risk_list() -> list[dict]:
    """StrategyRiskStatus[] from in-memory risk overrides.

    TODO: 真实策略列表/状态归 strategy-service 所有, 接入后改为跨服务聚合;
    当前仅返回被风控 pause/resume 干预过的策略。
    """
    return [
        {
            "id": s["id"],
            "name": s["id"],  # TODO: 策略名称需 strategy-service 数据源
            "status": s["status"],
            "dailyLossPct": 0.0,
            "positionCount": 0,
            "riskEventCount": 0,
            "pausedReason": s.get("paused_reason"),
            "pausedTime": s.get("paused_time"),
        }
        for s in _strategy_risk_states.values()
    ]


# ── GET /risk-dashboard ────────────────────────────────────────────────


@router.get("/risk-dashboard")
async def risk_dashboard(
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Aggregate risk dashboard (doc §4.2): circuitBreaker + positions +
    strategies + marketRegime + auditSummary."""
    # 1. Circuit breaker (in-memory state from circuit_breaker.py)
    acct_id = routes._broker_config.get("account_id", "default")
    cb = await get_state(acct_id)
    threshold_pct = cb["threshold_pct"]
    daily_loss_pct = cb["daily_loss_pct"]
    budget_remaining_pct = (
        round(max(0.0, threshold_pct - daily_loss_pct) / threshold_pct * 100, 2)
        if threshold_pct > 0
        else 0.0
    )

    # 2. Account + positions (paper engine; TODO: live 模式接 _get_active_broker)
    account = engine.get_account()
    total_assets = account.total_capital
    positions = [_to_position_risk(p, total_assets) for p in engine.get_positions()]
    positions.sort(key=lambda p: p["riskScore"], reverse=True)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "circuitBreaker": {
            "state": cb["status"],
            "dailyLossPct": daily_loss_pct,
            "thresholdPct": threshold_pct,
            "budgetRemainingPct": budget_remaining_pct,
            "totalAssets": round(total_assets, 2),
            "availableFunds": round(account.available, 2),
        },
        "positions": positions,
        "strategies": _strategy_risk_list(),
        "marketRegime": _mock_market_regime(),
        "auditSummary": _audit_summary(),
    }


# ── Risk write ops (doc §7 — all audited) ──────────────────────────────


@router.post("/risk/strategy/{strategy_id}/pause")
async def pause_strategy(
    strategy_id: str,
    body: RiskActionRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """风控暂停策略 (doc §7, action=RISK_PAUSE_STRATEGY)."""
    scope = resolve_trade_scope(user, tenant_id=tenant_id)
    reason = (body.reason if body else "") or "risk control pause"
    _strategy_risk_states[strategy_id] = {
        "id": strategy_id,
        "status": "paused",
        "paused_reason": reason,
        "paused_time": datetime.now(timezone.utc).isoformat(),
    }
    await _record_risk_audit(
        db,
        user=user,
        action="RISK_PAUSE_STRATEGY",
        object_type="strategy",
        object_id=strategy_id,
        detail={"reason": reason},
        tenant_id=scope["tenant_id"],
    )
    return {
        "strategy_id": strategy_id,
        "status": "paused",
        "applied": "mock",  # TODO: 落到 strategy-service 策略启停接口
        "reason": reason,
    }


@router.post("/risk/strategy/{strategy_id}/resume")
async def resume_strategy(
    strategy_id: str,
    body: RiskActionRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """风控恢复策略 (doc §7, action=RISK_RESUME_STRATEGY)."""
    scope = resolve_trade_scope(user, tenant_id=tenant_id)
    reason = (body.reason if body else "") or "risk control resume"
    _strategy_risk_states[strategy_id] = {
        "id": strategy_id,
        "status": "active",
        "paused_reason": None,
        "paused_time": None,
    }
    await _record_risk_audit(
        db,
        user=user,
        action="RISK_RESUME_STRATEGY",
        object_type="strategy",
        object_id=strategy_id,
        detail={"reason": reason},
        tenant_id=scope["tenant_id"],
    )
    return {
        "strategy_id": strategy_id,
        "status": "active",
        "applied": "mock",  # TODO: 落到 strategy-service 策略启停接口
        "reason": reason,
    }


@router.post("/risk/position/{code}/stop-loss")
async def stop_loss_position(
    code: str,
    body: RiskActionRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """风控止损单 — 触发该持仓全量卖出 (doc §7, action=RISK_STOP_LOSS)."""
    scope = resolve_trade_scope(user, tenant_id=tenant_id)
    code_upper = code.upper()
    reason = (body.reason if body else "") or "risk stop-loss"

    position = engine.positions.get(code_upper)
    order_payload: dict | None = None
    if position is not None and position.volume > 0:
        order = engine.place_order(code_upper, "SELL", 0, position.volume)
        order_payload = {
            "order_id": order.id,
            "status": order.status,
            "filled_price": order.filled_price,
            "volume": order.volume,
        }
        applied = "executed"
    else:
        applied = "mock"  # 无持仓可卖, 仅记审计

    await _record_risk_audit(
        db,
        user=user,
        action="RISK_STOP_LOSS",
        object_type="position",
        object_id=code_upper,
        detail={"reason": reason, "applied": applied, "order": order_payload},
        tenant_id=scope["tenant_id"],
    )
    return {
        "code": code_upper,
        "applied": applied,  # executed=paper 引擎已卖出; mock=无持仓, TODO: live 券商持仓
        "order": order_payload,
        "reason": reason,
    }


@router.post("/risk/position/{code}/reduce")
async def reduce_position(
    code: str,
    body: ReducePositionRequest,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """风控减仓 (doc §7, action=RISK_REDUCE_POSITION).

    ``pct`` 约定: 0<pct<=1 按比例 (0.5=减半), 1<pct<=100 按百分比。
    """
    scope = resolve_trade_scope(user, tenant_id=tenant_id)
    code_upper = code.upper()
    fraction = body.pct / 100 if body.pct > 1 else body.pct

    position = engine.positions.get(code_upper)
    order_payload: dict | None = None
    sell_volume = 0
    if position is not None and position.volume > 0:
        sell_volume = min(position.volume, int(position.volume * fraction))
        if sell_volume > 0:
            order = engine.place_order(code_upper, "SELL", 0, sell_volume)
            order_payload = {
                "order_id": order.id,
                "status": order.status,
                "filled_price": order.filled_price,
                "volume": order.volume,
            }
    applied = "executed" if order_payload else "mock"  # mock=无持仓/减仓量为0

    await _record_risk_audit(
        db,
        user=user,
        action="RISK_REDUCE_POSITION",
        object_type="position",
        object_id=code_upper,
        detail={
            "pct": body.pct,
            "sell_volume": sell_volume,
            "applied": applied,
            "reason": body.reason,
            "order": order_payload,
        },
        tenant_id=scope["tenant_id"],
    )
    return {
        "code": code_upper,
        "pct": body.pct,
        "sell_volume": sell_volume,
        "applied": applied,  # TODO: live 券商持仓减仓
        "order": order_payload,
    }


@router.post("/risk/liquidate-all")
async def liquidate_all(
    body: LiquidateAllRequest | None = None,
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """一键清仓 (doc §7, action=RISK_LIQUIDATE_ALL) — 高危操作, 后端二次校验
    要求 body.confirm=true, 否则 409。"""
    if body is None or not body.confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "CONFIRMATION_REQUIRED",
                "message": "一键清仓为高危操作, 请携带 {\"confirm\": true} 二次确认",
            },
        )

    scope = resolve_trade_scope(user, tenant_id=tenant_id)
    orders: list[dict] = []
    # Snapshot first — place_order mutates engine.positions.
    for position in list(engine.get_positions()):
        if position.volume <= 0:
            continue
        order = engine.place_order(position.code, "SELL", 0, position.volume)
        orders.append({
            "order_id": order.id,
            "code": position.code,
            "status": order.status,
            "filled_price": order.filled_price,
            "volume": order.volume,
        })
    applied = "executed" if orders else "mock"  # mock=无持仓, TODO: live 券商清仓

    await _record_risk_audit(
        db,
        user=user,
        action="RISK_LIQUIDATE_ALL",
        object_type="account",
        object_id=scope["account_id"] or "default",
        detail={
            "reason": body.reason,
            "applied": applied,
            "liquidated": len(orders),
            "orders": orders,
        },
        tenant_id=scope["tenant_id"],
    )
    return {
        "applied": applied,
        "liquidated": len(orders),
        "orders": orders,
        "reason": body.reason,
    }


# ── POST /risk/check-batch ─────────────────────────────────────────────


@router.post("/risk/check-batch")
async def risk_check_batch(
    body: RiskCheckBatchRequest,
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """批量风险检查 — 逐项过 risk_gateway.pre_check, 返回每项 verdict。"""
    broker = _PaperEngineAdapter(engine)  # TODO: live 模式接 _get_active_broker
    account = await broker.get_account()
    positions = await broker.get_positions()

    results: list[dict] = []
    for item in body.items:
        order = OrderRequest(
            symbol=item.code.upper(),
            side=OrderSide(item.action.upper()),
            order_type=OrderType.LIMIT if item.price > 0 else OrderType.MARKET,
            quantity=item.qty,
            price=item.price,
        )
        verdict = await pre_check(order, account, positions)
        results.append({
            "code": item.code.upper(),
            "action": item.action.lower(),
            "qty": item.qty,
            "price": item.price,
            **verdict.to_dict(),
        })

    return {
        "total": len(results),
        "passed": all(r["passed"] for r in results),
        "results": results,
    }
