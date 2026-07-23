"""Java adapter + resolve/java 单测（04 §3.4 / §4.5）。"""

from codemap.extract.java_adapter import JavaAdapter
from codemap.graph.model import RawImport
from codemap.resolve.java import resolve

JAVA_SOURCE = b"""\
package com.x;

import com.x.other.Bar;
import java.util.List;
import org.springframework.context.ApplicationContext;

public class Foo {
    public void greet() {}
    private int compute(int x) { return x; }
}

interface Iface {}
enum Color { RED, BLUE }
"""


# ---- 符号提取 ----

def test_java_extract_symbols():
    a = JavaAdapter()
    root = a.parse(JAVA_SOURCE)
    syms = a.extract_symbols(root, "com/x/Foo.java")
    types = [s.type for s in syms]
    assert types.count("class") == 3       # Foo + interface Iface + enum Color
    assert types.count("method") == 2      # Foo.greet + Foo.compute
    names = {s.name for s in syms}
    assert {"Foo", "Iface", "Color"} <= names
    assert "Foo.greet" in names


# ---- import 提取 ----

def test_java_extract_imports():
    a = JavaAdapter()
    root = a.parse(JAVA_SOURCE)
    imps = a.extract_imports(root, "com/x/Foo.java")
    modules = {i.module for i in imps}
    assert "com.x.other.Bar" in modules
    assert "java.util.List" in modules
    assert "org.springframework.context.ApplicationContext" in modules


# ---- resolve：source root + external ----

def _maven(tmp_path):
    """fixture：Maven 单模块 src/main/java/com/x/{Foo,other/Bar}.java。"""
    base = tmp_path / "src" / "main" / "java" / "com" / "x"
    base.mkdir(parents=True)
    (base / "Foo.java").write_text("package com.x;")
    (base / "other").mkdir()
    (base / "other" / "Bar.java").write_text("package com.x.other;")


def test_java_resolve_internal_class(tmp_path):
    _maven(tmp_path)
    e = resolve(RawImport(module="com.x.other.Bar", from_import=True),
                "src/main/java/com/x/Foo.java", tmp_path)
    assert e is not None
    assert e.dst == "file:src/main/java/com/x/other/Bar.java"


def test_java_resolve_jdk_external(tmp_path):
    _maven(tmp_path)
    for mod in ("java.util.List", "java.lang.String", "javax.servlet.http.HttpServlet", "jakarta.persistence.Entity"):
        assert resolve(RawImport(module=mod, from_import=True),
                       "src/main/java/com/x/Foo.java", tmp_path) is None


def test_java_resolve_third_party_external(tmp_path):
    _maven(tmp_path)
    for mod in ("org.springframework.context.ApplicationContext",
                "com.google.common.collect.Lists"):
        assert resolve(RawImport(module=mod, from_import=True),
                       "src/main/java/com/x/Foo.java", tmp_path) is None


def test_java_resolve_wildcard_no_edge(tmp_path):
    _maven(tmp_path)
    assert resolve(RawImport(module="com.x.*", from_import=True),
                   "src/main/java/com/x/Foo.java", tmp_path) is None


def test_java_resolve_multi_module(tmp_path):
    """多模块：root/api/.../Foo.java import root/shared/.../Util.java。"""
    for mod in ("api", "shared"):
        base = tmp_path / mod / "src" / "main" / "java" / "com" / "x"
        base.mkdir(parents=True)
        (base / ("Foo.java" if mod == "api" else "Util.java")).write_text(f"package com.x;")
    e = resolve(RawImport(module="com.x.Util", from_import=True),
                "api/src/main/java/com/x/Foo.java", tmp_path)
    assert e is not None
    assert e.dst == "file:shared/src/main/java/com/x/Util.java"
