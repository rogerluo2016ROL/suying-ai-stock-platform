# Prototype Page Rollout Matrix

## 2026-06-28 Re-Audit Decision

Current implementation is not accepted as full prototype rollout.

The main gap is `frontend/src/pages/NewUiModulePage.tsx`: it creates a generic page body for many modules, while the optimized previews require page-specific layouts, interactions, and data contracts. For the production rebuild, `NewUiModulePage` can remain only as a temporary fallback during migration and must not be counted as a completed target page.

Formal completion requires:

- each preview page has a dedicated React page section or sub-route implementation;
- top tabs match the module-level tabs in the preview, not cross-module workflow links;
- page body does not repeat platform explainer strips already shown in shell/header;
- no page renders blank white space when API data is missing;
- every interactive control in the preview has a React interaction, mock/fallback state, and final API contract;
- all private objects carry tenant/user/account scope.

This file is the working contract for landing the optimized prototype previews into the production React app.

- Preview source folder: `docs/design/New design/01 PRD 文档/`
- Preview pages counted on 2026-06-28: 63
- PRD/detail design documents counted at the same folder level: 140
- Current React shell: `frontend/src/App.tsx`
- Current partial UI migration: shared shell and some prototype components exist, but many pages are generic placeholders.
- Target rule: every preview page must have either a first-class React route or a first-class sub-tab route; repeated body-level progress/status strips are not copied into app pages.

## Implementation Status Vocabulary

| Status | Meaning |
|---|---|
| Planned | Route exists in matrix but page has not been rebuilt from the optimized preview. |
| Shell-only | Route uses new shell but body is still old UI or generic placeholder. |
| Prototype-reactified | Page body matches preview structure and interactions with mock/fallback data. |
| API-wired | Page consumes the target BFF/service contract. |
| Verified | Route, UI interaction, data contract, and tests passed. |

Current baseline after audit: most pages are `Planned` or `Shell-only`; no generic `NewUiModulePage` route should be upgraded beyond `Shell-only` until the page body is rebuilt.

## Phase Acceptance

| Phase | Acceptance |
|---|---|
| Phase 0 | This matrix covers all 63 preview pages and names a target route/component for each. |
| Phase 1 | Shared shell/components match optimized previews and tests assert redundant platform strips are absent. |
| Phase 2 | All target routes render without auth/routing errors. |
| Phase 3 | 行情决策 pages match previews and retain tabs/filters/tables/charts. |
| Phase 4 | 交易执行 pages support P0 chain: 候选池 -> 方案管理 -> 下单面板 -> 风控闸门 -> 回测复盘. |
| Phase 5 | 模型/系统 pages render and keep admin/system interactions usable. |
| Phase 6 | API contracts and tenant/account/public data boundaries are enforced by tests. |
| Phase 7 | Model-backed pages consume service payloads with lineage and fallback state. |
| Phase 8 | Paper trading works end-to-end; QMT/live path is explicitly gated. |
| Phase 9 | Frontend, backend, service, API smoke, and browser UAT checks pass or document a real external blocker. |

## Public vs Private Data Boundary

| Data class | Scope | Examples | UI rule |
|---|---|---|---|
| Public market data | Shared | 行情、指数、板块、因子、模型注册、训练指标摘要 | Can be cached and visible across accounts by permission. |
| Tenant private data | `tenant_id` | 策略、组合、方案模板、风控策略 | Never show another tenant's private objects. |
| Account private data | `tenant_id + user_id/account_id` | 自选、订单、持仓、成交、风控结论、决策上下文 | Every action must preserve account scope. |

## Page Matrix

