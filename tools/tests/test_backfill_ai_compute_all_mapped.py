import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "backfill_ai_compute_all_mapped.py"
_SPEC = importlib.util.spec_from_file_location("backfill_ai_compute_all_mapped", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def test_batch_event_delete_sql_preserves_referenced_events():
    sql = module.batch_event_delete_sql(chain_scoped=True)

    assert "NOT EXISTS" in sql
    assert "evidence_extracted_facts" in sql
    assert "f.evidence_event_id = e.event_id" in sql
