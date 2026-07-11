from app.quality import repository


class _Snapshot:
    def to_dict(self):
        return {
            "profile": "backtest_v1",
            "target_trade_date": "2026-07-10",
            "cutoff_time": None,
            "status": "ready",
            "sources": [{"source": "daily_kline", "status": "ready"}],
        }


class _Cursor:
    def __init__(self, row=None):
        self.row = row
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row=None):
        self.cursor_instance = _Cursor(row)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_save_persists_readiness_snapshot(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.save(_Snapshot())

    assert result["status"] == "ready"
    assert result["snapshot_id"]
    assert "INSERT INTO data_readiness_snapshots" in connection.cursor_instance.calls[0][0]
    assert connection.committed and connection.closed


def test_get_reads_persisted_snapshot(monkeypatch):
    connection = _Connection(
        ("SNAP-1", "backtest_v1", "2026-07-10", None, "ready", [{"source": "daily_kline"}])
    )
    monkeypatch.setattr(repository, "_connect", lambda: connection)

    result = repository.get("SNAP-1")

    assert result == {
        "snapshot_id": "SNAP-1",
        "profile": "backtest_v1",
        "target_trade_date": "2026-07-10",
        "cutoff_time": None,
        "status": "ready",
        "sources": [{"source": "daily_kline"}],
    }
    assert "FROM data_readiness_snapshots" in connection.cursor_instance.calls[0][0]
    assert connection.closed
