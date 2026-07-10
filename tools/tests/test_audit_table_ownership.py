from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from audit_table_ownership import audit_ownership


def test_ownership_registry_flags_unknown_writer():
    result = audit_ownership({"daily_kline": ["data-service", "rogue-service"]})
    assert result["violations"] == [{"table": "daily_kline", "writer": "rogue-service", "owner": "data-service"}]
