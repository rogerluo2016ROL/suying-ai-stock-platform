"""
Tests for session_resolver.

Uses tmp_path (pytest fixture) to mock a ~/.claude/projects/<slug>/ directory
with multiple JSONL files and verifies that:
  - resolve_session() returns the one with the latest mtime  (AC: mtime newest)
  - list_sessions() returns all files sorted by mtime descending
  - resolve_session() returns None when no JSONL files exist

Run from tools/team-dashboard/server/:
    pytest tests/
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

# conftest.py in parent directory adds server dir to sys.path
from session_resolver import (
    SessionInfo,
    _latest_in_dir,
    list_sessions,
    resolve_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, content: str = '{"type":"user"}\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# _latest_in_dir tests (internal helper, directly testable)
# ---------------------------------------------------------------------------

class TestLatestInDir:
    def test_returns_none_for_empty_dir(self, tmp_path: Path):
        result = _latest_in_dir(tmp_path)
        assert result is None

    def test_returns_only_file(self, tmp_path: Path):
        p = tmp_path / "abc123.jsonl"
        _write_jsonl(p)
        result = _latest_in_dir(tmp_path)
        assert result is not None
        assert result.session_id == "abc123"
        assert result.jsonl_path == p

    def test_returns_latest_of_multiple(self, tmp_path: Path):
        older = tmp_path / "old-session.jsonl"
        newer = tmp_path / "new-session.jsonl"
        _write_jsonl(older)
        time.sleep(0.02)  # ensure distinct mtime
        _write_jsonl(newer)
        result = _latest_in_dir(tmp_path)
        assert result is not None
        assert result.session_id == "new-session"

    def test_ignores_non_jsonl_files(self, tmp_path: Path):
        (tmp_path / "notes.txt").write_text("hello")
        (tmp_path / "data.json").write_text("{}")
        result = _latest_in_dir(tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# resolve_session (mocked filesystem) tests
# ---------------------------------------------------------------------------

class TestResolveSession:
    def test_no_project_dir_returns_none(self, tmp_path: Path):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        with patch("session_resolver.Path.home", return_value=fake_home):
            result = resolve_session(repo_path="/fake/project")
        assert result is None

    def test_picks_newest_jsonl(self, tmp_path: Path):
        slug = "-Users-test-Repo"
        project_dir = tmp_path / ".claude" / "projects" / slug
        project_dir.mkdir(parents=True)

        old = project_dir / "session-001.jsonl"
        new = project_dir / "session-002.jsonl"
        _write_jsonl(old)
        time.sleep(0.02)
        _write_jsonl(new)

        # Patch Path.home() so resolver looks in our tmp_path
        with patch("session_resolver.Path.home", return_value=tmp_path):
            result = resolve_session(repo_path="/Users/test/Repo")

        assert result is not None
        assert result.session_id == "session-002"

    def test_no_jsonl_files_returns_none(self, tmp_path: Path):
        slug = "-Users-test-EmptyProject"
        project_dir = tmp_path / ".claude" / "projects" / slug
        project_dir.mkdir(parents=True)

        with patch("session_resolver.Path.home", return_value=tmp_path):
            result = resolve_session(repo_path="/Users/test/EmptyProject")

        assert result is None


# ---------------------------------------------------------------------------
# list_sessions tests
# ---------------------------------------------------------------------------

class TestListSessions:
    def test_sorted_newest_first(self, tmp_path: Path):
        slug = "-Users-test-SortRepo"
        project_dir = tmp_path / ".claude" / "projects" / slug
        project_dir.mkdir(parents=True)

        for name in ("session-a", "session-b", "session-c"):
            _write_jsonl(project_dir / f"{name}.jsonl")
            time.sleep(0.02)

        with patch("session_resolver.Path.home", return_value=tmp_path):
            sessions = list_sessions(repo_path="/Users/test/SortRepo")

        assert len(sessions) == 3
        assert sessions[0].session_id == "session-c"
        assert sessions[-1].session_id == "session-a"

    def test_empty_when_no_dir(self, tmp_path: Path):
        with patch("session_resolver.Path.home", return_value=tmp_path):
            sessions = list_sessions(repo_path="/nonexistent/path")
        assert sessions == []
