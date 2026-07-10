import asyncio
from urllib.request import urlopen
from urllib.error import URLError
from .main import SERVICES

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
    for service, base in SERVICES.items():
        targets.setdefault(base, service.strip("/").split("/")[-1])
    results = await asyncio.gather(*(_probe(name, base) for base, name in targets.items()))
    return dict(results)
