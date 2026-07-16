from datetime import date

import pytest

from run_embodied_daily_refresh import EmbodiedRefreshOrchestrator, build_ranked_snapshot, identify_source_nodes


class FakeRepository:
    def __init__(self, events):
        self.events = events

    def begin_run(self, run_date, mode):
        self.events.append("begin")
        return type("Run", (), {"run_id": "run-1"})()

    def load_cursors(self):
        self.events.append("load_cursors")
        return {"announcement": "old"}

    def load_success_baseline(self, run_id):
        self.events.append("baseline")
        return {"status": "success", "mappings": []}

    def save_changes(self, changes):
        self.events.append("persist")
        return len(changes)

    def save_snapshot(self, run_id, snapshot):
        self.events.append("snapshot")

    def save_cursor(self, source, cursor, run_id):
        self.events.append(f"cursor:{source}")

    def finish_run(self, run_id, status, summary):
        self.events.append(f"finish:{status}")


def make_orchestrator(events, *, mapping_error=False):
    repository = FakeRepository(events)

    def refresh(cursors, as_of_date):
        events.append("refresh")
        return type("Refresh", (), {
            "rows": {"announcement": [{"content": "x"}]},
            "next_cursors": {"announcement": "new"},
            "errors": {"research": "unavailable"},
        })()

    def normalize(rows):
        events.append("normalize")
        return ["evidence"]

    def apply(evidence, run_id, as_of_date, *, persist=True):
        events.append("mapping")
        if mapping_error:
            raise RuntimeError("mapping failed")
        return ["mapped"]

    def rollback():
        events.append("rollback")

    def audit(run_id, mappings, mode):
        events.append("audit")
        return {"run_id": run_id, "mappings": mappings}

    def diff(baseline, snapshot):
        events.append("diff")
        return [{"payload": {"priority": "P3"}}]

    def deliver(*_args):
        events.append("deliver")

    return EmbodiedRefreshOrchestrator(
        repository=repository,
        refresh_sources=refresh,
        normalize_evidence=normalize,
        apply_mappings=apply,
        rollback_mappings=rollback,
        audit_and_rank=audit,
        diff_baseline=diff,
        deliver_changes=deliver,
    )


def test_dry_run_never_writes_or_sends():
    events = []
    result = make_orchestrator(events).run(mode="dry-run", as_of_date="2026-07-16")

    assert result.persisted is False
    assert result.delivery_attempted is False
    assert "begin" not in events
    assert "persist" not in events
    assert "mapping" in events
    assert result.snapshot["mappings"] == ["mapped"]


def test_apply_without_prior_success_diffs_against_empty_success_baseline():
    events = []
    orchestrator = make_orchestrator(events)
    orchestrator.repository.load_success_baseline = lambda _run_id: None
    seen = []
    orchestrator.diff_baseline = lambda baseline, snapshot: seen.append(baseline) or [{"payload": {"priority": "P3"}}]

    result = orchestrator.run(mode="apply", as_of_date="2026-07-17")

    assert seen == [{"status": "success", "mappings": []}]
    assert result.change_count == 1


def test_apply_obeys_transaction_sequence_and_only_advances_successful_cursors():
    events = []
    result = make_orchestrator(events).run(mode="apply", as_of_date=date(2026, 7, 16))

    assert result.persisted is True
    assert result.delivery_attempted is False
    assert events == [
        "begin", "load_cursors", "refresh", "normalize", "mapping", "audit",
        "baseline", "diff", "persist", "snapshot", "cursor:announcement", "finish:success",
    ]


def test_mapping_failure_rolls_back_and_never_persists_or_delivers():
    events = []
    with pytest.raises(RuntimeError, match="mapping failed"):
        make_orchestrator(events, mapping_error=True).run(mode="apply", as_of_date="2026-07-16")

    assert events == ["begin", "load_cursors", "refresh", "normalize", "mapping", "rollback", "finish:failed"]
    assert "persist" not in events
    assert "deliver" not in events


def test_audit_mode_is_strictly_read_only():
    events = []
    result = make_orchestrator(events).run(mode="audit", as_of_date="2026-07-16")

    assert result.persisted is False
    assert events == ["audit"]


