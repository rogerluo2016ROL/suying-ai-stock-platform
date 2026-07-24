from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parents[1]))


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        self.connection.executions.append((normalized, params))
        if "FROM supply_chain_hierarchy_nodes" in normalized:
            self.rows = self.connection.nodes
        elif "FROM business_tag_mapping" in normalized:
            self.rows = self.connection.mappings

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, nodes, mappings):
        self.nodes = nodes
        self.mappings = mappings
        self.executions = []

    def cursor(self):
        return FakeCursor(self)


def test_audit_reports_l1_l8_conflicts_and_unapproved_verified_mapping():
    from embodied_refresh.audit import audit_chain

    nodes = [
        ("EI-L1-ROOT", None, "L1", "具身智能", {}, "embodied"),
        ("EI-L5-HARMONIC", "EI-L1-ROOT", "L5", "谐波减速器", {}, "embodied"),
        ("18C-L5-HARMONIC", "EI-L1-ROOT", "L5", " 谐波-减速器 ", {}, "embodied"),
        ("EI-L8-EVENT", "MISSING-PARENT", "L8", "量产证据", {}, "embodied"),
        ("EI-L4-EMPTY", "EI-L1-ROOT", "L4", "", {}, "embodied"),
    ]
    mappings = [
        ("map-ok", "300503", "EI-L5-HARMONIC", "verified", ["ev-approved"], ["approved"]),
        ("map-bad", "000001", "MISSING-NODE", "candidate", [], []),
        ("map-review", "002896", "EI-L5-HARMONIC", "verified", ["ev-pending"], ["pending_review"]),
    ]
    audit = audit_chain(FakeConnection(nodes, mappings), "run-4")

    assert set(audit.coverage_by_layer) == {f"L{i}" for i in range(1, 9)}
    assert audit.coverage_by_layer["L2"] == 0
    assert audit.empty_core_node_ids == ["EI-L4-EMPTY"]
    assert audit.duplicate_groups[0].canonical_node_id == "EI-L5-HARMONIC"
    assert audit.duplicate_groups[0].duplicate_node_ids == ("18C-L5-HARMONIC",)
    assert audit.orphan_node_ids == ["EI-L8-EVENT"]
    assert audit.mappings_with_missing_nodes == ["map-bad"]
    assert audit.verified_with_unapproved_evidence == ["map-review"]


def test_verified_mapping_reports_when_only_some_evidence_ids_join():
    from embodied_refresh.audit import audit_chain

    nodes = [("EI-L5-HARMONIC", None, "L5", "谐波减速器", {}, "embodied")]
    mappings = [
        (
            "map-partial",
            "300503",
            "EI-L5-HARMONIC",
            "verified",
            ["ev-approved", "ev-missing"],
            ["approved"],
            1,
        )
    ]

    audit = audit_chain(FakeConnection(nodes, mappings), "run-4")

    assert audit.verified_with_unapproved_evidence == ["map-partial"]


def test_semantic_duplicate_normalization_removes_common_separators():
    from embodied_refresh.audit import audit_chain

    nodes = [
        ("EI-L5-HARMONIC", None, "L5", "harmonic reducer", {}, "embodied"),
        ("18C-L5-HARMONIC", None, "L5", "harmonic_reducer", {}, "embodied"),
        ("ALT-L5-HARMONIC", None, "L5", "harmonic/reducer", {}, "embodied"),
        ("ALT2-L5-HARMONIC", None, "L5", "harmonic-reducer", {}, "embodied"),
    ]

    audit = audit_chain(FakeConnection(nodes, []), "run-4")

    assert len(audit.duplicate_groups) == 1
    assert audit.duplicate_groups[0].canonical_node_id == "EI-L5-HARMONIC"
    assert set(audit.duplicate_groups[0].duplicate_node_ids) == {
        "18C-L5-HARMONIC", "ALT-L5-HARMONIC", "ALT2-L5-HARMONIC"
    }


