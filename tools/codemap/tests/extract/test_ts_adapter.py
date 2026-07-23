"""TS adapter + resolve/ts 单测（04 §3.2 / §4.2）。"""

from codemap.extract.ts_adapter import TSAdapter
from codemap.graph.model import RawImport
from codemap.resolve.ts import resolve

TS_SOURCE = b"""\
import { foo } from './util';
import bar from './bar';
import React from 'react';
import { x } from '@/mod';

export function hello(): void {}

class Greeter {
  greet(): void {}
}

interface Config { name: string }
"""


# ---- 符号提取 ----

def test_ts_extract_symbols():
    a = TSAdapter()
    root = a.parse(TS_SOURCE, "src/m.ts")
    syms = a.extract_symbols(root, "src/m.ts")
    types = [s.type for s in syms]
    assert types.count("function") == 1   # hello
    assert types.count("class") == 2      # Greeter + interface Config
    assert types.count("method") == 1     # Greeter.greet
    names = {s.name for s in syms}
    assert "hello" in names and "Greeter" in names and "Config" in names


# ---- import 提取（source specifier）----

def test_ts_extract_imports_source():
    a = TSAdapter()
    root = a.parse(TS_SOURCE, "src/m.ts")
    imps = a.extract_imports(root, "src/m.ts")
    modules = {i.module for i in imps}
    assert "./util" in modules
    assert "./bar" in modules
    assert "react" in modules
    assert "@/mod" in modules


# ---- resolve：相对 + tsconfig alias + bare external ----

