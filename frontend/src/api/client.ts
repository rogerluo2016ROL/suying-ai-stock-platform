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

export interface MembershipInfo {
  status: string
  plan?: string | null
  starts_at?: string | null
  ends_at?: string | null
  source?: string | null
  note?: string | null
  is_member: boolean
  days_remaining?: number | null
}

export interface AdminUser {
  id: number
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
  permissions?: string[]
  membership?: MembershipInfo | null
}

export interface AdminUsersResponse {
  total: number
  page: number
  page_size: number
  users: AdminUser[]
}

export interface PermissionItem {
  key: string
  label: string
  group: string
  description: string
  enabled: boolean
}

export interface RolePermissions {
  role: string
  label: string
  description?: string | null
  permissions: PermissionItem[]
}

export interface RolePermissionsListResponse {
  roles: RolePermissions[]
}

export interface MembershipUser {
  id: number
  name: string
  email: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
  membership: MembershipInfo
}

export interface MembershipsResponse {
  total: number
  page: number
  page_size: number
  members: MembershipUser[]
}

export interface UserAuthorizationPayload {
  role?: string
  is_active?: boolean
  membership?: {
    status?: string
    plan?: string | null
    starts_at?: string | null
    ends_at?: string | null
    source?: string | null
    note?: string | null
  }
}

const eastmoneyIndexSecids = ['1.000001', '0.399001', '0.399006', '0.899050']

function eastmoneyScaledNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Number((number / 100).toFixed(2)) : undefined
}

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

export const predictionApi = {
  getStatus: (): Promise<AxiosResponse<PredictionStatus>> =>
    api.get('/prediction/status'),

  getOverview: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/prediction/overview'),

  predict: (code: string, predDays = 10): Promise<AxiosResponse<PredictionResponse>> =>
    api.post(`/prediction/${code}?pred_days=${predDays}`),

  predictFast: (code: string, predDays = 15): Promise<AxiosResponse<FastPredictionResponse>> =>
    api.post(`/prediction/${code}/fast?pred_days=${predDays}`),

  predictBatch: (codes: string[], days = 30): Promise<AxiosResponse<BatchPredictionResponse>> =>
    api.post(`/prediction/${codes[0]}/meta?pred_days=${days}`, codes),

  compare: (codes: string[], predDays = 20): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.post(`/prediction/compare?pred_days=${predDays}`, codes),

  getAccuracyBacktest: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/prediction/accuracy-backtest'),
}

// ═══════════════════════════════════════════════════════════════════════════
// Strategy API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const strategyApi = {
  generate: (picks: StrategyPick[], capital = 1_000_000): Promise<AxiosResponse<StrategyGenerateResponse>> =>
    api.post(`/strategy/generate?capital=${capital}`, picks),

  getTemplates: (): Promise<AxiosResponse<StrategyTemplatesResponse>> =>
    api.get('/strategy/templates'),

  getPlans: (): Promise<AxiosResponse<StrategyPlansResponse>> =>
    api.get('/strategy/plans'),

  createPlan: (name: string, modelName: string, maxPositions: number, capital = 1_000_000): Promise<AxiosResponse<{ plan: StrategyPlan }>> =>
    api.post(`/strategy/plans?name=${encodeURIComponent(name)}&model_name=${modelName}&max_positions=${maxPositions}&capital=${capital}`),

  getPlan: (planId: string): Promise<AxiosResponse<StrategyPlan>> =>
    api.get(`/strategy/plans/${planId}`),

  addPicks: (planId: string, picks: StrategyPick[]): Promise<AxiosResponse<void>> =>
    api.post(`/strategy/plans/${planId}/picks`, picks),

  deletePlan: (planId: string): Promise<AxiosResponse<void>> =>
    api.delete(`/strategy/plans/${planId}`),
}

export interface TrainingModelRecord {
  id: string
  name: string
  version: number
  model_type: string
  stage: string
  run_id?: string | null
  experiment_id?: string | null
  metrics?: Record<string, number>
  artifact_uri?: string | null
  deployed_at?: string | null
  deployed_by?: string | null
  created_by: string
  created_at: string
  updated_at?: string | null
  notes?: string | null
}

