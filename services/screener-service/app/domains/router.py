"""Composition root for the three Screener HTTP domains."""

from fastapi import APIRouter

from app.domains.candidates.router import router as candidates_router
from app.domains.screening.router import router as screening_router
from app.domains.supply_chain.router import router as supply_chain_router

router = APIRouter()
router.include_router(screening_router)
router.include_router(candidates_router)
router.include_router(supply_chain_router)
