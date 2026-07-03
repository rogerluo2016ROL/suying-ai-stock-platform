"""Add supply-chain evidence pipeline tables.

Revision ID: 023
Revises: 022
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op


revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_LEVEL_CHECK = "source_level IN ('strong','mid','weak')"
FACT_NATURE_CHECK = (
    "fact_nature IN ('confirmed_fact','company_claim','analyst_estimate',"
    "'media_report','market_signal','rumor_signal')"
)
VALIDATION_STATUS_CHECK = "validation_status IN ('confirmed','pending','contradicted','expired','rejected')"
FRESHNESS_STATUS_CHECK = "freshness_status IN ('fresh','stale','expired','unknown')"
GAP_STATUS_CHECK = "gap_status IN ('pending','fulfilled','partially_fulfilled','missed','contradicted')"
REVIEW_STATUS_CHECK = "review_status IN ('candidate','pending_review','approved','rejected')"


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS evidence_source_catalog (
            source_id TEXT PRIMARY KEY,
            source_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_level TEXT NOT NULL CHECK ({SOURCE_LEVEL_CHECK}),
            source_reliability_score DOUBLE PRECISION,
            confidence_cap DOUBLE PRECISION,
            is_official BOOLEAN NOT NULL DEFAULT FALSE,
            is_third_party_estimate BOOLEAN NOT NULL DEFAULT FALSE,
            is_market_sentiment BOOLEAN NOT NULL DEFAULT FALSE,
            requires_cross_validation BOOLEAN NOT NULL DEFAULT FALSE,
            license_status TEXT NOT NULL DEFAULT 'unknown',
            update_frequency TEXT,
            crawl_method TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS raw_evidence_documents (
            doc_id TEXT PRIMARY KEY,
            source_id TEXT REFERENCES evidence_source_catalog(source_id),
            source_type TEXT NOT NULL,
            source_level TEXT NOT NULL CHECK ({SOURCE_LEVEL_CHECK}),
            company_code TEXT,
            company_name TEXT,
            title TEXT NOT NULL,
            publish_time TIMESTAMP,
            crawl_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            url TEXT,
            content_text TEXT,
            content_hash TEXT NOT NULL,
            doc_status TEXT NOT NULL DEFAULT 'active',
            license_status TEXT NOT NULL DEFAULT 'unknown',
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (content_hash)
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS evidence_extracted_facts (
            fact_id TEXT PRIMARY KEY,
            doc_id TEXT REFERENCES raw_evidence_documents(doc_id),
            mapping_id TEXT REFERENCES business_tag_mapping(mapping_id),
            company_code TEXT NOT NULL,
            chain_id TEXT,
            l5_tag TEXT,
            l6_route TEXT,
            business_segment TEXT,
            fact_type TEXT NOT NULL,
            fact_nature TEXT NOT NULL CHECK ({FACT_NATURE_CHECK}),
            fact_value TEXT,
            original_quote TEXT NOT NULL,
            source_level TEXT NOT NULL CHECK ({SOURCE_LEVEL_CHECK}),
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
            confidence_cap DOUBLE PRECISION,
            research_stage_signal TEXT,
            commercial_stage_signal TEXT,
            growth_signal BOOLEAN NOT NULL DEFAULT FALSE,
            profit_signal BOOLEAN NOT NULL DEFAULT FALSE,
            moat_signal BOOLEAN NOT NULL DEFAULT FALSE,
            risk_signal BOOLEAN NOT NULL DEFAULT FALSE,
            validation_status TEXT NOT NULL DEFAULT 'pending' CHECK ({VALIDATION_STATUS_CHECK}),
            evidence_event_id TEXT REFERENCES business_tag_evidence_events(event_id),
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_stage_transition_log (
            transition_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            old_research_stage TEXT,
            new_research_stage TEXT,
            old_commercial_stage TEXT,
            new_commercial_stage TEXT,
            trigger_fact_id TEXT REFERENCES evidence_extracted_facts(fact_id),
            trigger_event_id TEXT REFERENCES business_tag_evidence_events(event_id),
            change_reason TEXT,
            review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK ({REVIEW_STATUS_CHECK}),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_evidence_freshness (
            mapping_id TEXT PRIMARY KEY REFERENCES business_tag_mapping(mapping_id),
            last_strong_evidence_date DATE,
            last_mid_evidence_date DATE,
            last_weak_signal_date DATE,
            last_any_evidence_date DATE,
            days_since_update INTEGER,
            freshness_status TEXT NOT NULL DEFAULT 'unknown' CHECK ({FRESHNESS_STATUS_CHECK}),
            next_review_date DATE,
            stale_reason TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS business_tag_expectation_monitor (
            monitor_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            claim_text TEXT NOT NULL,
            claim_date DATE,
            claim_source_type TEXT,
            expected_result TEXT,
            expected_date DATE,
            actual_progress TEXT,
            gap_status TEXT NOT NULL DEFAULT 'pending' CHECK ({GAP_STATUS_CHECK}),
            market_price_change DOUBLE PRECISION,
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            source_doc_id TEXT REFERENCES raw_evidence_documents(doc_id),
            review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK ({REVIEW_STATUS_CHECK}),
            metadata JSONB NOT NULL DEFAULT '{{}}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_source_catalog_level ON evidence_source_catalog(source_level, enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_evidence_documents_company ON raw_evidence_documents(company_code, publish_time DESC NULLS LAST)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_raw_evidence_documents_source ON raw_evidence_documents(source_id, crawl_time DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_extracted_facts_mapping ON evidence_extracted_facts(mapping_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_extracted_facts_company ON evidence_extracted_facts(company_code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_extracted_facts_l5 ON evidence_extracted_facts(l5_tag)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_evidence_extracted_facts_status ON evidence_extracted_facts(validation_status, source_level)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_stage_transition_mapping ON business_tag_stage_transition_log(mapping_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_evidence_freshness_status ON business_tag_evidence_freshness(freshness_status, next_review_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_business_tag_expectation_monitor_mapping ON business_tag_expectation_monitor(mapping_id, gap_status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_business_tag_expectation_monitor_mapping")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_evidence_freshness_status")
    op.execute("DROP INDEX IF EXISTS idx_business_tag_stage_transition_mapping")
    op.execute("DROP INDEX IF EXISTS idx_evidence_extracted_facts_status")
    op.execute("DROP INDEX IF EXISTS idx_evidence_extracted_facts_l5")
    op.execute("DROP INDEX IF EXISTS idx_evidence_extracted_facts_company")
    op.execute("DROP INDEX IF EXISTS idx_evidence_extracted_facts_mapping")
    op.execute("DROP INDEX IF EXISTS idx_raw_evidence_documents_source")
    op.execute("DROP INDEX IF EXISTS idx_raw_evidence_documents_company")
    op.execute("DROP INDEX IF EXISTS idx_evidence_source_catalog_level")

    op.execute("DROP TABLE IF EXISTS business_tag_expectation_monitor")
    op.execute("DROP TABLE IF EXISTS business_tag_evidence_freshness")
    op.execute("DROP TABLE IF EXISTS business_tag_stage_transition_log")
    op.execute("DROP TABLE IF EXISTS evidence_extracted_facts")
    op.execute("DROP TABLE IF EXISTS raw_evidence_documents")
    op.execute("DROP TABLE IF EXISTS evidence_source_catalog")
