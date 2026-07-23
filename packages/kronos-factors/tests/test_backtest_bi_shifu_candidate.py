from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


def _module():
    path = Path(__file__).resolve().parents[3] / "tools" / "backtest_bi_shifu_trend_1y.py"
    spec = spec_from_file_location("backtest_bi_shifu_trend_1y", path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_entry_gap_accepts_only_the_configured_window():
    module = _module()

    assert module.entry_gap_allowed(-2.0, -2.0, 0.5)
    assert module.entry_gap_allowed(0.5, -2.0, 0.5)
    assert not module.entry_gap_allowed(-2.01, -2.0, 0.5)
    assert not module.entry_gap_allowed(0.51, -2.0, 0.5)


def test_candidate_cli_flag_is_parseable(monkeypatch):
    module = _module()
    monkeypatch.setattr(sys, "argv", ["backtest", "--candidate-v23"])

    assert module.parse_args().candidate_v23 is True


def test_rule_replay_variants_have_distinct_historical_gates():
    module = _module()

    assert module.variant_settings("v20") == {
        "macd_below_min_days": 0,
        "min_score": 0.0,
        "near_high_max_pct": -0.99,
        "obv_leading_price": False,
    }
    assert module.variant_settings("v22") == {
        "macd_below_min_days": 3,
        "min_score": 0.0,
        "near_high_max_pct": -0.04,
        "obv_leading_price": True,
    }


def test_pending_signal_dates_keeps_cached_dates_out_of_the_work_queue():
    module = _module()

    assert module.pending_signal_dates(["2026-01-01", "2026-01-02", "2026-01-03"], {"2026-01-02": []}) == [
        "2026-01-01",
        "2026-01-03",
    ]


def test_position_batch_requires_positive_budget():
    module = _module()

    assert module.has_opening_budget(0.01)
    assert not module.has_opening_budget(0.0)


def test_open_gap_stop_releases_cash_before_new_entries():
    module = _module()
    position = module.Position(
        code="000001", name="测试", signal_date="2026-01-01", entry_date="2026-01-02",
        exit_date="2026-01-03", entry_adj=10.0, stop_adj=9.0, shares=100.0,
        buy_notional=1000.0, score=10.0, grade="B",
    )

    result = module.open_gap_stop(position, {"open": 8.5, "low": 8.0, "close": 8.2, "adj_factor": 1.0}, 0.001)

    assert result is not None
    proceeds, reason, gross_return = result
    assert proceeds == pytest.approx(849.15)
    assert reason == "gap_stop"
    assert gross_return == pytest.approx(-0.15)
