import { domainHttp } from '../core/http'

export const modelsDomainApi = {
  registry: () => domainHttp.get('/training/models'),
  train: (payload: Record<string, unknown>) => domainHttp.post('/training/train', payload),
  promote: (modelId: string, payload: Record<string, unknown>) => domainHttp.post(`/training/models/${modelId}/deploy`, payload),
}
