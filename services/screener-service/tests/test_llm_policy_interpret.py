"""Tests for llm_policy_interpret module.

Covers:
- Prompt construction with required fields
- JSON parsing with Markdown fence stripping
- Schema validation with DEFAULT_INTERPRETATION defaults
"""

import pytest

from app.llm_policy_interpret import (
    DEFAULT_INTERPRETATION,
    POLICY_INTERPRET_PROMPT,
    build_policy_interpret_prompt,
    parse_interpretation_json,
)


class TestBuildPolicyInterpretPrompt:
    """Tests for build_policy_interpret_prompt function."""

    def test_prompt_contains_required_output_fields(self):
        """AC-1: Prompt must mention all required output fields."""
        prompt = build_policy_interpret_prompt("政策测试文本")
        required_fields = [
            "summary",
            "industry_themes",
            "bom_nodes",
            "investment_logic",
            "risk_factors",
        ]
        for field in required_fields:
            assert field in prompt, f"Prompt missing required field: {field}"

    def test_prompt_contains_key_industry_themes(self):
        """Prompt should mention key industry themes for extraction."""
        prompt = build_policy_interpret_prompt("政策测试文本")
        # Check for some key themes mentioned in the prompt
        assert "产业主题" in prompt or "industry_themes" in prompt
        assert "重点方向" in prompt or "key_directions" in prompt

    def test_prompt_includes_source_metadata(self):
        """Prompt should include source title and date when provided."""
        source = {
            "title": "十四五规划纲要",
            "published_at": "2026-06-24",
        }
        prompt = build_policy_interpret_prompt("政策文本", source)
        assert "十四五规划纲要" in prompt
        assert "2026-06-24" in prompt

    def test_prompt_handles_missing_source(self):
        """Prompt should work with no source metadata."""
        prompt = build_policy_interpret_prompt("政策文本")
        assert "政策文本" in prompt


