import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "materialize_ai_token_output.py"
SPEC = importlib.util.spec_from_file_location("materialize_token_output", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def evidence(**overrides):
    row = {
        "mapping_id": "mapping-1", "code": "300308", "layer_id": "L5",
        "evidence_grade": "E0", "review_status": "candidate",
        "product_verified": False, "verified_supply": False, "verified_order": False,
        "verified_project": False, "customer_usage_verified": False,
        "runtime_verified": False, "recurring_delivery_verified": False,
        "token_revenue_verified": False, "continuous_cashflow_verified": False,
        "market_signal_score": 0,
    }
    row.update(overrides)
    return row


def test_hardware_supply_can_reach_c_but_not_token_revenue_a():
    state = MODULE.build_pool_state(evidence(evidence_grade="E2", review_status="approved", verified_supply=True))
    assert state["pool_code"] == "C"
    assert "token_revenue_unverified" in state["reason_codes"]


def test_market_signal_does_not_change_industry_pool():
    state = MODULE.build_pool_state(evidence(evidence_grade="E1", review_status="approved", product_verified=True, market_signal_score=99))
    assert state["pool_code"] == "D"


def test_verified_revenue_reaches_a_only_with_approved_evidence():
    assert MODULE.build_pool_state(evidence(evidence_grade="E4", review_status="approved", token_revenue_verified=True))["pool_code"] == "A"
    assert MODULE.build_pool_state(evidence(evidence_grade="E4", review_status="pending_review", token_revenue_verified=True))["pool_code"] == "D"
