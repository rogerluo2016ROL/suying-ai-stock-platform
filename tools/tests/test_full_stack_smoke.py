import json
import importlib.util
from pathlib import Path
import sys
import urllib.error

import pytest

_SMOKE_PATH = Path(__file__).resolve().parents[1] / "full_stack_smoke.py"
_SPEC = importlib.util.spec_from_file_location("full_stack_smoke", _SMOKE_PATH)
smoke = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = smoke
_SPEC.loader.exec_module(smoke)


def test_join_url_preserves_single_slashes():
    assert smoke.join_url("http://127.0.0.1:18001/", "/api/v1/health") == "http://127.0.0.1:18001/api/v1/health"
    assert smoke.join_url("http://127.0.0.1:18001", "api/v1/health") == "http://127.0.0.1:18001/api/v1/health"


def test_extract_access_token_requires_token():
    assert smoke.extract_access_token({"access_token": "abc"}) == "abc"
    with pytest.raises(smoke.SmokeError, match="access_token"):
        smoke.extract_access_token({"user": {"email": "admin@suying.ai"}})


def test_extract_first_pick_requires_code_and_price_defaults_to_one():
    pick = smoke.extract_first_pick({"picks": [{"code": "002354", "name": "天娱数科"}]})
    assert pick["code"] == "002354"
    assert pick["price"] == 1.0


def test_backtest_url_uses_the_same_registered_screening_model():
    url = smoke.build_backtest_url("http://backtest", "bi_trend_launch", top_n=5)
    assert url == (
        "http://backtest/api/v1/backtest/factor-evidence?"
        "model_key=bi_trend_launch&forward_days=5&cost_bps=14.0"
    )


def test_backtest_must_complete_before_paper_order():
    assert smoke.require_completed_backtest({"status": "ready", "evaluation_id": "EV-1"})["status"] == "ready"
    with pytest.raises(smoke.SmokeError, match="backtest did not complete"):
        smoke.require_completed_backtest({"status": "blocked", "missing_requirements": ["observations"]})


def test_no_pick_is_success_when_readiness_passes():
    assert smoke.classify_screener_result({"result_status": "success_no_matches", "picks": []}) == "pass"


def test_smoke_rejects_live_mode():
    with pytest.raises(SystemExit):
        smoke.load_config(["--trade-mode", "live"])


def test_http_json_reports_error_body(monkeypatch):
    class FakeResponse:
        def read(self):
            return json.dumps({"detail": "bad request"}).encode("utf-8")

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, FakeResponse())

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(smoke.SmokeError, match="bad request"):
        smoke.http_json("POST", "http://example.test/api")

def test_smoke_rejects_live_mode():
    with pytest.raises(SystemExit):
        smoke.load_config(["--trade-mode", "live"])

def test_no_pick_is_success_when_readiness_passes():
    assert smoke.classify_screener_result({"result_status": "success_no_matches", "picks": []})["status"] == "pass"


def test_run_smoke_returns_safe_skips_for_a_real_no_pick(monkeypatch):
    responses = iter((
        {"access_token": "token", "user": {"email": "admin@suying.ai"}},
        {"result_status": "success_no_matches", "picks": []},
    ))
    monkeypatch.setattr(smoke, "http_json", lambda *args, **kwargs: next(responses))
    result = smoke.run_smoke(smoke.SmokeConfig(
        auth_url="http://auth", screener_url="http://screener", diagnosis_url="http://diagnosis",
        strategy_url="http://strategy", backtest_url="http://backtest", trade_url="http://trade",
        email="admin@suying.ai", password="secret", screener_mode="short", top_n=5, timeout=1,
    ))
    assert result["status"] == "pass"
    assert result["safe_skips"] == ["diagnosis", "strategy", "backtest", "paper_order"]
