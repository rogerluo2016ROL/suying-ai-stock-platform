import type { CompetitionLabel, ValueChainLabel } from '../../api/domains/chain/types'

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
  /** 传导链 (transmission) 位置 (migration 040), 与钻取链 L1-L8 不同维度 */
  transmission_layer?: string
  transmission_layer_name?: string
  /** overlay 注解标签 (chain/deconstruct 传 overlays=[...] 时按 node_id 合并) */
  value_chain?: ValueChainLabel
  competition?: CompetitionLabel
}

export interface ScoreDimension {
  key: string
  name: string
  weight: number
}

export interface WorkbenchModel {
  name?: string
  philosophy?: string
  score_dimensions?: ScoreDimension[]
}

/** 链路模板 key（chain/deconstruct template 参数，default = 不传） */
export type ChainTemplateKey =
  | 'default'
  | 'complex_tech'
  | 'ai_compute_infrastructure'
  | 'advanced_packaging_chiplet'
  | 'semiconductor_equipment_materials'
  | 'lithography_equipment_chain'
  | 'data_ai_application_commercialization'
  | 'defense_informatization_unmanned'
  | 'intelligent_driving_v2x'
  | 'controlled_fusion_materials'
  | 'industrial_machine_tools_cnc'
  | 'innovative_drug_cxo_adc_glp1'
  | 'flexible_dc_offshore_wind_grid'
  | 'rare_earth_minor_metals_security'
  | 'display_oled_microled'
  | 'domestic_os_database_industrial_software'
  | 'huawei_ascend_ai_ecosystem'
  | 'offshore_wind_subsea_cable'
  | 'new_power_system_grid'
  | 'embodied_intelligence'
  | 'storage_chips'

export interface CandidateCompany {
  code: string
  name?: string
  industry?: string
  rank?: number
  chain?: string
  layer?: string
  node_id?: string
  node_name?: string
  score?: number
  rating?: string
  trade_signal?: string
  mapping_confidence?: number
  mapping_id?: string
  mapping_status?: string
  mapping_source?: string
  mapping_quality_weight?: number
  mapping_adjusted_score?: number
  policy_theme?: string
  bom_path?: string[]
  products?: string[]
  materials?: string[]
  report_titles?: string[]
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
  /** V6: chokepoint score for卡脖子评分 */
  chokepoint_score?: number
  /** V6: gross margin percentage */
  gross_margin?: number
  /** V6: performance yield */
  performance_yield?: number
  /** V6: main business percentage */
  main_pct?: number
  /** V6: policy match score */
  policy_match_score?: number
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

// ─────────────────────────────────────────────────────────────────
// V6 ChainCandidate to CandidateCompany conversion
// ─────────────────────────────────────────────────────────────────

import type { ChainCandidate, ThreeFactorScores, ResonanceLevel } from '../../api/client'

/**
 * Convert V6 ChainCandidate to CandidateCompany for compatibility
 * with existing CandidateCompanyTable and ChainBubbleChart
 */
export function chainCandidateToCandidateCompany(candidate: ChainCandidate): CandidateCompany {
  // Build resonance info from three_factor_scores
  const resonance: Record<string, string> = {}
  if (candidate.three_factor_scores) {
    const { industry_cycle, policy_intensity, performance_proof } = candidate.three_factor_scores
    if (industry_cycle) {
      resonance.industry_cycle = `${industry_cycle.stage || '--'}:${industry_cycle.score || 0}`
    }
    if (policy_intensity) {
      resonance.policy_intensity = `${policy_intensity.stars || 0}:${policy_intensity.score || 0}`
    }
    if (performance_proof) {
      resonance.performance_proof = `${performance_proof.status || '--'}:${performance_proof.score || 0}`
    }
  }

  // Build dimension_scores from three_factor_scores
  const dimension_scores: Record<string, number> = {}
  if (candidate.three_factor_scores) {
    const { policy_intensity, performance_proof } = candidate.three_factor_scores
    if (policy_intensity?.score) {
      dimension_scores.policy_intensity = policy_intensity.score
    }
    if (performance_proof?.score) {
      dimension_scores.performance_proof = performance_proof.score
    }
  }
  // Add chokepoint_score
  if (candidate.chokepoint_score) {
    dimension_scores.chokepoint = candidate.chokepoint_score
  }

  // Determine trade_signal based on resonance_level
  const tradeSignal = candidate.resonance_level === '强启动' ? '强启动'
    : candidate.resonance_level === '启动' ? '启动'
    : candidate.resonance_level === '关注' ? '关注'
    : candidate.trade_signal || '观察'

  return {
    code: candidate.code,
    name: candidate.name,
    mapping_id: candidate.mapping_id,
    score: candidate.score,
    rating: candidate.chokepoint_score?.toString() || '',
    trade_signal: tradeSignal,
    chokepoint_score: candidate.chokepoint_score,
    resonance,
    dimension_scores,
    last_price: candidate.last_price,
    last_change_pct: candidate.last_change_pct,
    last_trade_date: candidate.last_trade_date,
    gross_margin: candidate.gross_margin,
    performance_yield: candidate.performance_yield,
    main_pct: candidate.main_pct,
    policy_match_score: candidate.policy_match_score,
    commercialization_stage: candidate.commercialization_note?.split('，')[0] || undefined,
    commercialization_cycle: candidate.three_factor_scores?.industry_cycle?.stage || undefined,
    selection_reason: candidate.commercialization_note || candidate.evidence?.[0] || undefined,
    evidence: candidate.evidence,
  }
}
