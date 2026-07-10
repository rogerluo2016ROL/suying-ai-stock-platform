from pathlib import Path


def test_backtest_routes_do_not_emit_proxy_factor_metrics():
    source = (Path(__file__).parents[1] / "app" / "routes.py").read_text()
    assert "ic_proxy" not in source
    assert "daily returns as proxy" not in source

