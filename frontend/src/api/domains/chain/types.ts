// Chain 域类型(从 client.ts 拆出, C 域拆分)

export interface PolicyInterpretRequest {
  text: string
  source?: Record<string, unknown>
  persist?: boolean
  provider?: string
}

export interface PolicyInterpretResponse {
  status: 'ok' | 'disabled' | 'error'
  interpretation_result: {
    summary: string
    industry_themes: Array<Record<string, unknown>>
    bom_nodes: string[]
    investment_logic: string
    risk_factors: Array<Record<string, unknown>>
  }
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    provider: string
    model: string
  }
  persisted: boolean
  reason?: string
}

export interface ChainDeconstructTree {
  node_id: string
  name: string
  layer?: number
  layer_id?: string
  layer_order?: number
  definition?: string
  key_questions?: string[]
  segments?: string[]
  evidence?: string[]
  companies?: string[]
  tracking_metrics?: string[]
  metrics?: {
    commercialization?: string[]
    expectation_gap?: string[]
    trigger_signals?: string[]
  }
  capex_evidence?: Array<{
    evidence_id: string
    company?: string
    region?: string
    fiscal_period?: string
    capex_amount?: number | null
    currency?: string
    capex_direction?: string[]
    mapped_layer_id: string
    mapped_segments?: string[]
    metric_usage?: string[]
    source_type?: string
    source_name?: string
    source_url?: string
    quote?: string
    as_of_date?: string
    evidence_level?: string
    collection_method?: string
    impact_direction?: string
    confidence?: string
  }>
  physical_metrics?: Array<{
    metric_id: string
    name: string
    mapped_layer_id: string
    mapped_segment?: string
    metric_usage?: string[]
    data_type?: string
    value?: number | string | null
    unit?: string
    period?: string
    direction?: string
    source_type?: string
    source_name?: string
    source_url?: string
    evidence_level?: string
    collection_method?: string
    as_of_date?: string
    impact_direction?: string
    confidence?: string
  }>
  evidence_chain?: Array<{
    evidence_id: string
    evidence_type: string
    mapped_layer_id: string
    mapped_segment?: string
    source_type?: string
    source_name?: string
    evidence_level?: string
    as_of_date?: string
    metric_usage?: string[]
    impact_direction?: string
    confidence?: string
  }>
  expectation_gap?: {
    expected?: Record<string, unknown>
    actual?: Record<string, unknown>
    gap_direction?: string
    gap_strength?: string
    calculation_method?: string
    formula?: string
    evidence_ids?: string[]
  }
  trigger_signal?: {
    signal_type?: string
    signal_strength?: string
    triggered_by_evidence_ids?: string[]
    mapped_layer_id?: string
    mapped_segments?: string[]
  }
  children?: ChainDeconstructTree[]
}

export interface ChainDeconstructTemplate {
  template_id: string
  name: string
  description?: string
  example_theme?: string
  source?: string
}

export interface ChainDeconstructResponse {
  theme: {
    id: string
    name: string
  }
  view: string
  template?: ChainDeconstructTemplate
  macro_context?: Array<{
    region: string
    policy_stance?: string
    inflation_state?: string
    rate_trend?: string
    liquidity_signal?: string
    source_type?: string
    source_name?: string
    source_url?: string
    as_of_date?: string
    evidence_level?: string
  }>
  tree: ChainDeconstructTree
}

export interface ChainNodeCompaniesResponse {
  node_id: string
  node_name: string
  company_count: number
  companies: unknown[]
}
