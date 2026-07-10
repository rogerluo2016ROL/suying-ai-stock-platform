from datetime import date
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("schema_audit", Path(__file__).with_name("schema_audit.py"))
schema_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schema_audit)
Finding = schema_audit.Finding
exit_code = schema_audit.exit_code
normalize_type = schema_audit.normalize_type
parse_init_sql = schema_audit.parse_init_sql


def test_expired_high_drift_exemption_fails():
    finding = Finding(
        table="stk_mins",
        severity="high",
        owner="data-service",
        exempt_until=date(2026, 7, 1),
    )

    assert exit_code([finding], today=date(2026, 7, 10), fail_on="medium") == 1


def test_active_exemption_does_not_fail_gate():
    finding = Finding(
        table="stk_mins",
        severity="high",
        owner="data-service",
        exemption="migration scheduled",
        exempt_until=date(2026, 7, 31),
    )

    assert exit_code([finding], today=date(2026, 7, 10), fail_on="medium") == 0


def test_low_finding_is_below_medium_threshold():
    assert exit_code([Finding(table="daily_kline", severity="low")], fail_on="medium") == 0


def test_postgres_type_aliases_are_normalized():
    assert normalize_type("character varying") == normalize_type("varchar")
    assert normalize_type("varchar(60)") == normalize_type("character varying")
    assert normalize_type("timestamp with time zone") == normalize_type("timestamptz")
    assert normalize_type("timestamp without time zone") == normalize_type("timestamp")
    assert normalize_type("numeric(18,2)") == normalize_type("numeric")


def test_column_name_starting_with_check_is_not_treated_as_constraint(tmp_path):
    sql = tmp_path / "init.sql"
    sql.write_text("CREATE TABLE IF NOT EXISTS jobs (check_interval_sec INTEGER, CHECK (check_interval_sec > 0));")
    assert ("check_interval_sec", "integer") in parse_init_sql(sql)["jobs"]["cols"]
