from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).parents[1]))


from embodied_refresh.changes import (  # noqa: E402
    ChangeBatch,
    diff_snapshots,
    priority_for_score,
    render_change_digest,
    score_change,
)


@pytest.mark.parametrize(
    ("score", "priority"),
    [(85, "P0"), (84, "P1"), (70, "P1"), (69, "P2"), (50, "P2"), (49, "P3")],
)
def test_priority_boundaries(score, priority):
    assert priority_for_score(score) == priority


def test_score_change_uses_exact_six_dimensions_and_clamps():
    change = {
        "source": 100,
        "commercialization": 80,
        "mapping_change": 60,
        "business_contribution": 40,
        "node_importance": 20,
        "freshness_crosscheck": 0,
    }
    assert score_change(change) == 65
    assert change["score_factors"] == {
        "source": {"value": 100.0, "weight": 25, "points": 25.0},
        "commercialization": {"value": 80.0, "weight": 25, "points": 20.0},
        "mapping_change": {"value": 60.0, "weight": 20, "points": 12.0},
        "business_contribution": {"value": 40.0, "weight": 15, "points": 6.0},
        "node_importance": {"value": 20.0, "weight": 10, "points": 2.0},
        "freshness_crosscheck": {"value": 0.0, "weight": 5, "points": 0.0},
    }

    assert score_change({name: 200 for name in change if name != "score_factors"}) == 100


def test_any_missing_score_factor_makes_change_unscored_p3():
    change = {"source_score": 80, "commercialization_score": None}
    assert score_change(change) is None
    assert change["score_factors"]["commercialization"]["value"] is None
    assert change["score_factors"]["commercialization"]["points"] is None
    assert change["priority"] == "P3"

    empty = {}
    assert score_change(empty) is None
    assert empty["score"] is None
    assert empty["priority"] == "P3"


def test_diff_snapshots_compares_success_baseline_and_deduplicates_fingerprints():
    previous = {
        "run_id": "last-success",
        "status": "success",
        "mappings": [{"code": "000001", "node_id": "L4-a", "status": "candidate", "stage": "样品"}],
    }
    current = {
        "run_id": "run-now",
        "status": "success",
        "mappings": [
            {"code": "000001", "node_id": "L4-a", "status": "verified", "stage": "小批量", "source": "公告"},
            {"code": "000001", "node_id": "L4-a", "status": "verified", "stage": "小批量", "source": "公告"},
        ],
    }
    changes = diff_snapshots(previous, current)

    assert len(changes) == 1
    assert changes[0].change_type == "status_upgraded"
    assert changes[0].payload["change_types"] == ["status_upgraded", "commercialization_advanced"]
    assert all(row.payload["before_status"] == "candidate" for row in changes)
    assert all(row.payload["after_status"] == "verified" for row in changes)
    assert all(row.payload["before_stage"] == "样品" for row in changes)
    assert all(row.payload["after_stage"] == "小批量" for row in changes)
    assert all(row.change_fingerprint for row in changes)
    rerun = diff_snapshots(previous, {**current, "run_id": "run-rerun"})
    assert rerun[0].change_fingerprint == changes[0].change_fingerprint


def test_diff_snapshots_rejects_failed_baseline():
    with pytest.raises(ValueError, match="success"):
        diff_snapshots({"run_id": "failed", "status": "failed", "mappings": []}, {"run_id": "now", "mappings": []})


def test_diff_classifies_all_eight_business_change_types_and_node_move_once():
    previous = {"run_id": "old", "status": "success", "chain_id": "embodied", "mappings": [
        {"code": "1", "node_id": "wide", "status": "candidate"},
        {"code": "2", "node_id": "n", "status": "candidate"},
        {"code": "3", "node_id": "n", "status": "verified"},
        {"code": "4", "node_id": "n", "status": "verified", "stage": 2},
        {"code": "5", "node_id": "n", "status": "verified", "evidence_grade": "B", "evidence_event_ids": ["e1"]},
        {"code": "6", "node_id": "n", "status": "verified", "evidence_grade": "A", "evidence_event_ids": ["e1"]},
        {"code": "7", "node_id": "n", "status": "verified"},
    ]}
    current = {"run_id": "new", "chain_id": "embodied", "mappings": [
        {"code": "1", "node_id": "precise", "status": "candidate"},
        {"code": "2", "node_id": "n", "status": "verified"},
        {"code": "3", "node_id": "n", "status": "candidate"},
        {"code": "4", "node_id": "n", "status": "verified", "stage": 5},
        {"code": "5", "node_id": "n", "status": "verified", "evidence_grade": "A", "evidence_event_ids": ["e1", "e2"]},
        {"code": "6", "node_id": "n", "status": "verified", "evidence_grade": "D", "evidence_event_ids": ["e1"]},
        {"code": "7", "node_id": "n", "status": "rejected"},
        {"code": "8", "node_id": "n", "status": "candidate"},
    ]}
    changes = diff_snapshots(previous, current)
    assert {change_type for row in changes for change_type in row.payload["change_types"]} == {
        "new_candidate", "evidence_strengthened", "status_upgraded", "node_adjusted",
        "commercialization_advanced", "evidence_weakened", "status_downgraded", "mapping_invalidated",
    }
    moved = [row for row in changes if row.change_type == "node_adjusted"]
    assert len(moved) == 1
    assert (moved[0].payload["before_node_id"], moved[0].payload["after_node_id"]) == ("wide", "precise")


