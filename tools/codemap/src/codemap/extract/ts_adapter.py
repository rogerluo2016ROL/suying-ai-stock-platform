"""TS / JS / TSX tree-sitter adapter（04 §3.2 / §4.2）。

M2 Task1 简化：用 typescript grammar 覆盖 .ts/.tsx/.js（tsx JSX 边角留 gate 暴露后切 tsx
grammar 分发）。符号 function/class/method/interface；import 提取 source specifier。
"""

from __future__ import annotations

from tree_sitter import Language, Node, Parser
import tree_sitter_typescript as tsts

from codemap.extract.base import complexity_from_span
from codemap.graph.model import NodeRecord, RawImport

_TS = Language(tsts.language_typescript())
_TSX = Language(tsts.language_tsx())


class TSAdapter:
    language = _TS
    extensions = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")

    def __init__(self) -> None:
        self._ts_parser = Parser(_TS)
        self._tsx_parser = Parser(_TSX)  # Task4 registry 按 .tsx 分发时启用

    def parse(self, source: bytes, file_path: str = "") -> Node:
        parser = self._tsx_parser if file_path.endswith((".tsx", ".jsx")) else self._ts_parser
        return parser.parse(source).root_node

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        out: list[NodeRecord] = []

        def visit(node: Node, cls: str | None) -> None:
            t = node.type
            if t in ("class_declaration", "interface_declaration"):
                name = _field(node, "name")
                if name:
                    out.append(NodeRecord(
                        id=f"class:{file_path}:{name}", type="class", name=name,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        complexity=complexity_from_span(node.start_point[0] + 1, node.end_point[0] + 1),
                    ))
                    for c in node.children:
                        visit(c, name)
                    return
            if t == "function_declaration":
                name = _field(node, "name")
                if name:
                    out.append(NodeRecord(
                        id=f"function:{file_path}:{name}", type="function", name=name,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        complexity=complexity_from_span(node.start_point[0] + 1, node.end_point[0] + 1),
                    ))
            if t == "method_definition":
                name = _field(node, "name")
                if name:
                    idp = f"method:{file_path}:{cls}.{name}" if cls else f"function:{file_path}:{name}"
                    out.append(NodeRecord(
                        id=idp, type="method" if cls else "function",
                        name=f"{cls}.{name}" if cls else name, file_path=file_path,
                        start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        complexity=complexity_from_span(node.start_point[0] + 1, node.end_point[0] + 1),
                    ))
            for c in node.children:
                visit(c, cls)

        visit(root, None)
        return out

    def extract_imports(self, root: Node, file_path: str) -> list[RawImport]:
        out: list[RawImport] = []

        def visit(node: Node) -> None:
            if node.type == "import_statement":
                src = _import_source(node)
                if src:
                    out.append(RawImport(module=src, symbols=(), level=0, from_import=True))
            for c in node.children:
                visit(c)

        visit(root)
        return out


def _field(node: Node, name: str) -> str | None:
    c = node.child_by_field_name(name)
    return c.text.decode() if c is not None else None


def _import_source(stmt: Node) -> str | None:
    """import_statement 的 source：递归找首个 string 节点（'./y' / '@/mod' / 'react'）。"""
    stack = [stmt]
    while stack:
        n = stack.pop()
        if n.type == "string":
            return n.text.decode().strip("\"'")
        stack.extend(reversed(n.children))
    return None
