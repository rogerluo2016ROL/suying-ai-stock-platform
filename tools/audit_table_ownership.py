"""Validate single-writer table ownership registry."""
import argparse, json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def audit_registry(registry, today=None):
    today = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    violations = []
    for table, spec in registry.items():
        owner, writers = spec.get("owner"), spec.get("writers", [])
        if not owner or writers != [owner]:
            violations.append({"table": table, "reason": "exactly one writer must equal owner"})
        exemption, exempt_until = spec.get("exemption"), spec.get("exempt_until")
        if bool(exemption) != bool(exempt_until):
            violations.append({"table": table, "reason": "exemption and exempt_until must be declared together"})
        elif exempt_until:
            try:
                expiry = date.fromisoformat(exempt_until)
            except (TypeError, ValueError):
                violations.append({"table": table, "reason": "exempt_until must be an ISO date"})
            else:
                if expiry < today:
                    violations.append({"table": table, "reason": f"ownership exemption expired on {expiry.isoformat()}"})
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
