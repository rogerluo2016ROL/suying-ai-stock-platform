"""PostgreSQL boundary for supply-chain selection V2."""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from psycopg2.extras import Json, RealDictCursor

from kronos_factors.scorer.supply_chain_selection_v2 import (
    ApprovedScoreInput,
    ExpectationGapInputs,
    aggregate_catalyst_score,
    aggregate_risk_score,
    calculate_actual_progress_score,
    calculate_approved_expectation_gap,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


class MissingSelectionTables(RuntimeError):
    def __init__(self, tables: list[str]):
        self.tables = list(tables)
        super().__init__("missing selection V2 tables: " + ", ".join(self.tables))


class SelectionRepository:
    REQUIRED_TABLES = (
        "business_tag_mapping",
        "business_tag_evidence_events",
        "evidence_extracted_facts",
        "raw_evidence_documents",
        "evidence_source_catalog",
        "business_tag_stage_tracking",
        "business_tag_evidence_freshness",
        "business_tag_expectation_monitor",
        "daily_kline",
        "adj_factor",
        "supply_chain_node_scores",
        "business_tag_authenticity_scores",
        "business_tag_operating_quality_scores",
        "business_tag_benefit_scores",
        "business_tag_selection_scores",
        "business_tag_pool_state",
        "business_tag_pool_transition_log",
    )

    def __init__(self, connection_factory: Callable[[], Any]):
        self.connection_factory = connection_factory

    def preflight(self, cur) -> list[str]:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            """,
            (list(self.REQUIRED_TABLES),),
        )
        present = {
            str(row["table_name"] if isinstance(row, dict) else row[0])
            for row in cur.fetchall()
        }
        return [table for table in self.REQUIRED_TABLES if table not in present]

    def fetch_asof_evidence(
        self,
        cur,
        mapping_id: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        publish_cutoff = cutoff.astimezone(SHANGHAI).replace(tzinfo=None)
        audit_cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
        cur.execute(
            """
            SELECT
                f.fact_id,
                f.evidence_event_id AS event_id,
                coalesce(d.publish_time, e.event_date::timestamp) AS publish_time,
                f.fact_type,
                f.fact_nature,
                f.validation_status,
                f.source_level,
                f.confidence,
                f.metadata,
                f.reviewer,
                f.review_note,
                f.reviewed_at,
                f.created_at
            FROM evidence_extracted_facts f
            LEFT JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
            LEFT JOIN business_tag_evidence_events e
              ON e.event_id = f.evidence_event_id
            WHERE f.mapping_id = %s
              AND coalesce(d.publish_time, e.event_date::timestamp) <= %s
              AND f.validation_status = 'confirmed'
              AND f.reviewer IS NOT NULL
              AND NULLIF(BTRIM(f.reviewer), '') IS NOT NULL
              AND f.review_note IS NOT NULL
              AND NULLIF(BTRIM(f.review_note), '') IS NOT NULL
              AND f.reviewed_at IS NOT NULL
              AND f.reviewed_at <= %s
              AND f.created_at IS NOT NULL
              AND f.created_at <= %s
            ORDER BY publish_time, event_id
            """,
            (mapping_id, publish_cutoff, cutoff, audit_cutoff),
        )
        facts = [dict(row) for row in cur.fetchall()]

        cur.execute(
            """
            SELECT
                e.event_id,
                e.event_date::timestamp AS publish_time,
                e.evidence_type AS fact_type,
                'confirmed_fact' AS fact_nature,
                'confirmed' AS validation_status,
                CASE
                    WHEN e.source_type IN ('annual_report','financial_report','announcement','exchange_filing')
                    THEN 'strong'
                    ELSE 'mid'
                END AS source_level,
                e.confidence,
                jsonb_build_object('source_type', e.source_type) AS metadata,
                e.reviewer,
                e.review_note,
                e.reviewed_at,
                e.created_at
            FROM business_tag_evidence_events e
            WHERE e.mapping_id = %s
              AND e.review_status = 'approved'
              AND e.event_date <= %s
              AND e.reviewer IS NOT NULL
              AND NULLIF(BTRIM(e.reviewer), '') IS NOT NULL
              AND e.review_note IS NOT NULL
              AND NULLIF(BTRIM(e.review_note), '') IS NOT NULL
              AND e.reviewed_at IS NOT NULL
              AND e.reviewed_at <= %s
              AND e.created_at IS NOT NULL
              AND e.created_at <= %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM evidence_extracted_facts linked_fact
                  WHERE linked_fact.evidence_event_id = e.event_id
                    AND linked_fact.mapping_id IS NOT DISTINCT FROM e.mapping_id
              )
            ORDER BY publish_time, event_id
            """,
            (mapping_id, publish_cutoff.date(), cutoff, audit_cutoff),
        )
        approved_events = [dict(row) for row in cur.fetchall()]

        deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
        linked_event_ids = {
            str(row["event_id"])
            for row in facts
            if row.get("event_id")
        }
        for row in facts:
            if row.get("fact_id"):
                identity = ("fact", str(row["fact_id"]))
            else:
                continue
            deduplicated[identity] = row
        for row in approved_events:
            event_id = str(row.get("event_id") or "")
            if not event_id or event_id in linked_event_ids:
                continue
            deduplicated[("event", event_id)] = row
        return sorted(
            deduplicated.values(),
            key=lambda row: (
                row.get("publish_time") or datetime.min,
                str(row.get("fact_id") or row.get("event_id") or ""),
            ),
        )

    def fetch_mappings(
        self,
        cur,
        *,
        chain_id: str,
        mapping_ids: list[str] | None,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        audit_cutoff = datetime.combine(
            trade_date,
            datetime.max.time(),
            tzinfo=SHANGHAI,
        ).astimezone(timezone.utc).replace(tzinfo=None)
        params: list[Any] = [
            trade_date,
            trade_date,
            audit_cutoff,
            audit_cutoff,
            chain_id,
        ]
        mapping_filter = ""
        if mapping_ids:
            mapping_filter = "AND b.mapping_id = ANY(%s)"
            params.append(mapping_ids)
        cur.execute(
            f"""
            SELECT
                b.mapping_id,
                b.code,
                b.business_segment_id,
                b.node_id,
                b.theme_id,
                b.chain_id,
                b.tag_name,
                b.l1_l8_path,
                b.revenue_ratio,
                b.gross_profit_ratio,
                b.confidence,
                b.status,
                b.evidence_ids,
                st.research_stage,
                st.commercialization_stage AS commercial_stage,
                st.review_status AS stage_review_status,
                st.created_at AS stage_created_at,
                st.source_event_id,
                st.source_event_review_status,
                st.source_event_reviewer,
                st.source_event_review_note,
                st.source_event_reviewed_at,
                st.source_event_date,
                st.source_event_created_at,
                ps.next_validation_event,
                ps.next_validation_date
            FROM business_tag_mapping b
            LEFT JOIN LATERAL (
                SELECT
                    st.research_stage,
                    st.commercialization_stage,
                    st.review_status,
                    st.created_at,
                    st.source_event_id,
                    source_event.review_status AS source_event_review_status,
                    source_event.reviewer AS source_event_reviewer,
                    source_event.review_note AS source_event_review_note,
                    source_event.reviewed_at AS source_event_reviewed_at,
                    source_event.event_date AS source_event_date,
                    source_event.created_at AS source_event_created_at
                FROM business_tag_stage_tracking st
                LEFT JOIN business_tag_evidence_events source_event
                  ON source_event.event_id = st.source_event_id
                 AND source_event.mapping_id = b.mapping_id
                WHERE st.mapping_id = b.mapping_id
                  AND st.trade_date <= %s
                ORDER BY st.trade_date DESC, st.created_at DESC
                LIMIT 1
            ) st ON TRUE
            LEFT JOIN business_tag_pool_state ps
              ON ps.mapping_id = b.mapping_id
             AND ps.effective_from <= %s
             AND ps.created_at IS NOT NULL
             AND ps.created_at <= %s
             AND ps.updated_at IS NOT NULL
             AND ps.updated_at <= %s
            WHERE b.chain_id = %s
              AND b.status <> 'rejected'
              {mapping_filter}
            ORDER BY b.code, b.mapping_id
            """,
            tuple(params),
        )
        return [dict(row) for row in cur.fetchall()]

    def fetch_node_score(
        self,
        cur,
        *,
        node_id: str,
        trade_date: date,
        model_version: str,
    ) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT *
            FROM supply_chain_node_scores
            WHERE node_id = %s
              AND trade_date = %s
              AND model_version = %s
            """,
            (node_id, trade_date, model_version),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _normalization_date(value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None

    @staticmethod
    def _normalization_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        numeric = float(value)
        if not math.isfinite(numeric) or not 0.0 <= numeric <= 100.0:
            return None
        return numeric

    @classmethod
    def _resolve_normalized_component(
        cls,
        rows: list[dict[str, Any]],
        *,
        key: str,
        trade_date: date,
        exact_as_of: bool = False,
    ) -> tuple[float | None, tuple[str, ...], bool]:
        accepted: list[tuple[str, float]] = []
        for row in rows:
            evidence_id = str(row.get("evidence_id") or "").strip()
            normalization = row.get("normalization")
            if not evidence_id or not isinstance(normalization, dict):
                continue
            method = normalization.get("method_version")
            if not isinstance(method, str) or not method.strip():
                continue
            as_of = cls._normalization_date(normalization.get("as_of_date"))
            if as_of is None or as_of > trade_date:
                continue
            if exact_as_of and as_of != trade_date:
                continue
            score = cls._normalization_number(normalization.get(key))
            if score is None:
                continue
            accepted.append((evidence_id, score))
        distinct_values = {score for _, score in accepted}
        if len(distinct_values) > 1:
            return None, (), True
        if not distinct_values:
            return None, (), False
        value = next(iter(distinct_values))
        evidence_ids = tuple(
            sorted({evidence_id for evidence_id, score in accepted if score == value})
        )
        return value, evidence_ids, False

    def _fetch_adjusted_price_reaction(
        self,
        cur,
        *,
        code: str,
        trade_date: date,
    ) -> float | None:
        cur.execute(
            """
            /* selection_context:adjusted_price */
            WITH requested AS (
                SELECT
                    %s::text AS requested_code,
                    split_part(%s::text, '.', 1) AS plain_code
            ), matching_codes AS (
                SELECT DISTINCT
                    k.code,
                    requested.requested_code,
                    requested.plain_code
                FROM daily_kline k
                CROSS JOIN requested
                WHERE k.trade_date = %s
                  AND CASE
                      WHEN POSITION('.' IN requested_code) > 0
                      THEN k.code = requested_code OR k.code = plain_code
                      ELSE split_part(k.code, '.', 1) = plain_code
                  END
            ), resolved_code AS (
                SELECT CASE
                    WHEN count(*) FILTER (WHERE code = requested_code) = 1
                    THEN max(code) FILTER (WHERE code = requested_code)
                    WHEN count(*) = 1 THEN min(code)
                END AS code
                FROM matching_codes
            )
            SELECT k.code, k.trade_date, k.close, a.adj_factor
            FROM daily_kline k
            JOIN resolved_code resolved ON resolved.code = k.code
            LEFT JOIN adj_factor a
              ON a.code = k.code
             AND a.trade_date = k.trade_date
            WHERE k.trade_date <= %s
            ORDER BY k.trade_date DESC
            LIMIT 21
            """,
            (code, code, trade_date, trade_date),
        )
        rows = [dict(row) for row in cur.fetchall()]
        if len(rows) != 21:
            return None
        ordered = sorted(rows, key=lambda row: row.get("trade_date"), reverse=True)
        if ordered[0].get("trade_date") != trade_date:
            return None
        if len({row.get("trade_date") for row in ordered}) != 21:
            return None
        real_codes = {str(row.get("code") or "") for row in ordered}
        if "" in real_codes or len(real_codes) != 1:
            return None
        adjusted_prices: list[float] = []
        for row in ordered:
            close = row.get("close")
            factor = row.get("adj_factor")
            if (
                isinstance(close, bool)
                or isinstance(factor, bool)
                or not isinstance(close, (int, float))
                or not isinstance(factor, (int, float))
            ):
                return None
            close_number = float(close)
            factor_number = float(factor)
            if (
                not math.isfinite(close_number)
                or not math.isfinite(factor_number)
                or close_number <= 0
                or factor_number <= 0
            ):
                return None
            adjusted_prices.append(close_number * factor_number)
        start = adjusted_prices[-1]
        end = adjusted_prices[0]
        if start == 0:
            return None
        reaction = end / start - 1.0
        return round(reaction, 10) if math.isfinite(reaction) else None

    def _fetch_approved_stage(
        self,
        cur,
        *,
        mapping_id: str,
        trade_date: date,
        cutoff: datetime,
    ) -> dict[str, Any] | None:
        cur.execute(
            """
            /* selection_context:stage */
            WITH latest_stage AS (
                SELECT st.*
                FROM business_tag_stage_tracking st
                WHERE st.mapping_id = %s
                  AND st.trade_date <= %s
                ORDER BY st.trade_date DESC, st.created_at DESC, st.stage_id DESC
                LIMIT 1
            )
            SELECT
                st.research_stage,
                st.commercialization_stage,
                st.source_event_id
            FROM latest_stage st
            JOIN business_tag_evidence_events source_event
              ON source_event.event_id = st.source_event_id
             AND source_event.mapping_id = st.mapping_id
            WHERE st.review_status = 'approved'
              AND (st.created_at AT TIME ZONE 'UTC') <= %s
              AND source_event.review_status = 'approved'
              AND source_event.reviewer IS NOT NULL
              AND NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL
              AND source_event.review_note IS NOT NULL
              AND NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL
              AND source_event.reviewed_at IS NOT NULL
              AND source_event.reviewed_at <= %s
              AND source_event.event_date <= %s
              AND (source_event.created_at AT TIME ZONE 'UTC') <= %s
            """,
            (mapping_id, trade_date, cutoff, cutoff, trade_date, cutoff),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _fetch_evidence_delta_rows(
        self,
        cur,
        *,
        mapping_id: str,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        cur.execute(
            """
            /* selection_context:evidence_delta */
            SELECT
                f.fact_id AS evidence_id,
                f.metadata->'review_normalization' AS normalization
            FROM evidence_extracted_facts f
            JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
            WHERE f.mapping_id = %s
              AND f.validation_status = 'confirmed'
              AND f.reviewer IS NOT NULL
              AND NULLIF(BTRIM(f.reviewer), '') IS NOT NULL
              AND f.review_note IS NOT NULL
              AND NULLIF(BTRIM(f.review_note), '') IS NOT NULL
              AND f.reviewed_at IS NOT NULL
              AND f.reviewed_at <= %s
              AND (f.created_at AT TIME ZONE 'UTC') <= %s
              AND d.publish_time IS NOT NULL
              AND (d.publish_time AT TIME ZONE 'Asia/Shanghai') <= %s
              AND f.metadata->'review_normalization' ? 'evidence_delta_score'
            ORDER BY f.fact_id
            """,
            (mapping_id, cutoff, cutoff, cutoff),
        )
        return [dict(row) for row in cur.fetchall()]

    def _fetch_expectation_rows(
        self,
        cur,
        *,
        mapping_id: str,
        trade_date: date,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        cur.execute(
            """
            /* selection_context:expectation */
            SELECT
                monitor.monitor_id AS evidence_id,
                monitor.gap_status,
                monitor.market_price_change,
                NULLIF(monitor.metadata->>'trigger_fact_id', '') AS trigger_fact_id,
                monitor.metadata->'review_normalization' AS normalization
            FROM business_tag_expectation_monitor monitor
            JOIN raw_evidence_documents d ON d.doc_id = monitor.source_doc_id
            WHERE monitor.mapping_id = %s
              AND monitor.review_status = 'approved'
              AND monitor.reviewer IS NOT NULL
              AND NULLIF(BTRIM(monitor.reviewer), '') IS NOT NULL
              AND monitor.review_note IS NOT NULL
              AND NULLIF(BTRIM(monitor.review_note), '') IS NOT NULL
              AND monitor.reviewed_at IS NOT NULL
              AND monitor.reviewed_at <= %s
              AND (monitor.created_at AT TIME ZONE 'UTC') <= %s
              AND monitor.claim_date IS NOT NULL
              AND monitor.claim_date <= %s
              AND d.publish_time IS NOT NULL
              AND (d.publish_time AT TIME ZONE 'Asia/Shanghai') <= %s
            ORDER BY monitor.monitor_id
            """,
            (mapping_id, cutoff, cutoff, trade_date, cutoff),
        )
        return [dict(row) for row in cur.fetchall()]

    def _fetch_approved_catalyst_inputs(
        self,
        cur,
        *,
        mapping_id: str,
        trade_date: date,
        cutoff: datetime,
    ) -> list[dict[str, Any]]:
        cur.execute(
            """
            /* selection_context:catalyst */
            SELECT
                monitor.monitor_id AS evidence_id,
                monitor.metadata->'review_normalization'->>'catalyst_score' AS raw_score,
                monitor.metadata->'review_normalization' AS normalization,
                coalesce(source.source_level, d.source_level) AS source_level,
                trigger_fact.confidence,
                source.source_reliability_score AS source_reliability
            FROM business_tag_expectation_monitor monitor
            JOIN raw_evidence_documents d ON d.doc_id = monitor.source_doc_id
            JOIN evidence_source_catalog source ON source.source_id = d.source_id
            JOIN evidence_extracted_facts trigger_fact
              ON trigger_fact.fact_id = NULLIF(monitor.metadata->>'trigger_fact_id', '')
             AND trigger_fact.mapping_id = monitor.mapping_id
            LEFT JOIN raw_evidence_documents trigger_doc
              ON trigger_doc.doc_id = trigger_fact.doc_id
            LEFT JOIN business_tag_evidence_events trigger_event
              ON trigger_event.event_id = trigger_fact.evidence_event_id
             AND trigger_event.mapping_id = trigger_fact.mapping_id
            WHERE monitor.mapping_id = %s
              AND monitor.review_status = 'approved'
              AND monitor.reviewer IS NOT NULL
              AND NULLIF(BTRIM(monitor.reviewer), '') IS NOT NULL
              AND monitor.review_note IS NOT NULL
              AND NULLIF(BTRIM(monitor.review_note), '') IS NOT NULL
              AND monitor.reviewed_at IS NOT NULL
              AND monitor.reviewed_at <= %s
              AND (monitor.created_at AT TIME ZONE 'UTC') <= %s
              AND monitor.expected_date > %s
              AND d.publish_time IS NOT NULL
              AND (d.publish_time AT TIME ZONE 'Asia/Shanghai') <= %s
              AND trigger_fact.validation_status = 'confirmed'
              AND trigger_fact.reviewer IS NOT NULL
              AND NULLIF(BTRIM(trigger_fact.reviewer), '') IS NOT NULL
              AND trigger_fact.review_note IS NOT NULL
              AND NULLIF(BTRIM(trigger_fact.review_note), '') IS NOT NULL
              AND trigger_fact.reviewed_at IS NOT NULL
              AND trigger_fact.reviewed_at <= %s
              AND (trigger_fact.created_at AT TIME ZONE 'UTC') <= %s
              AND coalesce(
                    trigger_doc.publish_time,
                    trigger_event.event_date::timestamp
                  ) IS NOT NULL
              AND (
                    coalesce(
                        trigger_doc.publish_time,
                        trigger_event.event_date::timestamp
                    ) AT TIME ZONE 'Asia/Shanghai'
                  ) <= %s
              AND coalesce(source.source_level, d.source_level) IN ('mid', 'strong')
              AND source.enabled IS TRUE
              AND source.source_reliability_score BETWEEN 0 AND 1
              AND trigger_fact.confidence BETWEEN 0 AND 1
            ORDER BY monitor.monitor_id
            """,
            (
                mapping_id,
                cutoff,
                cutoff,
                trade_date,
                cutoff,
                cutoff,
                cutoff,
                cutoff,
            ),
        )
        return [dict(row) for row in cur.fetchall()]

    def _fetch_confirmed_risk_inputs(
        self,
        cur,
        *,
        mapping_id: str,
        cutoff: datetime,
        excluded_fact_ids: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        cur.execute(
            """
            /* selection_context:risk */
            WITH claim_trigger_fact_ids AS (
                SELECT unnest(%s::text[]) AS fact_id
            )
            SELECT
                f.fact_id AS evidence_id,
                f.metadata->'review_normalization'->>'risk_score' AS raw_score,
                f.metadata->'review_normalization' AS normalization,
                coalesce(source.source_level, d.source_level, f.source_level) AS source_level,
                f.confidence,
                source.source_reliability_score AS source_reliability
            FROM evidence_extracted_facts f
            JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
            JOIN evidence_source_catalog source ON source.source_id = d.source_id
            WHERE f.mapping_id = %s
              AND f.validation_status = 'confirmed'
              AND f.reviewer IS NOT NULL
              AND NULLIF(BTRIM(f.reviewer), '') IS NOT NULL
              AND f.review_note IS NOT NULL
              AND NULLIF(BTRIM(f.review_note), '') IS NOT NULL
              AND f.reviewed_at IS NOT NULL
              AND f.reviewed_at <= %s
              AND (f.created_at AT TIME ZONE 'UTC') <= %s
              AND d.publish_time IS NOT NULL
              AND (d.publish_time AT TIME ZONE 'Asia/Shanghai') <= %s
              AND (
                    f.fact_type = 'negative'
                 OR coalesce(f.metadata->>'route_failure', 'false') = 'true'
                 OR (f.fact_nature = 'market_signal' AND f.risk_signal IS TRUE)
              )
              AND coalesce(f.metadata->>'route_eligibility_only', 'false') <> 'true'
              AND NULLIF(BTRIM(f.metadata->>'veto_reason'), '') IS NULL
              AND coalesce(f.metadata->>'is_veto', 'false') <> 'true'
              AND NOT EXISTS (
                  SELECT 1 FROM claim_trigger_fact_ids claim
                  WHERE claim.fact_id = f.fact_id
              )
              AND coalesce(source.source_level, d.source_level, f.source_level)
                  IN ('mid', 'strong')
              AND source.enabled IS TRUE
              AND source.source_reliability_score BETWEEN 0 AND 1
              AND f.confidence BETWEEN 0 AND 1
            ORDER BY f.fact_id
            """,
            (list(excluded_fact_ids), mapping_id, cutoff, cutoff, cutoff),
        )
        return [dict(row) for row in cur.fetchall()]

    def fetch_selection_context(
        self,
        cur,
        *,
        mapping_id: str,
        code: str,
        trade_date: date,
        cutoff: datetime,
    ) -> dict[str, Any]:
        limitations: list[str] = []
        price_reaction = self._fetch_adjusted_price_reaction(
            cur,
            code=code,
            trade_date=trade_date,
        )
        if price_reaction is None:
            limitations.append("missing_adjusted_price_reaction")

        stage = self._fetch_approved_stage(
            cur,
            mapping_id=mapping_id,
            trade_date=trade_date,
            cutoff=cutoff,
        )
        stage_ids: tuple[str, ...] = ()
        research_rank: int | None = None
        commercial_rank: int | None = None
        if stage:
            research = str(stage.get("research_stage") or "")
            commercial = str(stage.get("commercialization_stage") or "")
            if research in {f"R{rank}" for rank in range(7)} and commercial in {
                f"C{rank}" for rank in range(8)
            }:
                research_rank = int(research[1:])
                commercial_rank = int(commercial[1:])
                source_event_id = str(stage.get("source_event_id") or "").strip()
                if source_event_id:
                    stage_ids = (source_event_id,)
        if research_rank is None or commercial_rank is None:
            limitations.append("missing_audited_stage")

        delta_rows = self._fetch_evidence_delta_rows(
            cur,
            mapping_id=mapping_id,
            cutoff=cutoff,
        )
        evidence_delta, delta_ids, ambiguous_delta = self._resolve_normalized_component(
            delta_rows,
            key="evidence_delta_score",
            trade_date=trade_date,
        )
        if ambiguous_delta:
            limitations.append("ambiguous_evidence_delta_score")
        elif evidence_delta is None:
            limitations.append("missing_evidence_delta_score")

        actual_progress: float | None = None
        if (
            research_rank is not None
            and commercial_rank is not None
            and evidence_delta is not None
        ):
            actual_progress = calculate_actual_progress_score(
                research_rank,
                commercial_rank,
                evidence_delta,
            )

        expectation_rows = self._fetch_expectation_rows(
            cur,
            mapping_id=mapping_id,
            trade_date=trade_date,
            cutoff=cutoff,
        )
        market_rows = [
            row
            for row in expectation_rows
            if str(row.get("gap_status") or "") not in {"missed", "contradicted"}
        ]
        market_score, market_ids, ambiguous_market = self._resolve_normalized_component(
            market_rows,
            key="market_expectation_score",
            trade_date=trade_date,
            exact_as_of=True,
        )
        if market_score is not None:
            matching_ids = {
                str(row.get("evidence_id"))
                for row in market_rows
                if row.get("market_price_change") is not None
                and price_reaction is not None
                and isinstance(row.get("market_price_change"), (int, float))
                and not isinstance(row.get("market_price_change"), bool)
                and math.isfinite(float(row["market_price_change"]))
                and abs(float(row["market_price_change"]) - price_reaction * 100)
                <= 0.01
            }
            if not market_ids or any(item not in matching_ids for item in market_ids):
                market_score = None
                market_ids = ()
                limitations.append("market_price_reaction_mismatch")
        if ambiguous_market:
            limitations.append("ambiguous_market_expectation_score")
        elif market_score is None and "market_price_reaction_mismatch" not in limitations:
            limitations.append("missing_market_expectation_score")

        claim_rows = [
            row
            for row in expectation_rows
            if str(row.get("gap_status") or "") in {"missed", "contradicted"}
        ]
        claim_penalty, claim_ids, ambiguous_claim = self._resolve_normalized_component(
            claim_rows,
            key="claim_risk_penalty_score",
            trade_date=trade_date,
        )
        if ambiguous_claim:
            limitations.append("ambiguous_claim_risk_penalty_score")
        elif claim_penalty is None:
            limitations.append("missing_claim_risk_penalty_score")
        used_claim_trigger_ids = tuple(
            sorted(
                {
                    str(row.get("trigger_fact_id") or "").strip()
                    for row in claim_rows
                    if str(row.get("evidence_id") or "") in set(claim_ids)
                    and str(row.get("trigger_fact_id") or "").strip()
                }
            )
        )

        expectation_inputs = ExpectationGapInputs(
            actual_progress_score=actual_progress,
            market_expectation_score=market_score,
            evidence_delta_score=evidence_delta,
            claim_risk_penalty_score=claim_penalty,
            evidence_ids=tuple(sorted(set(stage_ids + delta_ids + market_ids + claim_ids))),
        )
        expectation_gap = calculate_approved_expectation_gap(expectation_inputs)
        if expectation_gap is None:
            limitations.append("missing_expectation_gap_score")

        catalyst_rows = self._fetch_approved_catalyst_inputs(
            cur,
            mapping_id=mapping_id,
            trade_date=trade_date,
            cutoff=cutoff,
        )
        catalyst_inputs: list[ApprovedScoreInput] = []
        for row in catalyst_rows:
            score, ids, ambiguous = self._resolve_normalized_component(
                [row],
                key="catalyst_score",
                trade_date=trade_date,
            )
            if score is None or ambiguous or not ids:
                continue
            catalyst_inputs.append(
                ApprovedScoreInput(
                    evidence_id=ids[0],
                    score=score,
                    source_level=str(row.get("source_level") or ""),
                    confidence=row.get("confidence"),
                    source_reliability=row.get("source_reliability"),
                )
            )
        catalyst = aggregate_catalyst_score(catalyst_inputs)
        if catalyst.score is None:
            limitations.append("missing_catalyst_score")

        risk_rows = self._fetch_confirmed_risk_inputs(
            cur,
            mapping_id=mapping_id,
            cutoff=cutoff,
            excluded_fact_ids=used_claim_trigger_ids,
        )
        risk_inputs: list[ApprovedScoreInput] = []
        for row in risk_rows:
            score, ids, ambiguous = self._resolve_normalized_component(
                [row],
                key="risk_score",
                trade_date=trade_date,
            )
            if score is None or ambiguous or not ids:
                continue
            risk_inputs.append(
                ApprovedScoreInput(
                    evidence_id=ids[0],
                    score=score,
                    source_level=str(row.get("source_level") or ""),
                    confidence=row.get("confidence"),
                    source_reliability=row.get("source_reliability"),
                )
            )
        risk = aggregate_risk_score(risk_inputs)
        if risk.score is None:
            limitations.append("missing_risk_score")

        evidence_ids = sorted(
            set(expectation_inputs.evidence_ids)
            | set(catalyst.evidence_ids)
            | set(risk.evidence_ids)
        )
        return {
            "actual_progress_score": actual_progress,
            "market_expectation_score": market_score,
            "evidence_delta_score": evidence_delta,
            "claim_risk_penalty_score": claim_penalty,
            "expectation_gap_score": expectation_gap,
            "catalyst_score": catalyst.score,
            "risk_score": risk.score,
            "adjusted_price_reaction": price_reaction,
            "selection_context_evidence_ids": evidence_ids,
            "selection_context_limitations": sorted(set(limitations)),
        }

    def _read_rows(self, statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection = self.connection_factory()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cur:
                missing = self.preflight(cur)
                if missing:
                    raise MissingSelectionTables(missing)
                cur.execute(statement, params)
                return [dict(row) for row in cur.fetchall()]
        finally:
            connection.close()

    def fetch_stock_explanation_rows(
        self,
        *,
        code: str,
        chain_id: str,
        trade_date: date,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        cutoff = datetime.combine(
            trade_date,
            datetime.max.time(),
            tzinfo=SHANGHAI,
        ).astimezone(timezone.utc)
        result: dict[str, dict[str, list[dict[str, Any]]]] = {}

        def bucket(mapping_id: str) -> dict[str, list[dict[str, Any]]]:
            return result.setdefault(
                mapping_id,
                {
                    "approved_evidence": [],
                    "pending_facts": [],
                    "rejected_facts": [],
                },
            )

        connection = self.connection_factory()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cur:
                missing = self.preflight(cur)
                if missing:
                    raise MissingSelectionTables(missing)
                cur.execute(
                    """
                    /* selection_explanation:facts */
                    SELECT
                        f.mapping_id,
                        f.fact_id AS evidence_id,
                        'fact' AS kind,
                        f.validation_status AS record_status,
                        f.fact_type,
                        f.source_level,
                        coalesce(d.publish_time, source_event.event_date::timestamp)
                            AS publish_time,
                        f.reviewed_at
                    FROM evidence_extracted_facts f
                    JOIN business_tag_mapping b ON b.mapping_id = f.mapping_id
                    LEFT JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
                    LEFT JOIN business_tag_evidence_events source_event
                      ON source_event.event_id = f.evidence_event_id
                     AND source_event.mapping_id = f.mapping_id
                    WHERE split_part(b.code, '.', 1) = split_part(%s, '.', 1)
                      AND b.chain_id = %s
                      AND coalesce(d.publish_time, source_event.event_date::timestamp)
                          IS NOT NULL
                      AND (
                          coalesce(d.publish_time, source_event.event_date::timestamp)
                          AT TIME ZONE 'Asia/Shanghai'
                      ) <= %s
                      AND (f.created_at AT TIME ZONE 'UTC') <= %s
                      AND (
                          f.validation_status IN ('pending', 'expired')
                          OR (
                              f.validation_status IN ('confirmed', 'rejected', 'contradicted')
                              AND
                              f.reviewer IS NOT NULL
                              AND NULLIF(BTRIM(f.reviewer), '') IS NOT NULL
                              AND f.review_note IS NOT NULL
                              AND NULLIF(BTRIM(f.review_note), '') IS NOT NULL
                              AND f.reviewed_at IS NOT NULL
                              AND f.reviewed_at <= %s
                          )
                      )
                    ORDER BY f.mapping_id, f.fact_id
                    """,
                    (code, chain_id, cutoff, cutoff, cutoff),
                )
                fact_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    /* selection_explanation:events */
                    SELECT
                        source_event.mapping_id,
                        source_event.event_id AS evidence_id,
                        'event' AS kind,
                        source_event.review_status AS record_status,
                        source_event.evidence_type AS fact_type,
                        CASE
                            WHEN source_event.source_type IN (
                                'annual_report','financial_report',
                                'announcement','exchange_filing'
                            ) THEN 'strong'
                            ELSE 'mid'
                        END AS source_level,
                        source_event.event_date::timestamp AS publish_time,
                        source_event.reviewed_at
                    FROM business_tag_evidence_events source_event
                    JOIN business_tag_mapping b
                      ON b.mapping_id = source_event.mapping_id
                    WHERE split_part(b.code, '.', 1) = split_part(%s, '.', 1)
                      AND b.chain_id = %s
                      AND source_event.event_date <= %s
                      AND (source_event.created_at AT TIME ZONE 'UTC') <= %s
                      AND source_event.review_status = 'approved'
                      AND source_event.reviewer IS NOT NULL
                      AND NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL
                      AND source_event.review_note IS NOT NULL
                      AND NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL
                      AND source_event.reviewed_at IS NOT NULL
                      AND source_event.reviewed_at <= %s
                    ORDER BY source_event.mapping_id, source_event.event_id
                    """,
                    (code, chain_id, trade_date, cutoff, cutoff),
                )
                event_rows = [dict(row) for row in cur.fetchall()]

                cur.execute(
                    """
                    /* selection_explanation:monitors */
                    SELECT
                        monitor.mapping_id,
                        monitor.monitor_id AS evidence_id,
                        'monitor' AS kind,
                        monitor.review_status AS record_status,
                        'expectation_monitor' AS fact_type,
                        coalesce(source.source_level, d.source_level)
                            AS source_level,
                        d.publish_time,
                        monitor.reviewed_at
                    FROM business_tag_expectation_monitor monitor
                    JOIN business_tag_mapping b ON b.mapping_id = monitor.mapping_id
                    JOIN raw_evidence_documents d ON d.doc_id = monitor.source_doc_id
                    LEFT JOIN evidence_source_catalog source
                      ON source.source_id = d.source_id
                    WHERE split_part(b.code, '.', 1) = split_part(%s, '.', 1)
                      AND b.chain_id = %s
                      AND d.publish_time IS NOT NULL
                      AND (d.publish_time AT TIME ZONE 'Asia/Shanghai') <= %s
                      AND (monitor.created_at AT TIME ZONE 'UTC') <= %s
                      AND monitor.review_status = 'approved'
                      AND monitor.reviewer IS NOT NULL
                      AND NULLIF(BTRIM(monitor.reviewer), '') IS NOT NULL
                      AND monitor.review_note IS NOT NULL
                      AND NULLIF(BTRIM(monitor.review_note), '') IS NOT NULL
                      AND monitor.reviewed_at IS NOT NULL
                      AND monitor.reviewed_at <= %s
                    ORDER BY monitor.mapping_id, monitor.monitor_id
                    """,
                    (code, chain_id, cutoff, cutoff, cutoff),
                )
                monitor_rows = [dict(row) for row in cur.fetchall()]
        finally:
            connection.close()

        for row in fact_rows:
            mapping_id = str(row.get("mapping_id") or "")
            evidence_id = str(row.get("evidence_id") or "")
            if not mapping_id or not evidence_id:
                continue
            status = str(row.get("record_status") or "")
            if status == "confirmed":
                bucket(mapping_id)["approved_evidence"].append(
                    {
                        "evidence_id": evidence_id,
                        "kind": "fact",
                        "status": "approved",
                        "fact_type": row.get("fact_type"),
                        "source_level": row.get("source_level"),
                        "publish_time": row.get("publish_time"),
                        "reviewed_at": row.get("reviewed_at"),
                    }
                )
            else:
                reviewed_at = row.get("reviewed_at")
                if status in {"rejected", "contradicted"}:
                    if not isinstance(reviewed_at, datetime):
                        continue
                    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
                        continue
                    if reviewed_at.astimezone(timezone.utc) > cutoff:
                        continue
                item = {
                    "fact_id": evidence_id,
                    "status": "pending" if status == "pending" else status,
                    "fact_type": row.get("fact_type"),
                    "source_level": row.get("source_level"),
                    "publish_time": row.get("publish_time"),
                }
                if reviewed_at is not None:
                    item["reviewed_at"] = reviewed_at
                target = (
                    "pending_facts"
                    if status in {"pending", "expired"}
                    else "rejected_facts"
                )
                bucket(mapping_id)[target].append(item)

        for row in [*event_rows, *monitor_rows]:
            mapping_id = str(row.get("mapping_id") or "")
            evidence_id = str(row.get("evidence_id") or "")
            if not mapping_id or not evidence_id:
                continue
            bucket(mapping_id)["approved_evidence"].append(
                {
                    "evidence_id": evidence_id,
                    "kind": row.get("kind"),
                    "status": "approved",
                    "fact_type": row.get("fact_type"),
                    "source_level": row.get("source_level"),
                    "publish_time": row.get("publish_time"),
                    "reviewed_at": row.get("reviewed_at"),
                }
            )

        for explanation in result.values():
            for key in ("approved_evidence", "pending_facts", "rejected_facts"):
                id_key = "evidence_id" if key == "approved_evidence" else "fact_id"
                explanation[key].sort(key=lambda item: str(item.get(id_key) or ""))
        return result

    @staticmethod
    def _selection_row_columns() -> str:
        return """
            b.code,
            b.mapping_id,
            b.business_segment_id,
            b.node_id,
            b.theme_id,
            b.chain_id,
            b.tag_name,
            b.l1_l8_path,
            b.revenue_ratio,
            b.gross_profit_ratio,
            b.confidence AS mapping_confidence,
            b.status AS mapping_status,
            b.evidence_ids AS mapping_evidence_ids,
            (b.business_segment_id IS NOT NULL AND
             (b.revenue_ratio IS NOT NULL OR b.gross_profit_ratio IS NOT NULL))
                AS independent_revenue,
            st.research_stage,
            st.commercialization_stage AS commercial_stage,
            a.evidence_level,
            a.authenticity_score,
            a.coverage_ratio AS authenticity_coverage,
            a.max_pool_code,
            a.review_status AS authenticity_review_status,
            a.score_detail AS authenticity_detail,
            a.evidence_ids AS authenticity_evidence_ids,
            o.growth_score,
            o.profit_score,
            o.moat_score,
            o.total_score AS operating_quality_score,
            o.total_coverage AS operating_quality_coverage,
            o.score_detail AS operating_quality_detail,
            ben.node_attractiveness,
            ben.benefit_score,
            ben.coverage_ratio AS benefit_coverage,
            ben.score_detail AS benefit_detail,
            s.expectation_gap_score,
            s.catalyst_score,
            s.risk_score,
            s.confidence_score,
            s.opportunity_score,
            s.pool_code,
            s.eligibility_status,
            s.veto_reasons,
            s.factor_detail,
            s.evidence_ids AS selection_evidence_ids,
            ps.state_status AS pool_state_status,
            ps.next_validation_event,
            ps.next_validation_date
        """

    def fetch_candidate_rows(
        self,
        *,
        chain_id: str,
        trade_date: date,
        pool: str | None,
        model_version: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.combine(
            trade_date,
            datetime.max.time(),
            tzinfo=SHANGHAI,
        ).astimezone(timezone.utc)
        params: list[Any] = [
            cutoff,
            cutoff,
            cutoff,
            chain_id,
            trade_date,
            model_version,
        ]
        primary_pool_filter = ""
        if pool is not None:
            primary_pool_filter = "AND pool_code = %s"
            params.append(pool)
        params.extend([limit, offset])
        columns = self._selection_row_columns()
        return self._read_rows(
            f"""
            WITH scored AS (
                SELECT
                    {columns},
                    row_number() OVER (
                        PARTITION BY b.code
                        ORDER BY
                            CASE a.evidence_level
                                WHEN 'E6' THEN 6 WHEN 'E5' THEN 5
                                WHEN 'E4' THEN 4 WHEN 'E3' THEN 3
                                WHEN 'E2' THEN 2 WHEN 'E1' THEN 1 ELSE 0
                            END DESC,
                            s.benefit_score DESC NULLS LAST,
                            b.mapping_id DESC
                    ) AS primary_rank
                FROM business_tag_selection_scores s
                JOIN business_tag_mapping b ON b.mapping_id = s.mapping_id
                JOIN business_tag_authenticity_scores a
                  ON a.mapping_id = s.mapping_id
                 AND a.trade_date = s.trade_date
                 AND a.model_version = s.model_version
                JOIN business_tag_operating_quality_scores o
                  ON o.mapping_id = s.mapping_id
                 AND o.trade_date = s.trade_date
                 AND o.model_version = s.model_version
                JOIN business_tag_benefit_scores ben
                  ON ben.mapping_id = s.mapping_id
                 AND ben.trade_date = s.trade_date
                 AND ben.model_version = s.model_version
                LEFT JOIN LATERAL (
                    SELECT stage.research_stage, stage.commercialization_stage
                    FROM (
                        SELECT stage_tracker.*
                        FROM business_tag_stage_tracking stage_tracker
                        WHERE stage_tracker.mapping_id = b.mapping_id
                          AND stage_tracker.trade_date <= s.trade_date
                          AND (
                              stage_tracker.created_at AT TIME ZONE 'UTC'
                          ) <= %s
                        ORDER BY stage_tracker.trade_date DESC,
                                 stage_tracker.created_at DESC
                        LIMIT 1
                    ) stage
                    JOIN business_tag_evidence_events source_event
                      ON source_event.event_id = stage.source_event_id
                     AND source_event.mapping_id = stage.mapping_id
                    WHERE stage.review_status = 'approved'
                      AND source_event.review_status = 'approved'
                      AND source_event.reviewer IS NOT NULL
                      AND NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL
                      AND source_event.review_note IS NOT NULL
                      AND NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL
                      AND source_event.reviewed_at IS NOT NULL
                      AND source_event.reviewed_at <= %s
                      AND source_event.event_date <= s.trade_date
                      AND (
                          source_event.created_at AT TIME ZONE 'UTC'
                      ) <= %s
                ) st ON TRUE
                LEFT JOIN business_tag_pool_state ps
                  ON ps.mapping_id = b.mapping_id
                WHERE b.chain_id = %s
                  AND s.trade_date = %s
                  AND s.model_version = %s
                  AND s.pool_code IS NOT NULL
                  AND b.status <> 'rejected'
            ),
            paged_codes AS (
                SELECT code, max(coalesce(opportunity_score, -1)) AS rank_score
                FROM scored
                WHERE primary_rank = 1
                  {primary_pool_filter}
                GROUP BY code
                ORDER BY rank_score DESC, code
                LIMIT %s OFFSET %s
            )
            SELECT scored.*
            FROM scored
            JOIN paged_codes USING (code)
            ORDER BY paged_codes.rank_score DESC, scored.code,
                     scored.primary_rank, scored.mapping_id
            """,
            tuple(params),
        )

    def fetch_stock_detail_rows(
        self,
        *,
        code: str,
        chain_id: str,
        trade_date: date,
        model_version: str,
    ) -> list[dict[str, Any]]:
        columns = self._selection_row_columns()
        cutoff = datetime.combine(
            trade_date,
            datetime.max.time(),
            tzinfo=SHANGHAI,
        ).astimezone(timezone.utc)
        return self._read_rows(
            f"""
            SELECT {columns}
            FROM business_tag_mapping b
            LEFT JOIN LATERAL (
                SELECT stage.research_stage, stage.commercialization_stage
                FROM (
                    SELECT stage_tracker.*
                    FROM business_tag_stage_tracking stage_tracker
                    WHERE stage_tracker.mapping_id = b.mapping_id
                      AND stage_tracker.trade_date <= %s
                      AND (
                          stage_tracker.created_at AT TIME ZONE 'UTC'
                      ) <= %s
                    ORDER BY stage_tracker.trade_date DESC,
                             stage_tracker.created_at DESC
                    LIMIT 1
                ) stage
                JOIN business_tag_evidence_events source_event
                  ON source_event.event_id = stage.source_event_id
                 AND source_event.mapping_id = stage.mapping_id
                WHERE stage.review_status = 'approved'
                  AND source_event.review_status = 'approved'
                  AND source_event.reviewer IS NOT NULL
                  AND NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL
                  AND source_event.review_note IS NOT NULL
                  AND NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL
                  AND source_event.reviewed_at IS NOT NULL
                  AND source_event.reviewed_at <= %s
                  AND source_event.event_date <= %s
                  AND (
                      source_event.created_at AT TIME ZONE 'UTC'
                  ) <= %s
            ) st ON TRUE
            JOIN business_tag_selection_scores s
              ON s.mapping_id = b.mapping_id
            JOIN business_tag_authenticity_scores a
              ON a.mapping_id = s.mapping_id
             AND a.trade_date = s.trade_date
             AND a.model_version = s.model_version
            JOIN business_tag_operating_quality_scores o
              ON o.mapping_id = s.mapping_id
             AND o.trade_date = s.trade_date
             AND o.model_version = s.model_version
            JOIN business_tag_benefit_scores ben
              ON ben.mapping_id = s.mapping_id
             AND ben.trade_date = s.trade_date
             AND ben.model_version = s.model_version
            LEFT JOIN business_tag_pool_state ps ON ps.mapping_id = b.mapping_id
            WHERE b.code = %s
              AND b.chain_id = %s
              AND s.trade_date = %s
              AND s.model_version = %s
              AND b.status <> 'rejected'
            ORDER BY
                CASE a.evidence_level
                    WHEN 'E6' THEN 6 WHEN 'E5' THEN 5 WHEN 'E4' THEN 4
                    WHEN 'E3' THEN 3 WHEN 'E2' THEN 2 WHEN 'E1' THEN 1 ELSE 0
                END DESC,
                s.benefit_score DESC NULLS LAST,
                b.mapping_id DESC
            """,
            (
                trade_date,
                cutoff,
                cutoff,
                trade_date,
                cutoff,
                code,
                chain_id,
                trade_date,
                model_version,
            ),
        )

    def fetch_transition_rows(
        self,
        *,
        code: str,
        chain_id: str,
        trade_date: date,
    ) -> list[dict[str, Any]]:
        cutoff = datetime.combine(
            trade_date,
            datetime.max.time(),
            tzinfo=SHANGHAI,
        ).astimezone(timezone.utc)
        return self._read_rows(
            """
            SELECT
                t.transition_id,
                t.mapping_id,
                t.code,
                t.from_pool_code,
                t.to_pool_code,
                t.transition_date,
                t.transition_reason,
                t.trigger_evidence_ids,
                t.review_status,
                t.reviewer,
                t.reviewed_at,
                t.created_at
            FROM business_tag_pool_transition_log t
            JOIN business_tag_mapping b ON b.mapping_id = t.mapping_id
            WHERE t.code = %s
              AND b.chain_id = %s
              AND t.transition_date <= %s
              AND (t.created_at AT TIME ZONE 'UTC') <= %s
            ORDER BY t.transition_date DESC, t.created_at DESC, t.transition_id
            """,
            (code, chain_id, trade_date, cutoff),
        )

    @staticmethod
    def _record_id(prefix: str, *parts: Any) -> str:
        token = hashlib.sha1(
            ":".join(str(part) for part in parts).encode("utf-8")
        ).hexdigest()[:20]
        return f"{prefix}-{token}"

    def upsert_score_bundle(self, cur, bundle: dict[str, Any]) -> None:
        mapping_id = str(bundle["mapping_id"])
        trade_date = bundle["trade_date"]
        model_version = str(bundle["model_version"])
        evidence_ids = list(bundle.get("evidence_ids") or [])

        authenticity = bundle["authenticity"]
        authenticity_detail = dict(authenticity.get("detail") or {})
        cur.execute(
            """
            INSERT INTO business_tag_authenticity_scores (
                score_id,mapping_id,trade_date,model_version,evidence_level,
                product_evidence_score,customer_evidence_score,
                order_revenue_evidence_score,source_reliability_score,
                freshness_score,authenticity_score,coverage_ratio,max_pool_code,
                evidence_ids,review_status,score_detail
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mapping_id, trade_date, model_version) DO UPDATE SET
                evidence_level=EXCLUDED.evidence_level,
                product_evidence_score=EXCLUDED.product_evidence_score,
                customer_evidence_score=EXCLUDED.customer_evidence_score,
                order_revenue_evidence_score=EXCLUDED.order_revenue_evidence_score,
                source_reliability_score=EXCLUDED.source_reliability_score,
                freshness_score=EXCLUDED.freshness_score,
                authenticity_score=EXCLUDED.authenticity_score,
                coverage_ratio=EXCLUDED.coverage_ratio,
                max_pool_code=EXCLUDED.max_pool_code,
                evidence_ids=EXCLUDED.evidence_ids,
                score_detail=EXCLUDED.score_detail
            """,
            (
                self._record_id("AUTH", mapping_id, trade_date, model_version),
                mapping_id,
                trade_date,
                model_version,
                authenticity["evidence_level"],
                authenticity_detail.get("product_evidence_score"),
                authenticity_detail.get("customer_evidence_score"),
                authenticity_detail.get("order_revenue_evidence_score"),
                authenticity_detail.get("source_reliability_score"),
                authenticity_detail.get("freshness_score"),
                authenticity.get("score"),
                authenticity.get("coverage_ratio", 0.0),
                authenticity.get("max_pool_code"),
                Json(evidence_ids),
                "pending_review",
                Json(authenticity_detail),
            ),
        )

        operating = bundle["operating_quality"]
        operating_detail = dict(operating.get("detail") or {})
        cur.execute(
            """
            INSERT INTO business_tag_operating_quality_scores (
                score_id,mapping_id,trade_date,model_version,growth_score,
                profit_score,moat_score,total_score,growth_coverage,
                profit_coverage,moat_coverage,total_coverage,data_status,
                cap_hits,score_detail,evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mapping_id, trade_date, model_version) DO UPDATE SET
                growth_score=EXCLUDED.growth_score,
                profit_score=EXCLUDED.profit_score,
                moat_score=EXCLUDED.moat_score,
                total_score=EXCLUDED.total_score,
                growth_coverage=EXCLUDED.growth_coverage,
                profit_coverage=EXCLUDED.profit_coverage,
                moat_coverage=EXCLUDED.moat_coverage,
                total_coverage=EXCLUDED.total_coverage,
                data_status=EXCLUDED.data_status,
                cap_hits=EXCLUDED.cap_hits,
                score_detail=EXCLUDED.score_detail,
                evidence_ids=EXCLUDED.evidence_ids
            """,
            (
                self._record_id("OPS", mapping_id, trade_date, model_version),
                mapping_id,
                trade_date,
                model_version,
                operating_detail.get("growth_score"),
                operating_detail.get("profit_score"),
                operating_detail.get("moat_score"),
                operating.get("score"),
                operating_detail.get("growth_coverage", 0.0),
                operating_detail.get("profit_coverage", 0.0),
                operating_detail.get("moat_coverage", 0.0),
                operating.get("coverage_ratio", 0.0),
                Json(operating_detail.get("data_status") or {}),
                Json(operating_detail.get("cap_hits") or []),
                Json(operating_detail),
                Json(evidence_ids),
            ),
        )

        benefit = bundle["benefit"]
        benefit_detail = dict(benefit.get("detail") or {})
        cur.execute(
            """
            INSERT INTO business_tag_benefit_scores (
                score_id,mapping_id,trade_date,model_version,node_attractiveness,
                operating_quality_score,revenue_exposure_score,
                order_certainty_score,profit_elasticity_score,
                delivery_capability_score,benefit_raw,authenticity_score,
                benefit_score,coverage_ratio,score_detail,evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mapping_id, trade_date, model_version) DO UPDATE SET
                node_attractiveness=EXCLUDED.node_attractiveness,
                operating_quality_score=EXCLUDED.operating_quality_score,
                revenue_exposure_score=EXCLUDED.revenue_exposure_score,
                order_certainty_score=EXCLUDED.order_certainty_score,
                profit_elasticity_score=EXCLUDED.profit_elasticity_score,
                delivery_capability_score=EXCLUDED.delivery_capability_score,
                benefit_raw=EXCLUDED.benefit_raw,
                authenticity_score=EXCLUDED.authenticity_score,
                benefit_score=EXCLUDED.benefit_score,
                coverage_ratio=EXCLUDED.coverage_ratio,
                score_detail=EXCLUDED.score_detail,
                evidence_ids=EXCLUDED.evidence_ids
            """,
            (
                self._record_id("BEN", mapping_id, trade_date, model_version),
                mapping_id,
                trade_date,
                model_version,
                benefit_detail.get("node_attractiveness"),
                benefit_detail.get("operating_quality_score"),
                benefit_detail.get("revenue_exposure_score"),
                benefit_detail.get("order_certainty_score"),
                benefit_detail.get("profit_elasticity_score"),
                benefit_detail.get("delivery_capability_score"),
                benefit_detail.get("benefit_raw"),
                benefit_detail.get("authenticity_score"),
                benefit.get("score"),
                benefit.get("coverage_ratio", 0.0),
                Json(benefit_detail),
                Json(evidence_ids),
            ),
        )

        selection = bundle["selection"]
        selection_detail = dict(selection.get("detail") or {})
        pool_gates = selection_detail.get("pool_gates")
        if "pool_gate" not in selection_detail and isinstance(pool_gates, dict):
            selection_detail["pool_gate"] = pool_gates.get("combined")
        selection_detail.setdefault(
            "blocking_gate",
            selection.get("blocking_gate"),
        )
        selection_detail.setdefault(
            "data_limitations",
            list(bundle.get("data_limitations") or []),
        )
        selection_detail.setdefault(
            "next_validation",
            {
                "event": bundle.get("next_validation_event"),
                # pool_state 读出的 date 对象不可 JSON 序列化，统一转 ISO 字符串
                "date": (
                    bundle["next_validation_date"].isoformat()
                    if hasattr(bundle.get("next_validation_date"), "isoformat")
                    else bundle.get("next_validation_date")
                ),
                "actions": [],
            },
        )
        cur.execute(
            """
            INSERT INTO business_tag_selection_scores (
                selection_id,mapping_id,trade_date,model_version,benefit_score,
                expectation_gap_score,catalyst_score,risk_score,confidence_score,
                opportunity_score,pool_code,eligibility_status,veto_reasons,
                factor_detail,evidence_ids
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (mapping_id, trade_date, model_version) DO UPDATE SET
                benefit_score=EXCLUDED.benefit_score,
                expectation_gap_score=EXCLUDED.expectation_gap_score,
                catalyst_score=EXCLUDED.catalyst_score,
                risk_score=EXCLUDED.risk_score,
                confidence_score=EXCLUDED.confidence_score,
                opportunity_score=EXCLUDED.opportunity_score,
                pool_code=EXCLUDED.pool_code,
                eligibility_status=EXCLUDED.eligibility_status,
                veto_reasons=EXCLUDED.veto_reasons,
                factor_detail=EXCLUDED.factor_detail,
                evidence_ids=EXCLUDED.evidence_ids
            """,
            (
                self._record_id("SEL", mapping_id, trade_date, model_version),
                mapping_id,
                trade_date,
                model_version,
                benefit.get("score"),
                selection_detail.get("expectation_gap_score"),
                selection_detail.get("catalyst_score"),
                selection_detail.get("risk_score"),
                selection.get("confidence_score"),
                selection.get("opportunity_score"),
                selection.get("pool_code"),
                selection.get("eligibility_status", "insufficient_evidence"),
                Json(selection.get("veto_reasons") or []),
                Json(selection_detail),
                Json(evidence_ids),
            ),
        )

    def transition_pool(self, cur, bundle: dict[str, Any]) -> bool:
        mapping_id = str(bundle["mapping_id"])
        new_pool = bundle["selection"].get("pool_code")
        cur.execute(
            "SELECT pool_code FROM business_tag_pool_state WHERE mapping_id = %s",
            (mapping_id,),
        )
        current = cur.fetchone()
        old_pool = (
            current.get("pool_code")
            if isinstance(current, dict)
            else (current[0] if current else None)
        )
        if old_pool == new_pool:
            return False

        trade_date = bundle["trade_date"]
        evidence_ids = list(bundle.get("evidence_ids") or [])
        transition_reason = f"computed_pool_change:{old_pool or 'OUT'}->{new_pool or 'OUT'}"
        cur.execute(
            """
            INSERT INTO business_tag_pool_transition_log (
                transition_id,mapping_id,code,from_pool_code,to_pool_code,
                transition_date,transition_reason,trigger_evidence_ids,
                review_status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (transition_id) DO NOTHING
            """,
            (
                self._record_id("POOL", mapping_id, trade_date, old_pool, new_pool),
                mapping_id,
                bundle["code"],
                old_pool,
                new_pool,
                trade_date,
                transition_reason,
                Json(evidence_ids),
                "pending_review",
            ),
        )
        if new_pool is None:
            cur.execute(
                "DELETE FROM business_tag_pool_state WHERE mapping_id = %s",
                (mapping_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO business_tag_pool_state (
                    mapping_id,code,pool_code,state_status,effective_from,
                    next_validation_event,next_validation_date,
                    source_selection_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (mapping_id) DO UPDATE SET
                    code=EXCLUDED.code,
                    pool_code=EXCLUDED.pool_code,
                    state_status=EXCLUDED.state_status,
                    effective_from=EXCLUDED.effective_from,
                    next_validation_event=EXCLUDED.next_validation_event,
                    next_validation_date=EXCLUDED.next_validation_date,
                    source_selection_id=EXCLUDED.source_selection_id,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    mapping_id,
                    bundle["code"],
                    new_pool,
                    "pending_review",
                    trade_date,
                    bundle.get("next_validation_event"),
                    bundle.get("next_validation_date"),
                    self._record_id(
                        "SEL",
                        mapping_id,
                        trade_date,
                        bundle.get("model_version", "v2.0"),
                    ),
                ),
            )
        return True
