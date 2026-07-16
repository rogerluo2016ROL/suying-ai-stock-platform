from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

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
        "embodied_mapping_conflicts",
        "embodied_mapping_transitions",
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
        "candidate",
        "verified",
        "weak_evidence",
        "rejected",
        "pending_review",
    ):
        assert status in source
    for trace_field in ("source_record_ids", "evidence_fingerprints", "source_names"):
        assert trace_field in source
    assert "attempt_count" in source
    assert "next_retry_at" in source


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
    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection(
        [("run-1", date(2026, 7, 17), "daily", "running", {}, None, None)]
    )
    run = EmbodiedRefreshRepository(conn).begin_run(date(2026, 7, 17), "daily")

    assert any(
        "pg_advisory_xact_lock" in sql
        for sql, _params in conn.cursor_instance.executions
    )
    lock_execution = next(
        execution
        for execution in conn.cursor_instance.executions
        if "pg_advisory_xact_lock" in execution[0]
    )
    assert lock_execution[1] == ("embodied-refresh-run:2026-07-17:daily",)
    assert all("ON CONFLICT" not in sql for sql, _ in conn.cursor_instance.executions)
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

    conn = FakeConnection([None, (1,), (1,)])
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


def test_finish_run_rejects_unknown_run_id():
    from embodied_refresh.repository import EmbodiedRefreshRepository

    conn = FakeConnection()
    with pytest.raises(LookupError, match="missing-run"):
        EmbodiedRefreshRepository(conn).finish_run("missing-run", "failed", {})
    assert conn.rollbacks == 1


@pytest.fixture
def postgres_refresh_schema():
    psycopg2 = pytest.importorskip("psycopg2")
    dsn = "postgresql://kronos:kronos@localhost:6432/kronos"
    schema = f"test_embodied_refresh_{uuid4().hex}"
    admin = psycopg2.connect(dsn)
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        cursor.execute(
            f"""
            CREATE TABLE "{schema}".embodied_refresh_runs (
                run_id TEXT PRIMARY KEY,
                run_date DATE NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                summary JSONB NOT NULL DEFAULT '{{}}',
                started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMPTZ,
                UNIQUE (run_date, mode)
            );
            CREATE TABLE "{schema}".embodied_evidence_changes (
                change_fingerprint TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES "{schema}".embodied_refresh_runs(run_id),
                node_id TEXT NOT NULL,
                change_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def connect():
        connection = psycopg2.connect(dsn)
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.commit()
        return connection

    try:
        yield connect
    finally:
        with admin.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA "{schema}" CASCADE')
        admin.close()


def test_begin_run_is_idempotent_across_chain_ids_under_postgres_concurrency(
    postgres_refresh_schema,
):
    from embodied_refresh.repository import EmbodiedRefreshRepository

    barrier = Barrier(2)

    def begin(chain_id):
        connection = postgres_refresh_schema()
        try:
            barrier.wait()
            return EmbodiedRefreshRepository(connection, chain_id=chain_id).begin_run(
                date(2026, 7, 17), "daily"
            ).run_id
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        run_ids = list(pool.map(begin, ("chain-a", "chain-b")))

    assert len(set(run_ids)) == 1
    connection = postgres_refresh_schema()
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM embodied_refresh_runs")
        assert cursor.fetchone()[0] == 1
    connection.close()


def test_save_changes_deduplicates_under_postgres_concurrency(postgres_refresh_schema):
    from embodied_refresh.models import EvidenceChange
    from embodied_refresh.repository import EmbodiedRefreshRepository

    setup = postgres_refresh_schema()
    run = EmbodiedRefreshRepository(setup).begin_run(date(2026, 7, 17), "daily")
    setup.close()
    barrier = Barrier(2)

    def save():
        connection = postgres_refresh_schema()
        try:
            barrier.wait()
            return EmbodiedRefreshRepository(connection).save_changes(
                [EvidenceChange("same-fingerprint", run.run_id, "node", "added", {})]
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _index: save(), range(2)))

    assert sorted(counts) == [0, 1]
    connection = postgres_refresh_schema()
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM embodied_evidence_changes")
        assert cursor.fetchone()[0] == 1
    connection.close()
