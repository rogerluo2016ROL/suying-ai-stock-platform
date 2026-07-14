"""Add isolated evidence and pool tables for AI Token commercial output."""

from typing import Sequence, Union

from alembic import op


revision: str = "035"
down_revision: Union[str, None] = "034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_commercial_evidence (
            evidence_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            chain_id TEXT NOT NULL DEFAULT 'ai_token_output',
            layer_id TEXT NOT NULL CHECK (layer_id IN ('L1','L2','L3','L4','L5','L6','L7','L8')),
            token_role TEXT NOT NULL,
            domestic_output_status TEXT NOT NULL DEFAULT 'unknown',
            overseas_output_status TEXT NOT NULL DEFAULT 'unknown',
            token_metric_type TEXT,
            token_volume DOUBLE PRECISION,
            token_price DOUBLE PRECISION,
            customer_status TEXT NOT NULL DEFAULT 'unknown',
            delivery_status TEXT NOT NULL DEFAULT 'unknown',
            revenue_status TEXT NOT NULL DEFAULT 'unknown',
            product_verified BOOLEAN NOT NULL DEFAULT FALSE,
            verified_supply BOOLEAN NOT NULL DEFAULT FALSE,
            verified_order BOOLEAN NOT NULL DEFAULT FALSE,
            verified_project BOOLEAN NOT NULL DEFAULT FALSE,
            customer_usage_verified BOOLEAN NOT NULL DEFAULT FALSE,
            runtime_verified BOOLEAN NOT NULL DEFAULT FALSE,
            recurring_delivery_verified BOOLEAN NOT NULL DEFAULT FALSE,
            token_revenue_verified BOOLEAN NOT NULL DEFAULT FALSE,
            continuous_cashflow_verified BOOLEAN NOT NULL DEFAULT FALSE,
            evidence_grade TEXT NOT NULL DEFAULT 'E0' CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
            review_status TEXT NOT NULL DEFAULT 'candidate' CHECK (review_status IN ('candidate','pending_review','approved','rejected','disabled')),
            source_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_id TEXT,
            source_url TEXT,
            quote TEXT,
            missing_fields JSONB NOT NULL DEFAULT '[]',
            next_validation_node TEXT,
            metadata JSONB NOT NULL DEFAULT '{}',
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, as_of_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_commercial_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            business_authenticity DOUBLE PRECISION,
            token_value_capture DOUBLE PRECISION,
            technology_inference_efficiency DOUBLE PRECISION,
            customer_commercialization DOUBLE PRECISION,
            competition_moat DOUBLE PRECISION,
            growth_realization DOUBLE PRECISION,
            evidence_quality DOUBLE PRECISION,
            weighted_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
            formal_ranking_eligible BOOLEAN NOT NULL DEFAULT FALSE,
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            score_detail JSONB NOT NULL DEFAULT '{}',
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, as_of_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_commercial_pool_states (
            pool_state_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            layer_id TEXT NOT NULL,
            evidence_grade TEXT NOT NULL CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
            pool_code TEXT CHECK (pool_code IN ('A','B','C','D')),
            industry_score DOUBLE PRECISION,
            market_signal_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
            reason_codes JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'candidate',
            next_validation_node TEXT,
            as_of_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, as_of_date)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_token_commercial_pool_transitions (
            transition_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            old_pool_code TEXT CHECK (old_pool_code IN ('A','B','C','D')),
            new_pool_code TEXT CHECK (new_pool_code IN ('A','B','C','D')),
            old_evidence_grade TEXT,
            new_evidence_grade TEXT,
            trigger_evidence_ids JSONB NOT NULL DEFAULT '[]',
            reason_codes JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            transition_date DATE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_token_commercial_evidence_mapping_date ON business_tag_token_commercial_evidence(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_commercial_evidence_code_layer ON business_tag_token_commercial_evidence(code, layer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_commercial_score_mapping_date ON business_tag_token_commercial_scores(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_commercial_pool_mapping_date ON business_tag_token_commercial_pool_states(mapping_id, as_of_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_token_commercial_pool_code_date ON business_tag_token_commercial_pool_states(pool_code, as_of_date DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_token_commercial_pool_code_date")
    op.execute("DROP INDEX IF EXISTS idx_token_commercial_pool_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_commercial_score_mapping_date")
    op.execute("DROP INDEX IF EXISTS idx_token_commercial_evidence_code_layer")
    op.execute("DROP INDEX IF EXISTS idx_token_commercial_evidence_mapping_date")
    op.execute("DROP TABLE IF EXISTS business_tag_token_commercial_pool_transitions")
    op.execute("DROP TABLE IF EXISTS business_tag_token_commercial_pool_states")
    op.execute("DROP TABLE IF EXISTS business_tag_token_commercial_scores")
    op.execute("DROP TABLE IF EXISTS business_tag_token_commercial_evidence")
