"""Normalize evidence and enforce conservative mapping-upgrade rules."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Sequence

from .models import (
    CommercializationStage,
    EvidenceGrade,
    NormalizedEvidence,
    RawEvidence,
)


VAGUE_TERMS = ("布局", "关注", "可用于", "有望用于", "涉及概念")
RELATION_TERMS = ("供应", "定点", "交付", "量产", "订单", "收入", "客户验证", "主营")
_UNAMBIGUOUS_RELATION_TERMS = (
    "已供应",
    "批量供应",
    "定点",
    "交付",
    "量产",
    "订单",
    "收入",
    "客户验证",
    "主营",
)

_SOURCE_GRADES = {
    EvidenceGrade.S: {
        "announcement",
        "annual_report",
        "periodic_report",
        "regulatory_reply",
    },
    EvidenceGrade.A: {"official_web", "official_wechat", "ir_record"},
    EvidenceGrade.B: {"exchange_qa", "government_official", "customer_official"},
    EvidenceGrade.C: {"research", "media_interview"},
}

_STAGE_TERMS = (
    (CommercializationStage.SIGNIFICANT_REVENUE_SHARE, ("收入占比显著提升", "收入占比达到")),
    (CommercializationStage.REVENUE_RECOGNITION, ("收入确认", "形成收入", "实现收入")),
    (CommercializationStage.CONFIRMED_ORDER, ("明确订单", "批量订单", "框架协议", "获得订单")),
    (CommercializationStage.MASS_PRODUCTION, ("批量交付", "批量供货", "量产", "产能释放")),
    (CommercializationStage.SMALL_BATCH, ("小批量", "小批交付", "试产", "试订单")),
    (CommercializationStage.DESIGN_WIN, ("客户定点", "定点", "供应商资格", "进入供应链")),
    (CommercializationStage.CUSTOMER_VALIDATION, ("客户验证", "客户认证")),
    (CommercializationStage.SAMPLE, ("送样", "样品", "样机", "原型机")),
    (CommercializationStage.TECHNOLOGY_RESEARCH, ("技术研发", "研发", "立项", "技术储备")),
)


def classify_source(source_type: str) -> EvidenceGrade:
    normalized = source_type.strip().lower()
    for grade, source_types in _SOURCE_GRADES.items():
        if normalized in source_types:
            return grade
    return EvidenceGrade.D


def commercialization_stage(text: str) -> CommercializationStage:
    normalized = _normalize_text(text)
    for stage, terms in _STAGE_TERMS:
        if any(term in normalized for term in terms):
            return stage
    return CommercializationStage.CONCEPT_RELATED


def normalize_evidence(raw: RawEvidence) -> NormalizedEvidence:
    source_id = raw.source_id.strip()
    source_type = raw.source_type.strip().lower()
    content = _normalize_text(raw.content)
    fingerprint_payload = json.dumps(
        {"source_id": source_id, "source_type": source_type, "content": content},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return NormalizedEvidence(
        source_id=source_id,
        source_type=source_type,
        content=content,
        event_date=raw.event_date,
        node_id=raw.node_id.strip() if raw.node_id else None,
        source_url=raw.source_url.strip() if raw.source_url else None,
        grade=classify_source(source_type),
        has_explicit_relation=_has_explicit_relation(content),
        stage=commercialization_stage(content),
        fingerprint=sha256(fingerprint_payload.encode("utf-8")).hexdigest(),
    )


def can_auto_verify(events: Sequence[NormalizedEvidence]) -> bool:
    clear = [
        event
        for event in events
        if event.node_id and event.event_date and event.has_explicit_relation
    ]
    return any(event.grade == EvidenceGrade.S for event in clear) or len(
        {event.source_id for event in clear if event.grade == EvidenceGrade.A}
    ) >= 2


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_explicit_relation(content: str) -> bool:
    if not any(term in content for term in RELATION_TERMS):
        return False
    if any(term in content for term in VAGUE_TERMS):
        return any(term in content for term in _UNAMBIGUOUS_RELATION_TERMS)
    return True
