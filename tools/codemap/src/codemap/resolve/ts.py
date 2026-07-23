"""TS / JS import 路径解析（04 §4.2）。

相对 specifier（./ ../）→ 后缀试探 + index；bare specifier（@/x、模块名）先查
tsconfig paths/baseUrl 别名 —— **alias 相对 tsconfig 所在目录解析**（非 project_root；
真实项目 tsconfig 常在 frontend/ 子目录，原用 root 致 @/ alias 全丢，recall ≈ 6.5%），
未命中 → external（node_modules）返回 None。
"""

from __future__ import annotations
import json
import re
from pathlib import Path

from codemap.graph.model import EdgeRecord, RawImport

# tsconfig 常是 JSONC（含 /* */ + // 注释），json.loads 不认，需剥离
_JSONC_COMMENT_RE = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)

TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")


_TS_FOR_ESM = {".js": (".ts", ".tsx", ".d.ts", ".js"), ".jsx": (".tsx", ".jsx"),
               ".mjs": (".mts", ".mjs"), ".cjs": (".cts", ".cjs")}


def resolve(raw: RawImport, current_file: str, project_root: str | Path) -> EdgeRecord | None:
    spec = raw.module
    if not spec:
        return None
    root = Path(project_root).resolve()
    base = _resolve_base(spec, current_file, root)
    if base is None:
        return None  # external（bare 未命中 alias）
    # ESM 写法：import './foo.js' 实际指 foo.ts（TS 编译到 JS，Claude-Code/bun 项目）。
    # base 有 .js 等 suffix → 试 .ts/.tsx（+ 原后缀兜底）；无 suffix → 全 TS_EXTS。
    if base.suffix:
        mapped = _TS_FOR_ESM.get(base.suffix)
        exts = mapped if mapped else (base.suffix,) + TS_EXTS  # .vue 等非 ESM → 试原后缀 + TS
    else:
        exts = TS_EXTS
    for ext in exts:
        cand = base.with_suffix(ext)
        if cand.is_file():
            return _edge(current_file, cand, root, raw)
        idx = (base.with_suffix("") if base.suffix else base) / f"index{ext}"
        if idx.is_file():
            return _edge(current_file, idx, root, raw)
    return None  # 解析失败


def _resolve_base(spec: str, current_file: str, root: Path) -> Path | None:
    """返回 spec 对应的无后缀 base **绝对** Path；bare 未命中 alias 返回 None（external）。"""
    if spec.startswith("."):
        return ((root / current_file).parent / spec).resolve()
    # bare specifier：查 tsconfig alias，相对 tsconfig 目录解析（非 root）
    tc, tc_dir = _find_tsconfig((root / current_file).parent, root)
    if tc is None:
        return None
    return _match_alias(spec, tc, tc_dir, root)


def _match_alias(spec: str, tc: dict, tc_dir: Path, root: Path) -> Path | None:
    """tsconfig compilerOptions.paths / baseUrl 解析（alias 相对 tsconfig 目录）。

    返回绝对 Path（如 @/mod + tsconfig 在 frontend/ → frontend/src/mod）；未命中 None。
    """
    co = tc.get("compilerOptions", {})
    paths = co.get("paths", {}) or {}
    for pat, targets in paths.items():
        prefix = pat.rstrip("/*")
        if spec == prefix or (prefix and spec.startswith(prefix + "/")):
            rest = spec[len(prefix):].lstrip("/")
            tgt = (targets[0] if targets else "").rstrip("/*")
            return (tc_dir / tgt / rest).resolve() if rest else (tc_dir / tgt).resolve()
    base_url = co.get("baseUrl")
    if base_url and (tc_dir / base_url / spec.split("/")[0]).exists():
        return (tc_dir / base_url / spec).resolve()
    return None


def _find_tsconfig(start: Path, root: Path) -> tuple[dict | None, Path | None]:
    """从 start 往上找 tsconfig（tsconfig.json + tsconfig.app.json Vite 拆分）。

    优先 ``compilerOptions.paths`` 非空的 —— Vite 项目 tsconfig.json 是 base（files:[]
    + references，无 paths），@/ paths 在 tsconfig.app.json；原只找 tsconfig.json 致
    @/ 全漏。返回 (dict, tsconfig_dir)。
    """
    for d in [start, *start.parents]:
        if root not in d.parents and d != root:
            break
        docs: list[tuple[dict, Path, dict | None]] = []
        for name in ("tsconfig.json", "tsconfig.app.json"):
            tc = d / name
            if tc.is_file():
                try:
                    doc = json.loads(_JSONC_COMMENT_RE.sub("", tc.read_text()))
                    docs.append((doc, d, (doc.get("compilerOptions") or {}).get("paths")))
                except Exception:
                    pass
        if docs:
            with_paths = [x for x in docs if x[2]]
            chosen = (with_paths or docs)[0]
            return chosen[0], chosen[1]
    return None, None


def _edge(current_file: str, target: Path, root: Path, raw: RawImport) -> EdgeRecord:
    try:
        rel = target.resolve().relative_to(root).as_posix()
    except ValueError:
        return None  # 解析到 root 外 = external（不应发生，_match_alias 已在 tc_dir 内）
    return EdgeRecord(
        src=f"file:{current_file}", dst=f"file:{rel}", type="imports", weight=0.7,
        detail=f"import {raw.module}",
    )
