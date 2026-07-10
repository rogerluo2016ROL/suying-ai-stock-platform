import { domainHttp } from '../core/http'

export const tradeDomainApi = {
  account: () => domainHttp.get('/trade/account'),
  positions: () => domainHttp.get('/trade/positions'),
  orders: () => domainHttp.get('/trade/orders'),
  placeOrder: (payload: Record<string, unknown>) => domainHttp.post('/trade/orders', payload),
}
