import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "materialize_ai_token_output_power.py"
SPEC = importlib.util.spec_from_file_location("materialize_ai_token_output_power", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_build_capacity_snapshot_preserves_model_and_hardware_profile():
    result = MODULE.build_capacity_snapshot({
        "available_mw": 10,
        "operating_hours": 100,
        "utilization": 0.5,
        "tokens_per_mw_hour": 2000,
        "cluster_availability": 0.8,
        "model_profile": "long_context_32k",
        "hardware_type": "inference_gpu",
        "precision": "int8",
        "batch_mode": "continuous_batching",
    })
    assert result["billable_tokens"] == 800000.0
    assert result["model_profile"] == "long_context_32k"
    assert result["hardware_type"] == "inference_gpu"


def test_pool_materialization_keeps_d_out_of_formal_items():
    result = MODULE.split_formal_and_provisional([
        {"mapping_id": "m1", "pool_code": "A"},
        {"mapping_id": "m2", "pool_code": "D"},
    ])
    assert [item["mapping_id"] for item in result["formal_items"]] == ["m1"]
    assert [item["mapping_id"] for item in result["provisional_items"]] == ["m2"]


def test_mapping_sql_excludes_rejected_and_disabled_statuses():
    sql = MODULE.build_mapping_sql("ai_token_output_power", formal_only=True)
    assert "COALESCE(m.status, '') NOT IN ('rejected', 'disabled')" in sql
    assert "pool_code IN ('A', 'B', 'C')" in sql
