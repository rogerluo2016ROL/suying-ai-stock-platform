from app.llm_supply_chain import build_extraction_prompt, parse_extraction_json


def test_build_extraction_prompt_mentions_required_fields():
    prompt = build_extraction_prompt("公司公告：产品已小批量交付")
    for key in ["policy_theme", "bom_nodes", "companies", "products", "commercialization_stage", "evidence"]:
        assert key in prompt


def test_parse_extraction_json_accepts_clean_json():
    raw = '{"policy_theme":"未来产业主攻方向","bom_nodes":["具身智能"],"companies":[{"code":"688001","name":"测试科技"}],"evidence":[{"summary":"小批量交付","confidence":0.8}]}'
    data = parse_extraction_json(raw)
    assert data["policy_theme"] == "未来产业主攻方向"
    assert data["evidence"][0]["confidence"] == 0.8


def test_parse_extraction_json_rejects_non_object_json():
    data = parse_extraction_json('["not", "object"]')
    assert data["parse_error"] == "non_object_json"
