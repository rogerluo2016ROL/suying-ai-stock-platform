"""analyze.incremental 单测（05 §2）。"""

import os
import sqlite3
import subprocess

from codemap.analyze.incremental import update
from codemap.builder import build
from codemap.graph.store import get_meta, init_db

_GIT_ENV = {**os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(tmp_path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(tmp_path), check=True, env=_GIT_ENV)


def _git_init_commit(tmp_path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")


def _edge_count(db, src: str, dst: str, etype: str) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM edges WHERE src=? AND dst=? AND type=?",
        (src, dst, etype),
    ).fetchone()[0]


def _node_ids(db) -> set[str]:
    return {r[0] for r in db.execute("SELECT id FROM nodes").fetchall()}


def test_update_no_change(tmp_path):
    """git_commit 未变 → unchanged。"""
    (tmp_path / "a.py").write_text("x = 1\n")
    build(tmp_path, tmp_path / "t.db")
    db = init_db(tmp_path / "t.db")
    head = get_meta(db, "git_commit")
    # 再次 update（commit 未变）
    stats = update(tmp_path, tmp_path / "t.db")
    assert stats["unchanged"] is True


def test_update_picks_up_new_file(tmp_path):
    """新增 .py → update 后进图谱。"""
    (tmp_path / "a.py").write_text("x = 1\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    # 加新文件 + commit
    (tmp_path / "b.py").write_text("y = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "add b")
    stats = update(tmp_path, tmp_path / "t.db")
    assert stats["changed"] >= 1  # b.py 新增
    db = sqlite3.connect(str(tmp_path / "t.db"))
    assert "file:b.py" in _node_ids(db)


def test_update_preserves_importer_edge_into_changed_file(tmp_path):
    """N-3：改 b.py（被 a.py import）后 update，a.py→b.py 的 imports 边必须仍在。

    回归：删 b 的节点 CASCADE 掉 a→b 边，重提只造 b 的出边，a→b 永不复原 →
    影响分析（反向 BFS WHERE dst=b）漏报 a。修法：把 reverse importer（a）一并重提。
    """
    (tmp_path / "b.py").write_text("def f():\n    return 1\n")
    (tmp_path / "a.py").write_text("import b\nx = b.f()\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    assert _edge_count(db, "file:a.py", "file:b.py", "imports") == 1
    # 改 b.py（a.py 不动）
    (tmp_path / "b.py").write_text("def f():\n    return 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "edit b")
    update(tmp_path, tmp_path / "t.db")
    assert _edge_count(db, "file:a.py", "file:b.py", "imports") == 1, \
        "N-3: editing b.py dropped a.py→b.py import edge (importer a not re-walked)"


def test_update_keeps_absolute_import_edge_in_src_layout(tmp_path):
    """N-2 + N-3：src-layout（backend/ 包根）下，改被依赖文件后 update，绝对 import 边仍在。

    N-2 回归：update 原不传 source_roots → ``from app.mod import x`` 在增量路径解析失败，
    使增量图系统性劣于 build 图。
    """
    pkg = tmp_path / "backend" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text("VAL = 1\n")
    (pkg / "use.py").write_text("from app.mod import VAL\nprint(VAL)\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    use_rel, mod_rel = "backend/app/use.py", "backend/app/mod.py"
    assert _edge_count(db, f"file:{use_rel}", f"file:{mod_rel}", "imports") == 1
    # 改 mod.py（use.py 不动）
    (pkg / "mod.py").write_text("VAL = 2\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "edit mod")
    update(tmp_path, tmp_path / "t.db")
    assert _edge_count(db, f"file:{use_rel}", f"file:{mod_rel}", "imports") == 1, \
        "N-2/N-3: editing mod.py dropped use.py→mod.py absolute-import edge"


def test_update_handles_git_rename(tmp_path):
    """N-5：git mv old.py → new.py 后 update，旧 file:old.py 节点清除、file:new.py 建立。

    回归：rename（R 状态）原只走 extract 新路径，旧路径节点永不删 → 残留 + 入边 stale。
    """
    (tmp_path / "old.py").write_text("v = 1\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    assert "file:old.py" in _node_ids(db)
    _git(tmp_path, "mv", "old.py", "new.py")
    _git(tmp_path, "commit", "-q", "-m", "rename")
    update(tmp_path, tmp_path / "t.db")
    nodes = _node_ids(db)
    assert "file:old.py" not in nodes, "N-5: renamed-away old.py node should be deleted"
    assert "file:new.py" in nodes, "N-5: renamed-to new.py node should be created"


def test_update_rebuilds_fts5_for_new_symbols(tmp_path):
    """N-4：update 后新增符号能被 FTS5 MATCH（build 末尾 rebuild，update 原先不 rebuild）。

    FTS5 external-content 表镜像 nodes.name+summary；增量不 rebuild → 新符号搜不到
    （且 keyword.py 有 stale 命中即 early-return，连 LIKE fallback 都不走）。
    """
    (tmp_path / "a.py").write_text("x = 1\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    (tmp_path / "m.py").write_text("def uniquefn():\n    pass\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "add m")
    update(tmp_path, tmp_path / "t.db")
    hit = db.execute(
        "SELECT COUNT(*) FROM nodes_fts WHERE nodes_fts MATCH 'uniquefn'"
    ).fetchone()[0]
    assert hit >= 1, "N-4: new symbol not FTS-searchable after update (FTS5 not rebuilt)"


def test_update_does_not_crash_on_import_to_nonadapted_extension(tmp_path):
    """W-1：a.ts import './x.css'（.css 无 adapter 无节点）→ update 不应 IntegrityError 回滚。

    回归：update 原裸 upsert_edge → FK 失败 → 整增量事务 ROLLBACK → update 抛错、db 停旧 commit。
    修法：update 用 _safe_edge 守卫（与 build 一致），悬空边跳过计入 edges_dropped。
    """
    (tmp_path / "x.css").write_text(".a {}\n")
    (tmp_path / "a.ts").write_text("import './x.css'\nconsole.log(1)\n")
    _git_init_commit(tmp_path)
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    # 改 a.ts 触发重提（其 import './x.css' 解析出 dst=file:x.css，但 .css 无节点）
    (tmp_path / "a.ts").write_text("import './x.css'\nconsole.log(2)\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "edit a.ts")
    try:
        stats = update(tmp_path, tmp_path / "t.db")
    except sqlite3.IntegrityError as e:
        raise AssertionError(f"W-1: update raised IntegrityError on unresolved import: {e}")
    # update 正常完成（事务未回滚）：a.ts 节点仍在
    assert "file:a.ts" in _node_ids(db), "W-1: update rolled back the txn, a.ts node lost"


def test_update_non_git_project_picks_up_changed_files(tmp_path):
    """I3：非 Git 项目（无 .git）改文件后 update 必须重提，不返回 unchanged。

    回归：``last = get_meta('git_commit') = ''`` == ``head = _git_head('') = ''`` → 直接
    ``return {'unchanged': True}``，永不重扫（非 Git 项目增量更新静默失效）。
    修法：head 为空时走基于文件 mtime/hash 的变更检测，对比 files 表 content_hash。
    """
    # 非 Git 目录（不 git init）
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    assert "file:a.py" in _node_ids(db)
    # 改一个文件 + 加一个新文件
    (tmp_path / "a.py").write_text("x = 999\n")
    (tmp_path / "c.py").write_text("z = 3\n")
    stats = update(tmp_path, tmp_path / "t.db")
    # 不能是 unchanged（关键断言：非 Git 项目改了文件必须检测到）
    assert not stats.get("unchanged"), "I3: non-Git project update returned unchanged (changes never detected)"
    # S2：精确 pin modify + add 都被计 —— a.py 修改 + c.py 新增 = 2 changed。
    # 回归：若未来 modify 检测坏（只检 add），changed 会跌到 1 仍满足旧的 ``>= 1`` 断言。
    assert stats["changed"] == 2, f"I3/S2: non-Git diff must count modify(a.py)+add(c.py)=2 (stats={stats})"
    # c.py 新节点必须入库
    assert "file:c.py" in _node_ids(db), "I3: new file c.py not added by non-Git update"


def test_update_non_git_project_detects_deleted_files(tmp_path):
    """I3：非 Git 项目删文件后 update 必须清旧节点（hash diff 路径覆盖删除）。"""
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    assert "file:b.py" in _node_ids(db)
    # 删 b.py
    (tmp_path / "b.py").unlink()
    stats = update(tmp_path, tmp_path / "t.db")
    assert not stats.get("unchanged"), "I3: non-Git update unchanged after file delete"
    assert stats["deleted"] >= 1, f"I3: non-Git diff missed deletion (stats={stats})"
    assert "file:b.py" not in _node_ids(db), "I3: deleted b.py node still present after update"
