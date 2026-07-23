import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  SignalLiveResponse,
  SignalHistoryResponse,
  SignalAnalyzeResponse,
  DashboardSummaryResponse,
  DataStatusResponse,
  TriggerSyncResponse,
  SyncSchedulesResponse,
} from '../../types'

/** Signal 域 API (从 client.ts 拆出, C 域拆分)。 */
export const signalApi = {
  getLevels: (): Promise<AxiosResponse<string[]>> =>
    api.get('/signal/levels'),

  getLive: (session = 'intra'): Promise<AxiosResponse<SignalLiveResponse>> =>
    api.get(`/signal/live?session=${session}`),

  getHistory: (code?: string): Promise<AxiosResponse<SignalHistoryResponse>> =>
    api.get(`/signal/history${code ? `?code=${code}` : ''}`),

  analyzeCode: (code: string): Promise<AxiosResponse<SignalAnalyzeResponse>> =>
    api.get(`/signal/analyze/${code}`),

  getDashboardSummary: (): Promise<AxiosResponse<DashboardSummaryResponse>> =>
    api.get(`/signal/dashboard-summary?_t=${Date.now()}`),

  getScreeningDashboardSummary: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get(`/dashboard/summary?_t=${Date.now()}`),

  getDashboardAuction: (): Promise<AxiosResponse<Record<string, unknown>>> =>
    api.get('/dashboard/auction'),

  getDataStatus: (): Promise<AxiosResponse<DataStatusResponse>> =>
    api.get(`/signal/data-status?_t=${Date.now()}`),

  triggerSync: (tableKey: string, days: number): Promise<AxiosResponse<TriggerSyncResponse>> =>
    api.post(`/signal/trigger-sync?table_key=${tableKey}&days=${days}`),

  getSyncSchedules: (): Promise<AxiosResponse<SyncSchedulesResponse>> =>
    api.get('/signal/sync-schedules'),

  updateSyncSchedules: (params: string): Promise<AxiosResponse<void>> =>
    api.post(`/signal/sync-schedules?${params}`),

  deleteSyncSchedule: (key: string): Promise<AxiosResponse<void>> =>
    api.delete(`/signal/sync-schedules?table_key=${key}`),
}
