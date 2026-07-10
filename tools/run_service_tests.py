"""Run one service's tests in an isolated subprocess."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_TARGETS = [
    "backend", "api-gateway", "data-service", "screener-service", "prediction-service",
    "strategy-service", "signal-service", "alert-service", "trade-service",
    "backtest-service", "training-service", "diagnosis-service",
]


def run_service(service: str, extra_args: list[str]) -> int:
    if service not in CORE_TARGETS:
        raise ValueError(f"Unknown service: {service}")
    service_dir = ROOT / "backend" if service == "backend" else ROOT / "services" / service
    if not service_dir.is_dir():
        raise ValueError(f"Service directory does not exist: {service_dir}")
    env = os.environ.copy()
    package_paths = [
        service_dir,
        ROOT / "packages" / "kronos-contracts",
        ROOT / "packages" / "kronos-factors",
        ROOT / "packages" / "kronos-core",
        ROOT / "packages" / "kronos-data",
    ]
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in package_paths)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", *extra_args],
        cwd=str(service_dir),
        env=env,
        check=False,
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--core", action="store_true", help="run the core service matrix")
    group.add_argument("service", nargs="?", choices=CORE_TARGETS)
    args, pytest_args = parser.parse_known_args()
    targets = CORE_TARGETS if args.core else [args.service]
    status = 0
    for service in targets:
        print(f"==> {service}", flush=True)
        status = run_service(service, pytest_args) or status
    return status


if __name__ == "__main__":
    raise SystemExit(main())
