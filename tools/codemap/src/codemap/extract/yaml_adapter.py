"""YAML adapter（04 §4.4）：docker-compose / k8s——services → service 节点 + depends_on → depends_on 边。

不用 tree-sitter（PyYAML 解析 dict 更准）。M2 Task2：docker-compose depends_on；
k8s / 其他 YAML 后续按需扩。
"""

from __future__ import annotations
from typing import Any

import yaml

from codemap.graph.model import EdgeRecord, NodeRecord, RawImport


class _LooseLoader(yaml.SafeLoader):
    """忽略未知 tag（docker-compose 的 !override / !reset 等自定义 tag）—— 降级 None 不崩。

    这些 tag 的值对 codemap 无意义（只关心 services + depends_on），降级安全。
    防 PyYAML safe_load 遇 !override 崩 → build Pass 2 整事务回滚。
    """

_LooseLoader.add_multi_constructor("!", lambda loader, suffix, node: None)
_LooseLoader.add_multi_constructor("tag:yaml.org,2002:", lambda loader, suffix, node: None)


class YAMLAdapter:
    extensions = (".yaml", ".yml")

    def parse(self, source: bytes, file_path: str = "") -> dict:
        return yaml.load(source, Loader=_LooseLoader) or {}

    def extract_symbols(self, doc: Any, file_path: str) -> list[NodeRecord]:
        out: list[NodeRecord] = []
        services = (doc.get("services") or {}) if isinstance(doc, dict) else {}
        for svc in services:
            out.append(NodeRecord(
                id=f"service:{file_path}:{svc}", type="service", name=svc, file_path=file_path,
            ))
        return out

    def extract_imports(self, doc: Any, file_path: str) -> list[RawImport]:
        return []  # YAML 不用 import 语义；depends_on 边走 extract_edges

    def extract_edges(self, doc: Any, file_path: str) -> list[EdgeRecord]:
        """docker-compose depends_on → service 间 depends_on 边（同文件内）。"""
        out: list[EdgeRecord] = []
        services = (doc.get("services") or {}) if isinstance(doc, dict) else {}
        for svc, cfg in services.items():
            deps = (cfg or {}).get("depends_on") or []
            if isinstance(deps, dict):  # long form: {db: {condition: ...}}
                deps = list(deps.keys())
            for dep in deps:
                out.append(EdgeRecord(
                    src=f"service:{file_path}:{svc}",
                    dst=f"service:{file_path}:{dep}",
                    type="depends_on", weight=0.6,
                    detail="depends_on",
                ))
        return out
