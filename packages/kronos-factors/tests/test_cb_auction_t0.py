from kronos_factors.engine.cb_auction_t0 import (
    _is_noise_concept,
    _normalize_stock_code,
    _risk_notes,
    _theme_score,
)


def test_normalize_stock_code_handles_suffix_and_plain_code():
    assert _normalize_stock_code("300001.SZ") == "300001"
    assert _normalize_stock_code("600000") == "600000"
    assert _normalize_stock_code(None) == ""


def test_noise_concept_filter_removes_style_and_region_labels():
    assert _is_noise_concept("昨日涨停") is True
    assert _is_noise_concept("百日新高") is True
    assert _is_noise_concept("浙江") is True
    assert _is_noise_concept("机器人") is False
    assert _is_noise_concept("固态电池") is False


def test_risk_notes_are_annotations():
    row = {
        "call_status": "公告实施强赎",
        "premium_rate": 68.2,
        "cb_amount": 5_000_000,
        "remain_size": 1_800_000_000,
        "delist_date": "2026-07-05",
    }

    notes = _risk_notes(row)

    assert "强赎中" in notes
    assert "高溢价68.2%" in notes
    assert "成交额偏低500.0万" in notes
    assert "剩余规模18.00亿" in notes
    assert "退市日期2026-07-05" in notes


def test_theme_score_ignores_risk_fields():
    safe = {
        "is_direct_trigger": False,
        "matched_concept_count": 2,
        "trigger_stock_count_sum": 3,
        "matched_fd_amount": 2_000_000_000,
        "concept_size_min": 8,
        "premium_rate": 2.0,
        "call_status": "安全",
    }
    risky = dict(safe, premium_rate=80.0, call_status="公告实施强赎")

    assert _theme_score(safe) == _theme_score(risky)
