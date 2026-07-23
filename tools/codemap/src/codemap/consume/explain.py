"""explain（07 §2）：节点深度解释（邻居 + 源码片段）。"""

from __future__ import annotations
import sqlite3
from pathlib import Path


def explain(target: str, db: sqlite3.Connection, project_root: str | Path | None = None) -> str:
    node = _resolve(target, db)
    if not node:
        return f"(未找到节点: {target})"
    nid, ntype, name, file_path, start_line, end_line, summary = node
    neighbors = db.execute(
        "SELECT src, type FROM edges WHERE dst=? "
        "UNION SELECT dst, type FROM edges WHERE src=?",
        (nid, nid),
    ).fetchall()
    lines = [f"# {name}（{ntype}）", f"- id: `{nid}`", f"- file: `{file_path}`",
             f"- lines: {start_line}-{end_line}", f"- summary: {summary or ''}"]
    if file_path and project_root:
        src = _read_source(Path(project_root) / file_path, start_line, end_line)
        if src:
            lines += ["", "```", src, "```"]
    lines += ["", "## 邻居"]
    for other, etype in neighbors:
        lines.append(f"- [{etype}] {other}")
    return "\n".join(lines)


def _resolve(target: str, db: sqlite3.Connection):
    rows = db.execute(
        "SELECT id, type, name, file_path, start_line, end_line, summary FROM nodes "
        "WHERE id=? OR name=? OR file_path=? LIMIT 1",
        (target, Path(target).name, target),
    ).fetchall()
    return rows[0] if rows else None


def _read_source(path: Path, start, end):
    if not path.is_file() or not start:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None
    return "\n".join(lines[start - 1:end])
