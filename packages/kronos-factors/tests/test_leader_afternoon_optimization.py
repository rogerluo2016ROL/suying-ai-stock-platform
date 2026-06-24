"""Tests for Qiu afternoon model post-backtest optimisations."""


def test_overheated_s_pick_is_downgraded():
    from kronos_factors.engine.leader_afternoon import apply_afternoon_optimization

    raw = {
        "code": "300001",
        "name": "样本科技",
        "industry": "软件服务",
        "total_score": 90,
        "grade": "S",
        "gain_pct": 18.5,
        "dist_to_limit": 0.7,
        "amount_yi_est": 18.0,
        "volume_score": 10,
        "capital_score": 10,
    }

    optimised = apply_afternoon_optimization(raw)

    assert optimised["raw_total_score"] == 90
    assert optimised["total_score"] < 85
    assert optimised["grade"] != "S"
    assert "crowded_breakout" in optimised["optimization_flags"]
    assert "weak_industry" in optimised["optimization_flags"]


def test_supportive_industry_gets_small_bonus_without_overfit():
    from kronos_factors.engine.leader_afternoon import apply_afternoon_optimization

    raw = {
        "code": "002000",
        "name": "样本汽配",
        "industry": "汽车配件",
        "total_score": 70,
        "grade": "B",
        "gain_pct": 7.6,
        "dist_to_limit": 4.2,
        "amount_yi_est": 2.0,
        "volume_score": 5,
        "capital_score": 14,
    }

    optimised = apply_afternoon_optimization(raw)

    assert optimised["total_score"] == 72
    assert optimised["grade"] == "A"
    assert "supportive_industry" in optimised["optimization_flags"]


def test_no_trade_picks_are_filtered_from_tradeable_list():
    from kronos_factors.engine.leader_afternoon import filter_tradeable_afternoon_picks

    picks = [
        {"code": "000001", "total_score": 90, "grade": "S", "_no_trade": True},
        {"code": "000002", "total_score": 78, "grade": "A"},
    ]

    tradeable = filter_tradeable_afternoon_picks(picks, top_n=20)

    assert [p["code"] for p in tradeable] == ["000002"]


def test_full_mode_allows_already_limit_up_stock_and_marks_resonance(monkeypatch):
    import kronos_factors.engine.leader_afternoon as afternoon

    hist = [
        {"close": 10 + i * 0.1, "high": 10.2 + i * 0.1, "low": 9.8 + i * 0.1, "volume": 1_000_000}
        for i in range(60)
    ]
    monkeypatch.setattr(afternoon, "get_kline_history", lambda *args, **kwargs: hist)
    monkeypatch.setattr(
        afternoon,
        "get_intraday_cumulative",
        lambda *args, **kwargs: {
            "day_high": 12.1,
            "day_low": 10.0,
            "total_amount": 600_000_000,
            "total_volume": 4_000_000,
        },
    )
    monkeypatch.setattr(afternoon, "get_moneyflow", lambda *args, **kwargs: None)
    monkeypatch.setattr(afternoon, "get_shanghai_index", lambda *args, **kwargs: 0.3)

    score = afternoon.score_stock_afternoon(
        "600000",
        "样本股份",
        "半导体",
        {"open": 10.0, "high": 11.0, "low": 9.8, "close": 11.0, "volume": 4_000_000, "amount": 600_000_000},
        10.0,
        db=object(),
        trade_date="2026-06-24",
        limit_info={"600000": {"is_at_limit": True}},
        sector_stats={"半导体": {"pct_change": 3.2, "peer_count": 8, "max_gain": 11.0}},
        allow_at_limit=True,
    )

    assert score is not None
    assert score["is_at_limit"] is True
    assert score["sector_resonance"]["sector"] == "半导体"
    assert score["sector_resonance"]["peer_count"] == 8
    assert score["sector_resonance"]["resonance_score"] == score["resonance_score"]


def test_sector_resonance_summary_groups_top_picks():
    from kronos_factors.engine.leader_afternoon import build_sector_resonance_summary

    picks = [
        {"code": "1", "name": "A", "industry": "半导体", "resonance_score": 15, "sector_change": 3.0, "peer_count": 8},
        {"code": "2", "name": "B", "industry": "半导体", "resonance_score": 12, "sector_change": 2.5, "peer_count": 7},
        {"code": "3", "name": "C", "industry": "通信设备", "resonance_score": 8, "sector_change": 1.0, "peer_count": 3},
    ]

    summary = build_sector_resonance_summary(picks)

    assert summary[0]["sector"] == "半导体"
    assert summary[0]["pick_count"] == 2
    assert summary[0]["representatives"] == ["A", "B"]
    assert summary[0]["avg_resonance_score"] == 13.5


def test_full_output_selection_ignores_bear_market_grade_and_sector_caps():
    from kronos_factors.engine.leader_afternoon import MarketEnv, select_afternoon_top

    scores = [
        {"code": "1", "industry": "半导体", "grade": "S", "total_score": 90},
        {"code": "2", "industry": "半导体", "grade": "A", "total_score": 80},
        {"code": "3", "industry": "半导体", "grade": "B", "total_score": 70},
    ]

    strict = select_afternoon_top(scores, MarketEnv.BEAR, top_n=30, full_output=False)
    full = select_afternoon_top(scores, MarketEnv.BEAR, top_n=30, full_output=True)

    assert [p["code"] for p in strict] == ["1"]
    assert [p["code"] for p in full] == ["1", "2", "3"]
