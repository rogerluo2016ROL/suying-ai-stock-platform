/** Strategy 域类型 (从 client.ts 拆出, C 域拆分)。 */

/** A screener pick passed to strategy generation / plan picks. */
export interface StrategyPick {
  candidate_id?: string
  source_module?: string
  source_mode?: string
  visibility?: 'private' | 'tenant_shared' | 'public'
  data_scope?: 'public' | 'tenant' | 'user' | 'account'
  code: string
  name?: string
  price?: number
  score?: number
  grade?: string
  [key: string]: unknown
}

// ── 执行器（量化交易）──

export interface PositionRules {
  max_positions?: number
  single_max_pct?: number
  total_position_cap_pct?: number
}

export interface RiskRules {
  daily_max_loss_pct?: number
  stop_loss_pct?: number
  take_profit_pct?: number
  trailing_stop_pct?: number
}

export interface AutoStrategy {
  id: string
  name: string
  status?: string
  trade_mode?: string
  capital?: number
  picks_count?: number
  picks?: unknown[]
  position_rules?: PositionRules
  risk_rules?: RiskRules
  created_at?: string
  updated_at?: string
}

export interface AutoLog {
  timestamp?: string
  level?: string
  message?: string
  details?: Record<string, string | number | undefined>
}

export interface MarketTemplate {
  id: string
  name: string
  description?: string
  model_name?: string
  risk_level?: string
  risk?: string
  max_positions?: number
  single_max?: number
  stop_loss_pct?: number
  target_return_pct?: number
  holding_days?: number
  capital?: number
  annual_return?: number
  max_drawdown?: number
}

// ── 执行器 API 响应 ──

export interface StrategyListResponse {
  strategies: AutoStrategy[]
}

export interface StrategyLogResponse {
  logs: AutoLog[]
}

export interface StrategyUpdateResponse {
  strategy: AutoStrategy
  message?: string
}

export interface StrategyActionResponse {
  status: string
  message?: string
}
