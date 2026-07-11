"""HTTP and service contracts for supply-chain selection V2."""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domains.supply_chain.selection_repository import MissingSelectionTables
from app.domains.supply_chain.selection_router import router
from app.domains.supply_chain import selection_service


app = FastAPI()
app.include_router(router)
client = TestClient(app)


def candidate_payload():
    return {
        "trade_date": "2026-07-11",
        "chain_id": "dexterous_hand",
        "model_version": "v2.0",
        "items": [
            {
                "code": "000001",
                "pool_code": "A",
                "primary_mapping_id": "m1",
                "secondary_mappings": [],
                "benefit_score": 70,
                "expectation_gap_score": 60,
                "risk_score": 20,
                "confidence_score": 80,
                "opportunity_score": 60.5,
                "evidence_level": "E4",
                "data_limitations": [],
            }
        ],
        "data_limitations": [],
    }


def test_candidates_return_primary_mapping_and_five_scores(monkeypatch):
    monkeypatch.setattr(
        selection_service,
        "list_selection_candidates",
        lambda **kwargs: candidate_payload(),
    )

    response = client.get(
        "/api/v1/supply-chain/selection/candidates",
        params={
            "chain_id": "dexterous_hand",
            "trade_date": "2026-07-11",
            "pool": "A",
        },
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["primary_mapping_id"] == "m1"
    assert item["benefit_score"] == 70
    assert item["opportunity_score"] == 60.5


def test_candidates_missing_tables_returns_503_with_table_names(monkeypatch):
    def fail(**kwargs):
        raise MissingSelectionTables(["business_tag_selection_scores"])

    monkeypatch.setattr(selection_service, "list_selection_candidates", fail)

    response = client.get(
        "/api/v1/supply-chain/selection/candidates",
        params={"chain_id": "dexterous_hand", "trade_date": "2026-07-11"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["missing_tables"] == [
        "business_tag_selection_scores"
    ]


def test_stock_detail_passes_explicit_asof_parameters(monkeypatch):
    captured = {}

    def detail(**kwargs):
        captured.update(kwargs)
        return {
            "code": kwargs["code"],
            "chain_id": kwargs["chain_id"],
            "trade_date": kwargs["trade_date"].isoformat(),
            "mappings": [],
            "transitions": [],
            "data_limitations": [],
        }

    monkeypatch.setattr(selection_service, "get_stock_selection_detail", detail)

    response = client.get(
        "/api/v1/supply-chain/selection/stocks/000001",
        params={"chain_id": "dexterous_hand", "trade_date": "2026-07-11"},
    )

    assert response.status_code == 200
    assert captured["trade_date"] == date(2026, 7, 11)
    assert captured["model_version"] == "v2.0"


def test_batch_score_defaults_to_dry_run(monkeypatch):
    captured = {}

    def batch(request):
        captured["request"] = request
        return {
            "dry_run": request.dry_run,
            "chain_id": request.chain_id,
            "trade_date": request.trade_date.isoformat(),
            "mapping_count": 0,
        }

    monkeypatch.setattr(selection_service, "batch_calculate_selection", batch)

    response = client.post(
        "/api/v1/supply-chain/selection/batch-score",
        json={"chain_id": "dexterous_hand", "trade_date": "2026-07-11"},
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert captured["request"].mapping_ids == []


class FakeRepository:
    def fetch_candidate_rows(self, **kwargs):
        return [
            {
                "code": "000001",
                "mapping_id": "m1",
                "benefit_score": 72,
                "evidence_level": "E4",
                "independent_revenue": True,
                "pool_code": "A",
                "expectation_gap_score": 60,
                "risk_score": 20,
                "confidence_score": 80,
                "opportunity_score": 62,
            },
            {
                "code": "000001",
                "mapping_id": "m2",
                "benefit_score": 60,
                "evidence_level": "E3",
                "independent_revenue": False,
                "pool_code": "B",
                "expectation_gap_score": 55,
                "risk_score": 25,
                "confidence_score": 70,
                "opportunity_score": 50,
            },
        ]


def test_service_aggregates_stock_mappings_without_score_stacking():
    result = selection_service.list_selection_candidates(
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        pool=None,
        model_version="v2.0",
        limit=50,
        offset=0,
        repository=FakeRepository(),
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["primary_mapping_id"] == "m1"
    assert result["items"][0]["stock_score"] == 72
    assert len(result["items"][0]["secondary_mappings"]) == 1