| Preview | Product module | Target route | Target component | Data/API owner | Status |
|---|---|---|---|---|---|
| `0.2 p0-main-flow-preview.html` | P0 主链路 | `/workflow/p0` | `P0Workflow` | gateway + trade/strategy/backtest | Planned |
| `0.3 platform-upgrade-preview.html` | 平台升级 | `/platform/upgrade` | `PlatformUpgrade` | backend auth/platform | Planned |
| `1.1 sentiment-dashboard-preview.html` | 智能看板 / 市场情绪 | `/` | `Dashboard` | signal-service | Planned |
| `1.2 auction-dashboard-preview.html` | 智能看板 / 竞价意图 | `/dashboard/auction` | `Dashboard` tab | signal-service + screener-service | Planned |
| `1.3 signal-overview-preview.html` | 智能看板 / 信号总览 | `/dashboard/signals` | `Dashboard` tab | signal-service | Planned |
| `1.4 watchlist-dashboard-preview.html` | 智能看板 / 自选跟踪 | `/dashboard/watchlist` | `Dashboard` tab | signal-service + account scope | Planned |
| `2.1 decision-overview-preview.html` | 开盘决策 / 决策总览 | `/open-decision` | `OpenDecision` | signal/screener/strategy | Planned |
| `2.2 auction-analysis-preview.html` | 开盘决策 / 竞价分析 | `/open-decision/auction` | `OpenDecision` tab | screener-service | Planned |
| `2.3 signal-scan-preview.html` | 开盘决策 / 信号扫描 | `/open-decision/signals` | `OpenDecision` tab | signal-service | Planned |
| `2.4 candidate-pool-preview.html` | 开盘决策 / 候选池 | `/open-decision/candidates` | `OpenDecision` tab | screener-service | Planned |
| `2.5 execution-monitor-preview.html` | 开盘决策 / 执行监控 | `/open-decision/execution` | `OpenDecision` tab | strategy/trade | Planned |
| `3.1 screener-workbench-preview.html` | 智能选股 / 选股工作台 | `/screener` | `Screener` | screener-service | Planned |
| `3.2 model-compare-preview.html` | 智能选股 / 模型对比 | `/screener/models` | `Screener` tab | screener/prediction | Planned |
| `3.3 factor-analysis-preview.html` | 智能选股 / 因子分析 | `/screener/factors` | `Screener` tab | screener/factor package | Planned |
| `4.1 policy-analysis-preview.html` | 产业链拆解 / 政策梳理 | `/supply-chain-bom/policy` | `SupplyChainBom` tab | LLM/strategy | Planned |
| `4.2 chain-decompose-preview.html` | 产业链拆解 / 产业链解构 | `/supply-chain-bom` | `SupplyChainBom` | LLM/market data | Planned |
| `4.3 company-analysis-preview.html` | 产业链拆解 / 多维度分析 | `/supply-chain-bom/company` | `SupplyChainBom` tab | screener/diagnosis | Planned |
| `5.0 prediction-preview.html` | K线预测 / 预测总览 | `/predictions` | `Predictions` | prediction-service | Planned |
| `5.1 single-stock-preview.html` | K线预测 / 单股预测 | `/predictions/single` | `Predictions` tab | prediction-service | Planned |
| `5.2 multi-compare-preview.html` | K线预测 / 多股对比 | `/predictions/compare` | `Predictions` tab | prediction-service | Planned |
| `5.3 backtest-preview.html` | K线预测 / 准确率回测 | `/predictions/backtest` | `Predictions` tab | prediction/backtest | Planned |
| `6.0 signal-detail-preview.html` | 交易信号 / 信号详情 | `/signals` | `Signals` | signal-service | Planned |
| `6.1 signal-overview-preview.html` | 交易信号 / 信号总览 | `/signals/overview` | `Signals` tab | signal-service | Planned |
| `6.2 signal-history-preview.html` | 交易信号 / 信号历史 | `/signals/history` | `Signals` tab | signal-service | Planned |
| `6.3 risk-scan-preview.html` | 交易信号 / 风险扫描 | `/signals/risk` | `Signals` tab | signal + risk verdict | Planned |
| `7.0 trade-center-preview.html` | 交易中心 / 总览 | `/trade` | `Trade` | trade-service | Planned |
| `7.1 order-panel-preview.html` | 交易中心 / 下单面板 | `/trade/order` | `Trade` tab | trade-service | Planned |
| `7.2 position-monitor-preview.html` | 交易中心 / 持仓监控 | `/trade/positions` | `Trade` tab | trade-service | Planned |
| `7.3 order-management-preview.html` | 交易中心 / 订单管理 | `/trade/orders` | `Trade` tab | trade-service | Planned |
| `7.4 account-overview-preview.html` | 交易中心 / 账户总览 | `/trade/account` | `Trade` tab | trade-service | Planned |
| `7.5 broker-management-preview.html` | 交易中心 / 券商管理 | `/trade/brokers` | `Trade` tab | trade-service | Planned |
| `8.1 strategy-market-preview.html` | 量化交易 / 策略市场 | `/auto-trade` | `AutoTrade` | strategy-service | Planned |
| `8.2 strategy-config-preview.html` | 量化交易 / 策略配置 | `/auto-trade/config` | `AutoTrade` tab | strategy-service | Planned |
| `8.3 strategy-monitor-preview.html` | 量化交易 / 策略监控 | `/auto-trade/monitor` | `AutoTrade` tab | strategy + trade | Planned |
| `8.4 strategy-log-preview.html` | 量化交易 / 策略日志 | `/auto-trade/logs` | `AutoTrade` tab | strategy-service | Planned |
| `9.1 plan-list-preview.html` | 方案管理 / 方案列表 | `/strategy` | `Strategy` | strategy-service | Planned |
| `9.2 plan-detail-preview.html` | 方案管理 / 方案详情 | `/strategy/detail` | `Strategy` tab | strategy-service | Planned |
| `9.3 plan-compare-preview.html` | 方案管理 / 方案对比 | `/strategy/compare` | `Strategy` tab | strategy-service | Planned |
| `9.4 settlement-report-preview.html` | 方案管理 / 复盘报告 | `/strategy/reports` | `Strategy` tab | strategy/backtest | Planned |
| `10.0 risk-control-dashboard-preview.html` | 风控中心 / 总览 | `/risk` | `RiskControl` | trade/risk | Planned |
| `10.1 risk-overview-preview.html` | 风控中心 / 风险总览 | `/risk/overview` | `RiskControl` tab | trade/risk | Planned |
| `10.2 position-risk-preview.html` | 风控中心 / 持仓风险 | `/risk/positions` | `RiskControl` tab | trade-service | Planned |
| `10.3 strategy-risk-preview.html` | 风控中心 / 策略风险 | `/risk/strategies` | `RiskControl` tab | strategy/risk | Planned |
| `10.4 market-risk-preview.html` | 风控中心 / 市场风险 | `/risk/market` | `RiskControl` tab | signal-service | Planned |
| `10.5 event-audit-preview.html` | 风控中心 / 事件审计 | `/risk/audit` | `RiskControl` tab | trade-service | Planned |
| `11.0 backtest-preview.html` | 回测分析 / 总览 | `/backtest` | `Backtest` | backtest-service | Planned |
| `11.1 backtest-run-preview.html` | 回测分析 / 运行回测 | `/backtest/run` | `Backtest` tab | backtest-service | Planned |
| `11.2 backtest-compare-preview.html` | 回测分析 / 回测对比 | `/backtest/compare` | `Backtest` tab | backtest-service | Planned |
| `11.3 backtest-trades-preview.html` | 回测分析 / 交易明细 | `/backtest/trades` | `Backtest` tab | backtest-service | Planned |
| `12.0 diagnosis-preview.html` | 个股诊断 / 入口 | `/diagnosis` | `Diagnosis` | diagnosis-service | Planned |
| `12.1 diagnosis-overview-preview.html` | 个股诊断 / 诊断总览 | `/diagnosis/overview` | `Diagnosis` tab | diagnosis-service | Planned |
| `12.2 model-perspective-preview.html` | 个股诊断 / 模型视角 | `/diagnosis/model` | `Diagnosis` tab | diagnosis/prediction | Planned |
| `12.3 diagnosis-compare-preview.html` | 个股诊断 / 多股对比 | `/diagnosis/compare` | `Diagnosis` tab | diagnosis-service | Planned |
| `12.4 diagnosis-risk-preview.html` | 个股诊断 / 风险扫描 | `/diagnosis/risk` | `Diagnosis` tab | diagnosis/risk | Planned |
| `13.0 model-training-preview.html` | 模型训练 / 总览 | `/training` | `Training` | training-service | Planned |
| `13.1 training-tasks-preview.html` | 模型训练 / 训练任务 | `/training/tasks` | `Training` tab | training-service | Planned |
| `13.2 mlflow-experiment-preview.html` | 模型训练 / MLflow 实验 | `/training/mlflow` | `Training` tab | training-service | Planned |
| `14.0 model-registry-preview.html` | 模型注册 | `/model-registry` | `ModelRegistry` | training/model registry | Planned |
| `15.0 data-update-preview.html` | 数据更新 / 总览 | `/data-update` | `DataUpdate` | data-service | Planned |
| `15.1 data-overview-preview.html` | 数据更新 / 数据概览 | `/data-update/overview` | `DataUpdate` tab | data-service | Planned |
| `15.2 all-tables-preview.html` | 数据更新 / 全表管理 | `/data-update/tables` | `DataUpdate` tab | data-service | Planned |
| `15.3 sync-schedule-preview.html` | 数据更新 / 同步计划 | `/data-update/schedule` | `DataUpdate` tab | data-service | Planned |
| `16.0 runtime-status-preview.html` | 运行状态 | `/runtime-status` | `RuntimeStatus` | gateway/service health | Planned |

