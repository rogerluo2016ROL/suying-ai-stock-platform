"""supply_chain_scoring 共享评分公式纯函数单测(固定输入,断言数值)。"""
import pytest

from kronos_factors.engine.supply_chain_scoring import (
    calculate_evidence_score,
    calculate_gap_momentum_score,
    calculate_market_expectation_score,
    calculate_prosperity_score,
    calculate_stage_progress_score,
    classify_business_tag_events,
    compute_expectation_gap_score,
    compute_three_high_score,
    normalize_event_title,
    split_claim_counts,
)

EVENTS = [
    {"evidence_type": "order_award", "impact_dimensions": ["growth"], "confidence": 0.8},
    {"evidence_type": "revenue_margin", "impact_dimensions": ["profit"], "confidence": 0.6},
    {"evidence_type": "patent_standard", "impact_dimensions": ["moat"], "confidence": 0.9},
]


def test_classify_business_tag_events():
    assert classify_business_tag_events(EVENTS) == {
        "growth": 1,
        "profit": 1,
        "moat": 1,
        "risk": 0,
        "order": 1,
        "dedup_removed": 0,
    }


def test_normalize_event_title():
    assert normalize_event_title("中标 5G 基站订单!") == "中标5g基站订单"
    assert normalize_event_title(None) == ""
    assert normalize_event_title("  A.B,c  ") == "abc"


def test_classify_business_tag_events_dedup_same_code_title_date():
    events = [
        # 与下一条同 code + 标准化标题 + 同日期,confidence 低,应被去重
        {"code": "000063", "title": "中标 5G 基站订单!", "event_date": "2026-07-01",
         "evidence_type": "order_award", "impact_dimensions": ["growth"], "confidence": 0.5},
        {"code": "000063", "title": "中标5g基站订单", "event_date": "2026-07-01",
         "evidence_type": "order_award", "impact_dimensions": ["growth"], "confidence": 0.9},
        # 日期不同 → 保留
        {"code": "000063", "title": "中标5G基站订单", "event_date": "2026-07-02",
         "evidence_type": "order_award", "impact_dimensions": ["growth"], "confidence": 0.7},
        # code 不同 → 保留
        {"code": "000938", "title": "中标5G基站订单", "event_date": "2026-07-01",
         "evidence_type": "order_award", "impact_dimensions": ["growth"], "confidence": 0.6},
        # 无标题 → 不参与去重,各自唯一
        {"code": "000063", "event_date": "2026-07-01",
         "evidence_type": "patent_standard", "impact_dimensions": ["moat"], "confidence": 0.4},
        {"code": "000063", "event_date": "2026-07-01",
         "evidence_type": "patent_standard", "impact_dimensions": ["moat"], "confidence": 0.4},
    ]
    counts = classify_business_tag_events(events)
    assert counts["growth"] == 3       # 4 条 order 事件去掉 1 条重复
    assert counts["order"] == 3
    assert counts["moat"] == 2         # 无标题事件不去重
    assert counts["dedup_removed"] == 1


def test_stage_progress_uses_fixed_table_max():
    assert calculate_stage_progress_score("R3", "C2") == 45.0
    assert calculate_stage_progress_score("R6", "C0") == 90.0
    assert calculate_stage_progress_score(None, None) == 0.0


def test_market_expectation_score():
    # 35 底分 + analyst 2*4 + news 1*2.5 + 其他 2*1.5 + 涨幅 8*1.25
    assert calculate_market_expectation_score(
        analyst_claims=2, news_claims=1, total_claims=5, price_change_20d=8.0
    ) == 58.5
    # 无输入时只剩底分;负涨幅不计价
    assert calculate_market_expectation_score() == 35.0
    assert calculate_market_expectation_score(price_change_20d=-12.0) == 35.0
    # analyst/news/其他/价格各项封顶 25/15/15/25 → 上限 100
    assert calculate_market_expectation_score(
        analyst_claims=100, news_claims=100, total_claims=400, price_change_20d=80.0
    ) == 100.0


def test_split_claim_counts_uses_shared_constants():
    counts = {
        "analyst_estimate": 2,
        "broker_report": 1,
        "financial_news": 1,
        "media_report": 1,
        "announcement": 3,
        "other": 2,
    }
    assert split_claim_counts(counts) == (3, 2, 10)


