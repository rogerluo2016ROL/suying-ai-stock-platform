import json
from pathlib import Path

from kronos_factors.engine.supply_chain_foundation import (
    build_foundation_catalog,
    load_supply_chain_config,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "configs" / "industry_chain_templates.json"
SUPPLY_CHAIN_PATH = ROOT / "configs" / "supply_chains.json"


def test_token_output_template_has_eight_layers_seven_dimensions_and_separate_market_layer():
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    template = next(item for item in data["templates"] if item["template_id"] == "ai_token_output_power")
    assert [layer["layer_id"] for layer in template["layers"]] == [
        "demand", "task", "core_product", "foundation",
        "integration", "supporting", "infrastructure", "commercialization",
    ]
    assert template["industry_dimensions"] == [
        "function_value", "technology_route", "physical_bom",
        "value_pool", "competition_moat", "supply_demand_cycle",
        "evidence_validation",
    ]
    assert template["market_layer"]["separate_from_industry_evidence"] is True
    assert template["power_source_types"] == [
        "curtailed_renewable", "valley_power",
        "park_self_generation_or_ppa", "nominal_capacity",
    ]


def test_token_output_chain_slug_is_stable():
    config = load_supply_chain_config(SUPPLY_CHAIN_PATH)
    catalog = build_foundation_catalog(config, chains=["AI Token输出电力"])
    assert catalog.chain_lookup["AI Token输出电力"]["chain_id"] == "ai_token_output_power"
    assert any(node["node_id"] == "chain_ai_token_output_power" for node in catalog.nodes)
