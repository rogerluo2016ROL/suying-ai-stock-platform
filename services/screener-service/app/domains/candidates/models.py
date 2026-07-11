"""Candidate-pool HTTP contracts owned by the candidates domain."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class CandidatePoolRecordRequest(BaseModel):
    source_module: str = Field(...)
    source_mode: str = Field(...)
    name: str = Field(...)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    candidate_pool_metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: str = Field(default="private")
    data_scope: str = Field(default="account")
    trade_date: Optional[str] = None
    time_slot: Optional[str] = None


class CandidatePoolRecordResponse(BaseModel):
    pool_id: str
    id: Optional[int] = None
    created_at: Optional[str] = None
    fallback_reason: Optional[str] = None


class CandidatePoolQueryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: list[dict[str, Any]] = Field(default_factory=list)
    empty_state: Optional[dict[str, Any]] = None
    fallback_reason: Optional[str] = None
