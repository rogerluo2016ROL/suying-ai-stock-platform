import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from kronos_contracts.health import ComponentCheck, ServiceHealth


def test_health_contract_distinguishes_live_and_ready():
    check = ComponentCheck(status="unavailable", reason="postgres timeout")
    health = ServiceHealth(service="demo", live=True, ready=False, checks={"postgres": check})
    assert health.live is True
    assert health.ready is False
    assert health.checks["postgres"].status == "unavailable"
