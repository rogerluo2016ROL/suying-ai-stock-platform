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

from fastapi import APIRouter, HTTPException, Query, Depends, Body
from kronos_auth import require_role
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit_log import record as record_audit, query as query_audit
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
from app.schemas import PlaceOrderRequest

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
        return OrderResult(
            order_id=o.id,
            broker_order_id="",
            status=OrderStatus.FILLED,
            filled_qty=o.volume,
            filled_avg_price=o.filled_price,
            message="filled (paper)",
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

@router.post("/order")
async def place_order(
    body: PlaceOrderRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    """Place a trading order — paper or live."""
    if body.direction.upper() not in ("BUY", "SELL"):
        raise HTTPException(400, "direction must be BUY or SELL")

    order_req = OrderRequest(
        symbol=body.code.upper(),
        side=OrderSide(body.direction.upper()),
        order_type=OrderType.LIMIT if body.price > 0 else OrderType.MARKET,
        quantity=body.volume,
        price=body.price,
    )

    # Determine broker
    if body.trade_mode == "live" and _live_broker is not None:
        broker = _live_broker
    else:
        broker = _PaperEngineAdapter(engine)

    # Risk check (only for live mode)
    risk_result = None
    is_probe = False
    if body.trade_mode == "live":
        acct = await broker.get_account()
        positions = await broker.get_positions()
        risk_result = await pre_check(order_req, acct, positions)
        if not risk_result.passed:
            raise HTTPException(
                400,
                detail={
                    "detail": risk_result.reject_reason,
                    "error_code": "RISK_REJECT",
                    "extra": risk_result.to_dict(),
                },
            )

        # Circuit breaker check (supports HALF_OPEN probing)
        acct_id = _broker_config.get("account_id", "default")
        await check_daily_loss(acct_id, daily_pnl=acct.daily_pnl)
        trade_allowed, block_reason = await can_trade(acct_id)
        if not trade_allowed:
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
        if body.trade_mode == "live" and is_probe:
            try:
                await record_probe(acct_id, success=False)
            except Exception:
                logger.exception("record_probe fallback failed for account=%s", acct_id)
        raise

    # HALF_OPEN probing: record the result
    if body.trade_mode == "live" and is_probe:
        probe_success = result.status.value not in ("REJECTED", "FAILED")
        await record_probe(acct_id, success=probe_success)

    # Audit log (best-effort)
    await _audit_record_safe(
        db,
        action="PLACE_ORDER",
        mode=body.trade_mode,
        user=user,
        details={
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
            "risk_check": risk_result.to_dict() if risk_result else None,
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
        "risk_check": risk_result.to_dict() if risk_result else None,
    }


@router.delete("/order/{order_id}")
async def cancel_order(
    order_id: str,
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    ok = engine.cancel_order(order_id)
    return {"order_id": order_id, "status": "cancelled" if ok else "not_found"}


@router.get("/orders")
async def list_orders(
    user: dict = Depends(require_role("admin", "internal_analyst", "user")),
):
    return {"orders": [{"id": o.id, "code": o.code, "direction": o.direction,
            "price": o.filled_price, "volume": o.volume, "status": o.status,
            "created": o.created_at} for o in engine.get_orders()]}


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
    return {
        "trade_mode": "paper",
        "total_capital": acct.total_capital,
        "available": acct.available,
        "market_value": acct.market_value,
        "total_pnl": round(acct.total_pnl, 2),
        "daily_pnl": round(acct.daily_pnl, 2),
    }


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
    broker_name: str = Query("xtquant"),
    account_id: str = Query(..., description="Broker account ID"),
    server_ip: str = Query("127.0.0.1"),
    server_port: int = Query(6001),
    trade_password: str = Body("", embed=True),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_role("admin")),
):
    """Connect to the live broker (xtquant/QMT)."""
    global _live_broker, _broker_config, _broker_connected_at

    if _live_broker is not None:
        raise HTTPException(
            409,
            detail={
                "detail": "已存在活动连接，请先断开",
                "error_code": "BROKER_ALREADY_CONNECTED",
            },
        )

    # P1-6 (audit): do NOT persist the plaintext trade_password into the
    # module-level _broker_config dict (real-money credential; would survive in
    # process memory until restart and leak on any future logger.debug of the
    # config or in a traceback). XtquantBroker.connect() authenticates via the
    # QMT userdata session path, not this password — so we only record a
    # boolean "was provided" flag for status/audit, and let the plaintext drop
    # out of scope here for GC. If a future broker needs the password, pass it
    # as a local variable to the constructor (never store on _broker_config).
    _broker_config = {
        "broker_name": broker_name,
        "account_id": account_id,
        "server_ip": server_ip,
        "server_port": server_port,
        "trade_password_provided": bool(trade_password),
    }

    if broker_name != "xtquant":
        raise HTTPException(400, f"Unsupported broker: {broker_name}")

    from app.xtquant_broker import XtquantBroker

    broker = XtquantBroker(
        path=os.environ.get("QMT_USERDATA_PATH", ""),
        account=account_id,
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
        details={"broker_name": broker_name, "account_id": account_id},
    )

    return {
        "broker_name": broker_name,
        "account_id": account_id,
        "status": "connected",
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


# ── Circuit Breaker routes ────────────────────────────────────────────

@router.get("/circuit-breaker")
async def get_circuit_breaker(
    user: dict = Depends(require_role("admin", "internal_analyst")),
):
    """Get current circuit breaker state."""
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
