"""Request and response contracts for supply-chain selection V2."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


PoolCode = Literal["A", "B", "C", "D"]
EvidenceLevel = Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6"]


class SelectionBatchCalculateRequest(BaseModel):
    chain_id: str
    trade_date: date
    mapping_ids: list[str] = Field(default_factory=list)
    model_version: str = "v2.0"
    dry_run: bool = True


class SelectionCandidate(BaseModel):
    code: str
    pool_code: PoolCode
    primary_mapping_id: str
    secondary_mappings: list[dict[str, Any]] = Field(default_factory=list)
    benefit_score: float | None = None
    expectation_gap_score: float | None = None
    catalyst_score: float | None = None
    risk_score: float | None = None
    confidence_score: float | None = None
    opportunity_score: float | None = None
    evidence_level: EvidenceLevel
    stock_score: float | None = None
    diversification_bonus: float = 0.0
    data_limitations: list[str] = Field(default_factory=list)


class SelectionCandidateResponse(BaseModel):
    trade_date: date
    chain_id: str
    model_version: str
    items: list[SelectionCandidate] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)


class SelectionStockDetailResponse(BaseModel):
    code: str
    chain_id: str
    trade_date: date
    model_version: str = "v2.0"
    mappings: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