def test_resolve_relative_with_extension_probe(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.ts").write_text("")
    (tmp_path / "src" / "util.ts").write_text("export const foo = 1;")
    e = resolve(RawImport(module="./util", from_import=True), "src/m.ts", tmp_path)
    assert e is not None and e.dst == "file:src/util.ts"


def test_resolve_relative_index(tmp_path):
    """./y 无 y.ts 但有 y/index.ts → index.ts。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.ts").write_text("")
    (tmp_path / "src" / "y").mkdir()
    (tmp_path / "src" / "y" / "index.ts").write_text("")
    e = resolve(RawImport(module="./y", from_import=True), "src/m.ts", tmp_path)
    assert e is not None and e.dst == "file:src/y/index.ts"


def test_resolve_bare_external(tmp_path):
    """react / lodash 是 bare specifier 无 tsconfig → external None。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.ts").write_text("")
    for mod in ("react", "lodash", "express"):
        assert resolve(RawImport(module=mod, from_import=True), "src/m.ts", tmp_path) is None


def test_resolve_tsconfig_alias(tmp_path):
    """@/mod 经 tsconfig paths 解析到 src/mod.ts。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.ts").write_text("")
    (tmp_path / "src" / "mod.ts").write_text("")
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
    )
    e = resolve(RawImport(module="@/mod", from_import=True), "src/m.ts", tmp_path)
    assert e is not None and e.dst == "file:src/mod.ts"


def test_resolve_bare_no_tsconfig_is_external(tmp_path):
    """无 tsconfig 时，bare specifier 一律 external。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.ts").write_text("")
    e = resolve(RawImport(module="@/mod", from_import=True), "src/m.ts", tmp_path)
    assert e is None


# ---- TSX 语法分发（I2）----

# JSX namespace ``<svg:rect/>``（紧凑形式）触发 TS grammar 的 ERROR 恢复失败 —— 整棵
# function_declaration 失配、extract_symbols 返回空。只有 TSX grammar 能正确解析。
# 用它作 differentiator 暴露「未传 file_path → 永走 TS grammar」的静默丢失 bug。
TSX_SOURCE = b"""\
import { Component } from './c';
function App(){return <svg:rect/>}
"""


def test_tsx_parse_uses_tsx_grammar_when_file_path_given():
    """I2：parse(file_path='m.tsx') 必须用 TSX grammar 抽出 JSX 里的 function。

    回归：``TSAdapter.parse`` 默认 ``file_path=''``，``''.endswith('.tsx')=False`` → 永远走
    TS grammar，JSX-only 语法（紧凑 ``<svg:rect/>`` namespace）使整棵 function_declaration
    失配（ERROR 恢复失败）→ extract_symbols 返回空 → 符号静默丢失。
    修法：builder/incremental 调 parse 时传 file_path，让 .tsx 走 TSX grammar。
    """
    a = TSAdapter()
    # 不传 file_path → 走 TS grammar（bug 行为，namespace 触发 ERROR）
    root_ts = a.parse(TSX_SOURCE)
    syms_ts = a.extract_symbols(root_ts, "m.tsx")
    # 传 .tsx → 走 TSX grammar（修法后）
    root_tsx = a.parse(TSX_SOURCE, file_path="m.tsx")
    syms_tsx = a.extract_symbols(root_tsx, "m.tsx")
    # TS grammar 因 namespace 失配 → 抽不到 App（验证 bug 真实存在）
    assert "App" not in {s.name for s in syms_ts}, \
        "test setup: TS grammar should fail on JSX namespace (else test isn't a real differentiator)"
    # TSX grammar 必须抽出 App（这是修法后应得到的结果）
    assert "App" in {s.name for s in syms_tsx}, \
        "I2: TSX file with file_path='.tsx' must use TSX grammar (App symbol missing)"


def test_tsx_parse_uses_tsx_grammar_for_jsx_extension():
    """W1：parse(file_path='m.jsx') 必须用 TSX grammar 抽出 JSX 里的 function。

    回归：``extensions`` 元组注册了 .jsx（也是 JSX 语法），但 ``parse`` 的调度谓词
    ``file_path.endswith('.tsx')`` 只捕获 .tsx。.jsx 走 TS grammar → JSX 触发 ERROR 恢复
    失败 → function_declaration 失配 → 符号静默丢失（与 I2 为 .tsx 修的故障模式相同）。
    修法：谓词拓宽为 ``endswith(('.tsx', '.jsx'))``。
    """
    a = TSAdapter()
    # 不传 file_path → 走 TS grammar（bug 行为，namespace 触发 ERROR）
    root_ts = a.parse(TSX_SOURCE)
    syms_ts = a.extract_symbols(root_ts, "m.jsx")
    # 传 .jsx → 应走 TSX grammar（修法后）
    root_jsx = a.parse(TSX_SOURCE, file_path="m.jsx")
    syms_jsx = a.extract_symbols(root_jsx, "m.jsx")
    # TS grammar 因 namespace 失配 → 抽不到 App（验证 bug 真实存在）
    assert "App" not in {s.name for s in syms_ts}, \
        "test setup: TS grammar should fail on JSX namespace (else test isn't a real differentiator)"
    # TSX grammar 必须抽出 App（这是修法后应得到的结果）
    assert "App" in {s.name for s in syms_jsx}, \
        "W1: .jsx file with file_path='.jsx' must use TSX grammar (App symbol missing)"


def test_tsx_build_extracts_symbols_and_imports(tmp_path):
    """I2 集成：build 一个 .tsx 文件 → App 符号 + Component import 必须入库。

    回归：builder.py:144 ``adapter.parse(content)`` 未传 file_path → .tsx 永远走 TS grammar，
    JSX-only 语法使 function_declaration 失配 → 符号/import 静默丢失，被宽 except 吞。
    """
    from codemap.builder import build

    (tmp_path / "c.tsx").write_text("export function Component(){return null}\n")
    (tmp_path / "App.tsx").write_text(TSX_SOURCE.decode())
    build(tmp_path, tmp_path / "t.db")
    import sqlite3
    db = sqlite3.connect(str(tmp_path / "t.db"))
    nodes = {r[0] for r in db.execute("SELECT id FROM nodes").fetchall()}
    # App function 节点必须在（证明 TSX grammar 被用）
    assert "function:App.tsx:App" in nodes, \
        "I2: App symbol missing from build (TSX grammar not dispatched for .tsx)"
    # Component import 边必须在
    edges = db.execute(
        "SELECT src, dst FROM edges WHERE type='imports'"
    ).fetchall()
    assert ("file:App.tsx", "file:c.tsx") in edges, \
        "I2: App.tsx → c.tsx import edge missing (TSX parse lost the import)"
