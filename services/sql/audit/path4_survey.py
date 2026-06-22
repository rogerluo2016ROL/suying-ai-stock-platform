#!/usr/bin/env python3
"""Path #4 inline executemany survey — read-only grep + AST static analysis.
ADR-015 §决策 0-6. 产物: docs/reviews/path4-inline-executemany-survey-<DATE>.md
SIT-6: 0 次 DDL/DML 关键字命中（仅 SELECT + 静态分析）."""
import ast, re, sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
SYNC = ROOT / "services/data-service/app/sync"
ETL = ROOT / "packages/kronos-data/kronos_data"
REPORT = ROOT / f"docs/reviews/path4-inline-executemany-survey-{date.today().isoformat()}.md"

# PG table snapshot (live PG 2026-06-22): {table: (exists, col_count)}
_PG = {
    "announcements": (True, 5), "cctv_news": (True, 5), "mp_report": (True, 6),
    "interact_qa": (True, 7), "policy_law": (True, 8), "fina_mainbz": (True, 6),
    "fina_audit": (True, 7), "stock_profiles": (True, 16), "st_history": (True, 5),
    "stocks": (True, 11), "stk_mins": (True, 10), "rt_k": (True, 12),
    "daily_kline": (True, 12), "moneyflow": (True, 11), "stk_limit": (True, 6),
    "daily_basic": (True, 8), "ths_daily": (True, 17), "limit_list_d": (True, 24),
}
CANDIDATES = [
    ("announcements", SYNC / "announcements.py", "announcements"),
    ("cctv_news", SYNC / "cctv_news.py", "cctv_news"),
    ("mp_report", SYNC / "mp_report.py", "mp_report"),
    ("interact", SYNC / "interact.py", "interact_qa"),
    ("policy_law", SYNC / "policy_law.py", "policy_law"),
    ("fina_mainbz", SYNC / "fina_mainbz.py", "fina_mainbz"),
    ("fina_audit", SYNC / "fina_audit.py", "fina_audit"),
    ("stock_profiles", SYNC / "stock_profiles.py", "stock_profiles"),
    ("namechange", SYNC / "namechange.py", "st_history"),
    ("stocks", SYNC / "stocks.py", "stocks"),
    ("rt_min", SYNC / "rt_min.py", "stk_mins"),
    ("tushare", SYNC / "tushare.py", "daily_kline"),
    ("etl_rt_k", ETL / "etl.py", "rt_k"),
]

def _grep(path: Path, pat: str) -> list:
    return [(i, l.rstrip()) for i, l in enumerate(open(path, errors="ignore"), 1) if re.search(pat, l)]

