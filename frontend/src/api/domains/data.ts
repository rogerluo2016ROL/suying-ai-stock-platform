import { domainHttp } from '../core/http'

export const dataDomainApi = {
  status: () => domainHttp.get('/data/status'),
  readiness: (profile: string) => domainHttp.get('/data/readiness', { params: { profile } }),
  schedules: () => domainHttp.get('/data/schedules'),
}
