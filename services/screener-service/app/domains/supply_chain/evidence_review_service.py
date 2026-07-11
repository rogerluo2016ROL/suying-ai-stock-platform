"""Application service for audited supply-chain evidence reviews."""

from __future__ import annotations

from typing import Any

from app.domains.supply_chain.evidence_review_repository import (
    EXPECTATION_NORMALIZATION_FIELDS,
    FACT_NORMALIZATION_FIELDS,
    EvidenceFactMetadataPatch,
    EvidenceReviewRepository,
    ReviewDecision,
    ReviewNormalization,
)


REVIEWER_ASSURANCE = (
    "The reviewer name is asserted by the caller. Shared database credentials "
    "do not verify the human operator's identity."
)


class EvidenceReviewService:
    """Validates target-specific review input before one repository transaction."""

    def __init__(self, repository: EvidenceReviewRepository | None = None):
        self.repository = repository or EvidenceReviewRepository()

    @staticmethod
    def _validate_common(
        *, decision: ReviewDecision, reviewer: str, note: str
    ) -> tuple[str, str]:
        if decision not in {"approved", "rejected", "needs_more_evidence"}:
            raise ValueError(f"unsupported review decision: {decision}")
        clean_reviewer = str(reviewer or "").strip()
        clean_note = str(note or "").strip()
        if not clean_reviewer:
            raise ValueError("reviewer is required")
        if not clean_note:
            raise ValueError("review note is required")
        return clean_reviewer, clean_note

    @staticmethod
    def _validate_normalization(
        *,
        decision: ReviewDecision,
        normalization: ReviewNormalization | None,
        allowed_fields: frozenset[str],
    ) -> None:
        if normalization is None:
            return
        if decision != "approved":
            raise ValueError("normalization may only be written by an approved review")
        invalid = normalization.score_fields() - allowed_fields
        if invalid:
            fields = ", ".join(sorted(invalid))
            raise ValueError(f"normalization fields are incompatible with target: {fields}")

    @staticmethod
    def _validate_stage_after(
        *, decision: ReviewDecision, stage_after: dict[str, str] | None
    ) -> None:
        if stage_after is not None and decision != "approved":
            raise ValueError("stage_after may only be written by an approved review")

    @staticmethod
    def _with_assurance(result: dict[str, Any]) -> dict[str, Any]:
        return {
            **result,
            "review_gate": "application_level",
            "reviewer_identity_verified": False,
            "reviewer_assurance": REVIEWER_ASSURANCE,
        }

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
        clean_reviewer, clean_note = self._validate_common(
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        self._validate_normalization(
            decision=decision,
            normalization=normalization,
            allowed_fields=FACT_NORMALIZATION_FIELDS,
        )
        self._validate_stage_after(decision=decision, stage_after=stage_after)
        if metadata_patch is not None and decision != "approved":
            raise ValueError("metadata patch may only be written by an approved review")
        result = self.repository.review_fact(
            fact_id=fact_id,
            decision=decision,
            reviewer=clean_reviewer,
            note=clean_note,
            stage_after=stage_after,
            normalization=normalization,
            metadata_patch=metadata_patch,
            connection=connection,
        )
        return self._with_assurance(result)

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
        clean_reviewer, clean_note = self._validate_common(
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        self._validate_stage_after(decision=decision, stage_after=stage_after)
        result = self.repository.review_event(
            event_id=event_id,
            decision=decision,
            reviewer=clean_reviewer,
            note=clean_note,
            stage_after=stage_after,
            confidence=confidence,
            connection=connection,
        )
        return self._with_assurance(result)

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
        clean_reviewer, clean_note = self._validate_common(
            decision=decision,
            reviewer=reviewer,
            note=note,
        )
        self._validate_normalization(
            decision=decision,
            normalization=normalization,
            allowed_fields=EXPECTATION_NORMALIZATION_FIELDS,
        )
        result = self.repository.review_expectation_monitor(
            monitor_id=monitor_id,
            decision=decision,
            reviewer=clean_reviewer,
            note=clean_note,
            normalization=normalization,
            connection=connection,
        )
        return self._with_assurance(result)

    def list_queue(self, *, limit: int = 50, connection=None) -> dict[str, Any]:
        return self._with_assurance(
            self.repository.list_queue(limit=limit, connection=connection)
        )


_service = EvidenceReviewService()


def review_fact(**kwargs):
    return _service.review_fact(**kwargs)


def review_event(**kwargs):
    return _service.review_event(**kwargs)


def review_expectation_monitor(**kwargs):
    return _service.review_expectation_monitor(**kwargs)


def list_queue(**kwargs):
    return _service.list_queue(**kwargs)


__all__ = [
    "EvidenceFactMetadataPatch",
    "EvidenceReviewService",
    "ReviewDecision",
    "ReviewNormalization",
    "list_queue",
    "review_event",
    "review_expectation_monitor",
    "review_fact",
]
