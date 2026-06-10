"""
Tests for watcher.py.

- parse_worktree_list: verify parsing of git porcelain output
- poll_worktrees: mock subprocess; verify return value
- JournalTailer: verify it reads only new lines after seek_to_end
- _is_under / _collect_docs_dirs: sanity checks
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from watcher import (
    JournalTailer,
    WatchEvent,
    WatchKind,
    _collect_docs_dirs,
    _is_under,
    load_all_tasks,
    parse_worktree_list,
    poll_worktrees,
)


# ---------------------------------------------------------------------------
# parse_worktree_list
# ---------------------------------------------------------------------------

class TestParseWorktreeList:
    PORCELAIN_OUTPUT = """\
worktree /Users/pc2026/repo
HEAD abc1234567890abcdef1234567890abcdef123456
branch refs/heads/main

worktree /Users/pc2026/repo/.worktrees/feature-branch
HEAD def1234567890abcdef1234567890abcdef123456
branch refs/heads/feature/my-feature

"""

    def test_parses_two_entries(self):
        result = parse_worktree_list(self.PORCELAIN_OUTPUT)
        assert len(result) == 2

    def test_first_entry_path(self):
        result = parse_worktree_list(self.PORCELAIN_OUTPUT)
        assert result[0]["path"] == "/Users/pc2026/repo"

    def test_branch_stripped(self):
        result = parse_worktree_list(self.PORCELAIN_OUTPUT)
        assert result[0]["branch"] == "main"
        assert result[1]["branch"] == "feature/my-feature"

    def test_empty_output(self):
        result = parse_worktree_list("")
        assert result == []

    def test_detached_head(self):
        output = "worktree /tmp/repo\nHEAD aabbcc\ndetached\n\n"
        result = parse_worktree_list(output)
        assert result[0].get("detached") is True


# ---------------------------------------------------------------------------
# poll_worktrees (mock subprocess)
# ---------------------------------------------------------------------------

class TestPollWorktrees:
    def test_returns_parsed_list(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "worktree /repo\nHEAD aaa\nbranch refs/heads/main\n\n"
        )
        with patch("watcher.subprocess.run", return_value=mock_result):
            result = poll_worktrees("/repo")
        assert len(result) == 1
        assert result[0]["branch"] == "main"

    def test_returns_empty_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 128
        mock_result.stderr = "not a git repo"
        with patch("watcher.subprocess.run", return_value=mock_result):
            result = poll_worktrees("/not-a-repo")
        assert result == []

    def test_handles_file_not_found(self):
        with patch("watcher.subprocess.run", side_effect=FileNotFoundError):
            result = poll_worktrees("/repo")
        assert result == []


# ---------------------------------------------------------------------------
# JournalTailer
# ---------------------------------------------------------------------------

class TestJournalTailer:
    def test_seek_to_end_skips_existing(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        f.write_text('{"type":"user"}\n{"type":"assistant"}\n')
        tailer = JournalTailer(f)
        tailer.seek_to_end()
        lines = tailer.read_new_lines()
        assert lines == []

    def test_reads_appended_lines(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        f.write_text('{"type":"user"}\n')
        tailer = JournalTailer(f)
        tailer.seek_to_end()
        # Append new line
        with f.open("a") as fh:
            fh.write('{"type":"assistant","message":{"role":"assistant","content":[]}}\n')
        lines = tailer.read_new_lines()
        assert len(lines) == 1

    def test_reads_from_beginning_if_not_seeked(self, tmp_path: Path):
        f = tmp_path / "session.jsonl"
        f.write_text('{"type":"user"}\n{"type":"assistant","message":{"role":"assistant","content":[]}}\n')
        tailer = JournalTailer(f)
        lines = tailer.read_new_lines()
        assert len(lines) == 2

    def test_handles_missing_file(self, tmp_path: Path):
        tailer = JournalTailer(tmp_path / "nonexistent.jsonl")
        lines = tailer.read_new_lines()
        assert lines == []


# ---------------------------------------------------------------------------
# load_all_tasks
# ---------------------------------------------------------------------------

class TestLoadAllTasks:
    def test_loads_json_files(self, tmp_path: Path):
        (tmp_path / "task1.json").write_text('{"id":"1","status":"pending"}')
        (tmp_path / "task2.json").write_text('{"id":"2","status":"completed"}')
        tasks = load_all_tasks(tmp_path)
        assert len(tasks) == 2
        ids = {t["id"] for t in tasks}
        assert ids == {"1", "2"}

    def test_skips_invalid_json(self, tmp_path: Path):
        (tmp_path / "bad.json").write_text("not json")
        (tmp_path / "good.json").write_text('{"id":"g"}')
        tasks = load_all_tasks(tmp_path)
        assert len(tasks) == 1

    def test_empty_dir_returns_empty(self, tmp_path: Path):
        tasks = load_all_tasks(tmp_path)
        assert tasks == []

    def test_missing_dir_returns_empty(self, tmp_path: Path):
        tasks = load_all_tasks(tmp_path / "nonexistent")
        assert tasks == []


# ---------------------------------------------------------------------------
# _is_under / _collect_docs_dirs
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_is_under_true(self):
        assert _is_under(Path("/a/b/c.txt"), Path("/a/b")) is True

    def test_is_under_false(self):
        assert _is_under(Path("/x/y.txt"), Path("/a/b")) is False

    def test_is_under_same_path(self):
        # Path.relative_to() succeeds for equal paths (returns "."), so _is_under
        # returns True — this is acceptable since a directory touching itself would
        # just be ignored by the caller's suffix check.
        assert _is_under(Path("/a/b"), Path("/a/b")) is True

    def test_collect_docs_dirs(self):
        dirs = _collect_docs_dirs("/my/repo")
        names = [d.name for d in dirs]
        assert set(names) == {"plans", "prd", "qa", "reviews"}


# ---------------------------------------------------------------------------
# run_watcher — empty watch_targets early-return (M-3w)
# ---------------------------------------------------------------------------

class TestRunWatcherEmptyTargets:
    """M-3w: verify run_watcher takes the early-return path when no directories exist."""

    async def test_empty_targets_delegates_to_poll_loop(self, tmp_path: Path):
        """When all candidate watch directories are absent, run_watcher should
        call _worktree_poll_loop (not awatch) and then return cleanly."""
        from watcher import run_watcher

        queue: asyncio.Queue[WatchEvent] = asyncio.Queue()
        poll_called = False

        async def fake_poll_loop(q, repo, interval):
            nonlocal poll_called
            poll_called = True
            # Return immediately — the real loop runs forever.

        with (
            patch("watcher._worktree_poll_loop", side_effect=fake_poll_loop),
            patch("pathlib.Path.home", return_value=tmp_path / "no-home"),
        ):
            # repo_path has no docs/ subdirs; project_dir is nonexistent.
            await run_watcher(
                queue=queue,
                repo_path=str(tmp_path),
                session_id="test-session-id",
                project_dir=tmp_path / "no-project",
            )

        assert poll_called, (
            "_worktree_poll_loop was not called — "
            "empty-watch-targets early-return path is broken"
        )
