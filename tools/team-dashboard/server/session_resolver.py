"""
session_resolver — locate the current Claude Code session JSONL.

Scans `~/.claude/projects/<slug>/` for `.jsonl` files and returns the one
with the highest mtime (most recent session).  The slug is derived from the
current working-directory path, matching the convention Claude Code uses:

    ~/.claude/projects/<path-with-dashes>/  where dashes replace `/`

Public API:
    resolve_session(repo_path: str | None = None) -> SessionInfo | None
    get_project_dir(repo_path: str | None = None) -> Path
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _repo_path_to_slug(repo_path: str) -> str:
    """
    Convert an absolute path to the slug Claude Code uses as the projects subdir.

    Example: /Users/pc2026/Documents/DevAgents/AppGenesisForge
             → -Users-pc2026-Documents-DevAgents-AppGenesisForge
    """
    # Claude Code replaces each "/" with "-" and keeps the leading "-"
    return repo_path.replace("/", "-")


def _find_project_dir(repo_path: str) -> Path | None:
    """Return the ~/.claude/projects/<slug>/ directory for *repo_path*, or None."""
    slug = _repo_path_to_slug(repo_path)
    candidate = Path.home() / ".claude" / "projects" / slug
    if candidate.exists() and candidate.is_dir():
        return candidate
    # Fallback: fuzzy match (last path component)
    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.exists():
        return None
    leaf = Path(repo_path).name  # e.g. "AppGenesisForge"
    for d in projects_root.iterdir():
        if d.is_dir() and d.name.endswith(leaf):
            return d
    return None


# ---------------------------------------------------------------------------
# Public dataclass & API
# ---------------------------------------------------------------------------

@dataclass
class SessionInfo:
    session_id: str
    jsonl_path: Path
    mtime: float
    project_dir: Path


def get_project_dir(repo_path: str | None = None) -> Path | None:
    """Return the ~/.claude/projects/<slug>/ Path, or None if not found."""
    rp = repo_path or os.getcwd()
    return _find_project_dir(rp)


def resolve_session(repo_path: str | None = None) -> SessionInfo | None:
    """
    Scan the project directory for JSONL files and return the one with the
    highest mtime.  Returns None when no JSONL file exists yet.
    """
    rp = repo_path or os.getcwd()
    project_dir = _find_project_dir(rp)

    if project_dir is None:
        logger.warning("session_resolver: no project dir found for %s", rp)
        return None

    return _latest_in_dir(project_dir)


def _latest_in_dir(project_dir: Path) -> SessionInfo | None:
    """Pick the JSONL with the latest mtime in *project_dir*."""
    best: SessionInfo | None = None

    for p in project_dir.glob("*.jsonl"):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue

        # Derive session_id from filename: strip .jsonl suffix
        sid = p.stem

        if best is None or mt > best.mtime:
            best = SessionInfo(
                session_id=sid,
                jsonl_path=p,
                mtime=mt,
                project_dir=project_dir,
            )

    if best is None:
        logger.debug("session_resolver: no JSONL files found in %s", project_dir)

    return best


def list_sessions(repo_path: str | None = None) -> list[SessionInfo]:
    """Return all sessions sorted by mtime descending (newest first)."""
    rp = repo_path or os.getcwd()
    project_dir = _find_project_dir(rp)
    if project_dir is None:
        return []

    results: list[SessionInfo] = []
    for p in project_dir.glob("*.jsonl"):
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        results.append(
            SessionInfo(session_id=p.stem, jsonl_path=p, mtime=mt, project_dir=project_dir)
        )

    results.sort(key=lambda s: s.mtime, reverse=True)
    return results
