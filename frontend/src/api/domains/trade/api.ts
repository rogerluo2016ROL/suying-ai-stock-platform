import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  AccountResponse,
  PositionsResponse,
  OrdersResponse,
  PlaceOrderRequest,
  PlaceOrderResponse,
  RiskVerdictQuery,
  RiskVerdictsResponse,
  DecisionContextQuery,
  DecisionContextsResponse,
} from '../../types'
import type { BrokerConnectRequest } from '../../types'

/** Trade 域 API（合并原 liveTradeApi，统一入口）。 */
export const tradeApi = {
  // ── Account & positions ──
  getAccount: (): Promise<AxiosResponse<AccountResponse>> =>
    api.get('/trade/account'),

  getPositions: (): Promise<AxiosResponse<PositionsResponse>> =>
    api.get('/trade/positions'),

  getOrders: (): Promise<AxiosResponse<OrdersResponse>> =>
    api.get('/trade/orders'),

  // ── Order ──
  placeOrder: (order: PlaceOrderRequest): Promise<AxiosResponse<PlaceOrderResponse>> =>
    api.post('/trade/order', order),

  preCheck: (params: Partial<PlaceOrderRequest> & { code: string; direction: string; price: number; volume: number }) =>
    api.post('/trade/order/pre-check', params),

  // ── Risk verdicts & decision contexts ──
  getRiskVerdicts: (params: RiskVerdictQuery = {}): Promise<AxiosResponse<RiskVerdictsResponse>> =>
    api.get('/trade/risk-verdicts', { params }),

  getDecisionContexts: (params: DecisionContextQuery = {}): Promise<AxiosResponse<DecisionContextsResponse>> =>
    api.get('/trade/decision-contexts', { params }),

  // ── Broker ──
  getBrokerStatus: () => api.get('/trade/broker/status'),

  connectBroker: (config: BrokerConnectRequest) => api.post('/trade/broker/connect', config),

  // ── Risk config & circuit breaker ──
  getRiskConfig: () => api.get('/trade/risk-config'),

  getCircuitBreakerStatus: () => api.get('/trade/circuit-breaker/status'),

  // ── Audit logs ──
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

  // ── Mode switch ──
  switchTradeMode: (mode: 'paper' | 'live') =>
    api.post('/trade/mode', { mode }),
}
