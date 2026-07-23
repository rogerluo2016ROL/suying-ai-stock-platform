"""analyze.reachability 单测（ADR-024）：orphan 模块（零 imports 入边的代码文件）检测。

粒度 = 文件/模块（codemap 只建 file→file imports 边、无 call-graph → 函数级不可判）。
"""

from codemap.analyze.reachability import find_orphan_modules, orphans_report
from codemap.graph.model import EdgeRecord, FileRecord, NodeRecord
from codemap.graph.store import init_db, upsert_edge, upsert_file, upsert_node


def _file(db, path, category="code"):
    upsert_file(db, FileRecord(path=path, language="python", category=category, line_count=1, content_hash="h"))
    upsert_node(db, NodeRecord(id=f"file:{path}", type="file", name=path.rsplit("/", 1)[-1], file_path=path))


def _imports(db, importer, imported):
    upsert_edge(db, EdgeRecord(src=f"file:{importer}", dst=f"file:{imported}", type="imports"))


def test_orphan_module_detected(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "src/used.py"); _file(db, "src/orphan.py"); _file(db, "src/consumer.py")
    _imports(db, "src/consumer.py", "src/used.py")  # used 被 import；orphan 无人 import
    names = {o["file"] for o in find_orphan_modules(db)}
    assert "src/orphan.py" in names
    assert "src/used.py" not in names
    assert "src/consumer.py" in names  # consumer 自己也没人 import（除非它是 entrypoint）


def test_imported_module_not_orphan(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "src/a.py"); _file(db, "src/b.py")
    _imports(db, "src/a.py", "src/b.py")
    assert not any(o["file"] == "src/b.py" for o in find_orphan_modules(db))


def test_entrypoint_basename_excluded(tmp_path):
    db = init_db(tmp_path / "t.db")
    for p in ("src/main.py", "src/__init__.py", "frontend/App.tsx", "backend/app.py"):
        _file(db, p)
    assert find_orphan_modules(db) == []  # 全是 entrypoint basename


def test_test_files_excluded(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "tests/test_login.py"); _file(db, "src/auth_test.py"); _file(db, "e2e/flow.spec.ts")
    assert find_orphan_modules(db) == []


def test_non_code_files_skipped(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "config/app.yaml", category="config")
    _file(db, "README.md", category="docs")
    assert find_orphan_modules(db) == []  # 只审 category=code


def test_extra_entrypoints(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "src/plugin_auto.py")  # 框架自动发现，无 import 入边
    assert any(o["file"] == "src/plugin_auto.py" for o in find_orphan_modules(db))
    # 按 basename 豁免
    assert not any(o["file"] == "src/plugin_auto.py" for o in find_orphan_modules(db, extra_entrypoints=["plugin_auto.py"]))
    # 按相对路径豁免
    assert not any(o["file"] == "src/plugin_auto.py" for o in find_orphan_modules(db, extra_entrypoints=["src/plugin_auto.py"]))


def test_changed_scope(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "src/orphan_a.py"); _file(db, "src/orphan_b.py")
    names = {o["file"] for o in find_orphan_modules(db, changed_files=["src/orphan_b.py"])}
    assert names == {"src/orphan_b.py"}


def test_report_shape(tmp_path):
    db = init_db(tmp_path / "t.db")
    _file(db, "src/orphan.py")
    rep = orphans_report(db, changed_files=["src/orphan.py"])
    assert rep["count"] == 1 and rep["scope"] == "changed" and rep["granularity"] == "module"
    assert rep["orphans"][0]["file"] == "src/orphan.py"
