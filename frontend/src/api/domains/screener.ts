import { domainHttp } from '../core/http'

export const screenerDomainApi = {
  modes: () => domainHttp.get('/screener/modes'),
  run: (payload: Record<string, unknown>) => domainHttp.post('/screener/run', payload),
  factorEvidence: (modelKey: string) => domainHttp.get('/backtest/factor-evidence', { params: { model_key: modelKey } }),
}
