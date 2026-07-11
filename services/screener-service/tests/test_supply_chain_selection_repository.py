"""SQL boundary contracts for supply-chain selection V2."""

from datetime import datetime, timezone
from datetime import date

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


def test_fetch_asof_evidence_uses_publish_time_cutoff_and_approved_events():
    cutoff = datetime(2026, 7, 11, 15, tzinfo=timezone.utc)
    cursor = FakeCursor(
        [
            [
                {
                    "event_id": "fact-1",
                    "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc),
                    "fact_type": "order_award",
                    "fact_nature": "confirmed_fact",
                    "validation_status": "confirmed",
                    "source_level": "strong",
                    "confidence": 0.9,
                    "metadata": {},
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
                }
            ],
        ]
    )
    repository = SelectionRepository(connection_factory=lambda: None)

    rows = repository.fetch_asof_evidence(cursor, "m1", cutoff)

    assert [row["event_id"] for row in rows] == ["event-1", "fact-1"]
    assert len(cursor.executed) == 2
    assert cursor.executed[0][1] == ("m1", cutoff)
    assert cursor.executed[1][1] == ("m1", cutoff.date())
    assert "publish_time" in cursor.executed[0][0]
    assert "review_status = 'approved'" in cursor.executed[1][0]


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
