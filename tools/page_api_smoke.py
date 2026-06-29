"""Page-level API smoke checks for frontend/backend connectivity.

This complements tools/full_stack_smoke.py. The full-stack smoke proves one
core business chain; this script probes page-critical APIs so we can separate
"page is a prototype" from "page calls an API that is down".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from full_stack_smoke import SmokeError, extract_access_token, http_json, join_url  # noqa: E402


HttpJson = Callable[[str, str, dict[str, Any] | list[Any] | None, str | None, float], dict[str, Any]]


@dataclass(frozen=True)
class SmokeConfig:
    auth_url: str
    screener_url: str
    prediction_url: str
    strategy_url: str
    signal_url: str
    trade_url: str
    backtest_url: str
    diagnosis_url: str
    training_url: str
    gateway_url: str
    email: str
    password: str
    timeout: float
    access_token: str | None = None
    register_name: str = "Suying Smoke User"


@dataclass(frozen=True)
class EndpointCheck:
    name: str
    service: str
    method: str
    path: str
    body: dict[str, Any] | list[Any] | None = None
    auth: bool = True
    action: bool = False
    optional: bool = False


READ_CHECKS: tuple[EndpointCheck, ...] = (
    EndpointCheck("gateway.health", "gateway", "GET", "/health", auth=False),
    EndpointCheck("auth.health", "auth", "GET", "/api/health", auth=False),
    EndpointCheck("screener.health", "screener", "GET", "/api/v1/health", auth=False),
    EndpointCheck("prediction.health", "prediction", "GET", "/api/v1/health", auth=False),
    EndpointCheck("strategy.health", "strategy", "GET", "/api/v1/health", auth=False),
    EndpointCheck("signal.health", "signal", "GET", "/api/v1/health", auth=False),
    EndpointCheck("trade.health", "trade", "GET", "/api/v1/health", auth=False),
    EndpointCheck("backtest.health", "backtest", "GET", "/api/v1/health", auth=False),
    EndpointCheck("diagnosis.health", "diagnosis", "GET", "/api/v1/health", auth=False),
    EndpointCheck("training.health", "training", "GET", "/api/v1/health", auth=False),
    EndpointCheck("screener.modes", "screener", "GET", "/api/v1/screener/modes"),
    EndpointCheck("signal.dashboard-summary", "signal", "GET", "/api/v1/signal/dashboard-summary"),
    EndpointCheck("dashboard.summary", "screener", "GET", "/api/v1/dashboard/summary"),
    EndpointCheck("dashboard.auction", "screener", "GET", "/api/v1/dashboard/auction"),
    EndpointCheck("supply-chain.themes", "screener", "GET", "/api/v1/screener/supply-chain/themes"),
    EndpointCheck("supply-chain.bom", "screener", "GET", "/api/v1/screener/supply-chain/bom"),
    EndpointCheck("supply-chain.workbench", "screener", "GET", "/api/v1/screener/supply-chain/workbench?top_n=20"),
    EndpointCheck(
        "chain.candidates",
        "screener",
        "GET",
        "/api/v1/screener/chain/candidates?filter=all&top_n=20",
        optional=True,
    ),
    EndpointCheck(
        "supply-chain.mapping-quality",
        "screener",
        "GET",
        "/api/v1/screener/supply-chain/mapping-review/quality",
    ),
    EndpointCheck("prediction.status", "prediction", "GET", "/api/v1/prediction/status"),
    EndpointCheck("strategy.templates", "strategy", "GET", "/api/v1/strategy/templates"),
    EndpointCheck("strategy.auto-list", "strategy", "GET", "/api/v1/strategy/list"),
    EndpointCheck("strategy.plans", "strategy", "GET", "/api/v1/strategy/plans"),
    EndpointCheck("signal.live", "signal", "GET", "/api/v1/signal/live?session=intra"),
    EndpointCheck("signal.history", "signal", "GET", "/api/v1/signal/history"),
    EndpointCheck("signal.data-status", "signal", "GET", "/api/v1/signal/data-status"),
    EndpointCheck("signal.sync-schedules", "signal", "GET", "/api/v1/signal/sync-schedules"),
    EndpointCheck("trade.account", "trade", "GET", "/api/v1/trade/account?trade_mode=paper"),
    EndpointCheck("trade.positions", "trade", "GET", "/api/v1/trade/positions?trade_mode=paper"),
    EndpointCheck("trade.orders", "trade", "GET", "/api/v1/trade/orders?trade_mode=paper"),
    EndpointCheck("trade.risk-config", "trade", "GET", "/api/v1/trade/risk-config"),
    EndpointCheck("trade.broker-status", "trade", "GET", "/api/v1/trade/broker/status"),
    EndpointCheck("trade.audit-logs", "trade", "GET", "/api/v1/trade/audit-logs?page=1&page_size=20"),
    EndpointCheck("trade.risk-verdicts", "trade", "GET", "/api/v1/trade/risk-verdicts?page=1&page_size=20"),
    EndpointCheck("trade.decision-contexts", "trade", "GET", "/api/v1/trade/decision-contexts?page=1&page_size=20"),
    EndpointCheck("backtest.factors", "backtest", "GET", "/api/v1/backtest/factors"),
    EndpointCheck("diagnosis.history", "diagnosis", "GET", "/api/v1/diagnosis/history"),
    EndpointCheck("training.models", "training", "GET", "/api/v1/training/models?page=1&page_size=20"),
    EndpointCheck("model-registry.models", "training", "GET", "/api/v1/training/models?page=1&page_size=20"),
    EndpointCheck("training.history", "training", "GET", "/api/v1/training/history?page=1&page_size=20"),
    EndpointCheck("training.schedule", "training", "GET", "/api/v1/training/schedule"),
)

ACTION_CHECKS: tuple[EndpointCheck, ...] = (
    EndpointCheck("screener.run", "screener", "POST", "/api/v1/screener/run?mode=short&top_n=5", action=True),
    EndpointCheck("prediction.predict", "prediction", "POST", "/api/v1/prediction/000001?pred_days=5", action=True),
)


def load_config(argv: list[str] | None = None) -> tuple[SmokeConfig, bool, bool]:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-actions", action="store_true", help="Also run safe action endpoints such as screener.run")
    parser.add_argument("--register-if-needed", action="store_true", help="Register the configured email if login returns 401")
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PAGE_SMOKE_TIMEOUT", os.environ.get("SMOKE_TIMEOUT", "45"))))
    args = parser.parse_args(argv)

    config = SmokeConfig(
        auth_url=os.environ.get("PAGE_SMOKE_AUTH_URL", os.environ.get("SMOKE_AUTH_URL", "http://127.0.0.1:19001")),
        screener_url=os.environ.get("PAGE_SMOKE_SCREENER_URL", os.environ.get("SMOKE_SCREENER_URL", "http://127.0.0.1:18001")),
        prediction_url=os.environ.get("PAGE_SMOKE_PREDICTION_URL", os.environ.get("SMOKE_PREDICTION_URL", "http://127.0.0.1:18002")),
        strategy_url=os.environ.get("PAGE_SMOKE_STRATEGY_URL", os.environ.get("SMOKE_STRATEGY_URL", "http://127.0.0.1:18003")),
        signal_url=os.environ.get("PAGE_SMOKE_SIGNAL_URL", os.environ.get("SMOKE_SIGNAL_URL", "http://127.0.0.1:18004")),
        trade_url=os.environ.get("PAGE_SMOKE_TRADE_URL", os.environ.get("SMOKE_TRADE_URL", "http://127.0.0.1:18006")),
        backtest_url=os.environ.get("PAGE_SMOKE_BACKTEST_URL", os.environ.get("SMOKE_BACKTEST_URL", "http://127.0.0.1:18007")),
        diagnosis_url=os.environ.get("PAGE_SMOKE_DIAGNOSIS_URL", os.environ.get("SMOKE_DIAGNOSIS_URL", "http://127.0.0.1:18009")),
        training_url=os.environ.get("PAGE_SMOKE_TRAINING_URL", os.environ.get("SMOKE_TRAINING_URL", "http://127.0.0.1:18008")),
        gateway_url=os.environ.get("PAGE_SMOKE_GATEWAY_URL", os.environ.get("SMOKE_GATEWAY_URL", "http://127.0.0.1:18080")),
        email=os.environ.get("PAGE_SMOKE_EMAIL", os.environ.get("SMOKE_EMAIL", "admin@suying.ai")),
        password=os.environ.get("PAGE_SMOKE_PASSWORD", os.environ.get("SMOKE_PASSWORD", "Admin123!")),
        timeout=args.timeout,
        access_token=os.environ.get("PAGE_SMOKE_ACCESS_TOKEN") or os.environ.get("SMOKE_ACCESS_TOKEN"),
        register_name=os.environ.get("PAGE_SMOKE_REGISTER_NAME", "Suying Smoke User"),
    )
    return config, args.include_actions, args.register_if_needed


def default_checks(include_actions: bool = False) -> list[EndpointCheck]:
    checks = list(READ_CHECKS)
    if include_actions:
        checks.extend(ACTION_CHECKS)
    return checks


def check_url(check: EndpointCheck, config: SmokeConfig) -> str:
    base = getattr(config, f"{check.service}_url")
    return join_url(base, check.path)


def login(
    config: SmokeConfig,
    http: HttpJson = http_json,
    register_if_needed: bool = False,
) -> str:
    if config.access_token:
        return config.access_token

    try:
        body = http(
            "POST",
            join_url(config.auth_url, "/api/v1/auth/login"),
            body={"email": config.email, "password": config.password},
            token=None,
            timeout=config.timeout,
        )
    except SmokeError as e:
        if not register_if_needed or "401" not in str(e):
            raise
        body = http(
            "POST",
            join_url(config.auth_url, "/api/v1/auth/register"),
            body={"name": config.register_name, "email": config.email, "password": config.password},
            token=None,
            timeout=config.timeout,
        )
    return extract_access_token(body)


def run_check(
    check: EndpointCheck,
    config: SmokeConfig,
    token: str | None,
    include_actions: bool = False,
    http: HttpJson = http_json,
) -> dict[str, Any]:
    if check.action and not include_actions:
        return {
            "name": check.name,
            "service": check.service,
            "status": "skipped",
            "reason": "action check requires --include-actions",
        }

    url = check_url(check, config)
    try:
        body = http(
            check.method,
            url,
            body=check.body,
            token=token if check.auth else None,
            timeout=config.timeout,
        )
    except SmokeError as e:
        status = "warning" if check.optional else "fail"
        return {
            "name": check.name,
            "service": check.service,
            "method": check.method,
            "url": url,
            "status": status,
            "error": str(e),
        }
    except Exception as e:
        status = "warning" if check.optional else "fail"
        return {
            "name": check.name,
            "service": check.service,
            "method": check.method,
            "url": url,
            "status": status,
            "error": str(e),
        }

    return {
        "name": check.name,
        "service": check.service,
        "method": check.method,
        "url": url,
        "status": "ok",
        "keys": sorted(body.keys())[:12],
    }


def run_checks(
    config: SmokeConfig,
    include_actions: bool = False,
    register_if_needed: bool = False,
    http: HttpJson = http_json,
) -> dict[str, Any]:
    checks = default_checks(include_actions=include_actions)
    public_checks = [check for check in checks if not check.auth]
    private_checks = [check for check in checks if check.auth]

    results = [
        run_check(check, config, token=None, include_actions=include_actions, http=http)
        for check in public_checks
    ]

    try:
        token = login(config, http=http, register_if_needed=register_if_needed)
    except SmokeError as e:
        results.append({
            "name": "auth.login",
            "service": "auth",
            "method": "POST",
            "url": join_url(config.auth_url, "/api/v1/auth/login"),
            "status": "fail",
            "error": str(e),
        })
        return {
            "status": "fail",
            "include_actions": include_actions,
            "checks": results,
        }

    results.extend(
        run_check(check, config, token, include_actions=include_actions, http=http)
        for check in private_checks
    )
    status = "ok" if not any(item["status"] == "fail" for item in results) else "fail"
    return {
        "status": status,
        "include_actions": include_actions,
        "checks": results,
    }


def main(argv: list[str] | None = None) -> int:
    config, include_actions, register_if_needed = load_config(argv)
    try:
        result = run_checks(config, include_actions=include_actions, register_if_needed=register_if_needed)
    except SmokeError as e:
        print(json.dumps({"status": "fail", "step": "auth.login", "error": str(e)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
