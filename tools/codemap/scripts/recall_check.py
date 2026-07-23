"""真实项目 import recall 抽检（防「单测全绿但真实项目漏 96%」类灾难）。

对照源码项目内 import（Python ast / TS·Vue grep）vs codemap db 的 imports 边，
出 recall（数量级）。M8 真实项目验证的必备项 —— 单测用合成小项目（import 恰好
解析），抓不到包根/alias/SFC 等 src-layout 真实问题。

跑：uv run python scripts/recall_check.py [project_root] [db_path]
阈值（建议）：Python ≥ 80%、TS/Vue ≥ 70%（受 .vue/.css 语言覆盖影响）。
低于阈值 → resolver 有 src-layout 类 bug，查包根/alias/tsconfig。

口径：数量级 recall（精确 1:1 匹配难 —— 一个 import 行可能建多条边，如
``from X import a,b`` 或 source_roots 多候选）；足够抓 recall 灾难。
"""
from __future__ import annotations
import ast
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
DB = Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / ".agf" / "code-map.db")
EXCLUDE = {".git", ".venv", "node_modules", "__pycache__", "dist", "build",
           "htmlcov", "coverage", ".pytest_cache", ".mypy_cache"}


def _files(suffixes: tuple) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=False,
    ).stdout.splitlines()
    return [ROOT / f for f in out if any(f.endswith(s) for s in suffixes)]


def _source_roots() -> list[Path]:
    """Python 包根候选（project_root + 一级子目录，同 builder._source_roots）。"""
    roots = [ROOT]
    for sub in sorted(os.listdir(ROOT)):
        p = ROOT / sub
        if p.is_dir() and sub not in EXCLUDE:
            roots.append(p)
    return roots


def py_recall(db: sqlite3.Connection) -> tuple[int, int]:
    """Python 真实项目内 import（ast + 物理文件在 source_roots 内）vs db 边。

    真值按 (file, module) 去重 —— 与 db 边的 src→dst ON CONFLICT 去重一致
    （同文件多次 ``from app.x import`` 只算 1 条边）。
    """
    import sys as _sys
    srs = _source_roots()
    truth_pairs: set[tuple[str, str]] = set()
    for f in _files((".py",)):
        rel = f.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(f.read_bytes())
        except SyntaxError:
            continue  # 坏文件（emoji/缩进）跳过，不阻塞度量
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.level > 0:
                # 相对 import（from . / from ..y），必项目内（同包）；与 db 边 1:1
                truth_pairs.add((rel, f"rel:{n.level}:{n.module or ''}"))
                continue
            mod = None
            if isinstance(n, ast.Import):
                mod = n.names[0].name
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                mod = n.module
            if not mod or mod.split(".")[0] in _sys.stdlib_module_names:
                continue
            for sr in srs:  # 项目内 = module 文件在某 source_root 下
                mp = sr / mod.replace(".", "/")
                if mp.with_suffix(".py").is_file() or (mp / "__init__.py").is_file():
                    truth_pairs.add((rel, mod))
                    break
    actual = db.execute(
        "SELECT COUNT(*) FROM edges WHERE type='imports' AND src LIKE 'file:%.py'"
    ).fetchone()[0]
    return len(truth_pairs), actual


def ts_recall(db: sqlite3.Connection) -> tuple[int, int]:
    """TS/Vue 项目内 import（@/ alias 或 ./ 相对，bare=node_modules external）vs db 边。

    真值按 (file, module) 去重，与 db 边一致。
    """
    truth_pairs: set[tuple[str, str]] = set()
    for f in _files((".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")):
        rel = f.relative_to(ROOT).as_posix()
        for line in f.read_text(errors="ignore").splitlines():
            s = line.strip()
            if not s.startswith("import") or "from " not in s:
                continue
            if not any(m in s for m in ["'@/", '"@/', "'./", '"./', "'../", '"../']):
                continue
            mod = s.split("from", 1)[1].strip().strip("'\"").strip()
            truth_pairs.add((rel, mod))
    actual = db.execute(
        "SELECT COUNT(*) FROM edges WHERE type='imports' AND "
        "(src LIKE 'file:%.ts' OR src LIKE 'file:%.tsx' OR src LIKE 'file:%.js' "
        "OR src LIKE 'file:%.jsx' OR src LIKE 'file:%.vue' OR src LIKE 'file:%.svelte')"
    ).fetchone()[0]
    return len(truth_pairs), actual


def _pct(a: int, t: int) -> str:
    return f"{a*100//t}%" if t else "—"


def main() -> None:
    if not DB.is_file():
        print(f"❌ db 不存在：{DB}（先 `codemap build {ROOT}`）", file=sys.stderr)
        sys.exit(2)
    db = sqlite3.connect(str(DB))
    pt, pa = py_recall(db)
    tt, ta = ts_recall(db)
    print(f"Python:  真实项目内 import {pt} / db 边 {pa} → recall {_pct(pa, pt)}  （阈值 ≥80%）")
    print(f"TS/Vue:  真实项目内 import {tt} / db 边 {ta} → recall {_pct(ta, tt)}  （阈值 ≥70%）")
    print("---")
    ok = (pa * 100 >= 80 * pt if pt else True) and (ta * 100 >= 70 * tt if tt else True)
    print(f"结果: {'PASS' if ok else 'FAIL（recall 低于阈值，查 resolver src-layout）'}")


if __name__ == "__main__":
    main()
