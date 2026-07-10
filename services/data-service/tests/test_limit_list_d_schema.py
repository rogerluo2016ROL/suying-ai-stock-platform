import importlib.util
from pathlib import Path


def _load_pg_writer():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "services/data-service/app/sync/pg_writer.py"
    spec = importlib.util.spec_from_file_location("pg_writer_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_limit_list_d_uses_ts_code_limit_type_schema(monkeypatch):
    pg_writer = _load_pg_writer()
    captured = {}

    def fake_pg_write(table, columns, conflict_cols, rows):
        captured["table"] = table
        captured["columns"] = columns
        captured["conflict_cols"] = conflict_cols
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(pg_writer, "_pg_write", fake_pg_write)

    written = pg_writer.write_limit_list_d(
        [
            (
                "20260630",
                "300001.SZ",
                "触发科技",
                12.3,
                20.0,
                100_000_000,
                5_000_000_000,
                8.8,
                1_500_000_000,
                "09:25:00",
                "09:30:00",
                0,
                "1/1",
                1,
            )
        ]
    )

    assert written == 1
    assert captured["table"] == "limit_list_d"
    assert captured["columns"] == [
        "trade_date",
        "ts_code",
        "limit_type",
        "name",
        "close",
        "pct_chg",
        "amount",
        "float_mv",
        "turnover_ratio",
        "fd_amount",
        "first_time",
        "last_time",
        "open_times",
        "up_stat",
        "limit_times",
    ]
    assert captured["conflict_cols"] == ["ts_code", "trade_date", "limit_type"]
    assert captured["rows"][0][:4] == ("20260630", "300001.SZ", "U", "触发科技")


def test_init_postgres_limit_list_d_matches_runtime_schema():
    repo_root = Path(__file__).resolve().parents[3]
    sql = (repo_root / "services/sql/init_postgres.sql").read_text(encoding="utf-8")
    start = sql.index("CREATE TABLE IF NOT EXISTS limit_list_d")
    end = sql.index("-- 同花顺每日指标", start)
    block = sql[start:end]

    assert "ts_code TEXT NOT NULL" in block
    assert "trade_date TEXT NOT NULL" in block
    assert "limit_type TEXT NOT NULL" in block
    assert "UNIQUE(ts_code, trade_date, limit_type)" in block
    assert "\n    code TEXT NOT NULL" not in block
    assert "PRIMARY KEY(code, trade_date)" not in block
