"""In-memory plan store for strategy-service."""

import uuid, threading
from datetime import datetime
from dataclasses import dataclass, field

@dataclass
class Plan:
    id: str
    name: str
    status: str  # draft/predicting/backtesting/confirmed/active/archived
    picks: list[dict]
    model_name: str
    capital: float = 1_000_000
    max_positions: int = 5
    single_max_pct: float = 0.2
    created_at: str = ""
    updated_at: str = ""

class PlanStore:
    def __init__(self):
        self._plans: dict[str, Plan] = {}
        self._lock = threading.Lock()

    def create(self, name: str, picks: list[dict], model_name: str = "all",
               capital: float = 1_000_000, max_positions: int = 5) -> Plan:
        with self._lock:
            pid = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now().isoformat()
            plan = Plan(id=pid, name=name, status="draft", picks=picks,
                        model_name=model_name, capital=capital,
                        max_positions=max_positions, created_at=now, updated_at=now)
            self._plans[pid] = plan
            return plan

    def get(self, plan_id: str) -> Plan | None:
        return self._plans.get(plan_id)

    def list_all(self) -> list[Plan]:
        return list(self._plans.values())

    def update(self, plan_id: str, **kwargs) -> Plan | None:
        plan = self._plans.get(plan_id)
        if not plan: return None
        for k, v in kwargs.items():
            if hasattr(plan, k): setattr(plan, k, v)
        plan.updated_at = datetime.now().isoformat()
        return plan

    def delete(self, plan_id: str) -> bool:
        if plan_id in self._plans:
            del self._plans[plan_id]
            return True
        return False

    def confirm(self, plan_id: str) -> Plan | None:
        return self.update(plan_id, status="confirmed")

    def archive(self, plan_id: str) -> Plan | None:
        return self.update(plan_id, status="archived")


_store = PlanStore()
def get_store() -> PlanStore: return _store
