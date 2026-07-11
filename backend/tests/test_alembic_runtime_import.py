from pathlib import Path


def test_alembic_env_makes_backend_package_importable_when_run_as_cli():
    """The Alembic CLI executes env.py from alembic/, not backend/.

    UAT starts migrations through that CLI path, so env.py must explicitly
    expose its parent directory before importing ``app``.
    """
    source = (Path(__file__).parents[1] / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "sys.path.insert(0, BACKEND_ROOT)" in source


def test_reconcile_migration_does_not_add_a_second_primary_key():
    source = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "030_reconcile_limit_and_ths_concept_schema.py"
    ).read_text(encoding="utf-8")
    assert "contype = 'p'" in source
    assert "DROP INDEX IF EXISTS idx_ths_concept_map_code" in source


def test_reconcile_migration_skips_sequence_default_for_identity_column():
    source = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "030_reconcile_limit_and_ths_concept_schema.py"
    ).read_text(encoding="utf-8")
    assert "is_identity = 'NO'" in source
    assert "ALTER COLUMN id SET DEFAULT" in source
