from pathlib import Path
import os
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=()):
        if sql.startswith(("SAVEPOINT", "ROLLBACK TO SAVEPOINT", "RELEASE SAVEPOINT")):
            self.connection.transaction_sql.append(sql)
            return
        source = next(name for name, spec in self.connection.specs.items() if spec.table in sql)
        self.connection.calls.append((source, params))
        if source in self.connection.failures:
            raise RuntimeError(f"{source} unavailable")
        self.rows = self.connection.rows.get(source, [])

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows=None, failures=()):
        from embodied_refresh.sources import SOURCE_SPECS

        self.specs = SOURCE_SPECS
        self.rows = rows or {}
        self.failures = set(failures)
        self.calls = []
        self.rollbacks = 0
        self.transaction_sql = []

    def cursor(self, **_kwargs):
        return FakeCursor(self)

    def rollback(self):
        self.rollbacks += 1


def test_incremental_fetch_uses_each_source_cursor():
    from embodied_refresh.sources import fetch_incremental_sources

    db = FakeConnection()
    result = fetch_incremental_sources(
        db, {"announcement": "2026-07-15", "interact_qa": "2026-07-14"}
    )
    assert result.queries["announcement"].since == "2026-07-15"
    assert result.queries["interact_qa"].since == "2026-07-14"


def test_failed_source_does_not_advance_cursor_or_hide_failure():
    from embodied_refresh.sources import fetch_incremental_sources

    result = fetch_incremental_sources(FakeConnection(failures={"research"}), {})
    assert "research" not in result.next_cursors
    assert "research" in result.errors


def test_successful_source_advances_to_max_observed_cursor():
    from embodied_refresh.sources import fetch_incremental_sources

    db = FakeConnection(rows={"announcement": [{"source_cursor": "2026-07-16"}, {"source_cursor": "2026-07-17"}]})
    result = fetch_incremental_sources(db, {"announcement": "2026-07-15"})
    assert result.next_cursors["announcement"] == "2026-07-17"


def test_main_business_uses_real_end_date_cursor_schema_contract():
    from embodied_refresh.sources import SOURCE_SPECS

    assert SOURCE_SPECS["main_business"].cursor_column == "end_date"


def test_local_fina_mainbz_schema_has_configured_cursor_column():
    dsn = os.environ.get("KRONOS_PG_URL")
    if not dsn:
        pytest.skip("set KRONOS_PG_URL to run live schema integration")
    psycopg2 = pytest.importorskip("psycopg2")
    from embodied_refresh.sources import SOURCE_SPECS

    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name FROM information_schema.columns
                 WHERE table_name = 'fina_mainbz'
                """
            )
            columns = {row[0] for row in cursor.fetchall()}
    finally:
        connection.close()
    assert SOURCE_SPECS["main_business"].cursor_column in columns


def test_external_connection_failure_isolated_by_savepoint_without_global_rollback():
    from embodied_refresh.sources import fetch_incremental_sources

    db = FakeConnection(failures={"research"})
    result = fetch_incremental_sources(db, {})
    assert "research" in result.errors
    assert db.rollbacks == 0
    assert any(sql.startswith("ROLLBACK TO SAVEPOINT") for sql in db.transaction_sql)
    assert "profile" in result.rows
