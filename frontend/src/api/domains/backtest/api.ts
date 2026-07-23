import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  FactorsResponse,
  FactorEvidenceResponse,
  BacktestRunResponse,
  BacktestCompareResponse,
} from '../../types'

/** Backtest 域 API (从 client.ts 拆出, C 域拆分)。 */
export const backtestApi = {
  getFactors: (): Promise<AxiosResponse<FactorsResponse>> =>
    api.get('/backtest/factors'),

  getFactorEvidence: (modelKey: string) =>
    api.get<FactorEvidenceResponse>('/backtest/factor-evidence', { params: { model_key: modelKey } }),

  run: (params: {
    mode?: string
    windows?: number
    top_n?: number
    forward_days?: number
  } = {}): Promise<AxiosResponse<BacktestRunResponse>> => {
    const { mode = 'all', windows = 3, top_n = 30, forward_days = 60 } = params
    const qs = new URLSearchParams({ mode, windows: String(windows), top_n: String(top_n), forward_days: String(forward_days) })
    return api.post(`/backtest/run?${qs.toString()}`)
  },

  calibrate: (mode = 'all'): Promise<AxiosResponse<unknown>> =>
    api.post(`/backtest/calibrate?mode=${mode}`),

  compare: (params: {
    strategy_ids?: string[]
    start_date?: string
    end_date?: string
  } = {}): Promise<AxiosResponse<BacktestCompareResponse>> => {
    const { strategy_ids = ['momentum', 'quality'], start_date, end_date } = params
    const qs = new URLSearchParams()
    strategy_ids.forEach(id => qs.append('strategy_ids', id))
    if (start_date) qs.set('start_date', start_date)
    if (end_date) qs.set('end_date', end_date)
    return api.post(`/backtest/compare?${qs.toString()}`)
  },
}
