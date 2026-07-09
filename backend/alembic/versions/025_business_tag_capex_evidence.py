"""Add mapped-company CAPEX evidence table.

Revision ID: 025
Revises: 024
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op


revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_LEVEL_CHECK = "source_level IN ('strong','mid','weak')"
EVIDENCE_LEVEL_CHECK = "evidence_level IN ('reported','directional','estimated','manual_judgement')"
REVIEW_STATUS_CHECK = "review_status IN ('pending_review','approved','rejected')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_capex_evidence (
            capex_evidence_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            company_name TEXT,
            chain_id TEXT,
            node_id TEXT,
            fiscal_period TEXT NOT NULL,
            report_date DATE,
            as_of_date DATE NOT NULL,
            capex_amount DOUBLE PRECISION,
            capex_amount_unit TEXT,
            currency TEXT,
            capex_direction JSONB NOT NULL DEFAULT '[]',
            mapped_layer_id TEXT NOT NULL,
            mapped_segments JSONB NOT NULL DEFAULT '[]',
            source_id TEXT,
            source_type TEXT NOT NULL,
            source_level TEXT NOT NULL DEFAULT 'mid' CHECK ({SOURCE_LEVEL_CHECK}),
            source_name TEXT NOT NULL,
            source_url TEXT,
            quote TEXT NOT NULL,
            evidence_level TEXT NOT NULL DEFAULT 'directional' CHECK ({EVIDENCE_LEVEL_CHECK}),
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK ({REVIEW_STATUS_CHECK}),
            amount_is_total_capex BOOLEAN NOT NULL DEFAULT FALSE,
            amount_is_segment_capex BOOLEAN NOT NULL DEFAULT FALSE,
            direction_is_ai_related BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_capex_mapping ON business_tag_capex_evidence(mapping_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_capex_code ON business_tag_capex_evidence(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_capex_chain ON business_tag_capex_evidence(chain_id, mapped_layer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_capex_review ON business_tag_capex_evidence(review_status, source_level)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_capex_asof ON business_tag_capex_evidence(as_of_date DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_business_tag_capex_asof")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_capex_review")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_capex_chain")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_capex_code")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_capex_mapping")
    op.execute("DROP TABLE IF EXISTS business_tag_capex_evidence")
