from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import run_research_pipeline as pipeline


def test_manifest_builder_rejects_official_dirty_worktree(monkeypatch):
    def fake_check_output(cmd, **_kwargs):
        return "abc123\n" if "rev-parse" in cmd else " M dirty.py\n"
    monkeypatch.setattr(pipeline.subprocess, "check_output", fake_check_output)
    with pytest.raises(Exception):
        pipeline.build_manifest(run_id="r", model_key="m", model_cfg={}, trade_date="2026-07-10", result_status="success", official=True)
