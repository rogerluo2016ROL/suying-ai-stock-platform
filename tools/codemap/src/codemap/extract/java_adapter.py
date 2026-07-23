"""Java tree-sitter adapter（04 §3.4 / §4.5）。

符号：class/interface/enum/record → class 节点；method/constructor → method（类内）。
import：import_declaration 的 scoped_identifier / wildcard（a.b.C / a.b.* / static a.b.C.m）。
"""

from __future__ import annotations

from tree_sitter import Language, Node, Parser
import tree_sitter_java as tsj

from codemap.extract.base import complexity_from_span
from codemap.graph.model import NodeRecord, RawImport

_JAVA = Language(tsj.language())


class JavaAdapter:
    language = _JAVA
    extensions = (".java",)

    def __init__(self) -> None:
        self._parser = Parser(_JAVA)

    def parse(self, source: bytes, file_path: str = "") -> Node:
        return self._parser.parse(source).root_node

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        out: list[NodeRecord] = []

        def visit(node: Node, cls: str | None) -> None:
            t = node.type
            if t in ("class_declaration", "interface_declaration",
                     "enum_declaration", "record_declaration"):
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
            if t in ("method_declaration", "constructor_declaration"):
                name = _field(node, "name")
                if name:
                    if cls:
                        out.append(NodeRecord(
                            id=f"method:{file_path}:{cls}.{name}", type="method",
                            name=f"{cls}.{name}", file_path=file_path,
                            start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        complexity=complexity_from_span(node.start_point[0] + 1, node.end_point[0] + 1),
                        ))
                    else:
                        out.append(NodeRecord(
                            id=f"function:{file_path}:{name}", type="function", name=name,
                            file_path=file_path,
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
            if node.type == "import_declaration":
                spec = _import_spec(node)
                if spec:
                    out.append(RawImport(module=spec, symbols=(), level=0, from_import=True))
            for c in node.children:
                visit(c)

        visit(root)
        return out


def _field(node: Node, name: str) -> str | None:
    c = node.child_by_field_name(name)
    return c.text.decode() if c is not None else None


def _import_spec(imp: Node) -> str | None:
    """import_declaration 的 scope：scoped_identifier（a.b.C）/ wildcard（a.b.*）。"""
    for child in imp.children:
        if child.type in ("scoped_identifier", "wildcard"):
            return child.text.decode()
    return None
