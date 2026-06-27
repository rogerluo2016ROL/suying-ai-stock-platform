"""Platform tenant/account bootstrap helpers."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.platform import BrokerAccount, Membership, Tenant
from app.models.user import User


DEFAULT_PLATFORM_TENANT_SLUG = "platform"
DEFAULT_TENANT_SLUG = "tenant-default"


def role_to_role_view(role: str | None) -> str:
    if role == "admin":
        return "admin"
    if role in {"internal_analyst", "external_analyst"}:
        return "trader"
    return "investor"


def role_to_platform_tenant_slug(role: str | None) -> str:
    return DEFAULT_PLATFORM_TENANT_SLUG if role == "admin" else DEFAULT_TENANT_SLUG


def default_broker_account_id(user: Any) -> str:
    return f"paper-u{int(user.id)}"


async def _get_or_create_tenant(
    db: AsyncSession,
    *,
    slug: str,
    name: str,
) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant:
        return tenant

    tenant = Tenant(slug=slug, name=name, status="active")
    db.add(tenant)
    await db.flush()
    return tenant


async def ensure_user_platform_defaults(db: AsyncSession, user: User) -> None:
    role = user.role.name if user.role else "user"
    tenant_slug = role_to_platform_tenant_slug(role)
    tenant_name = "平台运营" if tenant_slug == DEFAULT_PLATFORM_TENANT_SLUG else "默认租户"

    tenant = await _get_or_create_tenant(db, slug=tenant_slug, name=tenant_name)

    membership_result = await db.execute(
        select(Membership).where(
            Membership.tenant_id == tenant.id,
            Membership.user_id == user.id,
        ),
    )
    if not membership_result.scalar_one_or_none():
        db.add(
            Membership(
                tenant_id=tenant.id,
                user_id=user.id,
                role_view=role_to_role_view(role),
                is_default=True,
            ),
        )

    if role == "admin":
        return

    account_id = default_broker_account_id(user)
    account_result = await db.execute(
        select(BrokerAccount).where(
            BrokerAccount.tenant_id == tenant.id,
            BrokerAccount.account_id == account_id,
        ),
    )
    if not account_result.scalar_one_or_none():
        db.add(
            BrokerAccount(
                tenant_id=tenant.id,
                owner_user_id=user.id,
                account_id=account_id,
                account_name=f"{user.name} 模拟账户",
                adapter="paper",
                trade_mode="paper",
                is_default=True,
                can_trade=True,
                can_sync_positions=True,
            ),
        )


async def ensure_platform_defaults(db: AsyncSession) -> None:
    await _get_or_create_tenant(db, slug=DEFAULT_PLATFORM_TENANT_SLUG, name="平台运营")
    await _get_or_create_tenant(db, slug=DEFAULT_TENANT_SLUG, name="默认租户")

    result = await db.execute(select(User).options(selectinload(User.role)))
    for user in result.scalars().all():
        await ensure_user_platform_defaults(db, user)

    await db.commit()
