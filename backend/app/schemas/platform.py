"""Platform context contracts for tenant/account scoped requests."""

from typing import Literal

from pydantic import BaseModel, Field


RoleView = Literal["trader", "investor", "admin"]
Visibility = Literal["private", "tenant_shared", "public"]
DataScope = Literal["public", "tenant", "user", "account"]
TradeMode = Literal["paper", "live"]
BrokerAdapter = Literal["paper", "xtquant_qmt", "broker_rest"]


class PlatformContext(BaseModel):
    """Resolved request scope used before querying user-owned data."""

    tenant_id: str = Field(description="Tenant boundary for this request")
    user_id: int = Field(description="Authenticated user id")
    role: str = Field(description="Raw RBAC role")
    role_view: RoleView = Field(description="Product persona derived from RBAC")
    account_id: str | None = Field(
        default=None,
        description="Trading account boundary for portfolio/order data",
    )
    visibility: Visibility = Field(
        default="private",
        description="Whether produced data is private, tenant-shared, or public",
    )
    data_scope: DataScope = Field(
        default="account",
        description="Smallest data ownership scope needed by the request",
    )
    cross_tenant: bool = Field(
        default=False,
        description="True when an admin explicitly works outside its default tenant",
    )

