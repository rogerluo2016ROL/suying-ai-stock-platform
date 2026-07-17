import axios, { type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'

// ── 导入统一类型定义 ──
import type {
  ApiResponse,
  CandidatePoolRecordRequest,
  CandidatePoolQueryParams,
  CandidatePoolRecordResponse,
  WatchlistAddRequest,
  WatchlistAddResponse,
  WatchlistDeleteResponse,
  WatchlistQueryParams,
  WatchlistQueryResponse,
  CandidatePoolQueryResponse,
  ScreenerModesResponse,
  ScreenerRunResponse,
  PredictionStatus,
  PredictionResponse,
  FastPredictionResponse,
  BatchPredictionResponse,
  StrategyTemplatesResponse,
  StrategyPlansResponse,
  StrategyGenerateResponse,
  StrategyPlan,
  SignalLiveResponse,
  SignalHistoryResponse,
  SignalAnalyzeResponse,
  DashboardSummaryResponse,
  DataStatusResponse,
  MarketIndexQuotesResponse,
  UnreadAlertCountResponse,
  AccountResponse,
  PositionsResponse,
  OrdersResponse,
  PlaceOrderResponse,
  BacktestRunResponse,
  BacktestCompareResponse,
  FactorsResponse,
  FactorEvidenceResponse,
  DiagnosisReport,
  DiagnosisCompareResponse,
  DiagnosisHistoryResponse,
  HealthCheckResponse,
  ServiceHealth,
  SupplyChainBomResponse,
  MappingReviewQueueResponse,
  MappingQualityResponse,
  ChainCandidate,
  ChainCandidatesResponse,
  SyncSchedulesResponse,
  TriggerSyncResponse,
  PlaceOrderRequest,
  RiskVerdictQuery,
  RiskVerdictsResponse,
  DecisionContextQuery,
  DecisionContextsResponse,
  WorkbenchPageEnvelope,
} from './types'
import type { PlatformSession } from '../types/platform'
import { configureApiContext } from './core/context'

// C 拆分试点: axios 实例 + auth + 拦截器抽至 ./http (本文件 re-export 保持向后兼容)
import {
  api,
  rootApi,
  publicMarketApi,
  injectAuth,
  clearAuth,
  injectPlatformContext,
  clearPlatformContext,
} from './http'
export { injectAuth, clearAuth, injectPlatformContext, clearPlatformContext } from './http'

// ── 保留部分内联类型（与 types.ts 兼容） ──
// Strategy 域类型已拆至 ./domains/strategy/types (C 域拆分)
export type { StrategyPick } from './domains/strategy/types'

// Trade 域类型已拆至 ./domains/trade/types (C 域拆分)
export type { TradeOrder, TradeAccount } from './domains/trade/types'

// Admin 域类型已拆至 ./domains/admin/types (C 域拆分)
export type {
  MembershipInfo,
  AdminUser,
  AdminUsersResponse,
  PermissionItem,
  RolePermissions,
  RolePermissionsListResponse,
  MembershipUser,
  MembershipsResponse,
  UserAuthorizationPayload,
} from './domains/admin/types'

// eastmoney 辅助 + marketApi 已拆至 ./domains/market/api (C 域拆分)

// axios 实例 / auth 注入 / 请求-响应拦截器已抽至 ./http (C 拆分试点)

// ── Supply Chain Helper Types ──

type SupplyChainWorkbenchParams = number | {
  topN?: number
  themeId?: string
  nodeId?: string
}

export interface SupplyChainCandidateRankingParams {
  topN?: number
  chainId?: string
  signal?: string
}

export interface SupplyChainCapexEvidenceReviewQueueParams {
  limit?: number
  chainId?: string
  reviewStatus?: 'pending_review' | 'approved' | 'rejected'
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

export interface EvidenceChainDocument {
  doc_id: string
  source_id?: string
  source_type?: string
  title?: string
  publish_time?: string
  crawl_time?: string
  url?: string
  source_level?: string
  doc_status?: string
  license_status?: string
}

export interface EvidenceChainFact {
  fact_id: string
  mapping_id?: string
  fact_type?: string
  fact_nature?: string
  fact_value?: string
  original_quote?: string
  source_level?: string
  confidence?: number
  validation_status?: string
  research_stage_signal?: string
  commercial_stage_signal?: string
  growth_signal?: boolean
  profit_signal?: boolean
  moat_signal?: boolean
  risk_signal?: boolean
  created_at?: string
}

export interface EvidenceChainFreshness {
  mapping_id?: string
  freshness_status?: string
  days_since_update?: number
  last_strong_evidence_date?: string
  last_mid_evidence_date?: string
  last_weak_signal_date?: string
  last_any_evidence_date?: string
  next_review_date?: string
  stale_reason?: string
  updated_at?: string
}

export interface EvidenceChainStageTransition {
  transition_id: string
  mapping_id?: string
  old_research_stage?: string
  new_research_stage?: string
  old_commercial_stage?: string
  new_commercial_stage?: string
  trigger_fact_id?: string
  review_status?: string
  change_reason?: string
  created_at?: string
}

export interface EvidenceChainExpectation {
  monitor_id: string
  mapping_id?: string
  claim_text?: string
  claim_source_type?: string
  expected_result?: string
  actual_progress?: string
  gap_status?: string
  expected_date?: string
  review_status?: string
  created_at?: string
}

export interface EvidenceChainResponse {
  version: string
  mapping_id: string
  source_status: string
  documents: EvidenceChainDocument[]
  facts: EvidenceChainFact[]
  freshness: EvidenceChainFreshness | Record<string, never>
  stage_transitions: EvidenceChainStageTransition[]
  expectations: EvidenceChainExpectation[]
  limitations?: string[]
}

export interface EvidenceReviewQueueResponse {
  version: string
  queue: Array<Record<string, unknown>>
  counts: Record<string, number>
  limitations?: string[]
}

export interface CapexEvidenceReviewItem {
  capex_evidence_id: string
  mapping_id: string
  code: string
  company_name?: string
  chain_id?: string
  node_id?: string
  tag_name?: string
  fiscal_period?: string
  as_of_date?: string | null
  capex_amount?: number | null
  capex_amount_unit?: string
  currency?: string
  capex_direction?: string[]
  mapped_layer_id?: string
  mapped_segments?: string[]
  source_type?: string
  source_level?: string
  source_name?: string
  source_url?: string
  quote?: string
  evidence_level?: string
  confidence?: number
  review_status?: string
  amount_is_total_capex?: boolean
  amount_is_segment_capex?: boolean
  direction_is_ai_related?: boolean
  metadata?: Record<string, unknown>
  created_at?: string | null
}

export interface CapexEvidenceReviewQueueResponse {
  version: string
  source_status: string
  filters: Record<string, unknown>
  counts: Record<string, number>
  queue: CapexEvidenceReviewItem[]
  limitations?: string[]
}

export interface CapexEvidenceReviewRequest {
  review_status: 'approved' | 'rejected' | 'pending_review'
  reviewer?: string
  note?: string
  confidence?: number
}

export interface SupplyChainCandidateRankingItem {
  rank: number
  chain_id: string
  code: string
  name?: string
  industry?: string
  rank_score: number
  avg_rank_score?: number
  signal: string
  tag_count: number
  best_mapping_id: string
  best_tag_name: string
  node_id?: string
  mapping_status?: string
  three_high_total?: number
  growth_score?: number
  profit_score?: number
  moat_score?: number
  stage_score?: number
  evidence_score?: number
  expectation_gap_score?: number
  gap_type?: string
  research_stage?: string
  commercialization_stage?: string
  commercialization_indicator?: string
  expectation_gap_indicator?: string
  trigger_signal_indicator?: string
  bigtech_capex_tailwind?: {
    score?: number
    matched_layers?: string[]
    company_count?: number
    record_count?: number
    companies?: string[]
    commercialization_indicator?: string
    expectation_gap_indicator?: string
    trigger_signal_indicator?: string
  }
  company_capex_evidence?: {
    score?: number
    evidence_count?: number
    amount_count?: number
    direction_ai_count?: number
    fresh_count?: number
    avg_confidence?: number
    latest_as_of_date?: string
    directions?: string[] | string[][]
    indicator?: string
  }
  l8_match_rate?: number
  fresh_rate?: number
  freshness_status?: string
  fact_count?: number
  latest_price?: number
  latest_trade_date?: string
  change_1d_pct?: number
  change_20d_pct?: number
  mapping_ids?: string[]
  tag_names?: string[]
}

export interface SupplyChainCandidateRankingResponse {
  version: string
  source_status: string
  filters: {
    top_n: number
    chain_id?: string | null
    signal?: string | null
  }
  summary: {
    mapping_rows?: number
    company_chain_rows?: number
    chain_count?: number
    signal_distribution?: Record<string, number>
    bigtech_capex_context?: {
      company_count?: number
      record_count?: number
      companies?: string[]
    }
  }
  items: SupplyChainCandidateRankingItem[]
  by_chain: Record<string, SupplyChainCandidateRankingItem[]>
  limitations?: string[]
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

const buildSupplyChainCandidateRankingPath = (params: SupplyChainCandidateRankingParams = {}) => {
  const search = new URLSearchParams({
    top_n: String(params.topN ?? 100),
  })
  if (params.chainId) search.set('chain_id', params.chainId)
  if (params.signal) search.set('signal', params.signal)
  return `/screener/supply-chain/candidate-ranking?${search.toString()}`
}

const buildSupplyChainCapexEvidenceReviewQueuePath = (params: SupplyChainCapexEvidenceReviewQueueParams = {}) => {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 50),
    review_status: params.reviewStatus || 'pending_review',
  })
  if (params.chainId) search.set('chain_id', params.chainId)
  return `/screener/supply-chain/capex-evidence-review/queue?${search.toString()}`
}

