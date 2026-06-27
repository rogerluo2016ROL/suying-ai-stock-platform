from types import SimpleNamespace

from app.platform_scope import build_paper_account_view


def test_build_paper_account_view_includes_platform_boundaries():
    account = SimpleNamespace(
        total_capital=1_000_000,
        available=900_000,
        market_value=100_000,
        total_pnl=1200.5,
        daily_pnl=80.2,
    )

    view = build_paper_account_view(
        account,
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
    )

    assert view["tenant_id"] == "tenant-alpha"
    assert view["owner_user_id"] == "7"
    assert view["account_id"] == "paper-u7"
    assert view["adapter"] == "paper"
    assert view["trade_mode"] == "paper"
    assert view["data_scope"] == "account"
    assert view["total_capital"] == 1_000_000
