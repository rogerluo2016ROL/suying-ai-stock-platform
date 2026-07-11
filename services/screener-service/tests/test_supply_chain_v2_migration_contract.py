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

EVIDENCE_PIPELINE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "023_supply_chain_evidence_pipeline.py"
)

DATA_COLLECTION_CENTER_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "024_supply_chain_data_collection_center.py"
)

CAPEX_EVIDENCE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "025_business_tag_capex_evidence.py"
)

SELECTION_V2_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "032_supply_chain_research_selection_v2.py"
)

EVIDENCE_REVIEW_GATE_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend"
    / "alembic"
    / "versions"
    / "033_supply_chain_evidence_review_gate.py"
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


def test_supply_chain_evidence_pipeline_migration_defines_source_document_fact_tables():
    sql = EVIDENCE_PIPELINE_MIGRATION_PATH.read_text(encoding="utf-8")

    required_tables = [
        "evidence_source_catalog",
        "raw_evidence_documents",
        "evidence_extracted_facts",
        "business_tag_stage_transition_log",
        "business_tag_evidence_freshness",
        "business_tag_expectation_monitor",
    ]

    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    required_columns = [
        "source_level TEXT NOT NULL",
        "source_reliability_score DOUBLE PRECISION",
        "confidence_cap DOUBLE PRECISION",
        "requires_cross_validation BOOLEAN NOT NULL DEFAULT FALSE",
        "content_hash TEXT NOT NULL",
        "fact_nature TEXT NOT NULL",
        "validation_status TEXT NOT NULL DEFAULT 'pending'",
        "research_stage_signal TEXT",
        "commercial_stage_signal TEXT",
        "last_strong_evidence_date DATE",
        "freshness_status TEXT NOT NULL DEFAULT 'unknown'",
        "gap_status TEXT NOT NULL DEFAULT 'pending'",
    ]

    for column_contract in required_columns:
        assert column_contract in sql


def test_supply_chain_data_collection_center_migration_defines_job_and_specialized_tables():
    sql = DATA_COLLECTION_CENTER_MIGRATION_PATH.read_text(encoding="utf-8")

    required_tables = [
        "evidence_collection_jobs",
        "patent_events",
        "tender_award_events",
        "official_site_events",
        "industry_price_series",
    ]

    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql

    required_contracts = [
        "job_type TEXT NOT NULL",
        "scope_type TEXT NOT NULL",
        "status TEXT NOT NULL DEFAULT 'pending'",
        "duplicate_count INTEGER NOT NULL DEFAULT 0",
        "publication_number TEXT",
        "award_amount DOUBLE PRECISION",
        "event_type TEXT NOT NULL",
        "metric_name TEXT NOT NULL",
        "ALTER TABLE evidence_source_catalog ADD COLUMN IF NOT EXISTS base_url TEXT",
        "ALTER TABLE raw_evidence_documents ADD COLUMN IF NOT EXISTS doc_type TEXT",
    ]

    for contract in required_contracts:
        assert contract in sql


def test_business_tag_capex_evidence_migration_defines_structured_capex_table():
    sql = CAPEX_EVIDENCE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS business_tag_capex_evidence" in sql
    required_columns = [
        "capex_evidence_id TEXT PRIMARY KEY",
        "mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id)",
        "code TEXT NOT NULL",
        "fiscal_period TEXT NOT NULL",
        "capex_amount DOUBLE PRECISION",
        "capex_direction JSONB NOT NULL DEFAULT '[]'",
        "mapped_layer_id TEXT NOT NULL",
        "mapped_segments JSONB NOT NULL DEFAULT '[]'",
        "quote TEXT NOT NULL",
        "review_status TEXT NOT NULL DEFAULT 'pending_review'",
        "amount_is_total_capex BOOLEAN NOT NULL DEFAULT FALSE",
        "direction_is_ai_related BOOLEAN NOT NULL DEFAULT FALSE",
    ]
    for column_contract in required_columns:
        assert column_contract in sql

    required_indexes = [
        "idx_business_tag_capex_mapping",
        "idx_business_tag_capex_code",
        "idx_business_tag_capex_chain",
        "idx_business_tag_capex_review",
        "idx_business_tag_capex_asof",
    ]
    for index_name in required_indexes:
        assert index_name in sql


