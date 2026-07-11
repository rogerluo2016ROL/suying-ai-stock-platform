"""HTTP routes for supply-chain selection V2."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.domains.supply_chain import selection_service
from app.domains.supply_chain.models import (
    SelectionBatchCalculateRequest,
    SelectionCandidateResponse,
    SelectionStockDetailResponse,
)
from app.domains.supply_chain.selection_repository import MissingSelectionTables


router = APIRouter(
    prefix="/api/v1/supply-chain/selection",
    tags=["supply-chain-selection"],
)


def _unavailable(exc: MissingSelectionTables) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"missing_tables": exc.tables},
    )


def _invalid(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": str(exc)})


@router.get("/candidates", response_model=SelectionCandidateResponse)
def candidates(
    chain_id: str,
    trade_date: date,
    pool: Literal["A", "B", "C", "D"] | None = None,
    model_version: str = "v2.0",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        return selection_service.list_selection_candidates(
            chain_id=chain_id,
            trade_date=trade_date,
            pool=pool,
            model_version=model_version,
            limit=limit,
            offset=offset,
        )
    except MissingSelectionTables as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.get("/stocks/{code}", response_model=SelectionStockDetailResponse)
def stock_detail(
    code: str,
    chain_id: str,
    trade_date: date,
    model_version: str = "v2.0",
):
    try:
        return selection_service.get_stock_selection_detail(
            code=code,
            chain_id=chain_id,
            trade_date=trade_date,
            model_version=model_version,
        )
    except MissingSelectionTables as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        raise _invalid(exc) from exc


@router.post("/batch-score")
def batch_score(request: SelectionBatchCalculateRequest):
    try:
        return selection_service.batch_calculate_selection(request)
    except MissingSelectionTables as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        raise _invalid(exc) from exc
