from typing import Protocol

class BacktestAdapter(Protocol):
    model_key: str
    def run(self, request, readiness): ...
