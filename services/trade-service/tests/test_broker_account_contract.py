import pytest
from pydantic import ValidationError

from app.platform_schemas import BrokerAccountView, BrokerAdapterCapability


def test_paper_account_view_is_read_only_platform_contract():
    capability = BrokerAdapterCapability.for_adapter("paper")

    account = BrokerAccountView(
        tenant_id="tenant-default",
        owner_user_id="12",
        account_id="paper-001",
        account_name="默认模拟账户",
        adapter="paper",
        trade_mode="paper",
        is_default=True,
        can_trade=True,
        can_sync_positions=True,
        capability=capability,
        total_assets=1_000_000,
        available=800_000,
        market_value=200_000,
    )

    assert account.adapter == "paper"
    assert account.visibility == "private"
    assert account.data_scope == "account"
    assert account.capability.supports_paper_trading is True
    assert account.capability.supports_live_trading is False
    assert account.capability.requires_local_gateway is False


def test_xtquant_account_view_marks_gateway_and_live_capabilities():
    capability = BrokerAdapterCapability.for_adapter("xtquant_qmt")

    account = BrokerAccountView(
        tenant_id="tenant-alpha",
        owner_user_id="88",
        account_id="qmt-880001",
        account_name="QMT 实盘账户",
        adapter="xtquant_qmt",
        trade_mode="live",
        is_default=False,
        can_trade=False,
        can_sync_positions=True,
        capability=capability,
    )

    assert account.adapter == "xtquant_qmt"
    assert account.trade_mode == "live"
    assert account.capability.supports_live_trading is True
    assert account.capability.requires_local_gateway is True
    assert "LIMIT" in account.capability.order_types


def test_paper_adapter_cannot_be_declared_as_live_account():
    with pytest.raises(ValidationError):
        BrokerAccountView(
            tenant_id="tenant-default",
            owner_user_id="12",
            account_id="paper-live",
            account_name="错误账户",
            adapter="paper",
            trade_mode="live",
            capability=BrokerAdapterCapability.for_adapter("paper"),
        )
