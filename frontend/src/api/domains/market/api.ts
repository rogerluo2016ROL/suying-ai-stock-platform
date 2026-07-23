import type { AxiosResponse } from 'axios'
import { api, publicMarketApi } from '../../http'
import type { MarketIndexQuotesResponse } from '../../types'

/** Market 域 (从 client.ts 拆出, C 域拆分; eastmoney 辅助随迁)。 */

const eastmoneyIndexSecids = ['1.000001', '0.399001', '0.399006', '0.899050']

function eastmoneyScaledNumber(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? Number((number / 100).toFixed(2)) : undefined
}

export const marketApi = {
  getIndexQuotes: async (): Promise<AxiosResponse<MarketIndexQuotesResponse>> => {
    try {
      const responses = await Promise.all(
        eastmoneyIndexSecids.map(secid =>
          publicMarketApi.get('https://push2.eastmoney.com/api/qt/stock/get', {
            params: {
              secid,
              fields: 'f43,f48,f57,f58,f169,f170',
            },
          }),
        ),
      )
      const diff = responses
        .map(response => response.data?.data)
        .filter(Boolean)
        .map(row => ({
          f12: row.f57,
          f14: row.f58,
          f2: eastmoneyScaledNumber(row.f43),
          f3: eastmoneyScaledNumber(row.f170),
          f4: eastmoneyScaledNumber(row.f169),
          f6: row.f48,
        }))
      if (diff.length > 0) {
        return {
          ...responses[0],
          data: { source: 'eastmoney_realtime', data: { diff } },
        }
      }
    } catch {
      // Fall through to local post-market close snapshot.
    }
    return api.get('/screener/market/index-quotes')
  },
}
