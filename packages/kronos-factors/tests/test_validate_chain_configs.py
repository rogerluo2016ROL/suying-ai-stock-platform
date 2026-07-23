"""thin pytest wrapper for tools/validate_chain_configs.py."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "validate_chain_configs.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_chain_configs", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chain_configs_consistent():
    violations = _load_validator().validate()
    assert violations == [], "\n".join(violations)
