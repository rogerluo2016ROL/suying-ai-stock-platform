"""Gate supply-chain evidence approval behind an audited manual transaction.

Revision ID: 033
Revises: 032
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE evidence_extracted_facts
            ADD COLUMN IF NOT EXISTS reviewer TEXT,
            ADD COLUMN IF NOT EXISTS review_note TEXT,
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE business_tag_expectation_monitor
            ADD COLUMN IF NOT EXISTS reviewer TEXT,
            ADD COLUMN IF NOT EXISTS review_note TEXT,
            ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE business_tag_evidence_events
            ALTER COLUMN reviewed_at TYPE TIMESTAMP WITH TIME ZONE
            USING reviewed_at AT TIME ZONE 'Asia/Shanghai'
        """
    )

    # review_normalization is owned by a completed manual review.  Historical
    # collector metadata cannot establish that audit chain and is removed.
    op.execute(
        """
        UPDATE evidence_extracted_facts
        SET metadata = coalesce(metadata, '{}'::jsonb) - 'review_normalization'
        WHERE coalesce(metadata, '{}'::jsonb) ? 'review_normalization'
        """
    )
    op.execute(
        """
        UPDATE business_tag_expectation_monitor
        SET metadata = coalesce(metadata, '{}'::jsonb) - 'review_normalization'
        WHERE coalesce(metadata, '{}'::jsonb) ? 'review_normalization'
        """
    )

    # Preserve a confirmed fact only where its linked event already has a
    # complete, independently stored review trail.
    op.execute(
        """
        UPDATE evidence_extracted_facts AS fact
        SET reviewer = event.reviewer,
            review_note = event.review_note,
            reviewed_at = event.reviewed_at
        FROM business_tag_evidence_events AS event
        WHERE fact.evidence_event_id = event.event_id
          AND fact.validation_status = 'confirmed'
          AND event.review_status = 'approved'
          AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
          AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
          AND event.reviewed_at IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE evidence_extracted_facts
        SET validation_status = 'pending'
        WHERE validation_status = 'confirmed'
          AND (
              NULLIF(BTRIM(reviewer), '') IS NULL
              OR NULLIF(BTRIM(review_note), '') IS NULL
              OR reviewed_at IS NULL
          )
        """
    )
    op.execute(
        """
        UPDATE business_tag_evidence_events
        SET review_status = 'pending_review'
        WHERE review_status = 'approved'
          AND (
              NULLIF(BTRIM(reviewer), '') IS NULL
              OR NULLIF(BTRIM(review_note), '') IS NULL
              OR reviewed_at IS NULL
          )
        """
    )
    op.execute(
        """
        UPDATE business_tag_expectation_monitor
        SET review_status = 'pending_review'
        WHERE review_status = 'approved'
          AND (
              NULLIF(BTRIM(reviewer), '') IS NULL
              OR NULLIF(BTRIM(review_note), '') IS NULL
              OR reviewed_at IS NULL
          )
        """
    )
    op.execute(
        """
        UPDATE business_tag_stage_tracking AS stage
        SET review_status = 'pending_review'
        WHERE stage.review_status = 'approved'
          AND NOT EXISTS (
              SELECT 1
              FROM business_tag_evidence_events AS event
              WHERE event.event_id = stage.source_event_id
                AND event.mapping_id = stage.mapping_id
                AND event.review_status = 'approved'
                AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
                AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
                AND event.reviewed_at IS NOT NULL
          )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION guard_supply_chain_manual_review()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_TABLE_NAME = 'evidence_extracted_facts' THEN
                IF NEW.validation_status = 'confirmed' THEN
                    IF current_setting('app.supply_chain_review_action', true) IS DISTINCT FROM 'manual'
                       OR NULLIF(BTRIM(NEW.reviewer), '') IS NULL
                       OR NULLIF(BTRIM(NEW.review_note), '') IS NULL
                       OR NEW.reviewed_at IS NULL THEN
                        RAISE EXCEPTION
                            'confirmed supply-chain fact requires audited manual review';
                    END IF;
                END IF;
            ELSIF TG_TABLE_NAME IN (
                'business_tag_evidence_events',
                'business_tag_expectation_monitor'
            ) THEN
                IF TG_TABLE_NAME = 'business_tag_evidence_events'
                   AND TG_OP = 'UPDATE' THEN
                    IF OLD.review_status = 'approved'
                       AND (
                           NEW.review_status IS DISTINCT FROM 'approved'
                           OR NEW.mapping_id IS DISTINCT FROM OLD.mapping_id
                       ) THEN
                        UPDATE business_tag_stage_tracking
                        SET review_status = 'pending_review'
                        WHERE source_event_id = OLD.event_id
                          AND review_status = 'approved';
                    END IF;
                END IF;
                IF NEW.review_status = 'approved' THEN
                    IF current_setting('app.supply_chain_review_action', true) IS DISTINCT FROM 'manual'
                       OR NULLIF(BTRIM(NEW.reviewer), '') IS NULL
                       OR NULLIF(BTRIM(NEW.review_note), '') IS NULL
                       OR NEW.reviewed_at IS NULL THEN
                        RAISE EXCEPTION
                            'approved supply-chain evidence requires audited manual review';
                    END IF;
                END IF;
            ELSIF TG_TABLE_NAME = 'business_tag_stage_tracking' THEN
                IF NEW.review_status = 'approved' THEN
                    IF current_setting('app.supply_chain_review_action', true) IS DISTINCT FROM 'manual'
                       OR NEW.source_event_id IS NULL
                       OR NOT EXISTS (
                            SELECT 1
                            FROM business_tag_evidence_events AS event
                            WHERE event.event_id = NEW.source_event_id
                              AND event.mapping_id = NEW.mapping_id
                              AND event.review_status = 'approved'
                              AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
                              AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
                              AND event.reviewed_at IS NOT NULL
                       ) THEN
                        RAISE EXCEPTION
                            'approved supply-chain stage requires an audited source event';
                    END IF;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_chain_manual_review_fact "
        "ON evidence_extracted_facts"
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_chain_manual_review_fact
            BEFORE INSERT OR UPDATE ON evidence_extracted_facts
            FOR EACH ROW
            EXECUTE FUNCTION guard_supply_chain_manual_review()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_chain_manual_review_event "
        "ON business_tag_evidence_events"
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_chain_manual_review_event
            BEFORE INSERT OR UPDATE ON business_tag_evidence_events
            FOR EACH ROW
            EXECUTE FUNCTION guard_supply_chain_manual_review()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_chain_manual_review_expectation "
        "ON business_tag_expectation_monitor"
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_chain_manual_review_expectation
            BEFORE INSERT OR UPDATE ON business_tag_expectation_monitor
            FOR EACH ROW
            EXECUTE FUNCTION guard_supply_chain_manual_review()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_supply_chain_manual_review_stage "
        "ON business_tag_stage_tracking"
    )
    op.execute(
        """
        CREATE TRIGGER trg_supply_chain_manual_review_stage
            BEFORE INSERT OR UPDATE ON business_tag_stage_tracking
            FOR EACH ROW
            EXECUTE FUNCTION guard_supply_chain_manual_review()
        """
    )


def downgrade() -> None:
    for trigger_name, table_name in (
        ("trg_supply_chain_manual_review_stage", "business_tag_stage_tracking"),
        (
            "trg_supply_chain_manual_review_expectation",
            "business_tag_expectation_monitor",
        ),
        ("trg_supply_chain_manual_review_event", "business_tag_evidence_events"),
        ("trg_supply_chain_manual_review_fact", "evidence_extracted_facts"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_name}")
    op.execute("DROP FUNCTION IF EXISTS guard_supply_chain_manual_review()")

    op.execute(
        """
        ALTER TABLE business_tag_evidence_events
            ALTER COLUMN reviewed_at TYPE TIMESTAMP WITHOUT TIME ZONE
            USING reviewed_at AT TIME ZONE 'Asia/Shanghai'
        """
    )
    op.execute(
        """
        ALTER TABLE business_tag_expectation_monitor
            DROP COLUMN IF EXISTS reviewed_at,
            DROP COLUMN IF EXISTS review_note,
            DROP COLUMN IF EXISTS reviewer
        """
    )
    op.execute(
        """
        ALTER TABLE evidence_extracted_facts
            DROP COLUMN IF EXISTS reviewed_at,
            DROP COLUMN IF EXISTS review_note,
            DROP COLUMN IF EXISTS reviewer
        """
    )
