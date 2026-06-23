export interface ThemeRow {
  theme_id: string
  name: string
  policy_weight: number
  keywords: string[]
  node_count: number
  matrix?: Record<string, number | null>
  interpretation?: string
  strategic_logic?: string
  bom_focus?: string[]
  evidence_focus?: string[]
  policy_refs?: string[]
}

export interface BomNode {
  node_id: string
  theme_id: string
  chain_id: string
  parent_node_id?: string | null
  child_node_ids?: string[]
  level: string
  name: string
  node_type: string
  keywords: string[]
  policy_theme?: string
  bom_path?: string[]
}

export interface ScoreDimension {
  key: string
  name: string
  weight: number
}

export interface CandidateCompany {
  code: string
  name?: string
  industry?: string
  rank?: number
  chain?: string
  layer?: string
  score?: number
  rating?: string
  trade_signal?: string
  policy_theme?: string
  bom_path?: string[]
  products?: string[]
  materials?: string[]
  last_trade_date?: string
  last_price?: number
  last_change_pct?: number
  candidate_source?: string
  pool_status?: string
  upstream_node?: string
  impact_role?: string
  downstream_chains?: string[]
  influence_paths?: string[]
  evidence_gaps?: string[]
  selection_reason?: string
  commercialization_stage?: string
  commercialization_cycle?: string
  resonance?: Record<string, string>
  dimension_scores?: Record<string, number>
  financial_indicators?: Record<string, number | string>
  moat_evidence?: Array<{ evidence_type?: string; summary?: string; confidence?: number }>
  evidence?: any[]
}

export interface DataFreshnessBucket {
  latest_trade_date?: string
  latest_pub_date?: string
  latest_month?: string
  row_count?: number
}

export interface SupplyChainDataFreshness {
  market?: DataFreshnessBucket
  research_reports?: DataFreshnessBucket
  broker_recommend?: DataFreshnessBucket
}

export interface ResearchIngestionStatus {
  auto_collection_status?: string
  llm_auto_extract_enabled?: boolean
  manual_extract_available?: boolean
  batch_extract_endpoint?: string
  source_table?: string
  source_latest_pub_date?: string
  source_row_count?: number
  message?: string
}

export interface SelectedNodeThesis {
  node_id?: string
  name?: string
  policy_theme?: string
  bom_path?: string[]
  keywords?: string[]
  thesis?: string
  trigger_conditions?: string[]
  risk_factors?: string[]
  mapping_status?: string
  mapping_message?: string
}