export interface TrainingModelsResponse {
  models: TrainingModelRecord[]
  total: number
  page: number
  page_size: number
}

export interface TrainingHistoryRecord {
  job_id: string
  model_type: string
  status: string
  params?: Record<string, unknown> | null
  final_metrics?: Record<string, number> | null
  model_uri?: string | null
  created_by: string
  created_at: string
  started_at?: string | null
  completed_at?: string | null
  duration_seconds?: number | null
}

export interface TrainingHistoryResponse {
  jobs: TrainingHistoryRecord[]
  total: number
  page: number
  page_size: number
}

export interface TrainingScheduleResponse {
  enabled: boolean
  cron: string
  model_type: string
  params?: Record<string, unknown> | null
  auto_deploy: boolean
  next_run?: string | null
  last_run?: string | null
  last_job_id?: string | null
  last_job_status?: string | null
}

export interface TrainingModelActionResponse {
  model_id: string
  message: string
  stage?: string
  deployed_at?: string
  previous_production_version?: number | null
  new_production_version?: number
  rolled_back_from?: number
  reason?: string
}

export const trainingApi = {
  getModels: (params: { page?: number; page_size?: number; model_type?: string; stage?: string } = {}): Promise<AxiosResponse<TrainingModelsResponse>> =>
    api.get('/training/models', { params: { page: 1, page_size: 20, ...params } }),

  getModel: (modelId: string): Promise<AxiosResponse<TrainingModelRecord>> =>
    api.get(`/training/models/${modelId}`),

  deployModel: (modelId: string, body: { force?: boolean; notes?: string } = {}): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/deploy`, body),

  rollbackModel: (modelId: string, body: { target_version: number; reason?: string }): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/rollback`, body),

  archiveModel: (modelId: string, body: { reason: string }): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/archive`, body),

  getHistory: (params: { page?: number; page_size?: number; model_type?: string; status?: string } = {}): Promise<AxiosResponse<TrainingHistoryResponse>> =>
    api.get('/training/history', { params: { page: 1, page_size: 20, ...params } }),

  getSchedule: (): Promise<AxiosResponse<TrainingScheduleResponse>> =>
    api.get('/training/schedule'),
}

// ═══════════════════════════════════════════════════════════════════════════
// Signal API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const signalApi = {
  getLevels: (): Promise<AxiosResponse<string[]>> =>
    api.get('/signal/levels'),

  getLive: (session = 'intra'): Promise<AxiosResponse<SignalLiveResponse>> =>
    api.get(`/signal/live?session=${session}`),

  getHistory: (code?: string): Promise<AxiosResponse<SignalHistoryResponse>> =>
    api.get(`/signal/history${code ? `?code=${code}` : ''}`),

  analyzeCode: (code: string): Promise<AxiosResponse<SignalAnalyzeResponse>> =>
    api.get(`/signal/analyze/${code}`),

  getDashboardSummary: (): Promise<AxiosResponse<DashboardSummaryResponse>> =>
    api.get(`/signal/dashboard-summary?_t=${Date.now()}`),

  getScreeningDashboardSummary: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get(`/dashboard/summary?_t=${Date.now()}`),

  getDashboardAuction: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/dashboard/auction'),

  getDataStatus: (): Promise<AxiosResponse<DataStatusResponse>> =>
    api.get(`/signal/data-status?_t=${Date.now()}`),

  triggerSync: (tableKey: string, days: number): Promise<AxiosResponse<TriggerSyncResponse>> =>
    api.post(`/signal/trigger-sync?table_key=${tableKey}&days=${days}`),

  getSyncSchedules: (): Promise<AxiosResponse<SyncSchedulesResponse>> =>
    api.get('/signal/sync-schedules'),

  updateSyncSchedules: (params: string): Promise<AxiosResponse<void>> =>
    api.post(`/signal/sync-schedules?${params}`),

  deleteSyncSchedule: (key: string): Promise<AxiosResponse<void>> =>
    api.delete(`/signal/sync-schedules?table_key=${key}`),
}

export const marketApi = {
  getIndexQuotes: async (): Promise<AxiosResponse<MarketIndexQuotesResponse>> => {
    try {
      const responses = await Promise.all(
        eastmoneyIndexSecids.map(secid =>
          publicMarketApi.get('https://push2.eastmoney.com/api/qt/stock/get', {
            params: {
              secid,
              fields: 'f43,f48,f57,f58,f169,f170',
            },
          }),
        ),
      )
      const diff = responses
        .map(response => response.data?.data)
        .filter(Boolean)
        .map(row => ({
          f12: row.f57,
          f14: row.f58,
          f2: eastmoneyScaledNumber(row.f43),
          f3: eastmoneyScaledNumber(row.f170),
          f4: eastmoneyScaledNumber(row.f169),
          f6: row.f48,
        }))
      if (diff.length > 0) {
        return {
          ...responses[0],
          data: { source: 'eastmoney_realtime', data: { diff } },
        }
      }
    } catch {
      // Fall through to local post-market close snapshot.
    }
    return api.get('/screener/market/index-quotes')
  },
}

// ═══════════════════════════════════════════════════════════════════════════
// Workbench BFF API（页面级 ViewModel）
// ═══════════════════════════════════════════════════════════════════════════

export const workbenchApi = {
  getPage: (modulePath: string): Promise<AxiosResponse<WorkbenchPageEnvelope>> => {
    const normalized = modulePath.replace(/^\/+/, '')
    const path = normalized.split('/').filter(Boolean).map(encodeURIComponent).join('/')
    return api.get(`/workbench/${path}`)
  },
}

// ═══════════════════════════════════════════════════════════════════════════
// Alert API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const alertApi = {
  getChannels: (): Promise<AxiosResponse<unknown>> =>
    api.get('/alert/channels'),

  getConfig: (): Promise<AxiosResponse<unknown>> =>
    api.get('/alert/config'),

  getUnreadCount: (): Promise<AxiosResponse<UnreadAlertCountResponse>> =>
    api.get('/alert/unread-count'),
}

// ═══════════════════════════════════════════════════════════════════════════
// Admin RBAC / Membership API
// ═══════════════════════════════════════════════════════════════════════════

export const adminApi = {
  getUsers: (params: {
    page?: number
    page_size?: number
    role?: string
    is_active?: boolean
    q?: string
  } = {}): Promise<AxiosResponse<AdminUsersResponse>> =>
    api.get('/admin/users', { params }),

  getRolePermissions: (): Promise<AxiosResponse<RolePermissionsListResponse>> =>
    api.get('/admin/permissions/roles'),

  updateRolePermissions: (
    role: string,
    permissionKeys: string[],
  ): Promise<AxiosResponse<RolePermissions>> =>
    api.put(`/admin/permissions/roles/${encodeURIComponent(role)}`, {
      permission_keys: permissionKeys,
    }),

  updateUserAuthorization: (
    userId: number,
    payload: UserAuthorizationPayload,
  ): Promise<AxiosResponse<AdminUser>> =>
    api.put(`/admin/users/${userId}/authorization`, payload),

  getMemberships: (params: {
    page?: number
    page_size?: number
    status?: string
    q?: string
  } = {}): Promise<AxiosResponse<MembershipsResponse>> =>
    api.get('/admin/memberships', { params }),
}

// ═══════════════════════════════════════════════════════════════════════════
// Trade API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const tradeApi = {
  getAccount: (): Promise<AxiosResponse<AccountResponse>> =>
    api.get('/trade/account'),

  getPositions: (): Promise<AxiosResponse<PositionsResponse>> =>
    api.get('/trade/positions'),

  getOrders: (): Promise<AxiosResponse<OrdersResponse>> =>
    api.get('/trade/orders'),

  placeOrder: (order: PlaceOrderRequest): Promise<AxiosResponse<PlaceOrderResponse>> =>
    api.post('/trade/order', order),

  getRiskVerdicts: (params: RiskVerdictQuery = {}): Promise<AxiosResponse<RiskVerdictsResponse>> =>
    api.get('/trade/risk-verdicts', { params }),

  getDecisionContexts: (params: DecisionContextQuery = {}): Promise<AxiosResponse<DecisionContextsResponse>> =>
    api.get('/trade/decision-contexts', { params }),
}

// ═══════════════════════════════════════════════════════════════════════════
// Backtest API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const backtestApi = {
  getFactors: (): Promise<AxiosResponse<FactorsResponse>> =>
    api.get('/backtest/factors'),

  getFactorEvidence: (modelKey: string) =>
    api.get<FactorEvidenceResponse>('/backtest/factor-evidence', { params: { model_key: modelKey } }),

  run: (params: {
    mode?: string
    windows?: number
    top_n?: number
    forward_days?: number
  } = {}): Promise<AxiosResponse<BacktestRunResponse>> => {
    const { mode = 'all', windows = 3, top_n = 30, forward_days = 60 } = params
    const qs = new URLSearchParams({ mode, windows: String(windows), top_n: String(top_n), forward_days: String(forward_days) })
    return api.post(`/backtest/run?${qs.toString()}`)
  },

  calibrate: (mode = 'all'): Promise<AxiosResponse<unknown>> =>
    api.post(`/backtest/calibrate?mode=${mode}`),

  compare: (params: {
    strategy_ids?: string[]
    start_date?: string
    end_date?: string
  } = {}): Promise<AxiosResponse<BacktestCompareResponse>> => {
    const { strategy_ids = ['momentum', 'quality'], start_date, end_date } = params
    const qs = new URLSearchParams()
    strategy_ids.forEach(id => qs.append('strategy_ids', id))
    if (start_date) qs.set('start_date', start_date)
    if (end_date) qs.set('end_date', end_date)
    return api.post(`/backtest/compare?${qs.toString()}`)
  },
}

// ═══════════════════════════════════════════════════════════════════════════
// Diagnosis API（已类型化）
// ═══════════════════════════════════════════════════════════════════════════

export const diagnosisApi = {
  analyze: (code: string, forceRefresh = false): Promise<AxiosResponse<DiagnosisReport>> =>
    api.post('/diagnosis/analyze', { code, force_refresh: forceRefresh }),

  compare: (codes: string[], dimensions?: string[], forceRefresh = false): Promise<AxiosResponse<DiagnosisCompareResponse>> =>
    api.post('/diagnosis/compare', { codes, dimensions, force_refresh: forceRefresh }),

  getHistory: (): Promise<AxiosResponse<DiagnosisHistoryResponse>> =>
    api.get('/diagnosis/history'),

  getReportPdf: (code: string): Promise<AxiosResponse<Blob>> =>
    api.get(`/diagnosis/report/${code}/pdf`, { responseType: 'blob' }),
}

// ═══════════════════════════════════════════════════════════════════════════
// Health API（已类型化 + 语义化错误）
// ═══════════════════════════════════════════════════════════════════════════

export class HealthCheckError extends Error {
  constructor(public readonly service: string, public readonly cause?: unknown) {
    super(`health check failed for service "${service}"`)
    this.name = 'HealthCheckError'
  }
}

export const healthApi = {
  runtimeReadiness: (): Promise<AxiosResponse<{ live: boolean; ready: boolean; services: Record<string, { ready: boolean; error?: string }> }>> =>
    rootApi.get('/v1/runtime/readiness'),
  check: (service: string): Promise<AxiosResponse<HealthCheckResponse>> =>
    api.get(`/${service}/health`).catch((err: unknown) => {
      throw new HealthCheckError(service, err)
    }),

  gateway: (): Promise<AxiosResponse<HealthCheckResponse>> =>
    rootApi.get('/health').catch((err: unknown) => {
      throw new HealthCheckError('gateway', err)
    }),

  checkOnline: async (service: string): Promise<boolean> => {
    try {
      const res = await api.get<HealthCheckResponse>(`/${service}/health`)
      const status = String(res.data?.status ?? '')
      return status === 'online' || status === 'healthy'
    } catch {
      return false
    }
  },
}

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
