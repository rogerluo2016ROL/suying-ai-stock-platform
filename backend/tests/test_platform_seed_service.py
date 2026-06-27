from types import SimpleNamespace

from app.services.platform_service import (
    DEFAULT_PLATFORM_TENANT_SLUG,
    DEFAULT_TENANT_SLUG,
    default_broker_account_id,
    role_to_platform_tenant_slug,
    role_to_role_view,
)


def _user(user_id: int, role: str):
    return SimpleNamespace(id=user_id, role=SimpleNamespace(name=role))


def test_role_view_mapping_for_seeded_memberships():
    assert role_to_role_view("admin") == "admin"
    assert role_to_role_view("internal_analyst") == "trader"
    assert role_to_role_view("external_analyst") == "trader"
    assert role_to_role_view("user") == "investor"


def test_role_to_platform_tenant_slug_separates_admin_from_default_users():
    assert role_to_platform_tenant_slug("admin") == DEFAULT_PLATFORM_TENANT_SLUG
    assert role_to_platform_tenant_slug("internal_analyst") == DEFAULT_TENANT_SLUG
    assert role_to_platform_tenant_slug("user") == DEFAULT_TENANT_SLUG


def test_default_broker_account_id_is_unique_per_user():
    assert default_broker_account_id(_user(7, "user")) == "paper-u7"
    assert default_broker_account_id(_user(8, "internal_analyst")) == "paper-u8"
