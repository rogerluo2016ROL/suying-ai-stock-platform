import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "audit_ai_token_output_power.py"
SPEC = importlib.util.spec_from_file_location("audit_ai_token_output_power", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
audit = MODULE.audit


class FakeConnection:
    def __init__(self):
        self.rows = {}


def test_audit_marks_unknown_power_fields_and_excludes_d_pool(tmp_path):
    report = audit("postgresql://test", "2026-07-14", tmp_path / "v1.json", connection=FakeConnection())
    assert report["power_field_coverage"] < 1.0
    assert report["formal_pool_count"] == report["pool_counts"]["A"] + report["pool_counts"]["B"] + report["pool_counts"]["C"]
    assert report["provisional_pool_count"] == report["pool_counts"]["D"]
    assert "rejected_mapping_count" in report
