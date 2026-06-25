"""Tests for V6 three-factor resonance scoring."""

from kronos_factors.engine.supply_chain_bom_v5 import (
    classify_chokepoint_level,
    derive_resonance_v6,
    INDUSTRY_CYCLE_SCORE,
    PERFORMANCE_YIELD_SCORE,
    CHOKEPOINT_CORE_KEYWORDS,
    CHOKEPOINT_KEY_KEYWORDS,
)


def test_industry_cycle_score_mapping():
    """Test industry cycle score for each stage."""
    assert INDUSTRY_CYCLE_SCORE["放量"] == 12.0
    assert INDUSTRY_CYCLE_SCORE["放量/订单"] == 12.0
    assert INDUSTRY_CYCLE_SCORE["量产"] == 9.0
    assert INDUSTRY_CYCLE_SCORE["小批量"] == 6.0
    assert INDUSTRY_CYCLE_SCORE["样品"] == 3.0
    assert INDUSTRY_CYCLE_SCORE["样品/研发"] == 3.0
    assert INDUSTRY_CYCLE_SCORE["研发"] == 3.0
    assert INDUSTRY_CYCLE_SCORE["未识别"] == 2.0


def test_performance_yield_score_thresholds():
    """Test performance yield score for YoY growth thresholds."""
    assert PERFORMANCE_YIELD_SCORE[(100, float("inf"))] == 20.0
    assert PERFORMANCE_YIELD_SCORE[(50, 100)] == 15.0
    assert PERFORMANCE_YIELD_SCORE[(20, 50)] == 10.0
    assert PERFORMANCE_YIELD_SCORE[(0, 20)] == 5.0


def test_chokepoint_keyword_sets():
    """Test chokepoint keyword classification."""
    # Core keywords (垄断级)
    assert "垄断" in CHOKEPOINT_CORE_KEYWORDS
    assert "独家" in CHOKEPOINT_CORE_KEYWORDS
    assert "首家" in CHOKEPOINT_CORE_KEYWORDS
    assert "稀缺" in CHOKEPOINT_CORE_KEYWORDS
    assert "寡头" in CHOKEPOINT_CORE_KEYWORDS
    assert "唯一" in CHOKEPOINT_CORE_KEYWORDS
    assert "打破垄断" in CHOKEPOINT_CORE_KEYWORDS
    assert "卡脖子" in CHOKEPOINT_CORE_KEYWORDS

    # Key keywords (关键级)
    assert "国产替代" in CHOKEPOINT_KEY_KEYWORDS
    assert "进口替代" in CHOKEPOINT_KEY_KEYWORDS
    assert "自主可控" in CHOKEPOINT_KEY_KEYWORDS
    assert "客户验证" in CHOKEPOINT_KEY_KEYWORDS
    assert "认证" in CHOKEPOINT_KEY_KEYWORDS
    assert "供应商" in CHOKEPOINT_KEY_KEYWORDS
    assert "定点" in CHOKEPOINT_KEY_KEYWORDS
    assert "进入供应链" in CHOKEPOINT_KEY_KEYWORDS

    # No overlap between core and key
    assert not (CHOKEPOINT_CORE_KEYWORDS & CHOKEPOINT_KEY_KEYWORDS)


def test_classify_chokepoint_level_core():
    """Test '卡脖子核心' classification."""
    # High score + core keyword
    assert classify_chokepoint_level(10.0, ["垄断"]) == "卡脖子核心"
    assert classify_chokepoint_level(12.0, ["独家", "首家"]) == "卡脖子核心"
    assert classify_chokepoint_level(20.0, ["卡脖子"]) == "卡脖子核心"

    # High score but no core keyword -> not core
    assert classify_chokepoint_level(15.0, ["国产替代"]) == "关键环节"
    assert classify_chokepoint_level(10.0, []) == "关键环节"  # score >= 6


