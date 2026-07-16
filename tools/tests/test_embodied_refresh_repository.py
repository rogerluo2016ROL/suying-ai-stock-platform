from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).parents[1]))


def test_migration_defines_all_refresh_tables():
    source = Path(
        "backend/alembic/versions/036_embodied_intelligence_daily_refresh.py"
    ).read_text()
    for table in (
        "embodied_refresh_runs",
        "embodied_source_cursors",
        "embodied_evidence_changes",
        "embodied_leader_snapshots",
        "embodied_delivery_records",
    ):
        assert table in source


def test_migration_defines_required_constraints_and_statuses():
    source = Path(
        "backend/alembic/versions/036_embodied_intelligence_daily_refresh.py"
    ).read_text()
    for constraint in (
        "uq_embodied_run_date_mode",
        "uq_embodied_cursor_source",
        "uq_embodied_change_fingerprint",
        "uq_embodied_snapshot_rank",
        "uq_embodied_delivery_target",
    ):
        assert constraint in source
    for status in (
        "running",
        "success",
        "data_success_delivery_incomplete",
        "failed",
        "pending",
        "confirmed",
        "unconfirmed",
    ):
        assert status in source


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executions = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=()):
        self.executions.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows=()):
        self.cursor_instance = FakeCursor(rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self, **_kwargs):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_begin_run_returns_idempotent_batch():
    from datetime import date

    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection(
        [("run-1", date(2026, 7, 17), "daily", "running", {}, None, None)]
    )
    run = EmbodiedRefreshRepository(conn).begin_run(date(2026, 7, 17), "daily")

    sql, params = conn.cursor_instance.executions[0]
    assert "ON CONFLICT" not in sql
    assert params[:2] == (date(2026, 7, 17), "daily")
    assert params[3:] == (
        date(2026, 7, 17),
        "daily",
    )
    assert run.run_id == "run-1"
    assert conn.commits == 1


def test_load_success_baseline_only_returns_earlier_success():
    from datetime import date

    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection(
        [("run-0", date(2026, 7, 16), "daily", "success", {}, None, None)]
    )
    run = EmbodiedRefreshRepository(conn).load_success_baseline("run-1")

    sql, params = conn.cursor_instance.executions[0]
    assert "status = 'success'" in sql
    assert "run_date <" in sql
    assert params == ("run-1",)
    assert run and run.run_id == "run-0"


def test_save_cursor_uses_upsert_and_commits():
    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection()
    EmbodiedRefreshRepository(conn, chain_id="embodied").save_cursor(
        "exchange", "2026-07-17T15:00:00", "run-1"
    )

    sql, params = conn.cursor_instance.executions[0]
    assert "ON CONFLICT (chain_id, source_name) DO UPDATE" in sql
    assert params == ("embodied", "exchange", "2026-07-17T15:00:00", "run-1")
    assert conn.commits == 1


def test_save_changes_inserts_fingerprints_without_upsert():
    from embodied_refresh.models import EvidenceChange
    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection([(1,), None])
    changes = [
        EvidenceChange("fp-1", "run-1", "node-1", "added", {"x": 1}),
        EvidenceChange("fp-2", "run-1", "node-2", "updated", {"x": 2}),
    ]
    inserted = EmbodiedRefreshRepository(conn).save_changes(changes)

    assert inserted == 1
    assert all("ON CONFLICT" not in sql for sql, _ in conn.cursor_instance.executions)
    assert conn.commits == 1


def test_finish_run_rejects_non_terminal_status():
    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection()
    with pytest.raises(ValueError, match="terminal"):
        EmbodiedRefreshRepository(conn).finish_run("run-1", "running", {})
    assert not conn.cursor_instance.executions
