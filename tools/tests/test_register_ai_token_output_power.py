import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "register_ai_token_output_power.py"
SPEC = importlib.util.spec_from_file_location("register_ai_token_output_power", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
register = MODULE.register


class FakeConnection:
    def __init__(self):
        self.rows = {}

    def upsert(self, table, key, row):
        existed = (table, key) in self.rows
        self.rows[(table, key)] = row
        return "updated" if existed else "inserted"


def test_production_registration_requires_explicit_environment_guard(monkeypatch):
    monkeypatch.delenv("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION", raising=False)
    with pytest.raises(PermissionError, match="ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION"):
        register(mode="production", pg_url="postgresql://test", as_of_date="2026-07-14")


def test_staging_registration_is_idempotent():
    fake_pg = FakeConnection()
    first = register(mode="staging", pg_url="postgresql://test", as_of_date="2026-07-14", connection=fake_pg)
    second = register(mode="staging", pg_url="postgresql://test", as_of_date="2026-07-14", connection=fake_pg)
    assert first["inserted"] >= 1
    assert second["updated"] >= 1
    assert second["formal_pool_count"] == first["formal_pool_count"]
