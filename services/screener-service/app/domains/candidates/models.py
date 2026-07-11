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


class WatchlistAddRequest(BaseModel):
    code: str
    name: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 0
    watchlist_metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: str = "private"
    data_scope: str = "account"


class WatchlistItemResponse(BaseModel):
    id: int
    tenant_id: str
    owner_user_id: Optional[str] = None
    account_id: Optional[str] = None
    visibility: str
    data_scope: str
    code: str
    name: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int
    added_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WatchlistAddResponse(BaseModel):
    record: Optional[WatchlistItemResponse] = None
    fallback_reason: Optional[str] = None


class WatchlistQueryResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: list[WatchlistItemResponse] = Field(default_factory=list)
    empty_state: Optional[dict[str, Any]] = None
    fallback_reason: Optional[str] = None


class WatchlistDeleteResponse(BaseModel):
    deleted: int
    code: Optional[str] = None
    id: Optional[int] = None
    fallback_reason: Optional[str] = None
