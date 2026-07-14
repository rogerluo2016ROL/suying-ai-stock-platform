"""Public HTTP routes for transactional supply-chain evidence review."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.domains.supply_chain import evidence_review_service
from app.domains.supply_chain.evidence_review_repository import (
    EvidenceFactMetadataPatch,
    EvidenceReviewNotFound,
    ReviewDecision,
    ReviewNormalization,
)


class _ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: ReviewDecision
    reviewer: str = Field(min_length=1)
    note: str = Field(min_length=1)


class FactEvidenceReviewRequest(_ReviewRequest):
    stage_after: dict[str, str] | None = None
    normalization: ReviewNormalization | None = None
    metadata_patch: EvidenceFactMetadataPatch | None = None


class EventEvidenceReviewRequest(_ReviewRequest):
    stage_after: dict[str, str] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExpectationEvidenceReviewRequest(_ReviewRequest):
    normalization: ReviewNormalization | None = None


router = APIRouter(
    prefix="/api/v1/screener/supply-chain",
    tags=["supply-chain-evidence-review"],
)


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EvidenceReviewNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="evidence review failed")


@router.get("/evidence-review/queue")
def evidence_review_queue(limit: int = Query(default=50, ge=1, le=200)):
    try:
        return evidence_review_service.list_queue(limit=limit)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/evidence/facts/{fact_id}/review")
def review_fact(fact_id: str, request: FactEvidenceReviewRequest):
    try:
        return evidence_review_service.review_fact(
            fact_id=fact_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
            stage_after=request.stage_after,
            normalization=request.normalization,
            metadata_patch=request.metadata_patch,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/evidence/events/{event_id}/review")
def review_event(event_id: str, request: EventEvidenceReviewRequest):
    try:
        return evidence_review_service.review_event(
            event_id=event_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
            stage_after=request.stage_after,
            confidence=request.confidence,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/evidence/expectations/{monitor_id}/review")
def review_expectation_monitor(
    monitor_id: str,
    request: ExpectationEvidenceReviewRequest,
):
    try:
        return evidence_review_service.review_expectation_monitor(
            monitor_id=monitor_id,
            decision=request.decision,
            reviewer=request.reviewer,
            note=request.note,
            normalization=request.normalization,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


__all__ = [
    "EventEvidenceReviewRequest",
    "ExpectationEvidenceReviewRequest",
    "FactEvidenceReviewRequest",
    "router",
]
