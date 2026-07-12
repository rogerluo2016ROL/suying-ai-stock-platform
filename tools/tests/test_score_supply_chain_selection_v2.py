"""As-of and evidence-gate contracts for supply-chain selection V2 scoring."""

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "score_supply_chain_selection_v2.py"
SPEC = importlib.util.spec_from_file_location(
    "score_supply_chain_selection_v2",
    SCRIPT_PATH,
)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def base_mapping(**overrides):
    mapping = {
        "mapping_id": "m1",
        "code": "000001",
        "node_id": "dexterous_hand_foundation",
        "tag_name": "空心杯电机",
        "status": "candidate",
        "confidence": 0.35,
        "commercial_stage": "C1",
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "next_validation_event": None,
        "next_validation_date": None,
    }
    mapping.update(overrides)
    return mapping


def evidence(event_id, publish_time, fact_type, **overrides):
    row = {
        "event_id": event_id,
        "publish_time": publish_time,
        "fact_type": fact_type,
        "fact_nature": "confirmed_fact",
        "validation_status": "confirmed",
        "source_level": "strong",
        "confidence": 0.9,
        "metadata": {},
        "reviewer": "reviewer-1",
        "review_note": "checked against source",
        "reviewed_at": datetime(2026, 7, 10, 10, tzinfo=timezone.utc),
        "created_at": datetime(2026, 7, 9, 10, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


def test_score_mapping_ignores_evidence_after_trade_date():
    mapping = base_mapping(commercial_stage="C4")
    rows = [
        evidence(
            "old",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
        ),
        evidence(
            "future",
            datetime(2026, 7, 12, 9, tzinfo=timezone.utc),
            "revenue_margin",
            metadata={"revenue_confirmed": True},
        ),
    ]

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert "old" in result["evidence_ids"]
    assert "future" not in result["evidence_ids"]
    assert result["authenticity"]["evidence_level"] == "E4"


def test_score_mapping_never_promotes_pending_review_evidence():
    rows = [
        evidence(
            "pending",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_nature="media_report",
            validation_status="pending",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] == "D"
    assert result["evidence_ids"] == []


def test_score_mapping_rejects_approved_as_a_fact_validation_status():
    rows = [
        evidence(
            "approved",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            validation_status="approved",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["evidence_ids"] == []


def test_confirmed_evidence_keeps_the_confirmed_fact_nature_boundary():
    row = evidence(
        "company-claim",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "prototype_delivery",
        fact_nature="company_claim",
        validation_status="confirmed",
    )

    confirmed, limitations = module._confirmed_evidence(
        [row],
        cutoff=module._cutoff_utc(date(2026, 7, 11)),
    )

    assert confirmed == []
    assert limitations == []


def test_score_mapping_uses_fact_id_as_the_persisted_evidence_id():
    row = evidence(
        "shared-event",
        datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
        "order_award",
        fact_id="fact-1",
    )

    result = module.score_mapping(
        base_mapping(),
        [row],
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["evidence_ids"] == ["fact-1"]


def test_score_mapping_preserves_multiple_fact_ids_from_one_event():
    rows = [
        evidence(
            "shared-event",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            fact_type,
            fact_id=fact_id,
        )
        for fact_id, fact_type in (
            ("fact-1", "order_award"),
            ("fact-2", "capacity_mass_production"),
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["evidence_ids"] == ["fact-1", "fact-2"]


@pytest.mark.parametrize(
    "validation_status,audit_overrides",
    [
        ("confirmed", {"reviewer": None}),
        ("confirmed", {"reviewer": "   "}),
        ("confirmed", {"review_note": None}),
        ("confirmed", {"review_note": "   "}),
        ("confirmed", {"reviewed_at": None}),
        ("confirmed", {"reviewed_at": "not-a-timestamp"}),
        ("confirmed", {"reviewed_at": datetime(2026, 7, 10, 10)}),
        (
            "confirmed",
            {"reviewed_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        ),
        ("confirmed", {"created_at": None}),
        ("confirmed", {"created_at": "not-a-timestamp"}),
        ("confirmed", {"created_at": datetime(2026, 7, 11, 16)}),
        (
            "confirmed",
            {"created_at": datetime(2026, 7, 12, 9, tzinfo=timezone.utc)},
        ),
    ],
    ids=[
        "confirmed-missing-reviewer",
        "confirmed-blank-reviewer",
        "confirmed-missing-note",
        "confirmed-blank-note",
        "confirmed-missing-reviewed-at",
        "confirmed-invalid-reviewed-at",
        "confirmed-naive-reviewed-at",
        "confirmed-future-reviewed-at",
        "confirmed-missing-created-at",
        "confirmed-invalid-created-at",
        "confirmed-future-naive-utc-created-at",
        "confirmed-future-created-at",
    ],
)
def test_score_mapping_rejects_evidence_without_a_safe_audit_trail(
    validation_status,
    audit_overrides,
):
    rows = [
        evidence(
            "unsafe",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "order_award",
            fact_id="fact-unsafe",
            validation_status=validation_status,
            **audit_overrides,
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["evidence_ids"] == []
    assert any(
        "fact-unsafe" in limitation
        for limitation in result["data_limitations"]
    )


def test_confirmed_prototype_can_reach_c_but_not_customer_pool():
    rows = [
        evidence(
            "prototype",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E2"
    assert result["selection"]["pool_code"] == "C"


def test_confirmed_customer_validation_needs_next_event_for_b_pool():
    rows = [
        evidence(
            "customer",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "customer_validation",
        )
    ]
    mapping = base_mapping(
        next_validation_event="客户测试完成",
        next_validation_date=date(2026, 12, 31),
    )

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["evidence_level"] == "E3"
    assert result["selection"]["pool_code"] == "B"


def test_missing_publish_time_is_not_treated_as_historical_evidence():
    rows = [evidence("undated", None, "order_award")]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=None,
    )

    assert result["authenticity"]["evidence_level"] == "E1"
    assert "evidence_missing_publish_time:undated" in result["data_limitations"]


def test_negative_confirmed_fact_is_a_veto_not_a_small_penalty():
    rows = [
        evidence(
            "negative",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "negative",
            metadata={"veto_reason": "customer_cancelled"},
        )
    ]

    result = module.score_mapping(
        base_mapping(),
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "rejected"
    assert result["selection"]["veto_reasons"] == ["customer_cancelled"]


def test_score_bundle_keeps_component_inputs_for_auditable_persistence():
    rows = [
        evidence(
            "prototype",
            datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
            "prototype_delivery",
        )
    ]
    mapping = base_mapping(
        expectation_gap_score=55,
        catalyst_score=60,
        risk_score=20,
    )

    result = module.score_mapping(
        mapping,
        rows,
        trade_date=date(2026, 7, 11),
        node_score=70,
    )

    assert result["authenticity"]["detail"]["product_evidence_score"] == 80
    assert result["benefit"]["detail"]["node_attractiveness"] == 70
    assert result["benefit"]["detail"]["order_certainty_score"] == 30
    assert result["selection"]["detail"]["expectation_gap_score"] == 55
    assert result["selection"]["detail"]["risk_score"] == 20


class FakeRepository:
    def __init__(self, *, missing=None):
        self.missing = list(missing or [])
        self.upserts = []
        self.transitions = []

    def preflight(self, cur):
        return self.missing

    def fetch_mappings(self, cur, **kwargs):
        return [base_mapping()]

    def fetch_asof_evidence(self, cur, mapping_id, cutoff):
        return [
            evidence(
                "prototype",
                datetime(2026, 7, 10, 9, tzinfo=timezone.utc),
                "prototype_delivery",
            )
        ]

    def fetch_node_score(self, cur, **kwargs):
        return {"total_score": 70}

    def upsert_score_bundle(self, cur, bundle):
        self.upserts.append(bundle)

    def transition_pool(self, cur, bundle):
        self.transitions.append(bundle)
        return True


class FakeConnection:
    def __init__(self):
        self.cursor_value = object()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **kwargs):
        return FakeCursorContext(self.cursor_value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        return None


class FakeCursorContext:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self.cursor

    def __exit__(self, exc_type, exc, tb):
        return False


def test_batch_dry_run_scores_without_writing():
    repository = FakeRepository()
    connection = FakeConnection()

    result = module.run_batch_score(
        pg_url="postgresql://unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=True,
        repository=repository,
        connection_factory=lambda: connection,
    )

    assert result["dry_run"] is True
    assert result["mapping_count"] == 1
    assert result["pool_counts"] == {"C": 1}
    assert repository.upserts == []
    assert repository.transitions == []
    assert connection.commits == 0


def test_batch_write_persists_scores_and_transition_in_one_commit():
    repository = FakeRepository()
    connection = FakeConnection()

    result = module.run_batch_score(
        pg_url="postgresql://unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 11),
        model_version="v2.0",
        dry_run=False,
        repository=repository,
        connection_factory=lambda: connection,
    )

    assert result["written"] == 1
    assert result["transitions"] == 1
    assert len(repository.upserts) == 1
    assert len(repository.transitions) == 1
    assert connection.commits == 1


def test_batch_preflight_lists_all_missing_tables():
    repository = FakeRepository(
        missing=["business_tag_selection_scores", "business_tag_pool_state"]
    )

    try:
        module.run_batch_score(
            pg_url="postgresql://unused",
            chain_id="dexterous_hand",
            trade_date=date(2026, 7, 11),
            model_version="v2.0",
            dry_run=True,
            repository=repository,
            connection_factory=FakeConnection,
        )
    except module.MissingSelectionTables as exc:
        assert exc.tables == [
            "business_tag_selection_scores",
            "business_tag_pool_state",
        ]
    else:
        raise AssertionError("missing tables must stop batch scoring")


def test_cli_requires_explicit_trade_date_and_prints_json(monkeypatch, capsys):
    captured = {}

    def fake_run_batch_score(**kwargs):
        captured.update(kwargs)
        return {"dry_run": kwargs["dry_run"], "mapping_count": 0}

    monkeypatch.setattr(module, "run_batch_score", fake_run_batch_score)

    exit_code = module.main(
        [
            "--chain-id",
            "dexterous_hand",
            "--trade-date",
            "2026-07-11",
            "--model-version",
            "v2.0",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert captured["trade_date"] == date(2026, 7, 11)
    assert captured["dry_run"] is True
    assert '"mapping_count": 0' in capsys.readouterr().out
