from types import SimpleNamespace

from app.platform_scope import build_order_scope, build_paper_account_view, build_risk_verdict


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


def test_build_order_scope_includes_platform_boundaries():
    scope = build_order_scope(
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
    )

    assert scope == {
        "tenant_id": "tenant-alpha",
        "owner_user_id": "7",
        "account_id": "paper-u7",
        "visibility": "private",
        "data_scope": "account",
    }


def test_build_risk_verdict_reject_includes_context_and_payload():
    risk_result = SimpleNamespace(
        passed=False,
        requires_confirmation=False,
        to_dict=lambda: {
            "passed": False,
            "requires_confirmation": False,
            "confirm_reason": "",
            "checks": [{"rule": "capital", "level": "reject"}],
        },
    )

    verdict = build_risk_verdict(
        risk_result,
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        symbol="300750",
        trade_mode="paper",
        decision_context_id="CTX-1",
        candidate_id="CAND-1",
        plan_id="PLAN-1",
    )

    assert verdict["verdict_id"].startswith("RV-")
    assert verdict["tenant_id"] == "tenant-alpha"
    assert verdict["owner_user_id"] == "7"
    assert verdict["account_id"] == "paper-u7"
    assert verdict["result"] == "reject"
    assert verdict["scope"] == "order"
    assert verdict["symbol"] == "300750"
    assert verdict["decision_context_id"] == "CTX-1"
    assert verdict["candidate_id"] == "CAND-1"
    assert verdict["plan_id"] == "PLAN-1"
    assert verdict["risk_check"]["checks"][0]["rule"] == "capital"
