import os
import sys

import pytest

_PROJ = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
for pkg in ["packages/kronos-factors", "packages/kronos-core", "packages/kronos-data"]:
    path = os.path.join(_PROJ, pkg)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

_TOOLS = os.path.join(_PROJ, "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from kronos_factors.engine.bi_hardtech_v2 import V2Config

from backtest_bi_hardtech_v2 import (
    HISTORICAL_GLOBAL_REGIME,
    audit_sources,
    build_arms,
    count_missing_trade_factor_rows,
    evaluate_acceptance,
    validate_source_audit,
)


class _QueuedDb:
    def __init__(self, responses):
        self._responses = list(responses)
        self._current = None

    def execute(self, sql, params=()):
        assert self._responses, f"unexpected query: {sql} {params}"
        self._current = self._responses.pop(0)
        return self

    def fetchone(self):
        kind, value = self._current
        assert kind == "one"
        return value

    def fetchall(self):
        kind, value = self._current
        assert kind == "all"
        return value


def test_source_audit_rejects_daily_kline_before_requested_end():
    audit = {
        "result_data_end": "2026-07-15",
        "signal_end": "2026-07-08",
        "daily_kline_latest": "2026-07-14",
        "adj_factor_latest": "2026-07-14",
        "adj_factor_missing_trade_rows": 0,
        "sector_latest": "2026-07-08",
    }
    decision = validate_source_audit(audit)
    assert decision["errors"] == ["daily_kline_stale"]
    assert decision["warnings"] == ["adj_factor_lags_result_end"]


def test_audit_sources_warns_for_missing_and_unknown_metadata():
    db = _QueuedDb(
        [
            ("one", {"min_date": "2026-07-01", "max_date": "2026-07-15", "trade_days": 11, "row_count": 1100}),
            ("one", {"min_date": "2026-07-01", "max_date": "2026-07-14", "trade_days": 10, "row_count": 1000}),
            ("one", {"min_date": "2026-07-01", "max_date": "2026-07-08", "trade_days": 6, "row_count": 600}),
            ("one", {"row_count": 123}),
            (
                "all",
                [
                    {
                        "api": "daily",
                        "update_time": "15:30",
                        "update_frequency": "daily",
                        "doc_url": "https://example.com/daily",
                        "extraction_status": "ok",
                        "evidence": "doc",
                        "updated_at": "2026-07-15 16:00:00",
                    },
                    {
                        "api": "adj_factor",
                        "update_time": "unknown",
                        "update_frequency": "daily",
                        "doc_url": "https://example.com/adj",
                        "extraction_status": "unknown",
                        "evidence": "",
                        "updated_at": "2026-07-15 16:00:00",
                    },
                ],
            ),
            (
                "all",
                [
                    {"trade_date": "2026-07-01"},
                    {"trade_date": "2026-07-02"},
                    {"trade_date": "2026-07-03"},
                    {"trade_date": "2026-07-04"},
                    {"trade_date": "2026-07-07"},
                    {"trade_date": "2026-07-08"},
                    {"trade_date": "2026-07-09"},
                    {"trade_date": "2026-07-10"},
                    {"trade_date": "2026-07-13"},
                    {"trade_date": "2026-07-14"},
                    {"trade_date": "2026-07-15"},
                ],
            ),
        ]
    )

    audit = audit_sources(db, "2026-07-01", "2026-07-15")

    assert audit["daily_kline_latest"] == "2026-07-15"
    assert audit["adj_factor_latest"] == "2026-07-14"
    assert audit["sector_latest"] == "2026-07-08"
    assert "metadata_unknown:adj_factor" in audit["source_warnings"]
    assert "metadata_missing:index_daily" in audit["source_warnings"]


def test_missing_trade_factor_rows_only_use_asof_history_not_future_rows():
    missing = count_missing_trade_factor_rows(
        trade_rows=[
            {"code": "000001", "trade_date": "2026-07-02"},
            {"code": "000001", "trade_date": "2026-07-03"},
            {"code": "000002", "trade_date": "2026-07-02"},
        ],
        factor_rows=[
            {"code": "000001", "trade_date": "2026-07-01", "adj_factor": 1.2},
            {"code": "000001", "trade_date": "2026-07-04", "adj_factor": 1.3},
            {"code": "000002", "trade_date": "2026-07-03", "adj_factor": 0.9},
        ],
    )

    assert missing["missing_count"] == 1
    assert missing["missing_rows"] == [{"code": "000002", "trade_date": "2026-07-02"}]


def test_build_arms_uses_explicit_historical_regime_and_treats_rejections_as_data():
    calls = []

    def fake_run_bi_screening(db, signal_date, top_n=20, global_market_regime=None):
        calls.append((signal_date, top_n, global_market_regime))
        if signal_date == "2026-07-01":
            return (
                [{"code": "000001", "name": "A", "weight": 1.0, "sector_change": 1.0}],
                [],
                {"regime": "weak", "env": "weak"},
            )
        return (
            [
                {"code": "000002", "name": "B", "weight": 1.0, "sector_change": 1.0},
                {"code": "000003", "name": "C", "weight": 1.0, "sector_change": 0.5},
                {"code": "000004", "name": "D", "weight": 1.0, "sector_change": 0.2},
            ],
            [],
            {"regime": "neutral", "env": "neutral"},
        )

    import backtest_bi_hardtech_v2 as module

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "run_bi_screening", fake_run_bi_screening)
    monkeypatch.setattr(
        module,
        "next_trade_date",
        lambda db, signal_date: {
            "2026-07-01": "2026-07-02",
            "2026-07-02": "2026-07-03",
        }.get(signal_date),
    )
    monkeypatch.setattr(
        module,
        "confirm_for_next_open",
        lambda db, signal_date, picks, config: (
            picks[:2],
            [{"signal_date": signal_date, "code": picks[2]["code"], "reason": "daily_limit"}],
        ),
    )
    try:
        arms, rejected = build_arms(
            db=None,
            signal_dates=["2026-07-01", "2026-07-02"],
            top_n=3,
            config=V2Config(),
        )
    finally:
        monkeypatch.undo()

    assert calls == [
        ("2026-07-01", 3, HISTORICAL_GLOBAL_REGIME),
        ("2026-07-02", 3, HISTORICAL_GLOBAL_REGIME),
    ]
    assert [row.code for row in arms["baseline"]] == ["000001", "000002", "000003", "000004"]
    assert [row.code for row in arms["v2_a"]] == ["000002", "000003", "000004"]
    assert [row.code for row in arms["v2_b"]] == ["000002", "000003"]
    assert rejected == [
        {"signal_date": "2026-07-01", "code": "000001", "reason": "market_gate"},
        {"signal_date": "2026-07-02", "code": "000004", "reason": "daily_limit"},
    ]


def test_acceptance_requires_all_five_gates():
    decision = evaluate_acceptance(
        {
            "total_trades": 250,
            "total_return_pct": 3.0,
            "max_drawdown_pct": -12.0,
            "worst_month_pct": -7.0,
            "runtime_errors": 0,
        }
    )
    assert decision["passed"] is True
    assert all(decision["gates"].values())


def test_acceptance_fails_profitable_but_overtraded_result():
    decision = evaluate_acceptance(
        {
            "total_trades": 401,
            "total_return_pct": 3.0,
            "max_drawdown_pct": -12.0,
            "worst_month_pct": -7.0,
            "runtime_errors": 0,
        }
    )
    assert decision["passed"] is False
    assert decision["gates"]["annual_trade_count"] is False