def test_missing_revenue_is_not_zero_and_available_weights_are_normalized():
    from embodied_refresh.audit import rank_node_leaders

    ranked = rank_node_leaders([
        {
            "code": "300503", "company_name": "昊志机电", "node_id": "harmonic",
            "mapping_status": "verified", "business_authenticity": 80,
            "commercialization": 80, "technology_moat": 80,
            "revenue_realization": None, "node_importance": 80,
            "evidence_quality": 80, "competition_position": 80,
        },
        {
            "code": "000001", "company_name": "对照", "node_id": "sensor",
            "mapping_status": "verified", **{name: 70 for name in (
                "business_authenticity", "commercialization", "technology_moat",
                "revenue_realization", "node_importance", "evidence_quality",
                "competition_position",
            )},
        },
    ])

    assert ranked[0].code == "300503"
    assert ranked[0].dimension_scores["revenue_realization"] is None
    assert ranked[0].score == 80
    assert [row.code for row in ranked.formal_top3] == ["300503", "000001"]


def test_formal_and_watch_top3_are_evidence_constrained_and_labeled():
    from embodied_refresh.audit import rank_node_leaders

    candidates = []
    for index, status in enumerate(["verified"] * 4 + ["candidate"] * 4):
        candidates.append({
            "code": f"{index:06d}", "company_name": f"C{index}",
            "node_id": f"N{index}", "mapping_status": status,
            "business_authenticity": 100 - index,
        })
    ranked = rank_node_leaders(candidates)

    assert len(ranked.formal_top3) == 3
    assert all(row.candidate_label == "formal" for row in ranked.formal_top3)
    assert len(ranked.watch_top3) == 3
    assert all(row.candidate_label == "candidate" for row in ranked.watch_top3)
    assert {row.mapping_status for row in ranked.formal_top3} == {"verified"}
    assert {row.mapping_status for row in ranked.watch_top3} == {"candidate"}


def test_watch_pool_excludes_rejected_and_has_stable_tie_order():
    from embodied_refresh.audit import rank_node_leaders

    ranked = rank_node_leaders([
        {"code": "000003", "node_id": "N3", "mapping_status": "rejected"},
        {"code": "000002", "node_id": "N2", "mapping_status": "weak_evidence", "business_authenticity": 80},
        {"code": "000001", "node_id": "N1", "mapping_status": "pending_review", "business_authenticity": 80},
        {"code": "000000", "node_id": "N0", "mapping_status": "candidate", "business_authenticity": 80},
        {"code": "000004", "node_id": "N4", "mapping_status": "unknown", "business_authenticity": 100},
    ])

    assert [row.code for row in ranked.watch_top3] == ["000000", "000001", "000002"]


def test_multiple_tags_do_not_stack_add_score():
    from embodied_refresh.audit import rank_node_leaders

    ranked = rank_node_leaders([
        {"code": "300503", "node_id": "harmonic", "mapping_status": "verified", "business_authenticity": 80},
        {"code": "300503", "node_id": "servo", "mapping_status": "verified", "business_authenticity": 60},
    ])

    assert len([row for row in ranked if row.code == "300503"]) == 1
    assert ranked[0].score == 80


def test_candidate_with_no_available_dimension_is_rejected():
    import pytest
    from embodied_refresh.audit import rank_node_leaders

    with pytest.raises(ValueError, match="available scoring dimension"):
        rank_node_leaders([{"code": "300503", "mapping_status": "verified"}])


def test_dimension_scores_mapping_is_supported_without_filling_missing_values():
    from embodied_refresh.audit import rank_node_leaders

    ranked = rank_node_leaders([{
        "code": "300503",
        "mapping_status": "candidate",
        "dimension_scores": {"business_authenticity": 90, "revenue_realization": None},
    }])

    assert ranked.watch_top3[0].score == 90
    assert ranked.watch_top3[0].dimension_scores["revenue_realization"] is None
