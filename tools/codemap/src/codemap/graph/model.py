"""图谱数据模型（dataclass）。

SSOT: docs/design/deeply-understand/03-data-model.md
跨 Task 类型契约（M1 plan Global Constraints）：
  Task 1 定义 → Task 2 产 RawImport → Task 3 消费 RawImport 产 EdgeRecord → Task 1 store 接 EdgeRecord
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class FileRecord:
    """files 表行：文件级元数据 + 双指纹。"""
    path: str                          # 仓库相对路径
    language: str                      # python / javascript / typescript / sql / yaml / json / java / markdown / unknown
    category: str                      # code / config / docs / infra / data / script / markup
    line_count: int
    content_hash: str                  # sha256(文件字节)
    structure_hash: str | None = None  # sha256(canonical(symbols+imports))，首建时为 None
    analyzed_at: str = ""              # ISO8601


@dataclass
class NodeRecord:
    """nodes 表行：图谱节点（文件级 + 符号级）。"""
    id: str                            # 类型前缀 + 定位，如 file:src/a.py / function:src/a.py:f
    type: str                          # file/function/class/method/module/config/document/schema/service
    name: str
    file_path: str
    signature: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    complexity: str | None = None      # simple/moderate/complex
    summary: str | None = None


@dataclass
class EdgeRecord:
    """edges 表行：图谱边（带类型 + 权重）。

    方向约定（05 §1.1）：src = importer（依赖方），dst = imported（被依赖方）。
    即 A imports B → EdgeRecord(src=A, dst=B, type='imports')。
    """
    src: str
    dst: str
    type: str                          # imports/calls/contains/inherits/depends_on/tested_by/configures
    weight: float = 0.5
    detail: str | None = None


@dataclass
class RawImport:
    """未解析的原始 import（adapter.extract_imports 产，resolver.resolve 消费）。

    Python 语义：
      import a.b.c            → RawImport(module='a.b.c', symbols=(), level=0, from_import=False)
      from a.b import c, d    → RawImport(module='a.b', symbols=('c','d'), level=0, from_import=True)
      from . import x         → RawImport(module=None, symbols=('x',), level=1, from_import=True)
      from ..y import z       → RawImport(module='y', symbols=('z',), level=2, from_import=True)
    """
    module: str | None
    symbols: tuple[str, ...] = ()
    level: int = 0                     # 0=绝对，>0=相对 import 点数
    from_import: bool = False