// ═══════════════════════════════════════════════════════════════════════════
// Screener API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const screenerApi = {
  getModes: (): Promise<AxiosResponse<ScreenerModesResponse>> =>
    api.get('/screener/modes'),

  run: (mode: string, topN = 30, tradeDate?: string): Promise<AxiosResponse<ScreenerRunResponse>> => {
    const params = new URLSearchParams({ mode, top_n: String(topN) })
    if (tradeDate) params.set('trade_date', tradeDate)
    return api.post(`/screener/run?${params.toString()}`)
  },

  getSupplyChainThemes: (): Promise<AxiosResponse<SupplyChainBomResponse['themes']>> =>
    api.get('/screener/supply-chain/themes'),

  getSupplyChainBom: (): Promise<AxiosResponse<SupplyChainBomResponse>> =>
    api.get('/screener/supply-chain/bom'),

  getSupplyChainWorkbench: (params: SupplyChainWorkbenchParams = {}): Promise<AxiosResponse<unknown>> =>
    api.get(buildSupplyChainWorkbenchPath(params)),

  getSupplyChainCandidateRanking: (params: SupplyChainCandidateRankingParams = {}): Promise<AxiosResponse<SupplyChainCandidateRankingResponse>> =>
    api.get(buildSupplyChainCandidateRankingPath(params)),

  getSupplyChainNode: (nodeId: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/node/${encodeURIComponent(nodeId)}`),

  getSupplyChainCompany: (code: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/company/${encodeURIComponent(code)}`),

  getSupplyChainMappingQuality: (): Promise<AxiosResponse<MappingQualityResponse>> =>
    api.get('/screener/supply-chain/mapping-review/quality'),

  getSupplyChainMappingReviewQueue: (params: SupplyChainMappingReviewQueueParams = {}): Promise<AxiosResponse<MappingReviewQueueResponse>> =>
    api.get(buildSupplyChainMappingReviewQueuePath(params)),

  getSupplyChainEvidenceChain: (mappingId: string): Promise<AxiosResponse<EvidenceChainResponse>> =>
    api.get(`/screener/supply-chain/business-tag/${encodeURIComponent(mappingId)}/evidence-chain`),

  getSupplyChainEvidenceReviewQueue: (limit = 50): Promise<AxiosResponse<EvidenceReviewQueueResponse>> =>
    api.get(`/screener/supply-chain/evidence-review/queue?limit=${encodeURIComponent(String(limit))}`),

  getSupplyChainCapexEvidenceReviewQueue: (params: SupplyChainCapexEvidenceReviewQueueParams = {}): Promise<AxiosResponse<CapexEvidenceReviewQueueResponse>> =>
    api.get(buildSupplyChainCapexEvidenceReviewQueuePath(params)),

  reviewSupplyChainCapexEvidence: (capexEvidenceId: string, payload: CapexEvidenceReviewRequest): Promise<AxiosResponse<unknown>> =>
    api.post(`/screener/supply-chain/capex-evidence/${encodeURIComponent(capexEvidenceId)}/review`, payload),

  reviewSupplyChainMapping: (code: string, nodeId: string, decision: SupplyChainMappingReviewDecision): Promise<AxiosResponse<void>> =>
    api.post(
      `/screener/supply-chain/mapping-review/${encodeURIComponent(code)}/${encodeURIComponent(nodeId)}`,
      decision,
    ),

  extractSupplyChainFacts: (text: string, source: Record<string, unknown> = {}, persist = false): Promise<AxiosResponse<unknown>> =>
    api.post('/screener/supply-chain/extract', { text, source, persist }),

  // 候选池（account-scoped 私有对象）：scope 由 client 拦截器注入 X-Tenant-Id
  // X-Trade-Account-Id 头，前端不传明文 tenant/owner/account。打通「选股→加候选池→决策」主链路咽喉（M0）。
  recordCandidatePool: (payload: CandidatePoolRecordRequest): Promise<AxiosResponse<CandidatePoolRecordResponse>> =>
    api.post('/screener/candidate-pool', payload),

  queryCandidatePool: (params: CandidatePoolQueryParams = {}): Promise<AxiosResponse<CandidatePoolQueryResponse>> => {
    const qs = new URLSearchParams()
    if (params.source_module) qs.set('source_module', params.source_module)
    if (params.source_mode) qs.set('source_mode', params.source_mode)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get(query ? `/screener/candidate-pool?${query}` : '/screener/candidate-pool')
  },

  // watchlist（自选股，Batch B #11）—— scope 走拦截器头，前端不传明文（契约§9.3）
  addWatchlist: (payload: WatchlistAddRequest): Promise<AxiosResponse<WatchlistAddResponse>> =>
    api.post('/screener/watchlist', payload),
  listWatchlist: (params: WatchlistQueryParams = {}): Promise<AxiosResponse<WatchlistQueryResponse>> => {
    const qs = new URLSearchParams()
    if (params.code) qs.set('code', params.code)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get(query ? `/screener/watchlist?${query}` : '/screener/watchlist')
  },
  removeWatchlist: (key: { code?: string; id?: number }): Promise<AxiosResponse<WatchlistDeleteResponse>> => {
    const qs = new URLSearchParams()
    if (key.code) qs.set('code', key.code)
    if (key.id) qs.set('id', String(key.id))
    return api.delete(`/screener/watchlist?${qs.toString()}`)
  },
}

