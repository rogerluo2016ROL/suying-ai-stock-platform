// Supply Chain 域类型(从 client.ts 拆出, C 域拆分)

export type SupplyChainWorkbenchParams = number | {
  topN?: number
  themeId?: string
  nodeId?: string
}

export interface SupplyChainCandidateRankingParams {
  topN?: number
  chainId?: string
  signal?: string
}

export interface SupplyChainCapexEvidenceReviewQueueParams {
  limit?: number
  chainId?: string
  reviewStatus?: 'pending_review' | 'approved' | 'rejected'
}

export type SupplyChainMappingReviewStatus = 'reviewable' | 'pending_review' | 'weak_evidence' | 'verified' | 'rejected'

export interface SupplyChainMappingReviewQueueParams {
  status?: SupplyChainMappingReviewStatus
  nodeId?: string
  chainId?: string
  limit?: number
  offset?: number
}

export interface SupplyChainMappingReviewItem {
  code: string
  name?: string
  node_id: string
  node_name?: string
  chain_id?: string
  product_name?: string | null
  material_name?: string | null
  confidence?: number
  status: string
  mapping_source?: string
  evidence?: string[]
  evidence_gaps?: string[]
  updated_at?: string
  review_priority?: number
}

export interface SupplyChainMappingQuality {
  mapping_count: number
  review_queue_count: number
  status_counts: Record<string, number>
  source_counts: Record<string, number>
  hotspot_nodes: Array<{
    node_id: string
    node_name?: string
    chain_id?: string
    verified?: number
    pending_review?: number
    weak_evidence?: number
    rejected?: number
    review_pressure?: number
  }>
}

export interface SupplyChainMappingReviewDecision {
  decision: 'verified' | 'rejected' | 'needs_more_evidence' | 'pending_review'
  reviewer?: string
  note?: string
}

export interface EvidenceChainDocument {
  doc_id: string
  source_id?: string
  source_type?: string
  title?: string
  publish_time?: string
  crawl_time?: string
  url?: string
  source_level?: string
  doc_status?: string
  license_status?: string
}

export interface EvidenceChainFact {
  fact_id: string
  mapping_id?: string
  fact_type?: string
  fact_nature?: string
  fact_value?: string
  original_quote?: string
  source_level?: string
  confidence?: number
  validation_status?: string
  research_stage_signal?: string
  commercial_stage_signal?: string
  growth_signal?: boolean
  profit_signal?: boolean
  moat_signal?: boolean
  risk_signal?: boolean
  created_at?: string
}

export interface EvidenceChainFreshness {
  mapping_id?: string
  freshness_status?: string
  days_since_update?: number
  last_strong_evidence_date?: string
  last_mid_evidence_date?: string
  last_weak_signal_date?: string
  last_any_evidence_date?: string
  next_review_date?: string
  stale_reason?: string
  updated_at?: string
}

export interface EvidenceChainStageTransition {
  transition_id: string
  mapping_id?: string
  old_research_stage?: string
  new_research_stage?: string
  old_commercial_stage?: string
  new_commercial_stage?: string
  trigger_fact_id?: string
  review_status?: string
  change_reason?: string
  created_at?: string
}

export interface EvidenceChainExpectation {
  monitor_id: string
  mapping_id?: string
  claim_text?: string
  claim_source_type?: string
  expected_result?: string
  actual_progress?: string
  gap_status?: string
  expected_date?: string
  review_status?: string
  created_at?: string
}

export interface EvidenceChainResponse {
  version: string
  mapping_id: string
  source_status: string
  documents: EvidenceChainDocument[]
  facts: EvidenceChainFact[]
  freshness: EvidenceChainFreshness | Record<string, never>
  stage_transitions: EvidenceChainStageTransition[]
  expectations: EvidenceChainExpectation[]
  limitations?: string[]
}

export interface EvidenceReviewQueueResponse {
  version: string
  queue: Array<Record<string, unknown>>
  counts: Record<string, number>
  limitations?: string[]
}

export interface CapexEvidenceReviewItem {
  capex_evidence_id: string
  mapping_id: string
  code: string
  company_name?: string
  chain_id?: string
  node_id?: string
  tag_name?: string
  fiscal_period?: string
  as_of_date?: string | null
  capex_amount?: number | null
  capex_amount_unit?: string
  currency?: string
  capex_direction?: string[]
  mapped_layer_id?: string
  mapped_segments?: string[]
  source_type?: string
  source_level?: string
  source_name?: string
  source_url?: string
  quote?: string
  evidence_level?: string
  confidence?: number
  review_status?: string
  amount_is_total_capex?: boolean
  amount_is_segment_capex?: boolean
  direction_is_ai_related?: boolean
  metadata?: Record<string, unknown>
  created_at?: string | null
}

export interface CapexEvidenceReviewQueueResponse {
  version: string
  source_status: string
  filters: Record<string, unknown>
  counts: Record<string, number>
  queue: CapexEvidenceReviewItem[]
  limitations?: string[]
}

export interface CapexEvidenceReviewRequest {
  review_status: 'approved' | 'rejected' | 'pending_review'
  reviewer?: string
  note?: string
  confidence?: number
}

export interface SupplyChainCandidateRankingItem {
  rank: number
  chain_id: string
  code: string
  name?: string
  industry?: string
  rank_score: number
  avg_rank_score?: number
  signal: string
  tag_count: number
  best_mapping_id: string
  best_tag_name: string
  node_id?: string
  mapping_status?: string
  three_high_total?: number
  growth_score?: number
  profit_score?: number
  moat_score?: number
  stage_score?: number
  evidence_score?: number
  expectation_gap_score?: number
  gap_type?: string
  research_stage?: string
  commercialization_stage?: string
  commercialization_indicator?: string
  expectation_gap_indicator?: string
  trigger_signal_indicator?: string
  bigtech_capex_tailwind?: {
    score?: number
    matched_layers?: string[]
    company_count?: number
    record_count?: number
    companies?: string[]
    commercialization_indicator?: string
    expectation_gap_indicator?: string
    trigger_signal_indicator?: string
  }
  company_capex_evidence?: {
    score?: number
    evidence_count?: number
    amount_count?: number
    direction_ai_count?: number
    fresh_count?: number
    avg_confidence?: number
    latest_as_of_date?: string
    directions?: string[] | string[][]
    indicator?: string
  }
  l8_match_rate?: number
  fresh_rate?: number
  freshness_status?: string
  fact_count?: number
  latest_price?: number
  latest_trade_date?: string
  change_1d_pct?: number
  change_20d_pct?: number
  mapping_ids?: string[]
  tag_names?: string[]
}

export interface SupplyChainCandidateRankingResponse {
  version: string
  source_status: string
  filters: {
    top_n: number
    chain_id?: string | null
    signal?: string | null
  }
  summary: {
    mapping_rows?: number
    company_chain_rows?: number
    chain_count?: number
    signal_distribution?: Record<string, number>
    bigtech_capex_context?: {
      company_count?: number
      record_count?: number
      companies?: string[]
    }
  }
  items: SupplyChainCandidateRankingItem[]
  by_chain: Record<string, SupplyChainCandidateRankingItem[]>
  limitations?: string[]
}
