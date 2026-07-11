"""Markdown reporting contracts for evidence orchestration results."""

from __future__ import annotations

from datetime import date

from supply_chain_evidence_orchestrator import EvidenceRunResult
from supply_chain_evidence_report import DIMENSION_IDS, LAYER_IDS, render_evidence_report


def result_with_company(company: dict) -> EvidenceRunResult:
    return EvidenceRunResult(
        chain_id="dexterous_hand",
        as_of_date=date(2026, 7, 9),
        mode="collect",
        candidate_count=1,
        requirement_count=2,
        local_hits=1,
        official_discovery_hits=2,
        official_gap_hits=3,
        inserted_documents=1,
        duplicate_documents=0,
        pending_facts=1,
        approved_facts=0,
        failed_tasks=(),
        pool_counts={"A": 0, "B": 0, "C": 1, "D": 0},
        pool_transitions=0,
        writes=3,
        network_requests=5,
        data_limitations=("official_ir_publish_time_unknown",),
        companies=(company,),
    )


def test_report_labels_pending_evidence_as_pending_not_confirmed():
    result = result_with_company(
        {
            "company_code": "688001",
            "company_name": "测试公司",
            "mapping_id": "m1",
            "pending": [
                {"fact_id": "pending-order", "summary": "订单线索待人工核验"}
            ],
        }
    )

    markdown = render_evidence_report(result)

    assert "待审核" in markdown
    assert "已确认订单" not in markdown
    assert "pending-order" in markdown


def test_report_has_exact_eight_dimensions_and_eight_layers():
    markdown = render_evidence_report(
        result_with_company({"company_code": "688001", "mapping_id": "m1"})
    )

    assert DIMENSION_IDS == (
        "function_value",
        "technology_route",
        "physical_bom",
        "value_pool",
        "competition_moat",
        "supply_demand_cycle",
        "evidence_validation",
        "market_expectation",
    )
    assert LAYER_IDS == ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")
    header = next(line for line in markdown.splitlines() if line.startswith("| 层级 |"))
    assert header == "| 层级 | " + " | ".join(DIMENSION_IDS) + " |"
    for layer_id in LAYER_IDS:
        assert f"| {layer_id} |" in markdown


def test_one_dimension_never_changes_another_cell_on_same_layer():
    markdown = render_evidence_report(
        result_with_company(
            {
                "company_code": "688001",
                "mapping_id": "m1",
                "layers": {
                    "L1": {
                        "physical_bom": {
                            "status": "known",
                            "evidence_ids": ["bom-1"],
                        }
                    }
                },
            }
        )
    )

    row = next(line for line in markdown.splitlines() if line.startswith("| L1 |"))
    cells = [part.strip() for part in row.strip("|").split("|")]
    assert cells[1] == "unknown"  # function_value
    assert cells[2] == "unknown"  # technology_route
    assert cells[3] == "known (bom-1)"
    assert cells[4:] == ["unknown"] * 5


def test_report_contains_all_decision_sections_four_pools_af_and_limitations():
    markdown = render_evidence_report(
        result_with_company(
            {
                "company_code": "688001",
                "mapping_id": "m1",
                "approved": [{"fact_id": "a1", "summary": "已审核产品证据"}],
                "pending": [{"fact_id": "p1", "summary": "待审核线索"}],
                "rejected": [{"fact_id": "r1", "summary": "已驳回线索"}],
                "gaps": [
                    {
                        "requirement_id": "customer_validation",
                        "status": "missing",
                    }
                ],
                "next_actions": ["collect_customer_validation"],
            }
        )
    )

    for heading in (
        "## 已审核事实",
        "## 待审核事实",
        "## 已拒绝事实",
        "## 证据缺口",
        "## 下一步行动",
        "## 8 层 × 8 维矩阵",
        "## 四池",
        "## AF 搜索",
        "## 数据限制",
    ):
        assert heading in markdown
    for pool in ("A", "B", "C", "D"):
        assert f"| {pool} |" in markdown
    assert "official_discovery_hits | 2" in markdown
    assert "official_ir_publish_time_unknown" in markdown
