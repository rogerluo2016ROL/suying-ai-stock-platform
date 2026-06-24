"""Tests for Bi trend launch four-axis enhancement."""

import numpy as np


def _trend_arrays(n=80):
    closes = np.linspace(10.0, 13.0, n)
    closes[-6:] = [12.5, 12.2, 11.9, 12.05, 12.25, 12.45]
    highs = closes * 1.02
    lows = closes * 0.98
    volumes = np.full(n, 1_000_000.0)
    volumes[-6] = 2_500_000.0
    volumes[-3:] = [650_000.0, 620_000.0, 680_000.0]
    return closes, highs, lows, volumes


def test_hard_tech_conviction_marks_core_ai_compute_track():
    from kronos_factors.engine.bi_trend_launch import _score_hard_tech_conviction

    result = _score_hard_tech_conviction(
        industry="CPO光模块与AI算力设备",
        hard_tech_track="AI算力",
        chokepoint_score=1,
        peer_count=6,
    )

    assert result["track"] == "AI算力"
    assert result["tier"] == "core"
    assert result["score_adj"] >= 5
    assert "光模块" in result["matched_keywords"]
    assert result["chokepoint_level"] == "oligopoly"
    assert "AI算力" in result["conviction_reason"]


def test_hard_tech_conviction_keeps_broad_match_low_conviction():
    from kronos_factors.engine.bi_trend_launch import _score_hard_tech_conviction

    result = _score_hard_tech_conviction(
        industry="电子制造",
        hard_tech_track="硬科技",
        chokepoint_score=0,
        peer_count=30,
    )

    assert result["tier"] == "broad"
    assert result["score_adj"] <= 2
    assert result["chokepoint_level"] == "normal"


def test_hard_tech_conviction_uses_evidence_text_to_refine_track():
    from kronos_factors.engine.bi_trend_launch import _score_hard_tech_conviction

    result = _score_hard_tech_conviction(
        industry="通信设备",
        hard_tech_track="通信",
        chokepoint_score=0,
        peer_count=131,
        evidence_text="打造AI全栈光互连解决方案，受益国内AI算力发展",
    )

    assert result["track"] == "AI算力"
    assert result["tier"] == "core"
    assert result["score_adj"] >= 4
    assert "算力" in result["matched_keywords"]


def test_scored_pick_contains_explanation_fields():
    from kronos_factors.engine.bi_trend_launch import _score_bi_trend_arrays

    closes, highs, lows, volumes = _trend_arrays()
    result = _score_bi_trend_arrays(
        closes,
        highs,
        lows,
        volumes,
        code="688001",
        name="硬核科技",
        industry="CPO光模块与AI算力设备",
        sector_change=1.2,
        hard_tech_track="AI算力",
        chokepoint_score=1,
        peer_count=6,
    )

    assert result is not None
    assert "factor_breakdown" in result
    assert "entry_reason" in result
    assert "risk_flags" in result
    assert "quality_flags" in result
    assert "hard_tech" in result
    assert result["hard_tech"]["tier"] == "core"


def test_startup_quality_flags_late_rebound_and_distribution():
    from kronos_factors.engine.bi_trend_launch import _score_startup_quality

    result = _score_startup_quality(
        regime="weak",
        daily_gain=4.5,
        two_day_up=False,
        wr_now=82.0,
        ret_5d=10.0,
        ma20_extension_penalty=4,
        distribution_penalty=5,
        annual_vol=92.0,
        vol_regime="high",
        weekly_bearish=False,
        dead_cat=False,
    )

    assert result["score_adj"] < 0
    assert "late_rebound" in result["risk_flags"]
    assert "distribution_day" in result["risk_flags"]
    assert "weak_market_single_pop" in result["quality_flags"]


def test_ignition_power_rewards_fresh_coiling_reversal():
    from kronos_factors.engine.bi_trend_launch import _score_ignition_power

    result = _score_ignition_power(
        obv_days_above=2,
        obv_positive=True,
        obv_slope=8.0,
        ignition_bonus=4,
        coiling_bonus=3,
        compression_reversal_bonus=8,
        range_pos=0.22,
        higher_low=True,
        rebound_confirmed=True,
        vol_ratio=0.68,
        wr_now=72.0,
        wr_level="急跌→止跌→反弹🔥",
    )

    assert result["score_adj"] >= 7
    assert "fresh_obv_breakout" in result["power_flags"]
    assert "coiling_after_ignition" in result["power_flags"]
    assert "compression_reversal" in result["power_flags"]


def test_generate_bi_plan_uses_refined_hard_tech_track(monkeypatch):
    from kronos_factors.engine import bi_trend_launch

    monkeypatch.setattr(bi_trend_launch, "_get_atr_pct_for_code", lambda code: 0.0)

    plans = bi_trend_launch.generate_bi_plan([
        {
            "code": "002281",
            "name": "光迅科技",
            "close": 276.5,
            "grade": "S",
            "signal": "watch",
            "total_score": 86,
            "obv_level": "刚突破",
            "wr_level": "平稳",
            "hard_tech_track": "通信",
            "hard_tech": {"track": "AI算力", "tier": "core"},
        }
    ])

    assert plans[0]["hard_tech_track"] == "AI算力"
    assert "AI算力" in plans[0]["tips"]
    assert "通信" not in plans[0]["tips"]
