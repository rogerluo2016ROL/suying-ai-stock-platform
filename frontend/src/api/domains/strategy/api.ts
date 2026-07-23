import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type { StrategyPick } from './types'
import type {
  StrategyGenerateResponse,
  StrategyTemplatesResponse,
  StrategyPlansResponse,
  StrategyPlan,
} from '../../types'

/** Strategy 域 API (从 client.ts 拆出, C 域拆分)。 */
export const strategyApi = {
  generate: (picks: StrategyPick[], capital = 1_000_000): Promise<AxiosResponse<StrategyGenerateResponse>> =>
    api.post(`/strategy/generate?capital=${capital}`, picks),

  getTemplates: (): Promise<AxiosResponse<StrategyTemplatesResponse>> =>
    api.get('/strategy/templates'),

  getPlans: (): Promise<AxiosResponse<StrategyPlansResponse>> =>
    api.get('/strategy/plans'),

  createPlan: (name: string, modelName: string, maxPositions: number, capital = 1_000_000): Promise<AxiosResponse<{ plan: StrategyPlan }>> =>
    api.post(`/strategy/plans?name=${encodeURIComponent(name)}&model_name=${modelName}&max_positions=${maxPositions}&capital=${capital}`),

  getPlan: (planId: string): Promise<AxiosResponse<StrategyPlan>> =>
    api.get(`/strategy/plans/${planId}`),

  addPicks: (planId: string, picks: StrategyPick[]): Promise<AxiosResponse<void>> =>
    api.post(`/strategy/plans/${planId}/picks`, picks),

  deletePlan: (planId: string): Promise<AxiosResponse<void>> =>
    api.delete(`/strategy/plans/${planId}`),
}
