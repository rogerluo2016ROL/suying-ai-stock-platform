"""LanguageAdapter 抽象（扩展点，04 §2）。

每语言实现一个 adapter；新增语言 = 加 adapter + 注册，核心代码不动。
"""

from __future__ import annotations
from typing import Protocol, runtime_checkable

from tree_sitter import Language, Node

from codemap.graph.model import NodeRecord, RawImport


@runtime_checkable
class LanguageAdapter(Protocol):
    """语言适配器接口：tree-sitter 解析 + 符号/import 提取。

    resolve_import 不在 base（逐语言 resolver 单独实现，见 resolve/，因路径解析规则差异大）。
    """

    language: Language
    extensions: tuple[str, ...]

    def parse(self, source: bytes, file_path: str = "") -> Node:
        """解析源码字节为 AST root。

        file_path 用于按扩展名分发 grammar（TSX vs TS）；其他 adapter 可忽略但签名一致，
        让 builder/incremental 统一 ``parse(content, file_path=rel)`` 调用（I2 修法）。
        """
        ...

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        """从 AST 抽 file/function/class/method 节点（确定性）。"""
        ...

    def extract_imports(self, root: Node, file_path: str) -> list[RawImport]:
        """从 AST 抽 import 语句（未解析的原始形式，resolver 消费）。"""
        ...


def complexity_from_span(start_line: int | None, end_line: int | None) -> str | None:
    """符号复杂度 v1 启发式（行跨度）：≤10 simple / 11–30 moderate / >30 complex / 无跨度 None。

    确定性 + 跨语言（Python/TS/Java 符号均有 start_line/end_line）。N-7：原无 adapter 填
    ``NodeRecord.complexity`` → onboard/understand「复杂度热点/风险点」恒空、impact.risk_score
    复杂度项恒 moderate（承诺功能静默失效）。后续可升级 McCabe 圈复杂度（计 if/for/while/try
    等分支节点）；行跨度作 v1 已足以解除「恒空」并给风险评分一个真实信号。
    """
    if not start_line or not end_line or end_line < start_line:
        return None
    span = end_line - start_line + 1
    if span <= 10:
        return "simple"
    if span <= 30:
        return "moderate"
    return "complex"
