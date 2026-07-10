import importlib.util
from pathlib import Path

path = Path(__file__).with_name("schema_audit.py")
spec = importlib.util.spec_from_file_location("schema_audit", path)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)

def test_medium_gate_fails_for_high_or_medium_findings():
    assert module.audit_exit_code({"x": {"sev": "medium"}}, "medium") == 1
    assert module.audit_exit_code({"x": {"sev": "low"}}, "medium") == 0