## Immediate P0 UI Fix List

These are the visual problems that triggered the current rebuild and must stay fixed during route migration:

| Problem | Required fix |
|---|---|
| Page-body platform explainer strips repeat shell/account context | Remove from all app pages; show compact context in shell/header only. |
| Prototype top workflow cards plus in-body tabs duplicate each other | Keep one page-level tab system; use module tabs for sub-pages. |
| 开盘决策/竞价分析 main area renders as abnormal empty columns | Rebuild with actual auction candidates, sector resonance, locked plate, and candidate preview panels. |
| 产业链解构 only shows upstream/downstream mode | Restore 上下游拆解, 价值链拆解, 竞争格局 modes. |
| K线预测 总览 and 单股预测 duplicate content | 总览 shows portfolio/model overview; 单股预测 shows individual stock chart, horizon tabs, factors, and forecast cards. |
| Some content panels are blank when API data is unavailable | Render realistic fallback data with explicit “等待真实数据” state, not empty whitespace. |

## Page Data Contract Rule

Every target page must define a page ViewModel before implementation:

| Field | Required | Meaning |
|---|---|---|
| `page.title` | Yes | Current route title shown in shell/header. |
| `page.tabs` | Yes | Current module tabs only. |
| `context` | Yes | tenant/user/account/role/trade mode. |
| `data_domain` | Yes | public/tenant/user/account data labels used by UI. |
| `freshness` | Yes | data and model freshness. |
| `lineage` | Yes for P0/trading pages | DecisionContext/Candidate/Plan/Order/RiskVerdict references. |
| `sections` | Yes | Typed content sections matching the preview. |
| `actions` | Yes | Allowed actions with disabled/reason state. |

If a service cannot provide real data yet, the BFF must still return the same shape with `empty_state` or `fallback_reason`. The React page must never infer page structure from missing fields.
