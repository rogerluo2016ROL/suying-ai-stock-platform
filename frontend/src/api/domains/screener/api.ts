import type { AxiosResponse } from 'axios'
import { api } from '../../http'
import type {
  ScreenerModesResponse,
  ScreenerRunResponse,
  SupplyChainBomResponse,
  MappingQualityResponse,
  MappingReviewQueueResponse,
  CandidatePoolRecordRequest,
  CandidatePoolRecordResponse,
  CandidatePoolQueryParams,
  CandidatePoolQueryResponse,
  WatchlistAddRequest,
  WatchlistAddResponse,
  WatchlistQueryParams,
  WatchlistQueryResponse,
  WatchlistDeleteResponse,
} from '../../types'
import type {
  SupplyChainWorkbenchParams,
  SupplyChainCandidateRankingParams,
  SupplyChainCandidateRankingResponse,
  SupplyChainMappingReviewQueueParams,
  EvidenceChainResponse,
  EvidenceReviewQueueResponse,
  SupplyChainCapexEvidenceReviewQueueParams,
  CapexEvidenceReviewQueueResponse,
  CapexEvidenceReviewRequest,
  SupplyChainMappingReviewDecision,
} from '../supply-chain/types'
import {
  buildSupplyChainWorkbenchPath,
  buildSupplyChainCandidateRankingPath,
  buildSupplyChainMappingReviewQueuePath,
  buildSupplyChainCapexEvidenceReviewQueuePath,
} from '../supply-chain/build'

/** Screener 域 API(从 client.ts 拆出, C 域拆分)。含 supply-chain 相关方法,保持对象结构不变。 */
export const screenerApi = {
  getModes: (): Promise<AxiosResponse<ScreenerModesResponse>> =>
    api.get('/screener/modes'),

  run: (mode: string, topN = 30, tradeDate?: string): Promise<AxiosResponse<ScreenerRunResponse>> => {
    const params = new URLSearchParams({ mode, top_n: String(topN) })
    if (tradeDate) params.set('trade_date', tradeDate)
    return api.post(`/screener/run?${params.toString()}`)
  },

  getSupplyChainThemes: (): Promise<AxiosResponse<SupplyChainBomResponse['themes']>> =>
    api.get('/screener/supply-chain/themes'),

  getSupplyChainBom: (): Promise<AxiosResponse<SupplyChainBomResponse>> =>
    api.get('/screener/supply-chain/bom'),

  getSupplyChainWorkbench: (params: SupplyChainWorkbenchParams = {}): Promise<AxiosResponse<unknown>> =>
    api.get(buildSupplyChainWorkbenchPath(params)),

  getSupplyChainCandidateRanking: (params: SupplyChainCandidateRankingParams = {}): Promise<AxiosResponse<SupplyChainCandidateRankingResponse>> =>
    api.get(buildSupplyChainCandidateRankingPath(params)),

  getSupplyChainNode: (nodeId: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/node/${encodeURIComponent(nodeId)}`),

  getSupplyChainCompany: (code: string): Promise<AxiosResponse<unknown>> =>
    api.get(`/screener/supply-chain/company/${encodeURIComponent(code)}`),

  getSupplyChainMappingQuality: (): Promise<AxiosResponse<MappingQualityResponse>> =>
    api.get('/screener/supply-chain/mapping-review/quality'),

  getSupplyChainMappingReviewQueue: (params: SupplyChainMappingReviewQueueParams = {}): Promise<AxiosResponse<MappingReviewQueueResponse>> =>
    api.get(buildSupplyChainMappingReviewQueuePath(params)),

  getSupplyChainEvidenceChain: (mappingId: string): Promise<AxiosResponse<EvidenceChainResponse>> =>
    api.get(`/screener/supply-chain/business-tag/${encodeURIComponent(mappingId)}/evidence-chain`),

  getSupplyChainEvidenceReviewQueue: (limit = 50): Promise<AxiosResponse<EvidenceReviewQueueResponse>> =>
    api.get(`/screener/supply-chain/evidence-review/queue?limit=${encodeURIComponent(String(limit))}`),

  getSupplyChainCapexEvidenceReviewQueue: (params: SupplyChainCapexEvidenceReviewQueueParams = {}): Promise<AxiosResponse<CapexEvidenceReviewQueueResponse>> =>
    api.get(buildSupplyChainCapexEvidenceReviewQueuePath(params)),

  reviewSupplyChainCapexEvidence: (capexEvidenceId: string, payload: CapexEvidenceReviewRequest): Promise<AxiosResponse<unknown>> =>
    api.post(`/screener/supply-chain/capex-evidence/${encodeURIComponent(capexEvidenceId)}/review`, payload),

  reviewSupplyChainMapping: (code: string, nodeId: string, decision: SupplyChainMappingReviewDecision): Promise<AxiosResponse<void>> =>
    api.post(
      `/screener/supply-chain/mapping-review/${encodeURIComponent(code)}/${encodeURIComponent(nodeId)}`,
      decision,
    ),

  extractSupplyChainFacts: (text: string, source: Record<string, unknown> = {}, persist = false): Promise<AxiosResponse<unknown>> =>
    api.post('/screener/supply-chain/extract', { text, source, persist }),

  // 候选池(account-scoped 私有对象):scope 由 client 拦截器注入 X-Tenant-Id
  // X-Trade-Account-Id 头,前端不传明文 tenant/owner/account。打通「选股→加候选池→决策」主链路咽喉(M0)。
  recordCandidatePool: (payload: CandidatePoolRecordRequest): Promise<AxiosResponse<CandidatePoolRecordResponse>> =>
    api.post('/screener/candidate-pool', payload),

  queryCandidatePool: (params: CandidatePoolQueryParams = {}): Promise<AxiosResponse<CandidatePoolQueryResponse>> => {
    const qs = new URLSearchParams()
    if (params.source_module) qs.set('source_module', params.source_module)
    if (params.source_mode) qs.set('source_mode', params.source_mode)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get(query ? `/screener/candidate-pool?${query}` : '/screener/candidate-pool')
  },

  // watchlist(自选股,Batch B #11)—— scope 走拦截器头,前端不传明文(契约§9.3)
  addWatchlist: (payload: WatchlistAddRequest): Promise<AxiosResponse<WatchlistAddResponse>> =>
    api.post('/screener/watchlist', payload),
  listWatchlist: (params: WatchlistQueryParams = {}): Promise<AxiosResponse<WatchlistQueryResponse>> => {
    const qs = new URLSearchParams()
    if (params.code) qs.set('code', params.code)
    if (params.page) qs.set('page', String(params.page))
    if (params.page_size) qs.set('page_size', String(params.page_size))
    const query = qs.toString()
    return api.get(query ? `/screener/watchlist?${query}` : '/screener/watchlist')
  },
  removeWatchlist: (key: { code?: string; id?: number }): Promise<AxiosResponse<WatchlistDeleteResponse>> => {
    const qs = new URLSearchParams()
    if (key.code) qs.set('code', key.code)
    if (key.id) qs.set('id', String(key.id))
    return api.delete(`/screener/watchlist?${qs.toString()}`)
  },
}
