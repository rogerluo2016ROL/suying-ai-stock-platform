"""SQL boundary contracts for supply-chain selection V2."""

from datetime import datetime, timedelta, timezone
from datetime import date
from zoneinfo import ZoneInfo

import pytest

from app.domains.supply_chain.selection_repository import SelectionRepository


class FakeCursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self._current = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._current = self.responses.pop(0) if self.responses else []

    def fetchall(self):
        return self._current

    def fetchone(self):
        return self._current[0] if self._current else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self, **kwargs):
        return self._cursor

    def close(self):
        self.closed = True


class DispatchCursor:
    """Route responses by explicit query contract markers, not call order."""

    def __init__(self, responses):
        self.responses = dict(responses)
        self.executed = []
        self._current = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        marker = next((key for key in self.responses if key in sql), None)
        self._current = list(self.responses.get(marker, []))

    def fetchall(self):
        return self._current

    def fetchone(self):
        return self._current[0] if self._current else None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def adjusted_price_rows(*, end_close=112.5, code="003021.SZ"):
    end = date(2026, 7, 9)
    rows = []
    for offset in range(21):
        rows.append(
            {
                "code": code,
                "trade_date": end - timedelta(days=offset),
                "close": end_close if offset == 0 else 100.0,
                "adj_factor": 1.0,
            }
        )
    return rows


def reviewed_context_responses(**overrides):
    responses = {
        "selection_context:adjusted_price": adjusted_price_rows(),
        "selection_context:stage": [
            {
                "research_stage": "R6",
                "commercialization_stage": "C7",
                "source_event_id": "stage-event",
            }
        ],
        "selection_context:evidence_delta": [
            {
                "evidence_id": "delta-fact",
                "normalization": {
                    "method_version": "review-v1",
                    "as_of_date": "2026-07-09",
                    "evidence_delta_score": 40,
                },
            }
        ],
        "selection_context:expectation": [
            {
                "evidence_id": "market-monitor",
                "gap_status": "fulfilled",
                "market_price_change": 12.5,
                "normalization": {
                    "method_version": "review-v1",
                    "as_of_date": "2026-07-09",
                    "market_expectation_score": 50,
                },
            },
            {
                "evidence_id": "claim-monitor",
                "gap_status": "missed",
                "market_price_change": None,
                "trigger_fact_id": "claim-trigger",
                "normalization": {
                    "method_version": "review-v1",
                    "as_of_date": "2026-07-09",
                    "claim_risk_penalty_score": 20,
                },
            },
        ],
        "selection_context:catalyst": [
            {
                "evidence_id": "catalyst-monitor",
                "score": 80,
                "source_level": "strong",
                "confidence": 0.9,
                "source_reliability": 0.8,
                "normalization": {
                    "method_version": "review-v1",
                    "as_of_date": "2026-07-09",
                    "catalyst_score": 80,
                },
            }
        ],
        "selection_context:risk": [
            {
                "evidence_id": "risk-fact",
                "score": 70,
                "source_level": "mid",
                "confidence": 0.8,
                "source_reliability": 0.7,
                "normalization": {
                    "method_version": "review-v1",
                    "as_of_date": "2026-07-09",
                    "risk_score": 70,
                },
            }
        ],
    }
    responses.update(overrides)
    return responses


