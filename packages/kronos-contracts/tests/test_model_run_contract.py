import pytest
from pydantic import ValidationError
from kronos_contracts.model_run import ModelRunManifest
from datetime import datetime

def test_official_manifest_requires_clean_strict_run():
    with pytest.raises(ValidationError):
        ModelRunManifest(schema_version="1.0", run_id="RUN-1", official=True,
            working_tree_dirty=True, strict_timeline=False, model_key="bi_trend_launch",
            model_version="v13", code_commit="abc123", parameters_hash="sha256:x",
            target_trade_date="2026-07-10", data_snapshot_id="DS-1", universe_hash="sha256:u",
            result_status="success", cutoff_time=datetime(2026, 7, 10, 14, 30))

def test_research_manifest_can_be_non_strict():
    result = ModelRunManifest(schema_version="1.0", run_id="RUN-2", official=False,
        working_tree_dirty=True, strict_timeline=False, model_key="x", model_version="dev",
        code_commit="abc", parameters_hash="p", target_trade_date="2026-07-10",
        data_snapshot_id="DS", universe_hash="u", result_status="research")
    assert result.official is False

def test_official_manifest_requires_snapshot_and_cutoff():
    with pytest.raises(ValidationError):
        ModelRunManifest(schema_version="1.0", run_id="RUN-3", official=True,
            working_tree_dirty=False, strict_timeline=True, model_key="x", model_version="v1",
            code_commit="abc", parameters_hash="sha256:p", target_trade_date="2026-07-10",
            data_snapshot_id="UNAVAILABLE", universe_hash="sha256:u", result_status="success")
