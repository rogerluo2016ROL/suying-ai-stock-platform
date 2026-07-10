"""Bridge persisted model metrics to the shared promotion contract."""
from __future__ import annotations

import sys
from pathlib import Path

_contracts = Path(__file__).resolve().parents[3] / "packages" / "kronos-contracts"
if str(_contracts) not in sys.path:
    sys.path.insert(0, str(_contracts))

from kronos_contracts.admission import AdmissionResult, evaluate_admission


def admission_from_metrics(metrics: dict | None) -> AdmissionResult:
    gates = (metrics or {}).get("admission_gates") or {}
    return evaluate_admission({name: gates.get(name, False) for name in (
        "data_readiness", "out_of_sample", "drawdown", "costs", "timeline"
    )})
