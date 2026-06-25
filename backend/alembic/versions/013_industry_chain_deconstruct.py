"""Industry chain deconstruct tables for multi-industry supply chain analysis.

PRD: docs/prd/supply-chain-reconstruct-2026-06-24.md

This migration creates the storage contract for the industry chain deconstruct feature:
- industry_themes: Inherit policy_themes, add category/key_directions/policy_intensity
- chain_nodes: Inherit supply_chain_bom_nodes, add layer/value_chain/competition
- company_chain_mapping: Inherit company_bom_mapping, add resonance/three_factors/trade_signal
- policy_interpretations: New table for LLM-based policy interpretation records
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    # 1. industry_themes: Inherit policy_themes with extensions
    op.execute("""
        CREATE TABLE IF NOT EXISTS industry_themes (
            theme_id VARCHAR(50) PRIMARY KEY,
            theme_name VARCHAR(100) NOT NULL,
            category VARCHAR(20),
            key_directions JSONB,
            policy_intensity_stars INT DEFAULT 3,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 2. chain_nodes: Inherit supply_chain_bom_nodes with extensions
    op.execute("""
        CREATE TABLE IF NOT EXISTS chain_nodes (
            node_id VARCHAR(100) PRIMARY KEY,
            theme_id VARCHAR(50) REFERENCES industry_themes(theme_id),
            node_name VARCHAR(100) NOT NULL,
            layer INT NOT NULL,
            parent_node_id VARCHAR(100) REFERENCES chain_nodes(node_id),
            upstream_nodes JSONB,
            downstream_nodes JSONB,
            value_chain JSONB,
            competition JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 3. company_chain_mapping: Inherit company_bom_mapping with extensions
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_chain_mapping (
            id SERIAL PRIMARY KEY,
            code VARCHAR(10) NOT NULL,
            node_id VARCHAR(100) REFERENCES chain_nodes(node_id),
            main_pct DECIMAL(5,2),
            policy_match_score DECIMAL(3,2),
            chokepoint_score INT,
            evidence JSONB,
            three_factors JSONB,
            trade_signal VARCHAR(20),
            valid_from DATE,
            valid_to DATE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # 4. policy_interpretations: New table for LLM-based policy interpretation
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_interpretations (
            id SERIAL PRIMARY KEY,
            source_type VARCHAR(20),
            source_content TEXT,
            source_url VARCHAR(500),
            interpreted_themes JSONB,
            model_used VARCHAR(50),
            tokens_used INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_chain_nodes_theme_chain ON chain_nodes(theme_id, layer)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_chain_mapping_resonance ON company_chain_mapping(chokepoint_score DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_chain_mapping_node ON company_chain_mapping(node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_chain_mapping_code ON company_chain_mapping(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_interpretations_created_at ON policy_interpretations(created_at)")


def downgrade():
    # Drop indexes in reverse order
    op.execute("DROP INDEX IF EXISTS idx_policy_interpretations_created_at")
    op.execute("DROP INDEX IF EXISTS idx_company_chain_mapping_code")
    op.execute("DROP INDEX IF EXISTS idx_company_chain_mapping_node")
    op.execute("DROP INDEX IF EXISTS idx_company_chain_mapping_resonance")
    op.execute("DROP INDEX IF EXISTS idx_chain_nodes_theme_chain")

    # Drop tables in reverse order of creation (respecting foreign key dependencies)
    op.execute("DROP TABLE IF EXISTS policy_interpretations")
    op.execute("DROP TABLE IF EXISTS company_chain_mapping")
    op.execute("DROP TABLE IF EXISTS chain_nodes")
    op.execute("DROP TABLE IF EXISTS industry_themes")