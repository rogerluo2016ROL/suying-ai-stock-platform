import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("audit", Path(__file__).parents[1] / "audit_table_ownership.py")
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)

def test_table_has_exactly_one_owner():
    result = audit.audit_registry({"daily_kline": {"owner": "data-service", "writers": ["data-service"]}})
    assert result.violations == []

def test_multiple_writers_violate_registry():
    result = audit.audit_registry({"daily_kline": {"owner": "data-service", "writers": ["data-service", "screener-service"]}})
    assert result.violations