def test_compound_node_move_is_one_change_and_retains_all_change_types():
    factors = {f"{name}_score": 100 for name in (
        "source", "commercialization", "mapping_change", "business_contribution",
        "node_importance", "freshness_crosscheck",
    )}
    changes = diff_snapshots(
        {"status": "success", "chain_id": "embodied", "mappings": [
            {"code": "1", "node_id": "wide", "status": "candidate", "stage": 2, "evidence_event_ids": ["e1"]},
        ]},
        {"run_id": "new", "chain_id": "embodied", "mappings": [
            {"code": "1", "node_id": "precise", "status": "verified", "stage": 5,
             "evidence_grade": "A", "evidence_event_ids": ["e1", "e2"], **factors},
        ]},
    )
    assert len(changes) == 1
    assert changes[0].change_type == "node_adjusted"
    assert changes[0].payload["change_types"] == [
        "node_adjusted", "status_upgraded", "commercialization_advanced", "evidence_strengthened",
    ]
    digest = render_change_digest(ChangeBatch(changes, "2026-07-17 15:00"))
    assert digest is not None
    assert digest.count("- 1 ") == 1


def test_diff_recomputes_score_priority_and_fingerprint_ignores_volatile_metadata():
    previous = {"run_id": "old", "status": "success", "chain_id": "embodied", "mappings": []}
    row = {"code": "1", "node_id": "n", "status": "candidate", "stage": 2,
           **{f"{name}_score": 100 for name in (
               "source", "commercialization", "mapping_change", "business_contribution",
               "node_importance", "freshness_crosscheck",
           )},
           "score": 1, "priority": "P3", "updated_at": "yesterday",
           "evidence_event_ids": ["e2", "e1"]}
    first = diff_snapshots(previous, {"run_id": "new", "chain_id": "embodied", "mappings": [row]})[0]
    second = diff_snapshots(previous, {"run_id": "rerun", "chain_id": "embodied", "cursor": "x",
                                       "mappings": [{**row, "updated_at": "today"}]})[0]
    assert first.payload["score"] == 100
    assert first.payload["priority"] == "P0"
    assert first.change_fingerprint == second.change_fingerprint


def test_digest_is_deterministic_complete_and_excludes_p3():
    changes = []
    for code, score, priority in (("000002", 85, "P0"), ("000001", 85, "P0"), ("000003", 49, "P3")):
        changes.extend(
            diff_snapshots(
                {"run_id": "old", "status": "success", "mappings": []},
                {"run_id": "new", "mappings": [{
                    "code": code, "company_name": f"公司{code}", "node_id": "L4-a",
                    "status": "verified", "stage": "小批量", "source": "交易所公告",
                    "evidence_date": "2026-07-17", "remaining_risk": "订单落地待跟踪",
                    **{f"{name}_score": score for name in (
                        "source", "commercialization", "mapping_change", "business_contribution",
                        "node_importance", "freshness_crosscheck",
                    )},
                }]},
            )
        )
    batch = ChangeBatch(
        changes=changes,
        cutoff_time="2026-07-17 15:00:00 Asia/Shanghai",
        scan_size={"companies": 30, "evidence": 120},
        coverage_before={"L1": 1, "L8": 0},
        coverage_after={"L1": 1, "L8": 1},
        missing_mapping_nodes=["L6-减速器"],
        top3_entries=[{"company": "公司000001", "reason": "新增确证"}],
        top3_exits=[{"company": "旧龙头", "reason": "证据过期"}],
    )
    digest = render_change_digest(batch)

    assert digest is not None
    assert digest.index("000001") < digest.index("000002")
    assert "000003" not in digest
    for text in ("2026-07-17 15:00:00", "公司 30", "证据 120", "节点 L4-a", "无 → verified", "无 → 小批量", "交易所公告", "2026-07-17", "订单落地待跟踪", "L8: 0→1", "L6-减速器", "Top3进入", "公司000001：新增确证", "Top3退出"):
        assert text in digest
    assert "重要性分数衡量产业证据变动，不表示股价上涨概率。" in digest


def test_p3_only_batch_has_no_outbound_message():
    change = diff_snapshots(
        {"run_id": "old", "status": "success", "mappings": []},
        {"run_id": "new", "mappings": [{"code": "000003", "node_id": "n", "score": 49, "priority": "P3"}]},
    )[0]
    assert render_change_digest(ChangeBatch([change], "2026-07-17 15:00")) is None


def test_top3_structured_rows_require_reason():
    change = diff_snapshots(
        {"run_id": "old", "status": "success", "mappings": []},
        {"run_id": "new", "mappings": [{
            "code": "1", "node_id": "n",
            **{f"{name}_score": 100 for name in (
                "source", "commercialization", "mapping_change", "business_contribution",
                "node_importance", "freshness_crosscheck",
            )},
        }]},
    )[0]
    with pytest.raises(ValueError, match="reason"):
        render_change_digest(ChangeBatch([change], "2026-07-17 15:00", top3_entries=[{"company": "A"}]))
