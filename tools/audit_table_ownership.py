#!/usr/bin/env python3
"""Static table-owner gate for CI and release checks."""
from __future__ import annotations
import argparse
import json

OWNERS = {
    "daily_kline": "data-service", "daily_basic": "data-service",
    "adj_factor": "data-service", "stocks": "data-service",
    "factor_weights": "training-service", "orders": "trade-service",
}

def audit_ownership(writers: dict[str, list[str]]) -> dict:
    violations = []
    for table, services in writers.items():
        owner = OWNERS.get(table)
        if owner:
            violations.extend({"table": table, "writer": service, "owner": owner}
                              for service in services if service != owner)
    return {"owners": OWNERS, "violations": violations}

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--writers", help="JSON file mapping table to writer services")
    parser.add_argument("--fail-on", choices=("violation",), default="violation")
    args = parser.parse_args()
    writers = json.loads(open(args.writers, encoding="utf-8").read()) if args.writers else {}
    result = audit_ownership(writers)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["violations"] else 0

if __name__ == "__main__":
    raise SystemExit(main())
