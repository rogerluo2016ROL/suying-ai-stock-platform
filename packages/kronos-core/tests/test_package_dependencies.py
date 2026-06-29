import tomllib
from pathlib import Path


def test_kronos_transformer_runtime_dependencies_declared():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text())
    dependencies = metadata["project"]["dependencies"]

    assert any(dep.startswith("einops") for dep in dependencies)
    assert any(dep.startswith("safetensors") for dep in dependencies)
