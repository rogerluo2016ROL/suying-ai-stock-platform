import type { ScreenerPick, ScreenerRunResponse } from '../../api/types'

export type DetailItem = [string, number, string, string]

export type DetailGroup = {
  name: string
  items: DetailItem[]
}

export type ModelMode = {
  id: string
  name: string
  tags: string[]
}

export type ModelGroup = {
  key: string
  icon: string
  label: string
  count: number
  note: string
  defaultModel: string
  modes: ModelMode[]
}

export type ModelCompareRow = {
  modeId: string
  name: string
  tradeDate: string
  source: string
  count: number
  avgScore: number | null
  topPick?: ScreenerPick
}

export type ModelCompareRunRow = ModelCompareRow & {
  picks: ScreenerPick[]
}

export type ScreeningTraceStep = NonNullable<ScreenerRunResponse['screening_trace']>[number]
export type RejectionSummaryItem = NonNullable<ScreenerRunResponse['rejection_summary']>[number]

// 共识：同一只股票被几个模型选中 → 星级 + 选中模型简称列表
export type ConsensusRow = {
  code: string
  name: string
  price?: number
  changePct?: number
  stars: number // 1..N（被几个模型选中）
  models: { short: string; tone: string; score?: number }[]
  bestScore?: number
}

// 跨模型评分卡片的指标条（从 factor_breakdown 派生，token 化色）
export type ScoreIndicator = { label: string; value: number | null; width: number; tone: 'up' | 'down' | 'neu' | 'warn' }

// 行业因子暴露（按 industry 聚合 score 偏离）
export type IndustryRow = { industry: string; avg: number; level: 'high' | 'mid' | 'low'; count: number }

export type RunStage = 'idle' | 'data' | 'model' | 'output' | 'done' | 'error'

export type TradeDateResolver = (modeId: string, requestedDate?: string) => string | undefined
