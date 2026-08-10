export interface SignalStock {
  code: string
  name: string
  price: number
  change_pct: number
  signal: string
  desc?: string
  score?: number
  industry?: string
  market?: string
}

export interface WatchlistItem {
  code: string
  name: string
  market_cap?: number
  industry?: string
  price?: number
  change_pct?: number
  signal?: string
  score?: number
  stop_distance?: number
  risk_note?: string
}

export interface AlertSignal {
  code: string
  name: string
  level: string
  change_pct: number
  reason: string
}

export interface AuctionIntentItem {
  code: string
  name: string
  chg_pct?: number
  gap_pct?: number
  price?: number
  score?: number
  industry?: string
  vol_ratio?: number
  buy_sell_ratio?: number
  intent?: string
  reasons?: string[]
}

export interface LimitStockItem {
  code: string
  name?: string
  price?: number
  change_pct?: number
  chg_pct?: number
  score?: number
  industry?: string
  sector?: string
  board?: string
  concept?: string
  signal?: string
  desc?: string
}

export type LimitStocksPayload = LimitStockItem[] | {
  up_count?: number
  down_count?: number
  data_source?: string
  up_list?: LimitStockItem[]
  down_list?: LimitStockItem[]
  list?: LimitStockItem[]
  stocks?: LimitStockItem[]
}

export interface MarketSentimentData {
  score: number
  label: string
  trade_date?: string
  avg_change_pct?: number
  up_stocks?: number
  down_stocks?: number
  total_stocks?: number
  model?: string
  formula?: string
  sub_dimensions?: Record<string, string>
}

export interface MarketRegimeData {
  regime: string
  score: number
  confidence: number
  label: string
  dimensions?: Record<string, { score: number; weight: number }>
}

export interface DashboardData {
  refreshed_at?: string
  data_freshness?: {
    status?: string
    as_of?: string | null
    source?: string
    quality_score?: number
  }
  next_trading_day?: string | null
  market_sentiment?: MarketSentimentData
  market_regime_v2?: MarketRegimeData
  signal_stocks?: SignalStock[]
  limit_stocks?: LimitStocksPayload
  alert_signals?: AlertSignal[]
  auction_intent?: {
    trade_date?: string
    data_source?: string
    total_analyzed: number
    strong_bullish_count?: number
    moderate_bullish_count?: number
    bullish_count: number
    moderate_bearish_count?: number
    strong_bearish_count?: number
    bearish_count: number
    neutral_count?: number
    top_bullish?: AuctionIntentItem[]
    top_bearish?: AuctionIntentItem[]
  }
  watchlist?: WatchlistItem[]
  data_sources?: Record<string, string>
}

export type SentimentPageKey = 'today' | 'history' | 'sector'

export interface SectorResonance {
  name: string
  score: number
  upRatio: number
  change: number
  fund: number
}

export interface SectorStockDetail {
  code: string
  name: string
  industry: string
  price: number
  changePct: number
  score: number
  signal: string
  source: string
}

export type SignalLevelKey = 'STRONG_BUY' | 'BUY' | 'HOLD' | 'REDUCE' | 'SELL' | 'TIMING_ALERT'

export interface SignalMatrixItem {
  code: string
  name: string
  industry: string
  level: SignalLevelKey
  score: number
  price: number
  changePct: number
  watchlist?: boolean
}

export interface SentimentReason {
  title: string
  detail: string
  fallback: boolean
}
