// Supply Chain 域 build 辅助(从 client.ts 拆出, C 域拆分)

import type {
  SupplyChainWorkbenchParams,
  SupplyChainMappingReviewQueueParams,
  SupplyChainCandidateRankingParams,
  SupplyChainCapexEvidenceReviewQueueParams,
} from './types'

export const buildSupplyChainWorkbenchPath = (params: SupplyChainWorkbenchParams = {}) => {
  const topN = typeof params === 'number' ? params : params.topN ?? 30
  const search = new URLSearchParams({ top_n: String(topN) })
  if (typeof params !== 'number') {
    if (params.themeId) search.set('theme_id', params.themeId)
    if (params.nodeId) search.set('node_id', params.nodeId)
  }
  return `/screener/supply-chain/workbench?${search.toString()}`
}

export const buildSupplyChainMappingReviewQueuePath = (params: SupplyChainMappingReviewQueueParams = {}) => {
  const search = new URLSearchParams({
    status: params.status || 'reviewable',
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  })
  if (params.nodeId) search.set('node_id', params.nodeId)
  if (params.chainId) search.set('chain_id', params.chainId)
  return `/screener/supply-chain/mapping-review/queue?${search.toString()}`
}

export const buildSupplyChainCandidateRankingPath = (params: SupplyChainCandidateRankingParams = {}) => {
  const search = new URLSearchParams({
    top_n: String(params.topN ?? 100),
  })
  if (params.chainId) search.set('chain_id', params.chainId)
  if (params.signal) search.set('signal', params.signal)
  return `/screener/supply-chain/candidate-ranking?${search.toString()}`
}

export const buildSupplyChainCapexEvidenceReviewQueuePath = (params: SupplyChainCapexEvidenceReviewQueueParams = {}) => {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 50),
    review_status: params.reviewStatus || 'pending_review',
  })
  if (params.chainId) search.set('chain_id', params.chainId)
  return `/screener/supply-chain/capex-evidence-review/queue?${search.toString()}`
}
