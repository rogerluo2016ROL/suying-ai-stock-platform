"""consume 单测（07）：context/explain/onboard/understand。"""

from codemap.builder import build
from codemap.consume.context_builder import build_context
from codemap.consume.explain import explain
from codemap.consume.onboard import onboard
from codemap.consume.understand import understand


def _project(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("")
    (tmp_path / "app" / "mod.py").write_text("def foo():\n    'doc'\n    pass\n")
    (tmp_path / "app" / "util.py").write_text("from app import mod\n\ndef bar():\n    pass\n")
    build(tmp_path, tmp_path / "t.db")
    import sqlite3
    return sqlite3.connect(str(tmp_path / "t.db"))


def test_build_context(tmp_path):
    db = _project(tmp_path)
    out = build_context("foo", db)
    assert "Context: foo" in out


def test_explain(tmp_path):
    db = _project(tmp_path)
    out = explain("foo", db, tmp_path)
    assert "foo" in out
    assert "邻居" in out


def test_onboard(tmp_path):
    db = _project(tmp_path)
    out = onboard(db)
    assert "Onboard" in out
    assert "语言分布" in out


def test_understand(tmp_path):
    db = _project(tmp_path)
    out = understand(None, db)
    assert "理解地图" in out
    assert "子系统" in out
