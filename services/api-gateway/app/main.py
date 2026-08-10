import os
"""API Gateway — reverse proxy with rate limiting (urllib async wrapper).

Per CLAUDE.md: microservice HTTP calls use urllib async wrapper
(loop.run_in_executor), not httpx/aiohttp.
"""

import asyncio
import time
from datetime import datetime, timezone
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import URLError, HTTPError

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from kronos_auth import get_current_user_jwt
from kronos_auth.exceptions import UnauthorizedError
from app.service_registry import SERVICE_REGISTRY, sanitize_client_headers

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://localhost:3000").split(","), allow_methods=["*"], allow_headers=["*"])

@app.get("/api/v1/health/live")
async def health_live():
    return {"live": True, "service": "api-gateway", "version": "0.1.0"}

@app.get("/api/v1/health/ready")
async def health_ready():
    from .runtime import probe_services
    services = await probe_services()
    return {"live": True, "ready": all(item.get("ready", False) for item in services.values()), "services": services}

@app.get("/api/v1/runtime/readiness")
async def runtime_readiness(user: dict = Depends(get_current_user_jwt)):
    from .runtime import probe_runtime_matrix
    components = await probe_runtime_matrix()
    # 兼容旧契约: services 只含微服务（不含 PG/Redis），ready 为微服务聚合。
    service_components = [c for c in components if c["name"] not in ("postgresql", "redis")]
    services = {
        c["name"]: {"ready": c["status"] == "ok", "status": c["status"], "latency_ms": c["latency_ms"]}
        for c in service_components
    }
    # 安全收敛（release 门禁 High-1）：infra（PG/Redis 地址/端口/状态）明细仅对
    # admin/internal_analyst 返回；普通登录用户只见微服务聚合，status 也不含 infra。
    privileged = user.get("role") in ("admin", "internal_analyst")
    status_basis = components if privileged else service_components
    body = {
        "live": True,
        "ready": all(c["status"] == "ok" for c in service_components),
        "services": services,
        "status": "ok" if all(c["status"] == "ok" for c in status_basis) else "degraded",
    }
    if privileged:
        body["components"] = components
    return body

_rate_store: dict[str, list[float]] = {}
# P1-8: request counter for periodic eviction of stale rate-store keys.
# _rate_store[ip] is pruned to the last 60s on each hit, but keys with empty
# lists were never removed → unbounded growth over long runs with many IPs.
# Every _GC_INTERVAL requests we sweep the dict and drop keys whose window has
# fully expired, bounding memory.
_rate_request_count = 0
_RATE_GC_INTERVAL = 512

# DEF-3 fix: docker compose 容器内 localhost 指向 api-gateway 自己, 而非目标服务.
# GATEWAY_NETWORK_MODE=compose 时用 compose 服务名 (容器间 DNS); host 模式 uvicorn
# 直起用 localhost. UAT/compose 若漏传 env, 容器内也默认走 compose 服务名。
def _default_network_mode() -> str:
    configured = os.environ.get("GATEWAY_NETWORK_MODE", "").lower()
    if configured:
        return configured
    return "compose" if os.path.exists("/.dockerenv") else ""


_USE_COMPOSE = _default_network_mode() == "compose"
def _svc_url(service) -> str:
    """解析服务 URL: env GATEWAY_<NAME>_HOST > compose 服务名 > localhost."""
    env_name = service.host_env
    if env_name and os.environ.get(env_name):
        host = os.environ[env_name]
    elif _USE_COMPOSE:
        host = service.compose_host
    else:
        host = "localhost"
    return f"http://{host}:{service.port}"


SERVICES = {service.prefix: _svc_url(service) for service in SERVICE_REGISTRY}

_SERVICE_HEALTH_ALIASES = {
    f"{prefix}/health": (base, "/api/health" if prefix in ("/api/v1/auth", "/api/v1/admin") else "/api/v1/health")
    for prefix, base in SERVICES.items()
}


def _resolve_target(full: str, query: str | bytes | None = "") -> str | None:
    """Resolve an incoming gateway path to a target service URL.

    ``/api/v1/<service>/health`` is a gateway convenience alias. Individual
    services expose health at ``/api/v1/health`` rather than under their feature
    prefix, so the gateway rewrites the suffix for frontend/service checks.
    """
    if full in ("/api/health", "/health"):
        return None

    if full in _SERVICE_HEALTH_ALIASES:
        base, health_path = _SERVICE_HEALTH_ALIASES[full]
        target = f"{base}{health_path}"
    else:
        target_base = None
        for prefix, svc in SERVICES.items():
            if full.startswith(prefix):
                target_base = svc
                break
        if not target_base:
            return None
        target = f"{target_base}{full}"

    if query:
        q = query.decode() if isinstance(query, bytes) else str(query)
        target += f"?{q}"
    return target


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


