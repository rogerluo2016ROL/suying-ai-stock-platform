import axios, { type InternalAxiosRequestConfig } from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// ── Shared response/payload types (P1-01: replace `any` with typed shapes) ──

/** A screener pick passed to strategy generation / plan picks. */
export interface StrategyPick {
  code: string
  name?: string
  price?: number
  score?: number
  grade?: string
  [key: string]: unknown
}

/** Trade order record (audit log / orders list). */
export interface TradeOrder {
  id?: string | number
  code: string
  direction: string
  price: number
  volume: number
  status?: string
  time?: string
  filled_at?: string
  [key: string]: unknown
}

/** Trade account summary. */
export interface TradeAccount {
  total_capital?: number
  total_assets?: number
  total_pnl?: number
  available?: number
  market_value?: number
  [key: string]: unknown
}

// ── Auth interceptor state (injected by AuthProvider) ──

let _getAccessToken: (() => string | null) | null = null
let _onRefreshToken: (() => Promise<string | null>) | null = null
let _onForceLogout: (() => void) | null = null

export function injectAuth(
  getToken: () => string | null,
  refreshToken: () => Promise<string | null>,
  forceLogout: () => void,
) {
  _getAccessToken = getToken
  _onRefreshToken = refreshToken
  _onForceLogout = forceLogout
}

export function clearAuth() {
  _getAccessToken = null
  _onRefreshToken = null
  _onForceLogout = null
}

// ── Request interceptor: attach Authorization header ──

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = _getAccessToken?.()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor: 401 → refresh → retry ──

let _refreshPromise: Promise<string | null> | null = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (!_onRefreshToken) {
        _onForceLogout?.()
        return Promise.reject(error)
      }

      // Promise lock: only one refresh at a time
      if (!_refreshPromise) {
        _refreshPromise = _onRefreshToken().finally(() => {
          _refreshPromise = null
        })
      }

      const newToken = await _refreshPromise
      if (newToken) {
        originalRequest._retry = true
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return api(originalRequest)
      }

      // Refresh failed → force logout
      _onForceLogout?.()
    }

    return Promise.reject(error)
  },
)

// ── API modules (unchanged) ──

type SupplyChainWorkbenchParams = number | {
  topN?: number
  themeId?: string
  nodeId?: string
}

export type SupplyChainMappingReviewStatus = 'reviewable' | 'pending_review' | 'weak_evidence' | 'verified' | 'rejected'

export interface SupplyChainMappingReviewQueueParams {
  status?: SupplyChainMappingReviewStatus
  nodeId?: string
  chainId?: string
  limit?: number
  offset?: number
}

export interface SupplyChainMappingReviewItem {
  code: string
  name?: string
  node_id: string
  node_name?: string
  chain_id?: string
  product_name?: string | null
  material_name?: string | null
  confidence?: number
  status: string
  mapping_source?: string
  evidence?: string[]
  evidence_gaps?: string[]
  updated_at?: string
  review_priority?: number
}

export interface SupplyChainMappingQuality {
  mapping_count: number
  review_queue_count: number
  status_counts: Record<string, number>
  source_counts: Record<string, number>
  hotspot_nodes: Array<{
    node_id: string
    node_name?: string
    chain_id?: string
    verified?: number
    pending_review?: number
    weak_evidence?: number
    rejected?: number
    review_pressure?: number
  }>
}

export interface SupplyChainMappingReviewDecision {
  decision: 'verified' | 'rejected' | 'needs_more_evidence' | 'pending_review'
  reviewer?: string
  note?: string
}

const buildSupplyChainWorkbenchPath = (params: SupplyChainWorkbenchParams = {}) => {
  const topN = typeof params === 'number' ? params : params.topN ?? 30
  const search = new URLSearchParams({ top_n: String(topN) })
  if (typeof params !== 'number') {
    if (params.themeId) search.set('theme_id', params.themeId)
    if (params.nodeId) search.set('node_id', params.nodeId)
  }
  return `/screener/supply-chain/workbench?${search.toString()}`
}

const buildSupplyChainMappingReviewQueuePath = (params: SupplyChainMappingReviewQueueParams = {}) => {
  const search = new URLSearchParams({
    status: params.status || 'reviewable',
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  })
  if (params.nodeId) search.set('node_id', params.nodeId)
  if (params.chainId) search.set('chain_id', params.chainId)
  return `/screener/supply-chain/mapping-review/queue?${search.toString()}`
}

