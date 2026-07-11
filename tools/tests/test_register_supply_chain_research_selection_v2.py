"""Contracts for supply-chain research selection V2 registration."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "register_supply_chain_research_selection_v2.py"
)
SPEC = importlib.util.spec_from_file_location(
    "register_supply_chain_research_selection_v2",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_model_identity_and_stage_are_explicit():
    assert module.MODEL_ID == "supply_chain_research_selection_v2"
    assert module.MODEL_NAME == "产业链研究与选股模型"
    assert module.VERSION_TAG == "v2.0"
    assert module.MODEL_STAGE == "staging"


def test_snapshot_payload_keeps_audit_fields():
    payload = module.snapshot_factor_payload(
        {
            "pool_code": "A",
            "primary_mapping_id": "m1",
            "model_version": "v2.0",
            "benefit_score": 70,
            "expectation_gap_score": 60,
            "risk_score": 20,
            "confidence_score": 80,
            "opportunity_score": 60.5,
            "evidence_level": "E4",
            "coverage_ratio": 0.8,
            "veto_reasons": [],
        }
    )

    assert payload["pool_code"] == "A"
    assert payload["primary_mapping_id"] == "m1"
    assert payload["confidence_score"] == 80.0


def test_filter_snapshot_candidates_excludes_d_and_vetoed_rows():
    rows = [
        {
            "code": "1",
            "pool_code": "A",
            "veto_reasons": [],
            "benefit_score": 70,
            "evidence_level": "E4",
        },
        {
            "code": "2",
            "pool_code": "D",
            "veto_reasons": [],
            "benefit_score": 80,
            "evidence_level": "E1",
        },
        {
            "code": "3",
            "pool_code": "B",
            "veto_reasons": ["mapping_contradicted"],
            "benefit_score": 90,
            "evidence_level": "E3",
        },
    ]

    assert [row["code"] for row in module.filter_snapshot_candidates(rows)] == [
        "1"
    ]


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((statement, params))

    def fetchall(self):
        return self.rows


def test_fetch_pool_candidates_uses_one_primary_mapping_without_score_stacking():
    cursor = FakeCursor(
        [
            {
                "code": "000001",
                "mapping_id": "m1",
                "pool_code": "A",
                "benefit_score": 72,
                "evidence_level": "E4",
                "independent_revenue": True,
                "eligibility_status": "eligible",
                "veto_reasons": [],
            },
            {
                "code": "000001",
                "mapping_id": "m2",
                "pool_code": "B",
                "benefit_score": 60,
                "evidence_level": "E3",
                "independent_revenue": True,
                "eligibility_status": "eligible",
                "veto_reasons": [],
            },
        ]
    )

    rows = module.fetch_pool_candidates(
        cursor,
        trade_date="2026-07-11",
        model_version="v2.0",
    )

    assert len(rows) == 1
    assert rows[0]["primary_mapping_id"] == "m1"
    assert rows[0]["stock_score"] == 74.5
    assert cursor.executed[0][1] == ("2026-07-11", "v2.0")
