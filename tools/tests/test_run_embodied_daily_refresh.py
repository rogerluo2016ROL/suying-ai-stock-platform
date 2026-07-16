from datetime import date

import pytest

from run_embodied_daily_refresh import EmbodiedRefreshOrchestrator


class FakeRepository:
    def __init__(self, events):
        self.events = events

    def begin_run(self, run_date, mode):
        self.events.append("begin")
        return type("Run", (), {"run_id": "run-1"})()

    def load_cursors(self):
        self.events.append("load_cursors")
        return {"announcement": "old"}

    def load_success_baseline(self, run_id):
        self.events.append("baseline")
        return {"status": "success", "mappings": []}

    def save_changes(self, changes):
        self.events.append("persist")
        return len(changes)

    def save_snapshot(self, run_id, snapshot):
        self.events.append("snapshot")

    def save_cursor(self, source, cursor, run_id):
        self.events.append(f"cursor:{source}")

    def finish_run(self, run_id, status, summary):
        self.events.append(f"finish:{status}")


def make_orchestrator(events, *, mapping_error=False):
    repository = FakeRepository(events)

    def refresh(cursors, as_of_date):
        events.append("refresh")
        return type("Refresh", (), {
            "rows": {"announcement": [{"content": "x"}]},
            "next_cursors": {"announcement": "new"},
            "errors": {"research": "unavailable"},
        })()

    def normalize(rows):
        events.append("normalize")
        return ["evidence"]

    def apply(evidence, run_id, as_of_date):
        events.append("mapping")
        if mapping_error:
            raise RuntimeError("mapping failed")
        return ["mapped"]

    def rollback():
        events.append("rollback")

    def audit(run_id, mappings, mode):
        events.append("audit")
        return {"run_id": run_id, "mappings": mappings}

    def diff(baseline, snapshot):
        events.append("diff")
        return [{"payload": {"priority": "P3"}}]

    def deliver(*_args):
        events.append("deliver")

    return EmbodiedRefreshOrchestrator(
        repository=repository,
        refresh_sources=refresh,
        normalize_evidence=normalize,
        apply_mappings=apply,
        rollback_mappings=rollback,
        audit_and_rank=audit,
        diff_baseline=diff,
        deliver_changes=deliver,
    )


def test_dry_run_never_writes_or_sends():
    events = []
    result = make_orchestrator(events).run(mode="dry-run", as_of_date="2026-07-16")

    assert result.persisted is False
    assert result.delivery_attempted is False
    assert "begin" not in events
    assert "persist" not in events
    assert "mapping" not in events


def test_apply_obeys_transaction_sequence_and_only_advances_successful_cursors():
    events = []
    result = make_orchestrator(events).run(mode="apply", as_of_date=date(2026, 7, 16))

    assert result.persisted is True
    assert result.delivery_attempted is False
    assert events == [
        "begin", "load_cursors", "refresh", "normalize", "mapping", "audit",
        "baseline", "diff", "persist", "snapshot", "cursor:announcement", "finish:success",
    ]


def test_mapping_failure_rolls_back_and_never_persists_or_delivers():
    events = []
    with pytest.raises(RuntimeError, match="mapping failed"):
        make_orchestrator(events, mapping_error=True).run(mode="apply", as_of_date="2026-07-16")

    assert events == ["begin", "load_cursors", "refresh", "normalize", "mapping", "rollback", "finish:failed"]
    assert "persist" not in events
    assert "deliver" not in events
