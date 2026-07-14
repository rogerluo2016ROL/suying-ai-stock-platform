from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend" / "alembic" / "versions" / "035_ai_token_commercial_output.py"
)


def test_migration_is_isolated_from_power_chain():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert 'revision: str = "035"' in sql
    assert 'down_revision: Union[str, None] = "034"' in sql
    for table in (
        "business_tag_token_commercial_evidence",
        "business_tag_token_commercial_scores",
        "business_tag_token_commercial_pool_states",
        "business_tag_token_commercial_pool_transitions",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for field in ("domestic_output_status", "overseas_output_status", "token_role"):
        assert field in sql
    assert "evidence_grade IN ('E0','E1','E2','E3','E4','E5')" in sql
    assert "DROP TABLE business_tag_token_output_power_evidence" not in sql


def test_migration_has_mapping_date_uniqueness_and_indexes():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "UNIQUE (mapping_id, as_of_date)" in sql
    assert "idx_token_commercial_evidence_mapping_date" in sql
    assert "idx_token_commercial_pool_mapping_date" in sql
