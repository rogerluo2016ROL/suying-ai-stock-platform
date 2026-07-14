import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "audit_ai_token_output.py"
SPEC = importlib.util.spec_from_file_location("audit_token_output", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeConnection:
    audit_snapshot = {
        "mapping_count": 10, "unique_company_count": 8,
        "duplicate_company_layer_count": 1, "broad_tag_formal_count": 1,
        "pool_gate_violation_count": 0, "legacy_chain_mutation_count": 0,
        "rejected_formal_count": 0, "domestic_output_count": 2,
        "overseas_output_count": 1, "pool_counts": {"A": 1, "B": 1, "C": 2, "D": 6},
    }


def test_audit_blocks_duplicate_and_broad_formal_rows():
    result = MODULE.audit("unused", "2026-07-14", FakeConnection())
    assert result["duplicate_company_layer_count"] == 1
    assert result["broad_tag_formal_count"] == 1
    assert len(result["blocking_issues"]) == 2


def test_audit_reports_legacy_chain_without_mutating_it():
    result = MODULE.audit("unused", "2026-07-14", FakeConnection())
    assert result["legacy_chain_id"] == "ai_token_output_power"
    assert result["legacy_chain_mutation_count"] == 0
