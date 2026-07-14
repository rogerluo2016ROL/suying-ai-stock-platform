from app.domains.supply_chain import service


def fake_snapshot(*_args, **_kwargs):
    return [
        {"mapping_id": "mapping-1", "pool_code": "A", "evidence_grade": "E5", "coverage_ratio": 0.9},
    ]


def fake_provisional_snapshot(*_args, **_kwargs):
    return [
        {"mapping_id": "mapping-d", "pool_code": "D", "evidence_grade": "E1", "coverage_ratio": 0.2},
    ]


def fake_mapping_detail(*_args, **_kwargs):
    return {
        "mapping_id": "mapping-1",
        "evidence_chain": [{"source_url": "https://example.test/evidence"}],
        "capacity_snapshots": [{"model_profile": "long_context_32k"}],
        "market_layer": {"separate_from_industry_evidence": True},
    }


def test_token_output_power_payload_keeps_market_layer_separate(monkeypatch):
    monkeypatch.setattr(service.repository, "fetch_token_output_power_snapshot", fake_snapshot)
    monkeypatch.setattr(service.repository, "fetch_token_output_power_provisional_snapshot", fake_provisional_snapshot)
    payload = service.token_output_power_payload(top_n=10, include_provisional=True)
    assert payload["chain_id"] == "ai_token_output_power"
    assert set(payload["layers"]) == {f"L{i}" for i in range(1, 9)}
    assert payload["industry_dimensions"] == [
        "function_value", "technology_route", "physical_bom",
        "value_pool", "competition_moat", "supply_demand_cycle",
        "evidence_validation",
    ]
    assert payload["market_layer"]["separate_from_industry_evidence"] is True
    assert payload["items"][0]["pool_code"] in {"A", "B", "C"}
    assert payload["provisional_items"][0]["pool_code"] == "D"


def test_token_output_power_mapping_detail_returns_traceable_evidence(monkeypatch):
    monkeypatch.setattr(service.repository, "fetch_token_output_power_mapping", fake_mapping_detail)
    payload = service.token_output_power_mapping_detail("mapping-1")
    assert payload["mapping_id"] == "mapping-1"
    assert payload["evidence_chain"][0]["source_url"]
    assert payload["capacity_snapshots"][0]["model_profile"] == "long_context_32k"
    assert payload["market_layer"]["separate_from_industry_evidence"] is True
