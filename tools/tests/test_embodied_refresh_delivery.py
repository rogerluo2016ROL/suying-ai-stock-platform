from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parents[1]))

from embodied_refresh.delivery import deliver_change_batch


TARGETS = [
    {"chat_id": "oc_success", "name": "A"},
    {"chat_id": "oc_second", "name": "B"},
    {"chat_id": "oc_third", "name": "C"},
]


class MemoryRepository:
    def __init__(self):
        self.rows = {}
        self.run_status = None

    def delivery(self, batch_id, chat_id):
        return self.rows.get((batch_id, chat_id))

    def save_delivery(self, record):
        self.rows[(record.change_batch_id, record.chat_id)] = record

    def deliveries(self, batch_id):
        return [row for (saved_batch, _), row in self.rows.items() if saved_batch == batch_id]

    def finish_run(self, run_id, status, summary):
        self.run_status = status


def test_three_groups_require_individual_message_ids():
    repository = MemoryRepository()

    summary = deliver_change_batch(
        repository,
        "batch-1",
        TARGETS,
        "digest",
        lambda chat_id, _message: {"data": {"message_id": "om_" + chat_id}},
        lambda _chat_id, _message_id: True,
    )

    assert summary.confirmed == 3
    assert len({row.message_id for row in repository.deliveries("batch-1")}) == 3
    assert repository.run_status == "success"


def test_successful_group_is_not_resent_on_retry():
    repository = MemoryRepository()
    calls = Counter()

    def partial_sender(chat_id, _message):
        calls[chat_id] += 1
        if chat_id != "oc_success":
            raise RuntimeError("temporary")
        return {"message_id": "om_success"}

    now = datetime(2026, 7, 17, tzinfo=timezone.utc)
    deliver_change_batch(repository, "batch-2", TARGETS, "digest", partial_sender, lambda *_: True, now=now)
    summary = deliver_change_batch(repository, "batch-2", TARGETS, "digest", partial_sender, lambda *_: True, now=now)

    assert calls["oc_success"] == 1
    assert calls["oc_second"] == 1
    assert summary.status == "data_success_delivery_incomplete"
    assert repository.run_status == "data_success_delivery_incomplete"


def test_retry_backoff_is_5_15_30_minutes_without_sleep():
    repository = MemoryRepository()
    calls = Counter()

    def failing_sender(chat_id, _message):
        calls[chat_id] += 1
        raise RuntimeError("temporary")

    target = [{"chat_id": "oc_fail"}]
    times = [
        datetime(2026, 7, 17, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 17, 0, 5, tzinfo=timezone.utc),
        datetime(2026, 7, 17, 0, 20, tzinfo=timezone.utc),
        datetime(2026, 7, 17, 0, 50, tzinfo=timezone.utc),
    ]
    expected_next = ["00:05", "00:20", "00:50", None]
    for now, next_hm in zip(times, expected_next):
        deliver_change_batch(repository, "batch-3", target, "digest", failing_sender, lambda *_: True, now=now)
        row = repository.delivery("batch-3", "oc_fail")
        assert row.next_retry_at is None if next_hm is None else row.next_retry_at.strftime("%H:%M") == next_hm

    assert calls["oc_fail"] == 4
    assert repository.delivery("batch-3", "oc_fail").attempt_count == 4

    deliver_change_batch(
        repository,
        "batch-3",
        target,
        "digest",
        failing_sender,
        lambda *_: True,
        now=datetime(2026, 7, 17, 1, 50, tzinfo=timezone.utc),
    )
    assert calls["oc_fail"] == 4


def test_message_id_is_reconfirmed_without_resending():
    repository = MemoryRepository()
    sender_calls = Counter()
    confirmations = iter([False, True])

    def sender(chat_id, _message):
        sender_calls[chat_id] += 1
        return {"message_id": "om_existing"}

    start = datetime(2026, 7, 17, tzinfo=timezone.utc)
    deliver_change_batch(repository, "batch-4", [{"chat_id": "oc_a"}], "digest", sender, lambda *_: next(confirmations), now=start)
    deliver_change_batch(repository, "batch-4", [{"chat_id": "oc_a"}], "digest", sender, lambda *_: next(confirmations), now=start.replace(minute=5))

    assert sender_calls["oc_a"] == 1
    assert repository.delivery("batch-4", "oc_a").status == "confirmed"
