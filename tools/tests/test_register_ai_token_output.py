import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "register_ai_token_output.py"
SPEC = importlib.util.spec_from_file_location("register_ai_token_output", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FakeConnection:
    def __init__(self):
        self.rows = {}

    def upsert(self, table, key, row):
        existed = (table, key) in self.rows
        self.rows[(table, key)] = row
        return "updated" if existed else "inserted"


def test_registration_creates_eight_isolated_nodes():
    fake = FakeConnection()
    result = MODULE.register("staging", "unused", "2026-07-14", fake)
    nodes = [row for (table, _), row in fake.rows.items() if table == "supply_chain_hierarchy_nodes"]
    assert result["chain_id"] == "ai_token_output"
    assert result["node_count"] == 8
    assert all(row["chain_id"] == "ai_token_output" for row in nodes)
    assert {row["node_id"] for row in nodes} == {f"ai_token_output:L{i}" for i in range(1, 9)}


def test_production_registration_requires_explicit_guard(monkeypatch):
    monkeypatch.delenv("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION", raising=False)
    with pytest.raises(PermissionError):
        MODULE.register("production", "unused", "2026-07-14")
