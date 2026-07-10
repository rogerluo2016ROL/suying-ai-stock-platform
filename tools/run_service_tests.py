#!/usr/bin/env python3
"""Run a service's tests in an isolated cwd and Python import path."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE_TARGETS = [
    "backend", "api-gateway", "data-service", "screener-service", "prediction-service",
    "strategy-service", "signal-service", "alert-service", "trade-service",
    "backtest-service", "training-service", "diagnosis-service",
]


def _service_dir(service: str) -> Path:
    return ROOT / "backend" if service == "backend" else ROOT / "services" / service


def run_service(service: str, extra_args: list[str]) -> int:
    service_dir = _service_dir(service)
    if not (service_dir / "tests").is_dir():
        raise ValueError(f"unknown service or missing tests: {service}")
    env = os.environ.copy()
    package_paths = [ROOT / "packages" / name for name in ("kronos-contracts", "kronos-factors", "kronos-core", "kronos-data")]
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in [service_dir, *package_paths, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])
    result = subprocess.run([sys.executable, "-m", "pytest", "tests", *extra_args], cwd=service_dir, env=env, check=False)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", action="store_true")
    parser.add_argument("--service", choices=CORE_TARGETS)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    targets = CORE_TARGETS if args.core else ([args.service] if args.service else [])
    if not targets:
        parser.error("use --core or --service")
    rc = 0
    for service in targets:
        print(f"== {service} ==", flush=True)
        rc = run_service(service, args.pytest_args) or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
