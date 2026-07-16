"""Successful-baseline change detection, importance scoring and digest rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Mapping, MutableMapping, Sequence

from .models import EvidenceChange


SCORE_WEIGHTS = {
    "source": 25,
    "commercialization": 25,
    "mapping_change": 20,
    "business_contribution": 15,
    "node_importance": 10,
    "freshness_crosscheck": 5,
}


@dataclass(frozen=True)
class ChangeBatch:
    changes: Sequence[EvidenceChange]
    cutoff_time: str
    scan_size: Mapping[str, int] = field(default_factory=dict)
    coverage_before: Mapping[str, int] = field(default_factory=dict)
    coverage_after: Mapping[str, int] = field(default_factory=dict)
    missing_mapping_nodes: Sequence[str] = field(default_factory=tuple)
    top3_entries: Sequence[Mapping[str, str]] = field(default_factory=tuple)
    top3_exits: Sequence[Mapping[str, str]] = field(default_factory=tuple)


def priority_for_score(score: int | float | None) -> str:
    if score is None:
        return "P3"
    value = max(0.0, min(100.0, float(score)))
    if value >= 85:
        return "P0"
    if value >= 70:
        return "P1"
    if value >= 50:
        return "P2"
    return "P3"


def score_change(change: Any) -> int | None:
    """Return the exact weighted six-dimension score and retain its audit trail."""
    factors: dict[str, dict[str, float | int]] = {}
    total = 0.0
    complete = True
    for name, weight in SCORE_WEIGHTS.items():
        score_key = f"{name}_score"
        if isinstance(change, Mapping):
            raw = change.get(score_key) if score_key in change else change.get(name)
        else:
            raw = _get(change, score_key, None)
        if raw is None and not isinstance(change, Mapping):
            fallback = _get(change, name, None)
            raw = fallback if isinstance(fallback, (int, float)) else None
        if raw is None:
            factors[name] = {"value": None, "weight": weight, "points": None}
            complete = False
            continue
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            factors[name] = {"value": None, "weight": weight, "points": None}
            complete = False
            continue
        value = max(0.0, min(100.0, numeric))
        points = value * weight / 100
        factors[name] = {"value": value, "weight": weight, "points": points}
        total += points
    result = int(round(total)) if complete else None
    if isinstance(change, MutableMapping):
        change["score_factors"] = factors
        change["score"] = result
        change["priority"] = priority_for_score(result)
    elif hasattr(change, "payload") and isinstance(change.payload, MutableMapping):
        change.payload["score_factors"] = factors
        change.payload["score"] = result
        change.payload["priority"] = priority_for_score(result)
    return result


def diff_snapshots(previous: Any, current: Any) -> list[EvidenceChange]:
    """Compare the current snapshot only against an explicitly successful baseline."""
    if str(_get(previous, "status", "")) != "success":
        raise ValueError("baseline snapshot must have status success")
    run_id = str(_get(current, "run_id", ""))
    chain_id = str(_get(current, "chain_id", _get(previous, "chain_id", "embodied_intelligence")))
    old_by_code = _rows_by_code(_get(previous, "mappings", []) or [])
    new_by_code = _rows_by_code(_get(current, "mappings", []) or [])
    changes: list[EvidenceChange] = []
    seen: set[str] = set()
    for code in sorted(set(old_by_code) | set(new_by_code)):
        old_rows = {str(row.get("node_id", "")): row for row in old_by_code.get(code, [])}
        new_rows = {str(row.get("node_id", "")): row for row in new_by_code.get(code, [])}
        common_nodes = sorted(set(old_rows) & set(new_rows))
        for node_id in common_nodes:
            before, after = old_rows.pop(node_id), new_rows.pop(node_id)
            change_types = _classify_pair(before, after)
            if change_types:
                _append_change(changes, seen, chain_id, run_id, change_types, before, after)

        # A company's one removed node plus one added node is a semantic move,
        # not two unrelated add/remove notifications.
        while old_rows and new_rows:
            before_node = sorted(old_rows)[0]
            after_node = sorted(new_rows)[0]
            _append_change(
                changes, seen, chain_id, run_id, ["node_adjusted", *_classify_pair(old_rows[before_node], new_rows[after_node])],
                old_rows.pop(before_node), new_rows.pop(after_node),
            )
        for after in new_rows.values():
            _append_change(changes, seen, chain_id, run_id, ["new_candidate"], None, after)
        for before in old_rows.values():
            _append_change(changes, seen, chain_id, run_id, ["mapping_invalidated"], before, None)
    return changes


def render_change_digest(batch: ChangeBatch) -> str | None:
    """Render deterministic Chinese outbound text; P3 changes remain internal."""
    publishable = [
        change for change in batch.changes
        if change.payload.get("score") is not None and _priority(change) in {"P0", "P1", "P2"}
    ]
    if not publishable:
        return None
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    publishable.sort(
        key=lambda item: (
            priority_order[_priority(item)],
            -int(item.payload.get("score", 0)),
            str(item.payload.get("code", "")),
            item.change_fingerprint,
        )
    )
    counts = {priority: sum(_priority(row) == priority for row in publishable) for priority in ("P0", "P1", "P2")}
    lines = [
        "具身智能产业证据变动日报",
        f"截止时间：{batch.cutoff_time}",
        "扫描规模：" + ("；".join(
            f"{_scan_label(key)} {value}"
            for key, value in sorted(batch.scan_size.items())
        ) if batch.scan_size else "未提供"),
        f"出站变动：{len(publishable)}（P0 {counts['P0']} / P1 {counts['P1']} / P2 {counts['P2']}）",
    ]
    coverage = []
    for level in (f"L{number}" for number in range(1, 9)):
        before = int(batch.coverage_before.get(level, 0))
        after = int(batch.coverage_after.get(level, 0))
        if before != after:
            coverage.append(f"{level}: {before}→{after}")
    lines.append("产业链覆盖变化：" + ("；".join(coverage) if coverage else "L1–L8无变化"))
    lines.append("仍缺映射节点：" + ("；".join(sorted(batch.missing_mapping_nodes)) if batch.missing_mapping_nodes else "无"))

    current_priority = None
    for change in publishable:
        priority = _priority(change)
        if priority != current_priority:
            lines.extend(["", priority])
            current_priority = priority
        payload = change.payload
        lines.append(
            "- {code} {name} | 节点 {node} | {score}分 | 状态 {before_status} → {after_status} | "
            "阶段 {before_stage} → {after_stage} | 来源 {source} | 证据日期 {date} | 剩余风险 {risk}".format(
                code=payload.get("code", "未知代码"), name=payload.get("company_name", ""),
                node=_digest_node(payload),
                score=payload.get("score", 0), before_status=payload.get("before_status", "无"),
                after_status=payload.get("after_status", "无"), before_stage=payload.get("before_stage", "无"),
                after_stage=payload.get("after_stage", "无"), source=payload.get("source", "未提供"),
                date=payload.get("evidence_date", "未提供"), risk=payload.get("remaining_risk", "尚需持续核验"),
            ).rstrip()
        )
    lines.extend([
        "",
        "Top3进入：" + _render_top3(batch.top3_entries),
        "Top3退出：" + _render_top3(batch.top3_exits),
    ])
    lines.extend(["", "重要性分数衡量产业证据变动，不表示股价上涨概率。"])
    return "\n".join(lines)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _display(value: Any) -> str:
    return "无" if value is None or value == "" else str(value)


def _rows_by_code(rows: Sequence[Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        data = dict(row) if isinstance(row, Mapping) else dict(vars(row))
        result.setdefault(str(data.get("code", "")), []).append(data)
    return result


_STATUS_RANK = {"rejected": -2, "disabled": -2, "invalidated": -2, "weak_evidence": 0, "candidate": 1, "pending_review": 1, "verified": 2}
_GRADE_RANK = {"D": 1, "C": 2, "B": 3, "A": 4, "S": 5}
_CHANGE_TYPE_PRIORITY = {
    "mapping_invalidated": 0,
    "status_downgraded": 1,
    "node_adjusted": 2,
    "status_upgraded": 3,
    "commercialization_advanced": 4,
    "evidence_weakened": 5,
    "evidence_strengthened": 6,
    "new_candidate": 7,
}


def _classify_pair(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    before_status = str(before.get("status", "candidate"))
    after_status = str(after.get("status", "candidate"))
    result: list[str] = []
    if after_status in {"rejected", "disabled", "invalidated"} or after.get("mapping_invalidated") is True:
        result.append("mapping_invalidated")
    before_status_rank = _STATUS_RANK.get(before_status, 0)
    after_status_rank = _STATUS_RANK.get(after_status, 0)
    if after_status_rank > before_status_rank:
        result.append("status_upgraded")
    elif after_status_rank < before_status_rank:
        result.append("status_downgraded")
    if _stage_rank(after.get("stage")) > _stage_rank(before.get("stage")):
        result.append("commercialization_advanced")
    before_grade = _GRADE_RANK.get(str(before.get("evidence_grade", "")).upper(), 0)
    after_grade = _GRADE_RANK.get(str(after.get("evidence_grade", "")).upper(), 0)
    before_ids = set(_event_ids(before))
    after_ids = set(_event_ids(after))
    weakened = (
        after.get("evidence_valid") is False
        or after.get("is_valid") is False
        or after_grade < before_grade
        or bool(before_ids - after_ids)
    )
    strengthened = after_grade > before_grade or bool(after_ids - before_ids)
    if weakened:
        result.append("evidence_weakened")
    elif strengthened:
        result.append("evidence_strengthened")
    return result


def _stage_rank(stage: Any) -> int:
    if stage is None:
        return -1
    try:
        return int(stage)
    except (TypeError, ValueError):
        stages = ["概念相关", "技术研发", "样品", "送样", "客户验证", "定点", "供应商资格", "小批量", "量产", "明确订单", "收入确认", "收入占比显著提升"]
        text = str(stage)
        return stages.index(text) if text in stages else -1


def _event_ids(row: Mapping[str, Any] | None) -> tuple[str, ...]:
    if not row:
        return ()
    values = row.get("evidence_event_ids", row.get("evidence_ids", ())) or ()
    return tuple(sorted(str(value) for value in values))


def _append_change(
    changes: list[EvidenceChange], seen: set[str], chain_id: str, run_id: str,
    change_types: Sequence[str], before: Mapping[str, Any] | None, after: Mapping[str, Any] | None,
) -> None:
    ordered_types = sorted(set(change_types), key=lambda value: (_CHANGE_TYPE_PRIORITY[value], value))
    if not ordered_types:
        return
    change_type = ordered_types[0]
    active = after or before or {}
    payload = dict(active)
    payload.update({
        "chain_id": chain_id,
        "code": str(active.get("code", "")),
        "before_node_id": _display(_get(before, "node_id")),
        "after_node_id": _display(_get(after, "node_id")),
        "before_status": _display(_get(before, "status")),
        "after_status": _display(_get(after, "status")),
        "before_stage": _display(_get(before, "stage")),
        "after_stage": _display(_get(after, "stage")),
        "change_types": ordered_types,
    })
    # Cached aggregate values are never trusted; factors are the source of truth.
    payload.pop("score_factors", None)
    score_change(payload)
    canonical = {
        "chain_id": chain_id,
        "code": payload["code"],
        "before_node_id": payload["before_node_id"],
        "after_node_id": payload["after_node_id"],
        "evidence_event_ids": sorted(set(_event_ids(before)) | set(_event_ids(after))),
        "change_types": ordered_types,
        "target_status": payload["after_status"],
        "target_stage": payload["after_stage"],
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if fingerprint in seen:
        return
    seen.add(fingerprint)
    node_id = str(_get(after, "node_id", _get(before, "node_id", "")))
    changes.append(EvidenceChange(fingerprint, run_id, node_id, change_type, payload))


def _priority(change: EvidenceChange) -> str:
    return str(change.payload.get("priority") or priority_for_score(change.payload.get("score", 0)))


def _render_top3(rows: Sequence[Mapping[str, str]]) -> str:
    if not rows:
        return "无"
    rendered = []
    for row in rows:
        reason = str(row.get("reason", "")).strip()
        if not reason:
            raise ValueError("Top3 entry/exit must include reason")
        company = str(row.get("company", row.get("code", "未知公司")))
        rendered.append(f"{company}：{reason}")
    return "；".join(rendered)


def _scan_label(key: str) -> str:
    return {"companies": "公司", "evidence": "证据"}.get(key, key)


def _digest_node(payload: Mapping[str, Any]) -> str:
    after = payload.get("after_node_id")
    if after and after != "无":
        return str(after)
    before = payload.get("before_node_id")
    return str(before) if before and before != "无" else "未提供"
