from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "backfill_supply_chain_expectation_gap_history.py"
TOOLS_DIR = str(MODULE_PATH.parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)
SPEC = importlib.util.spec_from_file_location("backfill_supply_chain_expectation_gap_history", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_calculate_gap_momentum_rewards_recent_improvement() -> None:
    assert module.calculate_gap_momentum_score(current_gap=12, previous_gap=6, gap_20d_ago=4) > 60


def test_calculate_gap_momentum_penalizes_deterioration() -> None:
    assert module.calculate_gap_momentum_score(current_gap=4, previous_gap=10, gap_20d_ago=12) < 40