def test_selection_context_requires_review_audit_adjusted_prices_and_cutoffs():
    cursor = DispatchCursor(reviewed_context_responses())
    repository = SelectionRepository(connection_factory=lambda: None)
    cutoff = datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc)

    result = repository.fetch_selection_context(
        cursor,
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=cutoff,
    )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "review_status = 'approved'" in sql
    assert "validation_status = 'confirmed'" in sql
    assert "reviewer IS NOT NULL" in sql
    assert "NULLIF(BTRIM" in sql
    assert "review_note" in sql
    assert "reviewed_at" in sql
    assert "created_at" in sql
    assert "AT TIME ZONE 'Asia/Shanghai'" in sql
    assert "adj_factor" in sql
    assert "trigger_fact_id" in sql
    assert "expected_date > %s" in sql
    assert "claim_trigger_fact_ids" in sql
    assert "trigger_doc" in sql
    assert "trigger_event" in sql
    assert "source.enabled IS TRUE" in sql
    assert "monitor.claim_date <= %s" in sql
    assert "veto_reason" in sql
    assert "application_domain" not in sql
    risk_call = next(
        call for call in cursor.executed if "selection_context:risk" in call[0]
    )
    assert ["claim-trigger"] in risk_call[1]
    assert result["adjusted_price_reaction"] == 0.125
    assert result["actual_progress_score"] == 79.0
    assert result["market_expectation_score"] == 50.0
    assert result["evidence_delta_score"] == 40.0
    assert result["claim_risk_penalty_score"] == 20.0
    assert result["expectation_gap_score"] == 34.0
    assert result["catalyst_score"] == 80.0
    assert result["risk_score"] == 70.0
    assert result["selection_context_evidence_ids"] == [
        "catalyst-monitor",
        "claim-monitor",
        "delta-fact",
        "market-monitor",
        "risk-fact",
        "stage-event",
    ]
    assert result["selection_context_limitations"] == []


def test_selection_context_conflicting_normalizations_fail_closed():
    responses = reviewed_context_responses(
        **{
            "selection_context:evidence_delta": [
                {
                    "evidence_id": "delta-a",
                    "normalization": {
                        "method_version": "review-v1",
                        "as_of_date": "2026-07-09",
                        "evidence_delta_score": 40,
                    },
                },
                {
                    "evidence_id": "delta-b",
                    "normalization": {
                        "method_version": "review-v1",
                        "as_of_date": "2026-07-09",
                        "evidence_delta_score": 41,
                    },
                },
            ]
        }
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository.fetch_selection_context(
        DispatchCursor(responses),
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc),
    )

    assert result["evidence_delta_score"] is None
    assert result["actual_progress_score"] is None
    assert result["expectation_gap_score"] is None
    assert "ambiguous_evidence_delta_score" in result["selection_context_limitations"]


def test_ambiguous_claim_penalty_does_not_suppress_trigger_fact_from_risk():
    responses = reviewed_context_responses()
    claim = responses["selection_context:expectation"][1]
    responses["selection_context:expectation"].append(
        {
            **claim,
            "evidence_id": "claim-monitor-2",
            "normalization": {
                **claim["normalization"],
                "claim_risk_penalty_score": 21,
            },
        }
    )
    cursor = DispatchCursor(responses)
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository.fetch_selection_context(
        cursor,
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc),
    )

    risk_call = next(
        call for call in cursor.executed if "selection_context:risk" in call[0]
    )
    assert risk_call[1][0] == []
    assert result["claim_risk_penalty_score"] is None
    assert "ambiguous_claim_risk_penalty_score" in result[
        "selection_context_limitations"
    ]


def test_market_expectation_requires_fresh_decimal_to_stored_percent_match():
    responses = reviewed_context_responses()
    responses["selection_context:expectation"][0]["market_price_change"] = 0.125
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository.fetch_selection_context(
        DispatchCursor(responses),
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc),
    )

    assert result["adjusted_price_reaction"] == 0.125
    assert result["market_expectation_score"] is None
    assert result["expectation_gap_score"] is None
    assert "market_price_reaction_mismatch" in result["selection_context_limitations"]


def test_adjusted_price_query_prefers_exact_suffix_but_accepts_unique_plain_code():
    rows = adjusted_price_rows(code="003021")
    cursor = DispatchCursor({"selection_context:adjusted_price": rows})
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository._fetch_adjusted_price_reaction(
        cursor,
        code="003021.SZ",
        trade_date=date(2026, 7, 9),
    )

    sql = cursor.executed[0][0]
    assert result == 0.125
    assert "requested_code" in sql
    assert "code = requested_code" in sql
    assert "code = plain_code" in sql


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[1:].copy(),
        lambda rows: rows[:20],
        lambda rows: [
            {**row, "adj_factor": None if index == 10 else row["adj_factor"]}
            for index, row in enumerate(rows)
        ],
        lambda rows: [
            {**row, "code": "003021.SH" if index == 10 else row["code"]}
            for index, row in enumerate(rows)
        ],
        lambda rows: [
            {**row, "close": float("nan") if index == 10 else row["close"]}
            for index, row in enumerate(rows)
        ],
    ],
    ids=["missing-score-date", "short-window", "missing-factor", "mixed-code", "nan"],
)
def test_adjusted_price_reaction_requires_exact_date_complete_window_and_one_code(
    mutate,
):
    rows = mutate(adjusted_price_rows())
    cursor = DispatchCursor({"selection_context:adjusted_price": rows})
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository._fetch_adjusted_price_reaction(
        cursor,
        code="003021",
        trade_date=date(2026, 7, 9),
    )

    assert result is None


