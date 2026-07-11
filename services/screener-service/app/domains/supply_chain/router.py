"""Supply-chain HTTP domain router."""

from fastapi import APIRouter

from app.domains.supply_chain.evidence_review_router import (
    router as evidence_review_router,
)
from app.domains.supply_chain.selection_router import router as selection_router
from app.domains.supply_chain.service import *  # noqa: F401,F403
from app.domains.screening import service as _legacy

router = APIRouter(tags=["supply-chain"])
for _route in _legacy.router.routes:
    if (
        _route.path != "/api/v1/screener/supply-chain/evidence-review/queue"
        and ("/supply-chain/" in _route.path or "/chain/" in _route.path)
    ):
        router.routes.append(_route)
router.include_router(evidence_review_router)
router.include_router(selection_router)
