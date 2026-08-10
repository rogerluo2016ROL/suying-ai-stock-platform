import asyncio
import os
import socket
import time
from urllib.request import urlopen
from urllib.error import URLError
from .main import SERVICES
from .service_registry import SERVICE_REGISTRY

_PROBE_TIMEOUT = 2  # seconds; a hung service must not stall the whole endpoint

# 基础设施 TCP 探活目标（端口与 docker-compose 本机映射一致，可用 env 覆盖）。
_INFRA_TARGETS = (
    ("postgresql", os.environ.get("KRONOS_PG_HOST", "localhost"), int(os.environ.get("KRONOS_PG_PORT", "6432"))),
    ("redis", os.environ.get("KRONOS_REDIS_HOST", "localhost"), int(os.environ.get("KRONOS_REDIS_PORT", "7379"))),
)

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
        with urlopen(base + "/api/v1/health/ready", timeout=_PROBE_TIMEOUT) as response:
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
    probes += [_probe_tcp(name, host, port) for name, host, port in _INFRA_TARGETS]
    results = await asyncio.gather(*probes)
    return [_matrix_entry("api-gateway", 8080, "ok", 0.0), *results]
