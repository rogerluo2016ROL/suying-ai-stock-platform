"""API Gateway — unified reverse-proxy routes to backend micro-services.

All routes go through JWT auth middleware. Auth endpoints are proxied to the auth
service directly (login/register don't require a pre-existing token). Admin routes
require the "admin" role checked at the gateway before forwarding.
"""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.main import get_current_user, rate_limiter, require_role

logger = logging.getLogger("api-gateway")

router = APIRouter()

# ── Backend service addresses ──
BACKENDS: dict[str, str] = {
    "auth":      "http://localhost:9001",
    "screener":  "http://localhost:8001",
    "prediction":"http://localhost:8002",
    "strategy":  "http://localhost:8003",
    "signal":    "http://localhost:8004",
    "alert":     "http://localhost:8005",
    "trade":     "http://localhost:8006",
    "backtest":  "http://localhost:8007",
    "training":  "http://localhost:8008",
    "diagnosis": "http://localhost:8009",
}

# Shared httpx client (reused across requests)
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _client


# ── Proxy helper ──


async def _proxy(
    request: Request,
    service: str,
    path_prefix: str,
    auth_required: bool = True,
    admin_only: bool = False,
):
    """Forward a request to a backend service, preserving headers and body.

    Args:
        request: Incoming FastAPI request.
        service: Key into BACKENDS dict.
        path_prefix: The prefix to strip from the URL path (e.g. "/api/v1/screener").
        auth_required: If True, enforce JWT auth and forward the Authorization header.
        admin_only: If True, additionally require the "admin" role.
    """
    backend = BACKENDS.get(service)
    if not backend:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unknown backend service: {service}",
        )

    # Build target URL: strip the prefix, append the rest
    remaining = request.url.path
    if remaining.startswith(path_prefix):
        remaining = remaining[len(path_prefix):]
    if not remaining.startswith("/"):
        remaining = "/" + remaining
    # Preserve query string
    qs = request.url.query
    target_url = f"{backend}{remaining}"
    if qs:
        target_url += f"?{qs}"

    logger.info("Proxy %s %s -> %s", request.method, request.url.path, target_url)

    # Build forwarded headers
    headers = dict(request.headers)
    # Remove hop-by-hop headers
    for h in ("host", "transfer-encoding", "connection"):
        headers.pop(h, None)
    # Ensure Host matches backend
    headers["host"] = backend.split("://", 1)[1]

    # Read body
    body = await request.body()

    client = await _get_client()
    try:
        resp = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
        )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Backend {service} unreachable",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Backend {service} timeout",
        )

    # Strip hop-by-hop from response
    resp_headers = dict(resp.headers)
    for h in ("transfer-encoding", "connection", "keep-alive"):
        resp_headers.pop(h, None)

    return StreamingResponse(
        content=resp.aiter_bytes(),
        status_code=resp.status_code,
        headers=resp_headers,
    )


# ── Auth routes (no pre-auth required, applied by auth service itself) ──

@router.api_route(
    "/api/v1/auth/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter)],
)
async def proxy_auth(request: Request):
    """Forward all auth requests to auth service (port 9001).

    Auth routes handle their own authentication (login, register, refresh).
    The gateway does NOT enforce JWT on these — it just proxies and rate-limits.
    """
    return await _proxy(request, "auth", "/api/v1/auth", auth_required=False)


# ── Screener routes ──

@router.api_route(
    "/api/v1/screener/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_screener(request: Request):
    return await _proxy(request, "screener", "/api/v1/screener")


# ── Prediction routes ──

@router.api_route(
    "/api/v1/prediction/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_prediction(request: Request):
    return await _proxy(request, "prediction", "/api/v1/prediction")


# ── Strategy routes ──

@router.api_route(
    "/api/v1/strategy/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_strategy(request: Request):
    return await _proxy(request, "strategy", "/api/v1/strategy")


# ── Signal routes ──

@router.api_route(
    "/api/v1/signal/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_signal(request: Request):
    return await _proxy(request, "signal", "/api/v1/signal")


# ── Alert routes ──

@router.api_route(
    "/api/v1/alert/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_alert(request: Request):
    return await _proxy(request, "alert", "/api/v1/alert")


# ── Trade routes ──

@router.api_route(
    "/api/v1/trade/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_trade(request: Request):
    return await _proxy(request, "trade", "/api/v1/trade")


# ── Backtest routes (admin only) ──

@router.api_route(
    "/api/v1/backtest/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(require_role("admin"))],
)
async def proxy_backtest(request: Request):
    return await _proxy(request, "backtest", "/api/v1/backtest", admin_only=True)


# ── Training routes (admin only) ──

@router.api_route(
    "/api/v1/training/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(require_role("admin"))],
)
async def proxy_training(request: Request):
    return await _proxy(request, "training", "/api/v1/training", admin_only=True)


# ── Diagnosis routes ──

@router.api_route(
    "/api/v1/diagnosis/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    dependencies=[Depends(rate_limiter), Depends(get_current_user)],
)
async def proxy_diagnosis(request: Request):
    return await _proxy(request, "diagnosis", "/api/v1/diagnosis")
