"""builder.build 集成测：scan→extract→resolve→store 全链路。"""

import sqlite3

from codemap.builder import build, _safe_edge
from codemap.graph.store import init_db
from codemap.graph.model import EdgeRecord, NodeRecord


def test_build_creates_file_and_symbol_nodes(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("def foo():\n    pass\n\nclass Bar:\n    pass\n")

    stats = build(tmp_path, tmp_path / "t.db")
    assert stats["files"] == 2          # __init__.py + mod.py
    assert stats["symbols"] == 2        # foo + Bar

    db = sqlite3.connect(str(tmp_path / "t.db"))
    node_ids = {r[0] for r in db.execute("SELECT id FROM nodes").fetchall()}
    assert "file:pkg/mod.py" in node_ids
    assert "function:pkg/mod.py:foo" in node_ids
    assert "class:pkg/mod.py:Bar" in node_ids


def test_build_creates_contains_edges(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("def foo():\n    pass\n")

    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    contains = db.execute(
        "SELECT src, dst FROM edges WHERE type='contains'"
    ).fetchall()
    assert ("file:pkg/mod.py", "function:pkg/mod.py:foo") in contains


def test_build_resolves_internal_imports(tmp_path):
    """mod.py `from pkg import other` → imports 边到 pkg/__init__.py（M1 建到 X）。"""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("from pkg import other\n")
    (tmp_path / "pkg" / "other.py").write_text("X = 1\n")

    stats = build(tmp_path, tmp_path / "t.db")
    assert stats["imports"] == 1
    assert stats["imports_resolved"] == 1   # pkg 在项目内 → 建边

    db = sqlite3.connect(str(tmp_path / "t.db"))
    imp = db.execute(
        "SELECT src, dst FROM edges WHERE type='imports'"
    ).fetchall()
    assert ("file:pkg/mod.py", "file:pkg/__init__.py") in imp


def test_build_skips_external_imports(tmp_path):
    """import os → external，不建 imports 边。"""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("import os\nimport sys\n")

    stats = build(tmp_path, tmp_path / "t.db")
    assert stats["imports"] == 2
    assert stats["imports_resolved"] == 0   # os/sys 都 external


def test_build_multi_language_registry(tmp_path):
    """registry 串起 6 语言（Python/TS/Java/SQL/YAML/JSON）—— M2 集成。"""
    (tmp_path / "app.py").write_text("import os\ndef foo():\n    pass\n")
    (tmp_path / "m.ts").write_text("import { x } from './util';\nfunction bar() {}\n")
    (tmp_path / "util.ts").write_text("export const x = 1;\n")
    jdir = tmp_path / "src" / "main" / "java" / "com" / "x"
    jdir.mkdir(parents=True)
    (jdir / "Foo.java").write_text("package com.x;\nclass Foo {}\n")
    (tmp_path / "schema.sql").write_text("CREATE TABLE users (id INT);\n")
    (tmp_path / "compose.yml").write_text("services:\n  web:\n    depends_on: [db]\n  db: {}\n")
    (tmp_path / "package.json").write_text('{"name":"app","dependencies":{"react":"^18"}}')

    stats = build(tmp_path, tmp_path / "t.db")
    by_lang = stats["by_lang"]
    assert by_lang.get("python") == 1
    assert by_lang.get("typescript") == 2          # m.ts + util.ts
    assert by_lang.get("java") == 1
    assert by_lang.get("sql") == 1
    assert by_lang.get("yaml") == 1
    assert by_lang.get("json") == 1

    db = sqlite3.connect(str(tmp_path / "t.db"))
    # TS imports 边（m.ts → util.ts）
    imp = db.execute("SELECT src, dst FROM edges WHERE type='imports'").fetchall()
    assert ("file:m.ts", "file:util.ts") in imp
    # SQL schema 节点
    nodes = {r[0] for r in db.execute("SELECT id FROM nodes").fetchall()}
    assert "schema:schema.sql:users" in nodes
    # YAML service 节点 + depends_on
    assert "service:compose.yml:web" in nodes
    deps = db.execute("SELECT src, dst FROM edges WHERE type='depends_on'").fetchall()
    assert ("service:compose.yml:web", "service:compose.yml:db") in deps


def test_safe_edge_skips_when_dst_missing():
    """dst 不在 node_ids → 跳过返回 1，不触发 upsert_edge（FK 不崩）。"""
    db = init_db(":memory:")
    dropped = _safe_edge(db, EdgeRecord(src="file:a.py", dst="file:ghost.py", type="imports"),
                         node_ids=set())
    assert dropped == 1
    assert db.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0


def test_safe_edge_inserts_when_nodes_present():
    db = init_db(":memory:")
    from codemap.graph.store import upsert_file, upsert_node
    from codemap.graph.model import FileRecord
    for nid, name in [("file:a.py", "a.py"), ("file:b.py", "b.py")]:
        upsert_file(db, FileRecord(path=name, language="python", category="code",
                                   line_count=1, content_hash="x"))
        upsert_node(db, NodeRecord(id=nid, type="file", name=name, file_path=name))
    dropped = _safe_edge(db, EdgeRecord(src="file:a.py", dst="file:b.py", type="imports"),
                         node_ids={"file:a.py", "file:b.py"})
    assert dropped == 0
    assert db.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 1


def test_build_drops_import_to_unsupported_ext(tmp_path):
    """TS import .css（无 adapter，Pass 1 不建节点）→ edge 悬空 → _safe_edge 跳过 +
    edges_dropped 计数；build 不崩，同文件 contains 边仍建。

    防 import 无 adapter 扩展名触发 FK 失败回滚整个 Pass 2 事务的回归。
    （原用 .vue 测，SfcAdapter 落地后 .vue 有节点不再悬空，改 .css）
    """
    (tmp_path / "main.ts").write_text("import './style.css';\nfunction boot() {}\n")
    (tmp_path / "style.css").write_text("body {}\n")  # .css 无 adapter
    stats = build(tmp_path, tmp_path / "t.db")
    assert stats["edges_dropped"] >= 1            # main.ts → style.css 悬空跳过
    db = sqlite3.connect(str(tmp_path / "t.db"))
    contains = db.execute("SELECT COUNT(*) FROM edges WHERE type='contains'").fetchone()[0]
    assert contains >= 1                          # main.ts → boot 符号边仍建


def test_build_resolves_src_layout_absolute_import(tmp_path):
    """src-layout：backend/app/mod.py `from app import util` 应解析到 backend/app/__init__.py。

    M1 原只查 project_root 致 ``from app.x`` 全丢（OOTDLab recall ≈ 3.6%）；
    _source_roots 探测 backend/ 包根后命中。防回归。
    """
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "__init__.py").write_text("")
    (tmp_path / "backend" / "app" / "mod.py").write_text("from app import util\n")
    (tmp_path / "backend" / "app" / "util.py").write_text("X = 1\n")
    stats = build(tmp_path, tmp_path / "t.db")
    assert stats["imports_resolved"] >= 1
    db = sqlite3.connect(str(tmp_path / "t.db"))
    imp = db.execute("SELECT src, dst FROM edges WHERE type='imports'").fetchall()
    assert ("file:backend/app/mod.py", "file:backend/app/__init__.py") in imp


def test_build_resolves_ts_alias_via_tsconfig(tmp_path):
    """TS @/ alias 通过 tsconfig paths 解析，相对 tsconfig 目录（非 project_root）。

    tsconfig 在 frontend/ 子目录时，原用 root 解析 @/ 全丢；修后用 tsconfig_dir。
    """
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "tsconfig.json").write_text(
        '{"compilerOptions":{"baseUrl":".","paths":{"@/*":["src/*"]}}}')
    (tmp_path / "frontend" / "src").mkdir()
    (tmp_path / "frontend" / "src" / "mod.ts").write_text("import {x} from '@/util';\n")
    (tmp_path / "frontend" / "src" / "util.ts").write_text("export const x=1;\n")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    imp = db.execute("SELECT src, dst FROM edges WHERE type='imports'").fetchall()
    assert ("file:frontend/src/mod.ts", "file:frontend/src/util.ts") in imp


