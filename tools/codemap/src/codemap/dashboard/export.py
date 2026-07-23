"""图导出（mermaid / graphviz dot）：生成文本图代码，外部渲染。

- mermaid：markdown 内嵌（```mermaid 块），GitHub/IDE 直接渲染，适合 docs/PR
- dot：graphviz 布局（大图层次清晰），dot -Tpng 渲染，适合文档/PPT 静态图

两者从 db 读节点/边 → 生成图代码文本（不像 dashboard HTML 自己渲染）。
"""

from __future__ import annotations
import sqlite3


def _load(db: sqlite3.Connection, only_files: bool, max_nodes: int):
    node_where = "WHERE type='file'" if only_files else ""
    rows = db.execute(
        f"SELECT id, name FROM nodes {node_where} LIMIT ?", (max_nodes,)
    ).fetchall()
    ids = [r[0] for r in rows]
    nodes = [(r[0], r[1]) for r in rows]
    edges = []
    if ids:
        ph = ",".join("?" * len(ids))
        edge_where = "AND type='imports'" if only_files else ""
        edges = db.execute(
            f"SELECT src, dst FROM edges WHERE src IN ({ph}) AND dst IN ({ph}) {edge_where}",
            (*ids, *ids),
        ).fetchall()
    return nodes, edges


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def mermaid(db: sqlite3.Connection, only_files: bool = False, max_nodes: int = 200) -> str:
    """生成 mermaid flowchart（```mermaid 代码块），GitHub/IDE 直接渲染。

    节点 id 安全化（n0/n1/...，避免 file:backend/x 含特殊字符），label 显示文件名。
    """
    nodes, edges = _load(db, only_files, max_nodes)
    id_map = {nid: f"n{i}" for i, (nid, _) in enumerate(nodes)}
    lines = ["```mermaid", "graph LR"]
    for nid, name in nodes:
        lines.append(f'  {id_map[nid]}["{_esc(name)}"]')
    for src, dst in edges:
        lines.append(f"  {id_map[src]} --> {id_map[dst]}")
    lines.append("```")
    return "\n".join(lines)


def dot(db: sqlite3.Connection, only_files: bool = False, max_nodes: int = 500) -> str:
    """生成 graphviz DOT（digraph），dot -Tpng/-Tsvg 渲染，大图层次布局强。

    节点 id 引号包裹（含特殊字符安全），label 显示文件名。
    """
    nodes, edges = _load(db, only_files, max_nodes)
    lines = ["digraph G {", "  rankdir=LR;", "  node [shape=box, fontname=Helvetica];"]
    for nid, name in nodes:
        lines.append(f'  "{_esc(nid)}" [label="{_esc(name)}"];')
    for src, dst in edges:
        lines.append(f'  "{_esc(src)}" -> "{_esc(dst)}";')
    lines.append("}")
    return "\n".join(lines)
