import api from './client'

// ── Live Trade API (实盘交易) ──

export const liveTradeApi = {
  // Account & positions
  getAccount: () => api.get('/live-trade/account'),
  getPositions: () => api.get('/live-trade/positions'),
  getOrders: () => api.get('/live-trade/orders'),

  // Order
  placeOrder: (code: string, direction: string, volume: number, price = 0) =>
    api.post(`/live-trade/order?code=${code}&direction=${direction}&volume=${volume}&price=${price}`),

  // Pre-check (risk control check before order)
  preCheck: (params: { code: string; direction: string; price: number; volume: number }) =>
    api.post('/live-trade/order/pre-check', params),

  // Broker connection
  getBrokerStatus: () => api.get('/live-trade/broker/status'),
  connectBroker: () => api.post('/live-trade/broker/connect'),

  // Risk config
  getRiskConfig: () => api.get('/live-trade/risk-config'),

  // Circuit breaker
  getCircuitBreakerStatus: () => api.get('/live-trade/circuit-breaker/status'),

  // Audit logs
  getAuditLogs: (params: {
    page?: number
    page_size?: number
    start_date?: string
    end_date?: string
    action_type?: string
    stock_code?: string
    operator?: string
  }) => api.get('/live-trade/audit-logs', { params }),

  exportAuditLogs: (params: {
    start_date?: string
    end_date?: string
    action_type?: string
    stock_code?: string
    operator?: string
  }) => api.get('/live-trade/audit-logs/export', {
    params,
    responseType: 'blob',
  }),
}

// ── Mode switch ──

export const switchTradeMode = (mode: 'paper' | 'live') =>
  api.post('/trade/mode', { mode })
