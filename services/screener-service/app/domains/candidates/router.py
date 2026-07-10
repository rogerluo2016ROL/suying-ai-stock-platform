"""Candidate HTTP domain router."""

from fastapi import APIRouter

from app.domains.screening import service as _legacy

from app.domains.screening.service import (
    add_watchlist,
    list_watchlist,
    query_candidate_pool,
    record_candidate_pool,
    remove_watchlist,
)

router = APIRouter(tags=["candidates"])
for _route in _legacy.router.routes:
    if _route.path.endswith("/candidate-pool") or _route.path.endswith("/watchlist"):
        router.routes.append(_route)

__all__ = [
    "add_watchlist",
    "list_watchlist",
    "query_candidate_pool",
    "record_candidate_pool",
    "remove_watchlist",
]
