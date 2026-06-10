"""
Tests for transcript_parser.

Feeds 4 known event types + 1 unknown type through parse_line / parse_launch_prompt,
verifying correct structure and that unknown types are ignored (AC-3, AC-9).

Run from tools/team-dashboard/server/:
    pytest tests/
"""

from __future__ import annotations

import json
import logging

import pytest

# conftest.py in parent directory adds the server dir to sys.path
from transcript_parser import (
    parse_all_events_from_line,
    parse_launch_prompt,
    parse_line,
)


# ---------------------------------------------------------------------------
# Fixtures – sample JSONL lines
# ---------------------------------------------------------------------------

def _make_assistant_line(tools: list[dict], timestamp: str = "2026-05-13T10:00:00+08:00") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": timestamp,
            "message": {
                "role": "assistant",
                "content": tools,
            },
        }
    )


SEND_MESSAGE_LINE = _make_assistant_line(
    [
        {
            "type": "tool_use",
            "name": "SendMessage",
            "input": {
                "to": "frontend-dev",
                "summary": "API contract ready",
                "message": "SSE contract frozen. Endpoint live on :8765.",
            },
        }
    ]
)

TASK_CREATE_LINE = _make_assistant_line(
    [
        {
            "type": "tool_use",
            "name": "TaskCreate",
            "input": {
                "subject": "Build login API",
                "owner": "backend-dev",
                "description": "Implement POST /api/auth/login",
            },
        }
    ]
)

AGENT_LINE = _make_assistant_line(
    [
        {
            "type": "tool_use",
            "name": "Agent",
            "input": {
                "subagent_type": "backend-dev",
                "description": "Build backend data layer",
            },
        }
    ]
)

ASSISTANT_TEXT_LINE = _make_assistant_line(
    [
        {
            "type": "text",
            "text": "I will now implement the login endpoint.",
        }
    ]
)

UNKNOWN_TYPE_LINE = json.dumps(
    {
        "type": "some-future-internal-type",
        "timestamp": "2026-05-13T10:05:00+08:00",
        "payload": {"data": 42},
    }
)


# ---------------------------------------------------------------------------
# parse_launch_prompt tests
# ---------------------------------------------------------------------------

class TestParseLaunchPrompt:
    def _user_line(self, text: str) -> str:
        return json.dumps(
            {"type": "user", "message": {"role": "user", "content": text}}
        )

    def test_standard_launch(self):
        line = self._user_line(
            "/agf-team-start Add login flow [teammates: backend-dev, frontend-dev]"
        )
        result = parse_launch_prompt(line)
        assert result["feature_desc"] == "Add login flow"
        assert result["teammates"] == ["backend-dev", "frontend-dev"]

    def test_launch_without_teammates(self):
        line = self._user_line("/agf-team-start Fix auth bug")
        result = parse_launch_prompt(line)
        assert result["feature_desc"] == "Fix auth bug"
        assert result["teammates"] == []

    def test_fallback_non_agf_start(self):
        line = self._user_line("Just a regular message, nothing to do with agf-team-start")
        result = parse_launch_prompt(line)
        assert result["feature_desc"] == "(unparsed launch)"
        assert result["teammates"] == []

    def test_fallback_slash_clear(self):
        line = self._user_line("/clear")
        result = parse_launch_prompt(line)
        assert result["feature_desc"] == "(unparsed launch)"
        assert result["teammates"] == []

    def test_malformed_json(self):
        result = parse_launch_prompt("not json at all")
        assert result["feature_desc"] == "(unparsed launch)"
        assert result["teammates"] == []

    def test_teammates_trimmed(self):
        line = self._user_line(
            "/agf-team-start My feature [teammates:  backend-dev ,  ai-agent-dev ]"
        )
        result = parse_launch_prompt(line)
        assert result["teammates"] == ["backend-dev", "ai-agent-dev"]


# ---------------------------------------------------------------------------
# parse_line tests – known event types
# ---------------------------------------------------------------------------

class TestParseLineKnownTypes:
    def test_send_message(self):
        result = parse_line(SEND_MESSAGE_LINE)
        assert result is not None
        assert result["event_type"] == "SendMessage"
        assert result["details"]["to"] == "frontend-dev"
        assert "API contract ready" in result["details"]["summary"]

    def test_task_create(self):
        result = parse_line(TASK_CREATE_LINE)
        assert result is not None
        assert result["event_type"] == "TaskCreate"
        assert result["details"]["subject"] == "Build login API"
        assert result["details"]["owner"] == "backend-dev"

    def test_agent_spawn(self):
        result = parse_line(AGENT_LINE)
        assert result is not None
        assert result["event_type"] == "Agent"
        assert result["details"]["subagent_type"] == "backend-dev"

    def test_assistant_text(self):
        result = parse_line(ASSISTANT_TEXT_LINE)
        assert result is not None
        assert result["event_type"] == "assistant"
        assert "login endpoint" in result["summary"]


# ---------------------------------------------------------------------------
# parse_line tests – unknown type should be silently ignored
# ---------------------------------------------------------------------------

class TestParseLineUnknownType:
    def test_unknown_returns_none(self, caplog):
        with caplog.at_level(logging.WARNING, logger="transcript_parser"):
            result = parse_line(UNKNOWN_TYPE_LINE)
        assert result is None
        assert any("some-future-internal-type" in r.message for r in caplog.records)

    def test_silent_skip_types_return_none(self):
        for lt in ("last-prompt", "permission-mode", "attachment", "ai-title"):
            line = json.dumps({"type": lt})
            assert parse_line(line) is None, f"Expected None for type={lt}"


# ---------------------------------------------------------------------------
# parse_all_events_from_line – multiple tools in one turn
# ---------------------------------------------------------------------------

class TestParseAllEvents:
    def test_multiple_tool_uses(self):
        line = _make_assistant_line(
            [
                {
                    "type": "tool_use",
                    "name": "SendMessage",
                    "input": {"to": "frontend-dev", "summary": "hi", "message": "hello"},
                },
                {
                    "type": "tool_use",
                    "name": "TaskCreate",
                    "input": {"subject": "Task X", "owner": "backend-dev", "description": ""},
                },
            ]
        )
        events = parse_all_events_from_line(line)
        assert len(events) == 2
        types = {e["event_type"] for e in events}
        assert types == {"SendMessage", "TaskCreate"}

    def test_empty_on_non_assistant_line(self):
        assert parse_all_events_from_line(UNKNOWN_TYPE_LINE) == []

    def test_five_fixture_lines(self):
        """
        Feed 4 known + 1 unknown event; verify 4 structured results and unknown is skipped.
        """
        known_lines = [SEND_MESSAGE_LINE, TASK_CREATE_LINE, AGENT_LINE, ASSISTANT_TEXT_LINE]
        all_events = []
        for line in known_lines:
            all_events.extend(parse_all_events_from_line(line))
        # Unknown line produces nothing
        assert parse_all_events_from_line(UNKNOWN_TYPE_LINE) == []
        assert len(all_events) == 4
        event_types = {e["event_type"] for e in all_events}
        assert event_types == {"SendMessage", "TaskCreate", "Agent", "assistant"}
