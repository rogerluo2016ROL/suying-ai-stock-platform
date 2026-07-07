from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "backtest_supply_chain_expectation_gap_model.py"
TOOLS_DIR = str(MODULE_PATH.parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
SPEC = importlib.util.spec_from_file_location("backtest_supply_chain_expectation_gap_model", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_summarize_returns_and_compound() -> None:
    summary = module._summarize(
        [
            {"trade_date": "2026-07-02", "return_pct": 1.0},
            {"trade_date": "2026-07-02", "return_pct": -0.5},
            {"trade_date": "2026-07-03", "return_pct": 2.0},
        ]
    )

    assert summary["trade_count"] == 3
    assert summary["signal_days"] == 2
    assert summary["win_rate"] == 66.67
    assert summary["avg_return"] == 0.8333
    assert summary["compound_return"] == 2.255


def test_summarize_empty_records() -> None:
    summary = module._summarize([])

    assert summary["trade_count"] == 0
    assert summary["win_rate"] is None
    assert summary["compound_return"] is None


def test_summarize_by_signal_tier() -> None:
    summary = module._summarize_by_signal_tier(
        [
            {"trade_date": "2026-07-02", "signal_tier": "strong", "return_pct": 1.0},
            {"trade_date": "2026-07-02", "signal_tier": "strong", "return_pct": -0.5},
            {"trade_date": "2026-07-03", "signal_tier": "watch", "return_pct": 2.0},
        ]
    )

    assert summary["strong"]["trade_count"] == 2
    assert summary["strong"]["win_rate"] == 50.0
    assert summary["watch"]["trade_count"] == 1
    assert summary["watch"]["avg_return"] == 2.0
