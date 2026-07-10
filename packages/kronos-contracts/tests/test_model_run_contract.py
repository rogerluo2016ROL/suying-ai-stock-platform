from datetime import date
from pathlib import Path
import sys
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parents[1]))
from kronos_contracts.model_run import ModelRunManifest


def test_official_manifest_requires_clean_strict_run():
    with pytest.raises(ValidationError):
        ModelRunManifest(
            schema_version="1.0", run_id="RUN-1", official=True,
            working_tree_dirty=True, strict_timeline=False,
            model_key="bi_trend_launch", model_version="v13",
            code_commit="abc123", parameters_hash="sha256:x",
            target_trade_date=date(2026, 7, 10), data_snapshot_id="DS-1",
            universe_hash="sha256:u", result_status="success",
        )