def test_selection_v2_migration_defines_research_and_selection_tables():
    sql = SELECTION_V2_MIGRATION_PATH.read_text(encoding="utf-8")
    required = [
        "supply_chain_node_dimensions",
        "supply_chain_transmission_edges",
        "supply_chain_technology_routes",
        "supply_chain_node_scores",
        "business_tag_authenticity_scores",
        "business_tag_operating_quality_scores",
        "business_tag_benefit_scores",
        "business_tag_selection_scores",
        "business_tag_pool_state",
        "business_tag_pool_transition_log",
    ]
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_selection_v2_migration_preserves_unknown_and_audit_contracts():
    sql = SELECTION_V2_MIGRATION_PATH.read_text(encoding="utf-8")
    required = [
        "score DOUBLE PRECISION",
        "coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0",
        "status IN ('known','estimated','proxy','unknown','contradicted')",
        "evidence_level IN ('E0','E1','E2','E3','E4','E5','E6')",
        "pool_code IN ('A','B','C','D')",
        "model_version TEXT NOT NULL",
        "veto_reasons JSONB NOT NULL DEFAULT '[]'",
        "trigger_evidence_ids JSONB NOT NULL DEFAULT '[]'",
        "review_status TEXT NOT NULL DEFAULT 'pending_review'",
        "uq_screening_snapshots_supply_chain_v2",
        "CREATE TABLE IF NOT EXISTS screening_models",
        "CREATE TABLE IF NOT EXISTS model_versions",
    ]
    for contract in required:
        assert contract in sql


def test_evidence_review_gate_migration_revision_and_audit_contract():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'revision: str = "033"' in migration_text
    assert "032" in migration_text
    assert "ADD COLUMN IF NOT EXISTS reviewer TEXT" in migration_text
    assert "guard_supply_chain_manual_review" in migration_text
    assert "business_tag_expectation_monitor" in migration_text
    assert "business_tag_stage_tracking" in migration_text
    assert "OR NULLIF(BTRIM(NEW.review_note), '') IS NULL" in migration_text
    assert "TIMESTAMP WITH TIME ZONE" in migration_text
    assert "AT TIME ZONE 'Asia/Shanghai'" in migration_text


def test_evidence_review_gate_demotes_unverifiable_historical_approvals():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "validation_status = 'pending'" in migration_text
    assert "review_status = 'pending_review'" in migration_text
    assert "coalesce(metadata, '{}'::jsonb) - 'review_normalization'" in migration_text


def test_evidence_review_gate_has_four_manual_review_triggers():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration_text.count("CREATE TRIGGER trg_supply_chain_manual_review_") == 4
    for table_name in (
        "evidence_extracted_facts",
        "business_tag_evidence_events",
        "business_tag_expectation_monitor",
        "business_tag_stage_tracking",
    ):
        assert f"BEFORE INSERT OR UPDATE ON {table_name}" in migration_text
    assert migration_text.count(
        "current_setting('app.supply_chain_review_action', true) "
        "IS DISTINCT FROM 'manual'"
    ) >= 3
    assert "OR NULLIF(BTRIM(NEW.reviewer), '') IS NULL" in migration_text
    assert "OR NULLIF(BTRIM(NEW.review_note), '') IS NULL" in migration_text
    assert "OR NEW.reviewed_at IS NULL" in migration_text
    assert "source_event_id" in migration_text


def test_evidence_review_gate_preserves_stage_event_mapping_invariant():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "event.mapping_id = stage.mapping_id" in migration_text
    assert "event.mapping_id = NEW.mapping_id" in migration_text
    assert "UPDATE business_tag_stage_tracking" in migration_text
    assert "source_event_id = OLD.event_id" in migration_text
    assert "NEW.review_status IS DISTINCT FROM 'approved'" in migration_text
    assert "NEW.mapping_id IS DISTINCT FROM OLD.mapping_id" in migration_text


def test_evidence_review_gate_preserves_fact_event_mapping_invariant():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "event.mapping_id IS NOT DISTINCT FROM fact.mapping_id" in migration_text
    assert "event.mapping_id IS NOT DISTINCT FROM NEW.mapping_id" in migration_text
    assert "UPDATE evidence_extracted_facts AS fact" in migration_text
    assert "fact.evidence_event_id = OLD.event_id" in migration_text
    assert "NEW.mapping_id IS DISTINCT FROM fact.mapping_id" in migration_text
    assert "metadata = coalesce(fact.metadata, '{}'::jsonb) - 'review_normalization'" in migration_text


def test_evidence_review_gate_demotes_confirmed_linked_fact_without_audited_matching_event():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")

    assert "fact.evidence_event_id IS NOT NULL" in migration_text
    assert "event.event_id = fact.evidence_event_id" in migration_text
    assert "event.review_status = 'approved'" in migration_text
    assert "NOT EXISTS" in migration_text


def test_evidence_review_gate_timezone_upgrade_and_non_reapproving_downgrade():
    migration_text = EVIDENCE_REVIEW_GATE_MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade_text, downgrade_text = migration_text.split("def downgrade()", maxsplit=1)

    assert upgrade_text.count("ADD COLUMN IF NOT EXISTS reviewer TEXT") >= 2
    assert upgrade_text.count("ADD COLUMN IF NOT EXISTS review_note TEXT") >= 2
    assert (
        upgrade_text.count(
            "ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE"
        )
        >= 2
    )
    assert "ALTER COLUMN reviewed_at TYPE TIMESTAMP WITH TIME ZONE" in upgrade_text
    assert "reviewed_at AT TIME ZONE 'Asia/Shanghai'" in downgrade_text
    assert "SET validation_status = 'confirmed'" not in downgrade_text
    assert "SET review_status = 'approved'" not in downgrade_text
