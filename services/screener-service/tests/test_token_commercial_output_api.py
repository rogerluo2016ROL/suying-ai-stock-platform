from app.domains.supply_chain import service


def fake_pools(*_args, **kwargs):
    if kwargs.get("pool_codes") == ("D",):
        return [{"mapping_id": "d1", "code": "603881", "pool_code": "D", "evidence_grade": "E0", "coverage_ratio": 0.1}]
    return [{"mapping_id": "a1", "code": "300308", "pool_code": "A", "evidence_grade": "E4", "coverage_ratio": 0.8}]


def fake_counts(*_args, **_kwargs):
    return {"mapping_count": 2, "unique_company_count": 2, "formal_company_count": 1, "domestic_output_count": 1, "overseas_output_count": 0}


def test_overview_separates_counts_and_market_layer(monkeypatch):
    monkeypatch.setattr(service.repository, "list_token_output_pools", fake_pools)
    monkeypatch.setattr(service.repository, "token_output_counts", fake_counts)
    payload = service.token_output_payload(top_n=20, include_provisional=True)
    assert payload["chain_id"] == "ai_token_output"
    assert payload["mapping_count"] == 2
    assert payload["unique_company_count"] == 2
    assert payload["formal_company_count"] == 1
    assert payload["market_layer_separate"] is True
    assert payload["items"][0]["pool_code"] == "A"
    assert payload["provisional_items"][0]["pool_code"] == "D"


def test_mapping_detail_exposes_provenance_and_gaps(monkeypatch):
    monkeypatch.setattr(service.repository, "get_token_output_evidence", lambda *_: {
        "mapping_id": "TOKENMAP-1", "source_mapping_ids": ["source-1"],
        "evidence_grade": "E0", "missing_fields": ["token_revenue"],
        "next_validation_node": "company_product_evidence",
    })
    detail = service.token_output_mapping_detail("TOKENMAP-1")
    assert detail["source_mapping_ids"] == ["source-1"]
    assert detail["missing_fields"] == ["token_revenue"]
    assert detail["market_layer_separate"] is True
