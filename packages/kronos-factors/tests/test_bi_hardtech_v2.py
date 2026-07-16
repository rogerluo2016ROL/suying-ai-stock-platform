import pytest

from kronos_factors.engine.bi_hardtech_v2 import (
    V2Config,
    confirm_t1_open,
    market_allows_entry,
    select_daily_entries,
)


@pytest.mark.parametrize(
    "regime,allowed",
    [
        ("bull", True),
        ("neutral", True),
        ("weak", False),
        ("recovery", False),
        ("bear", False),
        ("crash", False),
    ],
)
def test_market_gate(regime, allowed):
    assert market_allows_entry(regime) is allowed


@pytest.mark.parametrize(
    "open_price,accepted,reason",
    [
        (98.49, False, "gap_below_min"),
        (98.50, True, "accepted"),
        (103.00, True, "accepted"),
        (103.01, False, "gap_above_max"),
    ],
)
def test_open_gap_boundaries(open_price, accepted, reason):
    decision = confirm_t1_open(100.0, open_price, 0.1, V2Config())
    assert decision.accepted is accepted
    assert decision.reason == reason


def test_missing_or_negative_sector_rejects_entry():
    assert confirm_t1_open(100.0, 100.0, None, V2Config()).reason == "sector_missing"
    assert confirm_t1_open(100.0, 100.0, -0.01, V2Config()).reason == "sector_negative"


def test_daily_entries_keep_baseline_order_and_cap_at_two():
    picks = [
        {"code": "000001", "sector_change": 1.0},
        {"code": "000002", "sector_change": 0.5},
        {"code": "000003", "sector_change": 0.2},
    ]
    selected, rejected = select_daily_entries(
        picks,
        open_by_code={p["code"]: 100.0 for p in picks},
        close_by_code={p["code"]: 100.0 for p in picks},
        config=V2Config(),
    )
    assert [p["code"] for p in selected] == ["000001", "000002"]
    assert rejected[-1]["reason"] == "daily_limit"
