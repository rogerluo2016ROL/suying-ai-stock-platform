"""
watcher.py — filesystem + git worktree event watcher.

Three-way watchfiles monitoring:
  1. ~/.claude/tasks/          — TaskCreate / TaskUpdate events
  2. ~/.claude/projects/<slug>/ — transcript JSONL updates (new lines appended)
  3. docs/{plans,prd,qa,reviews}/ — artifact files (plan / PRD / SIT / review)

Plus a 5-second polling loop for `git worktree list --porcelain`.

All detected changes are put onto an asyncio.Queue[WatchEvent] that the SSE
endpoint (main.py) consumes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class WatchKind(str, Enum):
    TASK_CHANGE = "task.update"
    TRANSCRIPT_APPEND = "timeline.append"
    ARTIFACT_CHANGE = "artifact.update"
    WORKTREE_POLL = "worktree.status"


@dataclass
class WatchEvent:
    kind: WatchKind
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Worktree parser
# ---------------------------------------------------------------------------

def parse_worktree_list(output: str) -> list[dict[str, Any]]:
    """
    Parse the output of `git worktree list --porcelain` into a list of dicts.

    Each block looks like:
        worktree /path/to/wt
        HEAD abc123
        branch refs/heads/feature/foo
    """
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[len("worktree "):]}
        elif line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif line.startswith("branch "):
            branch = line[len("branch "):]
            # strip refs/heads/ prefix
            current["branch"] = branch.replace("refs/heads/", "")
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["detached"] = True
    if current:
        worktrees.append(current)
    return worktrees


def poll_worktrees(repo_path: str) -> list[dict[str, Any]]:
    """Run `git worktree list --porcelain` in repo_path and return parsed list."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("git worktree list failed: %s", result.stderr.strip())
            return []
        return parse_worktree_list(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.warning("poll_worktrees error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Read all tasks from ~/.claude/tasks/
# ---------------------------------------------------------------------------

def load_all_tasks(tasks_dir: Path) -> list[dict[str, Any]]:
    """Load all *.json files from the tasks directory."""
    tasks: list[dict[str, Any]] = []
    if not tasks_dir.exists():
        return tasks
    for p in tasks_dir.glob("*.json"):
        try:
            data = json.loads(p.read_text())
            tasks.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load task %s: %s", p, exc)
    return tasks


# ---------------------------------------------------------------------------
# JSONL tail reader — track file position, emit only new lines
# ---------------------------------------------------------------------------

class JournalTailer:
    """Read new lines appended to a JSONL file since the last read."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._pos: int = 0

    def read_new_lines(self) -> list[str]:
        """Return all lines added since the last call."""
        lines: list[str] = []
        try:
            with self.path.open("r", errors="replace") as fh:
                fh.seek(self._pos)
                for raw in fh:
                    stripped = raw.rstrip("\n")
                    if stripped:
                        lines.append(stripped)
                self._pos = fh.tell()
        except OSError as exc:
            logger.warning("JournalTailer read error for %s: %s", self.path, exc)
        return lines

    def seek_to_end(self) -> None:
        """Fast-forward to the end of the file (skip historical content)."""
        try:
            with self.path.open("r", errors="replace") as fh:
                fh.seek(0, 2)  # SEEK_END
                self._pos = fh.tell()
        except OSError:
            self._pos = 0


# ---------------------------------------------------------------------------
# Main watcher coroutine
# ---------------------------------------------------------------------------

async def run_watcher(
    queue: asyncio.Queue[WatchEvent],
    repo_path: str,
    session_id: str,
    project_dir: Path,
    worktree_poll_interval: float = 5.0,
) -> None:
    """
    Start the 3-way watchfiles monitor + worktree poll loop.

    All changes are delivered via *queue*.

    Parameters
    ----------
    queue:                 asyncio Queue to put WatchEvent objects
    repo_path:             absolute path to the git repository root
    session_id:            current session ID (used to find the JSONL file)
    project_dir:           ~/.claude/projects/<slug>/ directory
    worktree_poll_interval: seconds between git worktree polls (default 5)
    """
    try:
        from watchfiles import awatch, Change  # type: ignore[import-untyped]
    except ImportError:
        logger.error("watchfiles not installed — polling worktrees only")
        await _worktree_poll_loop(queue, repo_path, worktree_poll_interval)
        return

    tasks_dir = Path.home() / ".claude" / "tasks"
    jsonl_path = project_dir / f"{session_id}.jsonl"
    docs_dirs = _collect_docs_dirs(repo_path)

    # Determine which directories actually exist to watch
    watch_targets: set[str] = set()
    for d in [tasks_dir, project_dir] + docs_dirs:
        if d.exists():
            watch_targets.add(str(d))
    if not watch_targets:
        logger.warning(
            "watcher: no directories to watch — skipping awatch, polling worktrees only"
        )
        await _worktree_poll_loop(queue, repo_path, worktree_poll_interval)
        return

    # Journal tailer for transcript JSONL (seek to end on startup)
    tailer = JournalTailer(jsonl_path)
    if jsonl_path.exists():
        tailer.seek_to_end()

    # Launch worktree poll as a concurrent task
    poll_task = asyncio.create_task(
        _worktree_poll_loop(queue, repo_path, worktree_poll_interval)
    )

    logger.info("watcher: monitoring %s", watch_targets)

    try:
        async for changes in awatch(*watch_targets, stop_event=None):
            for change_type, changed_path in changes:
                cp = Path(changed_path)

                # ----------------------------------------------------------
                # Tasks directory
                # ----------------------------------------------------------
                if _is_under(cp, tasks_dir) and cp.suffix == ".json":
                    tasks = load_all_tasks(tasks_dir)
                    await queue.put(
                        WatchEvent(
                            kind=WatchKind.TASK_CHANGE,
                            payload={"tasks": tasks},
                        )
                    )

                # ----------------------------------------------------------
                # Transcript JSONL
                # ----------------------------------------------------------
                elif _is_under(cp, project_dir) and cp.suffix == ".jsonl":
                    # If a new jsonl appeared, re-point the tailer
                    if cp != tailer.path:
                        tailer = JournalTailer(cp)
                        tailer.seek_to_end()
                    else:
                        new_lines = tailer.read_new_lines()
                        for raw_line in new_lines:
                            from transcript_parser import parse_all_events_from_line  # type: ignore[import-not-found]
                            events = parse_all_events_from_line(raw_line)
                            for evt in events:
                                await queue.put(
                                    WatchEvent(
                                        kind=WatchKind.TRANSCRIPT_APPEND,
                                        payload=evt,
                                    )
                                )

                # ----------------------------------------------------------
                # Artifact docs
                # ----------------------------------------------------------
                elif any(_is_under(cp, d) for d in docs_dirs):
                    try:
                        mtime = cp.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    await queue.put(
                        WatchEvent(
                            kind=WatchKind.ARTIFACT_CHANGE,
                            payload={"path": str(cp), "mtime": mtime},
                        )
                    )
    finally:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


async def _worktree_poll_loop(
    queue: asyncio.Queue[WatchEvent],
    repo_path: str,
    interval: float,
) -> None:
    """Periodically poll `git worktree list` and enqueue worktree.status events."""
    while True:
        await asyncio.sleep(interval)
        worktrees = poll_worktrees(repo_path)
        await queue.put(
            WatchEvent(
                kind=WatchKind.WORKTREE_POLL,
                payload={"worktrees": worktrees},
            )
        )


def _collect_docs_dirs(repo_path: str) -> list[Path]:
    """Return the docs sub-directories to watch for artifact changes."""
    base = Path(repo_path) / "docs"
    return [base / sub for sub in ("plans", "prd", "qa", "reviews")]


def _is_under(path: Path, parent: Path) -> bool:
    """Return True if *path* is inside *parent* directory."""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
