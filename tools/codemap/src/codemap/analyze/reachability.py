"""可达性 / orphan 分析（ADR-024）：找"写了但没人 import"的模块 = dead code / 未接线。

AGF 诚实层 ⑥（对标 claude-code-harness 的 no-dead-code 门，但用真图谱替代它那套
零调用的正则 spike）。与 analyze/impact 对称：impact 问"改了 B 谁受影响"（反向 import
BFS），本模块问"模块 X 有没有人 import"（零入边检测）。

**粒度 = 文件/模块，不是函数**（诚实边界）：codemap 只建 file→file 的 ``imports`` 边，
**不建 ``calls`` 边、import 不解析到符号级**（实测：``from pkg.util import f`` 只产
``file:app -> file:util`` 边）。故函数级 dead-code 不可判（同文件被调用的函数零入边、会全
误报）；只能可靠判**模块级**："新写一个组件/模块文件，但全仓无人 import" = 经典 dead code
（前端"写了组件没挂上"、后端"写了 router 没 include"都属此类）。函数级需 codemap 补 call-
graph 提取（未来工作），见 docs/known-limitations.md。

orphan module 判据：``type='file'`` 的**代码**文件节点，零入边 ``imports``，且非 entrypoint /
非测试 / 非 config。边方向（05 §1.1）：入边 = ``WHERE dst=file:<path>``。

**Web-only**：codemap 无 Swift adapter，本门不覆盖 Apple 轨。
残余假阳（框架自动发现的模块，如未走 import 的插件）由 review 层带理由 override 兜。
"""
from __future__ import annotations

import re
import sqlite3

# entrypoint 文件（作为根被运行 / 框架自动加载，零 import 入边正常）
ENTRYPOINT_BASENAMES = frozenset(
    {
        "main.py", "__main__.py", "__init__.py", "app.py", "asgi.py", "wsgi.py",
        "manage.py", "setup.py", "conftest.py", "cli.py", "settings.py", "urls.py",
        "index.ts", "index.tsx", "index.js", "index.jsx", "main.ts", "main.tsx",
        "main.js", "app.ts", "app.tsx", "App.tsx", "App.jsx", "vite.config.ts",
    }
)
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|e2e)/|(_test|\.test|\.spec|test_)", re.IGNORECASE)


def _is_test_path(path: str | None) -> bool:
    return bool(path and _TEST_PATH.search(path))


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def find_orphan_modules(
    db: sqlite3.Connection,
    changed_files: list[str] | None = None,
    extra_entrypoints: list[str] | None = None,
) -> list[dict]:
    """返回 orphan 模块（零 ``imports`` 入边的代码文件）。

    changed_files 给定时只报这些文件里的 orphan（PR-scoped）；否则全仓。
    extra_entrypoints 追加豁免文件（basename 或相对路径，如框架自动发现的模块）。
    """
    entry_names = set(ENTRYPOINT_BASENAMES)
    entry_paths: set[str] = set()
    for e in extra_entrypoints or []:
        e = e.strip()
        if not e:
            continue
        (entry_paths if "/" in e else entry_names).add(e)
    changed = set(changed_files) if changed_files else None

    imported = {
        r[0] for r in db.execute("SELECT DISTINCT dst FROM edges WHERE type='imports'").fetchall()
    }
    # 只审代码文件（跳过 config/docs/data/infra —— 它们本就常无 import 入边）
    rows = db.execute(
        """SELECT n.id, n.file_path, f.category
           FROM nodes n JOIN files f ON n.file_path = f.path
           WHERE n.type = 'file' AND f.category = 'code'"""
    ).fetchall()

    orphans: list[dict] = []
    for nid, file_path, _cat in rows:
        if nid in imported:
            continue
        if _basename(file_path) in entry_names or file_path in entry_paths:
            continue
        if _is_test_path(file_path):
            continue
        if changed is not None and file_path not in changed:
            continue
        orphans.append({"id": nid, "file": file_path})
    orphans.sort(key=lambda o: o["file"] or "")
    return orphans


def orphans_report(
    db: sqlite3.Connection,
    changed_files: list[str] | None = None,
    extra_entrypoints: list[str] | None = None,
) -> dict:
    """CLI 用：orphan 模块列表 + 计数 + scope 元信息。"""
    orphans = find_orphan_modules(db, changed_files, extra_entrypoints)
    return {
        "orphans": orphans,
        "count": len(orphans),
        "scope": "changed" if changed_files else "全仓",
        "changed_files": sorted(changed_files) if changed_files else [],
        "granularity": "module",
        "note": (
            "orphan = 零 imports 入边的代码模块（疑似写了没接线）；粒度=文件/模块（codemap 无 "
            "call-graph，函数级不可判）；假阳经 review override 兜；Web-only（无 Swift）"
        ),
    }
