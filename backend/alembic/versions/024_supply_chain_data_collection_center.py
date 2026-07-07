"""Add supply-chain data collection center tables.

Revision ID: 024
Revises: 023
Create Date: 2026-07-07
"""
from typing import Sequence, Union

from alembic import op


revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JOB_TYPE_CHECK = "job_type IN ('scheduled','manual','backfill','dry_run')"
JOB_STATUS_CHECK = "status IN ('pending','running','success','partial_success','failed','skipped')"
SOURCE_LEVEL_CHECK = "source_level IN ('strong','mid','weak')"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE evidence_source_catalog ADD COLUMN IF NOT EXISTS base_url TEXT
    """)
    op.execute("""
        ALTER TABLE evidence_source_catalog ADD COLUMN IF NOT EXISTS robots_policy TEXT
    """)
    op.execute("""
        ALTER TABLE evidence_source_catalog ADD COLUMN IF NOT EXISTS rate_limit_per_minute INTEGER
    """)
    op.execute("""
        ALTER TABLE raw_evidence_documents ADD COLUMN IF NOT EXISTS doc_type TEXT
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS evidence_collection_jobs (
            job_id TEXT PRIMARY KEY,
            source_id TEXT REFERENCES evidence_source_catalog(source_id),
            job_type TEXT NOT NULL CHECK ({JOB_TYPE_CHECK}),
            scope_type TEXT NOT NULL,
            scope_payload JSONB NOT NULL DEFAULT '{{}}',
            status TEXT NOT NULL DEFAULT 'pending' CHECK ({JOB_STATUS_CHECK}),
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            fetched_count INTEGER NOT NULL DEFAULT 0,
            inserted_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS patent_events (
            event_id TEXT PRIMARY KEY,
            doc_id TEXT REFERENCES raw_evidence_documents(doc_id),
            company_code TEXT,
            company_name TEXT,
            publication_number TEXT,
            application_number TEXT,
            patent_title TEXT NOT NULL,
            patent_abstract TEXT,
            applicant TEXT,
            ipc_class TEXT,
            application_date DATE,
            publication_date DATE,
            grant_date DATE,
            patent_status TEXT,
            related_mapping_id TEXT,
            moat_signal BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS tender_award_events (
            event_id TEXT PRIMARY KEY,
            doc_id TEXT REFERENCES raw_evidence_documents(doc_id),
            company_code TEXT,
            company_name TEXT,
            project_name TEXT NOT NULL,
            purchaser TEXT,
            supplier TEXT,
            award_amount DOUBLE PRECISION,
            currency TEXT,
            publish_date DATE,
            event_type TEXT NOT NULL,
            related_mapping_id TEXT,
            commercial_signal TEXT,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS official_site_events (
            event_id TEXT PRIMARY KEY,
            doc_id TEXT REFERENCES raw_evidence_documents(doc_id),
            company_code TEXT,
            company_name TEXT,
            source_level TEXT NOT NULL DEFAULT 'mid' CHECK ({SOURCE_LEVEL_CHECK}),
            event_type TEXT NOT NULL,
            title TEXT NOT NULL,
            event_date DATE,
            url TEXT,
            related_mapping_id TEXT,
            evidence_summary TEXT,
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS industry_price_series (
            series_id TEXT PRIMARY KEY,
            source_id TEXT REFERENCES evidence_source_catalog(source_id),
            chain_id TEXT,
            node_id TEXT,
            metric_name TEXT NOT NULL,
            metric_value DOUBLE PRECISION,
            unit TEXT,
            trade_date DATE NOT NULL,
            region TEXT,
            source_url TEXT,
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (source_id, chain_id, node_id, metric_name, trade_date, region)
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_collection_jobs_source_status ON evidence_collection_jobs(source_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_patent_events_company_date ON patent_events(company_code, publication_date DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tender_award_events_company_date ON tender_award_events(company_code, publish_date DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_official_site_events_company_date ON official_site_events(company_code, event_date DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_industry_price_series_chain_date ON industry_price_series(chain_id, trade_date DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_industry_price_series_chain_date")
    op.execute("DROP INDEX IF EXISTS idx_official_site_events_company_date")
    op.execute("DROP INDEX IF EXISTS idx_tender_award_events_company_date")
    op.execute("DROP INDEX IF EXISTS idx_patent_events_company_date")
    op.execute("DROP INDEX IF EXISTS idx_evidence_collection_jobs_source_status")

    op.execute("DROP TABLE IF EXISTS industry_price_series")
    op.execute("DROP TABLE IF EXISTS official_site_events")
    op.execute("DROP TABLE IF EXISTS tender_award_events")
    op.execute("DROP TABLE IF EXISTS patent_events")
    op.execute("DROP TABLE IF EXISTS evidence_collection_jobs")

    op.execute("ALTER TABLE raw_evidence_documents DROP COLUMN IF EXISTS doc_type")
    op.execute("ALTER TABLE evidence_source_catalog DROP COLUMN IF EXISTS rate_limit_per_minute")
    op.execute("ALTER TABLE evidence_source_catalog DROP COLUMN IF EXISTS robots_policy")
    op.execute("ALTER TABLE evidence_source_catalog DROP COLUMN IF EXISTS base_url")
