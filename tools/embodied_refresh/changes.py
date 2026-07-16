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
    coverage_before: Mapping[str, int] = field(default_factory=dict)
    coverage_after: Mapping[str, int] = field(default_factory=dict)
    top3_entries: Sequence[str] = field(default_factory=tuple)
    top3_exits: Sequence[str] = field(default_factory=tuple)


def priority_for_score(score: int | float) -> str:
    value = max(0.0, min(100.0, float(score)))
    if value >= 85:
        return "P0"
    if value >= 70:
        return "P1"
    if value >= 50:
        return "P2"
    return "P3"


def score_change(change: Any) -> int:
    """Return the exact weighted six-dimension score and retain its audit trail."""
    factors: dict[str, dict[str, float | int]] = {}
    total = 0.0
    for name, weight in SCORE_WEIGHTS.items():
        raw = _get(change, f"{name}_score", _get(change, name, 0))
        try:
            numeric = float(raw or 0)
        except (TypeError, ValueError):
            numeric = 0.0
        value = max(0.0, min(100.0, numeric))
        points = value * weight / 100
        factors[name] = {"value": value, "weight": weight, "points": points}
        total += points
    result = int(round(max(0.0, min(100.0, total))))
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
    old_rows = _index_rows(_get(previous, "mappings", []) or [])
    new_rows = _index_rows(_get(current, "mappings", []) or [])
    changes: list[EvidenceChange] = []
    seen: set[str] = set()
    for key in sorted(set(old_rows) | set(new_rows)):
        before = old_rows.get(key)
        after = new_rows.get(key)
        if before == after:
            continue
        change_type = "added" if before is None else "removed" if after is None else "updated"
        active = after or before or {}
        payload = dict(active)
        payload.update(
            {
                "code": str(_get(active, "code", key[0])),
                "before_status": _display(_get(before, "status")),
                "after_status": _display(_get(after, "status")),
                "before_stage": _display(_get(before, "stage")),
                "after_stage": _display(_get(after, "stage")),
            }
        )
        if "score" not in payload:
            score_change(payload)
        else:
            payload["score"] = max(0, min(100, int(round(float(payload["score"])))))
            payload.setdefault("priority", priority_for_score(payload["score"]))
        canonical = {"key": key, "type": change_type, "before": before, "after": after}
        fingerprint = hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        changes.append(EvidenceChange(fingerprint, run_id, str(key[1]), change_type, payload))
    return changes


def render_change_digest(batch: ChangeBatch) -> str | None:
    """Render deterministic Chinese outbound text; P3 changes remain internal."""
    publishable = [change for change in batch.changes if _priority(change) in {"P0", "P1", "P2"}]
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
        f"出站变动：{len(publishable)}（P0 {counts['P0']} / P1 {counts['P1']} / P2 {counts['P2']}）",
    ]
    coverage = []
    for level in (f"L{number}" for number in range(1, 9)):
        before = int(batch.coverage_before.get(level, 0))
        after = int(batch.coverage_after.get(level, 0))
        if before != after:
            coverage.append(f"{level}: {before}→{after}")
    lines.append("产业链覆盖变化：" + ("；".join(coverage) if coverage else "L1–L8无变化"))

    current_priority = None
    for change in publishable:
        priority = _priority(change)
        if priority != current_priority:
            lines.extend(["", priority])
            current_priority = priority
        payload = change.payload
        lines.append(
            "- {code} {name} | {score}分 | 状态 {before_status} → {after_status} | "
            "阶段 {before_stage} → {after_stage} | 来源 {source} | 证据日期 {date} | 剩余风险 {risk}".format(
                code=payload.get("code", "未知代码"), name=payload.get("company_name", ""),
                score=payload.get("score", 0), before_status=payload.get("before_status", "无"),
                after_status=payload.get("after_status", "无"), before_stage=payload.get("before_stage", "无"),
                after_stage=payload.get("after_stage", "无"), source=payload.get("source", "未提供"),
                date=payload.get("evidence_date", "未提供"), risk=payload.get("remaining_risk", "尚需持续核验"),
            ).rstrip()
        )
    lines.extend(["", "Top3进入：" + ("；".join(batch.top3_entries) if batch.top3_entries else "无"), "Top3退出：" + ("；".join(batch.top3_exits) if batch.top3_exits else "无")])
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


def _index_rows(rows: Sequence[Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    for row in rows:
        data = dict(row) if isinstance(row, Mapping) else dict(vars(row))
        key = (str(data.get("code", "")), str(data.get("node_id", "")))
        result[key] = data
    return result


def _priority(change: EvidenceChange) -> str:
    return str(change.payload.get("priority") or priority_for_score(change.payload.get("score", 0)))
