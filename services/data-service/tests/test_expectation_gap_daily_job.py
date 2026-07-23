"""预期差模型每日链路 job 的注册与串联行为测试。"""

from app import scheduler


def _registered_jobs(monkeypatch):
    """调 start_scheduler 但拦截事件循环与启动自检,只取注册表。"""
    monkeypatch.setattr(scheduler, "validate_pipeline_consistency", lambda: {})
    monkeypatch.setattr(scheduler, "_scheduler_loop", lambda: None)
    monkeypatch.setattr(scheduler, "run_missed_scheduled_research_tasks", lambda: None)

    class _FakeLoop:
        def create_task(self, _coro):
            return None

    monkeypatch.setattr(scheduler.asyncio, "get_event_loop", lambda: _FakeLoop())
    scheduler.start_scheduler()
    return {job["id"]: job for job in scheduler._jobs}


def test_expectation_gap_daily_job_registered(monkeypatch):
    jobs = _registered_jobs(monkeypatch)
    assert "expectation_gap_daily" in jobs
    job = jobs["expectation_gap_daily"]
    assert job["cron"] == "30 17 * * 1-5"
    assert job["fn"] is scheduler.run_supply_chain_expectation_gap_daily


def test_expectation_gap_daily_cron_matches_weekday_1730():
    from datetime import datetime

    assert scheduler._cron_match("30 17 * * 1-5", datetime(2026, 7, 23, 17, 30))   # 周四
    assert not scheduler._cron_match("30 17 * * 1-5", datetime(2026, 7, 23, 17, 31))
    assert not scheduler._cron_match("30 17 * * 1-5", datetime(2026, 7, 25, 17, 30))  # 周六


def test_expectation_gap_daily_chain_continues_after_step_failure(monkeypatch):
    """单步失败不阻断后续:refresh 抛异常时 reevaluate/snapshot 仍执行,整体 degraded。"""
    calls: list[str] = []

    class _FakeRefreshModule:
        @staticmethod
        def refresh_expectation_and_prosperity_scores(*_args, **_kwargs):
            calls.append("refresh")
            raise RuntimeError("boom")

    class _FakeReevaluateModule:
        @staticmethod
        def run(*_args, **_kwargs):
            calls.append("reevaluate")
            return {"written": 251, "review_status_counts": {"watch_review": 24}}

    class _FakeRegisterModule:
        @staticmethod
        def register_and_snapshot(*_args, **_kwargs):
            calls.append("snapshot")
            return {"snapshot_count": 19, "version_tag": "v1.0-r3"}

    import sys
    monkeypatch.setitem(sys.modules, "supply_chain_data_collection_center", _FakeRefreshModule)
    monkeypatch.setitem(sys.modules, "reevaluate_supply_chain_evidence_quality", _FakeReevaluateModule)
    monkeypatch.setitem(sys.modules, "register_supply_chain_expectation_gap_model", _FakeRegisterModule)

    result = scheduler.run_supply_chain_expectation_gap_daily()
    assert calls == ["refresh", "reevaluate", "snapshot"]
    assert result["status"] == "degraded"
    assert result["failed_steps"] == ["refresh_scores"]
    assert result["steps"]["reevaluate"]["status"] == "ok"
    assert result["steps"]["snapshot"]["snapshot_count"] == 19


def test_expectation_gap_daily_all_ok(monkeypatch):
    import sys

    class _FakeRefreshModule:
        @staticmethod
        def refresh_expectation_and_prosperity_scores(*_args, **_kwargs):
            return {"written_expectation_gap_scores": 5166}

    class _FakeReevaluateModule:
        @staticmethod
        def run(*_args, **_kwargs):
            return {"written": 251, "review_status_counts": {}}

    class _FakeRegisterModule:
        @staticmethod
        def register_and_snapshot(*_args, **_kwargs):
            return {"snapshot_count": 19, "version_tag": "v1.0-r3"}

    monkeypatch.setitem(sys.modules, "supply_chain_data_collection_center", _FakeRefreshModule)
    monkeypatch.setitem(sys.modules, "reevaluate_supply_chain_evidence_quality", _FakeReevaluateModule)
    monkeypatch.setitem(sys.modules, "register_supply_chain_expectation_gap_model", _FakeRegisterModule)

    result = scheduler.run_supply_chain_expectation_gap_daily()
    assert result["status"] == "ok"
    assert result["failed_steps"] == []
    assert result["written"] == 19
