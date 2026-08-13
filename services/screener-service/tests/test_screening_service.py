"""screening/service.py 纯函数/日期解析契约测试。

覆盖此前无专属测试的核心辅助函数 `_resolve_trade_date` / `_resolve_intraday_trade_date`：
- 给定具体日期直接返回（早返回，不触 DB）
- "latest" 走 DB 取最新交易日
- DB 失败时显式抛 RuntimeError（而非静默降级）
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domains.screening import service as svc


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row

    def execute(self, sql):
        return _FakeResult(self._row)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_resolve_trade_date_returns_concrete_date_without_db():
    # 具体日期早返回，不触 DB（无需 mock）
    assert svc._resolve_trade_date("2026-01-15") == "2026-01-15"


def test_resolve_trade_date_latest_queries_db(monkeypatch):
    monkeypatch.setattr(svc, "_get_factor_db", lambda: _FakeDB(("2026-08-12",)))
    assert svc._resolve_trade_date("latest") == "2026-08-12"


def test_resolve_trade_date_latest_db_failure_raises(monkeypatch):
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "_get_factor_db", _boom)
    with pytest.raises(RuntimeError):
        svc._resolve_trade_date("latest")


def test_resolve_intraday_trade_date_returns_concrete_date_without_db():
    assert svc._resolve_intraday_trade_date("2026-07-01") == "2026-07-01"


def test_resolve_intraday_trade_date_falls_back_to_daily_when_mins_empty(monkeypatch):
    # stk_mins 查询返回空 → 回退 _resolve_trade_date
    monkeypatch.setattr(svc, "_get_factor_db", lambda: _FakeDB(None))
    monkeypatch.setattr(svc, "_resolve_trade_date", lambda td: "2026-08-11")
    assert svc._resolve_intraday_trade_date("latest") == "2026-08-11"
