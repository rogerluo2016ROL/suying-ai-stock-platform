"""Validate single-writer table ownership registry."""
import argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit_registry(registry):
    violations = []
    for table, spec in registry.items():
        owner, writers = spec.get("owner"), spec.get("writers", [])
        if not owner or writers != [owner]:
            violations.append({"table": table, "reason": "exactly one writer must equal owner"})
    return type("AuditResult", (), {"violations": violations})()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-on", default="violation")
    args = parser.parse_args()
    registry = json.loads((ROOT / "configs/data_ownership.json").read_text())
    result = audit_registry(registry)
    if result.violations:
        print(json.dumps(result.violations, ensure_ascii=False))
        return 1
    print("table ownership: clean")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
