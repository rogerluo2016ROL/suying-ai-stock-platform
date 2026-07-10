from pathlib import Path


def test_alembic_env_makes_backend_package_importable_when_run_as_cli():
    """The Alembic CLI executes env.py from alembic/, not backend/.

    UAT starts migrations through that CLI path, so env.py must explicitly
    expose its parent directory before importing ``app``.
    """
    source = (Path(__file__).parents[1] / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "sys.path.insert(0, BACKEND_ROOT)" in source
