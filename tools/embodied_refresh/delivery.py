from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from inspect import signature
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid4, uuid5

from run_research_pipeline import extract_message_id, sanitize_delivery_error

from .models import DeliveryRecord


RETRY_DELAYS = (timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=30))


@dataclass(frozen=True)
class DeliverySummary:
    batch_id: str
    total: int
    confirmed: int
    pending: int
    status: str


def _error_detail(exc: Exception) -> dict[str, str]:
    return {"error": sanitize_delivery_error(exc)}


def _normalize_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = [{**target, "chat_id": str(target.get("chat_id") or "").strip()} for target in targets]
    chat_ids = [target["chat_id"] for target in normalized]
    if len(chat_ids) != 3 or any(not chat_id for chat_id in chat_ids) or len(set(chat_ids)) != 3:
        raise ValueError("targets must contain exactly three unique non-empty chat_id values")
    return normalized


def _send(sender: Callable[..., Any], chat_id: str, message: str, key: str) -> Any:
    try:
        parameters = signature(sender).parameters.values()
    except (TypeError, ValueError):
        return sender(chat_id, message)
    if any(parameter.name == "idempotency_key" or parameter.kind.name == "VAR_KEYWORD" for parameter in parameters):
        return sender(chat_id, message, idempotency_key=key)
    return sender(chat_id, message)


def scan_due_deliveries(repository: Any, *, now: datetime | None = None) -> list[DeliveryRecord]:
    current_time = now or datetime.now(timezone.utc)
    return [row for row in repository.due_deliveries(current_time) if row.status in {"failed", "unconfirmed", "pending", "sending", "reconcile_required"}]


def deliver_change_batch(
    repository: Any,
    batch_id: str,
    targets: list[dict[str, str]],
    message: str,
    sender: Callable[[str, str], Any],
    confirmer: Callable[[str, str], bool],
    *,
    now: datetime | None = None,
) -> DeliverySummary:
    """Attempt each due target once; retries are driven by later invocations."""
    current_time = now or datetime.now(timezone.utc)
    normalized_targets = _normalize_targets(targets)
    keys = {target["chat_id"]: str(uuid5(NAMESPACE_URL, f"embodied:{batch_id}:{target['chat_id']}")) for target in normalized_targets}
    repository.initialize_deliveries(batch_id, normalized_targets, message, current_time, idempotency_keys=keys)
    for target in normalized_targets:
        chat_id = target["chat_id"]
        with repository.claim_delivery(batch_id, target, current_time) as existing:
            if existing is None:
                continue
            if existing and existing.attempt_count >= len(RETRY_DELAYS) + 1:
                continue
            if existing and existing.next_retry_at and existing.next_retry_at > current_time:
                continue

            attempts = (existing.attempt_count if existing else 0) + 1
            message_id = existing.message_id if existing else None
            status = "unconfirmed"
            detail: dict[str, Any] = {
                "target_key": target.get("key") or "",
                "target_name": target.get("name") or "",
                "target_chat_id": chat_id,
                "message": message,
            }
            try:
                if not message_id:
                    message_id = extract_message_id(_send(sender, chat_id, message, keys[chat_id])) or None
                    if not message_id:
                        detail["error"] = "missing_message_id"
                if message_id and confirmer(chat_id, message_id):
                    status = "confirmed"
                    detail.pop("error", None)
                elif message_id:
                    detail["error"] = "message_not_confirmed"
            except Exception as exc:
                status = "failed" if not message_id else "unconfirmed"
                detail.update(_error_detail(exc))

            delay = RETRY_DELAYS[attempts - 1] if attempts <= len(RETRY_DELAYS) else None
            repository.save_delivery(DeliveryRecord(
                delivery_id=existing.delivery_id if existing else str(uuid4()),
                change_batch_id=batch_id, chat_id=chat_id, status=status,
                message_id=message_id, detail=detail, attempt_count=attempts,
                next_retry_at=current_time + delay if status != "confirmed" and delay else None,
            ))

    rows = repository.deliveries(batch_id)
    confirmed = sum(row.status == "confirmed" for row in rows)
    total = 3
    status = "success" if total > 0 and confirmed == total else "data_success_delivery_incomplete"
    summary = DeliverySummary(batch_id, total, confirmed, total - confirmed, status)
    return summary


def retry_due_batches(
    repository: Any,
    sender: Callable[..., Any],
    confirmer: Callable[[str, str], bool],
    *,
    now: datetime | None = None,
) -> list[DeliverySummary]:
    """Compensate due batches once; the scheduler may invoke this every five minutes."""
    summaries = []
    for batch_id in sorted({row.change_batch_id for row in scan_due_deliveries(repository, now=now)}):
        rows = repository.deliveries(batch_id)
        targets = [{"key": row.detail.get("target_key", ""), "name": row.detail.get("target_name", ""), "chat_id": row.chat_id} for row in rows]
        messages = {row.detail.get("message") for row in rows if row.detail.get("message") is not None}
        if len(targets) != 3 or len(messages) != 1:
            continue
        summary = deliver_change_batch(repository, batch_id, targets, messages.pop(), sender, confirmer, now=now)
        if summary.status == "success":
            repository.complete_delivery_run(batch_id, summary)
        summaries.append(summary)
    return summaries