// ═══════════════════════════════════════════════════════════════════════════
// Prediction API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { predictionApi } from './domains/prediction/api'

// ═══════════════════════════════════════════════════════════════════════════
// Strategy API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { strategyApi } from './domains/strategy/api'

// Training 域类型已拆至 ./domains/training/types (C 域拆分)
export type {
  TrainingModelRecord,
  TrainingModelsResponse,
  TrainingHistoryRecord,
  TrainingHistoryResponse,
  TrainingScheduleResponse,
  TrainingModelActionResponse,
} from './domains/training/types'

export { trainingApi } from './domains/training/api'

// ═══════════════════════════════════════════════════════════════════════════
// Signal API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { signalApi } from './domains/signal/api'

export { marketApi } from './domains/market/api'

// ═══════════════════════════════════════════════════════════════════════════
// Workbench BFF API（页面级 ViewModel）
// ═══════════════════════════════════════════════════════════════════════════

export { workbenchApi } from './domains/workbench/api'

// ═══════════════════════════════════════════════════════════════════════════
// Alert API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { alertApi } from './domains/alert/api'

// ═══════════════════════════════════════════════════════════════════════════
// Admin RBAC / Membership API
// ═══════════════════════════════════════════════════════════════════════════

export { adminApi } from './domains/admin/api'

