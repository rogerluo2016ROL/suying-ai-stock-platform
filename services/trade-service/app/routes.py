"""Trade API routes — paper trading + live trading via broker interface.

Existing paper-trading endpoints (POST /order, DELETE /order/{id},
GET /orders, GET /positions, GET /account, GET /pnl) are unchanged.

New live-trading endpoints (per PRD AC-11.1~11.9):
  PUT  /api/v1/trade/mode            — switch paper/live
  POST /api/v1/trade/broker/connect  — connect to broker
  GET  /api/v1/trade/broker/status   — broker connection status
  GET  /api/v1/trade/audit-logs      — query audit trail
  POST /api/v1/trade/circuit-breaker/reset  — manual reset
  GET  /api/v1/trade/circuit-breaker        — breaker status
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Depends, Body
from kronos_auth import require_role
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log import record as record_audit, query as query_audit
from app.decision_context_store import (
    record_once as record_decision_context_once,
    query as query_decision_contexts,
)
from app.order_store import record as record_trade_order, query as query_trade_orders
from app.risk_verdict_store import record as record_risk_verdict, query as query_risk_verdicts
from app.database import get_db
from app.engine import get_engine
from app.broker_interface import (
    BrokerInterface,
    OrderRequest,
    OrderSide,
    OrderType,
)
from app.risk_gateway import pre_check
from app.circuit_breaker import check_daily_loss, reset, get_state, can_trade, record_probe
from app.schemas import PlaceOrderRequest, BrokerConnectRequest
from app.platform_scope import (
    build_order_scope,
    build_paper_account_view,
    build_risk_verdict,
    resolve_trade_scope,
)

logger = logging.getLogger("trade-service.routes")

router = APIRouter(prefix="/api/v1/trade", tags=["trade"])

# ── Engine / Broker singletons ─────────────────────────────────────────
engine = get_engine()          # PaperTradingEngine (existing, unchanged)

_live_broker: BrokerInterface | None = None
_current_mode: str = os.environ.get("TRADE_MODE", "paper")
_broker_config: dict = {}
_broker_connected_at: datetime | None = None


def _get_live_broker() -> BrokerInterface | None:
    return _live_broker


def _get_active_broker() -> BrokerInterface:
    """Return the broker for the current global mode."""
    if _current_mode == "live" and _live_broker is not None:
        return _live_broker
    # Fallback: wrap paper engine in a simple adapter
    return _PaperEngineAdapter(engine)


class _PaperEngineAdapter:
    """Thin adapter so the paper engine can be used where BrokerInterface is expected."""

    def __init__(self, eng):
        self._eng = eng

    async def place_order(self, order: OrderRequest):
        from app.broker_interface import OrderResult, OrderStatus
        o = self._eng.place_order(
            code=order.symbol,
            direction=order.side.value,
            price=order.price,
            volume=order.quantity,
        )
        status = OrderStatus(o.status)
        return OrderResult(
            order_id=o.id,
            broker_order_id="",
            status=status,
            filled_qty=o.volume if status == OrderStatus.FILLED else 0,
            filled_avg_price=o.filled_price,
            message=f"{status.value} (paper)",
        )

    async def cancel_order(self, order_id: str):
        from app.broker_interface import CancelResult
        ok = self._eng.cancel_order(order_id)
        return CancelResult(order_id=order_id, success=ok, message="cancelled" if ok else "not found")

    async def get_positions(self):
        from app.broker_interface import Position as BIPosition
        return [
            BIPosition(
                symbol=p.code, quantity=p.volume, avg_cost=p.avg_cost,
                current_price=p.current_price, market_value=p.market_value,
                pnl=p.pnl, pnl_pct=p.pnl_pct,
            )
            for p in self._eng.get_positions()
        ]

    async def get_account(self):
        from app.broker_interface import AccountInfo
        a = self._eng.get_account()
        return AccountInfo(
            total_assets=a.total_capital,
            available=a.available,
            frozen=0.0,
            market_value=a.market_value,
            total_pnl=a.total_pnl,
            daily_pnl=a.daily_pnl,
        )

    async def sync(self):
        from app.broker_interface import SyncResult
        pos = await self.get_positions()
        acc = await self.get_account()
        return SyncResult(success=True, positions=pos, account=acc, message="synced (paper)")


# ═══════════════════════════════════════════════════════════════════════
# Existing paper-trading routes (unchanged)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/order/pre-check")
async def pre_check_order(
    body: PlaceOrderRequest = Body(...),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Run the same pre-trade risk gate used by order submission."""
    if body.direction.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "direction must be BUY or SELL")
    requested_mode = (body.trade_mode or _current_mode or "paper").lower()
    if requested_mode not in ("paper", "live"):
        raise HTTPException(400, detail={"detail": "trade_mode must be paper or live", "error_code": "INVALID_TRADE_MODE"})

    order_req = OrderRequest(
        symbol=body.code.upper(),
        side=OrderSide(body.direction.upper()),
        order_type=OrderType.LIMIT if body.price > 0 else OrderType.MARKET,
        quantity=body.volume,
        price=body.price,
    )

    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    order_scope = build_order_scope(**scope)
    if requested_mode == "live":
        if _live_broker is None:
            await _audit_record_safe(
                db,
                action="BROKER_NOT_CONNECTED",
                mode="live",
                user=user,
                details={
                    "order_scope": order_scope,
                    "decision_context_id": body.decision_context_id,
                    "candidate_id": body.candidate_id,
                    "plan_id": body.plan_id,
                    "request": {
                        "code": body.code,
                        "direction": body.direction,
                        "price": body.price,
                        "volume": body.volume,
                    },
                    "error_code": "BROKER_NOT_CONNECTED",
                },
                symbol=body.code,
            )
            raise HTTPException(
                503,
                detail={
                    "detail": "实盘券商未连接，请先连接 QMT/券商网关",
                    "error_code": "BROKER_NOT_CONNECTED",
                },
            )
        broker = _live_broker
    else:
        broker = _PaperEngineAdapter(engine)

    acct = await broker.get_account()
    positions = await broker.get_positions()
    risk_result = await pre_check(order_req, acct, positions)
    risk_verdict = build_risk_verdict(
        risk_result,
        **scope,
        symbol=order_req.symbol,
        trade_mode=requested_mode,
        decision_context_id=body.decision_context_id,
        candidate_id=body.candidate_id,
        plan_id=body.plan_id,
    )
    action = (
        "RISK_REJECT"
        if not risk_result.passed
        else "MANUAL_REVIEW"
        if risk_result.requires_confirmation
        else "RISK_PASS"
    )
    await _audit_record_safe(
        db,
        action=action,
        mode=requested_mode,
        user=user,
        details={
            "order_scope": order_scope,
            "decision_context_id": body.decision_context_id,
            "candidate_id": body.candidate_id,
            "plan_id": body.plan_id,
            "request": {
                "code": body.code,
                "direction": body.direction,
                "price": body.price,
                "volume": body.volume,
                "order_type": order_req.order_type.value,
            },
            "risk_verdict": risk_verdict,
            "risk_check": risk_result.to_dict(),
        },
        symbol=body.code,
    )
    return {
        **risk_result.to_dict(),
        "trade_mode": requested_mode,
        "order_scope": order_scope,
        "risk_verdict": risk_verdict,
    }


