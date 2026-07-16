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
        self.last_sql = sql
        self.executions.append((" ".join(sql.split()), params))
        if "INSERT INTO business_tag_mapping" in sql:
            self.connection.pending_mappings.append(params[0])
        if self.connection.fail_on and self.connection.fail_on in sql:
            raise RuntimeError("persistence failed")
        if "INSERT INTO embodied_mapping_transitions" in sql:
            self.connection.pending_history.append(params[0])

    def fetchall(self):
        if "FROM business_tag_evidence_events WHERE" in getattr(self, "last_sql", ""):
            return list(self.connection.historical)
        return list(self.connection.existing)

    def fetchone(self):
        return self.connection.existing


class FakeConnection:
    def __init__(self, existing=(), fail_on=None, historical=()):
        self.existing = list(existing)
        self.fail_on = fail_on
        self.historical = list(historical)
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


def test_new_mapping_with_single_s_source_is_verified_in_same_transaction():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection()
    changes = apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])], as_of=AS_OF)
    assert changes.created[0].to_status == "verified"
    insert = next((sql, params) for sql, params in conn.cursor_instance.executions if "INSERT INTO business_tag_mapping" in sql)
    transition = next((sql, params) for sql, params in conn.cursor_instance.executions if "INSERT INTO embodied_mapping_transitions" in sql)
    assert "verified" in insert[1]
    assert "pending_review" in transition[1]
    assert any("INSERT INTO business_tag_evidence_events" in sql for sql, _ in conn.cursor_instance.executions)
    assert __import__("json").loads(insert[1][8]) == [event("node-a").fingerprint]


def test_projection_uses_same_state_machine_without_writes():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection()
    changes = apply_mapping_changes(
        conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])],
        as_of=AS_OF, persist=False,
    )
    assert changes.created[0].to_status == "verified"
    assert conn.commits == 0
    assert all("INSERT" not in sql for sql, _ in conn.cursor_instance.executions)


def test_existing_candidate_upgrade_reuses_can_auto_verify_with_explicit_as_of(monkeypatch):
    import embodied_refresh.mappings as mappings

    seen = []
    monkeypatch.setattr(mappings, "can_auto_verify", lambda events, *, as_of: seen.append(as_of) or True)
    conn = FakeConnection(existing=[("map-1", "candidate", "node-a")])
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
    assert changes.conflicts[0].node_ids == ("node-a", "node-b")
    assert {item.conflict_type for item in changes.conflicts} == {"batch_ambiguity"}
    assert not changes.created
    assert any("INSERT INTO embodied_mapping_conflicts" in sql for sql, _ in conn.cursor_instance.executions)
    assert conn.commits == 1


def test_existing_different_node_creates_persisted_review_conflict():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(existing=[("map-old", "verified", "node-old")])
    changes = apply_mapping_changes(
        conn,
        [MappingEvidence("000001", "embodied", "node-new", "减速器", [event("node-new")])],
        as_of=AS_OF,
    )
    assert changes.conflicts[0].existing_node_id == "node-old"
    conflict = next(params for sql, params in conn.cursor_instance.executions if "INSERT INTO embodied_mapping_conflicts" in sql)
    assert "node-old" in conflict and "node-new" in conflict
    assert not changes.created


def test_same_node_evidence_batches_are_merged_before_upgrade(monkeypatch):
    import embodied_refresh.mappings as mappings

    seen = []
    monkeypatch.setattr(mappings, "can_auto_verify", lambda events, *, as_of: seen.append(list(events)) or len(events) == 2)
    conn = FakeConnection(existing=[("map-1", "candidate", "node-a")])
    changes = mappings.apply_mapping_changes(conn, [
        mappings.MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a", "one")], source_name="announcement"),
        mappings.MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a", "two")], source_name="research"),
    ], as_of=AS_OF)
    assert [item.source_id for item in seen[0]] == ["one", "two"]
    assert changes.updated[0].to_status == "verified"
    transition = next(params for sql, params in conn.cursor_instance.executions if "INSERT INTO embodied_mapping_transitions" in sql)
    assert __import__("json").loads(transition[8]) == ["one", "two"]
    fingerprints = __import__("json").loads(transition[9])
    assert len(fingerprints) == 2
    assert set(fingerprints).isdisjoint({"one", "two"})
    assert __import__("json").loads(transition[10]) == ["announcement", "research"]


def test_existing_match_and_new_mismatch_only_records_real_conflict_pair():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(existing=[("map-a", "verified", "node-a")])
    changes = apply_mapping_changes(conn, [
        MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")]),
        MappingEvidence("000001", "embodied", "node-b", "减速器", [event("node-b", "two")]),
    ], as_of=AS_OF)
    assert [(c.existing_node_id, c.proposed_node_id) for c in changes.conflicts] == [("node-a", "node-b")]


def test_multiple_existing_nodes_record_every_unequal_pair_without_self_conflict():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(existing=[
        ("map-a", "candidate", "node-a"),
        ("map-c", "candidate", "node-c"),
    ])
    changes = apply_mapping_changes(conn, [
        MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")]),
        MappingEvidence("000001", "embodied", "node-b", "减速器", [event("node-b", "two")]),
    ], as_of=AS_OF)
    pairs = {(c.existing_node_id, c.proposed_node_id) for c in changes.conflicts}
    assert pairs == {("node-a", "node-b"), ("node-c", "node-a"), ("node-c", "node-b")}
    assert all(existing != proposed for existing, proposed in pairs)


def test_persistence_failure_rolls_back_mapping_and_history_atomically():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(fail_on="embodied_mapping_transitions")
    with pytest.raises(RuntimeError, match="persistence failed"):
        apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [event("node-a")])], as_of=AS_OF)
    assert conn.commits == 0
    assert conn.rollbacks == 1
    assert conn.mappings == []
    assert conn.history == []


def test_unavailable_source_never_emits_downgrade():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    conn = FakeConnection(existing=[("map-1", "verified", "node-a")])
    changes = apply_mapping_changes(conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [], sources_available=False)], as_of=AS_OF)
    assert not changes.updated
    assert conn.commits == 1


def test_cross_day_two_independent_a_sources_upgrade_candidate():
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes

    prior = normalize_evidence(RawEvidence("official-one", "official_web", "公司已批量交付", AS_OF, "node-a",
                                            canonical_source_id="official-one"))
    current = normalize_evidence(RawEvidence("official-two", "official_wechat", "公司已批量交付", AS_OF, "node-a",
                                              canonical_source_id="official-two"))
    conn = FakeConnection(
        existing=[("map-1", "candidate", "node-a", [prior.fingerprint])],
        historical=[(prior.fingerprint, "official-one", "official_web", prior.content, AS_OF, "node-a", None)],
    )

    changes = apply_mapping_changes(
        conn, [MappingEvidence("000001", "embodied", "node-a", "传感器", [current])], as_of=AS_OF
    )

    assert changes.updated[0].to_status == "verified"
    assert any("SET mapping_id=%s" in sql for sql, _ in conn.cursor_instance.executions)
