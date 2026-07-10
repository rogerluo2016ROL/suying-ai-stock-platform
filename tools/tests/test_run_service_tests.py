from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
import run_service_tests


def test_each_service_uses_own_cwd_and_process(monkeypatch):
    calls = []

    def fake_run(cmd, cwd, env, check):
        calls.append((cmd, cwd, env))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_service_tests.run_service("trade-service", ["-q"]) == 0
    assert calls[0][1].as_posix().endswith("services/trade-service")
    assert calls[0][0][:3] == [sys.executable, "-m", "pytest"]
    assert calls[0][2]["PYTHONPATH"].split(":")[0].endswith("services/trade-service")