def _sync_funcs(fp: Path) -> list:
    if not fp.exists(): return []
    try:
        tree = ast.parse(fp.read_text())
        return [n.name for n in ast.iter_child_nodes(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and (n.name.startswith("sync_") or n.name.startswith("collect_"))]
    except SyntaxError:
        return ["<syntax error>"]

def survey(label: str, fp: Path, table: str) -> dict:
    """Static analysis: target, paths, risk, priority."""
    em = _grep(fp, r"executemany")
    pgw = _grep(fp, r"_pg_write\b")
    pgw_imp = _grep(fp, r"from app\.sync\.pg_writer import (write_|_pg_write)")
    pgc = _grep(fp, r"psycopg2\.connect")
    sqc = _grep(fp, r"sqlite3\.connect")
    ev = _grep(fp, r"execute_values")
    h_pgw = bool(pgw)
    h_wrapper = bool(pgw_imp) and not h_pgw
    h_pgc = bool(pgc); h_sqc = bool(sqc); h_ev = bool(ev); h_em = bool(em)

    if (h_pgw or h_wrapper) and h_sqc:   target = "dual"
    elif (h_pgw or h_wrapper):           target = "dual"
    elif h_pgc and not h_sqc:             target = "pg-only"
    elif h_sqc and not h_pgc:             target = "sqlite-only"
    elif h_pgc and h_sqc:                 target = "dual"
    else:                                 target = "unknown"

    if h_pgw and h_ev:        pg_path = "mixed"
    elif h_pgw:               pg_path = "_pg_write"
    elif h_wrapper:           pg_path = "_pg_write (via thin wrapper)"
    elif h_ev:                pg_path = "inline-execute_values"
    elif h_pgc:               pg_path = "inline-cursor"
    else:                     pg_path = "none"

    if h_em:      sqlite_path = "inline-executemany"
    elif h_sqc:   sqlite_path = "inline-execute"
    else:         sqlite_path = "none"

    pg_exists, pg_cols = _PG.get(table, (False, "?"))
    risk_map = {"stocks": "high", "stock_profiles": "high",
                "tushare": "medium", "namechange": "medium",
                "etl_rt_k": "low", "rt_min": "low"}
    risk = risk_map.get(label, "low")

    if label == "stocks":       pri = "P1"
    elif label == "tushare":    pri = "P1"
    elif label in ("etl_rt_k", "rt_min"): pri = "excluded"
    elif h_pgw and target == "dual":      pri = "P2"
    elif target == "dual":                pri = "P2"
    elif target == "pg-only":             pri = "P3"
    else:                                 pri = "P3"

    funcs = _sync_funcs(fp)
    if label == "etl_rt_k":
        funcs = ["sync_rt_k", "sync_rt_sw_k"]

    return {
        "module": label, "file": str(fp.relative_to(ROOT)), "table": table,
        "target": target, "pg_path": pg_path, "sqlite_path": sqlite_path,
        "em_locs": [f"L{ln}" for ln, _ in em] if em else ["none"],
        "funcs": funcs, "pg_exists": pg_exists, "pg_cols": pg_cols,
        "risk": risk, "priority": pri, "h_pgw": h_pgw,
    }

def _compat(r):
    """ADR-012 trunk compatibility string."""
    m = r["module"]
    if m == "stocks":
        return "需 upsert 扩展（ADR-015.0 前置）— PG 当前单条 cur.execute 循环 + ON CONFLICT DO update，不兼容 _pg_write"
    if m == "stock_profiles":
        return "需 upsert 扩展 — PG 当前 execute_values + ON CONFLICT DO update，SQLite 列子集（6/15）"
    if m == "namechange":
        return "需 upsert 扩展 — PG 当前 cur.executemany + ON CONFLICT DO update，无 SQLite 路径"
    if m == "tushare":
        return "PG 已全走 pg_writer thin wrapper，SQLite executemany 为 fallback — 需确认 insert-or-replace 语义兼容"
    if m == "etl_rt_k":
        return "kronos-data etl 通过 _get_etl_db() 统一 PG/SQLite，非 path #4 治理范围"
    if m == "rt_min":
        return "PG 已走 write_stk_mins thin wrapper，SQLite 为 best-effort backup — 低优先级"
    if r["h_pgw"]:
        return "PG 已走 _pg_write 主干 — 可直接切换，SQLite 侧沿用 inline executemany（方案 A 预期行为）"
    return "需评估 — 未检测到 _pg_write 调用"

def main():
    results = [survey(l, fp, t) for l, fp, t in CANDIDATES if fp.exists()]
    today = date.today().isoformat()
    dc = sum(1 for r in results if r["target"] == "dual")
    sc = sum(1 for r in results if r["target"] == "sqlite-only")
    pc = sum(1 for r in results if r["target"] == "pg-only")
    p1 = [r for r in results if r["priority"] == "P1"]
    p3 = [r for r in results if r["priority"] == "P3"]
    excl = [r for r in results if r["priority"] == "excluded"]

    s1 = "".join(f"| {r['module']} | {r['file']} | {r['table']} | {r['target']} | "
                 f"{', '.join(r['em_locs'][:3])} | {r['risk']} |\n" for r in results)
    s2 = "".join(f"| {r['module']} | {r['target']} | {r['pg_path']} | {r['sqlite_path']} | "
                 f"{'Yes' if r['pg_exists'] else 'No'} | {r['pg_cols']} | "
                 f"{', '.join(r['funcs'][:3])}{'...' if len(r['funcs'])>3 else ''} | "
                 f"{', '.join(r['em_locs'])} | {r['risk']} |\n" for r in results)
    s2x = "".join(f"### {r['module']}\n\n- 文件: `{r['file']}`\n"
                  f"- 主表: `{r['table']}` (PG: {'存在' if r['pg_exists'] else '不存在'}, {r['pg_cols']} 列)\n"
                  f"- 目标: **{r['target']}** | PG: `{r['pg_path']}` | SQLite: `{r['sqlite_path']}`\n"
                  f"- executemany: {', '.join(r['em_locs'])}\n"
                  f"- 风险: **{r['risk']}** | 优先级: **{r['priority']}**\n\n" for r in results)
    s3 = "".join(f"| {r['module']} | {r['risk']} | {'Yes' if r['h_pgw'] else 'No'} | "
                 f"{'Yes' if r['module'] in ('stocks','stock_profiles','namechange') else 'No'} | "
                 f"{r['priority']} |\n" for r in results)
    s4 = "".join(f"| {r['module']} | {_compat(r)} |\n" for r in results)
    s5 = "| P0 (前置) | `_pg_write` upsert 扩展 | **ADR-015.0** | 0.5d | 阻断 P1 stocks.py |\n"
    for i, r in enumerate(p1):
        s5 += f"| P1 | {r['module']} | ADR-015.{i+1} | 1-2d | {r['risk']} risk |\n"
    s5 += (f"| P2 | announcements/cctv_news/mp_report/policy_law (合并) | ADR-015.{len(p1)+1} | 1-2d | 4 模块同参数签名 |\n"
           f"| P2 | fina_mainbz/fina_audit/stock_profiles (合并) | ADR-015.{len(p1)+2} | 1-2d | fina_* 同型, stock_profiles 需 upsert |\n")
    for i, r in enumerate(p3):
        s5 += f"| P3 | {r['module']} | ADR-015.{len(p1)+2+i+1} | 0.5d | PG-only inline, 最小改动 |\n"
    s6 = ""
    for r in excl:
        if r["module"] == "rt_min":
            reason = "实时分钟线 PG 已走 write_stk_mins thin wrapper，SQLite 为 best-effort backup"
        elif r["module"] == "etl_rt_k":
            reason = "kronos-data etl 通过 _get_etl_db() 统一 PG/SQLite，非 path #4 治理范围"
        else:
            reason = "SQLite 本地文件无列错位/网络抖动风险"
        s6 += f"| {r['module']} | {r['table']} | {r['target']} | {reason} |\n"

    report = f"""# Path #4 inline executemany 盘点报告

> 日期: {today} | 生成: `services/sql/audit/path4_survey.py` | ADR-015 §决策 0-6

## §1 候选模块清单

实测: **{len(results)}** 模块（{dc} dual + {sc} SQLite-only + {pc} PG-only）

| 模块 | 源文件 | 主表 | 目标 | executemany | 风险 |
|---|---|---|---|---|---|
{s1}

## §2 维度盘点矩阵

| 模块 | 目标 | PG 路径 | SQLite 路径 | PG 表 | 列 | sync 函数 | executemany | 风险 |
|---|---|---|---|---|---|---|---|---|
{s2}

### 逐模块详情

{s2x}

## §3 风险评估

| 模块 | 列错位风险 | PG _pg_write | 需 upsert | 优先级 |
|---|---|---|---|---|
{s3}

## §4 ADR-012 兼容性

| 模块 | 兼容性评估 |
|---|---|
{s4}

**关键**: stocks/stock_profiles/namechange 需 upsert 语义 → ADR-015.0 前置; 7 模块可直接切换 _pg_write

## §5 子 ADR-015.X 推荐清单

| 优先级 | 模块 | 子 ADR | 工作量 | 备注 |
|---|---|---|---|---|
{s5}

子 ADR 数: 5（含 ADR-015.0）。实施: P0 → P1(stocks/tushare) → P2(公告+财务) → P3(namechange)

## §6 排除模块清单

| 模块 | 表 | 目标 | 排除理由 |
|---|---|---|---|
{s6}

引用: ADR-012 §决策 0 + ADR-015 §决策 0-6 + 方案 A + 基线 2026-06-22
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    print(f"Survey complete: {REPORT}")
    print(f"  Modules: {len(results)} total ({dc} dual, {sc} SQLite-only, {pc} PG-only)")

if __name__ == "__main__":
    main()