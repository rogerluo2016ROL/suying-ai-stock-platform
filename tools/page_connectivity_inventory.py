"""Build a frontend page-to-API connectivity inventory.

The inventory is intentionally static. It answers "which pages appear wired to
which frontend API calls?" before real smoke tests answer "do those APIs work?"
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


PAGE_ROOT = Path("frontend/src/pages")
APP_PATH = Path("frontend/src/App.tsx")

HIGH_RISK_COMPONENTS = {
    "SupplyChainBom",
    "Strategy",
    "Trade",
    "AuditLog",
    "RiskVerdicts",
    "DecisionContexts",
    "AutoTrade",
    "RiskControl",
    "Training",
    "ModelRegistry",
    "RuntimeStatus",
}

MEDIUM_RISK_COMPONENTS = {
    "Dashboard",
    "OpenDecision",
    "Screener",
    "ScreenerV2",
    "Predictions",
    "Signals",
    "Backtest",
    "Diagnosis",
    "DataUpdate",
    "PlatformUpgrade",
    "P0Workflow",
}

STALE_CONTRACT_MARKERS = {
    "/strategy/list": "old strategy list endpoint",
    "/strategy/${strategy.id}": "template strategy endpoint needs backend contract check",
    "/strategy/${strategy.id}/log": "strategy log endpoint needs backend contract check",
}

SOURCE_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")


@dataclass(frozen=True)
class RouteEntry:
    path: str
    component: str
    page_file: str


@dataclass
class InventoryRow:
    path: str
    component: str
    page_file: str
    status: str
    risk: str
    api_calls: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalise_page_import(import_path: str) -> str:
    normalized = import_path.strip()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized.startswith("pages/"):
        normalized = f"pages/{normalized}"
    page_file = Path("frontend/src") / normalized
    if not page_file.suffix:
        page_file = page_file.with_suffix(".tsx")
    return page_file.as_posix()


def extract_lazy_page_imports(app_source: str) -> dict[str, str]:
    pattern = re.compile(
        r"const\s+(?P<component>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*lazy\(\(\)\s*=>\s*import\((?P<quote>['\"])(?P<path>.+?)(?P=quote)\)\)"
    )
    return {
        match.group("component"): _normalise_page_import(match.group("path"))
        for match in pattern.finditer(app_source)
    }


def extract_protected_routes(app_source: str, lazy_imports: dict[str, str]) -> list[RouteEntry]:
    pattern = re.compile(
        r"\{\s*path:\s*(?P<quote>['\"])(?P<path>.+?)(?P=quote)\s*,\s*element:\s*<(?P<component>[A-Za-z_][A-Za-z0-9_]*)\s*/?>",
        re.MULTILINE,
    )
    routes: list[RouteEntry] = []
    for match in pattern.finditer(app_source):
        component = match.group("component")
        routes.append(
            RouteEntry(
                path=match.group("path"),
                component=component,
                page_file=lazy_imports.get(component, f"{PAGE_ROOT / component}.tsx"),
            )
        )
    return routes


def _dedupe_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})


def extract_api_calls(source: str) -> list[str]:
    calls: list[str] = []

    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*Api)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(", source):
        calls.append(f"{match.group(1)}.{match.group(2)}")

    request_pattern = re.compile(
        r"\b(api|rootApi)\.(get|post|put|delete|patch)\s*\(\s*(?P<quote>['\"`])(?P<path>.+?)(?P=quote)",
        re.DOTALL,
    )
    for match in request_pattern.finditer(source):
        calls.append(f"{match.group(1)}.{match.group(2)}({match.group('quote')}{match.group('path')}{match.group('quote')})")

    browser_patterns = [
        ("fetch", r"\bfetch\s*\(\s*(?P<quote>['\"`])(?P<path>.+?)(?P=quote)"),
        ("EventSource", r"\bnew\s+EventSource\s*\(\s*(?P<quote>['\"`])(?P<path>.+?)(?P=quote)"),
        ("window.open", r"\bwindow\.open\s*\(\s*(?P<quote>['\"`])(?P<path>.+?)(?P=quote)"),
    ]
    for label, pattern in browser_patterns:
        for match in re.finditer(pattern, source, re.DOTALL):
            calls.append(f"{label}({match.group('quote')}{match.group('path')}{match.group('quote')})")

    return _dedupe_sorted(calls)


def _resolve_local_import(current_file: Path, import_path: str) -> Path | None:
    base = current_file.parent / import_path
    candidates: list[Path] = []
    if base.suffix:
        candidates.append(base)
    else:
        candidates.extend(base.with_suffix(ext) for ext in SOURCE_EXTENSIONS)
        candidates.extend(base / f"index{ext}" for ext in SOURCE_EXTENSIONS)
    for candidate in candidates:
        if candidate.exists() and candidate.suffix in SOURCE_EXTENSIONS:
            return candidate
    return None


def _iter_local_imports(source: str) -> Iterable[str]:
    pattern = re.compile(
        r"(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?(?P<quote>['\"])(?P<path>\.[^'\"]+)(?P=quote)",
        re.MULTILINE,
    )
    for match in pattern.finditer(source):
        yield match.group("path")


def collect_related_sources(project_root: Path, page_file: str, max_depth: int = 3) -> list[str]:
    """Read a page plus local component/hook imports that may contain API calls."""

    root = (project_root / "frontend/src").resolve()
    start = (project_root / page_file).resolve()
    visited: set[Path] = set()
    sources: list[str] = []

    def walk(path: Path, depth: int) -> None:
        if path in visited or depth > max_depth:
            return
        try:
            rel = path.relative_to(root)
        except ValueError:
            return
        if rel.parts and rel.parts[0] == "contexts":
            return
        if "/api/" in path.as_posix():
            return
        visited.add(path)
        source = path.read_text(encoding="utf-8")
        sources.append(source)
        for import_path in _iter_local_imports(source):
            resolved = _resolve_local_import(path, import_path)
            if resolved is not None:
                walk(resolved.resolve(), depth + 1)

    if start.exists():
        walk(start, 0)
    return sources


def _stale_contract_notes(api_calls: list[str]) -> list[str]:
    notes: list[str] = []
    for call in api_calls:
        if call.startswith("api."):
            continue
        for marker, note in STALE_CONTRACT_MARKERS.items():
            if marker in call:
                notes.append(note)
    return notes


def classify_row(component: str, api_calls: list[str], source: str, page_exists: bool) -> tuple[str, str, list[str]]:
    notes: list[str] = []
    if not page_exists:
        return "missing-page", "high", ["page file referenced by route was not found"]

    stale_notes = _stale_contract_notes(api_calls)
    if stale_notes:
        notes.extend(stale_notes)
        return "stale-contract", "high", notes

    if not api_calls:
        notes.append("no frontend API calls detected")
        if component in {"Training", "ModelRegistry", "RuntimeStatus", "PlatformUpgrade"}:
            notes.append("system/model page should be verified against real services")
        risk = "high" if component in HIGH_RISK_COMPONENTS else "medium"
        return "prototype-only", risk, notes

    if "const services =" in source and component == "RuntimeStatus":
        notes.append("hard-coded service matrix should be replaced by health API checks")

    if component in HIGH_RISK_COMPONENTS:
        return "needs-smoke", "high", notes
    if component in MEDIUM_RISK_COMPONENTS:
        return "needs-smoke", "medium", notes
    return "needs-smoke", "medium", notes


def build_inventory(project_root: Path) -> list[InventoryRow]:
    app_file = project_root / APP_PATH
    app_source = app_file.read_text(encoding="utf-8")
    lazy_imports = extract_lazy_page_imports(app_source)
    routes = extract_protected_routes(app_source, lazy_imports)

    rows: list[InventoryRow] = []
    for route in routes:
        page_path = project_root / route.page_file
        page_exists = page_path.exists()
        sources = collect_related_sources(project_root, route.page_file) if page_exists else []
        source = "\n".join(sources)
        api_calls = extract_api_calls(source)
        status, risk, notes = classify_row(route.component, api_calls, source, page_exists)
        rows.append(
            InventoryRow(
                path=route.path,
                component=route.component,
                page_file=route.page_file,
                status=status,
                risk=risk,
                api_calls=api_calls,
                notes=notes,
            )
        )
    return rows


def _counter_lines(title: str, counter: Counter[str]) -> list[str]:
    lines = [f"### {title}", ""]
    for key in sorted(counter):
        lines.append(f"- {key}: {counter[key]}")
    lines.append("")
    return lines


def render_markdown(rows: list[InventoryRow]) -> str:
    risk_counter = Counter(row.risk for row in rows)
    status_counter = Counter(row.status for row in rows)

    lines: list[str] = [
        "# 全站页面联通盘点",
        "",
        "日期：2026-06-29",
        "",
        "## 结论摘要",
        "",
        "本报告由 `tools/page_connectivity_inventory.py` 静态生成，用于定位页面到前端 API 的连接情况。它不替代真实 API smoke 或浏览器 UAT。",
        "",
    ]
    lines.extend(_counter_lines("风险分布", risk_counter))
    lines.extend(_counter_lines("状态分布", status_counter))

    lines.extend(
        [
            "## 页面矩阵",
            "",
            "| 路由 | 页面 | 风险 | 状态 | API/动作 | 备注 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in rows:
        calls = "<br>".join(f"`{call}`" for call in row.api_calls) if row.api_calls else "-"
        notes = "<br>".join(row.notes) if row.notes else "-"
        lines.append(
            f"| `{row.path}` | `{row.component}` | `{row.risk}` | `{row.status}` | {calls} | {notes} |"
        )

    high_rows = [row for row in rows if row.risk == "high"]
    lines.extend(["", "## 高风险清单", ""])
    if high_rows:
        for row in high_rows:
            notes = "; ".join(row.notes) if row.notes else "needs real API smoke"
            lines.append(f"- `{row.path}` / `{row.component}`：{row.status}，{notes}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "1. 用 `tools/page_api_smoke.py` 对 `needs-smoke` 页面接口做真实服务验证。",
            "2. 如出现 `stale-contract` 页面，先核对后端路由，再修前端 API helper。",
            "3. 对 `prototype-only` 系统/模型页补真实服务状态，不能真实启用的功能必须显示禁用原因。",
            "",
        ]
    )
    return "\n".join(lines)


def rows_to_json(rows: list[InventoryRow]) -> str:
    return json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, help="Write markdown report to this file")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    args = parser.parse_args(argv)

    rows = build_inventory(args.root)
    content = rows_to_json(rows) if args.json else render_markdown(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
