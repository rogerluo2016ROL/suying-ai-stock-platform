"""codemap build：scan → extract → resolve → store（多语言 registry，两阶段单事务）。

registry 按扩展名分发到 adapter（M2：Python/TS·JS/SQL/YAML/JSON/Java）+ 各自 resolver。
两阶段：① 全部 file record + file 节点（保 imports 边 dst 先存在）；② 符号 + 同文件边 +
跨文件 imports 边。
"""

from __future__ import annotations
import hashlib
import os
import subprocess
from pathlib import Path

from codemap.extract.java_adapter import JavaAdapter
from codemap.extract.json_adapter import JSONAdapter
from codemap.extract.python_adapter import PythonAdapter
from codemap.extract.sfc_adapter import SfcAdapter
from codemap.extract.sql_adapter import SQLAdapter
from codemap.extract.ts_adapter import TSAdapter
from codemap.extract.yaml_adapter import YAMLAdapter
from codemap.graph.model import EdgeRecord, FileRecord, NodeRecord
from codemap.graph.store import init_db, set_meta, transaction, upsert_edge, upsert_file, upsert_node
from codemap.resolve.import_resolver import resolve as resolve_py
from codemap.resolve.java import resolve as resolve_java
from codemap.resolve.ts import resolve as resolve_ts
from codemap.scan.walker import walk

# (adapter_class, language, resolver_or_None)
_ADAPTERS: list[tuple] = [
    (PythonAdapter, "python", resolve_py),
    (TSAdapter, "typescript", resolve_ts),
    (SfcAdapter, "vue", resolve_ts),   # .vue/.svelte SFC，<script> import 走 TS resolver
    (JavaAdapter, "java", resolve_java),
    (SQLAdapter, "sql", None),
    (YAMLAdapter, "yaml", None),
    (JSONAdapter, "json", None),
]

# 扩展名 → (adapter 实例, language, resolver)
_REGISTRY: dict[str, tuple] = {}
for _cls, _lang, _res in _ADAPTERS:
    _inst = _cls()
    for _ext in _inst.extensions:
        _REGISTRY[_ext] = (_inst, _lang, _res)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _categorize(rel_path: str) -> str:
    ext = Path(rel_path).suffix
    if ext in (".md", ".rst"):
        return "docs"
    if ext in (".yaml", ".yml", ".toml", ".env", ".json"):
        return "config"
    if ext == ".sql":
        return "data"
    return "code"


