from pathlib import Path
import sys

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