def test_classify_chokepoint_level_key():
    """Test '关键环节' classification."""
    # Score >= 6 without core keyword
    assert classify_chokepoint_level(6.0, []) == "关键环节"
    assert classify_chokepoint_level(8.0, []) == "关键环节"

    # Key keyword (even with low score)
    assert classify_chokepoint_level(2.0, ["国产替代"]) == "关键环节"
    assert classify_chokepoint_level(0.0, ["客户验证", "认证"]) == "关键环节"

    # High score but no core keyword
    assert classify_chokepoint_level(12.0, ["国产替代"]) == "关键环节"


def test_classify_chokepoint_level_normal():
    """Test '普通' classification."""
    # Low score + no keywords
    assert classify_chokepoint_level(0.0, []) == "普通"
    assert classify_chokepoint_level(2.0, []) == "普通"
    assert classify_chokepoint_level(5.0, []) == "普通"

    # Low score + unrecognized keywords
    assert classify_chokepoint_level(3.0, ["其他"]) == "普通"


def test_derive_resonance_v6_all_factors_pass():
    """Test resonance when all 3 factors pass thresholds."""
    pick = {
        "policy_score": 15,  # > 9 threshold
        "q_sales_yoy": 120,  # >= 100 -> 20 points, > 15 threshold
    }
    result = derive_resonance_v6(pick, stage="放量")

    assert result["industry_cycle_score"] == 12.0
    assert result["policy_intensity_score"] == 15.0  # capped at 15
    assert result["performance_yield_score"] == 20.0
    assert result["resonance_factors"] == 3
    assert result["resonance_signal"] == "强启动"
    assert result["resonance_details"]["industry_cycle_passed"] is True
    assert result["resonance_details"]["policy_intensity_passed"] is True
    assert result["resonance_details"]["performance_yield_passed"] is True


def test_derive_resonance_v6_two_factors_pass():
    """Test resonance when 2 factors pass thresholds."""
    pick = {
        "policy_score": 12,  # > 9 threshold
        "q_sales_yoy": 30,   # 20-50 -> 10 points, < 15 threshold
    }
    result = derive_resonance_v6(pick, stage="量产")  # 9 points, >= 9 threshold

    assert result["industry_cycle_score"] == 9.0
    assert result["policy_intensity_score"] == 12.0
    assert result["performance_yield_score"] == 10.0
    assert result["resonance_factors"] == 2
    assert result["resonance_signal"] == "启动"
    assert result["resonance_details"]["industry_cycle_passed"] is True
    assert result["resonance_details"]["policy_intensity_passed"] is True
    assert result["resonance_details"]["performance_yield_passed"] is False


def test_derive_resonance_v6_one_factor_passes():
    """Test resonance when 1 factor passes threshold."""
    pick = {
        "policy_score": 6,   # < 9 threshold
        "q_sales_yoy": 20,   # 20-50 -> 10 points, < 15 threshold
    }
    result = derive_resonance_v6(pick, stage="量产")  # 9 points, >= 9 threshold

    assert result["industry_cycle_score"] == 9.0
    assert result["policy_intensity_score"] == 6.0
    assert result["performance_yield_score"] == 10.0
    assert result["resonance_factors"] == 1
    assert result["resonance_signal"] == "关注"
    assert result["resonance_details"]["industry_cycle_passed"] is True
    assert result["resonance_details"]["policy_intensity_passed"] is False
    assert result["resonance_details"]["performance_yield_passed"] is False


def test_derive_resonance_v6_zero_factors_pass():
    """Test resonance when no factors pass thresholds."""
    pick = {
        "policy_score": 5,   # < 9 threshold
        "q_sales_yoy": 10,   # 0-20 -> 5 points, < 15 threshold
    }
    result = derive_resonance_v6(pick, stage="研发")  # 3 points, < 9 threshold

    assert result["industry_cycle_score"] == 3.0
    assert result["policy_intensity_score"] == 5.0
    assert result["performance_yield_score"] == 5.0
    assert result["resonance_factors"] == 0
    assert result["resonance_signal"] == "观察"
    assert result["resonance_details"]["industry_cycle_passed"] is False
    assert result["resonance_details"]["policy_intensity_passed"] is False
    assert result["resonance_details"]["performance_yield_passed"] is False