def _git_head(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _safe_edge(conn, rec: EdgeRecord, node_ids: set[str]) -> int:
    """upsert_edge 前校验 src/dst 节点已建（在 node_ids）；悬空则跳过返回 1。

    防 resolver 解析到无 adapter 的扩展名（如 .css / .vue，未在 _REGISTRY → Pass 1 不
    建节点）导致 FK 失败、回滚整个 Pass 2 事务。返回 dropped 计数（0 建成功 / 1 跳过）。
    """
    if rec.src in node_ids and rec.dst in node_ids:
        upsert_edge(conn, rec)
        return 0
    return 1


def extract_pass(db, payloads, node_ids: set[str], root: Path, py_roots, stats: dict) -> None:
    """Pass-2 / 增量子阶段-2 公共提取：逐 payload 抽符号 + 同文件 contains 边 + 跨文件
    imports 边（_safe_edge 校验，悬空跳过）。build（全量）与 incremental（增量）共用，
    保证「update == build」不变量（两处循环曾逐字重复、须同步维护）。

    前置：调用方已在 transaction 内、node_ids 已含全部 file 节点。stats 用 .get 兜底累加，
    兼容 build（含 symbols/imports/imports_resolved 键）与 incremental（仅 edges_dropped/
    files_failed）两种 stats 形状。
    """
    for rel, content, adapter, resolver, lang in payloads:
        try:
            ast_root = adapter.parse(content, file_path=rel)
            for sym in adapter.extract_symbols(ast_root, rel):
                upsert_node(db, sym)
                node_ids.add(sym.id)
                stats["edges_dropped"] = stats.get("edges_dropped", 0) + _safe_edge(
                    db, EdgeRecord(src=f"file:{rel}", dst=sym.id, type="contains", weight=1.0), node_ids)
                stats["symbols"] = stats.get("symbols", 0) + 1
            if hasattr(adapter, "extract_edges"):
                for e in adapter.extract_edges(ast_root, rel):
                    stats["edges_dropped"] = stats.get("edges_dropped", 0) + _safe_edge(db, e, node_ids)
            if resolver:
                for raw in adapter.extract_imports(ast_root, rel):
                    stats["imports"] = stats.get("imports", 0) + 1
                    edge = (resolver(raw, rel, root, source_roots=py_roots)
                            if lang == "python" else resolver(raw, rel, root))
                    if edge is not None:
                        stats["imports_resolved"] = stats.get("imports_resolved", 0) + 1
                        stats["edges_dropped"] = stats.get("edges_dropped", 0) + _safe_edge(db, edge, node_ids)
        except Exception:
            stats["files_failed"] = stats.get("files_failed", 0) + 1
            continue


def _source_roots(root: Path) -> list[Path]:
    """Python 包根候选：project_root + 一级子目录（应对 backend/ src/ src-layout）。

    真实项目 Python 包根常是子目录（OOTDLab 的 backend/），M1 原 resolver 只查
    project_root 导致 ``from app.x`` 几乎全丢（recall ≈ 3.6%）。绝对 import 在各候选下找。
    排除明显非源目录。
    """
    exclude = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
               ".agf", "dist", "build", ".eggs", "htmlcov", "coverage", ".mypy_cache"}
    roots = [root]
    for sub in sorted(os.listdir(root)):
        p = root / sub
        if p.is_dir() and sub not in exclude:
            roots.append(p)
    return roots


def build(project_root: str | Path, db_path: str | Path = ".agf/code-map.db") -> dict:
    """全量建图（多语言）。返回 stats {files, symbols, imports, imports_resolved, edges, by_lang}。"""
    root = Path(project_root).resolve()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = init_db(db_path)
    stats = {"files": 0, "symbols": 0, "imports": 0, "imports_resolved": 0,
             "edges": 0, "edges_dropped": 0, "files_failed": 0, "by_lang": {}}
    payloads: list[tuple] = []
    node_ids = set()  # 已建节点 id（file + 符号），upsert_edge 前校验 src/dst 防悬空 FK 失败
    py_roots = _source_roots(root)  # Python 包根候选（backend/ src/ ...），绝对 import 在各候选下找

    # Pass 1：file record + file 节点
    with transaction(db):
        for fpath in walk(root):
            entry = _REGISTRY.get(fpath.suffix)
            if entry is None:
                continue
            adapter, lang, resolver = entry
            rel = fpath.relative_to(root).as_posix()
            try:
                content = fpath.read_bytes()
            except OSError:
                # N-8：单文件不可读（权限 / 悬空 symlink / IO）不崩整个 build，与 Pass 2 一致的 per-file 韧性
                stats["files_failed"] += 1
                continue
            upsert_file(db, FileRecord(
                path=rel, language=lang, category=_categorize(rel),
                line_count=content.count(b"\n") + 1, content_hash=_sha256(content),
            ))
            nid = f"file:{rel}"
            upsert_node(db, NodeRecord(id=nid, type="file", name=Path(rel).name, file_path=rel))
            node_ids.add(nid)
            stats["files"] += 1
            stats["by_lang"][lang] = stats["by_lang"].get(lang, 0) + 1
            payloads.append((rel, content, adapter, resolver, lang))

    # Pass 2：符号 + 同文件边 + 跨文件 imports 边（extract_pass 共享，与 incremental 一致）
    with transaction(db):
        extract_pass(db, payloads, node_ids, root, py_roots, stats)
        set_meta(db, "git_commit", _git_head(root))

    # FTS5 索引重建（external-content 表，从 nodes 镜像 name+summary）
    try:
        db.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
    except Exception:
        pass
    stats["edges"] = db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return stats
