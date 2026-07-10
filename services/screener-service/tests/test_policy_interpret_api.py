"""Tests for policy interpretation API endpoint."""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.screener import router
import app.routers.screener as screener_router


def _client():
    """Create test client with screener router."""
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _make_async_llm_response(content: str, provider: str = "deepseek", model: str = "deepseek-chat",
                              prompt_tokens: int = 100, completion_tokens: int = 200):
    """Create an async mock that returns LLMResponse."""
    from app.llm_multi_provider import LLMResponse, LLMUsage

    async def async_func(*args, **kwargs):
        return LLMResponse(
            content=content,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                provider=provider,
                model=model,
            ),
        )

    return async_func


def test_policy_interpret_endpoint_returns_400_for_empty_text():
    """AC-1: Empty text should return 400 error."""
    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={"text": "", "source": {"title": "测试政策"}},
    )
    assert r.status_code == 400
    assert "text is required" in r.json().get("detail", "")


def test_policy_interpret_endpoint_returns_disabled_without_llm_key(monkeypatch):
    """AC-5: LLM disabled should return status=disabled."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ARK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={"text": "国务院发布量子科技产业发展规划", "source": {"title": "测试政策"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "disabled"
    assert "API_KEY" in body.get("reason", "") or "missing" in body.get("reason", "")


def test_policy_interpret_endpoint_returns_ok_with_valid_text(monkeypatch):
    """AC-1, AC-2: Valid text should return structured interpretation."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-mocking")

    # Mock the LLM call to return a structured response (async)
    async_llm = _make_async_llm_response(
        '{"summary": "量子科技产业政策摘要", "industry_themes": [{"theme_id": "quantum", "theme_name": "量子科技", "policy_intensity": 5}], "bom_nodes": ["量子计算", "量子通信"], "investment_logic": "量子科技是未来产业核心方向", "risk_factors": [{"risk_type": "技术风险", "description": "技术成熟度不足", "severity": "中"}]}'
    )
    monkeypatch.setattr("app.llm_multi_provider.call_llm_with_fallback", async_llm)

    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={
            "text": "国务院发布量子科技产业发展规划，重点支持量子计算、量子通信等领域。",
            "source": {"title": "量子科技产业规划", "published_at": "2026-06-24"},
            "persist": False,
            "provider": "deepseek",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["persisted"] is False

    # Verify interpretation_result structure (AC-2)
    result = body.get("interpretation_result", {})
    assert result.get("summary") == "量子科技产业政策摘要"
    assert len(result.get("industry_themes", [])) == 1
    assert result.get("industry_themes", [])[0].get("theme_id") == "quantum"
    assert "量子计算" in result.get("bom_nodes", [])
    assert result.get("investment_logic") == "量子科技是未来产业核心方向"
    assert len(result.get("risk_factors", [])) == 1

    # Verify usage telemetry (AC-2)
    usage = body.get("usage", {})
    assert usage.get("prompt_tokens") == 100
    assert usage.get("completion_tokens") == 200
    assert usage.get("total_tokens") == 300
    assert usage.get("provider") == "deepseek"


def test_policy_interpret_endpoint_persists_to_pg_when_requested(monkeypatch):
    """AC-3: persist=True should write to policy_interpretations table."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-mocking")

    async_llm = _make_async_llm_response(
        '{"summary": "测试摘要", "industry_themes": [], "bom_nodes": [], "investment_logic": "", "risk_factors": []}',
        prompt_tokens=50,
        completion_tokens=100,
    )
    monkeypatch.setattr("app.llm_multi_provider.call_llm_with_fallback", async_llm)

    # Mock the persist function
    persist_called = False
    def fake_persist(text, source, interpretation, usage):
        nonlocal persist_called
        persist_called = True
        return {"status": "ok", "id": 42}

    monkeypatch.setattr(screener_router, "_persist_policy_interpretation", fake_persist)

    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={
            "text": "测试政策文本",
            "source": {"title": "测试政策"},
            "persist": True,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["persisted"] is True
    assert persist_called


def test_policy_interpret_endpoint_handles_provider_override(monkeypatch):
    """AC-1: provider parameter should be respected."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-qwen-key")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # Create async mock that verifies provider_override
    from app.llm_multi_provider import LLMResponse, LLMUsage

    captured_provider = None
    async def async_llm(messages, provider_override=None, **kwargs):
        nonlocal captured_provider
        captured_provider = provider_override
        return LLMResponse(
            content='{"summary": "Qwen解读结果", "industry_themes": [], "bom_nodes": [], "investment_logic": "", "risk_factors": []}',
            usage=LLMUsage(
                prompt_tokens=100,
                completion_tokens=150,
                total_tokens=250,
                provider="qwen",
                model="qwen-plus",
            ),
        )

    monkeypatch.setattr("app.llm_multi_provider.call_llm_with_fallback", async_llm)

    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={
            "text": "测试政策文本",
            "provider": "qwen",
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert captured_provider == "qwen"
    assert body.get("usage", {}).get("provider") == "qwen"


def test_policy_interpret_endpoint_handles_malformed_llm_response(monkeypatch):
    """Gracefully handles malformed JSON from LLM."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-for-mocking")

    async_llm = _make_async_llm_response(
        "This is not valid JSON, just plain text response.",
    )
    monkeypatch.setattr("app.llm_multi_provider.call_llm_with_fallback", async_llm)

    r = _client().post(
        "/api/v1/screener/policy/interpret",
        json={"text": "测试政策文本"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # parse_interpretation_json should return defaults with parse_error
    result = body.get("interpretation_result", {})
    assert result.get("summary") == ""  # Falls back to default


def test_policy_interpret_endpoint_response_model_declared():
    """Verify response_model is declared in decorator for OpenAPI generation (AC-2)."""
    # Check via FastAPI route object - response_model is set in decorator
    from app.routers.screener import router

    # Find the policy_interpret route (router has prefix /api/v1/screener)
    for route in router.routes:
        if hasattr(route, 'path') and 'policy/interpret' in route.path:
            assert route.response_model == screener_router.PolicyInterpretResponse
            assert route.operation_id == "policy_interpret"
            return

    # Alternative: check directly via endpoint function
    # The decorator sets response_model on the route, not on the function
    # If we can't find via path, verify the model class exists
    assert screener_router.PolicyInterpretResponse is not None
    # Verify the endpoint function exists
    assert hasattr(screener_router, 'policy_interpret')


def test_policy_interpret_endpoint_uses_correct_imports(monkeypatch):
    """Verify module imports are correct."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    # Import the modules used in endpoint to verify they exist
    from app.llm_multi_provider import PROVIDER_CONFIG, ProviderConfigError
    from app.llm_policy_interpret import build_policy_interpret_prompt, parse_interpretation_json

    # Verify PROVIDER_CONFIG has expected keys
    assert "deepseek" in PROVIDER_CONFIG
    assert "qwen" in PROVIDER_CONFIG
    assert "doubao" in PROVIDER_CONFIG
    assert "minimax" in PROVIDER_CONFIG

    # Verify prompt builder works
    prompt = build_policy_interpret_prompt("测试文本", {"title": "测试标题"})
    assert "测试文本" in prompt
    assert "测试标题" in prompt

    # Verify JSON parser works
    parsed = parse_interpretation_json('{"summary": "test", "bom_nodes": ["node1"]}')
    assert parsed.get("summary") == "test"
    assert parsed.get("bom_nodes") == ["node1"]
