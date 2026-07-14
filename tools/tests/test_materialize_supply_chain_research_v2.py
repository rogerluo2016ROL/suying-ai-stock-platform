"""Contracts for V2 industry research materialization."""

import importlib.util
import sys
from datetime import date
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "materialize_supply_chain_research_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "materialize_supply_chain_research_v2",
    SCRIPT_PATH,
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def test_build_research_rows_keeps_unknown_dimensions_nullable():
    template = {
        "template_id": "demo",
        "layers": [
            {
                "layer_id": "demand",
                "order": 1,
                "name": "需求层",
                "definition": "真实需求",
                "segments": ["工业"],
                "research_dimensions": {
                    "function_value": {
                        "status": "known",
                        "score": 80,
                        "coverage_ratio": 1,
                        "evidence_ids": ["ev1"],
                    }
                },
            }
        ],
        "technology_routes": [],
        "transmission_edges": [],
    }

    rows = module.build_research_rows(template, date(2026, 7, 11))

    assert len(rows["dimensions"]) == 8
    known = next(
        row
        for row in rows["dimensions"]
        if row["dimension_id"] == "function_value"
    )
    missing = next(
        row for row in rows["dimensions"] if row["dimension_id"] == "value_pool"
    )
    assert known["score"] == 80
    assert missing["status"] == "unknown"
    assert missing["score"] is None
    assert missing["coverage_ratio"] == 0.0


def test_dexterous_template_expands_to_eight_nodes_and_sixty_four_dimensions():
    template = module.get_industry_template("dexterous_hand")

    rows = module.build_research_rows(template, date(2026, 7, 11))

    assert len(rows["nodes"]) == 8
    assert len(rows["dimensions"]) == 64
    assert rows["nodes"][0]["parent_node_id"] is None
    assert rows["nodes"][-1]["parent_node_id"] == "dexterous_hand_infrastructure"


def test_axial_flux_route_is_not_promoted_without_evidence():
    template = module.get_industry_template("dexterous_hand")

    rows = module.build_research_rows(template, date(2026, 7, 11))
    route = next(
        item
        for item in rows["routes"]
        if item["route_id"] == "dexterous_axial_flux_motor"
    )

    assert route["maturity_stage"] == "concept"
    assert route["review_status"] == "pending_review"
    assert route["last_strong_evidence_date"] is None
    assert route["performance_metrics"]["continuous_torque"] is None


def test_derived_mapping_is_capped_as_candidate_without_original_evidence():
    source = {
        "mapping_id": "source-m1",
        "code": "000001",
        "business_segment_id": "seg1",
        "tag_name": "空心杯电机",
        "evidence_ids": [],
    }

    first = module.build_derived_mapping(
        template_id="dexterous_hand",
        source=source,
        matched_keyword="空心杯电机",
    )
    second = module.build_derived_mapping(
        template_id="dexterous_hand",
        source=source,
        matched_keyword="空心杯电机",
    )

    assert first["mapping_id"] == second["mapping_id"]
    assert first["status"] == "candidate"
    assert first["confidence"] == 0.35
    assert first["evidence_ids"] == []
    assert first["l1_l8_path"][-1]["requires_original_evidence"] is True


def test_derived_mapping_normalizes_exchange_suffix_and_repairs_candidate_rows():
    source = {
        "mapping_id": "source-603662-sh",
        "code": "603662.SH",
        "business_segment_id": None,
        "tag_name": "力传感器",
        "evidence_ids": [],
    }
    row = module.build_derived_mapping(
        template_id="dexterous_hand",
        source=source,
        matched_keyword="力传感器",
    )

    class CaptureCursor:
        def __init__(self):
            self.executed = []

        def execute(self, statement, params):
            self.executed.append((statement, params))

    cursor = CaptureCursor()
    module._upsert_candidate_mappings(cursor, [row])

    assert row["code"] == "603662"
    statement, params = cursor.executed[0]
    assert "DO UPDATE SET code=EXCLUDED.code" in statement
    assert "business_tag_mapping.status = 'candidate'" in statement
    assert params[1] == "603662"


def test_node_score_does_not_convert_unknown_dimensions_to_zero():
    template = module.get_industry_template("dexterous_hand")
    rows = module.build_research_rows(template, date(2026, 7, 11))

    assert len(rows["node_scores"]) == 8
    assert all(row["total_score"] is None for row in rows["node_scores"])
    assert all(
        row["score_status"] == "insufficient_evidence"
        for row in rows["node_scores"]
    )


def test_dry_run_returns_plan_without_opening_database(monkeypatch):
    def forbidden_connect(*args, **kwargs):
        raise AssertionError("dry-run must not connect to PostgreSQL")

    monkeypatch.setattr(module.psycopg2, "connect", forbidden_connect)

    result = module.materialize(
        pg_url="postgresql://unused",
        template_id="dexterous_hand",
        as_of_date=date(2026, 7, 11),
        dry_run=True,
    )

    assert result["dry_run"] is True
    assert result["planned"]["nodes"] == 8
    assert result["planned"]["dimensions"] == 64
    assert result["planned"]["candidate_mappings"] == "requires_database_read"
