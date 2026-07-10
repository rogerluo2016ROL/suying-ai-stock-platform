"""Fail-closed model admission contract."""
from __future__ import annotations
from dataclasses import dataclass

REQUIRED_GATES = ("data_readiness", "out_of_sample", "drawdown", "costs", "timeline")

@dataclass(frozen=True)
class AdmissionResult:
    status: str
    failed_gates: tuple[str, ...]

def evaluate_admission(gates: dict[str, bool]) -> AdmissionResult:
    failed = tuple(name for name in REQUIRED_GATES if not gates.get(name, False))
    return AdmissionResult("ready" if not failed else "blocked", failed)
