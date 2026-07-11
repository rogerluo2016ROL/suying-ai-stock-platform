"""Transactional supply-chain evidence review contracts."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.domains.supply_chain.evidence_review_repository import (
    EvidenceReviewRepository,
    EvidenceFactMetadataPatch,
    ReviewNormalization,
    normalize_review_decision,
)
from app.domains.supply_chain.evidence_review_router import (
    EventEvidenceReviewRequest,
    ExpectationEvidenceReviewRequest,
    FactEvidenceReviewRequest,
    router as evidence_review_router,
)
from app.domains.supply_chain.evidence_review_service import EvidenceReviewService


REVIEWED_AT = datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)


class FakeCursor:
    def __init__(self, *, one_by_token=None, many_by_token=None, fail_on=None, settings=None):
        self.one_by_token = one_by_token or {}
        self.many_by_token = many_by_token or {}
        self.fail_on = fail_on
        self.settings = settings if settings is not None else {
            "app.supply_chain_review_action": ""
        }
        self.executed = []
        self._one = None
        self._many = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        statement = str(statement)
        self.executed.append((statement, params))
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("scripted database failure")
        if "current_setting('app.supply_chain_review_action', true)" in statement:
            self._one = {
                "value": self.settings.get("app.supply_chain_review_action", "")
            }
            self._many = []
            return
        if "set_config('app.supply_chain_review_action', 'manual', true)" in statement:
            self.settings["app.supply_chain_review_action"] = "manual"
            self._one = {"set_config": "manual"}
            self._many = []
            return
        if "set_config('app.supply_chain_review_action', %s, true)" in statement:
            value = str((params or ("",))[0] or "")
            self.settings["app.supply_chain_review_action"] = value
            self._one = {"set_config": value}
            self._many = []
            return
        self._one = None
        self._many = []
        for token, row in self.one_by_token.items():
            if token in statement:
                self._one = dict(row) if row is not None else None
                break
        for token, rows in self.many_by_token.items():
            if token in statement:
                self._many = [dict(row) for row in rows]
                break

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_value = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self, **_kwargs):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def _fact_row(*, metadata, evidence_event_id="e1"):
    return {
        "fact_id": "f1",
        "mapping_id": "m1",
        "company_code": "300001",
        "evidence_event_id": evidence_event_id,
        "validation_status": "confirmed",
        "metadata": metadata,
        "reviewer": "roger",
        "review_note": "原文与灵巧手业务一致",
        "reviewed_at": REVIEWED_AT,
    }


def _event_row(*, status="approved"):
    return {
        "event_id": "e1",
        "mapping_id": "m1",
        "code": "300001",
        "event_date": date(2026, 7, 9),
        "review_status": status,
        "reviewer": "roger",
        "review_note": "原文与灵巧手业务一致",
        "reviewed_at": REVIEWED_AT,
        "stage_after": {"research_stage": "R4", "commercialization_stage": "C2"},
    }


def _fact_cursor(*, metadata, fail_on=None, settings=None, evidence_event_id="e1"):
    return FakeCursor(
        one_by_token={
            "UPDATE evidence_extracted_facts": _fact_row(
                metadata=metadata,
                evidence_event_id=evidence_event_id,
            ),
            "UPDATE business_tag_evidence_events": _event_row(),
            "INSERT INTO business_tag_stage_tracking": {
                "stage_id": "stage:e1",
                "mapping_id": "m1",
                "review_status": "approved",
            },
        },
        fail_on=fail_on,
        settings=settings,
    )


def test_needs_more_evidence_keeps_fact_pending():
    assert normalize_review_decision("needs_more_evidence") == (
        "pending",
        "pending_review",
    )


def test_review_normalization_rejects_out_of_range_scores():
    with pytest.raises(ValidationError):
        ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
            risk_score=101,
        )


def test_review_normalization_requires_at_least_one_score():
    with pytest.raises(ValidationError):
        ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
        )


def test_fact_metadata_patch_rejects_unknown_fields_and_invalid_enums():
    with pytest.raises(ValidationError):
        EvidenceFactMetadataPatch(application_domain="consumer_electronics")
    with pytest.raises(ValidationError):
        EvidenceFactMetadataPatch(
            application_domain="robot_hand",
            collector_guess=True,
        )


def test_fact_metadata_patch_rejects_invalid_legal_status():
    with pytest.raises(ValidationError):
        EvidenceFactMetadataPatch(legal_status="pending")


def test_fact_approval_sets_manual_marker_and_audit_fields():
    normalization = {
        "method_version": "manual-v1",
        "as_of_date": "2026-07-09",
        "reviewer": "roger",
        "reviewed_at": REVIEWED_AT.isoformat(),
        "evidence_delta_score": 65.0,
        "risk_score": 20.0,
    }
    cursor = _fact_cursor(
        metadata={"keep": "value", "review_normalization": normalization}
    )
    connection = FakeConnection(cursor)
    repo = EvidenceReviewRepository(connection_factory=lambda: connection)

    result = repo.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="原文与灵巧手业务一致",
        stage_after={"research_stage": "R4", "commercialization_stage": "C2"},
        normalization=ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
            evidence_delta_score=65,
            risk_score=20,
        ),
    )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "SAVEPOINT supply_chain_manual_review" in sql
    assert "set_config('app.supply_chain_review_action', 'manual', true)" in sql
    assert "review_normalization" in sql
    assert "RETURNING" in sql
    assert result["review_status"] == "approved"
    assert result["normalization_fields"] == ("evidence_delta_score", "risk_score")
    assert result["normalization"]["method_version"] == "manual-v1"
    assert result["normalization"]["as_of_date"] == "2026-07-09"
    assert result["metadata"]["keep"] == "value"
    assert result["reviewed_at"] == REVIEWED_AT
    assert cursor.settings["app.supply_chain_review_action"] == ""
    assert (connection.commits, connection.rollbacks, connection.closes) == (1, 0, 1)


def test_approval_without_normalization_clears_reserved_key_only():
    cursor = _fact_cursor(metadata={"keep": "value"}, evidence_event_id=None)
    repo = EvidenceReviewRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repo.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="已核对原始事实",
        stage_after=None,
        normalization=None,
    )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "coalesce(metadata, '{}'::jsonb) - 'review_normalization'" in sql
    assert result["metadata"] == {"keep": "value"}
    assert result["normalization_fields"] == ()
    assert result["normalization"] == {}


def test_approved_metadata_patch_is_merged_and_returned_from_database():
    stored_metadata = {
        "keep": "value",
        "application_domain": "robot_hand",
        "installation_position": "finger_joint",
        "revenue_confirmed": True,
    }
    cursor = _fact_cursor(metadata=stored_metadata, evidence_event_id=None)
    repo = EvidenceReviewRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repo.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="已核对产品、场景与收入原文",
        stage_after=None,
        metadata_patch=EvidenceFactMetadataPatch(
            application_domain="robot_hand",
            installation_position="finger_joint",
            revenue_confirmed=True,
        ),
    )

    update = next(
        (statement, params)
        for statement, params in cursor.executed
        if "UPDATE evidence_extracted_facts" in statement
    )
    assert "metadata || %s::jsonb" in update[0]
    assert "application_domain" in str(update[1])
    assert result["metadata"] == stored_metadata


def test_expectation_monitor_has_review_path_and_adjusted_return_query():
    stored = {
        "keep": "value",
        "review_normalization": {
            "method_version": "manual-v1",
            "as_of_date": "2026-07-09",
            "reviewer": "roger",
            "reviewed_at": REVIEWED_AT.isoformat(),
            "market_expectation_score": 55.0,
            "catalyst_score": 70.0,
        },
    }
    cursor = FakeCursor(
        one_by_token={
            "UPDATE business_tag_expectation_monitor": {
                "monitor_id": "x1",
                "mapping_id": "m1",
                "review_status": "approved",
                "market_price_change": 12.5,
                "metadata": stored,
                "reviewer": "roger",
                "review_note": "已核对原始声明、发布日期和预期日期",
                "reviewed_at": REVIEWED_AT,
            }
        }
    )
    repo = EvidenceReviewRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repo.review_expectation_monitor(
        monitor_id="x1",
        decision="approved",
        reviewer="roger",
        note="已核对原始声明、发布日期和预期日期",
        normalization=ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
            market_expectation_score=55,
            catalyst_score=70,
        ),
    )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "daily_kline" in sql
    assert "adj_factor" in sql
    assert "20" in sql
    assert result["review_status"] == "approved"
    assert result["market_price_change"] == 12.5
    assert result["normalization_fields"] == (
        "catalyst_score",
        "market_expectation_score",
    )


def test_event_review_uses_same_marker_and_database_audit_values():
    cursor = FakeCursor(
        one_by_token={"UPDATE business_tag_evidence_events": _event_row()}
    )
    repo = EvidenceReviewRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repo.review_event(
        event_id="e1",
        decision="approved",
        reviewer="roger",
        note="已核对原文",
        stage_after=None,
    )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "SAVEPOINT supply_chain_manual_review" in sql
    assert "set_config('app.supply_chain_review_action', 'manual', true)" in sql
    assert result["reviewed_at"] == REVIEWED_AT
    assert result["review_status"] == "approved"
    assert cursor.settings["app.supply_chain_review_action"] == ""


def test_caller_owned_connection_is_never_committed_rolled_back_or_closed():
    settings = {"app.supply_chain_review_action": "outer-action"}
    cursor = _fact_cursor(
        metadata={"keep": "value"},
        settings=settings,
        evidence_event_id=None,
    )
    connection = FakeConnection(cursor)
    repo = EvidenceReviewRepository(connection_factory=lambda: pytest.fail("unused"))

    repo.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="已核对",
        stage_after=None,
        connection=connection,
    )

    assert (connection.commits, connection.rollbacks, connection.closes) == (0, 0, 0)
    assert settings["app.supply_chain_review_action"] == "outer-action"


def test_caller_owned_failure_rolls_back_savepoint_and_restores_marker_only():
    settings = {"app.supply_chain_review_action": "outer-action"}
    cursor = _fact_cursor(
        metadata={},
        settings=settings,
        fail_on="UPDATE evidence_extracted_facts",
    )
    connection = FakeConnection(cursor)
    repo = EvidenceReviewRepository(connection_factory=lambda: pytest.fail("unused"))

    with pytest.raises(RuntimeError, match="scripted database failure"):
        repo.review_fact(
            fact_id="f1",
            decision="approved",
            reviewer="roger",
            note="已核对",
            stage_after=None,
            connection=connection,
        )

    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "ROLLBACK TO SAVEPOINT supply_chain_manual_review" in sql
    assert "RELEASE SAVEPOINT supply_chain_manual_review" in sql
    assert settings["app.supply_chain_review_action"] == "outer-action"
    assert (connection.commits, connection.rollbacks, connection.closes) == (0, 0, 0)


def test_owned_failure_rolls_back_and_closes_connection():
    cursor = _fact_cursor(metadata={}, fail_on="UPDATE evidence_extracted_facts")
    connection = FakeConnection(cursor)
    repo = EvidenceReviewRepository(connection_factory=lambda: connection)

    with pytest.raises(RuntimeError):
        repo.review_fact(
            fact_id="f1",
            decision="approved",
            reviewer="roger",
            note="已核对",
            stage_after=None,
        )

    assert (connection.commits, connection.rollbacks, connection.closes) == (0, 1, 1)
    assert cursor.settings["app.supply_chain_review_action"] == ""


def test_review_queue_contains_pending_facts_events_and_expectations():
    cursor = FakeCursor(
        many_by_token={
            "FROM evidence_extracted_facts": [
                {"queue_type": "fact", "id": "f1", "review_status": "pending"}
            ],
            "FROM business_tag_evidence_events": [
                {
                    "queue_type": "event",
                    "id": "e1",
                    "review_status": "pending_review",
                }
            ],
            "FROM business_tag_expectation_monitor": [
                {
                    "queue_type": "expectation_monitor",
                    "id": "x1",
                    "review_status": "pending_review",
                }
            ],
        }
    )
    repo = EvidenceReviewRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repo.list_queue(limit=50)

    assert [item["queue_type"] for item in result["queue"]] == [
        "fact",
        "event",
        "expectation_monitor",
    ]
    assert result["counts"] == {"facts": 1, "events": 1, "expectations": 1}


class RecordingRepository:
    def __init__(self):
        self.calls = []

    def review_fact(self, **kwargs):
        self.calls.append(("fact", kwargs))
        return {
            "fact_id": kwargs["fact_id"],
            "review_status": "approved",
            "reviewed_at": REVIEWED_AT,
            "metadata": {},
            "normalization": {},
            "normalization_fields": (),
        }


def test_service_rejects_patch_for_non_approved_decisions():
    repository = RecordingRepository()
    service = EvidenceReviewService(repository=repository)

    for decision in ("rejected", "needs_more_evidence"):
        with pytest.raises(ValueError, match="metadata patch.*approved"):
            service.review_fact(
                fact_id="f1",
                decision=decision,
                reviewer="roger",
                note="不通过",
                stage_after=None,
                metadata_patch=EvidenceFactMetadataPatch(revenue_confirmed=True),
            )
    assert repository.calls == []


def test_service_rejects_normalization_for_non_approved_decisions():
    repository = RecordingRepository()
    service = EvidenceReviewService(repository=repository)
    normalization = ReviewNormalization(
        method_version="manual-v1",
        as_of_date=date(2026, 7, 9),
        risk_score=20,
    )

    with pytest.raises(ValueError, match="normalization.*approved"):
        service.review_fact(
            fact_id="f1",
            decision="rejected",
            reviewer="roger",
            note="拒绝",
            stage_after=None,
            normalization=normalization,
        )
    assert repository.calls == []


def test_service_rejects_target_incompatible_normalization_fields():
    repository = RecordingRepository()
    service = EvidenceReviewService(repository=repository)

    with pytest.raises(ValueError, match="catalyst_score"):
        service.review_fact(
            fact_id="f1",
            decision="approved",
            reviewer="roger",
            note="已核对",
            stage_after=None,
            normalization=ReviewNormalization(
                method_version="manual-v1",
                as_of_date=date(2026, 7, 9),
                catalyst_score=70,
            ),
        )
    assert repository.calls == []


def test_service_passes_caller_owned_connection_and_discloses_gate_scope():
    repository = RecordingRepository()
    service = EvidenceReviewService(repository=repository)
    connection = object()

    result = service.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="已核对",
        stage_after=None,
        connection=connection,
    )

    assert repository.calls[0][1]["connection"] is connection
    assert result["review_gate"] == "application_level"
    assert result["reviewer_identity_verified"] is False
    assert "RBAC" not in result.get("reviewer_assurance", "")


def test_public_request_models_require_human_assertion_and_forbid_unknown_fields():
    for model in (
        FactEvidenceReviewRequest,
        EventEvidenceReviewRequest,
        ExpectationEvidenceReviewRequest,
    ):
        with pytest.raises(ValidationError):
            model(decision="approved", note="已核对")
        with pytest.raises(ValidationError):
            model(decision="approved", reviewer="roger", note="")

    with pytest.raises(ValidationError):
        FactEvidenceReviewRequest(
            decision="approved",
            reviewer="roger",
            note="已核对",
            metadata_patch={"collector_guess": True},
        )


def test_evidence_review_router_exposes_all_public_paths():
    paths = {route.path for route in evidence_review_router.routes}
    assert {
        "/api/v1/screener/supply-chain/evidence-review/queue",
        "/api/v1/screener/supply-chain/evidence/facts/{fact_id}/review",
        "/api/v1/screener/supply-chain/evidence/events/{event_id}/review",
        "/api/v1/screener/supply-chain/evidence/expectations/{monitor_id}/review",
    } <= paths


def test_legacy_event_review_delegates_without_system_reviewer(monkeypatch):
    from app.domains.screening import service as legacy

    captured = {}

    def fake_review_event(**kwargs):
        captured.update(kwargs)
        return {"event_id": kwargs["event_id"], "review_status": "pending_review"}

    monkeypatch.setattr(legacy.evidence_review_service, "review_event", fake_review_event)
    request = legacy.BusinessTagEvidenceReviewRequest(
        review_status="pending_review",
        reviewer="roger",
        note="需要补充原始公告",
        confidence=0.7,
        stage_after={"research_stage": "R3", "commercialization_stage": "C1"},
    )

    result = legacy._review_business_tag_evidence("e1", request)

    assert result["event_id"] == "e1"
    assert captured == {
        "event_id": "e1",
        "decision": "needs_more_evidence",
        "reviewer": "roger",
        "note": "需要补充原始公告",
        "confidence": 0.7,
        "stage_after": {"research_stage": "R3", "commercialization_stage": "C1"},
    }


def test_legacy_event_review_request_has_no_default_system_reviewer():
    from app.domains.screening.service import BusinessTagEvidenceReviewRequest

    with pytest.raises(ValidationError):
        BusinessTagEvidenceReviewRequest(
            review_status="approved",
            note="已核对",
        )


def test_reviewed_at_crossing_utc_day_uses_shanghai_review_date():
    reviewed_at = datetime(2026, 7, 11, 17, 30, tzinfo=timezone.utc)
    assert reviewed_at.astimezone(ZoneInfo("Asia/Shanghai")).date() == date(
        2026, 7, 12
    )
