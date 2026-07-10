"""Screening HTTP domain router, preserving the public Screener prefix."""

from fastapi import APIRouter

from app.domains.screening import service as _legacy

router = APIRouter(tags=["screening"])
for _route in _legacy.router.routes:
    if not any(token in _route.path for token in ("/supply-chain/", "/chain/", "/candidate-pool", "/watchlist")):
        router.routes.append(_route)
