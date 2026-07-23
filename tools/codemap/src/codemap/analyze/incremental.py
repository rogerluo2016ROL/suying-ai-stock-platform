"""增量更新（05 §2）：git diff → 删旧重提 changed files + 其 reverse importers → 更新 meta.commit。

正确性要点（修 N-2/N-3/N-4/N-5 + W-1 + I3，使 update 图与 build 等价）：
- N-3：删被改文件的节点会经 ``edges`` 两个 FK 的 ON DELETE CASCADE 掉「未变 import 方 →
  被改文件」的 imports 边。必须把 reverse importer（import 了被改文件的文件）一并重提，
  其 extract 会重建该 imports 边。否则影响分析（反向 BFS WHERE dst=被改文件）漏报 importer。
- N-2：Python resolver 须传 source_roots（src-layout 绝对 import），与 build 一致。
- W-1：跨文件 imports 边走 _safe_edge 守卫（悬空 dst 跳过），与 build 一致——否则
  ``import './x.css'``（.css 无 adapter 无节点）触发 FK 失败回滚整个增量事务。
- N-4：增量后重建 FTS5（external-content 镜像 nodes），否则新符号搜不到。
- N-5：git rename（R 状态）展开成 删旧路径 + 提新路径，否则旧节点残留 + 入边 stale。
- I3：非 Git 项目（``_git_head() == ''``）原 ``last == head == ''`` 直接返回 unchanged，
  永不重扫。修法：head 为空时走基于文件 content_hash 的变更检测（对比 files 表），覆盖
  add/modify/delete 三态。

两阶段（与 build 同构）：① 重建 file record + file 节点（保 imports 边 dst 先存在）；
② 符号 + 同文件边 + 跨文件 imports 边（_safe_edge 校验）。
"""

from __future__ import annotations
import subprocess
from pathlib import Path

from codemap.builder import _REGISTRY, _categorize, _git_head, _sha256, _source_roots, extract_pass
from codemap.graph.model import FileRecord, NodeRecord
from codemap.graph.store import (
    delete_nodes_for_file, get_meta, init_db, set_meta, transaction, upsert_file, upsert_node,
)
from codemap.scan.walker import walk as walk_files


def update(project_root: str | Path, db_path: str | Path = ".agf/code-map.db") -> dict:
    root = Path(project_root).resolve()
    db = init_db(db_path)
    last = get_meta(db, "git_commit")
    head = _git_head(root)
    if last == head:
        if head:
            # Git 项目、commit 未变 → 真无变化
            return {"unchanged": True, "changed": 0, "deleted": 0}
        # I3：非 Git 项目（head 空且 last 空）→ 不能早 return，走 hash diff 全量对比
        changed = _non_git_diff(db, root)
        if not changed:
            return {"unchanged": True, "changed": 0, "deleted": 0}
    else:
        changed = _git_diff_name_status(last, head, root)

    to_delete: set[str] = set()    # 相对路径：删旧节点（删除 / 无 adapter / 不在磁盘）
    to_extract: set[str] = set()   # 相对路径：重提（changed/modified/added + rename 目标）
    skipped = 0
    for rel, status in changed:
        fpath = root / rel
        if status == "d" or not fpath.is_file():
            to_delete.add(rel)
            continue
        if _REGISTRY.get(fpath.suffix) is None:
            to_delete.add(rel)  # 扩展名不再适配 → 清旧节点（防 stale）
            skipped += 1
            continue
        to_extract.add(rel)

    # N-3：捕获「import 了任一受影响文件」的 reverse importer。删受影响节点会 CASCADE 掉
    # importer→受影响 的 imports 边；importer 不重提则该边永久丢失（影响分析漏报）。
    affected = to_delete | to_extract
    importers = _reverse_importers(db, affected)
    importer_extract: set[str] = set()
    for rel in importers - to_extract - to_delete:
        fpath = root / rel
        if not fpath.is_file() or _REGISTRY.get(fpath.suffix) is None:
            continue  # 无 adapter 的 importer 不重提（其旧 imports 边已随受影响节点 CASCADE 清）
        importer_extract.add(rel)

    re_extract = to_extract | importer_extract
    py_roots = _source_roots(root)
    stats = {"changed": len(to_extract), "deleted": len(to_delete),
             "importers_re_extracted": len(importer_extract),
             "skipped": skipped, "edges_dropped": 0, "files_failed": 0}

    with transaction(db):
        # 删所有受影响 + importer 的旧节点（edges 两个 FK 的 ON DELETE CASCADE 自动清边）
        for rel in re_extract | to_delete:
            delete_nodes_for_file(db, rel)
        # node_ids = 删除后仍存活的节点（未变文件的 file + 符号节点），_safe_edge 据此校验
        node_ids = {r[0] for r in db.execute("SELECT id FROM nodes").fetchall()}

        # 子阶段 1：file record + file 节点（保 imports 边 dst 先存在）
        payloads = []
        for rel in re_extract:
            adapter, lang, resolver = _REGISTRY[(root / rel).suffix]
            try:
                content = (root / rel).read_bytes()
            except OSError:
                stats["files_failed"] += 1
                continue  # N-8：单文件不可读不崩整增量
            upsert_file(db, FileRecord(
                path=rel, language=lang, category=_categorize(rel),
                line_count=content.count(b"\n") + 1, content_hash=_sha256(content),
            ))
            nid = f"file:{rel}"
            upsert_node(db, NodeRecord(id=nid, type="file", name=Path(rel).name, file_path=rel))
            node_ids.add(nid)
            payloads.append((rel, content, adapter, resolver, lang))

        # 子阶段 2：符号 + 同文件边 + 跨文件 imports 边（extract_pass 共享，与 build 一致）
        extract_pass(db, payloads, node_ids, root, py_roots, stats)
        set_meta(db, "git_commit", head)

    # N-4：FTS5 重建（external-content 表镜像新 nodes；不重建则新符号搜不到）
    try:
        db.execute("INSERT INTO nodes_fts(nodes_fts) VALUES('rebuild')")
    except Exception:
        pass
    return stats


