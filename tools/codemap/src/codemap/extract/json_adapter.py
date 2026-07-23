"""JSON adapter（04 §4.4）：package.json 等——config 节点；dependencies external（不建项目内边）。

不用 tree-sitter（标准库 json 解析 dict 更准）。
"""

from __future__ import annotations
import json
import re
from typing import Any

from codemap.graph.model import EdgeRecord, NodeRecord, RawImport

_JSONC_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)


class JSONAdapter:
    extensions = (".json",)

    def parse(self, source: bytes, file_path: str = "") -> Any:
        # tsconfig 等 JSONC 含 /* */ 块注释 + // 行注释，标准 json.loads 不认 → 先剥离
        cleaned = _JSONC_COMMENT_RE.sub("", source.decode("utf-8", errors="ignore"))
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}  # 仍崩（trailing comma 等）→ 降级空，per-file try/except 兜底

    def extract_symbols(self, doc: Any, file_path: str) -> list[NodeRecord]:
        if isinstance(doc, dict) and ("name" in doc or "dependencies" in doc):
            # package.json / 类似清单
            return [NodeRecord(
                id=f"config:{file_path}", type="config",
                name=str(doc.get("name", file_path)), file_path=file_path,
            )]
        return []

    def extract_imports(self, doc: Any, file_path: str) -> list[RawImport]:
        return []  # dependencies 是 external（npm 包），不建项目内边

    def extract_edges(self, doc: Any, file_path: str) -> list[EdgeRecord]:
        return []  # package.json dependencies 全 external，无项目内边
