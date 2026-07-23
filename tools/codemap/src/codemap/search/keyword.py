"""关键词检索（FTS5，06 §1）。nodes_fts external-content 表（build 末尾 rebuild）。"""

from __future__ import annotations
import sqlite3


def search(query: str, db: sqlite3.Connection, limit: int = 15) -> list[dict]:
    """FTS5 MATCH；失败/空 → fallback nodes.name LIKE（三态降级第一档）。"""
    try:
        rows = db.execute(
            "SELECT n.id, n.type, n.name, n.file_path FROM nodes_fts f "
            "JOIN nodes n ON n.rowid = f.rowid WHERE nodes_fts MATCH ? LIMIT ?",
            (query, limit),
        ).fetchall()
        if rows:
            return [_row_dict(r) for r in rows]
    except sqlite3.OperationalError:
        pass
    # fallback：name LIKE
    rows = db.execute(
        "SELECT id, type, name, file_path FROM nodes WHERE name LIKE ? LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [_row_dict(r) for r in rows]


def _row_dict(r) -> dict:
    return {"id": r[0], "type": r[1], "name": r[2], "file_path": r[3]}
