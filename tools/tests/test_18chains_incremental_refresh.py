import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "run_18chains_incremental_refresh.py"
_SPEC = importlib.util.spec_from_file_location("run_18chains_incremental_refresh", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def test_pipeline_steps_run_data_before_decomposition():
    steps = module.build_pipeline_steps(days=30, pg_url="postgresql://x")
    names = [step.name for step in steps]

    assert names.index("sync_tushare_daily_kline") < names.index("backfill_all_business_tag_mappings")
    assert names.index("sync_announcements") < names.index("backfill_all_business_tag_mappings")
    assert names.index("backfill_all_business_tag_mappings") < names.index("backfill_existing_evidence_events")
    assert names.index("backfill_existing_evidence_events") < names.index("refresh_stage_transitions")


def test_step_runner_records_errors_and_continues():
    calls = []

    def fail_step():
        calls.append("fail")
        raise RuntimeError("boom")

    def ok_step():
        calls.append("ok")
        return {"written": 1}

    results = module.run_steps([
        module.PipelineStep("fail", fail_step),
        module.PipelineStep("ok", ok_step),
    ])

    assert calls == ["fail", "ok"]
    assert results[0]["status"] == "error"
    assert results[1]["status"] == "ok"


def test_acceptance_summary_requires_mappings_and_evidence():
    summary = module.build_acceptance_summary({
        "mapping_count": 2199,
        "chain_count": 18,
        "raw_docs": 2000,
        "facts": 2000,
        "l8_status": 800,
        "score_rows": 100,
    })

    assert summary["accepted"] is True
    assert summary["checks"]["chain_count"]["pass"] is True
    assert summary["checks"]["facts"]["pass"] is True


def test_expected_financial_period_respects_reporting_lag():
    assert str(module.expected_financial_period("2026-07-03")) == "2026-03-31"
    assert str(module.expected_financial_period("2026-09-20")) == "2026-06-30"


def test_finance_sync_can_skip_when_table_is_current():
    assert module.should_skip_finance_sync("2026-03-31", "2026-07-03") is True
    assert module.should_skip_finance_sync("2025-12-31", "2026-07-03") is False


def test_callable_runner_captures_noisy_stdout_and_stderr():
    def noisy():
        print("x" * 5000)
        print("err" * 2000, file=sys.stderr)
        return {"status": "ok", "written": 1}

    payload = module.run_callable_with_captured_output(noisy)

    assert payload["written"] == 1
    assert len(payload["stdout_tail"]) <= 4000
    assert len(payload["stderr_tail"]) <= 4000
