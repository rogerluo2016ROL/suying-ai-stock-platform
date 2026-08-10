import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type { StrategyPick } from './types'
import type {
  StrategyGenerateResponse,
  StrategyTemplatesResponse,
  StrategyPlansResponse,
  StrategyPlan,
} from '../../types'

/** Strategy 域 API（含方案 CRUD + 执行器控制，统一入口）。 */
export const strategyApi = {
  // ── 方案 CRUD ──
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

  // ── 执行器（量化交易）──
  listInstances: (status?: string): Promise<AxiosResponse> =>
    api.get('/strategy/list', { params: status ? { status } : undefined }),

  getInstance: (id: string): Promise<AxiosResponse> =>
    api.get(`/strategy/${id}`),

  /** 更新策略实例参数（PRD AC-10.8）。position_rules 整体替换，调用方需合并现有仓位规则。 */
  updateInstance: (id: string, body: {
    name?: string
    description?: string
    capital?: number
    trade_mode?: string
    check_interval_sec?: number
    position_rules?: Record<string, number>
    risk_rules?: Record<string, number>
  }): Promise<AxiosResponse> =>
    api.put(`/strategy/${id}`, body),

  getInstanceLog: (id: string): Promise<AxiosResponse> =>
    api.get(`/strategy/${id}/log`),

  startInstance: (id: string): Promise<AxiosResponse> =>
    api.post(`/strategy/${id}/start`),

  pauseInstance: (id: string): Promise<AxiosResponse> =>
    api.post(`/strategy/${id}/pause`),

  resumeInstance: (id: string): Promise<AxiosResponse> =>
    api.post(`/strategy/${id}/resume`),

  stopInstance: (id: string): Promise<AxiosResponse> =>
    api.post(`/strategy/${id}/stop`),
}
