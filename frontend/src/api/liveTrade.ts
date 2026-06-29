import api from './client'
import type { BrokerConnectRequest, PlaceOrderRequest } from './types'

// ── Live Trade API (实盘交易) ──

export const liveTradeApi = {
  // Account & positions
  getAccount: () => api.get('/trade/account'),
  getPositions: () => api.get('/trade/positions'),
  getOrders: () => api.get('/trade/orders'),

  // Order
  placeOrder: (order: PlaceOrderRequest) =>
    api.post('/trade/order', order),

  // Pre-check (risk control check before order)
  preCheck: (params: Partial<PlaceOrderRequest> & { code: string; direction: string; price: number; volume: number }) =>
    api.post('/trade/order/pre-check', params),

  // Broker connection
  getBrokerStatus: () => api.get('/trade/broker/status'),
  connectBroker: (config: BrokerConnectRequest) => api.post('/trade/broker/connect', config),

  // Risk config
  getRiskConfig: () => api.get('/trade/risk-config'),

  // Circuit breaker
  getCircuitBreakerStatus: () => api.get('/trade/circuit-breaker/status'),

  // Audit logs
  getAuditLogs: (params: {
    page?: number
    page_size?: number
    start_date?: string
    end_date?: string
    action_type?: string
    stock_code?: string
    operator?: string
  }) => api.get('/trade/audit-logs', { params }),

  exportAuditLogs: (params: {
    start_date?: string
    end_date?: string
    action_type?: string
    stock_code?: string
    operator?: string
  }) => api.get('/trade/audit-logs/export', {
    params,
    responseType: 'blob',
  }),
}

// ── Mode switch ──

export const switchTradeMode = (mode: 'paper' | 'live') =>
  api.post('/trade/mode', { mode })