// Screener
export const screenerApi = {
  getModes: () => api.get('/screener/modes'),
  run: (mode: string, topN = 30) => api.post(`/screener/run?mode=${mode}&top_n=${topN}`),
  getSupplyChainThemes: () => api.get('/screener/supply-chain/themes'),
  getSupplyChainBom: () => api.get('/screener/supply-chain/bom'),
  getSupplyChainWorkbench: (params: SupplyChainWorkbenchParams = {}) => api.get(buildSupplyChainWorkbenchPath(params)),
  getSupplyChainNode: (nodeId: string) => api.get(`/screener/supply-chain/node/${encodeURIComponent(nodeId)}`),
  getSupplyChainCompany: (code: string) => api.get(`/screener/supply-chain/company/${encodeURIComponent(code)}`),
  getSupplyChainMappingQuality: () => api.get<SupplyChainMappingQuality>('/screener/supply-chain/mapping-review/quality'),
  getSupplyChainMappingReviewQueue: (params: SupplyChainMappingReviewQueueParams = {}) =>
    api.get<{ total: number; limit: number; offset: number; items: SupplyChainMappingReviewItem[] }>(
      buildSupplyChainMappingReviewQueuePath(params),
    ),
  reviewSupplyChainMapping: (code: string, nodeId: string, decision: SupplyChainMappingReviewDecision) =>
    api.post(
      `/screener/supply-chain/mapping-review/${encodeURIComponent(code)}/${encodeURIComponent(nodeId)}`,
      decision,
    ),
  extractSupplyChainFacts: (text: string, source: Record<string, unknown> = {}, persist = false) =>
    api.post('/screener/supply-chain/extract', { text, source, persist }),
}

// Prediction
export const predictionApi = {
  getStatus: () => api.get('/prediction/status'),
  predict: (code: string, predDays = 10) => api.post(`/prediction/${code}?pred_days=${predDays}`),
  predictFast: (code: string, predDays = 15) => api.post(`/prediction/${code}/fast?pred_days=${predDays}`),
  predictBatch: (codes: string[], days = 30) =>
    api.post(`/prediction/${codes[0]}/meta?pred_days=${days}`, codes),
}

// Strategy
export const strategyApi = {
  generate: (picks: StrategyPick[], capital = 1_000_000) =>
    api.post(`/strategy/generate?capital=${capital}`, picks),
  getTemplates: () => api.get('/strategy/templates'),
  getPlans: () => api.get('/strategy/plans'),
  createPlan: (name: string, modelName: string, maxPositions: number, capital = 1_000_000) =>
    api.post(`/strategy/plans?name=${encodeURIComponent(name)}&model_name=${modelName}&max_positions=${maxPositions}&capital=${capital}`),
  getPlan: (planId: string) => api.get(`/strategy/plans/${planId}`),
  addPicks: (planId: string, picks: StrategyPick[]) =>
    api.post(`/strategy/plans/${planId}/picks`, picks),
  deletePlan: (planId: string) => api.delete(`/strategy/plans/${planId}`),
}

// Signal
export const signalApi = {
  getLevels: () => api.get('/signal/levels'),
  getLive: (session = 'intra') => api.get(`/signal/live?session=${session}`),
  getHistory: (code?: string) => api.get(`/signal/history${code ? `?code=${code}` : ''}`),
  analyzeCode: (code: string) => api.get(`/signal/analyze/${code}`),
  getDashboardSummary: () => api.get(`/signal/dashboard-summary?_t=${Date.now()}`),
  getDataStatus: () => api.get(`/signal/data-status?_t=${Date.now()}`),
  triggerSync: (tableKey: string, days: number) =>
    api.post(`/signal/trigger-sync?table_key=${tableKey}&days=${days}`),
  getSyncSchedules: () => api.get('/signal/sync-schedules'),
  updateSyncSchedules: (params: string) => api.post(`/signal/sync-schedules?${params}`),
  deleteSyncSchedule: (key: string) => api.delete(`/signal/sync-schedules?table_key=${key}`),
}

// Alert
export const alertApi = {
  getChannels: () => api.get('/alert/channels'),
  getConfig: () => api.get('/alert/config'),
  // P1-04: route the unread-count poll through the axios instance so it shares
  // the Authorization header + 401 refresh logic with every other request.
  getUnreadCount: () => api.get<number>('/alert/unread-count'),
}

// Trade
export const tradeApi = {
  getAccount: () => api.get('/trade/account'),
  getPositions: () => api.get('/trade/positions'),
  getOrders: () => api.get('/trade/orders'),
  placeOrder: (code: string, direction: string, volume: number, price = 0) =>
    api.post('/trade/order', { code, direction, volume, price }),
}

