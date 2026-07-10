from datetime import date
from app.routers.screener import _normalize_picks, _with_screener_contract


def test_normalize_picks_adds_candidate_contract_fields():
    picks = _normalize_picks(
        [
            {
                "code": "300750",
                "name": "宁德时代",
                "close": 218.5,
                "total_score": 18.2,
            },
        ],
        "leader_auction",
    )

    pick = picks[0]
    assert pick["candidate_id"] == "CAND-leader_auction-300750"
    assert pick["source_module"] == "screener"
    assert pick["source_mode"] == "leader_auction"
    assert pick["visibility"] == "public"
    assert pick["data_scope"] == "public"
    assert pick["price"] == 218.5
    assert pick["score"] == 18.2


def test_screener_contract_adds_model_metadata_freshness_and_fallback():
    today = date.today().isoformat()
    result = _with_screener_contract(
        {"mode": "short", "picks": []},
        mode="short",
        trade_date=today,
        fallback_reason=None,
    )

    assert result["model_metadata"]["name"] == "screener-multi-strategy-v2"
    assert result["model_metadata"]["inference_mode"] == "short"
    assert result["data_freshness"]["status"] == "fresh"
    assert result["data_freshness"]["as_of"] == today
    assert result["fallback_reason"] is None
