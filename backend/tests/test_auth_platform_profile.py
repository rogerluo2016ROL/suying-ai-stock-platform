from datetime import datetime, timezone
from types import SimpleNamespace

from app.routers.auth import build_token_user_response, build_user_response


def _user(role: str = "user", user_id: int = 42, **attrs):
    now = datetime(2026, 6, 27, tzinfo=timezone.utc)
    data = {
        "id": user_id,
        "name": "roger",
        "email": "roger@example.com",
        "role": SimpleNamespace(name=role),
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    data.update(attrs)
    return SimpleNamespace(**data)


def test_token_user_response_has_platform_defaults_for_investor():
    response = build_token_user_response(_user("user", user_id=9))

    assert response.tenant_id == "tenant-default"
    assert response.tenant_name == "默认租户"
    assert response.default_trade_account_id == "paper-default"
    assert response.trade_mode == "paper"
    assert response.broker_adapter == "paper"


def test_user_response_uses_default_membership_and_broker_account_when_present():
    tenant = SimpleNamespace(slug="tenant-alpha", name="Alpha 机构")
    membership = SimpleNamespace(tenant=tenant, is_default=True)
    account = SimpleNamespace(
        account_id="qmt-880001",
        adapter="xtquant_qmt",
        trade_mode="live",
        is_default=True,
    )

    response = build_user_response(
        _user(
            "internal_analyst",
            memberships=[membership],
            broker_accounts=[account],
        ),
    )

    assert response.tenant_id == "tenant-alpha"
    assert response.tenant_name == "Alpha 机构"
    assert response.default_trade_account_id == "qmt-880001"
    assert response.trade_mode == "live"
    assert response.broker_adapter == "xtquant_qmt"


def test_admin_defaults_to_platform_scope_without_trade_account():
    response = build_token_user_response(_user("admin", user_id=1))

    assert response.tenant_id == "platform"
    assert response.tenant_name == "平台运营"
    assert response.default_trade_account_id is None
    assert response.trade_mode == "paper"
    assert response.broker_adapter == "paper"
