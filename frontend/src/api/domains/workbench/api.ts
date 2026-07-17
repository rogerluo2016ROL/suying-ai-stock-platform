import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type { WorkbenchPageEnvelope } from '../../types'

/** Workbench 域 API (从 client.ts 拆出, C 域拆分)。 */
export const workbenchApi = {
  getPage: (modulePath: string): Promise<AxiosResponse<WorkbenchPageEnvelope>> => {
    const normalized = modulePath.replace(/^\/+/, '')
    const path = normalized.split('/').filter(Boolean).map(encodeURIComponent).join('/')
    return api.get(`/workbench/${path}`)
  },
}
