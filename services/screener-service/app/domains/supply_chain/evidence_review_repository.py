"""Transactional persistence boundary for supply-chain evidence review."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.domains.supply_chain.repository import connect


ReviewDecision = Literal["approved", "rejected", "needs_more_evidence"]

FACT_NORMALIZATION_FIELDS = frozenset({"evidence_delta_score", "risk_score"})
EXPECTATION_NORMALIZATION_FIELDS = frozenset(
    {"market_expectation_score", "catalyst_score", "claim_risk_penalty_score"}
)
_UNSET = object()


class ReviewNormalization(BaseModel):
    """Reviewer-owned score overrides stored with their audit context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    method_version: str = Field(min_length=1)
    as_of_date: date
    market_expectation_score: float | None = Field(default=None, ge=0, le=100)
    catalyst_score: float | None = Field(default=None, ge=0, le=100)
    evidence_delta_score: float | None = Field(default=None, ge=0, le=100)
    claim_risk_penalty_score: float | None = Field(default=None, ge=0, le=100)
    risk_score: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_score(self):
        values = self.model_dump(
            exclude={"method_version", "as_of_date"},
            exclude_none=True,
        )
        if not values:
            raise ValueError("normalization requires at least one score")
        if self.as_of_date > datetime.now(ZoneInfo("Asia/Shanghai")).date():
            raise ValueError("normalization as_of_date cannot be in the future")
        return self

    def score_fields(self) -> set[str]:
        return set(
            self.model_dump(
                exclude={"method_version", "as_of_date"},
                exclude_none=True,
            )
        )


