"""Pydantic schemas for diagnosis-service — PRD AC-12.1~12.7.

Matches the contracts defined in docs/adr/005-stock-diagnosis.md.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════

class RecommendationGrade(str, Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    HOLD = "持有"
    REDUCE = "减仓"
    SELL = "卖出"


class DimensionStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"


# ═══════════════════════════════════════════════════════════════════════════
# Dimension Sub-Models
# ═══════════════════════════════════════════════════════════════════════════

class DimensionScore(BaseModel):
    """Single dimension scoring result."""
    name: str = Field(..., description="Dimension name (cn)")
    score: float = Field(..., ge=0, le=100, description="Normalized score 0-100")
    weight: float = Field(..., ge=0, le=1, description="Weight in overall score")
    grade: str = Field(..., description="Letter grade A/B/C/D/E")
    status: DimensionStatus = Field(default=DimensionStatus.AVAILABLE)
    details: Optional[Dict[str, Any]] = Field(default=None, description="Dimension-specific detail fields")
    signals: Optional[List[str]] = Field(default=None, description="Key signals for this dimension")


class TechnicalDimension(DimensionScore):
    """Technical dimension (40%) — 25-factor composite."""
    factor_scores: Optional[Dict[str, float]] = Field(default=None, description="Individual factor scores")
    trend: Optional[str] = Field(default=None, description="Trend assessment")


class CapitalFlowDimension(DimensionScore):
    """Capital flow dimension (25%) — northbound/margin/institutional."""
    northbound_net: Optional[float] = Field(default=None, description="北向净流入 (万元)")
    margin_balance: Optional[float] = Field(default=None, description="融资余额 (万元)")
    leaderboard_net: Optional[float] = Field(default=None, description="龙虎榜净买入 (万元)")
    main_force_flow: Optional[float] = Field(default=None, description="主力资金净流入 (万元)")


class FundamentalDimension(DimensionScore):
    """Fundamental dimension (20%) — PE/ROE/growth/debt."""
    pe_percentile: Optional[float] = Field(default=None, description="PE 历史分位 (%)")
    roe: Optional[float] = Field(default=None, description="ROE (%)")
    revenue_growth: Optional[float] = Field(default=None, description="营业收入增速 (%)")
    debt_ratio: Optional[float] = Field(default=None, description="资产负债率 (%)")


class AIPredictDimension(DimensionScore):
    """AI prediction dimension (10%) — Kronos forecast."""
    pred_return: Optional[float] = Field(default=None, description="预测收益 (%)")
    pred_30d_close: Optional[float] = Field(default=None, description="30日预测收盘价")
    confidence: Optional[float] = Field(default=None, ge=0, le=1, description="预测置信度")
    inflection_days: Optional[List[int]] = Field(default=None, description="趋势拐点日")
    max_drawdown: Optional[float] = Field(default=None, description="最大回撤 (%)")


class SentimentDimension(DimensionScore):
    """Sentiment dimension (5%) — news + research."""
    news_sentiment: Optional[float] = Field(default=None, description="新闻情感分 (-1 to 1)")
    research_rating: Optional[str] = Field(default=None, description="最新研报评级")
    analyst_target: Optional[float] = Field(default=None, description="分析师目标价")


# ═══════════════════════════════════════════════════════════════════════════
# Diagnosis Report
# ═══════════════════════════════════════════════════════════════════════════

class DiagnosisReport(BaseModel):
    """Complete five-dimension diagnosis report."""
    code: str = Field(..., description="Stock code")
    overall_score: float = Field(..., ge=0, le=100, description="Overall score 0-100")
    grade: str = Field(..., description="Letter grade (A+/A/B+/B/C+/C/D/E)")
    recommendation: RecommendationGrade = Field(..., description="五级操作建议")
    recommendation_reason: str = Field(..., description="操作建议理由")
    dimensions: Dict[str, DimensionScore] = Field(..., description="Five dimension scores")
    key_levels: Dict[str, float] = Field(..., description="Support/resistance/stop-loss levels")
    risk_warnings: List[str] = Field(default_factory=list, description="风险提示")
    kronos_available: bool = Field(default=True, description="Kronos prediction availability")
    degraded: bool = Field(default=False, description="Whether diagnosis ran in degraded mode")
    degraded_dimensions: List[str] = Field(default_factory=list, description="Dimensions that were degraded/unavailable")
    created_at: Optional[datetime] = Field(default=None)


class DiagnosisAnalyzeRequest(BaseModel):
    """Request to run a stock diagnosis."""
    code: str = Field(..., description="Stock code (e.g. 000001, 300750)")
    force_refresh: bool = Field(default=False, description="Skip cache, force recalculation")


class DiagnosisCompareRequest(BaseModel):
    """Request to compare multiple stocks."""
    codes: List[str] = Field(..., min_length=2, max_length=5, description="Stock codes (2-5)")
    dimensions: Optional[List[str]] = Field(
        default=None,
        description="Dimensions to compare; None = all five"
    )
    force_refresh: bool = Field(default=False)


class DiagnosisCompareResponse(BaseModel):
    """Multi-stock comparison result."""
    stocks: List[DiagnosisReport] = Field(..., description="Diagnosis for each stock")
    ranking: List[Dict[str, Any]] = Field(..., description="Ranked by overall score")
    dimension_comparison: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict, description="Per-dimension comparison matrix"
    )


class DiagnosisHistoryItem(BaseModel):
    """Diagnosis history record."""
    id: int
    user_id: str
    code: str
    overall_score: float
    grade: str
    recommendation: str
    report: Dict[str, Any]
    created_at: datetime


class PaginatedDiagnosisHistory(BaseModel):
    """Paginated diagnosis history."""
    items: List[DiagnosisHistoryItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
