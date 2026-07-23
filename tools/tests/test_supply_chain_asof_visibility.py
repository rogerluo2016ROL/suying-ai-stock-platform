"""as-of 可见性规则单测:构造 reviewed_at/approved_date 在评分日 D 前后的行,断言可见性。"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


backfill = _load("backfill_supply_chain_expectation_gap_history")
register = _load("register_supply_chain_expectation_gap_model")


D1 = date(2026, 1, 5)
D2 = date(2026, 3, 20)
D3 = date(2026, 5, 20)
TRADE_DATES = [D1, D2, D3]


def _mapping() -> dict:
    return {
        "mapping_id": "M1",
        "code": "000001.SZ",
        "base_code": "000001",
        "chain_id": "chain_x",
        "tag_name": "测试标签",
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "listed_date": None,
        "is_st": 0,
    }


def _event(approved_date: date | None) -> dict:
    return {
        "mapping_id": "M1",
        "event_id": "E1",
        "code": "000001",
        "title": "订单落地",
        "evidence_type": "order",
        "impact_dimensions": ["growth"],
        "confidence": 0.8,
        "event_date": date(2025, 12, 1),
        "approved_date": approved_date,
    }


def _build(events, monitors, stages, as_of_strict):
    return backfill._build_scores_for_mapping(
        _mapping(),
        TRADE_DATES,
        {("000001", day) for day in TRADE_DATES},
        {("000001", day): None for day in TRADE_DATES},
        events,
        monitors,
        stages,
        {},
        as_of_strict=as_of_strict,
    )


def _gap_detail(gap_rows, day) -> dict:
    row = next(item for item in gap_rows if item["trade_date"] == day.isoformat())
    return json.loads(row["score_detail"])


def test_event_visible_only_after_approval_date_in_strict_mode() -> None:
    # 事件发生于 2025-12-01,但 2026-03-01 才审批通过:
    # D1(01-05) 不可见,D2(03-20)/D3 可见。
    _, gap_rows = _build([_event(date(2026, 3, 1))], [], [], as_of_strict=True)
    assert _gap_detail(gap_rows, D1)["approved_evidence_count"] == 0
    assert _gap_detail(gap_rows, D2)["approved_evidence_count"] == 1
    assert _gap_detail(gap_rows, D3)["approved_evidence_count"] == 1


def test_event_visible_by_event_date_in_lookahead_mode() -> None:
    # lookahead 对比模式沿用 event_date:D1 即可见(未来函数,仅对比用)。
    _, gap_rows = _build([_event(date(2026, 3, 1))], [], [], as_of_strict=False)
    assert _gap_detail(gap_rows, D1)["approved_evidence_count"] == 1


def test_event_with_null_approved_date_falls_back_to_event_date() -> None:
    # created_at/reviewed_at 均缺失时兜底到 event_date(见 _load_events 兜底链)。
    _, gap_rows = _build([_event(None)], [], [], as_of_strict=True)
    assert _gap_detail(gap_rows, D1)["approved_evidence_count"] == 1


def test_monitor_counts_use_rolling_60d_window_in_strict_mode() -> None:
    monitors = [
        {"mapping_id": "M1", "claim_source_type": "broker_report", "claim_date": date(2026, 1, 1)},
        {"mapping_id": "M1", "claim_source_type": "broker_report", "claim_date": date(2026, 2, 15)},
    ]
    _, gap_rows = _build([], monitors, [], as_of_strict=True)
    # D1(01-05):窗口 [2025-11-06, 01-05] → 只有 01-01 的 claim。
    assert _gap_detail(gap_rows, D1)["monitor_counts"] == {"broker_report": 1}
    # D2(03-20):窗口 [01-19, 03-20] → 01-01 过期,只剩 02-15。
    assert _gap_detail(gap_rows, D2)["monitor_counts"] == {"broker_report": 1}
    # D3(05-20):窗口 [03-21, 05-20] → 全部过期。
    assert _gap_detail(gap_rows, D3)["monitor_counts"] == {}


def test_monitor_counts_accumulate_in_lookahead_mode() -> None:
    monitors = [
        {"mapping_id": "M1", "claim_source_type": "broker_report", "claim_date": date(2026, 1, 1)},
        {"mapping_id": "M1", "claim_source_type": "broker_report", "claim_date": date(2026, 2, 15)},
    ]
    _, gap_rows = _build([], monitors, [], as_of_strict=False)
    assert _gap_detail(gap_rows, D3)["monitor_counts"] == {"broker_report": 2}


def test_stage_visible_only_after_approval_date_in_strict_mode() -> None:
    stage = {
        "mapping_id": "M1",
        "trade_date": date(2025, 12, 1),
        "research_stage": "R4",
        "commercialization_stage": "C2",
        "approved_date": date(2026, 4, 1),
    }
    three_rows, _ = _build([], [], [stage], as_of_strict=True)
    by_date = {row["trade_date"]: row["stage_score"] for row in three_rows}
    assert by_date[D1.isoformat()] == 0.0
    assert by_date[D2.isoformat()] == 0.0
    assert by_date[D3.isoformat()] == 60.0  # max(R4=60, C2=40)


def test_stage_visible_by_trade_date_in_lookahead_mode() -> None:
    stage = {
        "mapping_id": "M1",
        "trade_date": date(2025, 12, 1),
        "research_stage": "R4",
        "commercialization_stage": "C2",
        "approved_date": date(2026, 4, 1),
    }
    three_rows, _ = _build([], [], [stage], as_of_strict=False)
    by_date = {row["trade_date"]: row["stage_score"] for row in three_rows}
    assert by_date[D1.isoformat()] == 60.0


def test_strict_mode_marks_score_detail_version() -> None:
    _, gap_rows = _build([], [], [], as_of_strict=True)
    detail = _gap_detail(gap_rows, D1)
    assert detail["as_of_strict"] is True
    assert detail["monitor_window_days"] == 60
    assert detail["version"].endswith("strict")


class _FakeCursor:
    """记录 fetch_picks 下发的 SQL 与参数,返回空结果集。"""

    def __init__(self) -> None:
        self.queries: list[tuple[str, tuple]] = []

    def execute(self, query, params=None):
        self.queries.append((query, tuple(params or ())))

    def fetchall(self):
        return []


def test_fetch_picks_uses_asof_reassessment_join_by_default() -> None:
    cur = _FakeCursor()
    register.fetch_picks(cur, "2026-07-10", 30, 8.0)
    query, params = cur.queries[0]
    assert "DISTINCT ON (mapping_id)" in query
    assert "assessment_date <= %s" in query
    assert "SELECT max(assessment_date)" not in query
    # as-of 分支参数: (join 截止日, score_date, statuses, min_gap, top_n)
    assert params[0] == "2026-07-10"
    assert params[1] == "2026-07-10"
    assert sorted(params[2]) == ["strong_confirmed", "watch_review"]
    assert params[3] == 8.0
    assert params[4] == 30


def test_fetch_picks_lookahead_mode_keeps_global_latest_join() -> None:
    cur = _FakeCursor()
    register.fetch_picks(cur, "2026-07-10", 30, 8.0, allow_lookahead=True)
    query, params = cur.queries[0]
    assert "SELECT max(assessment_date)" in query
    assert "DISTINCT ON" not in query
    assert params[0] == "2026-07-10"


def test_fetch_picks_min_reassessment_overrides_status_whitelist() -> None:
    cur = _FakeCursor()
    register.fetch_picks(
        cur, "2026-07-10", 30, 8.0,
        min_reassessment=["strong_confirmed", "watch_review", "manual_review"],
    )
    _, params = cur.queries[0]
    assert sorted(params[2]) == ["manual_review", "strong_confirmed", "watch_review"]


def test_parse_min_reassessment_default_and_validation() -> None:
    assert sorted(register.parse_min_reassessment(None)) == ["strong_confirmed", "watch_review"]
    assert register.parse_min_reassessment("manual_review, watch_review") == ["manual_review", "watch_review"]
    try:
        register.parse_min_reassessment("not_a_status")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown status")
