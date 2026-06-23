"""supply_chain BOM V4 policy graph, evidence, and score tables.

PRD: docs/prd/supply-chain-bom-2026-06-23.md

This migration creates the storage contract for the policy-driven BOM graph:
policy sources, policy themes, BOM nodes and edges, company mappings, evidence,
per-date scores, and manual overrides. It is intentionally additive.
"""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_sources (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            title TEXT NOT NULL,
            source_url TEXT,
            published_at DATE,
            content_hash TEXT,
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS policy_themes (
            theme_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            policy_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            keywords JSONB NOT NULL DEFAULT '[]',
            source_ids JSONB NOT NULL DEFAULT '[]'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_bom_nodes (
            node_id TEXT PRIMARY KEY,
            theme_id TEXT NOT NULL,
            chain_id TEXT NOT NULL,
            parent_node_id TEXT,
            level TEXT NOT NULL,
            name TEXT NOT NULL,
            node_type TEXT NOT NULL,
            keywords JSONB NOT NULL DEFAULT '[]',
            policy_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_bom_edges (
            edge_id TEXT PRIMARY KEY,
            from_node_id TEXT NOT NULL,
            to_node_id TEXT NOT NULL,
            relation TEXT NOT NULL DEFAULT 'upstream_downstream'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_bom_mapping (
            mapping_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            node_id TEXT NOT NULL,
            product_name TEXT,
            material_name TEXT,
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'pending_review',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS company_evidence (
            evidence_id TEXT PRIMARY KEY,
            code TEXT,
            node_id TEXT,
            source_id TEXT,
            evidence_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            excerpt TEXT,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            evidence_date DATE,
            status TEXT NOT NULL DEFAULT 'pending_review'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_scores (
            score_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            trade_date DATE NOT NULL,
            node_id TEXT,
            total_score DOUBLE PRECISION NOT NULL,
            rating TEXT NOT NULL,
            trade_signal TEXT NOT NULL,
            dimension_scores JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]'
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_overrides (
            override_id TEXT PRIMARY KEY,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}',
            operator TEXT NOT NULL DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_sources_published_at ON policy_sources(published_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bom_nodes_theme_chain ON supply_chain_bom_nodes(theme_id, chain_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_bom_mapping_code ON company_bom_mapping(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_bom_mapping_node ON company_bom_mapping(node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_evidence_code ON company_evidence(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_evidence_node ON company_evidence(node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_supply_chain_scores_code_date ON supply_chain_scores(code, trade_date)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_supply_chain_scores_code_date")
    op.execute("DROP INDEX IF EXISTS idx_company_evidence_node")
    op.execute("DROP INDEX IF EXISTS idx_company_evidence_code")
    op.execute("DROP INDEX IF EXISTS idx_company_bom_mapping_node")
    op.execute("DROP INDEX IF EXISTS idx_company_bom_mapping_code")
    op.execute("DROP INDEX IF EXISTS idx_bom_nodes_theme_chain")
    op.execute("DROP INDEX IF EXISTS idx_policy_sources_published_at")

    op.execute("DROP TABLE IF EXISTS manual_overrides")
    op.execute("DROP TABLE IF EXISTS supply_chain_scores")
    op.execute("DROP TABLE IF EXISTS company_evidence")
    op.execute("DROP TABLE IF EXISTS company_bom_mapping")
    op.execute("DROP TABLE IF EXISTS supply_chain_bom_edges")
    op.execute("DROP TABLE IF EXISTS supply_chain_bom_nodes")
    op.execute("DROP TABLE IF EXISTS policy_themes")
    op.execute("DROP TABLE IF EXISTS policy_sources")
