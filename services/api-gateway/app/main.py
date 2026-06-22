import os
"""API Gateway — reverse proxy with rate limiting (urllib async wrapper).

Per CLAUDE.md: microservice HTTP calls use urllib async wrapper
(loop.run_in_executor), not httpx/aiohttp.
"""

import asyncio
import time
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError, HTTPError

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://localhost:3000").split(","), allow_methods=["*"], allow_headers=["*"])

_rate_store: dict[str, list[float]] = {}
# P1-8: request counter for periodic eviction of stale rate-store keys.
# _rate_store[ip] is pruned to the last 60s on each hit, but keys with empty
# lists were never removed → unbounded growth over long runs with many IPs.
# Every _GC_INTERVAL requests we sweep the dict and drop keys whose window has
# fully expired, bounding memory.
_rate_request_count = 0
_RATE_GC_INTERVAL = 512

# DEF-3 fix: docker compose 容器内 localhost 指向 api-gateway 自己, 而非目标服务.
# GATEWAY_NETWORK_MODE=compose 时用 compose 服务名 (容器间 DNS); default (host 模式
# uvicorn 直起) 用 localhost. 逐服务 host 覆盖 env (GATEWAY_<NAME>_HOST) 优先级最高.
_USE_COMPOSE = os.environ.get("GATEWAY_NETWORK_MODE", "").lower() == "compose"
_COMPOSE_HOSTS = {
    "/api/v1/auth": "backend",
    "/api/v1/admin": "backend",
    "/api/v1/screener": "screener-service",
    "/api/v1/prediction": "prediction-service",
    "/api/v1/strategy": "strategy-service",
    "/api/v1/signal": "signal-service",
    "/api/v1/dashboard": "signal-service",  # signal-service hosts dashboard aggregation
    "/api/v1/data": "signal-service",        # signal-service hosts data-status/sync
    "/api/v1/alert": "alert-service",
    "/api/v1/trade": "trade-service",
    "/api/v1/backtest": "backtest-service",
    "/api/v1/training": "training-service",
    "/api/v1/diagnosis": "diagnosis-service",
}
_HOST_ENV = {
    "/api/v1/auth": "GATEWAY_BACKEND_HOST",
    "/api/v1/admin": "GATEWAY_BACKEND_HOST",
    "/api/v1/screener": "GATEWAY_SCREENER_HOST",
    "/api/v1/prediction": "GATEWAY_PREDICTION_HOST",
    "/api/v1/strategy": "GATEWAY_STRATEGY_HOST",
    "/api/v1/signal": "GATEWAY_SIGNAL_HOST",
    "/api/v1/dashboard": "GATEWAY_SIGNAL_HOST",
    "/api/v1/data": "GATEWAY_SIGNAL_HOST",
    "/api/v1/alert": "GATEWAY_ALERT_HOST",
    "/api/v1/trade": "GATEWAY_TRADE_HOST",
    "/api/v1/backtest": "GATEWAY_BACKTEST_HOST",
    "/api/v1/training": "GATEWAY_TRAINING_HOST",
    "/api/v1/diagnosis": "GATEWAY_DIAGNOSIS_HOST",
}


def _svc_url(prefix: str, port: int) -> str:
    """解析服务 URL: env GATEWAY_<NAME>_HOST > compose 服务名 > localhost."""
    env_name = _HOST_ENV.get(prefix)
    if env_name and os.environ.get(env_name):
        host = os.environ[env_name]
    elif _USE_COMPOSE:
        host = _COMPOSE_HOSTS.get(prefix, "localhost")
    else:
        host = "localhost"
    return f"http://{host}:{port}"


SERVICES = {
    "/api/v1/auth": _svc_url("/api/v1/auth", 9001),
    "/api/v1/admin": _svc_url("/api/v1/admin", 9001),
    "/api/v1/screener": _svc_url("/api/v1/screener", 8001),
    "/api/v1/prediction": _svc_url("/api/v1/prediction", 8002),
    "/api/v1/strategy": _svc_url("/api/v1/strategy", 8003),
    "/api/v1/signal": _svc_url("/api/v1/signal", 8004),
    "/api/v1/dashboard": _svc_url("/api/v1/dashboard", 8004),
    "/api/v1/data": _svc_url("/api/v1/data", 8004),
    "/api/v1/alert": _svc_url("/api/v1/alert", 8005),
    "/api/v1/trade": _svc_url("/api/v1/trade", 8006),
    "/api/v1/backtest": _svc_url("/api/v1/backtest", 8007),
    "/api/v1/training": _svc_url("/api/v1/training", 8008),
    "/api/v1/diagnosis": _svc_url("/api/v1/diagnosis", 8009),
}


def _rate_check(ip: str) -> bool:
    global _rate_request_count
    now = time.time()
    w = [t for t in _rate_store.get(ip, []) if now - t < 60]
    # P1-8: drop the key when its window is empty instead of retaining a stale
    # empty list (which previously kept the IP in the dict forever).
    if w:
        _rate_store[ip] = w
    elif ip in _rate_store:
        del _rate_store[ip]
    if len(w) >= 60:
        return False
    w.append(now)
    _rate_store[ip] = w
    # P1-8: periodic full sweep — evict any other keys whose 60s window has
    # fully expired (covers IPs that stop sending before their next hit).
    _rate_request_count += 1
    if _rate_request_count % _RATE_GC_INTERVAL == 0:
        stale = [k for k, ts in _rate_store.items() if not any(now - t < 60 for t in ts)]
        for k in stale:
            del _rate_store[k]
    return True


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def gateway(request: Request, path: str):
    # Health check
    if path in ("api/health", "health"):
        return {"status": "healthy", "gateway": "api-gateway:8080"}

    # Rate limit
    ip = request.client.host if request.client else "unknown"
    if not _rate_check(ip):
        return JSONResponse({"detail": "Rate limit exceeded"}, 429)

    # Route mapping
    full = "/" + path
    target_base = None
    for prefix, svc in SERVICES.items():
        if full.startswith(prefix):
            target_base = svc
            break

    if not target_base:
        return JSONResponse({"detail": f"Not Found: {full}"}, 404)

    target = f"{target_base}{full}"
    if request.url.query:
        q = request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)
        target += f"?{q}"

    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host",)}

    loop = asyncio.get_running_loop()

    def _proxy():
        req = UrlRequest(target, data=body, headers=headers, method=request.method)
        return urlopen(req, timeout=30)

    try:
        resp = await loop.run_in_executor(None, _proxy)
        return Response(
            content=resp.read(),
            status_code=resp.status,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except URLError as e:
        return JSONResponse({"detail": "Upstream unavailable", "error": str(e.reason)}, 502)
    except HTTPError as e:
        return Response(
            content=e.read(),
            status_code=e.code,
            media_type=e.headers.get("content-type", "application/json"),
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
