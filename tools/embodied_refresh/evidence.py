"""Normalize evidence and enforce conservative mapping-upgrade rules."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from datetime import date, datetime
from collections import defaultdict
from typing import Sequence

from .models import (
    CommercializationStage,
    EvidenceGrade,
    NormalizedEvidence,
    RawEvidence,
)


VAGUE_TERMS = ("布局", "关注", "可用于", "有望用于", "涉及概念")
RELATION_TERMS = ("供应", "定点", "交付", "量产", "订单", "客户验证")
NEGATIVE_TERMS = ("尚未", "没有", "未形成", "不供应", "否认", "取消", "终止", "撤回", "停止")
FINGERPRINT_VERSION = "v1"

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
    (CommercializationStage.CONFIRMED_ORDER, ("明确订单", "批量订单", "获得订单", "新增订单")),
    (CommercializationStage.MASS_PRODUCTION, ("批量交付", "批量供货", "量产")),
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
    stages = [_stage_for_sentence(sentence) for sentence in _sentences(text)]
    return max(stages, default=CommercializationStage.CONCEPT_RELATED)


def normalize_evidence(raw: RawEvidence) -> NormalizedEvidence:
    source_id = raw.source_id.strip()
    source_type = raw.source_type.strip().lower()
    content = _normalize_text(raw.content)
    publisher_id = _optional_text(raw.publisher_id)
    canonical_source_id = _optional_text(raw.canonical_source_id) or publisher_id
    fingerprint_payload = json.dumps(
        {
            "source_identity": canonical_source_id or source_id,
            "source_type": source_type,
            "content": content,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return NormalizedEvidence(
        source_id=source_id,
        source_type=source_type,
        content=content,
        event_date=raw.event_date,
        node_id=_optional_text(raw.node_id),
        source_url=_optional_text(raw.source_url),
        grade=classify_source(source_type),
        has_explicit_relation=_has_explicit_relation(content),
        stage=commercialization_stage(content),
        fingerprint=f"{FINGERPRINT_VERSION}:{sha256(fingerprint_payload.encode('utf-8')).hexdigest()}",
        publisher_id=publisher_id,
        canonical_source_id=canonical_source_id,
        valid_until=raw.valid_until,
        is_valid=raw.is_valid and raw.valid is not False,
        fingerprint_version=FINGERPRINT_VERSION,
        valid=raw.is_valid and raw.valid is not False,
    )


def can_auto_verify(
    events: Sequence[NormalizedEvidence], *, as_of: date | datetime | None = None
) -> bool:
    cutoff = _as_date(as_of) if as_of is not None else date.today()
    clear = [
        event
        for event in events
        if event.node_id
        and event.event_date
        and event.has_explicit_relation
        and event.is_valid
        and event.valid
        and _as_date(event.event_date) <= cutoff
        and (event.valid_until is None or _as_date(event.valid_until) >= cutoff)
    ]
    by_node: dict[str, list[NormalizedEvidence]] = defaultdict(list)
    for event in clear:
        by_node[event.node_id].append(event)
    return any(
        any(event.grade == EvidenceGrade.S for event in node_events)
        or len(
            {
                event.canonical_source_id
                for event in node_events
                if event.grade == EvidenceGrade.A and event.canonical_source_id
            }
        )
        >= 2
        for node_events in by_node.values()
    )


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _optional_text(value: str | None) -> str | None:
    normalized = value.strip() if value else ""
    return normalized or None


def _has_explicit_relation(content: str) -> bool:
    return any(_sentence_has_explicit_relation(sentence) for sentence in _sentences(content))


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？!?；;\n]+", _normalize_text(text)) if part.strip()]


def _is_unsafe_sentence(sentence: str) -> bool:
    return any(term in sentence for term in NEGATIVE_TERMS) or any(
        term in sentence for term in VAGUE_TERMS
    )


def _sentence_has_explicit_relation(sentence: str) -> bool:
    if _is_unsafe_sentence(sentence):
        return False
    if "供应链" in sentence and not re.search(r"(?:已|批量|向.+)供应", sentence):
        sentence = sentence.replace("供应链", "")
    return any(_has_affirmative_term(sentence, term) for term in RELATION_TERMS)


def _stage_for_sentence(sentence: str) -> CommercializationStage:
    if _is_unsafe_sentence(sentence):
        return CommercializationStage.CONCEPT_RELATED
    has_revenue_ratio = "收入占比" in sentence and bool(
        re.search(r"\d+(?:\.\d+)?%", sentence)
    )
    if (
        has_revenue_ratio
        and any(term in sentence for term in ("显著提升", "大幅提升"))
        and not any(term in sentence for term in ("未提升", "并未提升", "没有提升"))
    ):
        return CommercializationStage.SIGNIFICANT_REVENUE_SHARE
    if has_revenue_ratio and not any(
        term in sentence for term in ("未达到", "尚未达到", "并未达到", "没有达到")
    ):
        return CommercializationStage.REVENUE_RECOGNITION
    if any(anchor in sentence for anchor in ("该业务", "该产品", "机器人业务", "传感器业务")) and any(
        term in sentence for term in ("收入确认", "形成收入", "实现收入")
    ):
        return CommercializationStage.REVENUE_RECOGNITION
    for stage, terms in _STAGE_TERMS:
        if any(_has_affirmative_term(sentence, term) for term in terms):
            return stage
    return CommercializationStage.CONCEPT_RELATED


def _has_affirmative_term(sentence: str, term: str) -> bool:
    return any(
        not _is_locally_negated(sentence, match.start(), match.end())
        for match in re.finditer(re.escape(term), sentence)
    )


def _is_locally_negated(sentence: str, start: int, end: int) -> bool:
    prefix = sentence[max(0, start - 10) : start]
    suffix = sentence[end : min(len(sentence), end + 6)]
    negation_before = re.search(
        r"(?:尚未|尚无|并未|没有|不存在|未|无|不)[^，,。；;但却]{0,6}$",
        prefix,
    )
    negation_after = re.match(r"(?:不存在|被?否认|被?取消|被?终止|已撤回)", suffix)
    return bool(negation_before or negation_after)


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value
