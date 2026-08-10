import axios, { type InternalAxiosRequestConfig } from 'axios'
import type { PlatformSession } from '../types/platform'
import { configureApiContext } from './core/context'

// C 拆分试点: axios 实例 + auth 注入 + 请求/响应拦截器, 从 client.ts 抽出为独立 HTTP 层。
// 各业务域 (api/domains/<feature>/) 后续 import 此处实例, 避免循环依赖。

export const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

export const rootApi = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

export const publicMarketApi = axios.create({
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: false,
})

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
  configureApiContext({ getToken })
}

export function clearAuth() {
  _getAccessToken = null
  _onRefreshToken = null
  _onForceLogout = null
  configureApiContext({ getToken: undefined })
}

export function injectPlatformContext(getSession: () => PlatformSession | null) {
  _getPlatformSession = getSession
  configureApiContext({ getSession })
}

export function clearPlatformContext() {
  _getPlatformSession = null
  configureApiContext({ getSession: undefined })
}

// ── Request interceptor: attach Authorization + platform boundary headers ──
// 共享工厂: api 与 rootApi 都挂（rootApi 直达网关的 /v1/runtime/readiness 等端点也需鉴权）。

function attachAuthRequestInterceptor(instance: typeof api) {
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = _getAccessToken?.()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    const platformSession = _getPlatformSession?.()
    if (platformSession?.tenantId) {
      config.headers['X-Tenant-Id'] = platformSession.tenantId
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
}

attachAuthRequestInterceptor(api)
attachAuthRequestInterceptor(rootApi)

// ── Response interceptor: 401 → refresh → retry ──
// 共享工厂: api 与 rootApi 挂同一逻辑, 重试时用各自实例保持 baseURL 语义。

let _refreshPromise: Promise<string | null> | null = null

function attachAuthRefreshInterceptor(instance: typeof api) {
  instance.interceptors.response.use(
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
          return instance(originalRequest)
        }

        // Refresh failed → force logout
        _onForceLogout?.()
      }

      return Promise.reject(error)
    },
  )
}

attachAuthRefreshInterceptor(api)
attachAuthRefreshInterceptor(rootApi)
