from kronos_factors.engine.supply_chain_bom import (
    derive_trade_signal,
    load_bom_config,
    score_company_v4,
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
