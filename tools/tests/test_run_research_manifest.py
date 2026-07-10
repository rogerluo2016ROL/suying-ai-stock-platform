import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("run_research_pipeline", ROOT / "tools/run_research_pipeline.py")
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


def _args(**overrides):
    values = dict(official=False, strict_timeline=False, data_snapshot_id="", cutoff_time="",
                  model_version="v1", cost_bps=14)
    values.update(overrides)
    return argparse.Namespace(**values)


def test_research_manifest_records_dirty_non_strict_run(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": True})
    manifest = pipeline.build_run_manifest(
        args=_args(), model_key="bi_trend_launch", run_id="RUN-1", trade_date="2026-07-10",
        result={"status": "ok", "picks": [{"code": "000001"}]},
        parameters={"top_n": 20}, artifacts=[tmp_path / "result.json"],
    )
    assert manifest.official is False
    assert manifest.working_tree_dirty is True
    assert manifest.strict_timeline is False


def test_official_manifest_requires_clean_worktree(monkeypatch):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": True})
    try:
        pipeline.build_run_manifest(
            args=_args(official=True, strict_timeline=True, data_snapshot_id="DS-1",
                       cutoff_time="2026-07-10T14:30:00"),
            model_key="x", run_id="RUN-2", trade_date="2026-07-10", result={"picks": []},
            parameters={}, artifacts=[],
        )
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("dirty official run must exit 2")


def test_manifest_hashes_are_deterministic(monkeypatch):
    monkeypatch.setattr(pipeline, "_git_state", lambda: {"commit": "abc123", "dirty": False})
    kwargs = dict(args=_args(), model_key="x", run_id="RUN-3", trade_date="2026-07-10",
                  result={"picks": [{"code": "000002"}, {"code": "000001"}]},
                  parameters={"b": 2, "a": 1}, artifacts=[])
    one = pipeline.build_run_manifest(**kwargs)
    two = pipeline.build_run_manifest(**kwargs)
    assert one.parameters_hash == two.parameters_hash
    assert one.universe_hash == two.universe_hash
