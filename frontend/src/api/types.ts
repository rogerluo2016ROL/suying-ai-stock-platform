/* ============================================================
   速赢AI — API TypeScript 类型定义

   来源：docs/design/new front/IMPLEMENTATION_PLAN.md 阶段1.2
   用途：定义所有API响应的TypeScript类型，替换 client.ts 中的 `any`

   设计文档要求：
   - 价格、涨跌幅、评分使用等宽字体 + font-variant-numeric: tabular-nums
   - 字段名与后端 _normalize_picks() 输出一致
   ============================================================ */

// ═══════════════════════════════════════════════════════════════════════════
// 通用类型
// ═══════════════════════════════════════════════════════════════════════════

/** 股票基础信息（代码 + 名称） */
export interface StockBase {
  code: string;
  name?: string;
}

/** 价格/涨跌幅等数值（使用等宽数字渲染） */
export interface NumericValue {
  price?: number;
  change_pct?: number;
  volume?: number;
  turnover?: number;
  score?: number;
}

/** API 响应通用包装 */
export interface ApiResponse<T> {
  data: T;
  status?: number;
  message?: string;
}

/** 分页参数 */
export interface PaginationParams {
  limit?: number;
  offset?: number;
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export type WorkbenchDataDomain = 'public' | 'tenant' | 'user' | 'account';
export type WorkbenchFreshnessStatus = 'fresh' | 'stale' | 'fallback' | 'unknown' | 'missing' | 'outdated';

export interface ModelMetadata {
  name: string;
  version?: string;
  provider?: string;
  inference_mode?: string;
  checkpoint_status?: string;
  loaded?: boolean;
  [key: string]: unknown;
}

export interface DataFreshness {
  status: WorkbenchFreshnessStatus;
  as_of?: string | null;
  source?: string;
  quality_score?: number;
  fallback_reason?: string | null;
}

export interface ServiceContractFields {
  model_metadata?: ModelMetadata;
  data_freshness?: DataFreshness;
  fallback_reason?: string | null;
}

export interface WorkbenchPageMeta {
  module: string;
  route: string;
  title: string;
}

export interface WorkbenchContext {
  tenant_id?: string;
  owner_user_id?: string;
  account_id?: string;
  data_scope?: WorkbenchDataDomain;
  trade_mode?: 'paper' | 'live' | string;
  role_view?: string;
}

export interface WorkbenchFreshness extends DataFreshness {}

export interface WorkbenchLineage {
  decision_context_id?: string | null;
  candidate_id?: string | null;
  plan_id?: string | null;
  order_id?: string | null;
  risk_verdict_id?: string | null;
  model_version?: string | null;
}

export interface WorkbenchSection {
  key: string;
  title: string;
  state: 'ready' | 'empty' | 'fallback' | 'loading' | 'error';
  metrics?: Record<string, string | number | boolean | null>;
  items?: Array<Record<string, unknown>>;
  fallback_reason?: string;
}

export interface WorkbenchAction {
  key: string;
  label: string;
  enabled: boolean;
  target?: string;
  reason?: string;
}

export interface WorkbenchPageEnvelope<TSection extends WorkbenchSection = WorkbenchSection> {
  status: 'ok' | 'error';
  page: WorkbenchPageMeta;
  context: WorkbenchContext;
  data_domain: WorkbenchDataDomain;
  freshness: WorkbenchFreshness;
  lineage: WorkbenchLineage;
  sections: TSection[];
  actions: WorkbenchAction[];
  message?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Screener（智能选股）
// ═══════════════════════════════════════════════════════════════════════════

/** 选股策略模式 */
export interface ScreenerMode {
  id: string;
  name: string;
  cycle: string;
  style: string;
}

/** 硬科技赛道标签 */
export interface HardTechLabel {
  track: string;
  tier: 'core' | 'strategic' | 'supply';
}

/** 评分因子分解 */
export interface FactorBreakdown {
  technical?: number;
  fundamental?: number;
  money_flow?: number;
  sentiment?: number;
  startup_quality?: number;
  ignition_power?: number;
  hard_tech_conviction?: number;
}

/** 风险/强势标签 */
export interface Flags {
  risk_flags?: string[];
  power_flags?: string[];
}

/** 单只候选股（后端已通过 _normalize_picks() 统一字段名） */
export interface ScreenerPick extends StockBase, NumericValue {
  candidate_id?: string;
  source_module?: string;
  source_mode?: string;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'public' | 'tenant' | 'user' | 'account';
  industry?: string;
  grade?: string; // S / A / B / C
  resonance_score?: number;
  is_at_limit?: boolean;
  entry_price?: number;
  stop_loss?: number;
  target_price?: number;
  entry_reason?: string;
  factor_breakdown?: FactorBreakdown;
  hard_tech?: HardTechLabel;
  risk_flags?: string[];
  power_flags?: string[];
  volume_ratio?: number;
  turnover_rate?: number;
  market_cap?: number;
  pe_ratio?: number;
}

/** 行业共振 */
export interface SectorResonance {
  sector: string;
  resonance_count: number;
  avg_score: number;
  top_picks?: ScreenerPick[];
}

/** 选股运行响应 */
export interface ScreenerRunResponse extends ServiceContractFields {
  trade_date?: string | null;
  picks: ScreenerPick[];
  observation_picks?: ScreenerPick[];
  total_picks?: number;
  total_observation_picks?: number;
  total_scored: number;
  total_excluded: number;
  elapsed: number;
  sector_resonance?: SectorResonance[];
  market_env?: string;
  timestamp?: string;
  no_result_reason?: string | null;
  process_summary?: Record<string, number>;
  screening_trace?: Array<{
    step: string;
    status: string;
    detail: string;
  }>;
  rejection_summary?: Array<{
    reason: string;
    count: number;
  }>;
}

/** 选股模式列表响应 */
export interface ScreenerModesResponse {
  modes: ScreenerMode[];
  total: number;
  latest_trade_date?: string | null;
  latest_dates?: Record<string, string | null | undefined>;
  data_freshness?: DataFreshness;
}

export interface MarketIndexQuote {
  code: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  change_amount?: number | null;
  amount?: number | null;
}

export interface MarketIndexQuotesResponse {
  source?: string;
  as_of?: string | null;
  fallback_reason?: string | null;
  data?: {
    diff?: Array<{
      f2?: number | string;
      f3?: number | string;
      f4?: number | string;
      f6?: number | string;
      f12?: string;
      f14?: string;
    }>;
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// Prediction（K线预测）
// ═══════════════════════════════════════════════════════════════════════════

/** 预测状态 */
export interface PredictionStatus extends ServiceContractFields {
  status: 'online' | 'offline' | 'loading';
  model_path?: string;
  checkpoint_status?: 'base_public' | 'finetuned' | 'not_loaded' | 'unknown';
  last_prediction_time?: string;
}

/** 单日预测点 */
export interface PredictionPoint {
  date: string;
  predicted_close: number;
  predicted_high?: number;
  predicted_low?: number;
  confidence?: number;
  trend?: 'up' | 'down' | 'neutral';
}

/** K线预测响应 */
export interface PredictionResponse extends ServiceContractFields {
  status: 'ok' | 'error' | 'no_data';
  code: string;
  predictions: PredictionPoint[];
  historical_data?: {
    dates: string[];
    closes: number[];
  };
  model_version?: string;
  pred_days?: number;
  elapsed?: number;
  reason?: string;
  pred_return_pct?: number; // 预测涨跌幅（百分比）
  confidence?: number; // 预测置信度
}

/** 快速预测响应 */
export interface FastPredictionResponse extends PredictionResponse {
  mode: 'fast';
  confidence_threshold?: number;
}

/** 批量预测响应 */
export interface BatchPredictionResponse extends ServiceContractFields {
  status: 'ok' | 'error';
  predictions: Record<string, PredictionResponse>;
  total_codes: number;
  elapsed: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Signal（交易信号）
// ═══════════════════════════════════════════════════════════════════════════

/** 信号等级 */
export type SignalLevel = 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell';

/** 单只股票信号 */
export interface StockSignal extends StockBase {
  level: SignalLevel;
  confidence?: number;
  score?: number;
  dimensions?: {
    technical?: number;
    fundamental?: number;
    money_flow?: number;
    sentiment?: number;
  };
  last_update?: string;
  expire_time?: string;
}

/** 信号实时响应 */
export interface SignalLiveResponse extends ServiceContractFields {
  session: 'intra' | 'daily';
  signals: StockSignal[];
  summary?: {
    strong_buy_count: number;
    buy_count: number;
    hold_count: number;
    sell_count: number;
    strong_sell_count: number;
    avg_confidence: number;
  };
  refreshed_at?: string;
}

/** 信号历史响应 */
export interface SignalHistoryResponse extends ServiceContractFields {
  signals: StockSignal[];
  total: number;
  date_range?: {
    start: string;
    end: string;
  };
}

/** 信号分析响应（单股深度） */
export interface SignalAnalyzeResponse extends StockSignal, ServiceContractFields {
  detail_factors?: Record<string, number>;
  recommendation?: string;
  risk_alerts?: string[];
}

/** Dashboard 汇总响应 */
export interface DashboardSummaryResponse extends ServiceContractFields {
  market_sentiment?: {
    score: number;
    label: string;
    trade_date: string;
    avg_change_pct: number;
    up_stocks: number;
    down_stocks: number;
    total_stocks: number;
    formula?: string;
  };
  limit_stocks?: ScreenerPick[];
  signal_stocks?: StockSignal[];
  service_health?: ServiceHealth[];
  screenings?: {
    total_models: number;
    recent_runs: number;
    avg_candidates: number;
  };
  watchlist?: {
    total: number;
    top_gainers: ScreenerPick[];
    top_losers: ScreenerPick[];
  };
  refreshed_at?: string;
}

/** 数据状态响应 */
export interface DataStatusResponse {
  status: 'ok' | 'error' | 'unavailable';
  fallback_reason?: string;
  refreshed_at?: string;
  total_tables: number;
  active_tables: number;
  total_rows: number;
  categories?: string[];
  sources: Array<{
    key: string;
    name: string;
    category: string;
    source: string;
    update: string;
    note: string;
    rows: number;
    min_date: string;
    max_date: string;
    status: 'active' | 'empty' | 'error';
  }>;
  sync_map: Record<string, {
    mode: string;
    days_default: number;
    desc: string;
  }>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Strategy（方案管理）
// ═══════════════════════════════════════════════════════════════════════════

/** 方案模板 */
export interface StrategyTemplate {
  id: string;
  name: string;
  description?: string;
  risk_level?: string;
  max_positions?: number;
  stop_loss_pct?: number;
  target_return_pct?: number;
  holding_days?: number;
}

/** 方案计划 */
export interface StrategyPlan {
  id: string;
  name: string;
  model_name?: string;
  max_positions: number;
  capital: number;
  status?: 'draft' | 'active' | 'paused' | 'closed';
  created_at?: string;
  updated_at?: string;
  picks?: ScreenerPick[];
  expected_return?: number;
  risk_score?: number;
}

/** 方案生成响应 */
export interface StrategyGenerateResponse {
  plan: StrategyPlan;
  recommendation?: string;
  risk_alerts?: string[];
}

/** 方案列表响应 */
export interface StrategyPlansResponse {
  plans: StrategyPlan[];
  total: number;
}

/** 方案模板列表响应 */
export interface StrategyTemplatesResponse {
  templates: StrategyTemplate[];
}

// ═══════════════════════════════════════════════════════════════════════════
// Trade（交易）
// ═══════════════════════════════════════════════════════════════════════════

/** 交易方向 */
export type TradeDirection = 'buy' | 'sell' | 'BUY' | 'SELL';

/** 交易订单 */
export interface TradeOrder {
  id: string | number;
  order_id?: string;
  code: string;
  name?: string;
  direction: TradeDirection;
  price: number;
  volume: number;
  amount?: number;
  status: 'pending' | 'filled' | 'partial' | 'cancelled' | 'rejected';
  filled_at?: string;
  created_at?: string;
  commission?: number;
  filled_price?: number;
  filled_volume?: number;
  tenant_id?: string;
  owner_user_id?: string;
  account_id?: string;
  trade_mode?: 'paper' | 'live' | string;
  decision_context_id?: string | null;
  candidate_id?: string | null;
  plan_id?: string | null;
  order_scope?: Record<string, unknown>;
  risk_verdict?: RiskVerdict | Record<string, unknown>;
}

/** 交易账户 */
export interface TradeAccount {
  total_capital: number;
  total_assets: number;
  market_value: number;
  available: number;
  frozen?: number;
  total_pnl: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  margin_used?: number;
  risk_level?: 'low' | 'medium' | 'high';
}

/** 持仓 */
export interface Position extends StockBase {
  volume: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  pnl: number;
  pnl_pct: number;
  today_pnl?: number;
  today_pnl_pct?: number;
  holding_days?: number;
  stop_loss?: number;
  target_price?: number;
}

/** 下单请求 */
export interface PlaceOrderRequest {
  code: string;
  direction: TradeDirection;
  volume: number;
  price?: number;
  trade_mode?: 'paper' | 'live';
  decision_context_id?: string;
  candidate_id?: string;
  plan_id?: string;
}

export interface BrokerConnectRequest {
  broker_name: 'mock_qmt' | 'xtquant';
  account_id: string;
  server_ip: string;
  server_port: number;
  environment: 'sandbox' | 'live';
  trade_password?: string;
}

/** 下单响应 */
export interface RiskCheckItem {
  rule: string;
  level: 'pass' | 'warn' | 'reject' | string;
  message?: string;
  detail?: Record<string, unknown>;
}

export interface RiskCheckPayload {
  passed: boolean;
  requires_confirmation?: boolean;
  confirm_reason?: string;
  checks: RiskCheckItem[];
}

export interface RiskVerdict {
  verdict_id: string;
  tenant_id: string;
  owner_user_id: string;
  account_id: string;
  visibility: 'private' | 'tenant_shared' | 'public';
  data_scope: 'public' | 'tenant' | 'user' | 'account';
  scope: 'candidate' | 'plan' | 'order' | 'strategy' | 'account' | string;
  result: 'pass' | 'warn' | 'reject' | 'manual_review' | string;
  symbol: string;
  trade_mode: 'paper' | 'live' | string;
  decision_context_id?: string;
  candidate_id?: string;
  plan_id?: string;
  order_id?: string | null;
  risk_check: RiskCheckPayload;
}

export interface RiskVerdictRecord {
  id: string | number;
  verdict_id: string;
  tenant_id: string;
  owner_user_id?: string | null;
  account_id?: string | null;
  result: RiskVerdict['result'];
  scope: RiskVerdict['scope'];
  trade_mode: RiskVerdict['trade_mode'];
  symbol?: string | null;
  order_id?: string | null;
  plan_id?: string | null;
  candidate_id?: string | null;
  decision_context_id?: string | null;
  details: RiskVerdict | Record<string, unknown>;
  created_at?: string | null;
}

export interface RiskVerdictQuery {
  result?: 'pass' | 'warn' | 'reject' | 'manual_review';
  trade_mode?: 'paper' | 'live';
  code?: string;
  decision_context_id?: string;
  order_id?: string;
  plan_id?: string;
  candidate_id?: string;
  page?: number;
  page_size?: number;
}

export interface RiskVerdictsResponse {
  total: number;
  page: number;
  page_size: number;
  records: RiskVerdictRecord[];
}

export interface DecisionContextRecord {
  id: string | number;
  decision_context_id: string;
  tenant_id: string;
  owner_user_id?: string | null;
  account_id?: string | null;
  source_type: 'candidate' | 'plan' | 'order' | 'strategy' | 'manual' | string;
  symbol?: string | null;
  plan_id?: string | null;
  candidate_id?: string | null;
  intent: string;
  payload: Record<string, unknown>;
  created_at?: string | null;
}

export interface DecisionContextQuery {
  decision_context_id?: string;
  code?: string;
  plan_id?: string;
  candidate_id?: string;
  page?: number;
  page_size?: number;
}

export interface DecisionContextsResponse {
  total: number;
  page: number;
  page_size: number;
  records: DecisionContextRecord[];
}

// ═══════════════════════════════════════════════════════════════════════════
// P0 公共对象契约
// ═══════════════════════════════════════════════════════════════════════════

/** 所有用户可产生对象的归属边界。公共行情可为 public，账户对象必须至少 account scope。 */
export interface PlatformObjectScope {
  tenant_id?: string;
  owner_user_id?: string | number | null;
  account_id?: string | null;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'public' | 'tenant' | 'user' | 'account';
}

/** P0 主链路对象之间的可追溯字段。 */
export interface PlatformLineage {
  decision_context_id?: string | null;
  candidate_id?: string | null;
  plan_id?: string | null;
  order_id?: string | null;
  risk_verdict_id?: string | null;
}

/** 决策上下文：记录一次模型/用户/系统动作的输入、意图和证据。 */
export type DecisionContext = DecisionContextRecord & PlatformObjectScope & PlatformLineage;

/** 候选标的：由选股、信号、产业链或人工加入，进入方案前必须可追踪来源。 */
export type Candidate = ScreenerPick & PlatformObjectScope & PlatformLineage;

/** 投资方案：用户/账户私有或租户共享的组合计划。 */
export type Plan = StrategyPlan & PlatformObjectScope & PlatformLineage;

/** 交易订单：仅账户域对象，实盘订单必须关联风控判定。 */
export type Order = TradeOrder & PlatformObjectScope & PlatformLineage;

/** 风控判定：候选、方案、订单、账户动作的放行/拦截结论。 */
export type RiskVerdictObject = RiskVerdictRecord & PlatformObjectScope & PlatformLineage;

export interface PlaceOrderResponse {
  order?: TradeOrder;
  order_id?: string;
  broker_order_id?: string | null;
  code?: string;
  direction?: TradeDirection | string;
  price?: number;
  volume?: number;
  status?: string;
  message?: string;
  tenant_id?: string;
  owner_user_id?: string;
  account_id?: string;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'public' | 'tenant' | 'user' | 'account';
  decision_context_id?: string;
  candidate_id?: string;
  plan_id?: string;
  order_scope?: {
    tenant_id: string;
    owner_user_id: string;
    account_id: string;
    visibility: string;
    data_scope: string;
  };
  risk_verdict?: RiskVerdict;
  risk_check?: RiskCheckPayload;
}

/** 订单列表响应 */
export interface OrdersResponse {
  orders: TradeOrder[];
  total: number;
  page?: number;
  page_size?: number;
}

/** 持仓列表响应 */
export interface PositionsResponse {
  positions: Position[];
  total_market_value: number;
  total_pnl: number;
}

/** 账户响应 */
export interface AccountResponse {
  account: TradeAccount;
  positions?: Position[];
}

// ═══════════════════════════════════════════════════════════════════════════
// Backtest（回测）
// ═══════════════════════════════════════════════════════════════════════════

/** 回测结果 */
export interface BacktestResult {
  strategy_id: string;
  strategy_name?: string;
  total_return: number;
  annual_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  avg_holding_days: number;
  total_trades: number;
  win_trades: number;
  loss_trades: number;
  start_date: string;
  end_date: string;
  equity_curve?: {
    dates: string[];
    values: number[];
  };
  trades?: {
    entries: string[];
    exits: string[];
    returns: number[];
  };
}

/** 回测运行响应 */
export interface BacktestRunResponse {
  results: BacktestResult[];
  windows: number;
  elapsed: number;
  best_strategy?: string;
  recommendation?: string;
}

/** 回测对比响应 */
export interface BacktestCompareResponse {
  comparison: BacktestResult[];
  winner?: string;
  summary?: string;
}

/** 因子列表响应 */
export interface FactorsResponse {
  factors: Array<{
    name: string;
    category: string;
    description?: string;
  }>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Diagnosis（诊断）
// ═══════════════════════════════════════════════════════════════════════════

/** 五维评分 */
export interface FiveDimensionScores {
  technical?: number;
  fundamental?: number;
  money_flow?: number;
  sentiment?: number;
  ai_prediction?: number;
}

/** 诊断报告（扩展版，匹配 Diagnosis.tsx 期望） */
export interface DiagnosisReport extends StockBase {
  overall_score: number;
  grade: string;
  recommendation?: string;
  recommendation_reason?: string;
  dimensions: Record<string, {
    name: string;
    score: number;
    weight: number;
    grade: string;
    status: string;
    details?: Record<string, unknown>;
    signals?: string[];
  }>;
  key_levels?: Record<string, number>;
  risk_warnings?: string[];
  kronos_available?: boolean;
  degraded?: boolean;
  degraded_dimensions?: string[];
  created_at?: string;
  support_levels?: number[];
  resistance_levels?: number[];
  trend?: 'up' | 'down' | 'sideways';
  alerts?: string[];
  last_update?: string;
  data_source?: string;
}

/** 诊断对比响应 */
export interface DiagnosisCompareResponse {
  stocks: DiagnosisReport[];
  comparison_table?: Record<string, Record<string, number>>;
  winner?: string;
  summary?: string;
}

/** 诊断历史项 */
export interface DiagnosisHistoryItem {
  id: string | number;
  code: string;
  name?: string;
  overall_score: number;
  grade: string;
  created_at: string;
}

/** 诊断历史响应 */
export interface DiagnosisHistoryResponse extends PaginatedResponse<DiagnosisHistoryItem> {}

// ═══════════════════════════════════════════════════════════════════════════
// Health（服务健康）
// ═══════════════════════════════════════════════════════════════════════════

/** 服务健康状态 */
export interface ServiceHealth {
  service: string;
  port: number;
  status: 'online' | 'offline' | 'degraded';
  latency?: number;
  last_check?: string;
  error?: string;
  description?: string;
}

/** 健康检查响应 */
export interface HealthCheckResponse {
  status: 'online' | 'offline' | 'degraded';
  service?: string;
  version?: string;
  uptime?: number;
  checks?: Record<string, boolean>;
}

// ═══════════════════════════════════════════════════════════════════════════
// Alert（预警）
// ═══════════════════════════════════════════════════════════════════════════

/** 预警渠道 */
export interface AlertChannel {
  id: string;
  type: 'email' | 'sms' | 'push' | 'webhook';
  enabled: boolean;
  config?: Record<string, unknown>;
}

/** 预警配置 */
export interface AlertConfig {
  channels: AlertChannel[];
  rules?: Array<{
    type: string;
    threshold?: number;
    enabled: boolean;
  }>;
}

/** 预警渠道列表响应 */
export interface AlertChannelsResponse {
  channels: AlertChannel[];
}

/** 未读预警数响应 */
export interface UnreadAlertCountResponse {
  unread: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Supply Chain（产业链）
// ═══════════════════════════════════════════════════════════════════════════

/** 产业链主题 */
export interface SupplyChainTheme {
  id: string;
  name: string;
  description?: string;
  policy_intensity?: number;
  industry_cycle?: string;
}

/** 产业链节点 */
export interface SupplyChainNode {
  node_id: string;
  name: string;
  layer: number;
  parent_id?: string;
  children?: SupplyChainNode[];
  upstream_nodes?: string[];
  downstream_nodes?: string[];
  value_chain?: {
    margin: number;
    pricing_power: number;
    value_added: number;
  };
}

/** 类型别名（页面兼容） */
export type ChainNode = SupplyChainNode;

/** Filter types for chain candidates */
export type ChainCandidateFilter = 'high_growth' | 'high_profit' | 'high_moat' | 'chokepoint_core' | 'all';

/** Resonance levels for V6 three-factor scoring */
export type ResonanceLevel = '强启动' | '启动' | '关注' | '观察';

/** Three-factor scores for a candidate */
export interface ThreeFactorScores {
  industry_cycle?: { stage: string; score: number };
  policy_intensity?: { stars: number; score: number };
  performance_proof?: { status: string; score: number };
}

/** Summary counts per filter type */
export type FilterSummary = Record<ChainCandidateFilter, number>;

/** Summary counts per resonance level */
export type ResonanceSummary = Record<ResonanceLevel, number>;

/** 产业链BOM响应 */
export interface SupplyChainBomResponse {
  themes: SupplyChainTheme[];
  nodes: SupplyChainNode[];
}

/** 产业链候选股 */
export interface ChainCandidate extends ScreenerPick {
  mapping_id?: string;
  chokepoint_score?: number;
  resonance_factors?: number;
  resonance_level?: '强启动' | '启动' | '关注' | '观察';
  commercialization_note?: string;
  policy_match_score?: number;
  evidence?: string[];
  three_factor_scores?: ThreeFactorScores;
  trade_signal?: string;
  last_price?: number;
  last_change_pct?: number;
  last_trade_date?: string;
  gross_margin?: number;
  performance_yield?: number;
  main_pct?: number;
}

/** 产业链候选股响应 */
export interface ChainCandidatesResponse {
  filter: string;
  resonance_level?: string;
  total_count: number;
  candidates: ChainCandidate[];
  filter_summary: Record<string, number>;
  resonance_summary: Record<string, number>;
  elapsed_ms: number;
}

/** 映射审查状态 */
export type MappingReviewStatus = 'reviewable' | 'pending_review' | 'weak_evidence' | 'verified' | 'rejected';

/** 映射审查项 */
export interface MappingReviewItem extends StockBase {
  node_id: string;
  node_name?: string;
  chain_id?: string;
  product_name?: string;
  material_name?: string;
  confidence?: number;
  status: MappingReviewStatus;
  mapping_source?: string;
  evidence?: string[];
  evidence_gaps?: string[];
  updated_at?: string;
  review_priority?: number;
}

/** 映射审查队列响应 */
export interface MappingReviewQueueResponse extends PaginatedResponse<MappingReviewItem> {}

/** 映射质量响应 */
export interface MappingQualityResponse {
  mapping_count: number;
  review_queue_count: number;
  status_counts: Record<MappingReviewStatus, number>;
  source_counts: Record<string, number>;
  hotspot_nodes: Array<{
    node_id: string;
    node_name?: string;
    verified?: number;
    pending_review?: number;
    weak_evidence?: number;
    rejected?: number;
    review_pressure?: number;
  }>;
}

/** 映射审查决策 */
export interface MappingReviewDecision {
  decision: 'verified' | 'rejected' | 'needs_more_evidence' | 'pending_review';
  reviewer?: string;
  note?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Training（模型训练）
// ═══════════════════════════════════════════════════════════════════════════

/** 训练任务 */
export interface TrainingTask extends ServiceContractFields {
  id: string;
  model_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  start_time?: string;
  end_time?: string;
  metrics?: Record<string, number>;
  log_path?: string;
}

/** 训练任务列表响应 */
export interface TrainingTasksResponse extends ServiceContractFields {
  tasks: TrainingTask[];
  total: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Model Registry（模型注册）
// ═══════════════════════════════════════════════════════════════════════════

/** 注册模型 */
export interface RegisteredModel extends ServiceContractFields {
  id: string;
  name: string;
  version: string;
  status: 'staging' | 'production' | 'archived';
  metrics?: Record<string, number>;
  registered_at?: string;
  path?: string;
}

/** 模型列表响应 */
export interface ModelsResponse extends ServiceContractFields {
  models: RegisteredModel[];
  total: number;
}

// ═══════════════════════════════════════════════════════════════════════════
// Data Update（数据更新）
// ═══════════════════════════════════════════════════════════════════════════

/** 同步任务状态 */
export interface SyncTaskStatus {
  table_key: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  last_sync?: string;
  next_sync?: string;
  rows_synced?: number;
  error?: string;
}

/** 同步调度 */
export interface SyncSchedule {
  table_key: string;
  days_back: number;
  interval_minutes: number;
  daily_at: string | null;
  enabled: boolean;
  last_sync_at?: string;
  next_sync_at?: string;
  created_at?: string;
  updated_at?: string;
}

/** 同步调度列表响应 */
export interface SyncSchedulesResponse {
  status: 'ok' | 'error';
  message?: string;
  schedules: SyncSchedule[];
}

/** 触发同步响应 */
export interface TriggerSyncResponse {
  status: 'ok' | 'error';
  table_key: string;
  mode?: string;
  desc?: string;
  days?: number;
  returncode?: number;
  output?: string[];
  stderr?: string;
  message?: string;
}

// ═══════════════════════════════════════════════════════════════════════════
// Candidate Pool（候选池 · account-scoped 私有对象，契约 §公共对象字段契约）
// scope(tenant/owner/account) 由前端拦截器注入请求头，前端类型/请求体均不含明文 scope。
// ═══════════════════════════════════════════════════════════════════════════

/** 候选池候选股条目 */
export interface CandidatePoolCandidate {
  code: string;
  name?: string;
  score?: number;
  grade?: string;
  rank?: number;
  [key: string]: unknown;
}

/** 候选池记录（持久化形态，含 scope 归属——查询响应里带回） */
export interface CandidatePoolRecord {
  pool_id: string;
  source_module: string; // screener / supply-chain / open-decision
  source_mode: string; // leader_scalp / cb_auction_t0 / ...
  name: string;
  candidates: CandidatePoolCandidate[];
  metadata?: Record<string, unknown> | null;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'public' | 'tenant' | 'user' | 'account';
  created_at?: string;
  updated_at?: string;
}

/** POST /screener/candidate-pool 入参 */
export interface CandidatePoolRecordRequest {
  source_module: string;
  source_mode: string;
  name: string;
  candidates: CandidatePoolCandidate[];
  // 后端 body 字段名为 candidate_pool_metadata（与 OpenAPI 一致；勿简写为 metadata）
  candidate_pool_metadata?: Record<string, unknown>;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'public' | 'tenant' | 'user' | 'account';
  /** pool_id 生成辅助（后端拼 POOL-{mode}-{trade_date}-{time_slot}-{scope}） */
  trade_date?: string;
  time_slot?: string;
}

export interface CandidatePoolRecordResponse extends ServiceContractFields {
  pool_id: string;
  id?: number;
  created_at?: string;
}

export interface CandidatePoolQueryParams {
  source_module?: string;
  source_mode?: string;
  page?: number;
  page_size?: number;
}

export interface CandidatePoolQueryResponse extends ServiceContractFields {
  total: number;
  page: number;
  page_size: number;
  records: CandidatePoolRecord[];
  /** 无数据时的空态（契约：缺数据返同 shape + reason，前端不空白） */
  empty_state?: { reason: string };
}

// ═══════════════════════════════════════════════════════════════════════════
// Watchlist（自选股，Batch B #11）—— scope 走 Header，前端不传明文（契约§9.3）
// ═══════════════════════════════════════════════════════════════════════════
export interface WatchlistAddRequest {
  code: string;
  name?: string;
  notes?: string;
  sort_order?: number;
  watchlist_metadata?: Record<string, unknown>;
  visibility?: 'private' | 'tenant_shared' | 'public';
  data_scope?: 'account' | 'tenant' | 'user' | 'public';
}

export interface WatchlistItem {
  id: number;
  tenant_id: string;
  owner_user_id?: string | null;
  account_id?: string | null;
  visibility: string;
  data_scope: string;
  code: string;
  name?: string | null;
  notes?: string | null;
  sort_order: number;
  added_at?: string | null;
  updated_at?: string | null;
  metadata?: Record<string, unknown>;
}

export interface WatchlistAddResponse extends ServiceContractFields {
  record: WatchlistItem | null;
}

export interface WatchlistQueryParams {
  code?: string;
  page?: number;
  page_size?: number;
}

export interface WatchlistQueryResponse extends ServiceContractFields {
  total: number;
  page: number;
  page_size: number;
  records: WatchlistItem[];
  /** 无数据时的空态 */
  empty_state?: { reason: string };
}

export interface WatchlistDeleteResponse extends ServiceContractFields {
  deleted: number;
  code?: string | null;
  id?: number | null;
}
