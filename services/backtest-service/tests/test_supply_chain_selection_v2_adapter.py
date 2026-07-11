"""Strict return and pool contracts for supply-chain selection V2."""

from datetime import date

import pytest

from app.adapters.base import BacktestRequest
from app.adapters.supply_chain_selection_v2 import (
    SupplyChainSelectionV2Adapter,
    normalize_stock_code,
)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, statement, params=None):
        self.executed.append((statement, params))

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeConnection:
    def __init__(self, rows):
        self.cursor_instance = FakeCursor(rows)
        self.closed = False

    def cursor(self, **kwargs):
        return self.cursor_instance

    def close(self):
        self.closed = True


@pytest.fixture
def fake_connection():
    return FakeConnection(
        [
            {
                "trade_date": date(2026, 7, 1),
                "stock_code": "300001.SZ",
                "factors": {
                    "pool_code": "A",
                    "benefit_score": 70,
                    "chain_id": "dexterous_hand",
                },
                "entry_date": date(2026, 7, 2),
                "entry_open": 10,
                "entry_adj": 2,
                "exit_close": 12,
                "exit_adj": 2.1,
                "chain_id": "dexterous_hand",
            },
            {
                "trade_date": date(2026, 7, 1),
                "stock_code": "600001.SH",
                "factors": {"pool_code": "B", "benefit_score": 60},
                "entry_date": date(2026, 7, 2),
                "entry_open": 10,
                "entry_adj": None,
                "exit_close": 11,
                "exit_adj": 2,
                "chain_id": "dexterous_hand",
            },
            {
                "trade_date": date(2026, 7, 1),
                "stock_code": "000001.SZ",
                "factors": {"pool_code": "D", "benefit_score": 90},
                "entry_date": date(2026, 7, 2),
                "entry_open": 10,
                "entry_adj": 1,
                "exit_close": 20,
                "exit_adj": 1,
                "chain_id": "dexterous_hand",
            },
        ]
    )


def test_normalize_stock_code_removes_exchange_suffix():
    assert normalize_stock_code("300001.SZ") == "300001"
    assert normalize_stock_code("688001") == "688001"


def test_adapter_registers_expected_model_key():
    assert (
        SupplyChainSelectionV2Adapter.model_key
        == "supply_chain_research_selection_v2"
    )


def test_pool_metrics_never_include_d_pool(fake_connection):
    report = SupplyChainSelectionV2Adapter().run(
        BacktestRequest(
            model_key="supply_chain_research_selection_v2",
            forward_days=5,
            cost_bps=14,
            min_periods=1,
            min_per_day=1,
            min_observations=1,
            connection_factory=lambda: fake_connection,
        ),
        readiness={"status": "ready"},
    )

    assert "D" not in report["by_pool"]
    assert report["by_pool"]["A"]["mean_return"] == pytest.approx(0.2586)
    assert report["coverage"]["missing_adj_factor_count"] == 1
    assert report["coverage"]["return_rows"] == 1
    assert report["execution_assumption"] == (
        "T+1 open to future adjusted close, 14.0 bps cost"
    )
    sql, params = fake_connection.cursor_instance.executed[0]
    assert "k.trade_date > s.trade_date" in sql
    assert "split_part(s.stock_code, '.', 1)" in sql
    assert "IN ('A','B','C')" in sql
    assert params == (4, "supply_chain_research_selection_v2")
    assert fake_connection.closed is True


def test_adapter_reports_insufficient_evidence_without_adjustment_factors():
    connection = FakeConnection(
        [
            {
                "trade_date": date(2026, 7, 1),
                "stock_code": "300001",
                "factors": {"pool_code": "A"},
                "entry_date": date(2026, 7, 2),
                "entry_open": 10,
                "entry_adj": None,
                "exit_close": 11,
                "exit_adj": None,
                "chain_id": "dexterous_hand",
            }
        ]
    )

    report = SupplyChainSelectionV2Adapter().run(
        BacktestRequest(
            model_key="supply_chain_research_selection_v2",
            min_periods=1,
            min_per_day=1,
            min_observations=1,
            connection_factory=lambda: connection,
        ),
        readiness={"status": "ready"},
    )

    assert report["status"] == "INSUFFICIENT_EVIDENCE"
    assert report["coverage"]["return_rows"] == 0
    assert "adjusted return rows" in report["insufficient_reason"]
