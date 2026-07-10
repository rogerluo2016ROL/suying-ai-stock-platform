import asyncio
from urllib.request import urlopen
from urllib.error import URLError
from .service_registry import SERVICE_REGISTRY

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
        targets.setdefault(f"http://{service.compose_host}:{service.port}", key)
    results = await asyncio.gather(*(_probe(name, base) for base, name in targets.items()))
    result = dict(results)
    result["api-gateway"] = {"ready": True, "status_code": 200}
    return result
