import type { CandidatePoolQueryResponse, ChainCandidate, DecisionContextRecord, Position, RiskVerdictRecord, StockSignal, TradeAccount, TradeOrder } from '../../api/types'

export interface AuctionRow {
  code: string
  name: string
  industry?: string
  gap?: number
  drop?: number
  vol: number
  score: number
  intent: string
}

export interface DashboardAuctionPick {
  code?: string
  name?: string
  industry?: string
  gap_pct?: number
  chg_pct?: number
  score?: number
  vol_ratio?: number
  volume_ratio?: number
  vol_z?: number
  intent?: string
}

export interface SectorRow {
  name: string
  count: number
  change: number
  lead: string
  width: number
}

export interface SignalRow {
  code: string
  name: string
  price: string
  signal: string
  score: number
  kronos: string
  target: string
  confidence: number
  consistency: string
  risk: string
  action: string
  watchlist: boolean
  dimensions: Array<{ label: string; value: number }>
}

export interface CandidateRow {
  code: string
  name: string
  source: string
  score: number
  risk: string
  size: string
}

export interface OrderRow {
  time: string
  code: string
  name: string
  dir: string
  price: string
  qty: string
  status: string
}

export interface PositionRow {
  code: string
  name: string
  value: string
  pnl: string
  weight: string
}

export interface OpenDecisionState {
  liveSignals: StockSignal[]
  liveTradeDate?: string
  candidates: ChainCandidate[]
  candidatePool?: CandidatePoolQueryResponse
  account?: TradeAccount
  positions: Position[]
  orders: TradeOrder[]
  verdicts: RiskVerdictRecord[]
  contexts: DecisionContextRecord[]
  auction: Record<string, unknown>
  loading: boolean
  error: string
}

export const emptyState: OpenDecisionState = {
  liveSignals: [],
  liveTradeDate: undefined,
  candidates: [],
  candidatePool: undefined,
  positions: [],
  orders: [],
  verdicts: [],
  contexts: [],
  auction: {},
  loading: true,
  error: '',
}

export interface AiSentimentReason {
  title: string
  detail: string
  fallback: boolean
}
