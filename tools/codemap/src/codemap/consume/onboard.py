"""onboard（07 §4）：项目概览 + 复杂度热点 + 关键文件。"""

from __future__ import annotations
import sqlite3

from codemap.graph import queries


def onboard(db: sqlite3.Connection) -> str:
    n_files = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    n_nodes = db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    n_edges = db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    by_lang = db.execute(
        "SELECT language, COUNT(*) FROM files GROUP BY language ORDER BY 2 DESC"
    ).fetchall()
    hotspots = queries.complex_nodes(db)
    high_fan = queries.high_fan_in(db)

    lines = ["# Onboard", "", f"- 文件: {n_files}", f"- 节点: {n_nodes}", f"- 边: {n_edges}",
             "", "## 语言分布"]
    for lang, c in by_lang:
        lines.append(f"- {lang}: {c}")
    lines += ["", "## 复杂度热点（complex）"]
    for nid, name, fp in hotspots:
        lines.append(f"- **{name}** `{fp}`")
    lines += ["", "## 高扇入节点（被多处依赖，改它影响广）"]
    for nid, c in high_fan:
        lines.append(f"- {nid}（{c} 入）")
    return "\n".join(lines)
