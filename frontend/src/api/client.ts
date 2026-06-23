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

const buildSupplyChainWorkbenchPath = (params: SupplyChainWorkbenchParams = {}) => {
  const topN = typeof params === 'number' ? params : params.topN ?? 30
  const search = new URLSearchParams({ top_n: String(topN) })
  if (typeof params !== 'number') {
    if (params.themeId) search.set('theme_id', params.themeId)
    if (params.nodeId) search.set('node_id', params.nodeId)
  }
  return `/screener/supply-chain/workbench?${search.toString()}`
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

export default api
