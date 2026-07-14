from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend" / "alembic" / "versions" / "034_ai_token_output_power.py"
)


def test_token_output_power_migration_defines_all_tables_and_guards():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    for table in [
        "business_tag_token_output_power_evidence",
        "business_tag_token_output_capacity_snapshots",
        "business_tag_token_dimension_scores",
        "business_tag_token_market_snapshots",
        "business_tag_token_pool_states",
        "business_tag_token_pool_transitions",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for contract in [
        "power_source_type IN ('unknown','curtailed_renewable','valley_power','park_self_generation_or_ppa','nominal_capacity')",
        "evidence_grade IN ('E0','E1','E2','E3','E4','E5')",
        "pool_code IN ('A','B','C','D')",
        "dimension_id IN ('function_value','technology_route','physical_bom','value_pool','competition_moat','supply_demand_cycle','evidence_validation')",
        "separate_from_industry_evidence BOOLEAN NOT NULL DEFAULT TRUE",
        "coverage_ratio DOUBLE PRECISION",
        "billable_tokens DOUBLE PRECISION",
        "cost_per_million_tokens DOUBLE PRECISION",
    ]:
        assert contract in sql


def test_token_output_power_migration_has_mapping_and_date_indexes():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    for index_name in [
        "idx_token_power_evidence_mapping_date",
        "idx_token_power_capacity_mapping_date",
        "idx_token_power_dimension_mapping_date",
        "idx_token_power_market_mapping_date",
        "idx_token_power_pool_mapping_date",
        "idx_token_power_transition_mapping_date",
    ]:
        assert index_name in sql