class EvidenceFactMetadataPatch(BaseModel):
    """Allowlisted fact metadata that only a completed review may assert."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    application_domain: Literal[
        "dexterous_hand",
        "robot_hand",
        "robot_joint",
        "robot_wrist",
        "automotive",
    ] | None = None
    installation_position: str | None = Field(default=None, min_length=1)
    revenue_confirmed: StrictBool | None = None
    profit_confirmed: StrictBool | None = None
    legal_status: Literal["active", "granted"] | None = None
    legal_status_date: date | None = None

    @model_validator(mode="after")
    def require_field(self):
        if not self.model_dump(exclude_none=True, exclude_unset=True):
            raise ValueError("metadata patch requires at least one field")
        return self


class EvidenceReviewNotFound(LookupError):
    """The requested review target does not exist."""


def normalize_review_decision(decision: ReviewDecision) -> tuple[str, str]:
    if decision not in {"approved", "rejected", "needs_more_evidence"}:
        raise ValueError(f"unsupported review decision: {decision}")
    return {
        "approved": ("confirmed", "approved"),
        "rejected": ("rejected", "rejected"),
        "needs_more_evidence": ("pending", "pending_review"),
    }[decision]


def _validate_review_input(
    *,
    decision: ReviewDecision,
    reviewer: str,
    note: str,
    normalization: ReviewNormalization | None = None,
    allowed_normalization_fields: frozenset[str] | None = None,
    metadata_patch: EvidenceFactMetadataPatch | None = None,
) -> tuple[str, str]:
    normalize_review_decision(decision)
    clean_reviewer = str(reviewer or "").strip()
    clean_note = str(note or "").strip()
    if not clean_reviewer:
        raise ValueError("reviewer is required")
    if not clean_note:
        raise ValueError("review note is required")
    if normalization is not None:
        if decision != "approved":
            raise ValueError("normalization may only be written by an approved review")
        allowed = allowed_normalization_fields or frozenset()
        invalid = normalization.score_fields() - allowed
        if invalid:
            fields = ", ".join(sorted(invalid))
            raise ValueError(
                f"normalization fields are incompatible with target: {fields}"
            )
    if metadata_patch is not None and decision != "approved":
        raise ValueError("metadata patch may only be written by an approved review")
    return clean_reviewer, clean_note


def _json_payload(model: BaseModel | None) -> str | None:
    if model is None:
        return None
    return json.dumps(
        model.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
    )


def _metadata_patch_payload(patch: EvidenceFactMetadataPatch | None) -> str:
    values = (
        patch.model_dump(mode="json", exclude_none=True, exclude_unset=True)
        if patch
        else {}
    )
    return json.dumps(values, ensure_ascii=False)


class EvidenceReviewRepository:
    """Runs each review under one SAVEPOINT and one transaction marker."""

    def __init__(self, connection_factory: Callable[[], Any] = connect):
        self.connection_factory = connection_factory

    def _manual_transaction(self, operation, *, connection=None):
        owns_connection = connection is None
        active = connection or self.connection_factory()
        try:
            with active.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SAVEPOINT supply_chain_manual_review")
                cur.execute(
                    "SELECT current_setting('app.supply_chain_review_action', true) AS value"
                )
                previous_marker = str((cur.fetchone() or {}).get("value") or "")
                try:
                    cur.execute(
                        "SELECT set_config('app.supply_chain_review_action', 'manual', true)"
                    )
                    result = operation(cur)
                    cur.execute(
                        "SELECT set_config('app.supply_chain_review_action', %s, true)",
                        (previous_marker,),
                    )
                    cur.execute("RELEASE SAVEPOINT supply_chain_manual_review")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT supply_chain_manual_review")
                    cur.execute(
                        "SELECT set_config('app.supply_chain_review_action', %s, true)",
                        (previous_marker,),
                    )
                    cur.execute("RELEASE SAVEPOINT supply_chain_manual_review")
                    raise
            if owns_connection:
                active.commit()
            return result
        except Exception:
            if owns_connection:
                active.rollback()
            raise
        finally:
            if owns_connection:
                active.close()

    @staticmethod
    def _update_fact(
        cur,
        *,
        fact_id: str,
        fact_status: str,
        reviewer: str,
        note: str,
        normalization_payload: str | None,
        metadata_patch_payload: str,
    ) -> dict[str, Any]:
        cur.execute(
            """
            WITH locked AS (
                SELECT fact_id,
                       coalesce(metadata, '{}'::jsonb) - 'review_normalization'
                           AS clean_metadata
                FROM evidence_extracted_facts
                WHERE fact_id = %s
                FOR UPDATE
            ), prepared AS (
                SELECT fact_id, clean_metadata || %s::jsonb AS metadata
                FROM locked
            )
            UPDATE evidence_extracted_facts AS fact
            SET validation_status = %s,
                reviewer = %s,
                review_note = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                metadata = CASE
                    WHEN %s::jsonb IS NULL THEN prepared.metadata
                    ELSE jsonb_set(
                        prepared.metadata,
                        '{review_normalization}',
                        %s::jsonb || jsonb_build_object(
                            'reviewer', %s,
                            'reviewed_at', CURRENT_TIMESTAMP
                        ),
                        true
                    )
                END,
                updated_at = CURRENT_TIMESTAMP
            FROM prepared
            WHERE fact.fact_id = prepared.fact_id
            RETURNING fact.fact_id, fact.mapping_id, fact.company_code,
                      fact.evidence_event_id, fact.validation_status,
                      fact.metadata, fact.reviewer, fact.review_note,
                      fact.reviewed_at
            """,
            (
                fact_id,
                metadata_patch_payload,
                fact_status,
                reviewer,
                note,
                normalization_payload,
                normalization_payload,
                reviewer,
            ),
        )
        row = cur.fetchone()
        if not row:
            raise EvidenceReviewNotFound(f"evidence fact '{fact_id}' not found")
        return dict(row)

    @staticmethod
    def _get_fact_review_target(cur, *, fact_id: str) -> dict[str, Any]:
        cur.execute(
            """
            SELECT fact_id, mapping_id, evidence_event_id
            FROM evidence_extracted_facts
            WHERE fact_id = %s
            FOR UPDATE
            """,
            (fact_id,),
        )
        row = cur.fetchone()
        if not row:
            raise EvidenceReviewNotFound(f"evidence fact '{fact_id}' not found")
        return dict(row)

    @staticmethod
    def _update_event(
        cur,
        *,
        event_id: str,
        event_status: str,
        reviewer: str,
        note: str,
        confidence: float | None = None,
        stage_after: dict[str, str] | None = None,
        expected_mapping_id: Any = _UNSET,
    ) -> dict[str, Any]:
        stage_payload = (
            json.dumps(stage_after, ensure_ascii=False) if stage_after is not None else None
        )
        mapping_clause = ""
        mapping_params: tuple[Any, ...] = ()
        if expected_mapping_id is not _UNSET:
            mapping_clause = "AND event.mapping_id IS NOT DISTINCT FROM %s"
            mapping_params = (expected_mapping_id,)
        cur.execute(
            f"""
            UPDATE business_tag_evidence_events AS event
            SET review_status = %s,
                reviewer = %s,
                review_note = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                confidence = COALESCE(%s, confidence),
                stage_after = CASE
                    WHEN %s::jsonb IS NULL THEN stage_after
                    ELSE %s::jsonb
                END
            WHERE event.event_id = %s
              {mapping_clause}
            RETURNING event.event_id, event.mapping_id, event.code,
                      event.event_date, event.review_status, event.reviewer,
                      event.review_note, event.reviewed_at, event.stage_after
            """,
            (
                event_status,
                reviewer,
                note,
                confidence,
                stage_payload,
                stage_payload,
                event_id,
            ) + mapping_params,
        )
        row = cur.fetchone()
        if not row:
            if expected_mapping_id is not _UNSET:
                raise ValueError(
                    f"linked evidence event '{event_id}' mapping does not match fact mapping"
                )
            raise EvidenceReviewNotFound(f"evidence event '{event_id}' not found")
        return dict(row)

    @staticmethod
    def _demote_stages_for_event(cur, *, event_id: str) -> None:
        cur.execute(
            """
            UPDATE business_tag_stage_tracking
            SET review_status = 'pending_review'
            WHERE source_event_id = %s
              AND review_status = 'approved'
            """,
            (event_id,),
        )

    @staticmethod
    def _upsert_stage_from_review(
        cur,
        *,
        event_id: str,
        stage_after: dict[str, str],
        note: str,
    ) -> dict[str, Any]:
        research_stage = str(stage_after.get("research_stage") or "R0")
        commercialization_stage = str(
            stage_after.get("commercialization_stage") or "C0"
        )
        cur.execute(
            """
            INSERT INTO business_tag_stage_tracking (
                stage_id, mapping_id, trade_date, research_stage,
                commercialization_stage, stage_reason, source_event_id,
                last_stage_change_date, review_status
            )
            SELECT
                'review:' || event.event_id,
                event.mapping_id,
                COALESCE(
                    event.event_date,
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
                ),
                %s,
                %s,
                %s,
                event.event_id,
                COALESCE(
                    event.event_date,
                    (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date
                ),
                'approved'
            FROM business_tag_evidence_events AS event
            WHERE event.event_id = %s
            ON CONFLICT (stage_id) DO UPDATE SET
                mapping_id = EXCLUDED.mapping_id,
                trade_date = EXCLUDED.trade_date,
                research_stage = EXCLUDED.research_stage,
                commercialization_stage = EXCLUDED.commercialization_stage,
                stage_reason = EXCLUDED.stage_reason,
                source_event_id = EXCLUDED.source_event_id,
                last_stage_change_date = EXCLUDED.last_stage_change_date,
                review_status = EXCLUDED.review_status
            RETURNING stage_id, mapping_id, trade_date, research_stage,
                      commercialization_stage, stage_reason, source_event_id,
                      last_stage_change_date, review_status
            """,
            (research_stage, commercialization_stage, note, event_id),
        )
        row = cur.fetchone()
        if not row:
            raise EvidenceReviewNotFound(
                f"approved source event '{event_id}' not found for stage update"
            )
        return dict(row)

    @staticmethod
    def _normalization_result(
        row: dict[str, Any], *, allowed_fields: frozenset[str]
    ) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
        metadata = dict(row.get("metadata") or {})
        raw_stored = metadata.get("review_normalization")
        stored = dict(raw_stored) if isinstance(raw_stored, dict) else {}
        fields = tuple(
            sorted(
                key
                for key, value in stored.items()
                if key in allowed_fields and value is not None
            )
        )
        return metadata, stored, fields

    def review_fact(
        self,
        *,
        fact_id: str,
        decision: ReviewDecision,
        reviewer: str,
        note: str,
        stage_after: dict[str, str] | None,
        normalization: ReviewNormalization | None = None,
        metadata_patch: EvidenceFactMetadataPatch | None = None,
        connection=None,
    ) -> dict[str, Any]:
        reviewer, note = _validate_review_input(
            decision=decision,
            reviewer=reviewer,
            note=note,
            normalization=normalization,
            allowed_normalization_fields=FACT_NORMALIZATION_FIELDS,
            metadata_patch=metadata_patch,
        )
        fact_status, event_status = normalize_review_decision(decision)
        normalization_payload = _json_payload(normalization)
        patch_payload = _metadata_patch_payload(metadata_patch)

        def operation(cur):
            target = self._get_fact_review_target(cur, fact_id=fact_id)
            event_id = target.get("evidence_event_id")
            stage_record = None
            if event_id:
                self._update_event(
                    cur,
                    event_id=str(event_id),
                    event_status=event_status,
                    reviewer=reviewer,
                    note=note,
                    stage_after=stage_after,
                    expected_mapping_id=target.get("mapping_id"),
                )
                if event_status != "approved":
                    self._demote_stages_for_event(cur, event_id=str(event_id))
            fact = self._update_fact(
                cur,
                fact_id=fact_id,
                fact_status=fact_status,
                reviewer=reviewer,
                note=note,
                normalization_payload=normalization_payload,
                metadata_patch_payload=patch_payload,
            )
            if event_id:
                if decision == "approved" and stage_after:
                    stage_record = self._upsert_stage_from_review(
                        cur,
                        event_id=str(event_id),
                        stage_after=stage_after,
                        note=note,
                    )
            return fact, stage_record

        fact, stage_record = self._manual_transaction(operation, connection=connection)
        metadata, stored, fields = self._normalization_result(
            fact,
            allowed_fields=FACT_NORMALIZATION_FIELDS,
        )
        return {
            "fact_id": str(fact.get("fact_id") or fact_id),
            "mapping_id": fact.get("mapping_id"),
            "validation_status": fact.get("validation_status") or fact_status,
            "review_status": event_status,
            "reviewer": fact.get("reviewer"),
            "review_note": fact.get("review_note"),
            "reviewed_at": fact.get("reviewed_at"),
            "metadata": metadata,
            "normalization": stored,
            "normalization_fields": fields,
            "stage_record": stage_record,
        }

    def review_event(
        self,
        *,
        event_id: str,
        decision: ReviewDecision,
        reviewer: str,
        note: str,
        stage_after: dict[str, str] | None,
        confidence: float | None = None,
        connection=None,
    ) -> dict[str, Any]:
        reviewer, note = _validate_review_input(
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        _, event_status = normalize_review_decision(decision)

        def operation(cur):
            event = self._update_event(
                cur,
                event_id=event_id,
                event_status=event_status,
                reviewer=reviewer,
                note=note,
                confidence=confidence,
                stage_after=stage_after,
            )
            if event_status != "approved":
                self._demote_stages_for_event(cur, event_id=event_id)
            stage_record = None
            if decision == "approved" and stage_after:
                stage_record = self._upsert_stage_from_review(
                    cur,
                    event_id=event_id,
                    stage_after=stage_after,
                    note=note,
                )
            return event, stage_record

        event, stage_record = self._manual_transaction(
            operation,
            connection=connection,
        )
        return {
            "event_id": str(event.get("event_id") or event_id),
            "mapping_id": event.get("mapping_id"),
            "review_status": event.get("review_status") or event_status,
            "reviewer": event.get("reviewer"),
            "review_note": event.get("review_note"),
            "reviewed_at": event.get("reviewed_at"),
            "stage_after": dict(event.get("stage_after") or {}),
            "stage_record": stage_record,
        }

    @staticmethod
    def _update_expectation_monitor(
        cur,
        *,
        monitor_id: str,
        event_status: str,
        reviewer: str,
        note: str,
        normalization_payload: str | None,
        anchor_date: date | None,
    ) -> dict[str, Any]:
        cur.execute(
            """
            WITH review_anchor AS (
                SELECT COALESCE(%s::date, (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai')::date) AS anchor_date
            ), target AS (
                SELECT monitor.monitor_id, mapping.code, review_anchor.anchor_date,
                       coalesce(monitor.metadata, '{}'::jsonb)
                           - 'review_normalization' AS clean_metadata
                FROM business_tag_expectation_monitor AS monitor
                JOIN business_tag_mapping AS mapping
                  ON mapping.mapping_id = monitor.mapping_id
                CROSS JOIN review_anchor
                WHERE monitor.monitor_id = %s
                FOR UPDATE OF monitor
            ), anchored_daily AS (
                SELECT daily.code, daily.trade_date, daily.close,
                       ROW_NUMBER() OVER (ORDER BY daily.trade_date DESC) AS rn
                FROM target
                JOIN daily_kline AS daily
                  ON split_part(daily.code, '.', 1)
                   = split_part(target.code, '.', 1)
                WHERE daily.close IS NOT NULL
                  AND daily.trade_date <= target.anchor_date
            ), adjusted_prices AS (
                SELECT daily.trade_date, daily.rn,
                       daily.close * factor.adj_factor AS adjusted_close
                FROM anchored_daily AS daily
                LEFT JOIN adj_factor AS factor
                  ON factor.code = daily.code
                 AND factor.trade_date = daily.trade_date
                WHERE daily.rn <= 21
            ), adjusted_return_20d AS (
                SELECT CASE
                    WHEN COUNT(*) = 21 AND COUNT(adjusted_close) = 21 THEN
                        (
                            MAX(adjusted_close) FILTER (WHERE rn = 1)
                            / NULLIF(
                                MAX(adjusted_close) FILTER (WHERE rn = 21),
                                0
                            )
                            - 1
                        ) * 100
                    ELSE NULL
                END AS market_price_change
                FROM adjusted_prices
            )
            UPDATE business_tag_expectation_monitor AS monitor
            SET review_status = %s,
                reviewer = %s,
                review_note = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                market_price_change = CASE
                    WHEN %s = 'approved'
                        THEN adjusted_return_20d.market_price_change
                    ELSE monitor.market_price_change
                END,
                metadata = CASE
                    WHEN %s::jsonb IS NULL THEN target.clean_metadata
                    ELSE jsonb_set(
                        target.clean_metadata,
                        '{review_normalization}',
                        %s::jsonb || jsonb_build_object(
                            'reviewer', %s,
                            'reviewed_at', CURRENT_TIMESTAMP
                        ),
                        true
                    )
                END,
                updated_at = CURRENT_TIMESTAMP
            FROM target, adjusted_return_20d
            WHERE monitor.monitor_id = target.monitor_id
            RETURNING monitor.monitor_id, monitor.mapping_id,
                      monitor.review_status, monitor.market_price_change,
                      monitor.metadata, monitor.reviewer, monitor.review_note,
                      monitor.reviewed_at
            """,
            (
                anchor_date,
                monitor_id,
                event_status,
                reviewer,
                note,
                event_status,
                normalization_payload,
                normalization_payload,
                reviewer,
            ),
        )
        row = cur.fetchone()
        if not row:
            raise EvidenceReviewNotFound(
                f"expectation monitor '{monitor_id}' not found"
            )
        return dict(row)

    def review_expectation_monitor(
        self,
        *,
        monitor_id: str,
        decision: ReviewDecision,
        reviewer: str,
        note: str,
        normalization: ReviewNormalization | None = None,
        connection=None,
    ) -> dict[str, Any]:
        reviewer, note = _validate_review_input(
            decision=decision,
            reviewer=reviewer,
            note=note,
            normalization=normalization,
            allowed_normalization_fields=EXPECTATION_NORMALIZATION_FIELDS,
        )
        _, event_status = normalize_review_decision(decision)
        normalization_payload = _json_payload(normalization)
        anchor_date = normalization.as_of_date if normalization else None

        def operation(cur):
            return self._update_expectation_monitor(
                cur,
                monitor_id=monitor_id,
                event_status=event_status,
                reviewer=reviewer,
                note=note,
                normalization_payload=normalization_payload,
                anchor_date=anchor_date,
            )

        monitor = self._manual_transaction(operation, connection=connection)
        metadata, stored, fields = self._normalization_result(
            monitor,
            allowed_fields=EXPECTATION_NORMALIZATION_FIELDS,
        )
        return {
            "monitor_id": str(monitor.get("monitor_id") or monitor_id),
            "mapping_id": monitor.get("mapping_id"),
            "review_status": monitor.get("review_status") or event_status,
            "reviewer": monitor.get("reviewer"),
            "review_note": monitor.get("review_note"),
            "reviewed_at": monitor.get("reviewed_at"),
            "market_price_change": monitor.get("market_price_change"),
            "metadata": metadata,
            "normalization": stored,
            "normalization_fields": fields,
        }

    def list_queue(self, *, limit: int = 50, connection=None) -> dict[str, Any]:
        capped_limit = max(1, min(int(limit or 50), 200))
        owns_connection = connection is None
        active = connection or self.connection_factory()
        try:
            with active.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM evidence_extracted_facts
                         WHERE validation_status = 'pending') AS facts,
                        (SELECT COUNT(*) FROM business_tag_evidence_events
                         WHERE review_status IN ('candidate', 'pending_review')) AS events,
                        (SELECT COUNT(*) FROM business_tag_expectation_monitor
                         WHERE review_status IN ('candidate', 'pending_review')) AS expectations
                    """,
                )
                count_row = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    WITH review_queue AS (
                        SELECT 'fact' AS queue_type, fact_id AS id,
                               mapping_id, company_code AS code,
                               fact_type AS title, original_quote AS summary,
                               validation_status AS review_status, created_at
                        FROM evidence_extracted_facts
                        WHERE validation_status = 'pending'
                        UNION ALL
                        SELECT 'event' AS queue_type, event_id AS id,
                               mapping_id, code, title, excerpt AS summary,
                               review_status, created_at
                        FROM business_tag_evidence_events
                        WHERE review_status IN ('candidate', 'pending_review')
                        UNION ALL
                        SELECT 'expectation_monitor' AS queue_type,
                               monitor_id AS id, mapping_id, NULL::text AS code,
                               '预期差待验证'::text AS title,
                               claim_text AS summary, review_status, created_at
                        FROM business_tag_expectation_monitor
                        WHERE review_status IN ('candidate', 'pending_review')
                    )
                    SELECT queue_type, id, mapping_id, code, title, summary,
                           review_status, created_at
                    FROM review_queue
                    ORDER BY created_at ASC NULLS LAST, queue_type, id
                    LIMIT %s
                    """,
                    (capped_limit,),
                )
                queue = [dict(row) for row in cur.fetchall()]
        finally:
            if owns_connection:
                active.close()

        return {
            "version": "supply-chain-evidence-review-queue-v2",
            "queue": queue,
            "counts": {
                "facts": int(count_row.get("facts") or 0),
                "events": int(count_row.get("events") or 0),
                "expectations": int(count_row.get("expectations") or 0),
            },
        }
