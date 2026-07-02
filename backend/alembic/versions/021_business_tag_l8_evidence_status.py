"""Add per-dimension L8 evidence status table.

Revision ID: 021
Revises: 020
Create Date: 2026-07-02
"""
from alembic import op


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


SOURCE_STATUS_CHECK = "source_status IN ('matched','missing','inferred','rejected')"


def upgrade():
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_l8_evidence_status (
            status_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            node_id TEXT,
            dimension_id TEXT NOT NULL,
            dimension_name TEXT NOT NULL,
            source_status TEXT NOT NULL DEFAULT 'missing' CHECK ({SOURCE_STATUS_CHECK}),
            evidence_event_ids JSONB NOT NULL DEFAULT '[]',
            evidence_count INTEGER NOT NULL DEFAULT 0,
            evidence_summary TEXT,
            required_keywords JSONB NOT NULL DEFAULT '[]',
            updated_at DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, dimension_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_l8_status_mapping ON business_tag_l8_evidence_status(mapping_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_l8_status_dimension ON business_tag_l8_evidence_status(dimension_id, source_status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_l8_status_code ON business_tag_l8_evidence_status(code)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_business_tag_l8_status_code")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_l8_status_dimension")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_l8_status_mapping")
    op.execute("DROP TABLE IF EXISTS business_tag_l8_evidence_status")
