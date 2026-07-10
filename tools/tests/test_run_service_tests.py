import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from run_service_tests import CORE_TARGETS, python_executable, run_service


def test_each_service_uses_own_cwd_and_process(monkeypatch):
    calls = []

    def fake_run(cmd, cwd, env, check):
        calls.append((cmd, cwd, env))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_service("trade-service", ["-q"]) == 0
    assert calls[0][1].endswith("services/trade-service")
    assert calls[0][0][:3] == [python_executable(), "-m", "pytest"]
    assert calls[0][2]["PYTHONPATH"].split(os.pathsep)[0].endswith("services/trade-service")


def test_unknown_service_is_rejected():
    with pytest.raises(ValueError, match="Unknown service"):
        run_service("not-a-service", [])


def test_core_targets_are_complete():
    assert "backend" in CORE_TARGETS
    assert "trade-service" in CORE_TARGETS
    assert len(CORE_TARGETS) == 12
