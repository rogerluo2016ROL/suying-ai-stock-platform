"""Platform scope helpers for trade-service read models."""

from __future__ import annotations

from uuid import uuid4


def resolve_trade_scope(
    user: dict,
    tenant_id: str | None = None,
    account_id: str | None = None,
) -> dict:
    role = user.get("role", "user")
    owner_user_id = str(user.get("sub") or user.get("id") or "service")
    default_tenant = "platform" if role == "admin" and owner_user_id == "service" else "tenant-default"
    return {
        "tenant_id": tenant_id or default_tenant,
        "owner_user_id": owner_user_id,
        "account_id": account_id or ("" if role == "admin" else f"paper-u{owner_user_id}"),
    }


def build_order_scope(
    *,
    tenant_id: str,
    owner_user_id: str,
    account_id: str,
    visibility: str = "private",
    data_scope: str = "account",
) -> dict:
    return {
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "account_id": account_id,
        "visibility": visibility,
        "data_scope": data_scope,
    }


def build_risk_verdict(
    risk_result,
    *,
    tenant_id: str,
    owner_user_id: str,
    account_id: str,
    symbol: str,
    trade_mode: str,
    decision_context_id: str = "",
    candidate_id: str = "",
    plan_id: str = "",
    order_id: str | None = None,
) -> dict:
    if risk_result is None:
        passed = True
        requires_confirmation = False
        risk_payload = {"passed": True, "requires_confirmation": False, "confirm_reason": "", "checks": []}
    else:
        passed = bool(getattr(risk_result, "passed", False))
        requires_confirmation = bool(getattr(risk_result, "requires_confirmation", False))
        risk_payload = risk_result.to_dict()

    if not passed:
        result = "reject"
    elif requires_confirmation:
        result = "warn"
    else:
        result = "pass"

    return {
        "verdict_id": f"RV-{uuid4().hex[:8].upper()}",
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "account_id": account_id,
        "visibility": "private",
        "data_scope": "account",
        "scope": "order",
        "result": result,
        "symbol": symbol,
        "trade_mode": trade_mode,
        "decision_context_id": decision_context_id,
        "candidate_id": candidate_id,
        "plan_id": plan_id,
        "order_id": order_id,
        "risk_check": risk_payload,
    }


def build_paper_account_view(
    account,
    *,
    tenant_id: str,
    owner_user_id: str,
    account_id: str,
) -> dict:
    return {
        "tenant_id": tenant_id,
        "owner_user_id": owner_user_id,
        "account_id": account_id,
        "account_name": "默认模拟账户",
        "adapter": "paper",
        "trade_mode": "paper",
        "visibility": "private",
        "data_scope": "account",
        "can_trade": True,
        "can_sync_positions": True,
        "total_capital": account.total_capital,
        "available": account.available,
        "market_value": account.market_value,
        "total_pnl": round(account.total_pnl, 2),
        "daily_pnl": round(account.daily_pnl, 2),
    }
