"""SQL adapter（04 §3.3 / §4.3）：CREATE TABLE → schema 节点 + FK REFERENCES → depends_on 边。

M2 Task2：纯 .sql。tree-sitter-sql 0.3 节点名：``create_table`` + ``keyword_references``
（后跟目标表 identifier）；Alembic `.py` 后处理留。
"""

from __future__ import annotations

from tree_sitter import Language, Node, Parser
import tree_sitter_sql as tssql

from codemap.graph.model import EdgeRecord, NodeRecord, RawImport


class SQLAdapter:
    language = Language(tssql.language())
    extensions = (".sql",)

    def __init__(self) -> None:
        self._parser = Parser(self.language)

    def parse(self, source: bytes, file_path: str = "") -> Node:
        return self._parser.parse(source).root_node

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        out: list[NodeRecord] = []

        def visit(n: Node) -> None:
            if n.type == "create_table":
                name = _first_identifier(n)
                if name:
                    out.append(NodeRecord(
                        id=f"schema:{file_path}:{name}", type="schema", name=name,
                        file_path=file_path,
                        start_line=n.start_point[0] + 1, end_line=n.end_point[0] + 1,
                    ))
            for c in n.children:
                visit(c)

        visit(root)
        return out

    def extract_imports(self, root: Node, file_path: str) -> list[RawImport]:
        return []  # SQL 不用 import 语义；FK 边走 extract_edges

    def extract_edges(self, root: Node, file_path: str) -> list[EdgeRecord]:
        """FOREIGN KEY ... REFERENCES bar → schema:foo depends_on schema:bar（同文件内）。

        tree-sitter-sql：``REFERENCES`` 是 ``keyword_references``，目标表是其后兄弟 identifier。
        """
        out: list[EdgeRecord] = []

        def visit(n: Node, current_table: str | None) -> None:
            if n.type == "create_table":
                tbl = _first_identifier(n) or current_table
                for c in n.children:
                    visit(c, tbl)
                return
            if n.type == "keyword_references":
                tgt = _next_sibling_identifier(n)
                if tgt and current_table:
                    out.append(EdgeRecord(
                        src=f"schema:{file_path}:{current_table}",
                        dst=f"schema:{file_path}:{tgt}",
                        type="depends_on", weight=0.6,
                        detail="foreign_key",
                    ))
            for c in n.children:
                visit(c, current_table)

        visit(root, None)
        return out


def _clean(text: str) -> str:
    return text.strip("\"`[]")


def _first_identifier(node: Node) -> str | None:
    """node 子树 depth-first 首个 identifier（create_table 里是表名，先于列定义里的列名）。"""
    if node.type == "identifier":
        return _clean(node.text.decode())
    for c in node.children:
        r = _first_identifier(c)
        if r:
            return r
    return None


def _next_sibling_identifier(node: Node) -> str | None:
    """node 之后兄弟子树的首个 identifier（keyword_references 后的目标表）。"""
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.children
    try:
        idx = siblings.index(node)
    except ValueError:
        return None
    for s in siblings[idx + 1:]:
        r = _first_identifier(s)
        if r:
            return r
    return None
