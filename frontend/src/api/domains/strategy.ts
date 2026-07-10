import { domainHttp } from '../core/http'

export const strategyDomainApi = {
  plans: () => domainHttp.get('/strategy/plans'),
  generate: (payload: Record<string, unknown>) => domainHttp.post('/strategy/generate', payload),
  compare: (payload: Record<string, unknown>) => domainHttp.post('/strategy/compare', payload),
}
