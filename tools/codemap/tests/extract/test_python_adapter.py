"""python_adapter 单测：符号 + import 提取（04 §3.1 / §4.1）。"""

from codemap.extract.python_adapter import PythonAdapter

SOURCE = b"""\
import os
import a.b.c
from a.b import c, d
from . import x
from ..y import z


def func1():
    pass


class Foo:
    def method1(self):
        pass

    async def method2(self):
        pass


def func2():
    pass
"""


def _adapter():
    return PythonAdapter()


# ---- 符号提取 ----

def test_extract_symbols_counts():
    root = _adapter().parse(SOURCE)
    syms = _adapter().extract_symbols(root, "src/m.py")
    types = [s.type for s in syms]
    assert types.count("function") == 2     # func1, func2
    assert types.count("class") == 1        # Foo
    assert types.count("method") == 2       # method1, method2


def test_extract_symbols_names_and_lines():
    root = _adapter().parse(SOURCE)
    syms = _adapter().extract_symbols(root, "src/m.py")
    by_name = {s.name: s for s in syms}
    assert "func1" in by_name
    assert "Foo" in by_name
    assert "Foo.method1" in by_name         # method 带类前缀
    assert by_name["func1"].start_line == 8 # `def func1` 在第 8 行（b"""\<newline> 续行去首换行）
    assert by_name["func1"].type == "function"


def test_extract_symbols_id_format():
    root = _adapter().parse(SOURCE)
    syms = _adapter().extract_symbols(root, "src/m.py")
    ids = {s.id for s in syms}
    assert "function:src/m.py:func1" in ids
    assert "class:src/m.py:Foo" in ids
    assert "method:src/m.py:Foo.method1" in ids


# ---- import 提取 ----

def test_extract_imports_counts():
    root = _adapter().parse(SOURCE)
    imps = _adapter().extract_imports(root, "src/m.py")
    assert len(imps) == 5


def test_extract_imports_absolute():
    root = _adapter().parse(SOURCE)
    imps = _adapter().extract_imports(root, "src/m.py")
    by_mod = {i.module: i for i in imps if i.module}
    assert by_mod["os"].from_import is False and by_mod["os"].level == 0
    assert by_mod["a.b.c"].from_import is False
    assert by_mod["a.b"].from_import is True
    assert set(by_mod["a.b"].symbols) == {"c", "d"}


def test_extract_imports_relative():
    root = _adapter().parse(SOURCE)
    imps = _adapter().extract_imports(root, "src/m.py")
    rel = [i for i in imps if i.level > 0]
    assert len(rel) == 2
    by_level = {i.level: i for i in rel}
    assert by_level[1].module is None and by_level[1].symbols == ("x",)   # from . import x
    assert by_level[2].module == "y" and by_level[2].symbols == ("z",)    # from ..y import z


def test_extract_imports_multi_module():
    """import a, b, c → 每个 module 一个 RawImport（原只取首个 return 致漏 b/c）。"""
    root = _adapter().parse(b"import os, sys\nimport a, b\n")
    imps = _adapter().extract_imports(root, "m.py")
    mods = {i.module for i in imps if i.module}
    assert {"os", "sys", "a", "b"} <= mods


def test_extract_symbols_sets_complexity_by_line_span():
    """N-7：adapter 必须给符号填 complexity（simple/moderate/complex）——原无 adapter 填此
    字段 → onboard/understand「复杂度热点/风险点」恒空、impact.risk_score 复杂度项恒 moderate
    （承诺功能静默失效）。行跨度启发式：≤10 simple / 11–30 moderate / >30 complex。"""
    adapter = PythonAdapter()
    body = b"\n".join(b"    x%d = %d" % (i, i) for i in range(40))   # 40 行函数体
    src = (
        b"def tiny():\n    return 1\n"                               # 2 行 → simple
        b"\n"
        b"def big():\n" + body + b"\n    return x0\n"                # 42 行 → complex
    )
    root = adapter.parse(src)
    syms = {s.name: s for s in adapter.extract_symbols(root, "m.py")}
    assert syms["tiny"].complexity is not None, "N-7: complexity must be populated (was always None)"
    assert syms["tiny"].complexity == "simple", "N-7: 2-line fn should be 'simple'"
    assert syms["big"].complexity == "complex", "N-7: 42-line fn should be 'complex'"


def test_extract_imports_module_with_import_substring():
    """I1：模块名含 'import' 子串时不应被 text.split('import') 截断。

    回归：``_module_part`` 用 ``text.split('import', 1)[0]`` 抽 module 片段，``from data_import
    import foo`` → module='data_'（截断，import 边丢失）；``from importlib import import_module``
    → module=None（完全丢失，resolver 漏解析）。修法：用 AST 子节点（dotted_name / relative_import）
    而非 stmt.text 文本切分。
    """
    adapter = PythonAdapter()
    src = (
        b"from data_import import foo\n"
        b"from importlib import import_module\n"
        b"from utils.csv_import import bar\n"
    )
    root = adapter.parse(src)
    imps = adapter.extract_imports(root, "m.py")
    by_mod = {i.module: i for i in imps if i.module}
    # module 名含 'import' 子串必须完整保留
    assert "data_import" in by_mod, "I1: 'data_import' truncated by text.split('import')"
    assert by_mod["data_import"].symbols == ("foo",)
    assert "importlib" in by_mod, "I1: 'importlib' dropped entirely (split at first 'import')"
    assert by_mod["importlib"].symbols == ("import_module",), "I1: symbol 'import_module' must keep"
    assert "utils.csv_import" in by_mod, "I1: dotted module with 'import' substring truncated"
    assert by_mod["utils.csv_import"].symbols == ("bar",)
