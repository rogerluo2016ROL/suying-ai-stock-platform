"""Full-stack smoke check: auth -> screener -> diagnosis -> strategy -> backtest -> paper trade.

Defaults target the local UAT port layout. Override URLs with environment
variables when checking dev/default ports.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class SmokeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmokeConfig:
    auth_url: str
    screener_url: str
    diagnosis_url: str
    strategy_url: str
    backtest_url: str
    trade_url: str
    email: str
    password: str
    screener_mode: str
    top_n: int
    timeout: float
    trade_mode: str = "paper"
    require_pick: bool = False


def join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _decode_json(raw: bytes, url: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    try:
        value = json.loads(text) if text else {}
    except json.JSONDecodeError as e:
        raise SmokeError(f"{url} returned non-JSON response: {text[:200]}") from e
    if not isinstance(value, dict):
        raise SmokeError(f"{url} returned JSON {type(value).__name__}, expected object")
    return value


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | list[Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _decode_json(resp.read(), url)
    except urllib.error.HTTPError as e:
        err = _decode_json(e.read(), url)
        detail = err.get("detail") or err.get("message") or err
        raise SmokeError(f"{method.upper()} {url} failed ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise SmokeError(f"{method.upper()} {url} unavailable: {e.reason}") from e


def extract_access_token(login_body: dict[str, Any]) -> str:
    token = login_body.get("access_token")
    if not isinstance(token, str) or not token:
        raise SmokeError("login response missing access_token")
    return token


def extract_first_pick(screen_body: dict[str, Any]) -> dict[str, Any]:
    picks = screen_body.get("picks")
    if not isinstance(picks, list) or not picks:
        raise SmokeError("screener response has no picks")
    pick = picks[0]
    if not isinstance(pick, dict) or not pick.get("code"):
        raise SmokeError("first screener pick missing code")
    normalized = dict(pick)
    try:
        price = float(normalized.get("price") or normalized.get("close") or 1.0)
    except (TypeError, ValueError):
        price = 1.0
    normalized["price"] = price if price > 0 else 1.0
    return normalized


def classify_screener_result(screen_body: dict[str, Any]) -> str:
    return "pass" if screen_body.get("result_status") == "success_no_matches" else "requires_pick"


def _query(params: dict[str, Any]) -> str:
    return urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})


def build_backtest_url(base_url: str, model_key: str, *, top_n: int) -> str:
    return join_url(base_url, "/api/v1/backtest/factor-evidence") + "?" + _query(
        {
            "model_key": model_key,
            "forward_days": 5,
            "cost_bps": 14.0,
        }
    )


def require_completed_backtest(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("status") != "ready":
        raise SmokeError(
            "backtest did not complete: "
            f"status={body.get('status')}, missing={body.get('missing_requirements') or []}"
        )
    return body


def load_config(argv: list[str] | None = None) -> SmokeConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default=os.environ.get("SMOKE_SCREENER_MODE", "short"))
    parser.add_argument("--top-n", type=int, default=int(os.environ.get("SMOKE_TOP_N", "5")))
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("SMOKE_TIMEOUT", "45")))
    parser.add_argument("--trade-mode", choices=("paper",), default="paper")
    parser.add_argument("--require-pick", action="store_true")
    args = parser.parse_args(argv)

    return SmokeConfig(
        auth_url=os.environ.get("SMOKE_AUTH_URL", "http://127.0.0.1:19001"),
        screener_url=os.environ.get("SMOKE_SCREENER_URL", "http://127.0.0.1:18001"),
        diagnosis_url=os.environ.get("SMOKE_DIAGNOSIS_URL", "http://127.0.0.1:18009"),
        strategy_url=os.environ.get("SMOKE_STRATEGY_URL", "http://127.0.0.1:18003"),
        backtest_url=os.environ.get("SMOKE_BACKTEST_URL", "http://127.0.0.1:18007"),
        trade_url=os.environ.get("SMOKE_TRADE_URL", "http://127.0.0.1:18006"),
        email=os.environ.get("SMOKE_EMAIL", "admin@suying.ai"),
        password=os.environ.get("SMOKE_PASSWORD", "Admin123!"),
        screener_mode=args.mode,
        top_n=args.top_n,
        timeout=args.timeout,
        trade_mode=args.trade_mode,
        require_pick=args.require_pick,
    )

def classify_screener_result(body: dict[str, Any], require_pick: bool = False) -> dict[str, Any]:
    if body.get("result_status") == "success_no_matches" and not require_pick:
        return {"status": "pass", "result_status": "success_no_matches", "safe_skips": ["diagnosis", "strategy", "backtest", "paper_order"]}
    if not body.get("picks"):
        raise SmokeError("screener returned no pick for a pick-required smoke")
    return {"status": "pass", "result_status": body.get("result_status", "success")}


def run_smoke(config: SmokeConfig) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    def record(name: str, payload: dict[str, Any]) -> dict[str, Any]:
        steps.append({"step": name, "status": "ok", "summary": payload})
        print(f"[OK] {name}: {payload}")
        return payload

    login_body = http_json(
        "POST",
        join_url(config.auth_url, "/api/v1/auth/login"),
        {"email": config.email, "password": config.password},
        timeout=config.timeout,
    )
    token = extract_access_token(login_body)
    record("auth.login", {"user": login_body.get("user", {}).get("email", config.email)})

    screen_url = join_url(config.screener_url, "/api/v1/screener/run") + "?" + _query(
        {"mode": config.screener_mode, "top_n": config.top_n}
    )
    screen_body = http_json("POST", screen_url, token=token, timeout=config.timeout)
    screener_result = classify_screener_result(screen_body, require_pick=config.require_pick)
    if screener_result["result_status"] == "success_no_matches":
        if config.require_pick:
            raise SmokeError("screener returned a valid no-pick result; full-chain evidence requires a real pick")
        return {
            "status": "pass", "result_status": "success_no_matches",
            "safe_skips": ["diagnosis", "strategy", "backtest", "paper_order"], "steps": steps,
        }
    pick = extract_first_pick(screen_body)
    record("screener.run", {"mode": config.screener_mode, "pick": f"{pick['code']} {pick.get('name', '')}".strip()})

    diagnosis_body = http_json(
        "POST",
        join_url(config.diagnosis_url, "/api/v1/diagnosis/analyze"),
        {"code": pick["code"], "force_refresh": False},
        token=token,
        timeout=config.timeout,
    )
    record("diagnosis.analyze", {"code": pick["code"], "score": diagnosis_body.get("overall_score")})

    plan_name = f"smoke-{time.strftime('%m%d%H%M%S')}"
    plan_url = join_url(config.strategy_url, "/api/v1/strategy/plans") + "?" + _query(
        {"name": plan_name, "model_name": config.screener_mode, "capital": 500000, "max_positions": 5}
    )
    plan_body = http_json("POST", plan_url, token=token, timeout=config.timeout)
    plan_id = plan_body.get("plan", {}).get("id")
    if not plan_id:
        raise SmokeError("strategy create plan response missing plan.id")
    record("strategy.plan.create", {"plan_id": plan_id})

    http_json(
        "POST",
        join_url(config.strategy_url, f"/api/v1/strategy/plans/{plan_id}/picks"),
        [pick],
        token=token,
        timeout=config.timeout,
    )
    confirm_body = http_json(
        "POST",
        join_url(config.strategy_url, f"/api/v1/strategy/plans/{plan_id}/confirm"),
        token=token,
        timeout=config.timeout,
    )
    record("strategy.plan.confirm", {"plan_id": plan_id, "status": confirm_body.get("status")})

    backtest_url = build_backtest_url(
        config.backtest_url, config.screener_mode, top_n=config.top_n
    )
    backtest_body = http_json("GET", backtest_url, token=token, timeout=config.timeout)
    require_completed_backtest(backtest_body)
    record("backtest.run", {"status": backtest_body.get("status"), "summary_keys": sorted((backtest_body.get("summary") or {}).keys())[:4]})

    order_body = http_json(
        "POST",
        join_url(config.trade_url, "/api/v1/trade/order"),
        {
            "code": pick["code"],
            "direction": "BUY",
            "volume": 100,
            "price": pick["price"],
            "trade_mode": "paper",
        },
        token=token,
        timeout=config.timeout,
    )
    record("trade.order.paper", {"order_id": order_body.get("order_id"), "status": order_body.get("status")})

    account_body = http_json(
        "GET",
        join_url(config.trade_url, "/api/v1/trade/account?trade_mode=paper"),
        token=token,
        timeout=config.timeout,
    )
    record("trade.account", {"available": account_body.get("available"), "market_value": account_body.get("market_value")})

    return {"status": "ok", "steps": steps, "plan_id": plan_id, "order_id": order_body.get("order_id")}


def main(argv: list[str] | None = None) -> int:
    config = load_config(argv)
    try:
        result = run_smoke(config)
    except SmokeError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
