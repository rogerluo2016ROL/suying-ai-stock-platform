import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  TrainingModelsResponse,
  TrainingModelRecord,
  TrainingModelActionResponse,
  TrainingHistoryResponse,
  TrainingScheduleResponse,
  TrainingRunRequest,
  TrainingRunResponse,
} from './types'

/** Training 域 API (从 client.ts 拆出, C 域拆分)。 */
export const trainingApi = {
  runTraining: (body: TrainingRunRequest): Promise<AxiosResponse<TrainingRunResponse>> =>
    api.post('/training/run', body),

  getModels: (params: { page?: number; page_size?: number; model_type?: string; stage?: string } = {}): Promise<AxiosResponse<TrainingModelsResponse>> =>
    api.get('/training/models', { params: { page: 1, page_size: 20, ...params } }),

  getModel: (modelId: string): Promise<AxiosResponse<TrainingModelRecord>> =>
    api.get(`/training/models/${modelId}`),

  deployModel: (modelId: string, body: { force?: boolean; notes?: string } = {}): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/deploy`, body),

  rollbackModel: (modelId: string, body: { target_version: number; reason?: string }): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/rollback`, body),

  archiveModel: (modelId: string, body: { reason: string }): Promise<AxiosResponse<TrainingModelActionResponse>> =>
    api.post(`/training/models/${modelId}/archive`, body),

  getHistory: (params: { page?: number; page_size?: number; model_type?: string; status?: string } = {}): Promise<AxiosResponse<TrainingHistoryResponse>> =>
    api.get('/training/history', { params: { page: 1, page_size: 20, ...params } }),

  getSchedule: (): Promise<AxiosResponse<TrainingScheduleResponse>> =>
    api.get('/training/schedule'),
}
