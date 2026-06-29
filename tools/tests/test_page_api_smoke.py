import importlib.util
import sys
from dataclasses import replace
from pathlib import Path


_SMOKE_PATH = Path(__file__).resolve().parents[1] / "page_api_smoke.py"
_SPEC = importlib.util.spec_from_file_location("page_api_smoke", _SMOKE_PATH)
page_smoke = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = page_smoke
_SPEC.loader.exec_module(page_smoke)


def _config():
    return page_smoke.SmokeConfig(
        auth_url="http://auth",
        screener_url="http://screener",
        prediction_url="http://prediction",
        strategy_url="http://strategy",
        signal_url="http://signal",
        trade_url="http://trade",
        backtest_url="http://backtest",
        diagnosis_url="http://diagnosis",
        training_url="http://training",
        gateway_url="http://gateway",
        email="admin@suying.ai",
        password="Admin123!",
        timeout=3.0,
    )


def test_check_url_uses_the_configured_service_base():
    check = page_smoke.EndpointCheck(
        name="signal.data-status",
        service="signal",
        method="GET",
        path="/api/v1/signal/data-status",
    )

    assert page_smoke.check_url(check, _config()) == "http://signal/api/v1/signal/data-status"


def test_default_checks_are_read_only_and_cover_model_pages():
    checks = page_smoke.default_checks(include_actions=False)
    names = {check.name for check in checks}

    assert "screener.run" not in names
    assert "auth.health" in names
    assert "signal.dashboard-summary" in names
    assert "supply-chain.workbench" in names
    assert "chain.candidates" in names
    assert "strategy.auto-list" in names
    assert "training.models" in names
    assert "training.history" in names
    assert "model-registry.models" in names
    assert next(check for check in checks if check.name == "chain.candidates").optional
    assert all(not check.action for check in checks)


def test_action_checks_are_explicitly_included():
    names = {check.name for check in page_smoke.default_checks(include_actions=True)}

    assert "screener.run" in names
    assert "prediction.predict" in names


def test_run_check_forwards_auth_token():
    calls = []

    def fake_http(method, url, body=None, token=None, timeout=30.0):
        calls.append({"method": method, "url": url, "body": body, "token": token, "timeout": timeout})
        return {"status": "ok"}

    result = page_smoke.run_check(
        page_smoke.EndpointCheck("strategy.plans", "strategy", "GET", "/api/v1/strategy/plans"),
        _config(),
        token="abc",
        http=fake_http,
    )

    assert result["status"] == "ok"
    assert calls == [{
        "method": "GET",
        "url": "http://strategy/api/v1/strategy/plans",
        "body": None,
        "token": "abc",
        "timeout": 3.0,
    }]


def test_run_check_skips_actions_without_flag():
    result = page_smoke.run_check(
        page_smoke.EndpointCheck(
            name="screener.run",
            service="screener",
            method="POST",
            path="/api/v1/screener/run?mode=short&top_n=5",
            action=True,
        ),
        _config(),
        token="abc",
        include_actions=False,
    )

    assert result["status"] == "skipped"
    assert "include-actions" in result["reason"]


def test_run_check_records_timeout_as_failure():
    def timeout_http(*args, **kwargs):
        raise TimeoutError("timed out")

    result = page_smoke.run_check(
        page_smoke.EndpointCheck("signal.data-status", "signal", "GET", "/api/v1/signal/data-status"),
        _config(),
        token="abc",
        http=timeout_http,
    )

    assert result["status"] == "fail"
    assert "timed out" in result["error"]


def test_login_uses_configured_access_token_without_http_call():
    config = replace(_config(), access_token="abc")

    def fail_http(*args, **kwargs):
        raise AssertionError("http should not be called when an access token is configured")

    assert page_smoke.login(config, http=fail_http) == "abc"


def test_login_can_register_when_explicitly_enabled():
    calls = []

    def fake_http(method, url, body=None, token=None, timeout=30.0):
        calls.append((method, url, body))
        if url.endswith("/login"):
            raise page_smoke.SmokeError("POST /login failed (401): bad credentials")
        return {"access_token": "registered-token"}

    token = page_smoke.login(_config(), http=fake_http, register_if_needed=True)

    assert token == "registered-token"
    assert calls[0][1] == "http://auth/api/v1/auth/login"
    assert calls[1][1] == "http://auth/api/v1/auth/register"
    assert calls[1][2]["email"] == "admin@suying.ai"


def test_run_checks_keeps_public_results_when_login_fails(monkeypatch):
    checks = [
        page_smoke.EndpointCheck("gateway.health", "gateway", "GET", "/health", auth=False),
        page_smoke.EndpointCheck("strategy.plans", "strategy", "GET", "/api/v1/strategy/plans"),
    ]
    monkeypatch.setattr(page_smoke, "default_checks", lambda include_actions=False: checks)

    def fake_http(method, url, body=None, token=None, timeout=30.0):
        if url == "http://gateway/health":
            return {"status": "healthy"}
        if url == "http://auth/api/v1/auth/login":
            raise page_smoke.SmokeError("POST /login failed (401): bad credentials")
        raise AssertionError(f"unexpected call: {url}")

    result = page_smoke.run_checks(_config(), http=fake_http)

    assert result["status"] == "fail"
    assert result["checks"][0]["name"] == "gateway.health"
    assert result["checks"][0]["status"] == "ok"
    assert result["checks"][1]["name"] == "auth.login"
    assert result["checks"][1]["status"] == "fail"