def test_prosperity_score():
    assert calculate_prosperity_score(2.0, 1.0) == 58.0
    assert calculate_prosperity_score(None, None) == 50.0


def test_evidence_score():
    # 3*12 + avg_conf(2.3/3)*60 + growth 1*4 + moat 1*4
    assert calculate_evidence_score(EVENTS) == 90.0


def test_compute_three_high_score():
    result = compute_three_high_score(
        revenue_ratio=0.2,
        gross_profit_ratio=0.1,
        events=EVENTS,
        stage_score=45.0,
        prosperity_score=58.0,
    )
    assert result["growth_score"] == pytest.approx(50.4)       # 20 + 14 + 12 + 8*0.55
    assert result["profit_score"] == pytest.approx(65.0)       # 45 + 10 + 1*10
    assert result["moat_score"] == pytest.approx(54.83)        # 28 + (2.3/3)*35
    assert result["evidence_score"] == pytest.approx(90.0)
    assert result["total_score"] == pytest.approx(59.14)       # 见公式权重
    assert result["score_cap"] == 100.0
    assert result["revenue_supported"] is True
    assert result["profit_supported"] is True


def test_compute_three_high_score_caps():
    no_financials = compute_three_high_score(
        revenue_ratio=None,
        gross_profit_ratio=None,
        events=EVENTS[:1],
        stage_score=90.0,
        prosperity_score=50.0,
    )
    assert no_financials["profit_score"] is None
    assert no_financials["score_cap"] == 70.0
    assert no_financials["total_score"] <= 70.0

    revenue_only = compute_three_high_score(
        revenue_ratio=0.2,
        gross_profit_ratio=None,
        events=EVENTS[:1],
        stage_score=90.0,
        prosperity_score=50.0,
    )
    assert revenue_only["profit_score"] is None
    assert revenue_only["score_cap"] == 85.0


def test_compute_expectation_gap_score():
    result = compute_expectation_gap_score(
        stage_score=45.0,
        evidence_score=90.0,
        prosperity_score=58.0,
        market_expectation_score=58.5,
        risk_events=1,
        price_change_20d=8.0,
    )
    assert result["risk_penalty_score"] == pytest.approx(20.0)
    assert result["actual_progress_score"] == pytest.approx(61.74)  # 22.5 + 28.8 + 10.44
    assert result["raw_gap"] == pytest.approx(16.64)
    # 新口径 (raw+100)/2:16.64 → 58.32
    assert result["expectation_gap_score"] == pytest.approx(58.32)
    assert result["gap_type"] == "positive"
    assert "actual_progress" in result["formula"]


def test_compute_expectation_gap_score_clamps_and_types():
    # actual=50*0.18=9,raw=9-60=-51 → (raw+100)/2=24.5:负预期差保留幅度
    # (旧口径 clamp[0,100] 会截断为 0)
    negative = compute_expectation_gap_score(
        stage_score=0.0,
        evidence_score=0.0,
        prosperity_score=50.0,
        market_expectation_score=60.0,
    )
    assert negative["raw_gap"] == pytest.approx(-51.0)
    assert negative["expectation_gap_score"] == pytest.approx(24.5)
    assert negative["gap_type"] == "negative"

    # raw=-115.2 低于映射下界 -100,clamp 到 0
    extreme = compute_expectation_gap_score(
        stage_score=0.0,
        evidence_score=0.0,
        prosperity_score=50.0,
        market_expectation_score=90.0,
        risk_events=3,
        price_change_20d=-10.0,
    )
    assert extreme["expectation_gap_score"] == 0.0
    assert extreme["gap_type"] == "negative"
    assert extreme["raw_gap"] < -100

    # raw=0 → 50=中性
    neutral = compute_expectation_gap_score(
        stage_score=30.0,
        evidence_score=20.0,
        prosperity_score=50.0,
        market_expectation_score=35.0,
    )
    assert neutral["gap_type"] == "neutral"
    assert neutral["expectation_gap_score"] == pytest.approx(
        (neutral["raw_gap"] + 100.0) / 2.0, abs=0.01
    )


def test_gap_momentum_score():
    assert calculate_gap_momentum_score(current_gap=60.0, previous_gap=55.0, gap_20d_ago=50.0) == 70.0
    assert calculate_gap_momentum_score(current_gap=40.0, previous_gap=None, gap_20d_ago=None) == 50.0
