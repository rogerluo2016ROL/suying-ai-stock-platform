from app.domains.screening.service import _snapshot_rows


def test_snapshot_rows_prefers_real_scored_cross_section_over_trade_list():
    result = {
        "picks": [{"code": "000001"}],
        "factor_observations": [
            {"code": "000001", "total_score": 90},
            {"code": "000002", "total_score": 80},
        ],
    }
    assert [row["code"] for row in _snapshot_rows(result)] == ["000001", "000002"]


def test_snapshot_rows_does_not_invent_rows_when_observations_are_empty():
    assert _snapshot_rows({"picks": [], "factor_observations": []}) == []
    assert _snapshot_rows({"picks": [{"code": "000001"}]}) == [{"code": "000001"}]
