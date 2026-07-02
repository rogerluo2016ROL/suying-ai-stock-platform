"""Supply-chain business tag tracking V2 tables.

PRD: docs/prd/supply-chain-business-tag-tracking-2026-07-02.md
Plan: docs/prd/supply-chain-data-support-implementation-plan-2026-07-02.md

This migration adds the storage contract for the V2 implementation:
L1-L8 hierarchy, business segment attribution, company-business-tag mappings,
evidence events, stage tracking, three-high scores, and expectation-gap scores.
It is additive and keeps the existing BOM V4 / chain deconstruct tables intact.
"""
from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


LAYER_CHECK = "layer_level IN ('L1','L2','L3','L4','L5','L6','L7','L8')"
VIEW_CHECK = "view_type IN ('bom','upstream_downstream','value_chain','competition')"
STATUS_CHECK = "status IN ('candidate','pending_review','weak_evidence','verified','rejected')"
REVIEW_STATUS_CHECK = "review_status IN ('candidate','pending_review','approved','rejected')"


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS supply_chain_hierarchy_nodes (
            node_id TEXT PRIMARY KEY,
            parent_node_id TEXT REFERENCES supply_chain_hierarchy_nodes(node_id),
            layer_level TEXT NOT NULL CHECK ({LAYER_CHECK}),
            layer_name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            policy_theme_id TEXT,
            chain_id TEXT,
            bom_node_id TEXT,
            source_table TEXT,
            source_id TEXT,
            keywords JSONB NOT NULL DEFAULT '[]',
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS supply_chain_deconstruct_views (
            view_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            view_type TEXT NOT NULL CHECK ({VIEW_CHECK}),
            payload JSONB NOT NULL DEFAULT '{{}}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (node_id, view_type)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS company_business_segments (
            segment_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            segment_name TEXT NOT NULL,
            report_period DATE,
            revenue DOUBLE PRECISION,
            revenue_ratio DOUBLE PRECISION,
            gross_profit DOUBLE PRECISION,
            gross_margin DOUBLE PRECISION,
            source_table TEXT,
            source_row_id TEXT,
            evidence_status TEXT NOT NULL DEFAULT 'pending_review',
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_mapping (
            mapping_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            business_segment_id TEXT REFERENCES company_business_segments(segment_id),
            node_id TEXT,
            theme_id TEXT,
            chain_id TEXT,
            tag_name TEXT NOT NULL,
            l1_l8_path JSONB NOT NULL DEFAULT '[]',
            revenue_ratio DOUBLE PRECISION,
            gross_profit_ratio DOUBLE PRECISION,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'pending_review' CHECK ({STATUS_CHECK}),
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_evidence_events (
            event_id TEXT PRIMARY KEY,
            mapping_id TEXT REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            node_id TEXT,
            event_date DATE,
            source_type TEXT NOT NULL,
            source_id TEXT,
            title TEXT,
            excerpt TEXT,
            original_url TEXT,
            evidence_type TEXT NOT NULL,
            impact_dimensions JSONB NOT NULL DEFAULT '[]',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK ({REVIEW_STATUS_CHECK}),
            reviewer TEXT,
            review_note TEXT,
            reviewed_at TIMESTAMP,
            stage_before JSONB NOT NULL DEFAULT '{{}}',
            stage_after JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_stage_tracking (
            stage_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            research_stage TEXT NOT NULL DEFAULT 'R0',
            commercialization_stage TEXT NOT NULL DEFAULT 'C0',
            stage_reason TEXT,
            source_event_id TEXT REFERENCES business_tag_evidence_events(event_id),
            last_stage_change_date DATE,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_three_high_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            growth_score DOUBLE PRECISION,
            profit_score DOUBLE PRECISION,
            moat_score DOUBLE PRECISION,
            stage_score DOUBLE PRECISION,
            evidence_score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_expectation_gap_scores (
            gap_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            actual_progress_score DOUBLE PRECISION,
            market_expectation_score DOUBLE PRECISION,
            evidence_delta_score DOUBLE PRECISION,
            risk_penalty_score DOUBLE PRECISION,
            expectation_gap_score DOUBLE PRECISION,
            gap_type TEXT,
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date)
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_supply_chain_hierarchy_layer ON supply_chain_hierarchy_nodes(layer_level)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_supply_chain_hierarchy_parent ON supply_chain_hierarchy_nodes(parent_node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_supply_chain_deconstruct_node_type ON supply_chain_deconstruct_views(node_id, view_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_company_business_segments_code ON company_business_segments(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_mapping_code ON business_tag_mapping(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_mapping_node ON business_tag_mapping(node_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_mapping_status ON business_tag_mapping(status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_evidence_code_date ON business_tag_evidence_events(code, event_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_evidence_mapping ON business_tag_evidence_events(mapping_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_stage_mapping_date ON business_tag_stage_tracking(mapping_id, trade_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_three_high_total ON business_tag_three_high_scores(trade_date, total_score DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_expectation_gap ON business_tag_expectation_gap_scores(trade_date, expectation_gap_score DESC NULLS LAST)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_business_tag_expectation_gap")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_three_high_total")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_stage_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_evidence_mapping")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_evidence_code_date")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_mapping_status")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_mapping_node")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_mapping_code")
    op.execute("DROP INDEX IF EXISTS idx_company_business_segments_code")
    op.execute("DROP INDEX IF EXISTS idx_supply_chain_deconstruct_node_type")
    op.execute("DROP INDEX IF EXISTS idx_supply_chain_hierarchy_parent")
    op.execute("DROP INDEX IF EXISTS idx_supply_chain_hierarchy_layer")

    op.execute("DROP TABLE IF EXISTS business_tag_expectation_gap_scores")
    op.execute("DROP TABLE IF EXISTS business_tag_three_high_scores")
    op.execute("DROP TABLE IF EXISTS business_tag_stage_tracking")
    op.execute("DROP TABLE IF EXISTS business_tag_evidence_events")
    op.execute("DROP TABLE IF EXISTS business_tag_mapping")
    op.execute("DROP TABLE IF EXISTS company_business_segments")
    op.execute("DROP TABLE IF EXISTS supply_chain_deconstruct_views")
    op.execute("DROP TABLE IF EXISTS supply_chain_hierarchy_nodes")