def test_context_rejects_future_or_invalid_normalization_without_defaults():
    responses = reviewed_context_responses()
    responses["selection_context:catalyst"][0]["normalization"] = {
        "as_of_date": "2026-07-10",
        "catalyst_score": 80,
    }
    responses["selection_context:risk"][0]["normalization"]["risk_score"] = float(
        "inf"
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    result = repository.fetch_selection_context(
        DispatchCursor(responses),
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc),
    )

    assert result["catalyst_score"] is None
    assert result["risk_score"] is None
    assert "missing_catalyst_score" in result["selection_context_limitations"]
    assert "missing_risk_score" in result["selection_context_limitations"]


def test_stock_explanation_rows_are_allowlisted_reviewed_and_asof():
    required = [{"table_name": name} for name in SelectionRepository.REQUIRED_TABLES]
    cursor = DispatchCursor(
        {
            "information_schema.tables": required,
            "selection_explanation:facts": [
                {
                    "mapping_id": "m1",
                    "evidence_id": "f-approved",
                    "kind": "fact",
                    "record_status": "confirmed",
                    "fact_type": "order_award",
                    "source_level": "strong",
                    "publish_time": datetime(2026, 7, 8, 9),
                    "reviewed_at": datetime(2026, 7, 8, 10, tzinfo=timezone.utc),
                },
                {
                    "mapping_id": "m1",
                    "evidence_id": "f-pending",
                    "kind": "fact",
                    "record_status": "pending",
                    "fact_type": "customer_validation",
                    "source_level": "mid",
                    "publish_time": datetime(2026, 7, 8, 11),
                    "reviewed_at": None,
                },
                {
                    "mapping_id": "m1",
                    "evidence_id": "f-rejected",
                    "kind": "fact",
                    "record_status": "rejected",
                    "fact_type": "order_award",
                    "source_level": "weak",
                    "publish_time": datetime(2026, 7, 8, 12),
                    "reviewed_at": datetime(2026, 7, 8, 16, tzinfo=timezone.utc),
                },
                {
                    "mapping_id": "m1",
                    "evidence_id": "f-future-rejected",
                    "kind": "fact",
                    "record_status": "rejected",
                    "fact_type": "order_award",
                    "source_level": "weak",
                    "publish_time": datetime(2026, 7, 8, 12),
                    "reviewed_at": datetime(2026, 7, 10, 1, tzinfo=timezone.utc),
                },
            ],
            "selection_explanation:events": [
                {
                    "mapping_id": "m1",
                    "evidence_id": "event-1",
                    "kind": "event",
                    "record_status": "approved",
                    "fact_type": "customer_validation",
                    "source_level": "mid",
                    "publish_time": date(2026, 7, 8),
                    "reviewed_at": datetime(2026, 7, 8, 13, tzinfo=timezone.utc),
                }
            ],
            "selection_explanation:monitors": [
                {
                    "mapping_id": "m1",
                    "evidence_id": "monitor-1",
                    "kind": "monitor",
                    "record_status": "approved",
                    "fact_type": "expectation_monitor",
                    "source_level": "strong",
                    "publish_time": datetime(2026, 7, 8, 14),
                    "reviewed_at": datetime(2026, 7, 8, 15, tzinfo=timezone.utc),
                }
            ],
        }
    )
    connection = FakeConnection(cursor)
    repository = SelectionRepository(connection_factory=lambda: connection)

    result = repository.fetch_stock_explanation_rows(
        code="003021",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
    )

    explanation = result["m1"]
    assert [item["evidence_id"] for item in explanation["approved_evidence"]] == [
        "event-1",
        "f-approved",
        "monitor-1",
    ]
    assert explanation["pending_facts"] == [
        {
            "fact_id": "f-pending",
            "status": "pending",
            "fact_type": "customer_validation",
            "source_level": "mid",
            "publish_time": datetime(2026, 7, 8, 11),
        }
    ]
    assert [item["fact_id"] for item in explanation["rejected_facts"]] == [
        "f-rejected"
    ]
    assert explanation["rejected_facts"][0]["reviewed_at"] == datetime(
        2026, 7, 8, 16, tzinfo=timezone.utc
    )
    assert connection.closed is True
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "content_text" not in sql
    assert "metadata" not in sql
    assert "review_note AS" not in sql
    assert "AT TIME ZONE 'Asia/Shanghai'" in sql
    assert "created_at AT TIME ZONE 'UTC'" in sql
    assert "reviewed_at <= %s" in sql
    assert "f.validation_status IN ('confirmed', 'rejected', 'contradicted')" in sql


