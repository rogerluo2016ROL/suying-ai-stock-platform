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
    assert changes[0].payload["before_status"] == "candidate"
    assert changes[0].payload["after_status"] == "verified"
    assert changes[0].payload["before_stage"] == "样品"
    assert changes[0].payload["after_stage"] == "小批量"
    assert changes[0].change_fingerprint
    rerun = diff_snapshots(previous, {**current, "run_id": "run-rerun"})
    assert rerun[0].change_fingerprint == changes[0].change_fingerprint


def test_diff_snapshots_rejects_failed_baseline():
    with pytest.raises(ValueError, match="success"):
        diff_snapshots({"run_id": "failed", "status": "failed", "mappings": []}, {"run_id": "now", "mappings": []})


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
                    "score": score, "priority": priority,
                }]},
            )
        )
    batch = ChangeBatch(
        changes=changes,
        cutoff_time="2026-07-17 15:00:00 Asia/Shanghai",
        coverage_before={"L1": 1, "L8": 0},
        coverage_after={"L1": 1, "L8": 1},
        top3_entries=["公司000001：新增确证"],
        top3_exits=["旧龙头：证据过期"],
    )
    digest = render_change_digest(batch)

    assert digest is not None
    assert digest.index("000001") < digest.index("000002")
    assert "000003" not in digest
    for text in ("2026-07-17 15:00:00", "无 → verified", "无 → 小批量", "交易所公告", "2026-07-17", "订单落地待跟踪", "L8: 0→1", "Top3进入", "Top3退出"):
        assert text in digest
    assert "重要性分数衡量产业证据变动，不表示股价上涨概率。" in digest


def test_p3_only_batch_has_no_outbound_message():
    change = diff_snapshots(
        {"run_id": "old", "status": "success", "mappings": []},
        {"run_id": "new", "mappings": [{"code": "000003", "node_id": "n", "score": 49, "priority": "P3"}]},
    )[0]
    assert render_change_digest(ChangeBatch([change], "2026-07-17 15:00")) is None
