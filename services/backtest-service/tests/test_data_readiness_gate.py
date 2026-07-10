from app.routes import readiness_gate


def test_backtest_readiness_gate_blocks_lagging_adjustments():
    result = readiness_gate({"status": "blocked", "sources": [{"source": "adj_factor", "status": "stale"}]})
    assert result["status"] == "blocked"
    assert result["fallback_reason"] == "required data is stale or incomplete"
