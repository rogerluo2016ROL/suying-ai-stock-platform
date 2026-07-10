import axios from 'axios'
import { apiContext } from './context'

export const domainHttp = axios.create({
  baseURL: '/api/v1', timeout: 30000, withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

domainHttp.interceptors.request.use(config => {
  const token = apiContext.token()
  if (token) config.headers.Authorization = `Bearer ${token}`
  const session = apiContext.session()
  if (session?.tenantId) config.headers['X-Tenant-Id'] = session.tenantId
  if (session?.accountId) config.headers['X-Trade-Account-Id'] = session.accountId
  if (session?.dataScope) config.headers['X-Data-Scope'] = session.dataScope
  if (session?.roleView) config.headers['X-Role-View'] = session.roleView
  if (session?.tradeMode) config.headers['X-Trade-Mode'] = session.tradeMode
  if (session?.brokerAdapter) config.headers['X-Broker-Adapter'] = session.brokerAdapter
  return config
})
