"""Contract tests for the supply-chain V2 business-tag migration."""

from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "020_supply_chain_business_tag_tracking.py"
)

L8_STATUS_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "021_business_tag_l8_evidence_status.py"
)


def test_supply_chain_v2_migration_defines_required_tables():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    required_tables = [
        "supply_chain_hierarchy_nodes",
        "supply_chain_deconstruct_views",
        "company_business_segments",
        "business_tag_mapping",
        "business_tag_evidence_events",
        "business_tag_stage_tracking",
        "business_tag_three_high_scores",
        "business_tag_expectation_gap_scores",
    ]

    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql


def test_supply_chain_v2_migration_keeps_core_v2_columns():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    required_columns = [
        "layer_level TEXT NOT NULL",
        "l1_l8_path JSONB NOT NULL DEFAULT '[]'",
        "revenue_ratio DOUBLE PRECISION",
        "gross_profit_ratio DOUBLE PRECISION",
        "research_stage TEXT NOT NULL DEFAULT 'R0'",
        "commercialization_stage TEXT NOT NULL DEFAULT 'C0'",
        "growth_score DOUBLE PRECISION",
        "profit_score DOUBLE PRECISION",
        "moat_score DOUBLE PRECISION",
        "expectation_gap_score DOUBLE PRECISION",
        "reviewer TEXT",
        "review_note TEXT",
        "reviewed_at TIMESTAMP",
    ]

    for column_contract in required_columns:
        assert column_contract in sql


def test_l8_evidence_status_migration_defines_per_dimension_table():
    sql = L8_STATUS_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS business_tag_l8_evidence_status" in sql
    assert "dimension_id TEXT NOT NULL" in sql
    assert "dimension_name TEXT NOT NULL" in sql
    assert "evidence_event_ids JSONB NOT NULL DEFAULT '[]'" in sql
    assert "UNIQUE (mapping_id, dimension_id)" in sql
