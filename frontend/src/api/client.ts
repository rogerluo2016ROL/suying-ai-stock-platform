// api/client.ts — 统一 API 入口
// C 域拆分后:各域 API 对象 + 类型已拆至 ./domains/* 与 ./http,本文件仅做聚合 re-export。
// 保持向后兼容:现有 `from 'client'` 的导入不破。

import { api } from './http'
export { injectAuth, clearAuth, injectPlatformContext, clearPlatformContext } from './http'

// ── 域类型 re-export ──
export type { StrategyPick } from './domains/strategy/types'
export type { TradeOrder, TradeAccount } from './domains/trade/types'
export type {
  MembershipInfo,
  AdminUser,
  AdminUsersResponse,
  PermissionItem,
  RolePermissions,
  RolePermissionsListResponse,
  MembershipUser,
  MembershipsResponse,
  UserAuthorizationPayload,
} from './domains/admin/types'
export type {
  TrainingModelRecord,
  TrainingModelsResponse,
  TrainingHistoryRecord,
  TrainingHistoryResponse,
  TrainingScheduleResponse,
  TrainingModelActionResponse,
} from './domains/training/types'

// ── Supply Chain 域(类型 + build 辅助,C 域拆分)──
export type {
  SupplyChainWorkbenchParams,
  SupplyChainCandidateRankingParams,
  SupplyChainCandidateRankingItem,
  SupplyChainCandidateRankingResponse,
  SupplyChainCapexEvidenceReviewQueueParams,
  SupplyChainMappingReviewStatus,
  SupplyChainMappingReviewQueueParams,
  SupplyChainMappingReviewItem,
  SupplyChainMappingQuality,
  SupplyChainMappingReviewDecision,
  EvidenceChainDocument,
  EvidenceChainFact,
  EvidenceChainFreshness,
  EvidenceChainStageTransition,
  EvidenceChainExpectation,
  EvidenceChainResponse,
  EvidenceReviewQueueResponse,
  CapexEvidenceReviewItem,
  CapexEvidenceReviewQueueResponse,
  CapexEvidenceReviewRequest,
} from './domains/supply-chain/types'
export {
  buildSupplyChainWorkbenchPath,
  buildSupplyChainMappingReviewQueuePath,
  buildSupplyChainCandidateRankingPath,
  buildSupplyChainCapexEvidenceReviewQueuePath,
} from './domains/supply-chain/build'

// ── Chain 域类型(C 域拆分)──
export type {
  PolicyInterpretRequest,
  PolicyInterpretResponse,
  ValueChainLabel,
  CompetitionLabel,
  ChainDeconstructTree,
  ChainDeconstructTemplate,
  ChainDeconstructResponse,
  ChainNodeCompaniesResponse,
} from './domains/chain/types'

// ═══════════════════════════════════════════════════════════════════════════
// 各域 API 对象
// ═══════════════════════════════════════════════════════════════════════════

export { screenerApi } from './domains/screener/api'
export { predictionApi } from './domains/prediction/api'
export { strategyApi } from './domains/strategy/api'
export { trainingApi } from './domains/training/api'
export { signalApi } from './domains/signal/api'
export { marketApi } from './domains/market/api'
export { workbenchApi } from './domains/workbench/api'
export { alertApi } from './domains/alert/api'
export { adminApi } from './domains/admin/api'
export { tradeApi } from './domains/trade/api'
export { backtestApi } from './domains/backtest/api'
export { diagnosisApi } from './domains/diagnosis/api'
export { healthApi, HealthCheckError } from './domains/health/api'
export { chainApi } from './domains/chain/api'

// ═══════════════════════════════════════════════════════════════════════════
// 共享类型 re-export(供 `from 'client'` 使用)
// ═══════════════════════════════════════════════════════════════════════════

export type {
  ScreenerModesResponse,
  ScreenerRunResponse,
  ScreenerPick,
  PredictionResponse,
  DiagnosisReport,
  DiagnosisCompareResponse,
  DashboardSummaryResponse,
  SignalLiveResponse,
  BacktestRunResponse,
  BacktestCompareResponse,
  AccountResponse,
  PositionsResponse,
  OrdersResponse,
  RiskVerdictsResponse,
  DecisionContextsResponse,
  WorkbenchPageEnvelope,
  WorkbenchSection,
  WorkbenchAction,
  PlaceOrderResponse,
  HealthCheckResponse,
  ServiceHealth,
  StrategyPlan,
  ChainCandidate,
  ChainCandidatesResponse,
  // Supply Chain aliases
  ChainNode,
  SupplyChainNode,
  SupplyChainTheme,
  ChainCandidateFilter,
  ResonanceLevel,
  ThreeFactorScores,
  FilterSummary,
  ResonanceSummary,
} from './types'

export default api