// Backtest
export const backtestApi = {
  getFactors: () => api.get('/backtest/factors'),
  run: (params: {
    mode?: string
    windows?: number
    top_n?: number
    forward_days?: number
  } = {}) => {
    const { mode = 'all', windows = 3, top_n = 30, forward_days = 60 } = params
    const qs = new URLSearchParams({ mode, windows: String(windows), top_n: String(top_n), forward_days: String(forward_days) })
    return api.post(`/backtest/run?${qs.toString()}`)
  },
  calibrate: (mode = 'all') => api.post(`/backtest/calibrate?mode=${mode}`),
  compare: (params: {
    strategy_ids?: string[]
    start_date?: string
    end_date?: string
  } = {}) => {
    const { strategy_ids = ['momentum', 'quality'], start_date, end_date } = params
    const qs = new URLSearchParams()
    strategy_ids.forEach(id => qs.append('strategy_ids', id))
    if (start_date) qs.set('start_date', start_date)
    if (end_date) qs.set('end_date', end_date)
    return api.post(`/backtest/compare?${qs.toString()}`)
  },
}

// Diagnosis
export const diagnosisApi = {
  analyze: (code: string, forceRefresh = false) =>
    api.post('/diagnosis/analyze', { code, force_refresh: forceRefresh }),
  compare: (codes: string[], dimensions?: string[], forceRefresh = false) =>
    api.post('/diagnosis/compare', { codes, dimensions, force_refresh: forceRefresh }),
  getHistory: () => api.get('/diagnosis/history'),
  getReportPdf: (code: string) =>
    api.get(`/diagnosis/report/${code}/pdf`, { responseType: 'blob' }),
}

// Health — check microservice health through API gateway
//
// FE-P1 review S-2: 原实现 `.catch(() => ({ data: { status: 'offline' } }))` 把任何
// 错误（网络/超时/CORS/5xx）伪装成 resolved 的 200 形态响应，破坏 axios 错误契约——
// 调用方 try/catch 永远进不到 catch，无法区分"服务 offline"与"请求本身失败"。
// 改为：失败时 throw HealthCheckError（语义化错误），调用方可 catch 后判 offline。
// 保留 `checkOffline()` 便捷访问器返回 boolean（内部 catch），兼容只想拿"在不在线"
// 布尔的简单调用方，不必每个调用点都写 try/catch。
export class HealthCheckError extends Error {
  constructor(public readonly service: string, public readonly cause?: unknown) {
    super(`health check failed for service "${service}"`)
    this.name = 'HealthCheckError'
  }
}

export const healthApi = {
  check: (service: string) =>
    api.get(`/${service}/health`).catch((err: unknown) => {
      throw new HealthCheckError(service, err)
    }),
  gateway: () =>
    api.get('/health').catch((err: unknown) => {
      throw new HealthCheckError('gateway', err)
    }),
  /** Convenience: returns true when the service is reachable and reports healthy. */
  checkOnline: async (service: string): Promise<boolean> => {
    try {
      const res = await api.get(`/${service}/health`)
      return (res as { data?: { status?: string } })?.data?.status === 'online'
    } catch {
      return false
    }
  },
}

// ── Chain API: Industry Chain Deconstruct (Phase 2) ─────────────────────────────────

/** Policy interpretation request payload */
export interface PolicyInterpretRequest {
  text: string
  source?: Record<string, unknown>
  persist?: boolean
  provider?: string
}

/** LLM usage telemetry */
export interface LLMUsageInfo {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  provider: string
  model: string
}

/** Structured interpretation result from LLM */
export interface InterpretationResult {
  summary: string
  industry_themes: Array<Record<string, unknown>>
  bom_nodes: string[]
  investment_logic: string
  risk_factors: Array<Record<string, unknown>>
}

/** Policy interpretation response */
export interface PolicyInterpretResponse {
  status: 'ok' | 'disabled' | 'error'
  interpretation_result: InterpretationResult
  usage: LLMUsageInfo
  persisted: boolean
  reason?: string
}

/** Chain deconstruct request params */
export interface ChainDeconstructParams {
  theme_id: string
  method?: 'upstream_downstream' | 'value_chain' | 'competition'
}

/** Chain node in deconstruct tree */
export interface ChainNode {
  node_id: string
  name: string
  layer: number
  children?: ChainNode[]
  upstream_nodes?: string[]
  downstream_nodes?: string[]
  value_chain?: {
    margin: number
    pricing_power: number
    value_added: number
  }
  competition?: {
    concentration: number
    leader_share: number
    barrier: number
    threat: number
  }
}

