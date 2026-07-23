"""Screener 请求/响应 Pydantic 模型（从 service.py 拆出，零行为变化）。"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Policy Interpretation Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class PolicyInterpretRequest(BaseModel):
    """Request model for policy interpretation endpoint."""

    text: str = Field(..., description="Policy document text to interpret")
    source: Optional[dict[str, Any]] = Field(
        default=None, description="Source metadata with title/published_at"
    )
    persist: bool = Field(default=False, description="Persist result to PG")
    provider: str = Field(default="deepseek", description="LLM provider to use")


class SupplyChainMappingReviewRequest(BaseModel):
    decision: str = Field(..., description="verified, rejected, needs_more_evidence, or pending_review")
    reviewer: str = Field(default="system", description="Reviewer name or operator id")
    note: str = Field(default="", description="Short review note")


class BusinessTagEvidenceReviewRequest(BaseModel):
    review_status: str = Field(..., description="approved, rejected, or pending_review")
    reviewer: str = Field(..., min_length=1, description="Asserted reviewer name or operator id")
    note: str = Field(..., min_length=1, description="Short review note")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    stage_after: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional R/C stage after approval, e.g. {'research_stage':'R3','commercialization_stage':'C2'}",
    )


class BusinessTagEvidenceExtractRequest(BaseModel):
    source_type: str = Field(..., description="announcement_title, research_title, irm_qa, manual, etc.")
    source_id: Optional[str] = Field(default=None)
    title: str = Field(default="")
    excerpt: str = Field(default="")
    original_url: Optional[str] = Field(default=None)
    event_date: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    persist: bool = Field(default=True, description="Whether to persist as pending_review evidence event")


class BusinessTagEvidenceBatchExtractRequest(BaseModel):
    mapping_id: Optional[str] = Field(default=None, description="Limit extraction to one business-tag mapping")
    code: Optional[str] = Field(default=None, description="Limit extraction to one stock code")
    source_types: list[str] = Field(
        default_factory=lambda: ["announcement_title", "research_title", "irm_qa", "interact_qa"],
        description="Candidate source types to scan",
    )
    limit: int = Field(default=50, ge=1, le=500)
    persist: bool = Field(default=True)


class BusinessTagThreeHighScoreRequest(BaseModel):
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist the score snapshot")


class BusinessTagExpectationGapScoreRequest(BaseModel):
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist the score snapshot")
    market_expectation_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Optional market expectation score; defaults to neutral 50 when unavailable",
    )


class BusinessTagBatchScoreRequest(BaseModel):
    code: Optional[str] = Field(default=None, description="Limit batch scoring to one stock code")
    node_id: Optional[str] = Field(default=None, description="Limit batch scoring to one supply-chain node")
    status: Optional[str] = Field(default=None, description="Limit batch scoring to one mapping status")
    score_types: list[str] = Field(
        default_factory=lambda: ["three_high", "expectation_gap"],
        description="Score types to run: three_high and/or expectation_gap",
    )
    trade_date: Optional[str] = Field(default=None, description="Score date, default today")
    persist: bool = Field(default=True, description="Whether to persist score snapshots")
    market_expectation_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    limit: int = Field(default=100, ge=1, le=500)


class SupplyChainRefreshWorkflowRequest(BaseModel):
    mapping_id: Optional[str] = Field(default=None, description="Limit refresh to one business-tag mapping")
    code: Optional[str] = Field(default=None, description="Limit refresh to one stock code")
    node_id: Optional[str] = Field(default=None, description="Limit scoring to one supply-chain node")
    status: Optional[str] = Field(default=None, description="Limit scoring to one mapping status")
    source_types: list[str] = Field(
        default_factory=lambda: ["announcement_title", "research_title", "irm_qa", "interact_qa"],
        description="Candidate source types to scan for evidence",
    )
    score_types: list[str] = Field(
        default_factory=lambda: ["three_high", "expectation_gap"],
        description="Score types to run after evidence extraction",
    )
    rank_types: list[str] = Field(
        default_factory=lambda: ["value", "expectation_gap"],
        description="Ranking previews to return after scoring",
    )
    trade_date: Optional[str] = Field(default=None)
    persist: bool = Field(default=True, description="Whether to persist evidence and score snapshots")
    market_expectation_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    include_evidence_extract: bool = Field(default=True)
    include_scores: bool = Field(default=True)
    include_rankings: bool = Field(default=True)
    evidence_limit: int = Field(default=50, ge=1, le=500)
    score_limit: int = Field(default=100, ge=1, le=500)
    top_n: int = Field(default=20, ge=1, le=200)


class SupplyChainInferredMaterializeRequest(BaseModel):
    theme_id: Optional[str] = Field(default="future_industry_core", description="Limit to one policy theme")
    node_id: Optional[str] = Field(default=None, description="Limit to one BOM/chain node")
    code: Optional[str] = Field(default=None, description="Limit to one stock code")
    status: Optional[str] = Field(default=None, description="Limit to mapping status")
    trade_date: Optional[str] = Field(default=None, description="Materialization date, default today")
    limit: int = Field(default=5000, ge=1, le=20000)
    persist: bool = Field(default=True, description="Whether to persist inferred records")
    include_three_high: bool = Field(default=True, description="Whether to persist inference-only three-high baseline")
    include_company_chain_projection: bool = Field(
        default=True,
        description="Whether to copy inferred three-high summary back to company_chain_mapping.three_factors",
    )


class InterpretationResult(BaseModel):
    """Structured interpretation result from LLM."""

    summary: str = Field(default="", description="Brief summary of the policy")
    industry_themes: list[dict[str, Any]] = Field(
        default_factory=list, description="Identified industry themes"
    )
    bom_nodes: list[str] = Field(
        default_factory=list, description="Supply-chain BOM nodes mentioned"
    )
    investment_logic: str = Field(default="", description="Investment thesis")
    risk_factors: list[dict[str, Any]] = Field(
        default_factory=list, description="Risk factors identified"
    )


class LLMUsageInfo(BaseModel):
    """Token usage telemetry from LLM call."""

    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    provider: str = Field(default="")
    model: str = Field(default="")


class PolicyInterpretResponse(BaseModel):
    """Response model for policy interpretation endpoint."""

    status: str = Field(..., description="ok, disabled, or error")
    interpretation_result: InterpretationResult = Field(
        default_factory=InterpretationResult
    )
    usage: LLMUsageInfo = Field(default_factory=LLMUsageInfo)
    persisted: bool = Field(default=False)
    reason: Optional[str] = Field(default=None, description="Error reason if status!=ok")


# ─────────────────────────────────────────────────────────────────────────────
# Candidate Pool REST API — 解封"选股 → 加候选池 → 决策"咽喉
#
# Scope（tenant_id / owner_user_id / account_id）全部从认证头注入，前端绝不传明文。
# pool_id 由后端按 POOL-{mode}-{trade_date}-{time_slot}-{scope} 生成（幂等 UPSERT）。
# ─────────────────────────────────────────────────────────────────────────────

class _LegacyCandidatePoolRecordRequest(BaseModel):
    """POST /screener/candidate-pool 入参。

    scope 字段（tenant/owner/account）不在此处——由后端从认证头注入。
    """

    source_module: str = Field(..., description="来源模块，如 screener / strategy / signal")
    source_mode: str = Field(..., description="来源模式，如 leader_auction / bi_trend_launch")
    name: str = Field(..., description="候选池名称")
    candidates: list[dict[str, Any]] = Field(
        default_factory=list, description="候选快照列表（每项含 candidate_id/code/score 等）"
    )
    candidate_pool_metadata: dict[str, Any] = Field(
        default_factory=dict, description="附加元数据（trade_date/time_slot/top_n 等）"
    )
    visibility: str = Field(default="private", description="可见性：private / tenant_shared / public")
    data_scope: str = Field(default="account", description="数据范围：account / tenant / public")
    trade_date: Optional[str] = Field(default=None, description="交易日 YYYY-MM-DD，用于 pool_id 生成")
    time_slot: Optional[str] = Field(default=None, description="时段 HH:MM，用于 pool_id 生成")


class _LegacyCandidatePoolRecordResponse(BaseModel):
    """POST /screener/candidate-pool 响应。"""

    pool_id: str = Field(..., description="后端生成的候选池 ID")
    id: Optional[int] = Field(default=None, description="数据库行 id（PG 不可用时为 None）")
    created_at: Optional[str] = Field(default=None, description="创建时间 ISO（PG 不可用时为 None）")
    fallback_reason: Optional[str] = Field(
        default=None, description="非空表示降级（如 PG 不可用、db 未注入），已忽略写入"
    )


class _LegacyCandidatePoolQueryResponse(BaseModel):
    """GET /screener/candidate-pool 响应。"""

    total: int = Field(..., description="满足 scope 过滤的总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    records: list[dict[str, Any]] = Field(default_factory=list, description="候选池记录列表")
    empty_state: Optional[dict[str, Any]] = Field(
        default=None, description="无数据时的空态提示（含 hint / suggestion）"
    )
    fallback_reason: Optional[str] = Field(
        default=None, description="非空表示降级（如 PG 不可用、db 未注入）"
    )
