"""Supply-chain HTTP domain router."""

from fastapi import APIRouter

from app.domains.supply_chain.service import *  # noqa: F401,F403
from app.domains.screening import service as _legacy

router = APIRouter(tags=["supply-chain"])
for _route in _legacy.router.routes:
    if "/supply-chain/" in _route.path or "/chain/" in _route.path:
        router.routes.append(_route)
