from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from kronos_factors.engine.cb_floor import CbFloorEngine
from tools.cb_backtest import parse_forward_days


def test_rating_gate_accepts_a_and_above():
    assert CbFloorEngine._rating_passes("AAA")
    assert CbFloorEngine._rating_passes("AA+")
    assert CbFloorEngine._rating_passes("A")
    assert not CbFloorEngine._rating_passes("BBB")
    assert not CbFloorEngine._rating_passes("")
    assert not CbFloorEngine._rating_passes(None)


def test_parse_maturity_call_price_extracts_number_from_text():
    assert CbFloorEngine._parse_maturity_call_price("到期赎回价110元") == 110.0
    assert CbFloorEngine._parse_maturity_call_price("108.5") == 108.5
    assert CbFloorEngine._parse_maturity_call_price(None) is None


def test_estimate_maturity_call_price_from_coupon_schedule():
    rate_clause = (
        "20200730-20210729,票面利率:0.50%;"
        "20210730-20220729,票面利率:0.70%;"
        "20220730-20230729,票面利率:1.00%;"
        "20230730-20240729,票面利率:1.80%;"
        "20240730-20250729,票面利率:2.50%;"
        "20250730-20260729,票面利率:3.00%"
    )
    assert CbFloorEngine._estimate_maturity_call_price(100.0, 3.0, rate_clause) == 109.5
    assert CbFloorEngine._estimate_maturity_call_price(100.0, 2.0, "") == 102.0


def test_resolve_maturity_call_price_prefers_announced_call_price():
    price, source = CbFloorEngine._resolve_maturity_call_price(
        announced_call_price=118.0,
        raw_maturity_call_price=None,
        par=100.0,
        coupon_rate=3.0,
        rate_clause="票面利率:3.00%",
    )
    assert price == 118.0
    assert source == "cb_call.call_price"


def test_price_gap_gate_requires_within_five_yuan():
    passed, score, gap = CbFloorEngine._price_gap_score(112.0, 110.0)
    assert passed is True
    assert gap == 2.0
    assert score > 0

    passed, score, gap = CbFloorEngine._price_gap_score(116.0, 110.0)
    assert passed is False
    assert gap == 6.0
    assert score == 0.0


def test_price_floor_requires_above_108_yuan():
    assert CbFloorEngine._price_floor_passes(108.01) is True
    assert CbFloorEngine._price_floor_passes(108.0) is False
    assert CbFloorEngine._price_floor_passes(88.35) is False
    assert CbFloorEngine._price_floor_passes(None) is False


def test_days_to_maturity():
    assert CbFloorEngine._days_to_maturity(date(2027, 6, 30), date(2026, 6, 30)) == 365


def test_route_a_rewards_low_premium_theme_and_liquidity():
    score = CbFloorEngine._route_a_theme_score(
        premium_score=90.0,
        theme_score=80.0,
        liquidity_score=70.0,
    )
    assert score == 82.0


def test_route_b_rewards_revision_countdown_and_history():
    score = CbFloorEngine._route_b_revision_score(
        revision_countdown_score=90.0,
        revision_history_score=80.0,
        governance_score=60.0,
    )
    assert score == 79.0


def test_combined_route_labels():
    assert CbFloorEngine._combined_route(80, 78) == "A+B共振"
    assert CbFloorEngine._combined_route(80, 40) == "A低溢价题材"
    assert CbFloorEngine._combined_route(40, 80) == "B下修事件"
    assert CbFloorEngine._combined_route(50, 45) == "底价观察"


def test_pledge_score_rewards_low_pledge_ratio():
    assert CbFloorEngine._pledge_score(5.0) == 100.0
    assert CbFloorEngine._pledge_score(20.0) == 70.0
    assert CbFloorEngine._pledge_score(40.0) == 35.0
    assert CbFloorEngine._pledge_score(None) == 50.0


def test_liquidity_proxy_scores_amount_against_remaining_size():
    assert CbFloorEngine._liquidity_proxy_score(amount=20_000_000, remain_size=200_000_000) == 100.0
    assert CbFloorEngine._liquidity_proxy_score(amount=2_000_000, remain_size=200_000_000) == 50.0
    assert CbFloorEngine._liquidity_proxy_score(amount=None, remain_size=200_000_000) == 50.0


