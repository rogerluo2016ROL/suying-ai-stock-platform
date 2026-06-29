import tomllib
from pathlib import Path


def test_pg_adapter_runtime_dependency_declared():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text())
    dependencies = metadata["project"]["dependencies"]

    assert any(dep.startswith("psycopg2-binary") for dep in dependencies)
