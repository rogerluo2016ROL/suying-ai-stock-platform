"""RBAC permission registry and membership entitlement helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any, Iterable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.platform import Membership, MembershipEvent, Tenant
from app.models.user import Role, RolePermission, User
from app.services.platform_service import (
    DEFAULT_PLATFORM_TENANT_SLUG,
    ensure_user_platform_defaults,
    role_to_platform_tenant_slug,
    role_to_role_view,
)


@dataclass(frozen=True)
class PermissionDefinition:
    key: str
    label: str
    group: str
    description: str


PERMISSION_DEFINITIONS: tuple[PermissionDefinition, ...] = (
    PermissionDefinition("dashboard", "智能看板", "行情决策", "查看市场总览、情绪和资金面"),
    PermissionDefinition("open_decision", "开盘决策", "行情决策", "查看竞价、开盘信号和候选池"),
    PermissionDefinition("screener", "智能选股", "行情决策", "查看和运行选股结果"),
    PermissionDefinition("supply_chain_bom", "产业链拆解", "行情决策", "查看产业链拆解和个股映射"),
    PermissionDefinition("predictions", "K线预测", "行情决策", "查看 K 线预测"),
    PermissionDefinition("signals", "交易信号", "行情决策", "查看交易信号和触发记录"),
    PermissionDefinition("trade", "交易中心", "交易执行", "查看交易账户、订单和持仓"),
    PermissionDefinition("auto_trade", "量化交易", "交易执行", "配置和查看自动交易"),
    PermissionDefinition("strategy", "方案管理", "交易执行", "查看和管理策略方案"),
    PermissionDefinition("risk", "风控中心", "交易执行", "查看风控规则和风险状态"),
    PermissionDefinition("backtest", "回测分析", "交易执行", "运行和查看回测"),
    PermissionDefinition("diagnosis", "个股诊断", "交易执行", "查看个股诊断"),
    PermissionDefinition("training", "模型训练", "模型 / 系统", "运行模型训练任务"),
    PermissionDefinition("model_registry", "模型注册", "模型 / 系统", "管理模型注册信息"),
    PermissionDefinition("data_update", "数据更新", "模型 / 系统", "查看和触发数据更新"),
    PermissionDefinition("runtime_status", "运行状态", "模型 / 系统", "查看系统运行状态"),
    PermissionDefinition("p0_workflow", "P0 主链路", "模型 / 系统", "查看核心链路监控"),
    PermissionDefinition("platform_upgrade", "平台升级", "模型 / 系统", "查看平台升级任务"),
    PermissionDefinition("admin_permissions", "权限授权", "平台管理", "配置用户角色和角色菜单权限"),
    PermissionDefinition("admin_memberships", "会员管理", "平台管理", "查看和管理会员周期"),
)

VALID_PERMISSION_KEYS = {item.key for item in PERMISSION_DEFINITIONS}

MARKET_PERMISSIONS = {
    "dashboard",
    "open_decision",
    "screener",
    "supply_chain_bom",
    "predictions",
    "signals",
    "strategy",
    "diagnosis",
    "data_update",
    "p0_workflow",
}

DEFAULT_ROLE_PERMISSION_KEYS: dict[str, set[str]] = {
    "admin": set(VALID_PERMISSION_KEYS),
    "internal_analyst": MARKET_PERMISSIONS
    | {"trade", "auto_trade", "risk", "backtest"},
    "external_analyst": MARKET_PERMISSIONS | {"backtest"},
    "user": MARKET_PERMISSIONS | {"trade"},
}

ROLE_LABELS = {
    "admin": "平台管理员",
    "internal_analyst": "操盘手",
    "external_analyst": "外部分析师",
    "user": "个人投资者",
}

VALID_MEMBERSHIP_STATUSES = {"inactive", "trial", "active", "expired", "cancelled"}
ACTIVE_MEMBERSHIP_STATUSES = {"trial", "active"}


def _definition_order(key: str) -> int:
    for index, item in enumerate(PERMISSION_DEFINITIONS):
        if item.key == key:
            return index
    return len(PERMISSION_DEFINITIONS)


def permission_keys_for_role(
    role_name: str,
    role_permissions: Iterable[RolePermission] | None = None,
) -> list[str]:
    enabled_by_key = {
        item.key: item.key in DEFAULT_ROLE_PERMISSION_KEYS.get(role_name, set())
        for item in PERMISSION_DEFINITIONS
    }
    if role_permissions is not None:
        for row in role_permissions:
            if row.permission_key in enabled_by_key:
                enabled_by_key[row.permission_key] = bool(row.enabled)
    return [item.key for item in PERMISSION_DEFINITIONS if enabled_by_key[item.key]]


def role_permission_payload(role: Role) -> dict[str, Any]:
    role_name = role.name
    role_permissions = getattr(role, "__dict__", {}).get("permissions")
    enabled = set(permission_keys_for_role(role_name, role_permissions))
    return {
        "role": role_name,
        "label": ROLE_LABELS.get(role_name, role_name),
        "description": role.description,
        "permissions": [
            {
                "key": item.key,
                "label": item.label,
                "group": item.group,
                "description": item.description,
                "enabled": item.key in enabled,
            }
            for item in PERMISSION_DEFINITIONS
        ],
    }


def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def summarize_membership(membership: Membership | None) -> dict[str, Any]:
    if membership is None:
        return {
            "status": "inactive",
            "plan": None,
            "starts_at": None,
            "ends_at": None,
            "source": None,
            "note": None,
            "is_member": False,
            "days_remaining": None,
        }

    now = datetime.now(timezone.utc)
    ends_at = _aware_datetime(getattr(membership, "membership_ends_at", None))
    stored_status = getattr(membership, "membership_status", None) or "inactive"
    effective_status = stored_status
    if stored_status in ACTIVE_MEMBERSHIP_STATUSES and ends_at is not None and ends_at < now:
        effective_status = "expired"

    is_member = effective_status in ACTIVE_MEMBERSHIP_STATUSES
    days_remaining = None
    if ends_at is not None:
        seconds = (ends_at - now).total_seconds()
        days_remaining = max(0, ceil(seconds / 86400))

    return {
        "status": effective_status,
        "plan": getattr(membership, "membership_plan", None),
        "starts_at": getattr(membership, "membership_starts_at", None),
        "ends_at": getattr(membership, "membership_ends_at", None),
        "source": getattr(membership, "membership_source", None),
        "note": getattr(membership, "membership_note", None),
        "is_member": is_member,
        "days_remaining": days_remaining,
    }


async def seed_role_permissions(db: AsyncSession) -> None:
    result = await db.execute(select(Role).options(selectinload(Role.permissions)))
    roles = list(result.scalars().all())
    for role in roles:
        existing = {row.permission_key: row for row in role.permissions}
        defaults = DEFAULT_ROLE_PERMISSION_KEYS.get(role.name, set())
        for item in PERMISSION_DEFINITIONS:
            if item.key not in existing:
                db.add(
                    RolePermission(
                        role_id=role.id,
                        permission_key=item.key,
                        enabled=item.key in defaults,
                    )
                )
    await db.commit()


async def list_role_permissions(db: AsyncSession) -> list[dict[str, Any]]:
    await seed_role_permissions(db)
    result = await db.execute(
        select(Role)
        .options(selectinload(Role.permissions))
        .order_by(Role.id)
    )
    return [role_permission_payload(role) for role in result.scalars().all()]


async def set_role_permissions(
    db: AsyncSession,
    role_name: str,
    permission_keys: list[str],
) -> dict[str, Any]:
    unknown = sorted(set(permission_keys) - VALID_PERMISSION_KEYS)
    if unknown:
        raise ValueError(f"Unknown permission keys: {', '.join(unknown)}")

    await seed_role_permissions(db)
    result = await db.execute(
        select(Role)
        .where(Role.name == role_name)
        .options(selectinload(Role.permissions))
    )
    role = result.scalar_one_or_none()
    if role is None:
        raise ValueError(f"Unknown role: {role_name}")

    enabled_keys = set(permission_keys)
    rows = {row.permission_key: row for row in role.permissions}
    for item in PERMISSION_DEFINITIONS:
        row = rows.get(item.key)
        if row is None:
            row = RolePermission(role_id=role.id, permission_key=item.key)
            db.add(row)
        row.enabled = item.key in enabled_keys

    await db.commit()
    result = await db.execute(
        select(Role)
        .where(Role.name == role_name)
        .options(selectinload(Role.permissions))
    )
    return role_permission_payload(result.scalar_one())


async def _get_or_create_tenant(db: AsyncSession, role_name: str) -> Tenant:
    slug = role_to_platform_tenant_slug(role_name)
    name = "平台运营" if slug == DEFAULT_PLATFORM_TENANT_SLUG else "默认租户"
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is not None:
        return tenant

    tenant = Tenant(slug=slug, name=name, status="active")
    db.add(tenant)
    await db.flush()
    return tenant


async def _default_membership_for_role(
    db: AsyncSession,
    user: User,
    role_name: str,
) -> Membership:
    await ensure_user_platform_defaults(db, user)
    tenant = await _get_or_create_tenant(db, role_name)
    await db.execute(
        update(Membership)
        .where(Membership.user_id == user.id)
        .values(is_default=False)
    )
    result = await db.execute(
        select(Membership).where(
            Membership.tenant_id == tenant.id,
            Membership.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        membership = Membership(
            tenant_id=tenant.id,
            user_id=user.id,
            role_view=role_to_role_view(role_name),
            is_default=True,
        )
        db.add(membership)
        await db.flush()
    membership.role_view = role_to_role_view(role_name)
    membership.is_default = True
    return membership


async def get_user_with_authorization(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.role).selectinload(Role.permissions),
            selectinload(User.memberships).selectinload(Membership.tenant),
            selectinload(User.broker_accounts),
        )
    )
    return result.scalar_one_or_none()


async def update_user_authorization(
    db: AsyncSession,
    target_user: User,
    *,
    role_name: str | None,
    is_active: bool | None,
    membership_update: dict[str, Any] | None,
    actor_user_id: int | None,
) -> User:
    if role_name is not None:
        role_result = await db.execute(select(Role).where(Role.name == role_name))
        role = role_result.scalar_one_or_none()
        if role is None:
            raise ValueError(f"Unknown role: {role_name}")
        target_user.role_id = role.id
        await db.flush()
        await db.refresh(target_user, attribute_names=["role"])

    if is_active is not None:
        target_user.is_active = is_active

    current_role = target_user.role.name if target_user.role else "user"
    membership = await _default_membership_for_role(db, target_user, current_role)

    if membership_update:
        status_value = membership_update.get("status")
        if status_value is not None and status_value not in VALID_MEMBERSHIP_STATUSES:
            raise ValueError(
                "Invalid membership status. Must be one of: "
                + ", ".join(sorted(VALID_MEMBERSHIP_STATUSES))
            )

        old_status = membership.membership_status
        old_ends_at = membership.membership_ends_at

        field_map = {
            "status": "membership_status",
            "plan": "membership_plan",
            "starts_at": "membership_starts_at",
            "ends_at": "membership_ends_at",
            "source": "membership_source",
            "note": "membership_note",
        }
        for field_name, model_attr in field_map.items():
            if field_name in membership_update:
                setattr(membership, model_attr, membership_update[field_name])
        if membership.membership_source is None:
            membership.membership_source = "admin"

        db.add(
            MembershipEvent(
                membership_id=membership.id,
                user_id=target_user.id,
                event_type="updated",
                old_status=old_status,
                new_status=membership.membership_status,
                old_ends_at=old_ends_at,
                new_ends_at=membership.membership_ends_at,
                note=membership.membership_note,
                created_by_user_id=actor_user_id,
            )
        )

    now = datetime.now(timezone.utc)
    target_user.updated_at = now
    membership.updated_at = now
    await db.commit()
    loaded = await get_user_with_authorization(db, target_user.id)
    return loaded or target_user


async def list_membership_users(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    q: str | None = None,
) -> tuple[list[User], int]:
    options = (
        selectinload(User.role).selectinload(Role.permissions),
        selectinload(User.memberships).selectinload(Membership.tenant),
        selectinload(User.broker_accounts),
    )
    query = select(User).options(*options)
    count_query = select(func.count(func.distinct(User.id))).select_from(User)

    if status:
        query = query.join(Membership).where(Membership.membership_status == status)
        count_query = count_query.join(Membership).where(Membership.membership_status == status)

    if q:
        like_pattern = f"%{q}%"
        query = query.where((User.name.ilike(like_pattern)) | (User.email.ilike(like_pattern)))
        count_query = count_query.where(
            (User.name.ilike(like_pattern)) | (User.email.ilike(like_pattern))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(result.scalars().unique().all()), total


def default_membership_for_user(user: User) -> Membership | None:
    memberships = getattr(user, "__dict__", {}).get("memberships")
    if not memberships:
        return None
    values = list(memberships)
    return next((item for item in values if item.is_default), values[0])


def role_permissions_for_user(user: User) -> list[str]:
    role = getattr(user, "role", None)
    role_name = role.name if role else "user"
    role_permissions = getattr(role, "__dict__", {}).get("permissions") if role else None
    return permission_keys_for_role(role_name, role_permissions)
