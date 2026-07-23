"""import_resolver 单测：04 §4.1 规则（绝对 / 相对 / external / package __init__）。"""

from codemap.graph.model import RawImport
from codemap.resolve.import_resolver import resolve


def _pkg(tmp_path):
    """fixture：pkg/__init__.py + pkg/mod.py + pkg/sub/__init__.py + pkg/sub/child.py。"""
    (tmp_path / "pkg" / "sub").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "mod.py").write_text("X = 1")
    (tmp_path / "pkg" / "sub" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "sub" / "child.py").write_text("Y = 2")


# ---- 绝对 import ----

def test_resolve_absolute_import_module(tmp_path):
    _pkg(tmp_path)
    raw = RawImport(module="pkg.mod", from_import=False)
    e = resolve(raw, "main.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/mod.py"
    assert e.src == "file:main.py"
    assert e.type == "imports"


def test_resolve_absolute_import_package(tmp_path):
    """import pkg → pkg/__init__.py。"""
    _pkg(tmp_path)
    raw = RawImport(module="pkg", from_import=False)
    e = resolve(raw, "main.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/__init__.py"


def test_resolve_from_import_to_package(tmp_path):
    """from pkg import mod → 建到 pkg（__init__.py），M1 不查 mod 子模块。"""
    _pkg(tmp_path)
    raw = RawImport(module="pkg", symbols=("mod",), from_import=True)
    e = resolve(raw, "main.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/__init__.py"


# ---- 相对 import ----

def test_resolve_relative_from_dot(tmp_path):
    """pkg/sub/child.py 里 `from . import X`（level=1）→ pkg/sub/__init__.py。"""
    _pkg(tmp_path)
    raw = RawImport(module=None, symbols=("X",), level=1, from_import=True)
    e = resolve(raw, "pkg/sub/child.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/sub/__init__.py"


def test_resolve_relative_from_dotdot(tmp_path):
    """pkg/sub/child.py 里 `from .. import mod`（level=2）→ pkg/__init__.py。"""
    _pkg(tmp_path)
    raw = RawImport(module=None, symbols=("mod",), level=2, from_import=True)
    e = resolve(raw, "pkg/sub/child.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/__init__.py"


def test_resolve_relative_with_module(tmp_path):
    """pkg/sub/child.py 里 `from ..pkg2 import z`（level=2 + module）→ pkg/pkg2/__init__.py。

    语义：child 在 pkg.sub，``..`` = pkg（sub 的父），``pkg2`` = pkg.pkg2。
    """
    _pkg(tmp_path)
    (tmp_path / "pkg" / "pkg2").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "pkg2" / "__init__.py").write_text("")
    raw = RawImport(module="pkg2", symbols=("z",), level=2, from_import=True)
    e = resolve(raw, "pkg/sub/child.py", tmp_path)
    assert e is not None
    assert e.dst == "file:pkg/pkg2/__init__.py"


# ---- external（不建边）----

def test_resolve_external_stdlib(tmp_path):
    """os / sys / pathlib 是标准库，不在 project_root → None。"""
    for mod in ("os", "sys", "pathlib", "json"):
        raw = RawImport(module=mod, from_import=False)
        assert resolve(raw, "main.py", tmp_path) is None


def test_resolve_external_third_party(tmp_path):
    """requests / numpy 等三方库不在 project_root → None。"""
    raw = RawImport(module="requests", from_import=False)
    assert resolve(raw, "main.py", tmp_path) is None


def test_resolve_from_external(tmp_path):
    """from os import path → os 不在 project → None。"""
    raw = RawImport(module="os", symbols=("path",), from_import=True)
    assert resolve(raw, "main.py", tmp_path) is None


def test_resolve_nonexistent_module(tmp_path):
    """项目内不存在的模块 → None。"""
    raw = RawImport(module="pkg.nonexistent", from_import=False)
    assert resolve(raw, "main.py", tmp_path) is None
