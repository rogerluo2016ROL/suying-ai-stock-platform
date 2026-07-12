"""SQL boundary contracts for supply-chain selection V2."""

from datetime import datetime, timezone
from datetime import date
from zoneinfo import ZoneInfo

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
    assert "f.fact_nature = 'confirmed_fact'" in facts_sql
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
    assert "b.status <> 'rejected'" in sql
    assert params == (date(2026, 7, 11), "dexterous_hand")


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
    assert "s.trade_date = %s" in sql
    assert "s.model_version = %s" in sql
    assert "AND pool_code = %s" in sql
    assert "GROUP BY code" in sql
    assert params == (
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
    assert "b.code = %s" in detail_sql
    assert detail_params == (
        date(2026, 7, 11),
        "000001",
        "dexterous_hand",
        date(2026, 7, 11),
        "v2.0",
    )
    assert "t.transition_date <= %s" in transition_sql
    assert transition_params == (
        "000001",
        "dexterous_hand",
        date(2026, 7, 11),
    )
