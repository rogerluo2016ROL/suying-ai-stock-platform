// P2-08: extracted pure data transformers for the Diagnosis page.
// Backend DiagnosisReport → frontend DiagnosisResult view model. Pure functions.

import type {
  DiagnosisReport,
  DiagnosisResult,
  DimensionScore,
  FactorDetail,
  CapitalFlow,
  Fundamentals,
  SentimentData,
  HistoryRecord,
} from './types'

export function transformHistoryItem(item: Record<string, unknown>): HistoryRecord {
  return {
    id: item.id as number,
    code: item.code as string,
    name: item.code as string,
    score: (item.overall_score as number) ?? (item.score as number) ?? 0,
    grade: (item.grade as string) ?? '',
    grade_label: (item.recommendation as string) ?? (item.grade_label as string) ?? '',
    created_at: (item.created_at as string) ?? '',
  }
}

export function transformDiagnosisReport(report: DiagnosisReport): DiagnosisResult {
  const dims = report.dimensions
  const tech = dims['technical'] || ({} as DimensionScore)
  const capital = dims['capital_flow'] || ({} as DimensionScore)
  const fund = dims['fundamental'] || ({} as DimensionScore)
  const ai = dims['ai_predict'] || ({} as DimensionScore)
  const sent = dims['sentiment'] || ({} as DimensionScore)

  // Factor details from technical dimension factor_scores
  const factorScores = tech.factor_scores || {}
  const factorCount = Object.keys(factorScores).length || 1
  const factor_details: FactorDetail[] = Object.entries(factorScores).map(([name, score]) => ({
    name,
    score: Math.round(score),
    weight: +(1 / factorCount).toFixed(3),
    direction: (score >= 60 ? 'bullish' : score <= 40 ? 'bearish' : 'neutral') as FactorDetail['direction'],
    detail: tech.signals?.join('; ') || undefined,
  }))

  // Capital flow mapping
  const capital_flow: CapitalFlow = {
    north_bound: {
      net_inflow: capital.northbound_net || 0,
      trend: (capital.northbound_net || 0) >= 0 ? '净流入' : '净流出',
    },
    margin: {
      balance: +((capital.margin_balance || 0) / 10000).toFixed(2),
      ratio: 0,
    },
    dragon_tiger: {
      net_buy: capital.leaderboard_net || 0,
      institutions: 0,
    },
  }

  // Fundamentals mapping
  const fundamentals: Fundamentals = {
    pe: fund.pe_percentile || 0,
    pb: 0,
    roe: fund.roe || 0,
    revenue_growth: fund.revenue_growth || 0,
    profit_growth: 0,
    debt_ratio: fund.debt_ratio || 0,
    market_cap: 0,
  }

  // Sentiment mapping: news_sentiment is -1..1 → scale to 0..10
  const sentiment: SentimentData = {
    news_score: +(((sent.news_sentiment || 0) + 1) * 5).toFixed(1),
    news_count: 0,
    research_rating: sent.research_rating || '无',
    research_target: sent.analyst_target || 0,
    social_sentiment: 0,
  }

  return {
    code: report.code,
    name: report.code,
    market: report.code.startsWith('6') ? '上海'
      : report.code.startsWith('00') || report.code.startsWith('30') ? '深圳'
      : '科创板',
    current_price: 0,
    change_pct: 0,
    overall_score: report.overall_score,
    grade: report.grade,
    grade_label: report.recommendation,
    dimensions: {
      technical: tech.score || 0,
      capital: capital.score || 0,
      fundamental: fund.score || 0,
      ai_prediction: ai.score || 0,
      sentiment: sent.score || 0,
    },
    factor_details,
    capital_flow,
    fundamentals,
    sentiment,
    historical_klines: [],
    predictions: [],
    suggestion: {
      action: report.recommendation,
      buy_price: report.key_levels?.['entry'] || 0,
      stop_loss: report.key_levels?.['stop_loss'] || 0,
      take_profit: report.key_levels?.['take_profit'] || report.key_levels?.['resistance'] || 0,
      confidence: +((ai.confidence || 0) * 100).toFixed(0),
      reasoning: report.recommendation_reason,
    },
  }
}
