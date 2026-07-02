import axios, { type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'

// ── 导入统一类型定义 ──
import type {
  ApiResponse,
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

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

const rootApi = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

const publicMarketApi = axios.create({
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: false,
})

const eastmoneyIndexSecids = ['1.000001', '0.399001', '0.399006', '0.899050']

function eastmoneyScaledNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Number((number / 100).toFixed(2)) : undefined
}

// ── Auth interceptor state (injected by AuthProvider) ──

let _getAccessToken: (() => string | null) | null = null
let _onRefreshToken: (() => Promise<string | null>) | null = null
let _onForceLogout: (() => void) | null = null
let _getPlatformSession: (() => PlatformSession | null) | null = null

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

export function injectPlatformContext(getSession: () => PlatformSession | null) {
  _getPlatformSession = getSession
}

export function clearPlatformContext() {
  _getPlatformSession = null
}

// ── Request interceptor: attach Authorization + platform boundary headers ──

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = _getAccessToken?.()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  const platformSession = _getPlatformSession?.()
  if (platformSession?.tenantId) {
    config.headers['X-Tenant-Id'] = platformSession.tenantId
  }
  if (platformSession?.ownerUserId) {
    config.headers['X-Owner-User-Id'] = platformSession.ownerUserId
  }
  if (platformSession?.accountId) {
    config.headers['X-Trade-Account-Id'] = platformSession.accountId
  }
  if (platformSession?.dataScope) {
    config.headers['X-Data-Scope'] = platformSession.dataScope
  }
  if (platformSession?.roleView) {
    config.headers['X-Role-View'] = platformSession.roleView
  }
  if (platformSession?.tradeMode) {
    config.headers['X-Trade-Mode'] = platformSession.tradeMode
  }
  if (platformSession?.brokerAdapter) {
    config.headers['X-Broker-Adapter'] = platformSession.brokerAdapter
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

// ── Supply Chain Helper Types ──

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

  getSupplyChainNode: (nodeId: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/node/${encodeURIComponent(nodeId)}`),

  getSupplyChainCompany: (code: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/company/${encodeURIComponent(code)}`),

  getSupplyChainMappingQuality: (): Promise<AxiosResponse<MappingQualityResponse>> =>
    api.get('/screener/supply-chain/mapping-review/quality'),

  getSupplyChainMappingReviewQueue: (params: SupplyChainMappingReviewQueueParams = {}): Promise<AxiosResponse<MappingReviewQueueResponse>> =>
    api.get(buildSupplyChainMappingReviewQueuePath(params)),

  reviewSupplyChainMapping: (code: string, nodeId: string, decision: SupplyChainMappingReviewDecision): Promise<AxiosResponse<void>> =>
    api.post(
      `/screener/supply-chain/mapping-review/${encodeURIComponent(code)}/${encodeURIComponent(nodeId)}`,
      decision,
    ),

  extractSupplyChainFacts: (text: string, source: Record<string, unknown> = {}, persist = false): Promise<AxiosResponse<unknown>> =>
    api.post('/screener/supply-chain/extract', { text, source, persist }),
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

export interface ChainDeconstructResponse {
  theme: {
    id: string
    name: string
  }
  view: string
  tree: {
    node_id: string
    name: string
    layer: number
    children?: unknown[]
  }
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

  deconstructChain: (params: { theme_id: string; method?: string }): Promise<AxiosResponse<ChainDeconstructResponse>> => {
    const { theme_id, method = 'upstream_downstream' } = params
    const qs = new URLSearchParams({ theme_id, method })
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
