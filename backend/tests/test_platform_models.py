from app.models.base import Base
from app.models.platform import BrokerAccount, Membership, Tenant
from app.models.user import User


def test_platform_tables_are_registered_in_metadata():
    assert "tenants" in Base.metadata.tables
    assert "memberships" in Base.metadata.tables
    assert "broker_accounts" in Base.metadata.tables


def test_tenant_membership_and_broker_account_columns():
    tenants = Base.metadata.tables["tenants"]
    memberships = Base.metadata.tables["memberships"]
    broker_accounts = Base.metadata.tables["broker_accounts"]

    assert {"id", "name", "slug", "status", "created_at", "updated_at"}.issubset(tenants.c.keys())
    assert {"tenant_id", "user_id", "role_view", "is_default"}.issubset(memberships.c.keys())
    assert {
        "tenant_id",
        "owner_user_id",
        "account_id",
        "account_name",
        "adapter",
        "trade_mode",
        "is_default",
        "can_trade",
    }.issubset(broker_accounts.c.keys())

    fk_targets = {fk.target_fullname for fk in memberships.foreign_keys}
    assert "tenants.id" in fk_targets
    assert "users.id" in fk_targets


def test_platform_model_relationship_names():
    assert Tenant.memberships.property.mapper.class_ is Membership
    assert Tenant.broker_accounts.property.mapper.class_ is BrokerAccount
    assert Membership.tenant.property.mapper.class_ is Tenant
    assert BrokerAccount.tenant.property.mapper.class_ is Tenant
    assert User.memberships.property.mapper.class_ is Membership
    assert User.broker_accounts.property.mapper.class_ is BrokerAccount
