"""Platform-aware FastAPI dependencies.

This module is intentionally database-light for phase A: it resolves the
tenant/account request scope from the authenticated user plus explicit headers.
Service routers can depend on it before user-owned reads or writes.
"""

from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.platform import PlatformContext, RoleView


def role_to_role_view(role: str | None) -> RoleView:
    if role == "admin":
        return "admin"
    if role in {"internal_analyst", "external_analyst"}:
        return "trader"
    return "investor"


def _role_name(current_user: Any) -> str:
    role = getattr(current_user, "role", None)
    if isinstance(role, str):
        return role
    return getattr(role, "name", None) or "user"


def _default_tenant_id(current_user: Any, role_view: RoleView) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id:
        return str(tenant_id)
    return "platform" if role_view == "admin" else "tenant-default"


def _default_account_id(current_user: Any) -> str | None:
    account_id = getattr(current_user, "default_trade_account_id", None)
    return str(account_id) if account_id else None


def build_platform_context(
    current_user: User,
    tenant_id_header: str | None = None,
    account_id_header: str | None = None,
) -> PlatformContext:
    role = _role_name(current_user)
    role_view = role_to_role_view(role)
    default_tenant_id = _default_tenant_id(current_user, role_view)
    tenant_id = tenant_id_header or default_tenant_id
    cross_tenant = tenant_id != default_tenant_id

    if cross_tenant and role_view != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access requires admin role",
        )

    account_id = account_id_header or _default_account_id(current_user)
    if role_view == "admin":
        visibility = "tenant_shared"
        data_scope = "tenant"
    else:
        visibility = "private"
        data_scope = "account"

    return PlatformContext(
        tenant_id=tenant_id,
        user_id=int(current_user.id),
        role=role,
        role_view=role_view,
        account_id=account_id,
        visibility=visibility,
        data_scope=data_scope,
        cross_tenant=cross_tenant,
    )


async def get_platform_context(
    current_user: User = Depends(get_current_user),
    tenant_id_header: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    account_id_header: Annotated[
        str | None,
        Header(alias="X-Trade-Account-Id"),
    ] = None,
) -> PlatformContext:
    return build_platform_context(
        current_user=current_user,
        tenant_id_header=tenant_id_header,
        account_id_header=account_id_header,
    )


def require_account_scope(
    context: PlatformContext = Depends(get_platform_context),
) -> PlatformContext:
    if context.data_scope != "account" or not context.account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Trading account context is required",
        )
    return context
