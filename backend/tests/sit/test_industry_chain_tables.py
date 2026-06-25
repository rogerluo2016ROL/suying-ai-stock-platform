"""SIT integration tests for Industry Chain Deconstruct tables.

Requires: Postgres running (docker-compose), DATABASE_URL set or default.
Run: pytest tests/sit/test_industry_chain_tables.py -v

AC verification:
- AC-1: alembic upgrade head creates 4 tables
- AC-2: tables contain inherited fields (chain_nodes has parent_node_id)
- AC-3: indexes created (idx_chain_nodes_theme_chain, idx_company_chain_mapping_resonance)
- AC-4: alembic downgrade -1 can rollback
- AC-5: pytest verifies table structure
"""

import os
import pytest

os.environ["DATABASE_TEST_NULLPOOL"] = "1"

from sqlalchemy import create_engine, text
from app.config import DATABASE_URL


@pytest.fixture(scope="module")
def db_engine():
    """Create sync engine for table structure verification."""
    # Convert async URL to sync for structure checks
    sync_url = DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url)
    yield engine


class TestIndustryChainTables:
    """AC-1, AC-5: Verify table structure after migration."""

    def test_industry_themes_table_exists(self, db_engine):
        """AC-1: industry_themes table exists with correct columns."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'industry_themes'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: (row[1], row[2]) for row in result}

        # Verify required columns
        assert "theme_id" in columns
        assert columns["theme_id"][0] == "character varying"
        assert columns["theme_id"][1] == "NO"  # PRIMARY KEY

        assert "theme_name" in columns
        assert columns["theme_name"][1] == "NO"  # NOT NULL

        assert "category" in columns
        assert "key_directions" in columns
        assert columns["key_directions"][0] == "jsonb"

        assert "policy_intensity_stars" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_chain_nodes_table_exists(self, db_engine):
        """AC-1, AC-2: chain_nodes table exists with inherited fields."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'chain_nodes'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: (row[1], row[2]) for row in result}

        # Verify required columns
        assert "node_id" in columns
        assert "theme_id" in columns  # FK to industry_themes
        assert "node_name" in columns
        assert "layer" in columns  # 1-5 layers
        assert "parent_node_id" in columns  # AC-2: inherited field
        assert "upstream_nodes" in columns
        assert "downstream_nodes" in columns
        assert "value_chain" in columns  # JSONB for margin/pricing_power/value_added
        assert "competition" in columns  # JSONB for concentration/leader_share/barrier/threat
        assert "created_at" in columns

        # Verify JSONB types
        assert columns["value_chain"][0] == "jsonb"
        assert columns["competition"][0] == "jsonb"

    def test_company_chain_mapping_table_exists(self, db_engine):
        """AC-1: company_chain_mapping table exists."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'company_chain_mapping'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: (row[1], row[2]) for row in result}

        # Verify required columns
        assert "id" in columns  # SERIAL PK
        assert "code" in columns
        assert "node_id" in columns  # FK to chain_nodes
        assert "main_pct" in columns
        assert "policy_match_score" in columns
        assert "chokepoint_score" in columns
        assert "evidence" in columns  # JSONB
        assert "three_factors" in columns  # JSONB
        assert "trade_signal" in columns
        assert "valid_from" in columns
        assert "valid_to" in columns
        assert "created_at" in columns

    def test_policy_interpretations_table_exists(self, db_engine):
        """AC-1: policy_interpretations table exists."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'policy_interpretations'
                ORDER BY ordinal_position
            """))
            columns = {row[0]: (row[1], row[2]) for row in result}

        # Verify required columns
        assert "id" in columns  # SERIAL PK
        assert "source_type" in columns
        assert "source_content" in columns
        assert "source_url" in columns
        assert "interpreted_themes" in columns  # JSONB
        assert "model_used" in columns
        assert "tokens_used" in columns
        assert "created_at" in columns

    def test_indexes_created(self, db_engine):
        """AC-3: Required indexes exist."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes
                WHERE tablename IN ('chain_nodes', 'company_chain_mapping', 'policy_interpretations')
            """))
            indexes = [row[0] for row in result]

        # Verify required indexes
        assert "idx_chain_nodes_theme_chain" in indexes
        assert "idx_company_chain_mapping_resonance" in indexes
        assert "idx_company_chain_mapping_node" in indexes
        assert "idx_company_chain_mapping_code" in indexes
        assert "idx_policy_interpretations_created_at" in indexes

    def test_foreign_key_constraints(self, db_engine):
        """Verify FK constraints exist for data integrity."""
        with db_engine.connect() as conn:
            result = conn.execute(text("""
                SELECT tc.table_name, tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_name IN ('chain_nodes', 'company_chain_mapping')
            """))
            fks = [(row[0], row[2], row[3]) for row in result]

        # Verify chain_nodes -> industry_themes FK
        assert ("chain_nodes", "theme_id", "industry_themes") in fks
        # Verify chain_nodes self-reference FK
        assert ("chain_nodes", "parent_node_id", "chain_nodes") in fks
        # Verify company_chain_mapping -> chain_nodes FK
        assert ("company_chain_mapping", "node_id", "chain_nodes") in fks