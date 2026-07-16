from datetime import date
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from embodied_refresh.evidence import normalize_evidence
from embodied_refresh.models import RawEvidence


AS_OF = date(2026, 7, 17)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params=()):
        self.executions.append((" ".join(sql.split()), params))
        if "INSERT INTO business_tag_mapping" in sql:
            self.connection.pending_mappings.append(params[0])
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("persistence failed")
        if "INSERT INTO business_tag_stage_transition_log" in sql:
            self.connection.pending_history.append(params[0])

    def fetchone(self):
        return self.connection.existing


class FakeConnection:
    def __init__(self, existing=None, fail_on=None):
        self.existing = existing
        self.fail_on = fail_on
        self.cursor_instance = FakeCursor(self)
        self.commits = 0
        self.rollbacks = 0
        self.mappings = []
        self.history = []
        self.pending_mappings = []
        self.pending_history = []

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1
        self.mappings.extend(self.pending_mappings)
        self.history.extend(self.pending_history)
        self.pending_mappings.clear()
        self.pending_history.clear()

    def rollback(self):
        self.rollbacks += 1
        self.pending_mappings.clear()
        self.pending_history.clear()


def event(node_id, source_id="filing"):
    return normalize_evidence(RawEvidence(source_id, "annual_report", "公司已批量交付", AS_OF, node_id))


def test_new_mapping_is_candidate_and_pending_review():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection()
    changes = apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])], as_of=AS_OF)
    assert changes.created[0].to_status == "candidate"
    insert = next((sql, params) for sql, params in conn.cursor_instance.executions if "INSERT INTO business_tag_mapping" in sql)
    transition = next((sql, params) for sql, params in conn.cursor_instance.executions if "INSERT INTO business_tag_stage_transition_log" in sql)
    assert "candidate" in insert[1]
    assert "pending_review" in transition[1]


def test_existing_candidate_upgrade_reuses_can_auto_verify_with_explicit_as_of(monkeypatch):
    import embodied_refresh.mappings as mappings

    seen = []
    monkeypatch.setattr(mappings, "can_auto_verify", lambda events, *, as_of: seen.append(as_of) or True)
    conn = FakeConnection(existing=("map-1", "candidate", "node-a"))
    changes = mappings.apply_mapping_changes(conn, [mappings.MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])], as_of=AS_OF)
    assert seen == [AS_OF]
    assert changes.updated[0].to_status == "verified"


def test_ambiguous_nodes_create_review_conflict_instead_of_first_match():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection()
    changes = apply_mapping_changes(conn, [
        MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")]),
        MappingEvidence("000001", "embodied", "node-b", "减速器", [event("node-b", "filing-2")]),
    ], as_of=AS_OF)
    assert len(changes.conflicts) == 1
    assert not changes.created
    assert conn.commits == 1


def test_persistence_failure_rolls_back_mapping_and_history_atomically():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(fail_on="business_tag_stage_transition_log")
    with pytest.raises(RuntimeError, match="persistence failed"):
        apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])], as_of=AS_OF)
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.mappings == []
    assert conn.history == []


def test_unavailable_source_never_emits_downgrade():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(existing=("map-1", "verified", "node-a"))
    changes = apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [], sources_available=False)], as_of=AS_OF)
    assert not changes.updated
    assert conn.commits == 1