// ═══════════════════════════════════════════════════════════════════════════
// Trade API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

// Trade 域 API 已拆至 ./domains/trade/api (C 域拆分)
export { tradeApi } from './domains/trade/api'

// ═══════════════════════════════════════════════════════════════════════════
// Backtest API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { backtestApi } from './domains/backtest/api'

// ═══════════════════════════════════════════════════════════════════════════
// Diagnosis API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export { diagnosisApi } from './domains/diagnosis/api'

// ═══════════════════════════════════════════════════════════════════════════
// Health API（已类型化 + 语义化错误）
// ═══════════════════════════════════════════════════════════════════════════

// Health 域 API + HealthCheckError 已拆至 ./domains/health/api (C 域拆分)
export { healthApi, HealthCheckError } from './domains/health/api'

// ═══════════════════════════════════════════════════════════════════════════
// Chain API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export interface PolicyInterpretRequest {
  text: string
  source?: Record<string, unknown>
  persist?: boolean
  provider?: string
}

export interface PolicyInterpretResponse {
  status: 'ok' | 'disabled' | 'error'
  interpretation_result: {
    summary: string
    industry_themes: Array<Record<string, unknown>>
    bom_nodes: string[]
    investment_logic: string
    risk_factors: Array<Record<string, unknown>>
  }
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    provider: string
    model: string
  }
  persisted: boolean
  reason?: string
}

