"""understand（07 §4.1）：理解地图（接管 agf-understand）。

按目录聚类 → 子系统；高扇入 → 核心依赖；复杂度 → 风险点。
M4 确定性版（entry + 目录聚类 + 扇入/复杂度），LLM 润色可选（设计 07 §5）。
"""

from __future__ import annotations
import sqlite3

from codemap.graph import queries


def understand(topic: str | None, db: sqlite3.Connection) -> str:
    topic = topic or "整个仓库"
    files = db.execute("SELECT path FROM files").fetchall()
    dirs: dict[str, list[str]] = {}
    for (p,) in files:
        d = "/".join(p.split("/")[:-1]) or "."
        dirs.setdefault(d, []).append(p)
    high_fan = queries.high_fan_in(db)
    complex_nodes = queries.complex_nodes(db)

    lines = [f"# 理解地图: {topic}", "", "## 子系统（按目录聚类）"]
    for d in sorted(dirs, key=lambda x: -len(dirs[x])):
        lines.append(f"- **{d}** — {len(dirs[d])} 文件")
    lines += ["", "## 核心依赖（高扇入，改它影响广）"]
    for nid, c in high_fan:
        lines.append(f"- {nid}（被 {c} 处依赖）")
    lines += ["", "## 风险点（complex 节点，接手小心）"]
    for nid, name, fp in complex_nodes:
        lines.append(f"- **{name}** `{fp}`")
    lines += ["", "_确定性生成（目录 + 扇入 + 复杂度）；未决问题留给人工评审_"]
    return "\n".join(lines)
