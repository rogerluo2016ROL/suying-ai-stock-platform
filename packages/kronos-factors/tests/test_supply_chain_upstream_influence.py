from kronos_factors.engine.supply_chain import (
    load_upstream_influence_rules,
    match_upstream_influence_rules,
)


def test_upstream_influence_rules_match_non_board_material_supplier():
    rules = load_upstream_influence_rules()

    matches = match_upstream_influence_rules(
        code="300522",
        name="世名科技",
        industry="染料涂料",
        main_business="",
        rules=rules,
    )

    assert matches
    match = matches[0]
    assert match["candidate_source"] == "upstream_influence"
    assert match["pool_status"] == "观察池"
    assert match["upstream_node"] == "功能色浆/纳米材料"
    assert "显示材料" in match["downstream_chains"]
    assert "世名科技 → 功能色浆/纳米材料 → 显示材料" in match["influence_paths"]
