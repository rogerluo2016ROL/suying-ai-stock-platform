"""PostgreSQL boundary for supply-chain selection V2."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any, Callable

from psycopg2.extras import Json


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
        "business_tag_stage_tracking",
        "business_tag_evidence_freshness",
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
        cur.execute(
            """
            SELECT
                coalesce(f.evidence_event_id, f.fact_id) AS event_id,
                coalesce(d.publish_time, e.event_date::timestamp) AS publish_time,
                f.fact_type,
                f.fact_nature,
                f.validation_status,
                f.source_level,
                f.confidence,
                f.metadata
            FROM evidence_extracted_facts f
            LEFT JOIN raw_evidence_documents d ON d.doc_id = f.doc_id
            LEFT JOIN business_tag_evidence_events e
              ON e.event_id = f.evidence_event_id
            WHERE f.mapping_id = %s
              AND coalesce(d.publish_time, e.event_date::timestamp) <= %s
            ORDER BY publish_time, event_id
            """,
            (mapping_id, cutoff),
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
                jsonb_build_object('source_type', e.source_type) AS metadata
            FROM business_tag_evidence_events e
            WHERE e.mapping_id = %s
              AND e.review_status = 'approved'
              AND e.event_date <= %s
            ORDER BY publish_time, event_id
            """,
            (mapping_id, cutoff.date()),
        )
        approved_events = [dict(row) for row in cur.fetchall()]

        deduplicated = {
            str(row["event_id"]): row
            for row in facts + approved_events
            if row.get("event_id")
        }
        return sorted(
            deduplicated.values(),
            key=lambda row: (
                row.get("publish_time") or datetime.min,
                str(row.get("event_id") or ""),
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
        params: list[Any] = [trade_date, chain_id]
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
                ps.next_validation_event,
                ps.next_validation_date
            FROM business_tag_mapping b
            LEFT JOIN LATERAL (
                SELECT research_stage, commercialization_stage
                FROM business_tag_stage_tracking st
                WHERE st.mapping_id = b.mapping_id
                  AND st.trade_date <= %s
                ORDER BY st.trade_date DESC, st.created_at DESC
                LIMIT 1
            ) st ON TRUE
            LEFT JOIN business_tag_pool_state ps ON ps.mapping_id = b.mapping_id
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