class TestParseInterpretationJson:
    """Tests for parse_interpretation_json function."""

    def test_parse_clean_json(self):
        """AC-2 & AC-3: Should parse clean JSON object correctly."""
        raw = """{
            "summary": "政策支持量子科技产业发展",
            "industry_themes": [
                {
                    "theme_id": "quantum",
                    "theme_name": "量子科技",
                    "key_directions": ["量子计算", "量子通信"],
                    "keywords": ["国产替代", "自主可控"],
                    "policy_intensity": 5
                }
            ],
            "bom_nodes": ["量子芯片", "低温系统"],
            "investment_logic": "量子科技迎来政策红利期",
            "risk_factors": [
                {"risk_type": "技术风险", "description": "技术成熟度低", "severity": "高"}
            ]
        }"""
        data = parse_interpretation_json(raw)
        assert data["summary"] == "政策支持量子科技产业发展"
        assert len(data["industry_themes"]) == 1
        assert data["industry_themes"][0]["theme_id"] == "quantum"
        assert "量子芯片" in data["bom_nodes"]
        assert data["investment_logic"] == "量子科技迎来政策红利期"
        assert len(data["risk_factors"]) == 1
        assert "parse_error" not in data

    def test_parse_json_with_markdown_fence(self):
        """AC-2: Should strip Markdown code fences."""
        raw = """```json
{
    "summary": "脑机接口产业政策解读",
    "industry_themes": [],
    "bom_nodes": ["电极", "信号处理器"],
    "investment_logic": "脑机接口进入临床验证阶段",
    "risk_factors": []
}
```"""
        data = parse_interpretation_json(raw)
        assert data["summary"] == "脑机接口产业政策解读"
        assert "电极" in data["bom_nodes"]
        assert "parse_error" not in data

    def test_parse_json_with_plain_fence(self):
        """AC-2: Should strip plain code fences (no language tag)."""
        raw = """```
{
    "summary": "氢能发展规划",
    "industry_themes": [],
    "bom_nodes": ["电解槽", "储氢罐"],
    "investment_logic": "氢能产业链逐步完善",
    "risk_factors": []
}
```"""
        data = parse_interpretation_json(raw)
        assert data["summary"] == "氢能发展规划"
        assert "parse_error" not in data

    def test_parse_json_embedded_in_text(self):
        """Should extract JSON from surrounding text."""
        raw = """根据政策分析，提取结果如下：

{
    "summary": "具身智能产业加速",
    "industry_themes": [],
    "bom_nodes": ["减速器", "伺服电机"],
    "investment_logic": "具身智能国产替代加速",
    "risk_factors": []
}

以上为结构化输出。"""
        data = parse_interpretation_json(raw)
        assert data["summary"] == "具身智能产业加速"
        assert "parse_error" not in data

    def test_parse_empty_string_returns_error(self):
        """Should return error for empty input."""
        data = parse_interpretation_json("")
        assert data["parse_error"] == "empty"

    def test_parse_invalid_json_returns_error(self):
        """Should return error for invalid JSON."""
        data = parse_interpretation_json("not json at all")
        assert data["parse_error"] == "invalid_json"

    def test_parse_non_object_json_returns_error(self):
        """Should return error for non-object JSON (e.g., array)."""
        data = parse_interpretation_json('["not", "an", "object"]')
        assert data["parse_error"] == "non_object_json"

    def test_missing_fields_get_defaults(self):
        """AC-3: Missing fields should be filled with DEFAULT_INTERPRETATION defaults."""
        raw = '{"summary": "部分数据", "bom_nodes": ["节点1"]}'
        data = parse_interpretation_json(raw)
        assert data["summary"] == "部分数据"
        assert data["bom_nodes"] == ["节点1"]
        # These should have default values
        assert data["industry_themes"] == []
        assert data["investment_logic"] == ""
        assert data["risk_factors"] == []

    def test_non_list_fields_corrected_to_empty_list(self):
        """List fields with wrong type should be corrected to empty list."""
        raw = '{"summary": "测试", "industry_themes": "not a list", "bom_nodes": null, "risk_factors": {}}'
        data = parse_interpretation_json(raw)
        assert data["industry_themes"] == []
        assert data["bom_nodes"] == []
        assert data["risk_factors"] == []

    def test_non_string_fields_corrected_to_empty_string(self):
        """String fields with wrong type should be corrected to empty string."""
        raw = '{"summary": [], "investment_logic": 123, "industry_themes": [], "bom_nodes": [], "risk_factors": []}'
        data = parse_interpretation_json(raw)
        assert data["summary"] == ""
        assert data["investment_logic"] == ""


class TestDefaultInterpretation:
    """Tests for DEFAULT_INTERPRETATION constant."""

    def test_default_has_all_required_fields(self):
        """DEFAULT_INTERPRETATION must have all required output fields."""
        required_fields = [
            "summary",
            "industry_themes",
            "bom_nodes",
            "investment_logic",
            "risk_factors",
        ]
        for field in required_fields:
            assert field in DEFAULT_INTERPRETATION, f"DEFAULT_INTERPRETATION missing: {field}"

    def test_default_list_fields_are_empty_lists(self):
        """List fields should default to empty lists."""
        list_fields = ["industry_themes", "bom_nodes", "risk_factors"]
        for field in list_fields:
            assert DEFAULT_INTERPRETATION[field] == []

    def test_default_string_fields_are_empty_strings(self):
        """String fields should default to empty strings."""
        string_fields = ["summary", "investment_logic"]
        for field in string_fields:
            assert DEFAULT_INTERPRETATION[field] == ""


class TestPolicyInterpretPrompt:
    """Tests for POLICY_INTERPRET_PROMPT constant."""

    def test_prompt_is_template(self):
        """Prompt should be a format template with placeholders."""
        assert "{title}" in POLICY_INTERPRET_PROMPT
        assert "{published_at}" in POLICY_INTERPRET_PROMPT
        assert "{text}" in POLICY_INTERPRET_PROMPT

    def test_prompt_mentions_all_industries(self):
        """Prompt should mention key industries for extraction."""
        # Strategic emerging industries
        assert "新一代信息技术" in POLICY_INTERPRET_PROMPT or "人工智能" in POLICY_INTERPRET_PROMPT
        # Future industries
        assert "量子科技" in POLICY_INTERPRET_PROMPT or "脑机接口" in POLICY_INTERPRET_PROMPT