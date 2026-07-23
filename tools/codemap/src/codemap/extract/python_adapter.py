"""Python tree-sitter adapter：符号 + import 提取（04 §3.1 / §4.1）。

实现用 AST 遍历（避 Query API 版本差异），queries/python.scm 是声明式参考。
"""

from __future__ import annotations
import re

from tree_sitter import Language, Node, Parser
import tree_sitter_python as tspython

from codemap.extract.base import complexity_from_span
from codemap.graph.model import NodeRecord, RawImport


class PythonAdapter:
    language = Language(tspython.language())
    extensions = (".py",)

    def __init__(self) -> None:
        self._parser = Parser(self.language)

    def parse(self, source: bytes, file_path: str = "") -> Node:
        return self._parser.parse(source).root_node

    # ---- 符号提取（04 §3.1）----

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        out: list[NodeRecord] = []
        cls_stack: list[str] = []

        def visit(node: Node) -> None:
            t = node.type
            if t == "class_definition":
                name = _field(node, "name")
                if name:
                    out.append(NodeRecord(
                        id=f"class:{file_path}:{name}", type="class", name=name,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                        complexity=complexity_from_span(node.start_point[0] + 1, node.end_point[0] + 1),
                    ))
                    cls_stack.append(name)
                for c in node.children:
                    visit(c)
                if name:
                    cls_stack.pop()
                return
            if t == "function_definition":
                name = _field(node, "name")
                if name:
                    if cls_stack:
                        cls = cls_stack[-1]
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
                    visit(c)
                return
            for c in node.children:
                visit(c)

        visit(root)
        return out

    # ---- import 提取（04 §4.1）----

    def extract_imports(self, root: Node, file_path: str) -> list[RawImport]:
        out: list[RawImport] = []

        def visit(node: Node) -> None:
            if node.type == "import_statement":
                out.extend(_parse_import(node))
            elif node.type == "import_from_statement":
                out.append(_parse_from_import(node))
            for c in node.children:
                visit(c)

        visit(root)
        return out


# ---- 辅助 ----

def _field(node: Node, name: str) -> str | None:
    """取命名子节点文本（如 function_definition 的 name）。"""
    child = node.child_by_field_name(name)
    return child.text.decode() if child is not None else None


def _dotted(node: Node) -> str | None:
    """合并 dotted_name 子树为 'a.b.c'。"""
    if node.type != "dotted_name":
        return None
    return ".".join(c.text.decode() for c in node.children if c.type == "identifier")


def _parse_import(stmt: Node) -> list[RawImport]:
    """import a.b.c [as d] / import a, b —— 每个 dotted_name 一个 RawImport。

    多模块 import（``import a, b, c``）原只取首个 return 致漏 b/c（recall 漏）；现全取。
    """
    mods: list[str] = []
    for child in stmt.children:
        if child.type == "dotted_name":
            mods.append(_dotted(child))
        elif child.type == "aliased_import":
            for c in child.children:
                if c.type == "dotted_name":
                    mods.append(_dotted(c))
                    break
    return [RawImport(module=m, symbols=(), level=0, from_import=False) for m in mods]


_LEADING_DOTS = re.compile(r"^\s*(\.+)")


def _parse_from_import(stmt: Node) -> RawImport:
    """from a.b import c, d / from . import x / from ..y import z。

    module + level 从 AST 子节点抽（在 ``from`` 与 ``import`` 关键字之间）：
    - ``dotted_name`` → 绝对 module（``a.b.c``）
    - ``relative_import`` → leading dots 计 level + 去点后余下作 module（``..y`` → level=2, module='y'）

    symbols 从 AST（import 关键字后的 dotted_name / identifier / aliased_import 内部名）。

    I1 修法：原用 ``stmt.text.decode()`` 的 ``text.split('import', 1)[0]`` 抽 module 片段，
    模块名含 'import' 子串（``data_import`` / ``importlib``）会被截断或完全丢失。
    改用 AST 子节点遍历，grammar 节点自带边界，不依赖文本子串切分。
    """
    module: str | None = None
    level = 0
    symbols: list[str] = []
    seen_import_kw = False
    for child in stmt.children:
        ct = child.type
        if ct == "from":
            continue
        if ct == "import":                 # keyword 分界（anonymous token）
            seen_import_kw = True
            continue
        if not seen_import_kw:
            # module 片段（from 后、import 前）
            if ct == "dotted_name":
                module = _dotted(child)
            elif ct == "relative_import":
                text = child.text.decode()
                m = _LEADING_DOTS.match(text)
                if m:
                    level = len(m.group(1))
                    rest = text[m.end():].strip()
                    module = rest or None
            continue
        # symbols 片段（import 关键字后）
        if ct == "dotted_name":
            symbols.append(_dotted(child))
        elif ct == "identifier":
            symbols.append(child.text.decode())
        elif ct == "aliased_import":       # `c as d` → 取 c
            for c in child.children:
                if c.type == "dotted_name":
                    symbols.append(_dotted(c))
                    break
                if c.type == "identifier":
                    symbols.append(c.text.decode())
                    break
    return RawImport(module=module, symbols=tuple(symbols), level=level, from_import=True)
