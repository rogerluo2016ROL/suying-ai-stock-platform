"""HTTP and service contracts for supply-chain selection V2."""

from datetime import date
from urllib.parse import urlsplit

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
                "catalyst_score": 55,
                "risk_score": 20,
                "confidence_score": 80,
                "opportunity_score": 60.5,
                "evidence_level": "E4",
                "data_limitations": [],
            }
        ],
        "data_limitations": [],
    }


def test_candidates_return_primary_mapping_and_six_scores_on_public_path(monkeypatch):
    monkeypatch.setattr(
        selection_service,
        "list_selection_candidates",
        lambda **kwargs: candidate_payload(),
    )

    response = client.get(
        "/api/v1/screener/supply-chain/selection/candidates",
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
    assert item["catalyst_score"] == 55
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
                "catalyst_score": 55,
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
                "catalyst_score": None,
                "risk_score": 25,
                "confidence_score": 70,
                "opportunity_score": 50,
                "metadata": {"token": "must-not-leak"},
                "source_url": (
                    "https://user:password@example.com/report"
                    "?X-Amz-Signature=must-not-leak&safe=ok"
                ),
                "pool_state_status": "current-only",
                "next_validation_event": "current-only",
                "next_validation_date": "2026-08-01",
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


class RepositoryWithMissingCatalyst:
    def fetch_candidate_rows(self, **kwargs):
        return [
            {
                "code": "003021",
                "mapping_id": "m1",
                "benefit_score": 72,
                "expectation_gap_score": 60,
                "catalyst_score": None,
                "risk_score": 20,
                "confidence_score": 80,
                "opportunity_score": None,
                "evidence_level": "E4",
                "independent_revenue": True,
                "pool_code": "A",
            }
        ]


def test_candidate_contract_reports_missing_catalyst_without_neutral_fill():
    result = selection_service.list_selection_candidates(
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        pool=None,
        model_version="v2.0",
        limit=50,
        offset=0,
        repository=RepositoryWithMissingCatalyst(),
    )

    assert result["items"][0]["catalyst_score"] is None
    assert "missing_catalyst_score:m1" in result["items"][0]["data_limitations"]


def test_public_and_deprecated_alias_routes_share_the_same_handler(monkeypatch):
    monkeypatch.setattr(
        selection_service,
        "list_selection_candidates",
        lambda **kwargs: candidate_payload(),
    )
    params = {"chain_id": "dexterous_hand", "trade_date": "2026-07-11"}

    public = client.get(
        "/api/v1/screener/supply-chain/selection/candidates",
        params=params,
    )
    alias = client.get("/api/v1/supply-chain/selection/candidates", params=params)

    assert public.status_code == alias.status_code == 200
    assert public.json() == alias.json()


def test_openapi_contains_only_public_selection_routes():
    paths = set(client.get("/openapi.json").json()["paths"])
    public = {
        "/api/v1/screener/supply-chain/selection/candidates",
        "/api/v1/screener/supply-chain/selection/stocks/{code}",
        "/api/v1/screener/supply-chain/selection/batch-score",
    }
    aliases = {
        "/api/v1/supply-chain/selection/candidates",
        "/api/v1/supply-chain/selection/stocks/{code}",
        "/api/v1/supply-chain/selection/batch-score",
    }

    assert public <= paths
    assert paths.isdisjoint(aliases)


class DetailRepository:
    def __init__(
        self,
        *,
        future_gap=False,
        missing_gate=False,
        future_transition=False,
    ):
        self.future_gap = future_gap
        self.missing_gate = missing_gate
        self.future_transition = future_transition

    def fetch_stock_detail_rows(self, **kwargs):
        factor_detail = {
            "expectation_gap_score": 60,
            "catalyst_score": None,
            "risk_score": 20,
            "pool_gates": {"combined": {"level": "E4", "max_pool_code": "A"}},
            "blocking_gate": None,
            "nested": {"api_key": "must-not-leak", "safe": "ok"},
            "userinfo_url": "https://user:password@example.com/report",
            "signed_url": "https://example.com/report?token=must-not-leak",
            "plain_url": "https://example.com/report",
            "relative_url": "/download/report?token=must-not-leak#private",
            "protocol_relative_url": (
                "//user:password@example.com/report?token=must-not-leak"
            ),
            "bare_relative_url": "download/report?token=must-not-leak",
            "urls": {"primary": "/nested/report?token=must-not-leak#private"},
            "links": {"download": "nested/report?token=must-not-leak"},
            "url": {"value": "/value/report?token=must-not-leak"},
            "source_metadata": {"internal": "must-not-leak"},
            "review_note": "internal-review-note",
            "signed_url": (
                "https://user:password@example.com/report"
                "?X-Amz-Signature=must-not-leak&safe=ok"
            ),
        }
        if self.missing_gate:
            factor_detail.pop("pool_gates")
        return [
            {
                "code": "003021",
                "mapping_id": "m1",
                "benefit_score": 72,
                "expectation_gap_score": 60,
                "catalyst_score": None,
                "risk_score": 20,
                "confidence_score": 80,
                "opportunity_score": None,
                "authenticity_detail": {"source": "audited"},
                "operating_quality_detail": {"growth": None},
                "benefit_detail": {"benefit_raw": 75},
                "factor_detail": factor_detail,
                "l1_l8_path": {
                    "evidence_gaps_as_of_date": (
                        "2026-07-12" if self.future_gap else "2026-07-09"
                    ),
                    "evidence_gaps": [
                        {
                            "requirement_id": "customer_validation",
                            "status": "missing",
                            "evidence_ids": [],
                            "next_action": "collect_official_customer_validation",
                            "authorization": "must-not-leak",
                        }
                    ],
                },
                "next_validation_event": "current-pool-state-event",
                "next_validation_date": "2026-07-20",
            }
        ]

    def fetch_transition_rows(self, **kwargs):
        if not self.future_transition:
            return []
        return [
            {
                "transition_id": "future-backfill",
                "transition_date": "2026-07-09",
                # Naive created_at is UTC; this is 2026-07-10 02:00 in Shanghai.
                "created_at": "2026-07-09T18:00:00",
            }
        ]

    def fetch_stock_explanation_rows(self, **kwargs):
        return {
            "m1": {
                "approved_evidence": [
                    {
                        "evidence_id": "f1",
                        "kind": "fact",
                        "status": "approved",
                        "fact_type": "order_award",
                        "source_level": "strong",
                        "publish_time": "2026-07-08T09:00:00+08:00",
                        "reviewed_at": "2026-07-09T10:00:00+08:00",
                        "review_note": "internal audit note",
                        "password": "must-not-leak",
                        "metadata": {"token": "must-not-leak"},
                        "review_note": "internal-review-note",
                    },
                    {
                        "evidence_id": "verified-is-not-approved",
                        "kind": "fact",
                        "status": "verified",
                        "publish_time": "2026-07-08T09:00:00+08:00",
                        "reviewed_at": "2026-07-09T10:00:00+08:00",
                    },
                    {
                        "evidence_id": "missing-review-time",
                        "kind": "fact",
                        "status": "approved",
                        "publish_time": "2026-07-08T09:00:00+08:00",
                    },
                    {
                        "evidence_id": "missing-publish-time",
                        "kind": "fact",
                        "status": "approved",
                        "reviewed_at": "2026-07-09T10:00:00+08:00",
                    },
                    {
                        "evidence_id": "future",
                        "kind": "fact",
                        "status": "approved",
                        "fact_type": "order_award",
                        "source_level": "strong",
                        "publish_time": "2026-07-12T09:00:00+08:00",
                        "reviewed_at": "2026-07-12T10:00:00+08:00",
                    },
                ],
                "pending_facts": [
                    {
                        "fact_id": "f2",
                        "status": "pending",
                        "fact_type": "customer_validation",
                        "metadata": {"token": "must-not-leak"},
                    }
                ],
                "rejected_facts": [],
            }
        }


def _contains_sensitive_key(value):
    sensitive = (
        "api_key",
        "token",
        "secret",
        "password",
        "authorization",
        "cookie",
        "credential",
        "dsn",
    )
    if isinstance(value, dict):
        return any(
            any(marker in str(key).casefold() for marker in sensitive)
            or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False


def _contains_key(value, target):
    if isinstance(value, dict):
        return target in value or any(_contains_key(item, target) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, target) for item in value)
    return False


def _contains_unsafe_url(value):
    if isinstance(value, dict):
        return any(_contains_unsafe_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_url(item) for item in value)
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        return False
    parsed = urlsplit(value)
    return bool(parsed.username or parsed.password or parsed.query)


def test_stock_detail_returns_nine_safe_asof_explanation_fields_per_mapping():
    result = selection_service.get_stock_selection_detail(
        code="003021",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        model_version="v2.0",
        repository=DetailRepository(),
    )

    mapping = result["mappings"][0]
    for field in (
        "approved_evidence",
        "pending_facts",
        "rejected_facts",
        "evidence_gaps",
        "score_components",
        "missing_score_inputs",
        "pool_gate",
        "blocking_gate",
        "next_validation",
    ):
        assert field in mapping
    assert [item["evidence_id"] for item in mapping["approved_evidence"]] == ["f1"]
    assert mapping["pending_facts"][0]["status"] == "pending"
    assert mapping["evidence_gaps"][0]["status"] == "missing"
    assert mapping["pool_gate"]["level"] == "E4"
    assert mapping["blocking_gate"] is None
    assert mapping["missing_score_inputs"] == ["catalyst_score", "opportunity_score"]
    assert mapping["next_validation"]["actions"] == [
        "collect_official_customer_validation"
    ]
    assert mapping["next_validation"]["event"] is None
    assert mapping["next_validation"]["date"] is None
    assert "unverifiable_historical_pool_state:m1" in mapping["data_limitations"]
    assert "pool_state_status" not in mapping
    assert "next_validation_event" not in mapping
    assert "next_validation_date" not in mapping
    assert "source_metadata" not in str(result)
    assert "review_note" not in str(result)
    assert "review_note" not in mapping["approved_evidence"][0]
    assert "user:password" not in str(result)
    assert "x-amz-signature" not in str(result).casefold()
    assert not _contains_sensitive_key(result)
    assert not _contains_key(result, "metadata")
    assert not _contains_key(result, "review_note")
    assert not _contains_unsafe_url(result)
    assert mapping["score_components"]["selection"]["plain_url"] == (
        "https://example.com/report"
    )
    assert mapping["score_components"]["selection"]["relative_url"] == (
        "/download/report"
    )
    assert mapping["score_components"]["selection"]["protocol_relative_url"] == (
        "//example.com/report"
    )
    assert mapping["score_components"]["selection"]["bare_relative_url"] == (
        "download/report"
    )
    assert mapping["score_components"]["selection"]["urls"] == {
        "primary": "/nested/report"
    }
    assert mapping["score_components"]["selection"]["links"] == {
        "download": "nested/report"
    }
    assert mapping["score_components"]["selection"]["url"] == {
        "value": "/value/report"
    }


def test_stock_detail_rejects_future_gap_snapshot_and_reports_missing_gate_detail():
    result = selection_service.get_stock_selection_detail(
        code="003021",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        model_version="v2.0",
        repository=DetailRepository(future_gap=True, missing_gate=True),
    )

    mapping = result["mappings"][0]
    assert mapping["evidence_gaps"] == []
    assert "evidence_gaps" not in mapping["l1_l8_path"]
    assert "evidence_gaps_as_of_date" not in mapping["l1_l8_path"]
    assert mapping["pool_gate"] is None
    assert "missing_pool_gate:m1" in mapping["data_limitations"]


def test_stock_and_batch_public_routes_match_deprecated_aliases(monkeypatch):
    monkeypatch.setattr(
        selection_service,
        "get_stock_selection_detail",
        lambda **kwargs: {
            "code": kwargs["code"],
            "chain_id": kwargs["chain_id"],
            "trade_date": kwargs["trade_date"].isoformat(),
            "model_version": kwargs["model_version"],
            "mappings": [],
            "transitions": [],
            "data_limitations": [],
        },
    )
    monkeypatch.setattr(
        selection_service,
        "batch_calculate_selection",
        lambda request: {"dry_run": request.dry_run, "mapping_count": 0},
    )
    params = {"chain_id": "dexterous_hand", "trade_date": "2026-07-11"}
    public_stock = client.get(
        "/api/v1/screener/supply-chain/selection/stocks/003021",
        params=params,
    )
    alias_stock = client.get(
        "/api/v1/supply-chain/selection/stocks/003021",
        params=params,
    )
    payload = {"chain_id": "dexterous_hand", "trade_date": "2026-07-11"}
    public_batch = client.post(
        "/api/v1/screener/supply-chain/selection/batch-score",
        json=payload,
    )
    alias_batch = client.post(
        "/api/v1/supply-chain/selection/batch-score",
        json=payload,
    )

    assert public_stock.status_code == alias_stock.status_code == 200
    assert public_stock.json() == alias_stock.json()
    assert public_batch.status_code == alias_batch.status_code == 200
    assert public_batch.json() == alias_batch.json()
    alias_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/supply-chain/selection")
    ]
    assert len(alias_routes) == 3
    assert all(route.deprecated is True for route in alias_routes)
    assert all(route.include_in_schema is False for route in alias_routes)


def test_candidate_secondary_mapping_is_recursively_sanitized():
    result = selection_service.list_selection_candidates(
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        pool=None,
        model_version="v2.0",
        limit=50,
        offset=0,
        repository=FakeRepository(),
    )

    secondary = result["items"][0]["secondary_mappings"][0]
    assert not _contains_sensitive_key(secondary)
    assert "must-not-leak" not in str(secondary)
    assert "user:password" not in str(secondary)
    assert "x-amz-signature" not in str(secondary).casefold()
    assert "pool_state_status" not in secondary
    assert "next_validation_event" not in secondary
    assert "next_validation_date" not in secondary


def test_stock_detail_filters_future_created_transition():
    result = selection_service.get_stock_selection_detail(
        code="003021",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        model_version="v2.0",
        repository=DetailRepository(future_transition=True),
    )

    assert result["transitions"] == []