/** Chain deconstruct response */
export interface ChainDeconstructResponse {
  theme: {
    id: string
    name: string
  }
  view: string
  tree: ChainNode
  value_chain?: Record<string, { margin: number; pricing_power: number; value_added: number }>
  competition?: Record<string, { concentration: number; leader_share: number; barrier: number; threat: number }>
}

/** Three-factor resonance */
export interface ThreeFactors {
  industry_cycle?: {
    stage: string
    score: number
  }
  policy_intensity?: {
    stars: number
    score: number
  }
  performance_proof?: {
    status: string
    score: number
  }
}

/** Resonance summary */
export interface Resonance {
  summary: string
  dimensions: ThreeFactors
  active_count: number
}

/** Company mapped to chain node */
export interface ChainNodeCompany {
  code: string
  name: string
  rank: number
  main_pct: number | null
  policy_match_score: number | null
  chokepoint_score: number
  evidence: Array<Record<string, unknown>>
  three_factors: ThreeFactors
  trade_signal: string
  resonance: Resonance
}

/** Chain node companies response */
export interface ChainNodeCompaniesResponse {
  node_id: string
  node_name: string
  company_count: number
  companies: ChainNodeCompany[]
}

/** Filter types for chain candidates */
export type ChainCandidateFilter = 'high_growth' | 'high_profit' | 'high_moat' | 'chokepoint_core' | 'all'

/** Resonance levels for V6 three-factor scoring */
export type ResonanceLevel = '强启动' | '启动' | '关注' | '观察'

/** V6 three-factor scores for a candidate */
export interface ThreeFactorScores {
  industry_cycle?: { stage: string; score: number }
  policy_intensity?: { stars: number; score: number }
  performance_proof?: { status: string; score: number }
}

/** Candidate with V6 resonance scoring */
export interface ChainCandidate {
  code: string
  name: string
  score: number
  chokepoint_score: number
  three_factor_scores: ThreeFactorScores
  resonance_factors: number
  resonance_level: ResonanceLevel
  trade_signal: string
  commercialization_note?: string
  gross_margin?: number
  performance_yield?: number
  main_pct?: number
  policy_match_score?: number
  evidence?: string[]
  last_price?: number
  last_change_pct?: number
  last_trade_date?: string
}

/** Summary counts per filter type */
export interface FilterSummary {
  high_growth: number
  high_profit: number
  high_moat: number
  chokepoint_core: number
  all: number
}

/** Summary counts per resonance level */
export interface ResonanceSummary {
  '强启动': number
  '启动': number
  '关注': number
  '观察': number
}

/** Chain candidates API response */
export interface ChainCandidatesResponse {
  filter: ChainCandidateFilter
  resonance_level?: ResonanceLevel
  total_count: number
  candidates: ChainCandidate[]
  filter_summary: FilterSummary
  resonance_summary: ResonanceSummary
  elapsed_ms: number
}

/** Chain API module for industry chain deconstruct */
export const chainApi = {
  /** Interpret policy document via LLM to extract structured insights */
  interpretPolicy: (
    text: string,
    source?: Record<string, unknown>,
    persist = false,
    provider = 'deepseek',
  ) =>
    api.post<PolicyInterpretResponse>('/screener/policy/interpret', {
      text,
      source,
      persist,
      provider,
    }),

  /** Deconstruct industry chain into tree structure */
  deconstructChain: (params: ChainDeconstructParams) => {
    const { theme_id, method = 'upstream_downstream' } = params
    const qs = new URLSearchParams({ theme_id, method })
    return api.get<ChainDeconstructResponse>(`/screener/chain/deconstruct?${qs.toString()}`)
  },

  /** Get companies mapped to a specific chain node */
  getNodeCompanies: (nodeId: string) =>
    api.get<ChainNodeCompaniesResponse>(`/screener/chain/node/${encodeURIComponent(nodeId)}/companies`),

  /** Get filtered supply-chain candidates with V6 resonance scoring */
  getCandidates: (params: {
    filter?: 'high_growth' | 'high_profit' | 'high_moat' | 'chokepoint_core' | 'all'
    resonance_level?: '强启动' | '启动' | '关注' | '观察'
    top_n?: number
    trade_date?: string
  } = {}) => {
    const { filter = 'all', resonance_level, top_n = 30, trade_date } = params
    const qs = new URLSearchParams({ filter, top_n: String(top_n) })
    if (resonance_level) qs.set('resonance_level', resonance_level)
    if (trade_date) qs.set('trade_date', trade_date)
    return api.get<ChainCandidatesResponse>(`/screener/chain/candidates?${qs.toString()}`)
  },
}

export default api
