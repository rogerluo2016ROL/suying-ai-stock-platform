#!/usr/bin/env python3
"""B6 platform-chain smoke test against a running trade-service.

This script only submits a paper order. It never uses live mode.

Example:
  SUYING_ACCESS_TOKEN=... python tools/b6_platform_chain_smoke.py \
    --base-url http://localhost:8006 --tenant tenant-alpha --account paper-u7
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


def _request(method: str, url: str, *, token: str | None, headers: dict[str, str], payload: dict | None = None) -> dict:
    request_headers = {
        "Accept": "application/json",
        **headers,
    }
    data = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if token:
        request_headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8") if exc.fp else ""
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {body}") from exc


def _get(base_url: str, path: str, params: dict, *, token: str | None, headers: dict[str, str]) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"
    return _request("GET", url, token=token, headers=headers)


def _post(base_url: str, path: str, payload: dict, *, token: str | None, headers: dict[str, str]) -> dict:
    return _request("POST", f"{base_url.rstrip('/')}{path}", token=token, headers=headers, payload=payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run B6 paper-trading lineage smoke test.")
    parser.add_argument("--base-url", default=os.getenv("TRADE_SERVICE_BASE_URL", "http://localhost:8006"))
    parser.add_argument("--tenant", default=os.getenv("SUYING_TENANT_ID", "tenant-alpha"))
    parser.add_argument("--account", default=os.getenv("SUYING_TRADE_ACCOUNT_ID", "paper-u7"))
    parser.add_argument("--token", default=os.getenv("SUYING_ACCESS_TOKEN"))
    parser.add_argument("--code", default="300750")
    parser.add_argument("--price", type=float, default=218.5)
    parser.add_argument("--volume", type=int, default=100)
    args = parser.parse_args()

    headers = {
        "X-Tenant-Id": args.tenant,
        "X-Trade-Account-Id": args.account,
    }
    suffix = int(time.time())
    lineage = {
        "decision_context_id": f"CTX-b6-smoke-{args.code}-{suffix}",
        "candidate_id": f"CAND-b6-smoke-{args.code}",
        "plan_id": "PLAN-b6-smoke",
    }
    payload = {
        "code": args.code,
        "direction": "BUY",
        "price": args.price,
        "volume": args.volume,
        "trade_mode": "paper",
        **lineage,
    }

    try:
        order = _post(args.base_url, "/api/v1/trade/order", payload, token=args.token, headers=headers)
        verdicts = _get(
            args.base_url,
            "/api/v1/trade/risk-verdicts",
            {"decision_context_id": lineage["decision_context_id"], "page": 1, "page_size": 20},
            token=args.token,
            headers=headers,
        )
        contexts = _get(
            args.base_url,
            "/api/v1/trade/decision-contexts",
            {"decision_context_id": lineage["decision_context_id"], "page": 1, "page_size": 20},
            token=args.token,
            headers=headers,
        )
        orders = _get(
            args.base_url,
            "/api/v1/trade/orders",
            {"code": args.code, "page": 1, "page_size": 20},
            token=args.token,
            headers=headers,
        )
    except Exception as exc:
        print(f"[B6 smoke] FAIL: {exc}", file=sys.stderr)
        return 1

    records = verdicts.get("records", [])
    context_records = contexts.get("records", [])
    order_records = orders.get("orders", [])
    order_id = order.get("order_id")

    ok = (
        order.get("decision_context_id") == lineage["decision_context_id"]
        and any(item.get("decision_context_id") == lineage["decision_context_id"] for item in records)
        and any(item.get("decision_context_id") == lineage["decision_context_id"] for item in context_records)
        and any(item.get("order_id") == order_id for item in order_records)
    )
    if not ok:
        print(json.dumps({
            "order": order,
            "verdicts": verdicts,
            "contexts": contexts,
            "orders": orders,
        }, ensure_ascii=False, indent=2))
        print("[B6 smoke] FAIL: lineage chain did not round-trip", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "ok",
        "order_id": order_id,
        **lineage,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
