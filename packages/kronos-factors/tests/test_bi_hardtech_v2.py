from unittest.mock import patch

import pytest

from kronos_factors.engine import bi_trend_launch
from kronos_factors.engine.bi_hardtech_v2 import (
    V2Config,
    confirm_t1_open,
    market_allows_entry,
    select_daily_entries,
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


@pytest.mark.parametrize(
    "regime,allowed",
    [
        ("bull", True),
        ("neutral", True),
        ("weak", False),
        ("recovery", False),
        ("bear", False),
        ("crash", False),
    ],
)
def test_market_gate(regime, allowed):
    assert market_allows_entry(regime) is allowed


@pytest.mark.parametrize(
    "open_price,accepted,reason",
    [
        (98.49, False, "gap_below_min"),
        (98.50, True, "accepted"),
        (103.00, True, "accepted"),
        (103.01, False, "gap_above_max"),
    ],
)
def test_open_gap_boundaries(open_price, accepted, reason):
    decision = confirm_t1_open(100.0, open_price, 0.1, V2Config())
    assert decision.accepted is accepted
    assert decision.reason == reason


def test_missing_or_negative_sector_rejects_entry():
    assert confirm_t1_open(100.0, 100.0, None, V2Config()).reason == "sector_missing"
    assert confirm_t1_open(100.0, 100.0, -0.01, V2Config()).reason == "sector_negative"
    assert confirm_t1_open(100.0, 100.0, 0.0, V2Config()).accepted is True


def test_daily_entries_keep_baseline_order_and_cap_at_two():
    picks = [
        {"code": "000001", "sector_change": 1.0},
        {"code": "000002", "sector_change": 0.5},
        {"code": "000003", "sector_change": 0.2},
    ]
    selected, rejected = select_daily_entries(
        picks,
        open_by_code={p["code"]: 100.0 for p in picks},
        close_by_code={p["code"]: 100.0 for p in picks},
        config=V2Config(),
    )
    assert [p["code"] for p in selected] == ["000001", "000002"]
    assert selected[0]["confirmation_reason"] == "accepted"
    assert rejected[-1]["confirmation_reason"] == "daily_limit"


def test_explicit_historical_regime_skips_current_regime_lookup():
    explicit = {"regime": "neutral", "bonus": 0.0}
    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        side_effect=AssertionError("current regime must not be read"),
    ):
        regime, source = bi_trend_launch._resolve_global_market_regime(explicit)
    assert regime == explicit
    assert source == "explicit"


def test_default_regime_keeps_runtime_lookup():
    expected = {"regime": "bull", "bonus": 0.1}
    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        return_value=expected,
    ) as lookup:
        regime, source = bi_trend_launch._resolve_global_market_regime(None)
    lookup.assert_called_once_with()
    assert regime == expected
    assert source == "current_runtime"


def test_run_bi_screening_no_prev_trade_date_keeps_return_contract():
    db = _QueuedDb([("one", None)])
    explicit = {"regime": "neutral", "bonus": 0.0}

    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        side_effect=AssertionError("current regime must not be read"),
    ):
        top, scores, market_info = bi_trend_launch.run_bi_screening(
            db, "2026-07-16", global_market_regime=explicit
        )

    assert top == []
    assert scores == []
    assert market_info == {
        "breadth": 50,
        "env": "unknown",
        "global_regime_source": "explicit",
    }


def test_run_bi_screening_crash_return_keeps_return_contract():
    db = _QueuedDb(
        [
            ("one", {"prev_date": "2026-07-15"}),
            ("one", {"cnt": 101}),
            ("one", {"up": 0, "down": 100}),
            ("one", {"pd": None}),
            ("one", {"pd": None}),
            ("all", []),
        ]
    )
    explicit = {"regime": "weak", "bonus": -0.1}

    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        side_effect=AssertionError("current regime must not be read"),
    ):
        top, scores, market_info = bi_trend_launch.run_bi_screening(
            db, "2026-07-16", global_market_regime=explicit
        )

    assert top == []
    assert scores == []
    assert market_info["env"] == "crash"
    assert market_info["breadth"] == 0.0
    assert market_info["breadth_5d"] == 0.0
    assert market_info["sh_trend"] == "up"
    assert market_info["global_regime_source"] == "explicit"