@router.post("/order")
async def place_order(
    body: PlaceOrderRequest = Body(...),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Place a trading order — paper or live."""
    if body.direction.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "direction must be BUY or SELL")
    requested_mode = (body.trade_mode or _current_mode or "paper").lower()
    if requested_mode not in ("paper", "live"):
        raise HTTPException(400, detail={"detail": "trade_mode must be paper or live", "error_code": "INVALID_TRADE_MODE"})

    order_req = OrderRequest(
        symbol=body.code.upper(),
        side=OrderSide(body.direction.upper()),
        order_type=OrderType.LIMIT if body.price > 0 else OrderType.MARKET,
        quantity=body.volume,
        price=body.price,
    )

    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    order_scope = build_order_scope(**scope)
    if requested_mode == "live":
        if _live_broker is None:
            await _audit_record_safe(
                db,
                action="BROKER_NOT_CONNECTED",
                mode="live",
                user=user,
                details={
                    "order_scope": order_scope,
                    "decision_context_id": body.decision_context_id,
                    "candidate_id": body.candidate_id,
                    "plan_id": body.plan_id,
                    "request": {
                        "code": body.code,
                        "direction": body.direction,
                        "price": body.price,
                        "volume": body.volume,
                    },
                    "error_code": "BROKER_NOT_CONNECTED",
                },
                symbol=body.code,
            )
            raise HTTPException(
                503,
                detail={
                    "detail": "实盘券商未连接，请先连接 QMT/券商网关",
                    "error_code": "BROKER_NOT_CONNECTED",
                },
            )
        broker = _live_broker
    else:
        broker = _PaperEngineAdapter(engine)

    if body.decision_context_id:
        await _decision_context_record_safe(
            db,
            decision_context_id=body.decision_context_id,
            tenant_id=scope["tenant_id"],
            owner_user_id=scope["owner_user_id"],
            account_id=scope["account_id"],
            symbol=body.code,
            plan_id=body.plan_id,
            candidate_id=body.candidate_id,
            payload={
                "source": "trade_order",
                "trade_mode": requested_mode,
                "plan_id": body.plan_id,
                "candidate_id": body.candidate_id,
                "request": {
                    "code": body.code,
                    "direction": body.direction,
                    "price": body.price,
                    "volume": body.volume,
                },
            },
        )

    # Risk check for both paper and live modes. Paper orders use the same
    # verdict contract so the frontend and audit trail can rely on one shape.
    acct = await broker.get_account()
    positions = await broker.get_positions()
    risk_result = await pre_check(order_req, acct, positions)
    risk_verdict = build_risk_verdict(
        risk_result,
        **scope,
        symbol=order_req.symbol,
        trade_mode=requested_mode,
        decision_context_id=body.decision_context_id,
        candidate_id=body.candidate_id,
        plan_id=body.plan_id,
    )
    if not risk_result.passed:
        await _risk_verdict_record_safe(
            db,
            verdict=risk_verdict,
            symbol=body.code,
        )
        await _audit_record_safe(
            db,
            action="RISK_REJECT",
            mode=requested_mode,
            user=user,
            details={
                "order_scope": order_scope,
                "decision_context_id": body.decision_context_id,
                "candidate_id": body.candidate_id,
                "plan_id": body.plan_id,
                "request": {
                    "code": body.code, "direction": body.direction, "price": body.price,
                    "volume": body.volume, "order_type": order_req.order_type.value,
                },
                "risk_verdict": risk_verdict,
            },
            symbol=body.code,
        )
        raise HTTPException(
            400,
            detail={
                "detail": risk_result.reject_reason,
                "error_code": "RISK_REJECT",
                "extra": risk_verdict,
            },
        )
    await _audit_record_safe(
        db,
        action="RISK_PASS",
        mode=requested_mode,
        user=user,
        details={
            "order_scope": order_scope,
            "decision_context_id": body.decision_context_id,
            "candidate_id": body.candidate_id,
            "plan_id": body.plan_id,
            "request": {
                "code": body.code, "direction": body.direction, "price": body.price,
                "volume": body.volume, "order_type": order_req.order_type.value,
            },
            "risk_verdict": risk_verdict,
            "risk_check": risk_result.to_dict(),
        },
        symbol=body.code,
    )

    is_probe = False
    if requested_mode == "live":
        # Circuit breaker check (supports HALF_OPEN probing)
        acct_id = scope["account_id"] or _broker_config.get("account_id", "default")
        await check_daily_loss(acct_id, daily_pnl=acct.daily_pnl)
        trade_allowed, block_reason = await can_trade(acct_id)
        if not trade_allowed:
            await _audit_record_safe(
                db,
                action="CIRCUIT_BREAKER_BLOCK",
                mode=requested_mode,
                user=user,
                details={
                    "order_scope": order_scope,
                    "decision_context_id": body.decision_context_id,
                    "candidate_id": body.candidate_id,
                    "plan_id": body.plan_id,
                    "block_reason": block_reason,
                    "risk_verdict": risk_verdict,
                    "error_code": "CIRCUIT_BREAKER_OPEN",
                },
                symbol=body.code,
            )
            raise HTTPException(
                409,
                detail={
                    "detail": f"交易已暂停: {block_reason}",
                    "error_code": "CIRCUIT_BREAKER_OPEN",
                },
            )
        is_probe = block_reason.startswith("HALF_OPEN")

    # Execute. P0-3: can_trade() atomically reserves the single HALF_OPEN probe
    # slot (increments probing_count) when it grants a probe. If place_order
    # raises, we must still settle the reservation via record_probe(success=False)
    # so the slot is not leaked (which would wedge the breaker in HALF_OPEN,
    # blocking all live trades until manual reset / next-day rollover). A failed
    # probe transitions HALF_OPEN → TRIGGERED, matching the existing failure
    # semantics — so this is consistent, not a new state.
    try:
        result = await broker.place_order(order_req)
    except Exception:
        if requested_mode == "live" and is_probe:
            try:
                await record_probe(acct_id, success=False)
            except Exception:
                logger.exception("record_probe fallback failed for account=%s", acct_id)
        raise

    # HALF_OPEN probing: record the result
    if requested_mode == "live" and is_probe:
        probe_success = result.status.value not in ("REJECTED", "FAILED")
        await record_probe(acct_id, success=probe_success)

    risk_verdict["order_id"] = result.order_id

    await _risk_verdict_record_safe(
        db,
        verdict=risk_verdict,
        order_id=result.order_id,
        symbol=body.code,
    )
    await _order_record_safe(
        db,
        order_id=result.order_id,
        tenant_id=scope["tenant_id"],
        owner_user_id=scope["owner_user_id"],
        account_id=scope["account_id"],
        trade_mode=requested_mode,
        code=order_req.symbol,
        direction=order_req.side.value,
        price=result.filled_avg_price,
        volume=order_req.quantity,
        status=result.status.value,
        decision_context_id=body.decision_context_id,
        candidate_id=body.candidate_id,
        plan_id=body.plan_id,
        order_scope=order_scope,
        risk_verdict=risk_verdict,
    )

    # Audit log (best-effort)
    await _audit_record_safe(
        db,
        action="PLACE_ORDER",
        mode=requested_mode,
        user=user,
        details={
            "order_scope": order_scope,
            "decision_context_id": body.decision_context_id,
            "candidate_id": body.candidate_id,
            "plan_id": body.plan_id,
            "request": {
                "code": body.code, "direction": body.direction, "price": body.price,
                "volume": body.volume, "order_type": order_req.order_type.value,
            },
            "result": {
                "order_id": result.order_id,
                "broker_order_id": result.broker_order_id,
                "status": result.status.value,
                "filled_qty": result.filled_qty,
                "filled_avg_price": result.filled_avg_price,
            },
            "risk_verdict": risk_verdict,
            "risk_check": risk_result.to_dict(),
        },
        symbol=body.code,
        order_id=result.order_id,
    )

    return {
        "order_id": result.order_id,
        "broker_order_id": result.broker_order_id or None,
        "code": order_req.symbol,
        "direction": order_req.side.value,
        "price": result.filled_avg_price,
        "volume": order_req.quantity,
        "status": result.status.value,
        "message": result.message,
        "tenant_id": order_scope["tenant_id"],
        "owner_user_id": order_scope["owner_user_id"],
        "account_id": order_scope["account_id"],
        "visibility": order_scope["visibility"],
        "data_scope": order_scope["data_scope"],
        "decision_context_id": body.decision_context_id,
        "candidate_id": body.candidate_id,
        "plan_id": body.plan_id,
        "order_scope": order_scope,
        "risk_verdict": risk_verdict,
        "risk_check": risk_result.to_dict(),
    }


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    trade_mode: str = Query("paper", description="paper | live"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    requested_mode = (trade_mode or _current_mode or "paper").lower()
    if requested_mode not in ("paper", "live"):
        raise HTTPException(400, detail={"detail": "trade_mode must be paper or live", "error_code": "INVALID_TRADE_MODE"})

    if requested_mode == "live":
        if _live_broker is None:
            await _audit_record_safe(
                db,
                action="BROKER_NOT_CONNECTED",
                mode="live",
                user=user,
                details={"order_id": order_id, "operation": "cancel", "error_code": "BROKER_NOT_CONNECTED"},
                order_id=order_id,
            )
            raise HTTPException(
                503,
                detail={
                    "detail": "实盘券商未连接，请先连接 QMT/券商网关",
                    "error_code": "BROKER_NOT_CONNECTED",
                },
            )
        result = await _live_broker.cancel_order(order_id)
        ok = result.success
    else:
        ok = engine.cancel_order(order_id)

    status = "cancelled" if ok else "not_found"
    await _audit_record_safe(
        db,
        action="CANCEL_ORDER",
        mode=requested_mode,
        user=user,
        details={"order_id": order_id, "status": status},
        order_id=order_id,
    )
    return {"order_id": order_id, "status": status, "trade_mode": requested_mode}


@router.get("/orders")
async def list_orders(
    trade_mode: str | None = Query(None, description="paper | live"),
    code: str | None = Query(None, description="Stock code"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    try:
        return await query_trade_orders(
            db,
            tenant_id=scope["tenant_id"],
            account_id=scope["account_id"],
            trade_mode=trade_mode,
            code=code,
            page=page,
            page_size=page_size,
        )
    except Exception:
        await db.rollback()
        logger.exception("Trade order ledger query failed; falling back to paper engine orders")
        orders = [
            {
                "id": o.id,
                "order_id": o.id,
                "code": o.code,
                "direction": o.direction,
                "price": o.filled_price,
                "volume": o.volume,
                "status": o.status,
                "created": o.created_at,
                "tenant_id": scope["tenant_id"],
                "owner_user_id": scope["owner_user_id"],
                "account_id": scope["account_id"],
            }
            for o in engine.get_orders()
        ]
        return {"orders": orders, "total": len(orders), "page": page, "page_size": page_size}


@router.get("/positions")
async def get_positions(
    trade_mode: str = Query("paper", description="paper | live"),
    sync: bool = Query(False, description="Sync from broker first"),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    if trade_mode == "live" and _live_broker is not None:
        if sync:
            await _live_broker.sync()
        positions = await _live_broker.get_positions()
        return {
            "trade_mode": "live",
            "positions": [
                {
                    "code": p.symbol, "volume": p.quantity,
                    "avg_cost": round(p.avg_cost, 2),
                    "market_value": p.market_value,
                    "pnl": round(p.pnl, 2),
                    "pnl_pct": round(p.pnl_pct, 2),
                }
                for p in positions
            ],
        }

    return {"trade_mode": "paper", "positions": [{"code": p.code, "volume": p.volume,
            "avg_cost": round(p.avg_cost, 2), "market_value": p.market_value,
            "pnl": round(p.pnl, 2), "pnl_pct": round(p.pnl_pct, 2)}
            for p in engine.get_positions()]}


@router.get("/account")
async def get_account(
    trade_mode: str = Query("paper", description="paper | live"),
    sync: bool = Query(False, description="Sync from broker first"),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    if trade_mode == "live" and _live_broker is not None:
        if sync:
            await _live_broker.sync()
        acct = await _live_broker.get_account()
        acct_id = _broker_config.get("account_id", "default")
        breaker = await get_state(acct_id)
        return {
            "trade_mode": "live",
            "broker_name": _broker_config.get("broker_name", "xtquant"),
            "account_id": acct.account_id or _broker_config.get("account_id", ""),
            "total_assets": acct.total_assets,
            "available_cash": acct.available,
            "frozen_cash": acct.frozen,
            "market_value": acct.market_value,
            "total_pnl": round(acct.total_pnl, 2),
            "daily_pnl": round(acct.daily_pnl, 2),
            "circuit_breaker": {
                "status": breaker["status"],
                "daily_loss_pct": breaker["daily_loss_pct"],
                "can_trade": breaker["can_trade"],
            },
        }

    acct = engine.get_account()
    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    return build_paper_account_view(acct, **scope)


@router.get("/pnl")
async def get_pnl(
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    acct = engine.get_account()
    orders = engine.get_orders()
    trades = [o for o in orders if o.status == "filled"]
    return {
        "total_pnl": round(acct.total_pnl, 2), "daily_pnl": round(acct.daily_pnl, 2),
        "total_trades": len(trades), "positions": len(engine.get_positions()),
        "total_capital": acct.total_capital,
    }


# ═══════════════════════════════════════════════════════════════════════
# New live-trading routes (PRD AC-11.1~11.9)
# ═══════════════════════════════════════════════════════════════════════

@router.put("/mode")
async def switch_mode(
    mode: str = Query("paper", description="paper | live"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Switch global trading mode between paper and live."""
    global _current_mode

    if mode not in ("paper", "live"):
        raise HTTPException(400, "mode must be paper or live")

    if mode == "live" and _live_broker is None:
        raise HTTPException(
            503,
            detail={
                "detail": "请先连接券商",
                "error_code": "BROKER_NOT_CONNECTED",
            },
        )

    previous = _current_mode
    _current_mode = mode

    await _audit_record_safe(
        db,
        action="MODE_SWITCH",
        mode=mode,
        user=user,
        details={"previous_mode": previous, "current_mode": mode},
    )

    return {
        "previous_mode": previous,
        "current_mode": mode,
        "switched_at": datetime.now(timezone.utc).isoformat(),
        "broker_status": {
            "connected": _live_broker is not None,
            "broker_name": _broker_config.get("broker_name", ""),
            "account_id": _broker_config.get("account_id", ""),
        } if mode == "live" else None,
    }


@router.post("/broker/connect")
async def broker_connect(
    body: BrokerConnectRequest | None = Body(default=None),
    broker_name: str | None = Query(default=None),
    account_id: str | None = Query(default=None, description="Broker account ID"),
    server_ip: str = Query("127.0.0.1"),
    server_port: int = Query(6001),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Connect to a broker adapter.

    ``mock_qmt`` is a sandbox-only adapter for UI/API integration. It never
    imports Xtquant and keeps the effective trade mode as paper.
    """
    global _live_broker, _broker_config, _broker_connected_at

    if _live_broker is not None:
        raise HTTPException(
            409,
            detail={
                "detail": "已存在活动连接，请先断开",
                "error_code": "BROKER_ALREADY_CONNECTED",
            },
        )

    if body is None:
        if not account_id:
            raise HTTPException(400, "account_id is required")
        body = BrokerConnectRequest(
            broker_name=broker_name or "xtquant",
            account_id=account_id,
            server_ip=server_ip,
            server_port=server_port,
            environment="live",
        )

    if body.environment not in ("sandbox", "live"):
        raise HTTPException(400, "environment must be sandbox or live")

    # P1-6 (audit): do NOT persist the plaintext trade_password into the
    # module-level _broker_config dict (real-money credential; would survive in
    # process memory until restart and leak on any future logger.debug of the
    # config or in a traceback). XtquantBroker.connect() authenticates via the
    # QMT userdata session path, not this password — so we only record a
    # boolean "was provided" flag for status/audit, and let the plaintext drop
    # out of scope here for GC. If a future broker needs the password, pass it
    # as a local variable to the constructor (never store on _broker_config).
    _broker_config = {
        "broker_name": body.broker_name,
        "account_id": body.account_id,
        "server_ip": body.server_ip,
        "server_port": body.server_port,
        "environment": body.environment,
        "adapter": "mock" if body.broker_name == "mock_qmt" else body.broker_name,
        "trade_password_provided": bool(body.trade_password),
    }

    if body.broker_name == "mock_qmt":
        if body.environment != "sandbox":
            raise HTTPException(400, "mock_qmt only supports sandbox environment")
        _live_broker = _PaperEngineAdapter(engine)
        _broker_connected_at = datetime.now(timezone.utc)
        await _audit_record_safe(
            db,
            action="BROKER_CONNECT",
            mode="paper",
            user=user,
            details={
                "broker_name": body.broker_name,
                "account_id": body.account_id,
                "environment": body.environment,
                "adapter": "mock",
            },
        )
        return {
            "broker_name": body.broker_name,
            "account_id": body.account_id,
            "status": "connected",
            "environment": body.environment,
            "adapter": "mock",
            "trade_mode": "paper",
            "connected_at": _broker_connected_at.isoformat(),
        }

    if body.broker_name != "xtquant":
        raise HTTPException(400, f"Unsupported broker: {body.broker_name}")

    from app.xtquant_broker import XtquantBroker

    broker = XtquantBroker(
        path=os.environ.get("QMT_USERDATA_PATH", ""),
        account=body.account_id,
    )
    connected = await broker.connect()
    if not connected:
        raise HTTPException(
            502,
            detail={
                "detail": "连接券商服务失败",
                "error_code": "BROKER_CONNECTION_ERROR",
            },
        )

    _live_broker = broker
    _broker_connected_at = datetime.now(timezone.utc)

    await _audit_record_safe(
        db,
        action="BROKER_CONNECT",
        mode="live",
        user=user,
        details={
            "broker_name": body.broker_name,
            "account_id": body.account_id,
            "environment": body.environment,
        },
    )

    return {
        "broker_name": body.broker_name,
        "account_id": body.account_id,
        "status": "connected",
        "environment": body.environment,
        "adapter": body.broker_name,
        "trade_mode": "live",
        "connected_at": _broker_connected_at.isoformat(),
    }


@router.get("/broker/status")
async def broker_status(user: dict = Depends(require_role("admin", "internal_analyst", "user", "external_analyst"))):
    """Get current broker connection status."""
    connected = _live_broker is not None
    return {
        "connected": connected,
        "broker_name": _broker_config.get("broker_name", "xtquant"),
        "account_id": _broker_config.get("account_id", None),
        "environment": _broker_config.get("environment", "live"),
        "adapter": _broker_config.get("adapter", _broker_config.get("broker_name", "xtquant")),
        "trade_mode": "paper" if _broker_config.get("environment") == "sandbox" else _current_mode,
        "status": "connected" if connected else "disconnected",
        "last_heartbeat": None,
        "heartbeat_interval_sec": int(os.environ.get("BROKER_HEARTBEAT_INTERVAL_SEC", "30")),
        "reconnect_count": 0,
        "reconnect_max": int(os.environ.get("BROKER_RECONNECT_MAX", "5")),
        "error_message": None,
        "uptime_seconds": (
            int((datetime.now(timezone.utc) - _broker_connected_at).total_seconds())
            if connected and _broker_connected_at
            else 0
        ),
    }


@router.get("/risk-config")
async def risk_config(user: dict = Depends(require_role("admin", "internal_analyst", "user"))):
    """Return frontend-visible pre-trade risk thresholds."""
    return {
        "large_order_threshold": float(os.environ.get("RISK_LARGE_TRADE_THRESHOLD", "500000")),
        "max_single_amount": float(os.environ.get("RISK_MAX_SINGLE_ORDER_AMOUNT", "500000")),
        "max_position_pct": float(os.environ.get("RISK_MAX_POSITION_CONCENTRATION", "30")),
        "price_limit_pct": float(os.environ.get("RISK_PRICE_LIMIT_PCT", "10.0")),
    }


# ── Circuit Breaker routes ────────────────────────────────────────────

@router.get("/circuit-breaker")
async def get_circuit_breaker(
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Get current circuit breaker state."""
    acct_id = _broker_config.get("account_id", "default")
    state = await get_state(acct_id)
    return {"breakers": [state]}


@router.get("/circuit-breaker/status")
async def get_circuit_breaker_status(
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Compatibility endpoint used by the frontend live-trade hook."""
    acct_id = _broker_config.get("account_id", "default")
    state = await get_state(acct_id)
    return {"breakers": [state]}


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(
    reason: str = Query("manual reset", description="Reset reason"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Manually reset the circuit breaker."""
    acct_id = _broker_config.get("account_id", "default")
    state_before = await get_state(acct_id)
    await reset(acct_id, reason=reason)
    state_after = await get_state(acct_id)

    await _audit_record_safe(
        db,
        action="CIRCUIT_BREAKER",
        mode="live",
        user=user,
        details={
            "previous_status": state_before["status"],
            "current_status": state_after["status"],
            "reason": reason,
        },
    )

    return {
        "breaker_type": "daily_loss",
        "previous_status": state_before["status"],
        "current_status": state_after["status"],
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }


# ── Audit Log routes ──────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    action: str | None = Query(None, description="Filter by action type"),
    trade_mode: str | None = Query(None, description="paper | live"),
    code: str | None = Query(None, description="Stock code"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Query the audit log (read-only)."""
    return await query_audit(
        db,
        action=action,
        mode=trade_mode,
        symbol=code,
        page=page,
        page_size=page_size,
    )


@router.get("/risk-verdicts")
async def get_risk_verdicts(
    result: str | None = Query(None, description="pass | warn | reject | manual_review"),
    trade_mode: str | None = Query(None, description="paper | live"),
    code: str | None = Query(None, description="Stock code"),
    decision_context_id: str | None = Query(None, description="DecisionContext id"),
    order_id: str | None = Query(None, description="Order id"),
    plan_id: str | None = Query(None, description="Plan id"),
    candidate_id: str | None = Query(None, description="Candidate id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Query persisted RiskVerdicts for the current tenant/account scope."""
    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    try:
        return await query_risk_verdicts(
            db,
            tenant_id=scope["tenant_id"],
            account_id=scope["account_id"],
            result=result,
            trade_mode=trade_mode,
            symbol=code,
            decision_context_id=decision_context_id,
            order_id=order_id,
            plan_id=plan_id,
            candidate_id=candidate_id,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/decision-contexts")
async def get_decision_contexts(
    decision_context_id: str | None = Query(None, description="DecisionContext id"),
    code: str | None = Query(None, description="Stock code"),
    plan_id: str | None = Query(None, description="Plan id"),
    candidate_id: str | None = Query(None, description="Candidate id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    account_id: str | None = Header(default=None, alias="X-Trade-Account-Id"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Query persisted DecisionContext snapshots for the current account."""
    scope = resolve_trade_scope(user, tenant_id=tenant_id, account_id=account_id)
    return await query_decision_contexts(
        db,
        tenant_id=scope["tenant_id"],
        account_id=scope["account_id"],
        decision_context_id=decision_context_id,
        symbol=code,
        plan_id=plan_id,
        candidate_id=candidate_id,
        page=page,
        page_size=page_size,
    )


# ── Helpers ────────────────────────────────────────────────────────────

def _uid(user: dict | None) -> int | None:
    """Extract a numeric user id from the JWT payload returned by require_role.

    ``require_role`` returns the decoded JWT (keys: sub, name, role, ...).
    ``sub`` may be a numeric user id (string) or ``"service"`` for internal
    service-to-service calls; return None for the latter / non-numeric values.
    """
    if not user:
        return None
    raw = user.get("sub") or user.get("user_id") or user.get("id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _audit_record_safe(
    db: AsyncSession,
    *,
    action: str,
    mode: str,
    user: dict | None = None,
    details: dict | None = None,
    symbol: str | None = None,
    order_id: str | None = None,
    client_ip: str | None = None,
) -> None:
    """Best-effort audit log write — never blocks the main operation.

    On DB failure: rollback + ``logger.exception`` (never silent, never re-raise).
    Per AC-4 / ADR-007 Q-3.
    """
    try:
        await record_audit(
            db,
            user_id=_uid(user),
            action=action,
            mode=mode,
            details=details,
            symbol=symbol,
            order_id=order_id,
            client_ip=client_ip,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "AUDIT write failed (non-fatal) action=%s mode=%s symbol=%s order=%s",
            action, mode, symbol, order_id,
        )


async def _risk_verdict_record_safe(
    db: AsyncSession,
    *,
    verdict: dict,
    order_id: str | None = None,
    symbol: str | None = None,
) -> None:
    """Best-effort RiskVerdict write — never blocks order processing."""
    try:
        await record_risk_verdict(
            db,
            verdict=verdict,
            order_id=order_id,
            symbol=symbol,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "RiskVerdict write failed (non-fatal) verdict=%s symbol=%s order=%s",
            verdict.get("verdict_id"), symbol, order_id,
        )


async def _decision_context_record_safe(
    db: AsyncSession,
    *,
    decision_context_id: str,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    symbol: str | None = None,
    plan_id: str | None = None,
    candidate_id: str | None = None,
    intent: str = "manual_order",
    payload: dict | None = None,
) -> None:
    """Best-effort DecisionContext snapshot write — never blocks orders."""
    try:
        await record_decision_context_once(
            db,
            decision_context_id=decision_context_id,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            account_id=account_id,
            source_type="order",
            symbol=symbol,
            plan_id=plan_id,
            candidate_id=candidate_id,
            intent=intent,
            payload=payload
            or {
                "plan_id": plan_id,
                "candidate_id": candidate_id,
                "symbol": symbol,
            },
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "DecisionContext write failed (non-fatal) context=%s symbol=%s plan=%s",
            decision_context_id, symbol, plan_id,
        )


async def _order_record_safe(
    db: AsyncSession,
    *,
    order_id: str,
    tenant_id: str,
    owner_user_id: str | None,
    account_id: str | None,
    trade_mode: str,
    code: str,
    direction: str,
    price: float | None,
    volume: int,
    status: str,
    decision_context_id: str | None = None,
    candidate_id: str | None = None,
    plan_id: str | None = None,
    order_scope: dict | None = None,
    risk_verdict: dict | None = None,
) -> None:
    """Best-effort order ledger write — never blocks order processing."""
    try:
        await record_trade_order(
            db,
            order_id=order_id,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            account_id=account_id,
            trade_mode=trade_mode,
            code=code,
            direction=direction,
            price=price,
            volume=volume,
            status=status,
            decision_context_id=decision_context_id,
            candidate_id=candidate_id,
            plan_id=plan_id,
            order_scope=order_scope,
            risk_verdict=risk_verdict,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("TradeOrder write failed (non-fatal) order=%s symbol=%s", order_id, code)
