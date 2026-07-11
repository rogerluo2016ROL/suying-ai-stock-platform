from pathlib import Path


def test_backfill_script_is_explicitly_real_data_only():
    source = Path("tools/backfill_bi_trend_factor_snapshots.py").read_text(encoding="utf-8")
    assert "_run_bi_trend_mode" in source
    assert "record_picks" in source
    assert "factor_observations" in source
    assert "synthetic" not in source.lower()
