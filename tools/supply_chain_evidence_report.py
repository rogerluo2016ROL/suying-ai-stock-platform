"""Human-readable Markdown reporting for supply-chain evidence runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from supply_chain_evidence_orchestrator import EvidenceRunResult


LAYER_IDS = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")
DIMENSION_IDS = (
    "function_value",
    "technology_route",
    "physical_bom",
    "value_pool",
    "competition_moat",
    "supply_demand_cycle",
    "evidence_validation",
    "market_expectation",
)
CELL_STATUSES = {"known", "proxy", "unknown", "contradicted"}


def _text(value: object) -> str:
    return " ".join(str(value or "").replace("|", "\\|").split())


def _facts(companies: Sequence[Mapping], key: str) -> list[tuple[Mapping, Mapping]]:
    rows: list[tuple[Mapping, Mapping]] = []
    for company in companies:
        for fact in company.get(key) or ():
            if isinstance(fact, Mapping):
                rows.append((company, fact))
    return rows


def _render_fact_section(
    heading: str,
    companies: Sequence[Mapping],
    key: str,
    *,
    label: str,
) -> list[str]:
    lines = [heading, ""]
    rows = _facts(companies, key)
    if not rows:
        lines.extend(["- 无", ""])
        return lines
    for company, fact in rows:
        code = _text(company.get("company_code")) or "unknown-company"
        mapping_id = _text(company.get("mapping_id")) or "unknown-mapping"
        fact_id = _text(fact.get("fact_id")) or "unknown-fact"
        summary = _text(fact.get("summary")) or "无摘要"
        lines.append(
            f"- [{label}] {code} / {mapping_id} / {fact_id}: {summary}"
        )
    lines.append("")
    return lines


def _cell_value(cell: object) -> str:
    if not isinstance(cell, Mapping):
        return "unknown"
    status = str(cell.get("status") or "unknown").casefold()
    if status not in CELL_STATUSES:
        status = "unknown"
    evidence_ids = tuple(
        dict.fromkeys(
            _text(value) for value in cell.get("evidence_ids") or () if _text(value)
        )
    )
    return f"{status} ({', '.join(evidence_ids)})" if evidence_ids else status


def _render_matrix(companies: Sequence[Mapping]) -> list[str]:
    lines = ["## 8 层 × 8 维矩阵", ""]
    if not companies:
        lines.extend(["- 无候选公司", ""])
        return lines
    header = "| 层级 | " + " | ".join(DIMENSION_IDS) + " |"
    separator = "| --- | " + " | ".join("---" for _ in DIMENSION_IDS) + " |"
    for company in companies:
        code = _text(company.get("company_code")) or "unknown-company"
        mapping_id = _text(company.get("mapping_id")) or "unknown-mapping"
        lines.extend([f"### {code} / {mapping_id}", "", header, separator])
        layers = company.get("layers")
        layers = layers if isinstance(layers, Mapping) else {}
        for layer_id in LAYER_IDS:
            dimensions = layers.get(layer_id)
            dimensions = dimensions if isinstance(dimensions, Mapping) else {}
            cells = [
                _cell_value(dimensions.get(dimension_id))
                for dimension_id in DIMENSION_IDS
            ]
            lines.append(f"| {layer_id} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def _render_gaps(companies: Sequence[Mapping]) -> list[str]:
    lines = ["## 证据缺口", ""]
    count = 0
    for company in companies:
        for gap in company.get("gaps") or ():
            if not isinstance(gap, Mapping) or gap.get("status") == "satisfied":
                continue
            count += 1
            lines.append(
                "- "
                f"{_text(company.get('company_code')) or 'unknown-company'} / "
                f"{_text(company.get('mapping_id')) or 'unknown-mapping'} / "
                f"{_text(gap.get('requirement_id'))}: {_text(gap.get('status'))}"
            )
    if not count:
        lines.append("- 无")
    lines.append("")
    return lines


def _render_actions(companies: Sequence[Mapping]) -> list[str]:
    lines = ["## 下一步行动", ""]
    count = 0
    for company in companies:
        for gap in company.get("gaps") or ():
            if not isinstance(gap, Mapping):
                continue
            action = _text(gap.get("next_action"))
            if not action or action == "none":
                continue
            count += 1
            lines.append(
                f"- {_text(company.get('company_code')) or 'unknown-company'} / "
                f"{_text(company.get('mapping_id')) or 'unknown-mapping'} / "
                f"{_text(gap.get('requirement_id')) or 'unknown-requirement'}: "
                f"{action}"
            )
    if not count:
        lines.append("- 无")
    lines.append("")
    return lines


def render_evidence_report(result: EvidenceRunResult) -> str:
    """Render pending evidence conservatively and each matrix cell independently."""

    companies = tuple(result.companies)
    lines = [
        f"# 产业链证据编排报告：{_text(result.chain_id)}",
        "",
        f"- 截止日：{result.as_of_date.isoformat()}",
        f"- 模式：{result.mode}",
        f"- 候选数：{result.candidate_count}",
        f"- 证据需求数：{result.requirement_count}",
        f"- 待审核事实：{result.pending_facts}",
        f"- 已审核事实：{result.approved_facts}",
        f"- 顶层仓储/评分变更调用数：{result.writes}",
        f"- 网络请求：{result.network_requests}",
        "",
    ]
    lines.extend(
        _render_fact_section("## 已审核事实", companies, "approved", label="已审核")
    )
    lines.extend(
        _render_fact_section("## 待审核事实", companies, "pending", label="待审核")
    )
    lines.extend(
        _render_fact_section("## 已拒绝事实", companies, "rejected", label="已拒绝")
    )
    lines.extend(_render_gaps(companies))
    lines.extend(_render_actions(companies))
    lines.extend(_render_matrix(companies))

    lines.extend(["## 四池", "", "| 池 | 数量 |", "| --- | ---: |"])
    for pool in ("A", "B", "C", "D"):
        lines.append(f"| {pool} | {int(result.pool_counts.get(pool, 0))} |")
    lines.extend([f"", f"- 池转移数：{result.pool_transitions}", ""])

    lines.extend(
        [
            "## AF 搜索",
            "",
            "| 指标 | 数量 |",
            "| --- | ---: |",
            f"| local_hits | {result.local_hits} |",
            f"| official_discovery_hits | {result.official_discovery_hits} |",
            f"| official_gap_hits | {result.official_gap_hits} |",
            "",
            "## 数据限制",
            "",
        ]
    )
    if result.data_limitations:
        lines.extend(f"- {_text(value)}" for value in result.data_limitations)
    else:
        lines.append("- 无已知限制")
    if result.failed_tasks:
        lines.extend(
            ["", "### 失败任务", ""]
            + [f"- {_text(value)}" for value in result.failed_tasks]
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "CELL_STATUSES",
    "DIMENSION_IDS",
    "LAYER_IDS",
    "render_evidence_report",
]