def _reverse_importers(db, affected_files: set[str]) -> set[str]:
    """import 了 affected_files 任一节点的未变 import 方文件路径集（reverse 1-hop）。

    边方向：imports src=importer, dst=imported（impact.py §1.1）。删 affected 节点会
    CASCADE 掉 importer→affected 边，故这些 importer 须重提以重建该边。
    """
    if not affected_files:
        return set()
    ph = ",".join("?" * len(affected_files))
    rows = db.execute(
        f"""SELECT DISTINCT n2.file_path
            FROM edges e
            JOIN nodes n1 ON e.dst = n1.id
            JOIN nodes n2 ON e.src = n2.id
            WHERE e.type='imports' AND n1.file_path IN ({ph})""",
        list(affected_files),
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def _git_diff_name_status(last: str, head: str, root: Path) -> list[tuple[str, str]]:
    """git diff --name-status last..head → [(path, status_letter)]。

    rename（Rxx）/ copy（Cxx）展开：rename = 删旧路径 + 提新路径（N-5，防旧节点残留）；
    copy = 提新路径。其余取 status 首字母（m/a/d/...）。
    """
    if not last or not head:
        return []
    out = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-status", f"{last}..{head}"],
        capture_output=True, text=True, check=False,
    )
    result: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        code = parts[0][0].lower()
        if code == "r" and len(parts) >= 3:
            result.append((parts[1], "d"))   # 旧路径：删节点（CASCADE 清其入边 stale）
            result.append((parts[2], "m"))   # 新路径：重提（重建其被 import 的入边）
        elif code == "c" and len(parts) >= 3:
            result.append((parts[2], "a"))   # copy：新路径作 add
        else:
            result.append((parts[-1], code))
    return result


def _non_git_diff(db, root: Path) -> list[tuple[str, str]]:
    """I3：非 Git 项目变更检测 —— 对比 files 表 content_hash vs 当前磁盘扫描结果。

    三态覆盖：
    - 'd' 在 files 表但磁盘找不到（删除）
    - 'a' 磁盘有但 files 表无（新增）
    - 'm' 两边都有但 hash 不同（修改）

    仅扫有 adapter 的扩展名（与 build Pass 1 一致），避免把 .png / .lock 等也算进来。
    """
    known: dict[str, str] = {
        row[0]: row[1]
        for row in db.execute("SELECT path, content_hash FROM files").fetchall()
    }
    on_disk: dict[str, str] = {}
    for fpath in walk_files(root):
        if _REGISTRY.get(fpath.suffix) is None:
            continue  # 与 build 一致：无 adapter 的扩展名不参与建图
        rel = fpath.relative_to(root).as_posix()
        try:
            content = fpath.read_bytes()
        except OSError:
            continue  # 不可读跳过（与 build Pass 1 一致）
        on_disk[rel] = _sha256(content)
    result: list[tuple[str, str]] = []
    for rel in known:
        if rel not in on_disk:
            result.append((rel, "d"))
    for rel, h in on_disk.items():
        if rel not in known:
            result.append((rel, "a"))
        elif known[rel] != h:
            result.append((rel, "m"))
    return result
