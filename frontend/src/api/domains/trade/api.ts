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

/** Trade 域 API (从 client.ts 拆出, C 域拆分)。 */
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
