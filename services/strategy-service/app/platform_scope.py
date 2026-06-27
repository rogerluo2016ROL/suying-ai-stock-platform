"""Platform scope helpers for strategy resources."""


def resolve_platform_scope(
    user: dict,
    tenant_id: str | None = None,
    account_id: str | None = None,
    data_scope: str | None = None,
) -> dict:
    role = user.get("role", "user")
    owner_user_id = str(user.get("sub") or user.get("id") or "service")
    default_tenant = "platform" if role == "admin" and owner_user_id == "service" else "tenant-default"
    resolved_data_scope = data_scope or ("tenant" if role == "admin" and owner_user_id == "service" else "account")

    return {
        "tenant_id": tenant_id or default_tenant,
        "owner_user_id": owner_user_id,
        "account_id": account_id or "",
        "visibility": "private",
        "data_scope": resolved_data_scope,
    }


def plan_to_dict(plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "status": plan.status,
        "picks_count": len(plan.picks),
        "model_name": plan.model_name,
        "capital": plan.capital,
        "max_positions": plan.max_positions,
        "single_max_pct": plan.single_max_pct,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
        "tenant_id": plan.tenant_id,
        "owner_user_id": plan.owner_user_id,
        "account_id": plan.account_id,
        "visibility": plan.visibility,
        "data_scope": plan.data_scope,
    }
