// P2-08: extracted type definitions for the Diagnosis page.
// These mirror the backend Pydantic DiagnosisReport shapes + the frontend
// transformed view model (DiagnosisResult). Pure types — zero runtime risk.

export interface FactorDetail {
  name: string
  score: number
  weight: number
  direction: 'bullish' | 'bearish' | 'neutral'
  detail?: string
}

export interface CapitalFlow {
  north_bound: { net_inflow: number; trend: string }
  margin: { balance: number; ratio: number }
  dragon_tiger: { net_buy: number; institutions: number }
}

export interface Fundamentals {
  pe: number
  pb: number
  roe: number
  revenue_growth: number
  profit_growth: number
  debt_ratio: number
  market_cap: number
}

export interface SentimentData {
  news_score: number
  news_count: number
  research_rating: string
  research_target: number
  social_sentiment: number
}

export interface PredictionPoint {
  date: string
  open: number
  close: number
  high: number
  low: number
}

// ── Backend-aligned interfaces (matching Pydantic DiagnosisReport) ──

export interface DimensionScore {
  name: string
  score: number
  weight: number
  grade: string
  status: string
  details?: Record<string, unknown>
  signals?: string[]
  // Sub-dimension optional fields
  factor_scores?: Record<string, number>
  trend?: string
  northbound_net?: number
  margin_balance?: number
  leaderboard_net?: number
  main_force_flow?: number
  pe_percentile?: number
  roe?: number
  revenue_growth?: number
  debt_ratio?: number
  pred_return?: number
  pred_30d_close?: number
  confidence?: number
  inflection_days?: number[]
  max_drawdown?: number
  news_sentiment?: number
  research_rating?: string
  analyst_target?: number
}

export interface DiagnosisReport {
  code: string
  overall_score: number
  grade: string
  recommendation: string
  recommendation_reason: string
  dimensions: Record<string, DimensionScore>
  key_levels: Record<string, number>
  risk_warnings: string[]
  kronos_available: boolean
  degraded: boolean
  degraded_dimensions: string[]
  created_at?: string
}

export interface DiagnosisCompareResponse {
  stocks: DiagnosisReport[]
  ranking: Record<string, unknown>[]
  dimension_comparison: Record<string, Record<string, unknown>[]>
}

export interface DiagnosisResult {
  code: string
  name: string
  market: string
  current_price: number
  change_pct: number
  overall_score: number
  grade: string
  grade_label: string
  dimensions: {
    technical: number
    capital: number
    fundamental: number
    ai_prediction: number
    sentiment: number
  }
  factor_details: FactorDetail[]
  capital_flow: CapitalFlow
  fundamentals: Fundamentals
  sentiment: SentimentData
  historical_klines: PredictionPoint[]
  predictions: PredictionPoint[]
  suggestion: {
    action: string
    buy_price: number
    stop_loss: number
    take_profit: number
    confidence: number
    reasoning: string
  }
}

export interface HistoryRecord {
  id: number
  code: string
  name: string
  score: number
  grade: string
  grade_label: string
  created_at: string
}