export interface ChainDeconstructTree {
  node_id: string
  name: string
  layer?: number
  layer_id?: string
  layer_order?: number
  definition?: string
  key_questions?: string[]
  segments?: string[]
  evidence?: string[]
  companies?: string[]
  tracking_metrics?: string[]
  metrics?: {
    commercialization?: string[]
    expectation_gap?: string[]
    trigger_signals?: string[]
  }
  capex_evidence?: Array<{
    evidence_id: string
    company?: string
    region?: string
    fiscal_period?: string
    capex_amount?: number | null
    currency?: string
    capex_direction?: string[]
    mapped_layer_id: string
    mapped_segments?: string[]
    metric_usage?: string[]
    source_type?: string
    source_name?: string
    source_url?: string
    quote?: string
    as_of_date?: string
    evidence_level?: string
    collection_method?: string
    impact_direction?: string
    confidence?: string
  }>
  physical_metrics?: Array<{
    metric_id: string
    name: string
    mapped_layer_id: string
    mapped_segment?: string
    metric_usage?: string[]
    data_type?: string
    value?: number | string | null
    unit?: string
    period?: string
    direction?: string
    source_type?: string
    source_name?: string
    source_url?: string
    evidence_level?: string
    collection_method?: string
    as_of_date?: string
    impact_direction?: string
    confidence?: string
  }>
  evidence_chain?: Array<{
    evidence_id: string
    evidence_type: string
    mapped_layer_id: string
    mapped_segment?: string
    source_type?: string
    source_name?: string
    evidence_level?: string
    as_of_date?: string
    metric_usage?: string[]
    impact_direction?: string
    confidence?: string
  }>
  expectation_gap?: {
    expected?: Record<string, unknown>
    actual?: Record<string, unknown>
    gap_direction?: string
    gap_strength?: string
    calculation_method?: string
    formula?: string
    evidence_ids?: string[]
  }
  trigger_signal?: {
    signal_type?: string
    signal_strength?: string
    triggered_by_evidence_ids?: string[]
    mapped_layer_id?: string
    mapped_segments?: string[]
  }
  children?: ChainDeconstructTree[]
}