# P2-4 (audit): hop-by-hop (RFC 7230 §6.1) + body-encoding headers that must
# NOT be forwarded when re-emitting an upstream response — urllib has already
# read+decoded the body, so Content-Length / Content-Encoding / Transfer-Encoding
# would corrupt the downstream response if re-emitted. Content-Type is excluded
# here because Response(media_type=…) sets it (avoids a duplicate header).
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
    "content-length", "content-encoding", "content-type",
}


def _forward_headers(upstream_headers) -> dict:
    """Build a headers dict from upstream, stripping hop-by-hop / body-encoding.

    Set-Cookie is excluded here because Starlette's Response(headers=...)
    accepts a plain string map. Cookies are appended as raw headers by
    _proxy_response so multiple Set-Cookie values survive the proxy.
    """
    out: dict[str, str] = {}
    # Normal single-valued headers.
    for k, v in upstream_headers.items():
        if k.lower() in _HOP_BY_HOP or k.lower() == "set-cookie":
            continue
        out[k] = v
    return out


def _forward_cookies(upstream_headers) -> list[str]:
    cookies = upstream_headers.get_all("Set-Cookie") if hasattr(upstream_headers, "get_all") else None
    return list(cookies or [])


def _proxy_response(content: bytes, status_code: int, upstream_headers) -> Response:
    response = Response(
        content=content,
        status_code=status_code,
        headers=_forward_headers(upstream_headers),
        media_type=upstream_headers.get("content-type", "application/json"),
    )
    for cookie in _forward_cookies(upstream_headers):
        response.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
    return response


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workbench_context(request: Request) -> dict:
    return {
        "tenant_id": request.headers.get("X-Tenant-Id") or "public",
        "owner_user_id": request.headers.get("X-Owner-User-Id"),
        "account_id": request.headers.get("X-Trade-Account-Id"),
        "data_scope": request.headers.get("X-Data-Scope") or "public",
        "trade_mode": request.headers.get("X-Trade-Mode") or "paper",
        "role_view": request.headers.get("X-Role-View"),
        "broker_adapter": request.headers.get("X-Broker-Adapter") or "paper",
    }


def _workbench_envelope(module_path: str, request: Request) -> dict:
    module = module_path.strip("/") or "p0"
    return {
        "status": "unavailable",
        "page": {"module": module, "route": f"/{module}", "title": module},
        "context": _workbench_context(request),
        "freshness": {
            "status": "missing",
            "as_of": None,
            "source": "api-gateway",
            "fallback_reason": "real workbench aggregation is not connected",
        },
        "lineage": {},
        "sections": [],
        "actions": [],
    }


@app.get("/api/v1/workbench/{module_path:path}")
async def workbench_page(request: Request, module_path: str):
    return _workbench_envelope(module_path, request)


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
    target = _resolve_target(full, request.url.query)
    if not target:
        return JSONResponse({"detail": f"Not Found: {full}"}, 404)

    # 网关侧 JWT 验签（函数式代理，不走 FastAPI 依赖）。放行规则：
    # - OPTIONS 预检（浏览器不带 Authorization；CORSMiddleware 通常已拦截，双保险）
    # - 各服务 /health 别名（探活必须匿名可达）
    # - /api/v1/auth/*（登录/刷新必须匿名可达；backend 侧自行校验其余 auth 接口）
    # 验通过把 claims 传给 sanitize_client_headers 注入 X-Owner-User-Id；
    # 客户端伪造的 X-Service-Auth / X-Owner-User-Id 一律被剥离。
    claims = None
    if (
        request.method != "OPTIONS"
        and full not in _SERVICE_HEALTH_ALIASES
        and not full.startswith("/api/v1/auth/")
    ):
        try:
            claims = await get_current_user_jwt(request)
        except UnauthorizedError as e:
            return JSONResponse({"detail": e.detail}, status_code=401)

    body = await request.body()
    headers = sanitize_client_headers(
        {k: v for k, v in request.headers.items() if k.lower() not in ("host",)},
        claims,
    )

    loop = asyncio.get_running_loop()

    def _proxy():
        req = UrlRequest(target, data=body, headers=headers, method=request.method)
        return urlopen(req, timeout=30)

    try:
        resp = await loop.run_in_executor(None, _proxy)
        body = resp.read()
        # P2-4 (audit): forward upstream headers (Set-Cookie, X-Request-ID,
        # Cache-Control, …) instead of only Content-Type. Strip hop-by-hop
        # headers (RFC 7230 §6.1) plus Content-Length / Content-Encoding /
        # Transfer-Encoding (body already read+decoded by urllib, re-emitting
        # these would corrupt the downstream response) and Content-Type (set
        # via media_type below to avoid duplication).
        return _proxy_response(body, resp.status, resp.headers)
    except URLError as e:
        return JSONResponse({"detail": "Upstream unavailable", "error": str(e.reason)}, 502)
    except HTTPError as e:
        return _proxy_response(e.read(), e.code, e.headers)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
