"""Python import 路径解析（04 §4.1）。

消费 RawImport（adapter 产），解析成项目内 EdgeRecord 或 None（external）。
external = 标准库 / site-packages / 不可解析 → 不建边。

绝对 import（``from app.x import y``）在 **source_roots 候选**下找 —— project_root
+ 一级子目录（应对 ``backend/`` / ``src/`` 等 src-layout 包根；M1 原只查 project_root，
真实项目 ``from app.x`` 几乎全丢，recall ≈ 3.6%）。相对 import（``from . import y``）
基于 current_file 包，不受 source_roots 影响。
"""

from __future__ import annotations
from pathlib import Path

from codemap.graph.model import EdgeRecord, RawImport


def resolve(raw: RawImport, current_file: str, project_root: str | Path,
            source_roots: list | None = None) -> EdgeRecord | None:
    """解析 Python import → 项目内 EdgeRecord（imports 边）或 None（external）。

    current_file 与返回 EdgeRecord.dst 里的路径都是相对 project_root 的 POSIX 相对路径。
    source_roots：绝对 import 的包根候选（默认 [project_root]）；build 探测后传
    [project_root, project_root/backend, ...] 应对 src-layout。
    """
    root = Path(project_root).resolve()
    roots = [Path(r).resolve() for r in (source_roots or [root])]
    target_rel = _resolve_to_relpath(raw, current_file, root, roots)
    if target_rel is None:
        return None  # external
    return EdgeRecord(
        src=f"file:{current_file}",
        dst=f"file:{target_rel}",
        type="imports",
        weight=0.7,
        detail=_detail(raw),
    )


def _resolve_to_relpath(raw: RawImport, current_file: str, root: Path,
                        source_roots: list) -> str | None:
    """返回目标文件相对 project_root 的 POSIX 路径，或 None（external / 找不到）。"""
    # 相对 import：基于 current_file 包（不受 source_roots 影响）
    if raw.level > 0:
        base = (root / current_file).parent
        for _ in range(raw.level - 1):
            base = base.parent
        mp = (base / raw.module.replace(".", "/")) if raw.module else base
        return _first_match(mp, root)
    if not raw.module:
        return None  # 绝对 import 无 module 不可解析
    # 绝对 import：在 source_roots 候选下找（应对 backend/ src/ 包根）
    for sr in source_roots:
        mp = sr / raw.module.replace(".", "/")
        rel = _first_match(mp, root)
        if rel is not None:
            return rel
    return None  # 所有候选都无物理文件 = external


def _first_match(module_path: Path, root: Path) -> str | None:
    """module_path 候选文件，返回相对 root 的 POSIX 路径；不在 root 内 = None。"""
    for cand in _candidates(module_path):
        if cand.is_file():
            try:
                return cand.resolve().relative_to(root).as_posix()
            except ValueError:
                return None  # 解析到 project_root 外 = external
    return None


def _candidates(module_path: Path) -> list[Path]:
    """物理文件候选：mod.py / mod/__init__.py。"""
    if module_path.suffix == ".py":
        return [module_path]
    return [module_path.with_suffix(".py"), module_path / "__init__.py"]


def _detail(raw: RawImport) -> str:
    if raw.from_import:
        return f"from {'.' * raw.level}{raw.module or ''} import {', '.join(raw.symbols)}"
    return f"import {raw.module}"
