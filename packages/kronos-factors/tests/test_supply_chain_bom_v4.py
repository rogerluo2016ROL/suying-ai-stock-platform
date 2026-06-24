from kronos_factors.engine.supply_chain_bom import (
    derive_trade_signal,
    load_bom_config,
    score_company_v4,
)
from kronos_factors.engine.supply_chain_bom_v5 import (
    DIM_WEIGHTS as V5_DIM_WEIGHTS,
    score_bom_ratio,
    score_chokepoint_hits,
    score_company_v5,
    score_growth,
    score_profit,
)


def test_load_bom_config_contains_future_industry_core():
    cfg = load_bom_config()
    names = {theme["name"] for theme in cfg["themes"]}
    assert "未来产业主攻方向" in names
    node_names = {node["name"] for node in cfg["nodes"]}
    assert {"量子科技", "具身智能", "第六代移动通信"}.issubset(node_names)


def test_policy_themes_include_expert_interpretation_fields():
    cfg = load_bom_config()
    themes = {theme["theme_id"]: theme for theme in cfg["themes"]}

    for theme_id in ("future_industry_core", "new_quality_productivity", "tech_self_reliance"):
        theme = themes[theme_id]
        assert theme["interpretation"]
        assert theme["strategic_logic"]
        assert theme["bom_focus"]
        assert theme["evidence_focus"]

    assert "科技创新" in themes["new_quality_productivity"]["interpretation"]
    assert "关键核心技术" in themes["tech_self_reliance"]["interpretation"]


def test_derive_trade_signal_labels():
    assert derive_trade_signal(86, {"commercialization": 14, "market": 9}) == "强启动"
    assert derive_trade_signal(78, {"commercialization": 12, "market": 7}) == "启动"
    assert derive_trade_signal(70, {"commercialization": 7, "market": 4}) == "观察"
    assert derive_trade_signal(48, {"risk": 9}) == "风险回避"


def test_score_company_v4_adds_required_fields():
    pick = {
        "code": "688001",
        "name": "测试科技",
        "chain": "具身智能",
        "layer": "核心部件",
        "total_score": 72,
        "growth_score": 24,
        "profit_score": 10,
        "moat_score": 20,
    }
    enriched = score_company_v4(
        pick,
        [{"evidence_type": "policy", "confidence": 0.9, "summary": "入选未来产业主攻方向"}],
    )
    assert enriched["rating"] in {"S", "A", "B", "C", "D"}
    assert enriched["trade_signal"] in {"观察", "关注", "启动", "强启动", "风险回避"}
    assert enriched["policy_theme"]
    assert enriched["bom_path"]
    assert "dimension_scores" in enriched
    assert "evidence" in enriched


def test_v5_dimension_weights_match_embodied_ai_model():
    assert V5_DIM_WEIGHTS == {
        "policy": 15,
        "bom": 15,
        "chokepoint": 20,
        "growth": 15,
        "profit": 10,
        "commercialization": 15,
        "market": 10,
    }


def test_v5_scores_bom_ratio_and_chokepoint_diversity():
    assert score_bom_ratio(83.4) == 15.0
    assert score_bom_ratio(57.5) == 12.0
    assert score_bom_ratio(28.5) == 8.0
    assert score_bom_ratio(8.7) == 2.0

    assert score_chokepoint_hits({"垄断": 3, "客户验证": 2}) == 16.0
    assert score_chokepoint_hits({"垄断": 3, "客户验证": 2, "国产替代": 2}) == 20.0


def test_v5_scores_financial_growth_and_profit():
    assert score_growth(20, 120) == (15.0, "财务yoy120%")
    assert score_growth(10, 61) == (12.0, "财务yoy61%")
    assert score_growth(38, 5) == (9.0, "财务yoy38%")
    assert score_growth(-5, -19) == (3.0, "财务yoy-5%(负)")
    assert score_growth(None, None, forecast_type="预增", forecast_max=80) == (12.0, "预告预增80%")

    assert score_profit(52) == (10.0, "毛利率52%")
    assert score_profit(34) == (7.0, "毛利率34%")
    assert score_profit(11) == (2.0, "毛利率11%(低)")
    assert score_profit(None) == (6.0, "中性(无财务)")


def test_score_company_v5_uses_shared_rules_for_total_rating_and_signal():
    pick = {
        "code": "300503",
        "name": "昊志机电",
        "chain": "具身智能",
        "layer": "控制器",
        "policy_score": 15,
        "main_pct": 17.8874,
        "q_sales_yoy": 484,
        "netprofit_yoy": 12,
        "gross_margin": 42,
    }
    evidence = [
        {"evidence_type": "commercialization", "stage": "放量/订单", "confidence": 0.9},
        {"evidence_type": "commercialization", "stage": "量产", "confidence": 0.8},
        {"evidence_type": "chokepoint", "keywords": ["垄断", "客户验证"], "confidence": 0.9},
        {"evidence_type": "chokepoint", "keywords": ["垄断", "国产替代"], "confidence": 0.8},
    ] * 5

    scored = score_company_v5(pick, evidence)

    assert scored["dimension_scores"] == {
        "policy": 15.0,
        "bom": 4.0,
        "chokepoint": 20.0,
        "growth": 15.0,
        "profit": 7.0,
        "commercialization": 12.0,
        "market": 10.0,
        "risk": 0.0,
    }
    assert scored["total_score"] == 83.0
    assert scored["rating"] == "A"
    assert scored["trade_signal"] == "启动"
