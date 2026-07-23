import pytest
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "kronos-auth"))


def _require_role_stub(*_roles):
    async def _dependency():
        return {"sub": "7", "role": "user"}

    return _dependency


sys.modules["kronos_auth"] = types.SimpleNamespace(require_role=_require_role_stub)
sys.modules["app.database"] = types.SimpleNamespace(get_db=lambda: None)


@pytest.mark.asyncio
async def test_broker_connect_accepts_json_body_for_mock_qmt_sandbox(monkeypatch):
    from app import routes
    from app.schemas import BrokerConnectRequest

    captured = []

    async def fake_audit(db, **kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)
    monkeypatch.setattr(routes, "_live_broker", None, raising=False)
    monkeypatch.setattr(routes, "_broker_config", {}, raising=False)
    monkeypatch.setattr(routes, "_broker_connected_at", None, raising=False)

    response = await routes.broker_connect(
        body=BrokerConnectRequest(
            broker_name="mock_qmt",
            account_id="sandbox-qmt-001",
            server_ip="127.0.0.1",
            server_port=16001,
            environment="sandbox",
        ),
        db=object(),
        user={"sub": "7", "role": "admin"},
    )

    assert response["status"] == "connected"
    assert response["broker_name"] == "mock_qmt"
    assert response["account_id"] == "sandbox-qmt-001"
    assert response["environment"] == "sandbox"
    assert response["trade_mode"] == "paper"
    assert routes._broker_config["environment"] == "sandbox"
    assert routes._broker_config["adapter"] == "mock"
    assert captured[0]["action"] == "BROKER_CONNECT"
    assert captured[0]["mode"] == "paper"