def test_derive_resonance_v6_profit_yoy_used():
    """Test resonance uses profit_yoy when higher than revenue_yoy."""
    pick = {
        "policy_score": 15,
        "q_sales_yoy": 30,   # 10 points
        "netprofit_yoy": 150,  # 20 points (max)
    }
    result = derive_resonance_v6(pick, stage="放量")

    assert result["performance_yield_score"] == 20.0  # uses max of revenue/profit
    assert result["resonance_factors"] == 3


def test_derive_resonance_v6_negative_yoy():
    """Test resonance with negative YoY growth."""
    pick = {
        "policy_score": 15,
        "q_sales_yoy": -20,
    }
    result = derive_resonance_v6(pick, stage="放量")

    assert result["performance_yield_score"] == 0.0
    assert result["resonance_factors"] == 2  # only industry_cycle + policy


def test_derive_resonance_v6_missing_stage():
    """Test resonance with missing stage."""
    pick = {
        "policy_score": 15,
        "q_sales_yoy": 100,
    }
    result = derive_resonance_v6(pick, stage=None)

    assert result["industry_cycle_score"] == 2.0  # "未识别"
    assert result["resonance_factors"] == 2  # policy + performance


def test_derive_resonance_v6_policy_relevance():
    """Test policy intensity with relevance weighting."""
    pick = {
        "policy_score": 15,
        "policy_relevance": 0.5,  # reduces policy intensity
        "q_sales_yoy": 100,
    }
    result = derive_resonance_v6(pick, stage="放量")

    # 15 * 0.5 = 7.5, capped at 15 -> 7.5 (below 9 threshold)
    assert result["policy_intensity_score"] == 7.5
    assert result["resonance_factors"] == 2  # industry_cycle + performance


def test_derive_resonance_v6_thresholds_in_output():
    """Test that thresholds are included in output."""
    pick = {"policy_score": 15, "q_sales_yoy": 100}
    result = derive_resonance_v6(pick, stage="放量")

    assert "thresholds" in result
    assert result["thresholds"]["industry_cycle"] == 9.0
    assert result["thresholds"]["policy_intensity"] == 9.0
    assert result["thresholds"]["performance_yield"] == 15.0


def test_derive_resonance_v6_量产_threshold():
    """Test that 量产 (9.0) exactly passes threshold."""
    pick = {"policy_score": 6, "q_sales_yoy": 20}
    result = derive_resonance_v6(pick, stage="量产")

    # 量产 = 9.0, exactly at threshold
    assert result["industry_cycle_score"] == 9.0
    assert result["resonance_details"]["industry_cycle_passed"] is True


def test_derive_resonance_v6_小批量_below_threshold():
    """Test that 小批量 (6.0) is below threshold."""
    pick = {"policy_score": 6, "q_sales_yoy": 20}
    result = derive_resonance_v6(pick, stage="小批量")

    assert result["industry_cycle_score"] == 6.0
    assert result["resonance_details"]["industry_cycle_passed"] is False


def test_derive_resonance_v6_yoy_50_threshold():
    """Test that yoy=50 exactly passes performance threshold."""
    pick = {"policy_score": 15, "q_sales_yoy": 50}
    result = derive_resonance_v6(pick, stage="放量")

    # 50% is in (50, 100) range -> 15 points, exactly at threshold
    assert result["performance_yield_score"] == 15.0
    assert result["resonance_details"]["performance_yield_passed"] is True


def test_derive_resonance_v6_yoy_49_below_threshold():
    """Test that yoy=49 is below performance threshold."""
    pick = {"policy_score": 15, "q_sales_yoy": 49}
    result = derive_resonance_v6(pick, stage="放量")

    # 49% is in (20, 50) range -> 10 points, below threshold
    assert result["performance_yield_score"] == 10.0
    assert result["resonance_details"]["performance_yield_passed"] is False