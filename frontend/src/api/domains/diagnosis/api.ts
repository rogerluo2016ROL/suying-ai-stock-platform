import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  DiagnosisReport,
  DiagnosisCompareResponse,
  DiagnosisHistoryResponse,
} from '../../types'

/** Diagnosis 域 API (从 client.ts 拆出, C 域拆分)。 */
export const diagnosisApi = {
  analyze: (code: string, forceRefresh = false): Promise<AxiosResponse<DiagnosisReport>> =>
    api.post('/diagnosis/analyze', { code, force_refresh: forceRefresh }),

  compare: (codes: string[], dimensions?: string[], forceRefresh = false): Promise<AxiosResponse<DiagnosisCompareResponse>> =>
    api.post('/diagnosis/compare', { codes, dimensions, force_refresh: forceRefresh }),

  getHistory: (): Promise<AxiosResponse<DiagnosisHistoryResponse>> =>
    api.get('/diagnosis/history'),

  getReportPdf: (code: string): Promise<AxiosResponse<Blob>> =>
    api.get(`/diagnosis/report/${code}/pdf`, { responseType: 'blob' }),
}
