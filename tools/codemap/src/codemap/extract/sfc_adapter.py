"""SFC 框架 adapter（Vue .vue / Svelte .svelte）：取 <script> 块 → 委托 TSAdapter。

SFC 文件的 import 在 <script> 块里，是标准 ES import，复用 TSAdapter 提取；
不为每框架写完整 adapter（template 组件引用 <Comp> 不做 —— 可选增强，非 import
依赖图必需，04 §6）。.astro 的 frontmatter（---）语法不同，暂不支持。
"""

from __future__ import annotations
import re
from tree_sitter import Node

from codemap.extract.ts_adapter import TSAdapter
from codemap.graph.model import NodeRecord, RawImport

# <script setup lang="ts"> ... </script>（支持多块，非贪婪，IGNORECASE 防 <SCRIPT>）
_SCRIPT_RE = re.compile(rb"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)


def _extract_script(content: bytes) -> bytes:
    """提取所有 <script> 块内容并拼接（Vue 可有 <script> + <script setup> 两块）。"""
    parts = _SCRIPT_RE.findall(content)
    return b"\n".join(parts) if parts else b""


class SfcAdapter:
    """Vue/Svelte SFC：parse 取 script → 委托 TSAdapter；符号/import 提取全复用 TS。"""

    extensions = (".vue", ".svelte")
    # language 占位（Protocol 声明 Language 类型，但 builder 用 _ADAPTERS 的 _lang；
    # SFC 无单一 tree-sitter grammar，取 script 后走 TS grammar）
    language = TSAdapter.language

    def __init__(self) -> None:
        self._ts = TSAdapter()

    def parse(self, source: bytes, file_path: str = "") -> Node:
        return self._ts.parse(_extract_script(source), file_path=file_path)

    def extract_symbols(self, root: Node, file_path: str) -> list[NodeRecord]:
        return self._ts.extract_symbols(root, file_path)

    def extract_imports(self, root: Node, file_path: str) -> list[RawImport]:
        return self._ts.extract_imports(root, file_path)
