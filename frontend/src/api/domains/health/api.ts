import type { AxiosResponse } from 'axios'
import { api, rootApi } from '../../http'
import type { HealthCheckResponse } from '../../types'

/** Health 域 (从 client.ts 拆出, C 域拆分)。 */

export class HealthCheckError extends Error {
  constructor(public readonly service: string, public readonly cause?: unknown) {
    super(`health check failed for service "${service}"`)
    this.name = 'HealthCheckError'
  }
}

export const healthApi = {
  runtimeReadiness: (): Promise<AxiosResponse<{ live: boolean; ready: boolean; services: Record<string, { ready: boolean; error?: string }> }>> =>
    rootApi.get('/v1/runtime/readiness'),

  check: (service: string): Promise<AxiosResponse<HealthCheckResponse>> =>
    api.get(`/${service}/health`).catch((err: unknown) => {
      throw new HealthCheckError(service, err)
    }),

  gateway: (): Promise<AxiosResponse<HealthCheckResponse>> =>
    rootApi.get('/health').catch((err: unknown) => {
      throw new HealthCheckError('gateway', err)
    }),

  checkOnline: async (service: string): Promise<boolean> => {
    try {
      const res = await api.get<HealthCheckResponse>(`/${service}/health`)
      const status = String(res.data?.status ?? '')
      return status === 'online' || status === 'healthy'
    } catch {
      return false
    }
  },
}
