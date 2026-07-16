from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from run_research_pipeline import extract_message_id

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
    return {"error": f"{type(exc).__name__}: {exc}"[-500:]}


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
    for target in targets:
        chat_id = str(target.get("chat_id") or "").strip()
        if not chat_id:
            continue
        existing = repository.delivery(batch_id, chat_id)
        if existing and existing.status == "confirmed":
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
        }
        try:
            if not message_id:
                message_id = extract_message_id(sender(chat_id, message)) or None
                if not message_id:
                    detail["error"] = "missing_message_id"
            if message_id and confirmer(chat_id, message_id):
                status = "confirmed"
                detail.pop("error", None)
            elif message_id:
                detail["error"] = "message_not_confirmed"
        except Exception as exc:
            detail.update(_error_detail(exc))

        delay = RETRY_DELAYS[attempts - 1] if attempts <= len(RETRY_DELAYS) else None
        repository.save_delivery(
            DeliveryRecord(
                delivery_id=existing.delivery_id if existing else str(uuid4()),
                change_batch_id=batch_id,
                chat_id=chat_id,
                status=status,
                message_id=message_id,
                detail=detail,
                attempt_count=attempts,
                next_retry_at=current_time + delay if status != "confirmed" and delay else None,
            )
        )

    rows = repository.deliveries(batch_id)
    confirmed = sum(row.status == "confirmed" for row in rows)
    total = len({str(target.get("chat_id") or "").strip() for target in targets if target.get("chat_id")})
    status = "success" if total > 0 and confirmed == total else "data_success_delivery_incomplete"
    summary = DeliverySummary(batch_id, total, confirmed, total - confirmed, status)
    repository.finish_run(batch_id, status, {
        "delivery_total": total,
        "delivery_confirmed": confirmed,
        "delivery_pending": total - confirmed,
    })
    return summary
