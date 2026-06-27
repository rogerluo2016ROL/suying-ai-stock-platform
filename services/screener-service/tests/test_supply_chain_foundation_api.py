import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.screener import router
import app.routers.screener as screener_router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_workbench_candidates_include_mapping_context(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_get_supply_chain_candidate_pool",
        lambda top_n, trade_date=None: [{
            "code": "301526",
            "name": "国际复材",
            "chain": "半导体",
            "layer": "材料",
            "score": 71.0,
            "rating": "B",
            "trade_signal": "观察",
            "node_id": "semiconductor_materials",
            "node_name": "材料",
            "mapping_confidence": 0.85,
            "mapping_status": "verified",
            "mapping_source": "main_business",
            "evidence_gaps": [],
        }],
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/workbench?top_n=10")

    assert r.status_code == 200
    candidate = r.json()["candidates"][0]
    assert candidate["node_id"] == "semiconductor_materials"
    assert candidate["node_name"] == "材料"
    assert candidate["mapping_confidence"] == 0.85
    assert candidate["mapping_status"] == "verified"
    assert candidate["mapping_source"] == "main_business"
    assert candidate["evidence_gaps"] == []


def test_mapping_review_queue_endpoint_returns_ranked_items(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_query_supply_chain_mapping_review_queue",
        lambda status, node_id, chain_id, limit, offset: {
            "total": 2,
            "limit": limit,
            "offset": offset,
            "items": [
                {
                    "code": "301526",
                    "name": "国际复材",
                    "node_id": "semiconductor_materials",
                    "node_name": "材料",
                    "chain_id": "semiconductor",
                    "confidence": 0.8,
                    "status": "pending_review",
                    "mapping_source": "introduction",
                    "evidence": ["电子级玻璃布"],
                    "evidence_gaps": ["是否有明确客户或供应链认证"],
                    "review_priority": 92.0,
                }
            ],
        },
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/mapping-review/queue?limit=10&status=pending_review")

    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["items"][0]["code"] == "301526"
    assert body["items"][0]["review_priority"] == 92.0


def test_mapping_review_decision_endpoint_updates_mapping(monkeypatch):
    captured = {}

    def fake_apply(code, node_id, decision, reviewer, note):
        captured.update({
            "code": code,
            "node_id": node_id,
            "decision": decision,
            "reviewer": reviewer,
            "note": note,
        })
        return {
            "status": "ok",
            "code": code,
            "node_id": node_id,
            "mapping_status": "verified",
            "review": {"decision": decision, "reviewer": reviewer, "note": note},
        }

    monkeypatch.setattr(screener_router, "_apply_supply_chain_mapping_review", fake_apply, raising=False)

    r = _client().post(
        "/api/v1/screener/supply-chain/mapping-review/301526/semiconductor_materials",
        json={"decision": "verified", "reviewer": "roger", "note": "主营业务和行业均匹配"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["mapping_status"] == "verified"
    assert captured == {
        "code": "301526",
        "node_id": "semiconductor_materials",
        "decision": "verified",
        "reviewer": "roger",
        "note": "主营业务和行业均匹配",
    }


def test_mapping_review_quality_endpoint_returns_hotspots(monkeypatch):
    monkeypatch.setattr(
        screener_router,
        "_query_supply_chain_mapping_quality",
        lambda: {
            "mapping_count": 15606,
            "status_counts": {"verified": 1069, "pending_review": 10511, "weak_evidence": 4026},
            "source_counts": {"main_business": 4366},
            "hotspot_nodes": [
                {
                    "node_id": "advanced_manufacturing_integration",
                    "node_name": "集成",
                    "pending_review": 846,
                    "weak_evidence": 68,
                    "verified": 24,
                    "review_pressure": 914,
                }
            ],
        },
        raising=False,
    )

    r = _client().get("/api/v1/screener/supply-chain/mapping-review/quality")

    assert r.status_code == 200
    body = r.json()
    assert body["mapping_count"] == 15606
    assert body["hotspot_nodes"][0]["review_pressure"] == 914
