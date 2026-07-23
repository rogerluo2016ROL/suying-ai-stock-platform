import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type { ChainCandidate, ChainCandidatesResponse } from '../../types'
import type {
  PolicyInterpretResponse,
  ChainDeconstructResponse,
  ChainNodeCompaniesResponse,
} from './types'
import { buildSupplyChainWorkbenchPath } from '../supply-chain/build'

/** Chain 域 API(从 client.ts 拆出, C 域拆分)。 */
export const chainApi = {
  interpretPolicy: (
    text: string,
    source?: Record<string, unknown>,
    persist = false,
    provider = 'deepseek',
  ): Promise<AxiosResponse<PolicyInterpretResponse>> =>
    api.post('/screener/policy/interpret', {
      text,
      source,
      persist,
      provider,
    }),

  deconstructChain: (params: { theme_id: string; method?: string; template?: string; overlays?: string[] }): Promise<AxiosResponse<ChainDeconstructResponse>> => {
    const { theme_id, method = 'upstream_downstream', template, overlays } = params
    const qs = new URLSearchParams({ theme_id, method })
    if (template) qs.set('template', template)
    // overlay 注解可叠加: overlays=value_chain&overlays=competition
    overlays?.forEach(name => qs.append('overlays', name))
    return api.get(`/screener/chain/deconstruct?${qs.toString()}`)
  },

  getNodeCompanies: (nodeId: string): Promise<AxiosResponse<ChainNodeCompaniesResponse>> =>
    api.get(`/screener/chain/node/${encodeURIComponent(nodeId)}/companies`),

  getCandidates: (params: {
    filter?: string
    resonance_level?: string
    top_n?: number
    trade_date?: string
  } = {}): Promise<AxiosResponse<ChainCandidatesResponse>> => {
    const { filter = 'all', resonance_level, top_n = 30, trade_date } = params
    const workbenchPath = buildSupplyChainWorkbenchPath({ topN: top_n })
    return api.get(workbenchPath).then((response) => {
      const body = response.data as {
        candidates?: ChainCandidate[]
        candidate_count?: number
        filter_summary?: Record<string, number>
        resonance_summary?: Record<string, number>
      }
      return {
        ...response,
        data: {
          filter,
          resonance_level,
          trade_date,
          total_count: body.candidate_count ?? body.candidates?.length ?? 0,
          candidates: body.candidates || [],
          filter_summary: body.filter_summary || {},
          resonance_summary: body.resonance_summary || {},
          elapsed_ms: 0,
        },
      } as AxiosResponse<ChainCandidatesResponse>
    })
  },
}
