import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  PredictionStatus,
  PredictionResponse,
  FastPredictionResponse,
  BatchPredictionResponse,
} from '../../types'

/** Prediction 域 API (从 client.ts 拆出, C 域拆分)。 */
export const predictionApi = {
  getStatus: (): Promise<AxiosResponse<PredictionStatus>> =>
    api.get('/prediction/status'),

  getOverview: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/prediction/overview'),

  predict: (code: string, predDays = 10): Promise<AxiosResponse<PredictionResponse>> =>
    api.post(`/prediction/${code}?pred_days=${predDays}`),

  predictFast: (code: string, predDays = 15): Promise<AxiosResponse<FastPredictionResponse>> =>
    api.post(`/prediction/${code}/fast?pred_days=${predDays}`),

  predictBatch: (codes: string[], days = 30): Promise<AxiosResponse<BatchPredictionResponse>> =>
    api.post(`/prediction/${codes[0]}/meta?pred_days=${days}`, codes),

  compare: (codes: string[], predDays = 20): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.post(`/prediction/compare?pred_days=${predDays}`, codes),

  getAccuracyBacktest: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/prediction/accuracy-backtest'),
}
