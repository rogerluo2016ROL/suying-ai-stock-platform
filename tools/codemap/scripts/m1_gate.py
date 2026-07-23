"""M1 首语言 gate 半自动抽检：codemap 提取 vs Python ast 真值（09 §2）。

跑：uv run python scripts/m1_gate.py [project_root]
输出：符号 / import 提取 precision·recall + external 判定 accuracy。
阈值（09 §2）：符号 ≥95%、import ≥90%（首语言 gate）；external 误判 ≤5%（即 acc ≥95%）。
"""

from __future__ import annotations
import ast
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from codemap.builder import build  # noqa: E402
from codemap.extract.python_adapter import PythonAdapter  # noqa: E402
from codemap.resolve.import_resolver import resolve  # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
STDLIB = getattr(sys, "stdlib_module_names", set())
adapter = PythonAdapter()

build(ROOT, ROOT / ".agf" / "m1-gate.db")
db = sqlite3.connect(str(ROOT / ".agf" / "m1-gate.db"))
py_files = [r[0] for r in db.execute("SELECT path FROM files WHERE language='python'").fetchall()]
db.close()

sym_tp = sym_fp = sym_fn = 0
imp_tp = imp_fp = imp_fn = 0
ext_total = ext_correct = 0

for rel in py_files:
    src = (ROOT / rel).read_bytes()
    ts_root = adapter.parse(src)

    # 符号：method 名含类前缀，统一取 last segment 对比 ast（ast 不区分 method/function）
    cm_syms = {s.name.split(".")[-1] for s in adapter.extract_symbols(ts_root, rel)}
    at = ast.parse(src.decode())
    ast_syms = {n.name for n in ast.walk(at)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    sym_tp += len(cm_syms & ast_syms)
    sym_fp += len(cm_syms - ast_syms)
    sym_fn += len(ast_syms - cm_syms)

    # import module 集合
    cm_mods = {i.module for i in adapter.extract_imports(ts_root, rel) if i.module}
    ast_mods: set[str] = set()
    for n in ast.walk(at):
        if isinstance(n, ast.Import):
            ast_mods.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            ast_mods.add(n.module)
    imp_tp += len(cm_mods & ast_mods)
    imp_fp += len(cm_mods - ast_mods)
    imp_fn += len(ast_mods - cm_mods)

    # external 判定：codemap None vs 真值（标准库 or 物理不在项目内）
    for raw in adapter.extract_imports(ts_root, rel):
        if not raw.module or raw.level > 0:
            continue
        cm_none = resolve(raw, rel, ROOT) is None
        mod_path = ROOT / raw.module.replace(".", "/")
        truth_none = raw.module.split(".")[0] in STDLIB or not (
            mod_path.with_suffix(".py").exists() or (mod_path / "__init__.py").exists())
        ext_total += 1
        if cm_none == truth_none:
            ext_correct += 1


def metric(tp: int, fp: int, fn: int) -> tuple[float, float]:
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    return p, r


sp, sr = metric(sym_tp, sym_fp, sym_fn)
ip, ir = metric(imp_tp, imp_fp, imp_fn)
ea = ext_correct / ext_total if ext_total else 1.0

print(f"files: {len(py_files)}")
print(f"符号:    P={sp:.1%} R={sr:.1%}  (tp={sym_tp} fp={sym_fp} fn={sym_fn})")
print(f"import:  P={ip:.1%} R={ir:.1%}  (tp={imp_tp} fp={imp_fp} fn={imp_fn})")
print(f"external:acc={ea:.1%}  ({ext_correct}/{ext_total})")
print("---")
print(f"gate 阈值（09 §2）: 符号 ≥95% & import ≥90% & external ≥95%")
print(f"结果: {'PASS' if sr >= 0.95 and ir >= 0.90 and ea >= 0.95 else 'FAIL'}")
