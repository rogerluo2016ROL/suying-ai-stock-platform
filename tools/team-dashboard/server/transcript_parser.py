"""
transcript_parser — decode Claude Code JSONL transcript lines.

Two public functions:
  parse_launch_prompt(line: str) -> dict   parse the first user message for
                                           agf-team-start metadata
  parse_line(line: str) -> dict | None     classify a transcript line into a
                                           structured timeline event

JSONL line types we recognise (spec §5):
  tool_use  SendMessage  → { event_type: "SendMessage",  to, summary, message_snippet }
  tool_use  TaskCreate   → { event_type: "TaskCreate",   subject, owner }
  tool_use  TaskUpdate   → { event_type: "TaskUpdate",   task_id, status }
  tool_use  Agent        → { event_type: "Agent",        subagent_type, description }
  assistant message      → { event_type: "assistant",    text_snippet }

Any other line type → return None, emit WARN log.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAUNCH_RE = re.compile(
    r"/agf-team-start\s+(?P<desc>.+?)(?:\s*\[teammates:\s*(?P<mates>[^\]]+)\])?$",
    re.IGNORECASE | re.DOTALL,
)

_TEAMMATES_INLINE_RE = re.compile(
    r"\[teammates:\s*(?P<mates>[^\]]+)\]", re.IGNORECASE
)


def _extract_text_from_content(content: Any) -> str:
    """Return plain text from a message content field (str or list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        return json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_launch_prompt(line: str) -> dict[str, Any]:
    """
    Parse the first user message line of a session to extract agf-team-start
    metadata.

    Returns a dict with keys:
        feature_desc: str   — e.g. "Add login flow"
        teammates:    list  — e.g. ["backend-dev", "frontend-dev"]

    Falls back gracefully if the line is not a recognisable launch prompt.
    """
    obj = _parse_json_line(line)
    if obj is None:
        return {"feature_desc": "(unparsed launch)", "teammates": []}

    msg = obj.get("message", {})
    content_raw = msg.get("content", "") if isinstance(msg, dict) else ""
    text = _extract_text_from_content(content_raw).strip()

    # Match the standard launch pattern
    m = _LAUNCH_RE.search(text)
    if m:
        desc = m.group("desc").strip()
        mates_str = m.group("mates") or ""
        # Strip a trailing [teammates: ...] from desc if it slipped in
        desc = _TEAMMATES_INLINE_RE.sub("", desc).strip()
        teammates = [t.strip() for t in mates_str.split(",") if t.strip()] if mates_str else []
        return {"feature_desc": desc, "teammates": teammates}

    # Fallback: maybe teammates are in a separate marker elsewhere in text
    mates_match = _TEAMMATES_INLINE_RE.search(text)
    teammates = (
        [t.strip() for t in mates_match.group("mates").split(",") if t.strip()]
        if mates_match
        else []
    )

    return {"feature_desc": "(unparsed launch)", "teammates": teammates}


def parse_line(line: str) -> dict[str, Any] | None:
    """
    Parse a single JSONL transcript line into a structured timeline event dict.

    Returns the *first* event found on the line, or None if the line carries no
    timeline-relevant content.  When a single line may contain multiple tool_use
    blocks (common for assistant turns), call parse_all_events_from_line() instead
    to retrieve all of them.

    For lines with unrecognised *line types* (e.g. unknown top-level ``type``
    values), emits a WARN log and returns None so the stream is not blocked.

    Returned dict always contains:
        event_type: str
        timestamp:  str   (ISO-8601 if available, else "")
        summary:    str
        details:    dict
    """
    obj = _parse_json_line(line)
    if obj is None:
        return None

    line_type = obj.get("type", "")

    # Delegate assistant-line parsing to the multi-event function to avoid
    # duplicating the extraction logic and silently dropping extra tool_use blocks.
    if line_type == "assistant":
        events = parse_all_events_from_line(line)
        return events[0] if events else None

    # user messages — only relevant as raw text (parse_launch_prompt handles them)
    if line_type == "user":
        return None

    # Metadata lines that are expected and silently skipped
    _SILENT_SKIP = {
        "last-prompt", "permission-mode", "attachment", "file-history-snapshot",
        "ai-title", "queue-operation", "summary",
    }
    if line_type in _SILENT_SKIP:
        return None

    # Unknown line types → WARN log + skip
    if line_type:
        logger.warning("transcript_parser: unknown line type %r — skipping", line_type)
    return None


def parse_all_events_from_line(line: str) -> list[dict[str, Any]]:
    """
    Like parse_line but returns ALL events extracted from a single JSONL line
    (an assistant turn may contain multiple tool_use blocks).
    """
    obj = _parse_json_line(line)
    if obj is None:
        return []

    line_type = obj.get("type", "")
    timestamp = obj.get("timestamp", "")

    if line_type != "assistant":
        return []

    msg = obj.get("message", {})
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return []

    content = msg.get("content", [])
    if not isinstance(content, list):
        return []

    results: list[dict[str, Any]] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")

        if item_type == "tool_use":
            tool_name = item.get("name", "")
            inp = item.get("input", {}) or {}

            if tool_name == "SendMessage":
                results.append(
                    {
                        "event_type": "SendMessage",
                        "timestamp": timestamp,
                        "summary": f"→ {inp.get('to', '?')}: {inp.get('summary', '')}",
                        "details": {
                            "to": inp.get("to", ""),
                            "summary": inp.get("summary", ""),
                            "message_snippet": str(inp.get("message", ""))[:120],
                        },
                    }
                )
            elif tool_name in ("TaskCreate",):
                results.append(
                    {
                        "event_type": "TaskCreate",
                        "timestamp": timestamp,
                        "summary": f"TaskCreate: {inp.get('subject', inp.get('title', '?'))}",
                        "details": {
                            "subject": inp.get("subject", inp.get("title", "")),
                            "owner": inp.get("owner", ""),
                            "description": str(inp.get("description", ""))[:120],
                        },
                    }
                )
            elif tool_name == "TaskUpdate":
                results.append(
                    {
                        "event_type": "TaskUpdate",
                        "timestamp": timestamp,
                        "summary": f"TaskUpdate #{inp.get('taskId','?')} → {inp.get('status','')}",
                        "details": {
                            "task_id": inp.get("taskId", ""),
                            "status": inp.get("status", ""),
                            "subject": inp.get("subject", ""),
                        },
                    }
                )
            elif tool_name == "Agent":
                results.append(
                    {
                        "event_type": "Agent",
                        "timestamp": timestamp,
                        "summary": f"Spawn {inp.get('subagent_type', '?')}: {inp.get('description', '')[:60]}",
                        "details": {
                            "subagent_type": inp.get("subagent_type", ""),
                            "description": str(inp.get("description", ""))[:120],
                        },
                    }
                )
            # else: silently skip other tool_use types

        elif item_type == "text":
            text = item.get("text", "").strip()
            if text:
                results.append(
                    {
                        "event_type": "assistant",
                        "timestamp": timestamp,
                        "summary": text[:100],
                        "details": {"text_snippet": text[:200]},
                    }
                )

    return results
