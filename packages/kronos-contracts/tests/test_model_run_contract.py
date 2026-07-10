import pytest
from pydantic import ValidationError
from kronos_contracts.model_run import ModelRunManifest

def test_official_manifest_requires_clean_strict_run():
    with pytest.raises(ValidationError):
        ModelRunManifest(schema_version="1.0", run_id="RUN-1", official=True,
            working_tree_dirty=True, strict_timeline=False, model_key="bi_trend_launch",
            model_version="v13", code_commit="abc123", parameters_hash="sha256:x",
            target_trade_date="2026-07-10", data_snapshot_id="DS-1", universe_hash="sha256:u",
            result_status="success")

def test_research_manifest_can_be_non_strict():
    result = ModelRunManifest(schema_version="1.0", run_id="RUN-2", official=False,
        working_tree_dirty=True, strict_timeline=False, model_key="x", model_version="dev",
        code_commit="abc", parameters_hash="p", target_trade_date="2026-07-10",
        data_snapshot_id="DS", universe_hash="u", result_status="research")
    assert result.official is False
