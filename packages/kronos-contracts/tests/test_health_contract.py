from kronos_contracts.health import ComponentCheck, build_health

def test_process_can_be_live_while_dependency_is_unavailable():
    health = build_health("demo", "0.1.0", {"postgres": ComponentCheck(status="unavailable", latency_ms=10)})
    assert health.live is True
    assert health.ready is False

def test_ready_when_all_checks_pass():
    health = build_health("demo", "0.1.0", {"postgres": ComponentCheck(status="ready")})
    assert health.ready is True