def test_preflight_returns_every_missing_required_table():
    cursor = FakeCursor(
        [[{"table_name": "business_tag_mapping"}, {"table_name": "evidence_extracted_facts"}]]
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    missing = repository.preflight(cursor)

    assert "business_tag_mapping" not in missing
    assert "evidence_extracted_facts" not in missing
    assert "business_tag_selection_scores" in missing
    assert "business_tag_pool_state" in missing
    assert "business_tag_expectation_monitor" in missing
    assert "evidence_source_catalog" in missing
    assert "daily_kline" in missing
    assert "adj_factor" in missing


def test_fetch_asof_evidence_preserves_each_fact_linked_to_the_same_event():
    cutoff = datetime(2026, 7, 11, 15, tzinfo=timezone.utc)
    reviewed_at = datetime(2026, 7, 10, 10, tzinfo=timezone.utc)
    created_at = datetime(2026, 7, 9, 10, tzinfo=timezone.utc)
    cursor = FakeCursor(
        [
            [
                {
                    "fact_id": fact_id,
                    "event_id": "shared-event",
                    "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc),
                    "fact_type": fact_type,
                    "fact_nature": "confirmed_fact",
                    "validation_status": "confirmed",
                    "source_level": "strong",
                    "confidence": 0.9,
                    "metadata": {},
                    "reviewer": "reviewer-1",
                    "review_note": "checked against source",
                    "reviewed_at": reviewed_at,
                    "created_at": created_at,
                }
                for fact_id, fact_type in (
                    ("fact-1", "order_award"),
                    ("fact-2", "capacity_mass_production"),
                )
            ],
            [
                {
                    "event_id": "shared-event",
                    "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc),
                    "fact_type": "order_award",
                    "fact_nature": "confirmed_fact",
                    "validation_status": "confirmed",
                    "source_level": "strong",
                    "confidence": 0.9,
                    "metadata": {},
                    "reviewer": "reviewer-1",
                    "review_note": "checked against source",
                    "reviewed_at": reviewed_at,
                    "created_at": created_at,
                }
            ],
        ]
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    rows = repository.fetch_asof_evidence(cursor, "m1", cutoff)

    assert [row.get("fact_id") for row in rows] == ["fact-1", "fact-2"]
    assert all(row["event_id"] == "shared-event" for row in rows)


def test_fetch_asof_evidence_requires_complete_reviews_before_cutoff():
    cutoff = datetime(2026, 7, 11, 15, tzinfo=timezone.utc)
    publish_cutoff = cutoff.astimezone(ZoneInfo("Asia/Shanghai")).replace(
        tzinfo=None
    )
    audit_cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None)
    reviewed_at = datetime(2026, 7, 10, 10, tzinfo=timezone.utc)
    created_at = datetime(2026, 7, 9, 10, tzinfo=timezone.utc)
    cursor = FakeCursor(
        [
            [
                {
                    "fact_id": "fact-1",
                    "event_id": None,
                    "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc),
                    "fact_type": "order_award",
                    "fact_nature": "confirmed_fact",
                    "validation_status": "confirmed",
                    "source_level": "strong",
                    "confidence": 0.9,
                    "metadata": {},
                    "reviewer": "reviewer-1",
                    "review_note": "checked against source",
                    "reviewed_at": reviewed_at,
                    "created_at": created_at,
                }
            ],
            [
                {
                    "event_id": "event-1",
                    "publish_time": datetime(2026, 7, 9, tzinfo=timezone.utc),
                    "fact_type": "customer_validation",
                    "fact_nature": "confirmed_fact",
                    "validation_status": "confirmed",
                    "source_level": "mid",
                    "confidence": 0.8,
                    "metadata": {},
                    "reviewer": "reviewer-2",
                    "review_note": "approved event",
                    "reviewed_at": reviewed_at,
                    "created_at": created_at,
                }
            ],
        ]
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    rows = repository.fetch_asof_evidence(cursor, "m1", cutoff)

    assert [row.get("fact_id") or row.get("event_id") for row in rows] == [
        "event-1",
        "fact-1",
    ]
    assert len(cursor.executed) == 2
    facts_sql = " ".join(cursor.executed[0][0].split())
    events_sql = " ".join(cursor.executed[1][0].split())
    assert cursor.executed[0][1] == (
        "m1",
        publish_cutoff,
        cutoff,
        audit_cutoff,
    )
    assert cursor.executed[1][1] == (
        "m1",
        publish_cutoff.date(),
        cutoff,
        audit_cutoff,
    )
    assert "f.fact_id" in facts_sql
    assert "f.evidence_event_id AS event_id" in facts_sql
    assert "coalesce(d.publish_time, e.event_date::timestamp) <= %s" in facts_sql
    assert "AT TIME ZONE" not in facts_sql
    assert "f.validation_status = 'confirmed'" in facts_sql
    assert "f.fact_nature = 'confirmed_fact'" not in facts_sql
    assert "f.reviewer IS NOT NULL" in facts_sql
    assert "NULLIF(BTRIM(f.reviewer), '') IS NOT NULL" in facts_sql
    assert "f.review_note IS NOT NULL" in facts_sql
    assert "NULLIF(BTRIM(f.review_note), '') IS NOT NULL" in facts_sql
    assert "f.reviewed_at IS NOT NULL" in facts_sql
    assert "f.reviewed_at <= %s" in facts_sql
    assert "f.created_at IS NOT NULL" in facts_sql
    assert "f.created_at <= %s" in facts_sql
    assert "e.review_status = 'approved'" in events_sql
    assert "e.reviewer IS NOT NULL" in events_sql
    assert "NULLIF(BTRIM(e.reviewer), '') IS NOT NULL" in events_sql
    assert "e.review_note IS NOT NULL" in events_sql
    assert "NULLIF(BTRIM(e.review_note), '') IS NOT NULL" in events_sql
    assert "e.reviewed_at IS NOT NULL" in events_sql
    assert "e.reviewed_at <= %s" in events_sql
    assert "e.created_at IS NOT NULL" in events_sql
    assert "e.created_at <= %s" in events_sql
    assert "NOT EXISTS" in events_sql
    assert "linked_fact.evidence_event_id = e.event_id" in events_sql
    assert (
        "linked_fact.mapping_id IS NOT DISTINCT FROM e.mapping_id"
        in events_sql
    )
    assert rows[0]["reviewer"] == "reviewer-2"
    assert rows[0]["review_note"] == "approved event"
    assert rows[0]["reviewed_at"] == reviewed_at
    assert rows[0]["created_at"] == created_at


def test_fetch_mappings_reads_latest_asof_stage_without_future_rows():
    cursor = FakeCursor(
        [[{"mapping_id": "m1", "code": "000001", "commercial_stage": "C3"}]]
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    rows = repository.fetch_mappings(
        cursor,
        chain_id="dexterous_hand",
        mapping_ids=None,
        trade_date=date(2026, 7, 11),
    )

    assert rows[0]["mapping_id"] == "m1"
    sql, params = cursor.executed[0]
    assert "st.trade_date <= %s" in sql
    assert "st.review_status AS stage_review_status" in sql
    assert "st.created_at AS stage_created_at" in sql
    assert "source_event_review_status" in sql
    assert "source_event_reviewer" in sql
    assert "source_event_review_note" in sql
    assert "source_event_reviewed_at" in sql
    assert "source_event_date" in sql
    assert "source_event_created_at" in sql
    assert "source_event.mapping_id = b.mapping_id" in sql
    assert "ps.effective_from <= %s" in sql
    assert "ps.created_at <= %s" in sql
    assert "ps.updated_at <= %s" in sql
    assert "b.status <> 'rejected'" in sql
    audit_cutoff = datetime(2026, 7, 11, 15, 59, 59, 999999)
    assert params == (
        date(2026, 7, 11),
        date(2026, 7, 11),
        audit_cutoff,
        audit_cutoff,
        "dexterous_hand",
    )


def test_fetch_node_score_is_versioned_and_asof():
    cursor = FakeCursor([[{"total_score": 72.5}]])
    repository = SelectionRepository(connection_factory=lambda: None)

    row = repository.fetch_node_score(
        cursor,
        node_id="dexterous_hand_foundation",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
    )

    assert row == {"total_score": 72.5}
    assert cursor.executed[0][1] == (
        "dexterous_hand_foundation",
        date(2026, 7, 11),
        "v2.0",
    )


def test_upsert_score_bundle_writes_four_versioned_score_tables():
    cursor = FakeCursor([[], [], [], []])
    repository = SelectionRepository(connection_factory=lambda: None)
    bundle = {
        "mapping_id": "m1",
        "code": "000001",
        "trade_date": date(2026, 7, 11),
        "model_version": "v2.0",
        "authenticity": {
            "score": 80.0,
            "coverage_ratio": 0.8,
            "detail": {},
            "evidence_level": "E4",
            "max_pool_code": "A",
        },
        "operating_quality": {
            "score": None,
            "coverage_ratio": 0.0,
            "detail": {
                "growth_score": None,
                "growth_coverage": 0.0,
                "profit_score": None,
                "profit_coverage": 0.0,
                "moat_score": None,
                "moat_coverage": 0.0,
                "cap_hits": [],
            },
        },
        "benefit": {
            "score": 60.0,
            "coverage_ratio": 0.35,
            "detail": {"benefit_raw": 75.0},
        },
        "selection": {
            "score": None,
            "coverage_ratio": 0.25,
            "detail": {"status": "insufficient_evidence"},
            "opportunity_score": None,
            "confidence_score": 75.0,
            "pool_code": "C",
            "eligibility_status": "eligible",
            "veto_reasons": [],
        },
        "evidence_ids": ["ev1"],
    }

    repository.upsert_score_bundle(cursor, bundle)

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "INSERT INTO business_tag_authenticity_scores" in sql
    assert "INSERT INTO business_tag_operating_quality_scores" in sql
    assert "INSERT INTO business_tag_benefit_scores" in sql
    assert "INSERT INTO business_tag_selection_scores" in sql
    assert sql.count("ON CONFLICT (mapping_id, trade_date, model_version)") == 4


def test_transition_pool_writes_log_only_when_pool_changes():
    cursor = FakeCursor([[{"pool_code": "C"}], [], []])
    repository = SelectionRepository(connection_factory=lambda: None)
    bundle = {
        "mapping_id": "m1",
        "code": "000001",
        "trade_date": date(2026, 7, 11),
        "selection": {"pool_code": "B"},
        "evidence_ids": ["ev1"],
    }

    changed = repository.transition_pool(cursor, bundle)

    assert changed is True
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "INSERT INTO business_tag_pool_transition_log" in sql
    assert "INSERT INTO business_tag_pool_state" in sql


def test_transition_pool_skips_log_when_pool_is_unchanged():
    cursor = FakeCursor([[{"pool_code": "B"}]])
    repository = SelectionRepository(connection_factory=lambda: None)

    changed = repository.transition_pool(
        cursor,
        {
            "mapping_id": "m1",
            "code": "000001",
            "trade_date": date(2026, 7, 11),
            "selection": {"pool_code": "B"},
            "evidence_ids": [],
        },
    )

    assert changed is False
    assert len(cursor.executed) == 1


def test_fetch_candidate_rows_applies_asof_version_pool_and_stock_pagination():
    required = [{"table_name": name} for name in SelectionRepository.REQUIRED_TABLES]
    cursor = FakeCursor(
        [
            required,
            [
                {
                    "code": "000001",
                    "mapping_id": "m1",
                    "pool_code": "A",
                    "benefit_score": 72.0,
                }
            ],
        ]
    )
    connection = FakeConnection(cursor)
    repository = SelectionRepository(connection_factory=lambda: connection)

    rows = repository.fetch_candidate_rows(
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        pool="A",
        model_version="v2.0",
        limit=50,
        offset=0,
    )

    assert rows[0]["mapping_id"] == "m1"
    sql, params = cursor.executed[1]
    cutoff = datetime.combine(
        date(2026, 7, 11),
        datetime.max.time(),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    ).astimezone(timezone.utc)
    assert "s.trade_date = %s" in sql
    assert "s.model_version = %s" in sql
    assert "stage_tracker.created_at AT TIME ZONE 'UTC'" in sql
    assert "stage.review_status = 'approved'" in sql
    assert "JOIN business_tag_evidence_events source_event" in sql
    assert "source_event.mapping_id = stage.mapping_id" in sql
    assert "source_event.review_status = 'approved'" in sql
    assert "NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL" in sql
    assert "NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL" in sql
    assert "source_event.reviewed_at <= %s" in sql
    assert "AND pool_code = %s" in sql
    assert "GROUP BY code" in sql
    assert params == (
        cutoff,
        cutoff,
        cutoff,
        "dexterous_hand",
        date(2026, 7, 11),
        "v2.0",
        "A",
        50,
        0,
    )
    assert connection.closed is True


def test_fetch_stock_detail_and_transitions_are_cut_off_by_trade_date():
    required = [{"table_name": name} for name in SelectionRepository.REQUIRED_TABLES]
    cursor = FakeCursor(
        [
            required,
            [{"code": "000001", "mapping_id": "m1", "pool_code": "B"}],
            required,
            [{"transition_id": "t1", "transition_date": date(2026, 7, 10)}],
        ]
    )
    connection = FakeConnection(cursor)
    repository = SelectionRepository(connection_factory=lambda: connection)

    rows = repository.fetch_stock_detail_rows(
        code="000001",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
    )
    transitions = repository.fetch_transition_rows(
        code="000001",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
    )

    assert rows[0]["mapping_id"] == "m1"
    assert transitions[0]["transition_id"] == "t1"
    detail_sql, detail_params = cursor.executed[1]
    transition_sql, transition_params = cursor.executed[3]
    cutoff = datetime.combine(
        date(2026, 7, 11),
        datetime.max.time(),
        tzinfo=ZoneInfo("Asia/Shanghai"),
    ).astimezone(timezone.utc)
    assert "b.code = %s" in detail_sql
    assert "stage_tracker.created_at AT TIME ZONE 'UTC'" in detail_sql
    assert "stage.review_status = 'approved'" in detail_sql
    assert "JOIN business_tag_evidence_events source_event" in detail_sql
    assert "source_event.mapping_id = stage.mapping_id" in detail_sql
    assert "source_event.review_status = 'approved'" in detail_sql
    assert "NULLIF(BTRIM(source_event.reviewer), '') IS NOT NULL" in detail_sql
    assert "NULLIF(BTRIM(source_event.review_note), '') IS NOT NULL" in detail_sql
    assert "source_event.reviewed_at <= %s" in detail_sql
    assert detail_params == (
        date(2026, 7, 11),
        cutoff,
        cutoff,
        date(2026, 7, 11),
        cutoff,
        "000001",
        "dexterous_hand",
        date(2026, 7, 11),
        "v2.0",
    )
    assert "t.transition_date <= %s" in transition_sql
    assert "t.created_at AT TIME ZONE 'UTC'" in transition_sql
    assert transition_params == (
        "000001",
        "dexterous_hand",
        date(2026, 7, 11),
        cutoff,
    )
