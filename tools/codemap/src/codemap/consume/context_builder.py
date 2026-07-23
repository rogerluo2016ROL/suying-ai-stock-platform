"""context-builder（07 §1）：query → 检索 + 1-hop 扩展 → markdown 上下文。"""

from __future__ import annotations
import sqlite3


def build_context(query: str, db: sqlite3.Connection, max_nodes: int = 15) -> str:
    matched = _fts_search(query, db, max_nodes)
    matched_ids = [m[0] for m in matched]
    if not matched_ids:
        return f"(无匹配节点: {query})"
    expanded = set(matched_ids)
    ph = ",".join("?" * len(matched_ids))
    for row in db.execute(
        f"SELECT src, dst FROM edges WHERE src IN ({ph}) OR dst IN ({ph})",
        (*matched_ids, *matched_ids),
    ).fetchall():
        expanded.add(row[0])
        expanded.add(row[1])
    eph = ",".join("?" * len(expanded))
    nodes = db.execute(
        f"SELECT id, type, name, file_path, summary FROM nodes WHERE id IN ({eph})",
        tuple(expanded),
    ).fetchall()
    edges = db.execute(
        f"SELECT src, dst, type FROM edges WHERE src IN ({eph}) AND dst IN ({eph})",
        (*expanded, *expanded),
    ).fetchall()
    lines = [f"# Context: {query}", "", "## 节点"]
    for nid, t, name, fp, summary in nodes:
        lines.append(f"- **{name}** ({t}) `{fp}` — {summary or ''}")
    lines += ["", "## 关系"]
    for src, dst, et in edges:
        lines.append(f"- {src} --[{et}]--> {dst}")
    return "\n".join(lines)


def _fts_search(query: str, db: sqlite3.Connection, limit: int):
    # M4：nodes.name LIKE（nodes_fts external-content 未 populate，FTS5 索引留 M5）
    return db.execute(
        "SELECT id, name FROM nodes WHERE name LIKE ? LIMIT ?", (f"%{query}%", limit)
    ).fetchall()
