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
