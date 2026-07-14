import json
from pathlib import Path


CONFIG = Path(__file__).resolve().parents[1] / "configs" / "industry_chain_templates.json"


def load_template(template_id: str) -> dict:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return next(row for row in data["templates"] if row.get("template_id") == template_id)


def test_token_output_template_has_confirmed_layers_and_dimensions():
    template = load_template("ai_token_output")
    assert [row["name"] for row in template["layers"]] == [
        "Token需求场景", "模型与AI产品", "推理优化软件", "核心算力硬件",
        "集群与网络支撑", "Token服务与交付平台", "计量计费与运营", "商业变现与输出",
    ]
    assert template["industry_dimensions"] == [
        "demand_authenticity", "model_product_strength", "inference_unit_economics",
        "bom_supply_position", "delivery_customer_stickiness", "commercial_output",
        "evidence_realization",
    ]
    assert template["market_layer_separate"] is True


def test_legacy_power_template_remains_available():
    assert load_template("ai_token_output_power")["chain_id"] == "ai_token_output_power"
