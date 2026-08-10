import asyncio
import os
import socket
import time
from urllib.request import urlopen, HTTPRedirectHandler, build_opener
from urllib.error import URLError
from .main import SERVICES
from .service_registry import SERVICE_REGISTRY

_PROBE_TIMEOUT = 2  # seconds; a hung service must not stall the whole endpoint

class _NoRedirectHandler(HTTPRedirectHandler):
    """不跟随重定向（避免维护期 302→登录页 200 被误判 ok，issue #16）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_http_opener = build_opener(_NoRedirectHandler())


def _infra_targets() -> list[tuple[str, str, int]]:
    """基础设施 TCP 探活目标。仅在 KRONOS_PG_PORT / KRONOS_REDIS_PORT 显式配置时纳入——
    未配置则跳过（不报 down），避免用错误的默认端口（宿主映射 6432/7379 在容器内不通）
    造成 infra 永远误报 down、status 误判 degraded（issue #16）。"""
    targets: list[tuple[str, str, int]] = []
    pg_port = os.environ.get("KRONOS_PG_PORT")
    if pg_port:
        targets.append(("postgresql", os.environ.get("KRONOS_PG_HOST", "localhost"), int(pg_port)))
    redis_port = os.environ.get("KRONOS_REDIS_PORT")
    if redis_port:
        targets.append(("redis", os.environ.get("KRONOS_REDIS_HOST", "localhost"), int(redis_port)))
    return targets

async def _probe(name: str, base: str) -> tuple[str, dict]:
    try:
        def request():
            with urlopen(base + "/api/v1/health/ready", timeout=2) as response:
                return response.status
        status = await asyncio.to_thread(request)
        return name, {"ready": status == 200, "status_code": status}
    except Exception as exc:
        return name, {"ready": False, "error": str(exc)}

async def probe_services() -> dict[str, dict]:
    targets = {}
    for service in SERVICE_REGISTRY:
        key = "backend-auth" if service.name == "backend" else service.name
        targets.setdefault(SERVICES[service.prefix], key)
    results = await asyncio.gather(*(_probe(name, base) for base, name in targets.items()))
    result = dict(results)
    result["api-gateway"] = {"ready": True, "status_code": 200}
    return result


def _matrix_entry(name: str, port: int, status: str, latency_ms) -> dict:
    return {"name": name, "port": port, "status": status, "latency_ms": latency_ms}


async def _probe_http(name: str, port: int, base: str) -> dict:
    """HTTP 探活微服务（沿用现有 /api/v1/health/ready 路径）。"""
    start = time.perf_counter()

    def request():
        with _http_opener.open(base + "/api/v1/health/ready", timeout=_PROBE_TIMEOUT) as response:
            return response.status

    try:
        await asyncio.to_thread(request)
        return _matrix_entry(name, port, "ok", round((time.perf_counter() - start) * 1000, 1))
    except (socket.timeout, TimeoutError):
        return _matrix_entry(name, port, "timeout", round((time.perf_counter() - start) * 1000, 1))
    except URLError as exc:
        # HTTPError（非 2xx）与连接拒绝都视为 down；reason 为 timeout 时归 timeout。
        status = "timeout" if isinstance(getattr(exc, "reason", None), (socket.timeout, TimeoutError)) else "down"
        latency = round((time.perf_counter() - start) * 1000, 1) if status == "timeout" else None
        return _matrix_entry(name, port, status, latency)
    except Exception:
        return _matrix_entry(name, port, "down", None)


async def _probe_tcp(name: str, host: str, port: int) -> dict:
    """TCP 连接探活（PostgreSQL / Redis，不发任何协议数据）。"""
    start = time.perf_counter()

    def connect():
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT):
            pass

    try:
        await asyncio.to_thread(connect)
        return _matrix_entry(name, port, "ok", round((time.perf_counter() - start) * 1000, 1))
    except (socket.timeout, TimeoutError):
        return _matrix_entry(name, port, "timeout", round((time.perf_counter() - start) * 1000, 1))
    except OSError:
        return _matrix_entry(name, port, "down", None)


async def probe_runtime_matrix() -> list[dict]:
    """并发探活 12 个微服务 + PostgreSQL + Redis，返回状态矩阵。

    每项: {name, port, status: ok|down|timeout, latency_ms: float|null(down)}。
    api-gateway 为 self，直接标记 ok 不自探。
    """
    targets = {}
    for service in SERVICE_REGISTRY:
        key = "backend-auth" if service.name == "backend" else service.name
        targets.setdefault(SERVICES[service.prefix], (key, service.port))
    probes = [_probe_http(name, port, base) for base, (name, port) in targets.items()]
    probes += [_probe_tcp(name, host, port) for name, host, port in _infra_targets()]
    results = await asyncio.gather(*probes)
    return [_matrix_entry("api-gateway", 8080, "ok", 0.0), *results]