export interface ChainDeconstructTemplate {
  template_id: string
  name: string
  description?: string
  example_theme?: string
  source?: string
}

export interface ChainDeconstructResponse {
  theme: {
    id: string
    name: string
  }
  view: string
  template?: ChainDeconstructTemplate
  macro_context?: Array<{
    region: string
    policy_stance?: string
    inflation_state?: string
    rate_trend?: string
    liquidity_signal?: string
    source_type?: string
    source_name?: string
    source_url?: string
    as_of_date?: string
    evidence_level?: string
  }>
  tree: ChainDeconstructTree
}

export interface ChainNodeCompaniesResponse {
  node_id: string
  node_name: string
  company_count: number
  companies: unknown[]
}

export const chainApi = {
  interpretPolicy: (
    text: string,
    source?: Record<string, unknown>,
    persist = false,
    provider = 'deepseek',
  ): Promise<AxiosResponse<PolicyInterpretResponse>> =>
    api.post('/screener/policy/interpret', {
      text,
      source,
      persist,
      provider,
    }),

  deconstructChain: (params: { theme_id: string; method?: string; template?: string }): Promise<AxiosResponse<ChainDeconstructResponse>> => {
    const { theme_id, method = 'upstream_downstream', template } = params
    const qs = new URLSearchParams({ theme_id, method })
    if (template) qs.set('template', template)
    return api.get(`/screener/chain/deconstruct?${qs.toString()}`)
  },

  getNodeCompanies: (nodeId: string): Promise<AxiosResponse<ChainNodeCompaniesResponse>> =>
    api.get(`/screener/chain/node/${encodeURIComponent(nodeId)}/companies`),

  getCandidates: (params: {
    filter?: string
    resonance_level?: string
    top_n?: number
    trade_date?: string
  } = {}): Promise<AxiosResponse<ChainCandidatesResponse>> => {
    const { filter = 'all', resonance_level, top_n = 30, trade_date } = params
    const workbenchPath = buildSupplyChainWorkbenchPath({ topN: top_n })
    return api.get(workbenchPath).then((response) => {
      const body = response.data as {
        candidates?: ChainCandidate[]
        candidate_count?: number
        filter_summary?: Record<string, number>
        resonance_summary?: Record<string, number>
      }
      return {
        ...response,
        data: {
          filter,
          resonance_level,
          trade_date,
          total_count: body.candidate_count ?? body.candidates?.length ?? 0,
          candidates: body.candidates || [],
          filter_summary: body.filter_summary || {},
          resonance_summary: body.resonance_summary || {},
          elapsed_ms: 0,
        },
      } as AxiosResponse<ChainCandidatesResponse>
    })
  },
}

// ═══════════════════════════════════════════════════════════════════════════
// 导出类型供其他文件使用
// ═══════════════════════════════════════════════════════════════════════════

export type {
  ScreenerModesResponse,
  ScreenerRunResponse,
  ScreenerPick,
  PredictionResponse,
  DiagnosisReport,
  DiagnosisCompareResponse,
  DashboardSummaryResponse,
  SignalLiveResponse,
  BacktestRunResponse,
  BacktestCompareResponse,
  AccountResponse,
  PositionsResponse,
  OrdersResponse,
  RiskVerdictsResponse,
  DecisionContextsResponse,
  WorkbenchPageEnvelope,
  WorkbenchSection,
  WorkbenchAction,
  PlaceOrderResponse,
  HealthCheckResponse,
  ServiceHealth,
  StrategyPlan,
  ChainCandidate,
  ChainCandidatesResponse,
  // Supply Chain aliases
  ChainNode,
  SupplyChainNode,
  SupplyChainTheme,
  ChainCandidateFilter,
  ResonanceLevel,
  ThreeFactorScores,
  FilterSummary,
  ResonanceSummary,
} from './types'

export default api
