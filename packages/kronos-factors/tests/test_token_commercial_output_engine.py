import pytest

from kronos_factors.engine.token_commercial_output import (
    classify_token_role,
    derive_token_pool,
    normalize_stock_code,
    score_token_dimensions,
)


def test_normalize_stock_code_merges_exchange_suffixes():
    assert normalize_stock_code("300308.SZ") == "300308"
    assert normalize_stock_code("SH.688041") == "688041"
    assert normalize_stock_code("300308") == "300308"


def test_broad_cloud_tag_needs_specific_evidence():
    assert classify_token_role("云服务", {}) is None
    assert classify_token_role("推理API云服务", {"api_calls": 100}) == "L6"
    assert classify_token_role("AI服务器", {"verified_supply": True}) == "L4"
    assert classify_token_role("高速光模块", {"verified_supply": True}) == "L5"


@pytest.mark.parametrize("grade,review,facts,expected", [
    ("E0", "candidate", {}, "D"),
    ("E1", "approved", {"product": True}, "D"),
    ("E2", "approved", {"verified_supply": True}, "C"),
    ("E3", "approved", {"customer_usage": True, "running": True}, "B"),
    ("E4", "approved", {"token_revenue": True}, "A"),
    ("E5", "approved", {"token_revenue": True, "continuous_cashflow": True}, "A"),
    ("E4", "rejected", {"token_revenue": True}, None),
])
def test_pool_gate(grade, review, facts, expected):
    assert derive_token_pool(grade, review, facts)[0] == expected


def test_score_does_not_fill_missing_dimensions():
    result = score_token_dimensions({"business_authenticity": 80, "token_value_capture": 60})
    assert result["coverage_ratio"] == pytest.approx(0.4)
    assert result["weighted_score"] == pytest.approx(70.0)
    assert result["formal_ranking_eligible"] is False