def test_build_resolves_ts_alias_in_vite_split_tsconfig(tmp_path):
    """Vite 拆分：tsconfig.json base 无 paths，tsconfig.app.json 含 @/ paths。

    _find_tsconfig 优先含 paths 的；原只找 tsconfig.json（base）致 @/ 全漏（IdiomsOps）。
    """
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "tsconfig.json").write_text('{"files":[],"references":[]}')  # base 无 paths
    (tmp_path / "frontend" / "tsconfig.app.json").write_text(
        '{\n"compilerOptions":{\n/* alias comment — JSONC */\n"baseUrl":".",\n'
        '"paths":{"@/*":["./src/*"]}}}')  # JSONC（含注释），_find_tsconfig 需剥离
    (tmp_path / "frontend" / "src").mkdir()
    (tmp_path / "frontend" / "src" / "mod.ts").write_text("import {x} from '@/util';\n")
    (tmp_path / "frontend" / "src" / "util.ts").write_text("export const x=1;\n")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    imp = db.execute("SELECT src, dst FROM edges WHERE type='imports'").fetchall()
    assert ("file:frontend/src/mod.ts", "file:frontend/src/util.ts") in imp


def test_build_extracts_vue_script_imports(tmp_path):
    """Vue SFC：<script> 块的 import 经 SfcAdapter 提取（委托 TSAdapter）。

    .vue→.ts（相对）+ .vue→.vue（Comp.vue 现有节点，不再悬空）。
    """
    (tmp_path / "App.vue").write_text(
        '<template><div/></template>\n<script setup lang="ts">\n'
        "import { auth } from './stores/auth';\nimport Comp from './Comp.vue';\n"
        "</script>\n")
    (tmp_path / "stores").mkdir()
    (tmp_path / "stores" / "auth.ts").write_text("export const auth = {};\n")
    (tmp_path / "Comp.vue").write_text("<template/><script/>")
    build(tmp_path, tmp_path / "t.db")
    db = sqlite3.connect(str(tmp_path / "t.db"))
    imp = db.execute("SELECT src, dst FROM edges WHERE type='imports'").fetchall()
    assert ("file:App.vue", "file:stores/auth.ts") in imp    # 相对 import
    assert ("file:App.vue", "file:Comp.vue") in imp           # .vue → .vue


def test_build_skips_unreadable_file_instead_of_aborting(tmp_path):
    """N-8：build Pass 1 单文件不可读（悬空 symlink / 权限 / IO）不应崩整个 build——与 Pass 2
    一致的 per-file 韧性（Pass 2 已 try/except；Pass 1 原裸 read_bytes → 一文件 ROLLBACK 全 build）。"""
    (tmp_path / "good.py").write_text("x = 1\n")
    (tmp_path / "bad.py").symlink_to("does-not-exist")  # 悬空 symlink → read_bytes FileNotFoundError
    stats = build(tmp_path, tmp_path / "t.db")  # 当前代码：抛 FileNotFoundError → ROLLBACK → build 死
    assert stats["files_failed"] >= 1, "N-8: unreadable file should be counted in files_failed"
    db = sqlite3.connect(str(tmp_path / "t.db"))
    nodes = {r[0] for r in db.execute("SELECT id FROM nodes WHERE type='file'").fetchall()}
    assert "file:good.py" in nodes, "N-8: good.py should be indexed after skipping bad.py"
