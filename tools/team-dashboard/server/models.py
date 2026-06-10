"""
Pydantic data models for Team Dashboard server.

Defines:
- SessionMeta: metadata about the current agf-team-start session
- SSE event envelope + 5 concrete event payload types
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Session metadata (parsed from the first user message in the JSONL transcript)
# ---------------------------------------------------------------------------

class SessionMeta(BaseModel):
    session_id: str
    feature_desc: str = "(unparsed launch)"
    lead: str = "product-lead"
    teammates: list[str] = Field(default_factory=list)
    started_at: str = ""          # ISO-8601 string; empty when unknown
    worktree_path: str = ""       # filled later by watcher / git worktree


# ---------------------------------------------------------------------------
# SSE event payloads
# ---------------------------------------------------------------------------

class InitialPayload(BaseModel):
    meta: SessionMeta
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)   # last 100
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    worktree: list[dict[str, Any]] = Field(default_factory=list)


class TaskUpdatePayload(BaseModel):
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    event_type: str                # "SendMessage" | "TaskCreate" | "Agent" | "assistant"
    timestamp: str = ""
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class ArtifactUpdatePayload(BaseModel):
    path: str
    mtime: float


class WorktreeStatusPayload(BaseModel):
    worktrees: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generic SSE event envelope  (type + payload)
# ---------------------------------------------------------------------------

class SSEEvent(BaseModel):
    type: str           # "initial" | "task.update" | "timeline.append" | "artifact.update" | "worktree.status"
    payload: Any