def test_partial_delivery_status_is_not_overwritten_with_success():
    events = []
    orchestrator = make_orchestrator(events)
    orchestrator.diff_baseline = lambda *_: [{"payload": {"priority": "P1"}}]
    orchestrator.deliver_changes = lambda *_: type("Summary", (), {
        "status": "data_success_delivery_incomplete", "confirmed": 1, "pending": 2,
    })()

    result = orchestrator.run(mode="apply", as_of_date="2026-07-16", send_feishu=True)

    assert result.status == "data_success_delivery_incomplete"
    assert events[-1] == "finish:data_success_delivery_incomplete"


def test_real_five_source_shapes_are_identified_without_node_id():
    rows = {
        "announcement": [{"id": "a", "ts_code": "000001.SZ", "title": "伺服电机量产", "content": "客户验收"}],
        "interact_qa": [{"id": "q", "code": "000002", "question": "是否生产减速器", "answer": "公司减速器已经小批量交付"}],
        "research": [{"id": "r", "code": "000003", "title": "力传感器龙头", "abstract": "收入增长"}],
        "profile": [{"id": "p", "ts_code": "000004.SZ", "main_business": "机器视觉解决方案", "business_scope": "软件"}],
        "main_business": [{"id": "m", "ts_code": "000005.SZ", "bz_item": "灵巧手", "bz_sales": "1000"}],
    }
    nodes = [
        {"node_id": "servo", "display_name": "伺服电机", "metadata": {}},
        {"node_id": "reducer", "display_name": "减速器", "metadata": {}},
        {"node_id": "force", "display_name": "力传感器", "metadata": {}},
        {"node_id": "vision", "display_name": "机器视觉", "metadata": {}},
        {"node_id": "hand", "display_name": "灵巧手", "metadata": {}},
    ]

    identified, conflicts = identify_source_nodes(rows, nodes)

    assert len(identified) == 5
    assert conflicts == []


def test_interact_question_keyword_without_answer_confirmation_is_rejected():
    rows = {"interact_qa": [{"id": "q", "code": "002765", "question": "公司机器人关节是否有订单", "answer": "请关注后续公告"}]}
    nodes = [{"node_id": "joint", "display_name": "机器人关节", "metadata": {}}]
    assert identify_source_nodes(rows, nodes) == ([], [])


def test_generic_perception_term_does_not_independently_identify_node():
    rows = {"profile": [{"id": "p", "code": "002457", "main_business": "城市综合感知系统"}]}
    nodes = [{"node_id": "perception", "display_name": "感知系统", "metadata": {}}]
    assert identify_source_nodes(rows, nodes) == ([], [])


def test_non_stock_nan_code_is_rejected():
    rows = {"research": [{"id": "r", "code": "nan", "title": "机器人关节量产"}]}
    nodes = [{"node_id": "joint", "display_name": "机器人关节", "metadata": {}}]
    assert identify_source_nodes(rows, nodes) == ([], [])


def test_ambiguous_node_text_goes_to_conflict_not_mapping_evidence():
    rows = {"announcement": [{"id": "a", "code": "000001", "title": "伺服电机与减速器合作"}]}
    nodes = [
        {"node_id": "servo", "display_name": "伺服电机", "metadata": {}},
        {"node_id": "reducer", "display_name": "减速器", "metadata": {}},
    ]

    identified, conflicts = identify_source_nodes(rows, nodes)

    assert identified == []
    assert conflicts[0]["node_ids"] == ["reducer", "servo"]


def test_runtime_snapshot_ranks_persisted_candidates_and_handles_empty_pool():
    from embodied_refresh.audit import ChainAudit
    audit = ChainAudit("run-1", {}, [], [], [], [], [])
    empty = build_ranked_snapshot("run-1", audit, [], None)
    ranked = build_ranked_snapshot("run-1", audit, [{
        "code": "000001", "company_name": "甲公司", "node_id": "servo",
        "mapping_status": "verified", "business_authenticity": 90,
    }], None)

    assert empty["leaders"] == []
    assert ranked["formal_top3"][0]["code"] == "000001"
    assert ranked["formal_top3"][0]["rank"] == 1
