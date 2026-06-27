from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.platform_deps import (
    build_platform_context,
    require_account_scope,
    role_to_role_view,
)


def _user(role: str, user_id: int = 7, tenant_id: str | None = None):
    return SimpleNamespace(
        id=user_id,
        role=SimpleNamespace(name=role),
        tenant_id=tenant_id,
    )


def test_role_mapping_matches_platform_personas():
    assert role_to_role_view("admin") == "admin"
    assert role_to_role_view("internal_analyst") == "trader"
    assert role_to_role_view("external_analyst") == "trader"
    assert role_to_role_view("user") == "investor"


def test_non_admin_defaults_to_private_account_context():
    context = build_platform_context(
        current_user=_user("user", user_id=12),
        account_id_header="paper-001",
    )

    assert context.tenant_id == "tenant-default"
    assert context.user_id == 12
    assert context.role_view == "investor"
    assert context.account_id == "paper-001"
    assert context.visibility == "private"
    assert context.data_scope == "account"
    assert context.cross_tenant is False


def test_admin_can_switch_tenant_context_for_operations():
    context = build_platform_context(
        current_user=_user("admin", user_id=1),
        tenant_id_header="tenant-alpha",
    )

    assert context.tenant_id == "tenant-alpha"
    assert context.role_view == "admin"
    assert context.visibility == "tenant_shared"
    assert context.data_scope == "tenant"
    assert context.cross_tenant is True


def test_non_admin_cannot_switch_to_another_tenant():
    with pytest.raises(HTTPException) as exc_info:
        build_platform_context(
            current_user=_user("internal_analyst", tenant_id="tenant-a"),
            tenant_id_header="tenant-b",
        )

    assert exc_info.value.status_code == 403
    assert "Cross-tenant" in exc_info.value.detail


def test_require_account_scope_rejects_context_without_account():
    context = build_platform_context(current_user=_user("admin", user_id=1))

    with pytest.raises(HTTPException) as exc_info:
        require_account_scope(context)

    assert exc_info.value.status_code == 400
    assert "account" in exc_info.value.detail