@pytest.mark.asyncio
async def test_place_order_persists_full_lineage_for_b6_chain(monkeypatch):
    from app import routes
    from app.broker_interface import AccountInfo, OrderResult, OrderStatus
    from app.schemas import PlaceOrderRequest

    captured = {
        "decision_contexts": [],
        "risk_verdicts": [],
        "orders": [],
        "audits": [],
    }

    class FakeBroker:
        async def get_account(self):
            return AccountInfo(
                total_assets=1_000_000,
                available=900_000,
                frozen=0,
                market_value=0,
                total_pnl=0,
                daily_pnl=0,
            )

        async def get_positions(self):
            return []

        async def place_order(self, order):
            return OrderResult(
                order_id="ORD-B6",
                broker_order_id="",
                status=OrderStatus.FILLED,
                filled_qty=order.quantity,
                filled_avg_price=order.price,
                message="filled paper",
            )

    async def fake_decision_context(db, **kwargs):
        captured["decision_contexts"].append(kwargs)

    async def fake_risk_verdict(db, **kwargs):
        captured["risk_verdicts"].append(kwargs)

    async def fake_order(db, **kwargs):
        captured["orders"].append(kwargs)

    async def fake_audit(db, **kwargs):
        captured["audits"].append(kwargs)

    monkeypatch.setattr(routes, "_PaperEngineAdapter", lambda _engine: FakeBroker(), raising=False)
    monkeypatch.setattr(routes, "_decision_context_record_safe", fake_decision_context, raising=False)
    monkeypatch.setattr(routes, "_risk_verdict_record_safe", fake_risk_verdict, raising=False)
    monkeypatch.setattr(routes, "_order_record_safe", fake_order, raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)

    response = await routes.place_order(
        body=PlaceOrderRequest(
            code="300750",
            direction="BUY",
            price=218.5,
            volume=100,
            trade_mode="paper",
            decision_context_id="CTX-auto-strat-300750-1",
            candidate_id="CAND-300750",
            plan_id="PLAN-AUTO",
        ),
        tenant_id="tenant-alpha",
        account_id=None,
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response["order_id"] == "ORD-B6"
    assert response["decision_context_id"] == "CTX-auto-strat-300750-1"
    assert response["candidate_id"] == "CAND-300750"
    assert response["plan_id"] == "PLAN-AUTO"

    context = captured["decision_contexts"][0]
    assert context["decision_context_id"] == "CTX-auto-strat-300750-1"
    assert context["tenant_id"] == "tenant-alpha"
    assert context["account_id"] == "paper-u7"
    assert context["plan_id"] == "PLAN-AUTO"
    assert context["candidate_id"] == "CAND-300750"

    verdict = captured["risk_verdicts"][0]["verdict"]
    assert verdict["order_id"] == "ORD-B6"
    assert verdict["decision_context_id"] == "CTX-auto-strat-300750-1"
    assert verdict["candidate_id"] == "CAND-300750"
    assert verdict["plan_id"] == "PLAN-AUTO"

    order = captured["orders"][0]
    assert order["order_id"] == "ORD-B6"
    assert order["decision_context_id"] == "CTX-auto-strat-300750-1"
    assert order["candidate_id"] == "CAND-300750"
    assert order["plan_id"] == "PLAN-AUTO"
    assert order["risk_verdict"]["order_id"] == "ORD-B6"


@pytest.mark.asyncio
async def test_live_order_requires_connected_broker_and_never_falls_back_to_paper(monkeypatch):
    from fastapi import HTTPException

    from app import routes
    from app.broker_interface import AccountInfo, OrderResult, OrderStatus
    from app.schemas import PlaceOrderRequest

    captured_audits = []
    used_paper = False

    class FakePaperBroker:
        async def get_account(self):
            return AccountInfo(total_assets=1_000_000, available=900_000)

        async def get_positions(self):
            return []

        async def place_order(self, order):
            return OrderResult(
                order_id="PAPER-FALLBACK",
                status=OrderStatus.FILLED,
                filled_qty=order.quantity,
                filled_avg_price=order.price,
                message="paper fallback",
            )

    def fake_paper_adapter(_engine):
        nonlocal used_paper
        used_paper = True
        return FakePaperBroker()

    async def fake_audit(db, **kwargs):
        captured_audits.append(kwargs)

    monkeypatch.setattr(routes, "_live_broker", None, raising=False)
    monkeypatch.setattr(routes, "_LIVE_TRADING_ENABLED", True, raising=False)
    monkeypatch.setattr(routes, "_PaperEngineAdapter", fake_paper_adapter, raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)

    with pytest.raises(HTTPException) as exc:
        await routes.place_order(
            body=PlaceOrderRequest(
                code="300750",
                direction="BUY",
                price=218.5,
                volume=100,
                trade_mode="live",
                decision_context_id="CTX-live-1",
                candidate_id="CAND-live-1",
                plan_id="PLAN-live-1",
            ),
            tenant_id="tenant-alpha",
            account_id="qmt-001",
            db=object(),
            user={"sub": "7", "role": "user"},
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BROKER_NOT_CONNECTED"
    assert used_paper is False
    assert captured_audits[0]["action"] == "BROKER_NOT_CONNECTED"
    assert captured_audits[0]["mode"] == "live"


@pytest.mark.asyncio
async def test_pre_check_order_supports_paper_mode_and_audits_risk_pass(monkeypatch):
    from app import routes
    from app.broker_interface import AccountInfo
    from app.schemas import PlaceOrderRequest

    captured_audits = []

    class FakeBroker:
        async def get_account(self):
            return AccountInfo(total_assets=1_000_000, available=900_000)

        async def get_positions(self):
            return []

    async def fake_audit(db, **kwargs):
        captured_audits.append(kwargs)

    monkeypatch.setattr(routes, "_PaperEngineAdapter", lambda _engine: FakeBroker(), raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)

    response = await routes.pre_check_order(
        body=PlaceOrderRequest(
            code="300750",
            direction="BUY",
            price=218.5,
            volume=100,
            trade_mode="paper",
            decision_context_id="CTX-precheck-1",
            candidate_id="CAND-precheck-1",
            plan_id="PLAN-precheck-1",
        ),
        tenant_id="tenant-alpha",
        account_id=None,
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response["passed"] is True
    assert response["trade_mode"] == "paper"
    assert response["risk_verdict"]["result"] == "pass"
    assert response["risk_verdict"]["decision_context_id"] == "CTX-precheck-1"
    assert captured_audits[0]["action"] == "RISK_PASS"
    assert captured_audits[0]["mode"] == "paper"


@pytest.mark.asyncio
async def test_pre_check_live_requires_connected_broker(monkeypatch):
    from fastapi import HTTPException

    from app import routes
    from app.schemas import PlaceOrderRequest

    captured_audits = []
    used_paper = False

    def fake_paper_adapter(_engine):
        nonlocal used_paper
        used_paper = True
        raise AssertionError("live pre-check must not use paper fallback")

    async def fake_audit(db, **kwargs):
        captured_audits.append(kwargs)

    monkeypatch.setattr(routes, "_live_broker", None, raising=False)
    monkeypatch.setattr(routes, "_PaperEngineAdapter", fake_paper_adapter, raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)

    with pytest.raises(HTTPException) as exc:
        await routes.pre_check_order(
            body=PlaceOrderRequest(
                code="300750",
                direction="BUY",
                price=218.5,
                volume=100,
                trade_mode="live",
                decision_context_id="CTX-live-precheck-1",
            ),
            tenant_id="tenant-alpha",
            account_id="qmt-001",
            db=object(),
            user={"sub": "7", "role": "user"},
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "BROKER_NOT_CONNECTED"
    assert used_paper is False
    assert captured_audits[0]["action"] == "BROKER_NOT_CONNECTED"
    assert captured_audits[0]["mode"] == "live"


@pytest.mark.asyncio
async def test_cancel_order_records_audit_event(monkeypatch):
    from app import routes

    captured_audits = []

    class FakeEngine:
        def cancel_order(self, order_id):
            assert order_id == "ORD-CANCEL-1"
            return True

    async def fake_audit(db, **kwargs):
        captured_audits.append(kwargs)

    monkeypatch.setattr(routes, "engine", FakeEngine(), raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)

    response = await routes.cancel_order(
        order_id="ORD-CANCEL-1",
        trade_mode="paper",
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response == {"order_id": "ORD-CANCEL-1", "status": "cancelled", "trade_mode": "paper"}
    assert captured_audits[0]["action"] == "CANCEL_ORDER"
    assert captured_audits[0]["mode"] == "paper"
    assert captured_audits[0]["order_id"] == "ORD-CANCEL-1"


@pytest.mark.asyncio
async def test_get_risk_verdicts_queries_current_platform_scope(monkeypatch):
    from app import routes

    captured = {}

    async def fake_query(db, **kwargs):
        captured.update(kwargs)
        return {"total": 0, "page": kwargs["page"], "page_size": kwargs["page_size"], "records": []}

    monkeypatch.setattr(routes, "query_risk_verdicts", fake_query, raising=False)

    response = await routes.get_risk_verdicts(
        result="reject",
        trade_mode="paper",
        code="300750",
        decision_context_id="CTX-1",
        order_id="ORD-1",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
        page=2,
        page_size=10,
        tenant_id="tenant-alpha",
        account_id=None,
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response["page"] == 2
    assert captured == {
        "tenant_id": "tenant-alpha",
        "account_id": "paper-u7",
        "result": "reject",
        "trade_mode": "paper",
        "symbol": "300750",
        "decision_context_id": "CTX-1",
        "order_id": "ORD-1",
        "plan_id": "PLAN-1",
        "candidate_id": "CAND-1",
        "page": 2,
        "page_size": 10,
    }


@pytest.mark.asyncio
async def test_risk_verdict_record_safe_commits_success_and_rolls_back_failure(monkeypatch):
    from app import routes

    class FakeDb:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    async def fake_record(db, **kwargs):
        assert kwargs["verdict"]["verdict_id"] == "RV-test"
        assert kwargs["order_id"] == "ORD-1"
        return 101

    db = FakeDb()
    monkeypatch.setattr(routes, "record_risk_verdict", fake_record, raising=False)

    await routes._risk_verdict_record_safe(
        db,
        verdict={"verdict_id": "RV-test", "symbol": "300750"},
        order_id="ORD-1",
        symbol="300750",
    )

    assert db.commits == 1
    assert db.rollbacks == 0

    async def failing_record(db, **kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(routes, "record_risk_verdict", failing_record, raising=False)

    await routes._risk_verdict_record_safe(
        db,
        verdict={"verdict_id": "RV-test", "symbol": "300750"},
        order_id="ORD-2",
        symbol="300750",
    )

    assert db.commits == 1
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_get_decision_contexts_queries_current_platform_scope(monkeypatch):
    from app import routes

    captured = {}

    async def fake_query(db, **kwargs):
        captured.update(kwargs)
        return {"total": 0, "page": kwargs["page"], "page_size": kwargs["page_size"], "records": []}

    monkeypatch.setattr(routes, "query_decision_contexts", fake_query, raising=False)

    response = await routes.get_decision_contexts(
        decision_context_id="CTX-1",
        code="300750",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
        page=1,
        page_size=20,
        tenant_id="tenant-alpha",
        account_id=None,
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response["page"] == 1
    assert captured == {
        "tenant_id": "tenant-alpha",
        "account_id": "paper-u7",
        "decision_context_id": "CTX-1",
        "symbol": "300750",
        "plan_id": "PLAN-1",
        "candidate_id": "CAND-1",
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.asyncio
async def test_decision_context_record_safe_commits_success_and_rolls_back_failure(monkeypatch):
    from app import routes

    class FakeDb:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    async def fake_record_once(db, **kwargs):
        assert kwargs["decision_context_id"] == "CTX-1"
        assert kwargs["symbol"] == "300750"
        assert kwargs["payload"]["plan_id"] == "PLAN-1"
        return 201

    db = FakeDb()
    monkeypatch.setattr(routes, "record_decision_context_once", fake_record_once, raising=False)

    await routes._decision_context_record_safe(
        db,
        decision_context_id="CTX-1",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        symbol="300750",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
    )

    assert db.commits == 1
    assert db.rollbacks == 0

    async def failing_record_once(db, **kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(routes, "record_decision_context_once", failing_record_once, raising=False)

    await routes._decision_context_record_safe(
        db,
        decision_context_id="CTX-1",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        symbol="300750",
        plan_id="PLAN-1",
        candidate_id="CAND-1",
    )

    assert db.commits == 1
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_list_orders_queries_platform_scoped_order_ledger(monkeypatch):
    from app import routes

    captured = {}

    async def fake_query(db, **kwargs):
        captured.update(kwargs)
        return {"total": 0, "page": kwargs["page"], "page_size": kwargs["page_size"], "orders": []}

    monkeypatch.setattr(routes, "query_trade_orders", fake_query, raising=False)

    response = await routes.list_orders(
        trade_mode="paper",
        code="300750",
        page=1,
        page_size=20,
        tenant_id="tenant-alpha",
        account_id=None,
        db=object(),
        user={"sub": "7", "role": "user"},
    )

    assert response["page"] == 1
    assert captured == {
        "tenant_id": "tenant-alpha",
        "account_id": "paper-u7",
        "trade_mode": "paper",
        "code": "300750",
        "page": 1,
        "page_size": 20,
    }


@pytest.mark.asyncio
async def test_order_record_safe_commits_success_and_rolls_back_failure(monkeypatch):
    from app import routes

    class FakeDb:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    async def fake_record(db, **kwargs):
        assert kwargs["order_id"] == "ORD-1"
        assert kwargs["tenant_id"] == "tenant-alpha"
        assert kwargs["decision_context_id"] == "CTX-1"
        return 301

    db = FakeDb()
    monkeypatch.setattr(routes, "record_trade_order", fake_record, raising=False)

    await routes._order_record_safe(
        db,
        order_id="ORD-1",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        trade_mode="paper",
        code="300750",
        direction="BUY",
        price=218.5,
        volume=100,
        status="FILLED",
        decision_context_id="CTX-1",
        candidate_id="CAND-1",
        plan_id="PLAN-1",
        order_scope={"visibility": "private"},
        risk_verdict={"verdict_id": "RV-1"},
    )

    assert db.commits == 1
    assert db.rollbacks == 0

    async def failing_record(db, **kwargs):
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(routes, "record_trade_order", failing_record, raising=False)

    await routes._order_record_safe(
        db,
        order_id="ORD-2",
        tenant_id="tenant-alpha",
        owner_user_id="7",
        account_id="paper-u7",
        trade_mode="paper",
        code="300750",
        direction="BUY",
        price=218.5,
        volume=100,
        status="FILLED",
    )

    assert db.commits == 1
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_live_order_blocked_when_kill_switch_off(monkeypatch):
    """部署级总开关关闭时，live 下单一律 503 LIVE_TRADING_DISABLED（先于券商检查）。"""
    from fastapi import HTTPException

    from app import routes
    from app.schemas import PlaceOrderRequest

    used_paper = False

    def fake_paper_adapter(_engine):
        nonlocal used_paper
        used_paper = True
        raise AssertionError("kill-switch block must not reach broker selection")

    monkeypatch.setattr(routes, "_LIVE_TRADING_ENABLED", False, raising=False)
    monkeypatch.setattr(routes, "_PaperEngineAdapter", fake_paper_adapter, raising=False)

    with pytest.raises(HTTPException) as exc:
        await routes.place_order(
            body=PlaceOrderRequest(
                code="300750",
                direction="BUY",
                price=218.5,
                volume=100,
                trade_mode="live",
            ),
            tenant_id="tenant-alpha",
            account_id=None,
            db=object(),
            user={"sub": "7", "role": "user"},
        )

    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == "LIVE_TRADING_DISABLED"
    assert used_paper is False


@pytest.mark.asyncio
async def test_large_order_warn_requires_confirmed_flag(monkeypatch):
    """大额订单（WARN）未带 confirmed=true → 409 CONFIRMATION_REQUIRED，不放行。"""
    from fastapi import HTTPException

    from app import routes
    from app.broker_interface import AccountInfo
    from app.schemas import PlaceOrderRequest

    captured_audits = []

    class FakeBroker:
        async def get_account(self):
            return AccountInfo(total_assets=1_000_000, available=900_000)

        async def get_positions(self):
            return []

        async def place_order(self, order):
            raise AssertionError("unconfirmed large order must not reach broker")

    async def fake_audit(db, **kwargs):
        captured_audits.append(kwargs)

    async def fake_verdict_record(db, **kwargs):
        return None

    monkeypatch.setattr(routes, "_PaperEngineAdapter", lambda _engine: FakeBroker(), raising=False)
    monkeypatch.setattr(routes, "_audit_record_safe", fake_audit, raising=False)
    monkeypatch.setattr(routes, "_risk_verdict_record_safe", fake_verdict_record, raising=False)

    with pytest.raises(HTTPException) as exc:
        await routes.place_order(
            body=PlaceOrderRequest(
                code="300750",
                direction="BUY",
                price=100.0,
                volume=3000,  # ¥300,000 ≥ 250k WARN 阈值，≤ 500k REJECT 上限
                trade_mode="paper",
            ),
            tenant_id="tenant-alpha",
            account_id=None,
            db=object(),
            user={"sub": "7", "role": "user"},
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "CONFIRMATION_REQUIRED"
    assert captured_audits[-1]["action"] == "RISK_CONFIRM_REQUIRED"