def test_premium_gate_requires_revision_signal_above_30_percent():
    assert CbFloorEngine._premium_revision_gate(29.9, 30.0, 20.0) is True
    assert CbFloorEngine._premium_revision_gate(30.1, 80.0, 20.0) is True
    assert CbFloorEngine._premium_revision_gate(30.1, 30.0, 80.0) is False
    assert CbFloorEngine._premium_revision_gate(30.1, 30.0, 20.0) is False
    assert CbFloorEngine._premium_revision_gate(None, 30.0, 20.0) is False


def test_revision_countdown_score_from_stock_closes():
    closes = [8.0] * 15 + [9.0] * 15
    assert CbFloorEngine._revision_countdown_score_from_closes(closes, 10.0) == 60.0
    closes = [8.0] * 12 + [9.0] * 18
    assert CbFloorEngine._revision_countdown_score_from_closes(closes, 10.0) == 50.0
    closes = [8.0] * 5 + [9.0] * 25
    assert CbFloorEngine._revision_countdown_score_from_closes(closes, 10.0) == 30.0


def test_revision_announcement_signal_prioritizes_no_revision():
    titles = [
        "关于预计触发转股价格向下修正条件的提示性公告",
        "关于不向下修正仙乐转债转股价格的公告",
    ]
    assert CbFloorEngine._revision_announcement_signal(titles) == "no_revision"
    assert CbFloorEngine._revision_announcement_signal(["关于预计触发转股价格向下修正条件的提示性公告"]) == "expected_trigger"
    assert CbFloorEngine._revision_announcement_signal(["关于调整可转债转股价格的公告"]) == "neutral"


def test_revision_announcement_signal_does_not_exclude_this_time_no_revision():
    titles = ["关于本次不向下修正威唐转债转股价格的公告"]
    signal = CbFloorEngine._revision_announcement_signal(titles)
    assert signal == "neutral"
    assert CbFloorEngine._revision_signal_allows_pick(signal) is True


def test_no_revision_signal_is_hard_exclusion():
    assert CbFloorEngine._revision_signal_allows_pick("no_revision") is False
    assert CbFloorEngine._revision_signal_allows_pick("expected_trigger") is True
    assert CbFloorEngine._revision_signal_allows_pick("neutral") is True


def test_revision_countdown_score_uses_announcement_signal():
    assert CbFloorEngine._revision_countdown_score("no_revision", 90.0) == 0.0
    assert CbFloorEngine._revision_countdown_score("expected_trigger", 30.0) == 90.0
    assert CbFloorEngine._revision_countdown_score("neutral", 60.0) == 60.0


def test_ownership_state_control_detection():
    assert CbFloorEngine._detect_state_control("实际控制人为北京市国资委", "") is True
    assert CbFloorEngine._detect_state_control("中央企业控股", "") is True
    assert CbFloorEngine._detect_state_control("", "地方国企背景") is True
    assert CbFloorEngine._detect_state_control("民营企业", "创始人控股") is False
    assert CbFloorEngine._is_state_control("000401", "", "") is True


def test_strong_redemption_call_is_hard_exclusion():
    assert CbFloorEngine._is_strong_redemption_call("公告实施强赎") is True
    assert CbFloorEngine._is_strong_redemption_call("公告提示强赎") is True
    assert CbFloorEngine._is_strong_redemption_call("公告到期赎回") is False
    assert CbFloorEngine._is_strong_redemption_call(None) is False


def test_bank_industry_is_hard_exclusion():
    assert CbFloorEngine._is_bank_industry("银行") is True
    assert CbFloorEngine._is_bank_industry("股份制银行") is True
    assert CbFloorEngine._is_bank_industry("医药商业") is False
    assert CbFloorEngine._is_bank_industry(None) is False


def test_parse_forward_days_accepts_comma_list():
    assert parse_forward_days("5,10,20") == [5, 10, 20]
    assert parse_forward_days("5") == [5]
