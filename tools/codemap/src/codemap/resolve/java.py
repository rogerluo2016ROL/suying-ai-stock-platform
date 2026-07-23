"""Java import 路径解析（04 §4.5）：source root 探测 + 包→路径 + JDK/jar external。

source root：Maven ``src/main/java`` + ``src/test/java`` / Gradle sourceSets（默认同 Maven）
/ 多模块（每子目录各自的 src/main/java）/ 通用 fallback。
``import a.b.C`` → ``<source_root>/a/b/C.java``；``.*`` 通配 → None（不建边）；
JDK（java.* / javax.*）+ 三方 jar → None（external）。
"""

from __future__ import annotations
from pathlib import Path

from codemap.graph.model import EdgeRecord, RawImport

JAVA_SRC_ROOTS = ("src/main/java", "src/test/java", "src/main/kotlin")
JDK_PREFIXES = ("java.", "javax.", "jakarta.", "sun.", "com.sun.")


def resolve(raw: RawImport, current_file: str, project_root: str | Path) -> EdgeRecord | None:
    spec = raw.module
    if not spec or spec.endswith(".*"):
        return None  # 通配不建单文件边（M2 简化）
    root = Path(project_root).resolve()
    cls_rel = spec.replace(".", "/") + ".java"
    for sr in _find_source_roots(root):
        target = sr / cls_rel
        if target.is_file():
            try:
                rel = target.resolve().relative_to(root)
            except ValueError:
                return None
            return EdgeRecord(
                src=f"file:{current_file}", dst=f"file:{rel.as_posix()}",
                type="imports", weight=0.7, detail=f"import {spec}",
            )
    return None  # JDK / 三方 jar / 找不到 → external


def _find_source_roots(root: Path) -> list[Path]:
    """探测 Maven/Gradle source root：根级 + 多模块子目录级。"""
    roots: list[Path] = []
    for sr in JAVA_SRC_ROOTS:
        d = root / sr
        if d.is_dir():
            roots.append(d)
    # 多模块：root/<module>/src/main/java（简化扫一层子目录）
    if root.is_dir():
        for sub in root.iterdir():
            if not sub.is_dir() or sub.name.startswith("."):
                continue
            for sr in JAVA_SRC_ROOTS:
                d = sub / sr
                if d.is_dir():
                    roots.append(d)
    return roots
