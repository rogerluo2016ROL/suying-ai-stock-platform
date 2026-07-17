import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type { UnreadAlertCountResponse } from '../../types'

/** Alert 域 API (从 client.ts 拆出, C 域拆分)。 */
export const alertApi = {
  getChannels: (): Promise<AxiosResponse<unknown>> =>
    api.get('/alert/channels'),

  getConfig: (): Promise<AxiosResponse<unknown>> =>
    api.get('/alert/config'),

  getUnreadCount: (): Promise<AxiosResponse<UnreadAlertCountResponse>> =>
    api.get('/alert/unread-count'),
}
