from app.market_strength import compute_market_strength, load_market_strength


def test_compute_market_strength_uses_snapshot_rows():
    rows = [
        {
            "code": "000001",
            "snapshot_time": "2026-07-14 14:00:00",
            "close": 10.5,
            "pre_close": 10.0,
        },
        {
            "code": "000002",
            "snapshot_time": "2026-07-14 14:00:00",
            "close": 9.0,
            "pre_close": 10.0,
        },
        {
            "code": "000003",
            "snapshot_time": "2026-07-14 14:00:00",
            "close": 10.1,
            "pre_close": 10.0,
        },
    ]

    result = compute_market_strength(
        "2026-07-14",
        "14:00",
        rows,
        minimum_coverage=3,
    )

    assert result["status"] == "ok"
    assert result["snapshot_time"] == "2026-07-14 14:00:00"
    assert result["advancers"] == 2
    assert result["decliners"] == 1
    assert result["above_5pct"] == 1
    assert result["below_minus_5pct"] == 1
    assert result["median_pct"] == 1.0


def test_compute_market_strength_reports_insufficient_coverage():
    result = compute_market_strength(
        "2026-07-14",
        "14:00",
        [{"code": "000001", "snapshot_time": "2026-07-14 14:00:00", "close": 10.5, "pre_close": 10.0}],
        minimum_coverage=100,
    )

    assert result == {
        "status": "insufficient",
        "scope": "intraday_market_breadth",
        "trade_date": "2026-07-14",
        "cutoff_time": "14:00",
        "snapshot_time": "2026-07-14 14:00:00",
        "coverage": 1,
        "reason": "有效股票数 1 低于最低要求 100",
    }


class _FakeCursor:
    description = [
        ("code",),
        ("snapshot_time",),
        ("close",),
        ("pre_close",),
    ]

    def __init__(self):
        self.sql = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return [
            ("000001", "2026-07-14 14:00:00", 10.5, 10.0),
            ("000002", "2026-07-14 14:00:00", 9.0, 10.0),
        ]


class _FakeConnection:
    def __init__(self):
        self.cursor_instance = _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return self.cursor_instance


def test_load_market_strength_queries_latest_snapshot_before_cutoff():
    connection = _FakeConnection()

    result = load_market_strength(
        "2026-07-14",
        "14:00",
        "postgresql://example",
        minimum_coverage=2,
        connect=lambda _dsn: connection,
    )

    assert result["status"] == "ok"
    assert result["coverage"] == 2
    assert "stk_mins" in connection.cursor_instance.sql
    assert "m.trade_time >= %s" in connection.cursor_instance.sql
    assert "stk_auction_o" in connection.cursor_instance.sql
    assert "daily_kline" in connection.cursor_instance.sql
    assert connection.cursor_instance.params == (
        "2026-07-14 00:00:00",
        "2026-07-14 14:00:59",
        "2026-07-14",
        "2026-07-14",
    )
