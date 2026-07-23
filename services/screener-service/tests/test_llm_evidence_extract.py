"""Tests for LLM structured evidence extraction (mock LLM, no network)."""

from app.llm_evidence_extract import (
    build_evidence_prompt,
    extract_evidence,
    is_confirmed_hit,
    parse_evidence_json,
)


def _mock_call(raw: str):
    def call(messages):
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        return raw

    return call


def test_build_evidence_prompt_contains_company_business_and_fields():
    prompt = build_evidence_prompt("恒烁股份", "公司存算一体芯片已流片", "存算一体/存内计算(CIM)芯片")
    assert "恒烁股份" in prompt
    assert "存算一体/存内计算(CIM)芯片" in prompt
    assert "公司存算一体芯片已流片" in prompt
    for key in ["relevant", "names_company", "business", "stage", "strength", "reason"]:
        assert key in prompt


def test_parse_evidence_json_accepts_clean_json():
    raw = '{"relevant": true, "names_company": true, "business": "NOR存内计算芯片", "stage": "sample", "strength": "strong", "reason": "公告点名公司存算一体芯片送样"}'
    data = parse_evidence_json(raw)
    assert data["relevant"] is True
    assert data["names_company"] is True
    assert data["business"] == "NOR存内计算芯片"
    assert data["stage"] == "sample"
    assert data["strength"] == "strong"
    assert "公告点名" in data["reason"]


def test_parse_evidence_json_accepts_fenced_json():
    raw = '```json\n{"relevant": false, "names_company": false, "business": "", "stage": "none", "strength": "weak", "reason": "行业泛文"}\n```'
    data = parse_evidence_json(raw)
    assert data["relevant"] is False
    assert data["strength"] == "weak"


def test_parse_evidence_json_normalizes_unknown_enums():
    raw = '{"relevant": true, "names_company": true, "business": "x", "stage": "量产阶段", "strength": "高", "reason": "r"}'
    data = parse_evidence_json(raw)
    assert data["stage"] == "none"
    assert data["strength"] == "weak"


def test_parse_evidence_json_rejects_garbage():
    assert parse_evidence_json("") is None
    assert parse_evidence_json("not json at all") is None
    assert parse_evidence_json('["a", "b"]') is None


def test_parse_evidence_json_coerces_string_bools():
    raw = '{"relevant": "true", "names_company": "false", "business": "b", "stage": "order", "strength": "mid", "reason": "r"}'
    data = parse_evidence_json(raw)
    assert data["relevant"] is True
    assert data["names_company"] is False
    assert data["stage"] == "order"


def test_extract_evidence_returns_parsed_result_on_mock_hit():
    raw = '{"relevant": true, "names_company": true, "business": "TSV刻蚀设备", "stage": "mass_production", "strength": "strong", "reason": "年报明确TSV设备批量销售"}'
    result = extract_evidence("中微公司", "公司TSV深硅刻蚀设备已批量销售", "TSV深硅刻蚀设备", call_fn=_mock_call(raw))
    assert result is not None
    assert is_confirmed_hit(result) is True


def test_extract_evidence_returns_none_on_llm_exception():
    def boom(messages):
        raise RuntimeError("network down")

    assert extract_evidence("中微公司", "text", "TSV设备", call_fn=boom) is None


def test_extract_evidence_returns_none_on_unparseable_llm_output():
    assert extract_evidence("中微公司", "text", "TSV设备", call_fn=_mock_call("抱歉我无法判断")) is None


def test_is_confirmed_hit_requires_relevant_names_company_strong():
    base = {"relevant": True, "names_company": True, "business": "b", "stage": "order", "strength": "strong", "reason": "r"}
    assert is_confirmed_hit(base) is True
    assert is_confirmed_hit({**base, "names_company": False}) is False
    assert is_confirmed_hit({**base, "relevant": False}) is False
    assert is_confirmed_hit({**base, "strength": "mid"}) is False
    assert is_confirmed_hit(None) is False
