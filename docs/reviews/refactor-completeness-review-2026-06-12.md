# Refactor Completeness Review — 产品差距分析

- **Date**: 2026-06-12
- **Reviewer**: product-lead
- **Scope**: 3 个 PRD 的产品质量 + 交付状态 + 跨 feature 差距
- **References**:
  - `docs/prd/data-pipeline-refactor-2026-06-12.md`
  - `docs/prd/auto-trading-2026-06-10.md`
  - `docs/prd/live-trading-2026-06-10.md`
  - `Kronos/docs/投资管理平台_PRD_产品需求文档.md`（master PRD，AC-10.x / AC-11.x 的母文档）
  - `docs/reviews/data-pipeline-refactor-2026-06-12.md`
  - `docs/reviews/auto-trading-backend-2026-06-10.md` / `auto-trading-frontend-2026-06-10.md`
  - `docs/reviews/live-trading-backend-2026-06-10.md` / `live-trading-frontend-2026-06-10.md`
  - `docs/qa/auto-trading-e2e-2026-06-10.md` / `auto-trading-uat-2026-06-10.md`
  - `docs/qa/live-trading-e2e-2026-06-10.md` / `live-trading-uat-2026-06-10.md`
  - `progress/tech-lead.md`（2026-06-12 架构合规审查，3 P0 + 4 P1）

---

## 1. PRD 产品需求覆盖度评估

### 1.1 data-pipeline-refactor-2026-06-12.md

| 章节 | 状态 | 评价 |
|---|---|---|
| §1 Background | ✅ 完整 | 6 条痛点清晰，4 跳链路图直观 |
| §2 Goal & Non-Goals | ✅ 完整 | 3 项 KPI 可量化，5 项 Non-Goals 边界明确 |
| §3 User Stories | ✅ 完整 | 4 条 US，角色 + 场景 + 价值清晰 |
| §4 Acceptance Criteria | ✅ 完整 | 8 条 AC（P0:3 / P1:3 / P2:2），全部可 curl 验证 |
| §5 Design | ✅ 完整 | 架构图 + ADR 决策引用表 + 调度变更 + 改动文件清单 |
| §6 Technical Constraints | ✅ 完整 | 7 条约，含性能预算和速率门禁 |
| §7 Cost Estimate | ✅ 完整 | Medium 档 + token 估算 |
| §8 Out of Scope | ✅ 完整 | 6 项显式排除 |
| §9 Open Questions | ✅ 全部决议 | 5 个问题均由 ADR-006 落盘，各有 owner |
| §10 Sign-offs | ⚠️ 未完整 | tech-lead ✅ / product-lead ✅ / **backend-dev 未签** |

**PRD 质量评分**: 9/10（§10 缺 backend-dev 确认签字）

---

### 1.2 auto-trading-2026-06-10.md

| 章节 | 状态 | 评价 |
|---|---|---|
| §1 Background | ❌ 缺失 | 未说明痛点/背景，直接跳 Scope |
| §2 Goal & Non-Goals | ❌ 缺失 | 无 KPI，无 Non-Goals 防范围蔓延 |
| §3 User Stories | ❌ 缺失 | 无 As-a/I-want/So-that 格式 |
| §4 Acceptance Criteria | ⚠️ 不完整 | 仅引用外部 AC ID（AC-10.6~10.8, AC-11.5~11.6），未逐条列出可验证文本 |
| §5 Design | ⚠️ 不完整 | 4 个组件名罗列，无架构图/API 契约/数据模型 |
| §6 Technical Constraints | ❌ 缺失 | — |
| §7 Cost Estimate | ❌ 缺失 | — |
| §8 Out of Scope | ❌ 缺失 | — |
| §9 Open Questions | ❌ 缺失 | — |
| §10 Sign-offs | ❌ 缺失 | — |

**PRD 质量评分**: 1/10。该文件是 **轻量 spec 提取稿**，非独立 PRD。其母文档为 `Kronos/docs/投资管理平台_PRD_产品需求文档.md` §3.10。

---

### 1.3 live-trading-2026-06-10.md

| 章节 | 状态 | 评价 |
|---|---|---|
| §1 Background | ❌ 缺失 | 未说明痛点/背景 |
| §2 Goal & Non-Goals | ❌ 缺失 | 无 KPI，无 Non-Goals |
| §3 User Stories | ❌ 缺失 | 无标准格式 |
| §4 Acceptance Criteria | ⚠️ 不完整 | 7 条 AC 有简要映射，但缺少 Verification method 列，且 AC-11.5/AC-11.6 缺失（跳号: 11.1~11.4 → 11.7~11.9） |
| §5 Design | ⚠️ 部分 | 有架构流程图 + DB schema，但无前端 UI 引用 |
| §6 Technical Constraints | ❌ 缺失 | — |
| §7 Cost Estimate | ❌ 缺失 | — |
| §8 Out of Scope | ❌ 缺失 | — |
| §9 Open Questions | ❌ 违规 | **3 个 Open Questions 均无 Owner**（违反 `product-workflow.md` §4.1: "每条必须标 Owner，否则不允许进入 Step 2 任务分配"） |
| §10 Sign-offs | ❌ 缺失 | — |

**PRD 质量评分**: 2/10。同 auto-trading，是轻量 spec 提取稿。母文档为 `Kronos/docs/投资管理平台_PRD_产品需求文档.md` §3.11。

**Open Questions（无 Owner，阻断级）**:
1. xtquant 需本地运行客户端，Docker 部署方案？→ **无 Owner**
2. 券商断线后持仓如何处理？→ **无 Owner**
3. 实盘是否需要独立交易密码（非登录密码）？→ **无 Owner**

---

## 2. 交付状态矩阵

### 2.1 按 Stage Gate 逐 feature 审视

| Stage Gate | data-pipeline-refactor | auto-trading | live-trading |
|---|---|---|---|
| **PRD** | ✅ Approved (v1.1) | ⚠️ 轻量 spec，非独立 PRD | ⚠️ 轻量 spec，非独立 PRD |
| **Code + Unit + SIT** | ✅ progress/backend-dev.md 有 SIT 证据 | ⚠️ 有 progress/backend-dev-autotrade.md + frontend-dev-autotrade.md | ⚠️ 有 progress/backend-dev-livetrade.md + frontend-dev-livetrade.md |
| **Code Review** | ⚠️ Approve with Changes (2 fix needed) | ❌ **BLOCK** (BE: 2 criticals / FE: 1 critical) | ⚠️ Approve with Changes (BE: 3 blockers / FE: 2 blockers) |
| **E2E** | ❌ 未执行 | ⚠️ 10/10 PASS（但在 CR BLOCK 状态下执行）| ⚠️ 10/10 PASS（但在 CR 有 5 个 blocker 状态下执行）|
| **UAT** | ❌ 未执行 | ⚠️ 7/7 PASS approve（但在 CR BLOCK 状态下执行）| ⚠️ 8/8 PASS approve（但在 CR 有 5 个 blocker 状态下执行）|

### 2.2 阶段门违规详细记录

#### 违规 1: auto-trading CR BLOCK → E2E/UAT 照常推进

- **Code Review Backend verdict**: **BLOCK** — 2 critical bugs（ExecutorManager double-execution + auto_trading_executor pnl_pct 零除）
- **Code Review Frontend verdict**: **BLOCK** — 1 critical bug（API path `/api/v1/auto-trade/*` vs backend `/api/v1/strategy/*` 全量不匹配）
- **UAT 报告声称**: "2 criticals fixed" — 但 fix 之后**没有 re-review 证据**，前端 API 路径 mismatch 未提及修复
- **UAT 执行者**: "team-lead"，非 qa-engineer（违反角色分工）
- **结论**: 该 feature 在 CR stage gate 被 BLOCK 后不应进入 E2E，属于**阶段门跳跃**

#### 违规 2: live-trading CR 有 5 个 blocker → E2E/UAT 照常推进

- **Code Review Backend** (APPROVE WITH CHANGES)：
  - B-1: XtquantBroker 静默 fallback 到 stub（虚假成交风险）
  - B-2: 审计日志表名不一致（`audit_logs` vs `trade_audit_log`）
  - B-3: 熔断状态机缺 HALF_OPEN + 无 DB 持久化
- **Code Review Frontend** (APPROVE WITH CHANGES)：
  - B-1: RiskCheckModal 风控字段契约不匹配（`passed`/`block` vs `level`）
  - B-2: Paper 模式下单用 GET 式 query params
- **E2E/UAT 执行者**: "team-lead"，非 qa-engineer
- **结论**: 5 个 blocker 在未确认修复的情况下推进 E2E/UAT，**UAT 签字无效**

#### 违规 3: E2E/UAT 报告格式不符合 skill 规范

- E2E/UAT 报告未使用 `agf-writing-qa-report` skill
- 报告为简化 markdown 表格，缺少 prerequisite gate 详细校验、证据截图、环境描述
- UAT 签字人非 product-lead（应由 product-lead 对照 PRD AC 逐条业务签字）

---

## 3. 跨 Feature 差距

### 3.1 母 PRD 与子 spec 断链

- `auto-trading-2026-06-10.md` 和 `live-trading-2026-06-10.md` 都引用 `Kronos/docs/投资管理平台_PRD_产品需求文档.md` 的 AC-10.x / AC-11.x
- 但这个母 PRD 的 AC 原文**未被摘录到子 spec 中**，只放了 ID 引用
- 按 `product-workflow.md` §3.3 规则 1：Task 派发时必须"逐字摘录" AC，子 spec 也应至少复述 AC 原文
- **风险**: AC-11.5 / AC-11.6 在 live-trading-2026-06-10.md 中完全缺失

### 3.2 数据管道重构对下游 feature 的影响未评估

- `data-pipeline-refactor` 改变了 data-service → PG 的数据写入路径
- auto-trading 的 `strategy-service（8003）` 和 live-trading 的 `trade-service（8006）` 都依赖 PG 数据
- 但 **没有任何集成测试或影响评估** 覆盖以下场景：
  - PG 写入延迟增加是否影响自动交易策略的调仓时机判断？
  - `stocks` 表新增/更新是否影响实盘交易的股票代码校验？
  - `mv_daily_composite_ranking` 新物化视图是否被 screener-service 引用？

### 3.3 测试策略覆盖率空白

| 测试层级 | data-pipeline-refactor | auto-trading | live-trading |
|---|---|---|---|
| Unit 测试 | ✅ SIT 证据含语法检查 | ⚠️ 未确认 | ⚠️ 未确认 |
| SIT（集成）| ✅ progress/backend-dev.md | ⚠️ progress 文件存在但质量待 audit | ⚠️ progress 文件存在但质量待 audit |
| E2E | ❌ 未执行 | ⚠️ 执行但前置 gate 不通过 | ⚠️ 执行但前置 gate 不通过 |
| UAT | ❌ 未执行 | ⚠️ 执行但前置 gate 不通过 | ⚠️ 执行但前置 gate 不通过 |
| 跨 feature 集成 | ❌ 无 | ❌ 无 | ❌ 无 |

### 3.4 Live Trading 上线阻断项

按 `product-workflow.md` §4.1 规则，Open Questions 无 Owner 即不允许进入 Step 2 任务分配。当前 live-trading 的 3 个 OQ 均无 Owner，意味着：

1. **xtquant Docker 部署方案**未定 → 生产环境无法部署
2. **券商断线持仓处理**未定 → 实盘资金风险敞口
3. **独立交易密码**未定 → 合规/安全未闭环

这 3 个问题是实盘上线的**硬阻断**，且不会随代码实现自行消失。

### 3.5 架构合规审查（tech-lead 2026-06-12）

> 来源：`progress/tech-lead.md`，全量 ADR-001~006 + CLAUDE.md 交叉验证。

#### P0 发现（3 项，影响当前 feature 交付有效性）

| ID | 问题 | 影响范围 | 关联 feature |
|---|---|---|---|
| P0-1 | **stk_auction_o schema 冲突** — `scheduler.py` INSERT 列与 `init_postgres.sql` 表定义完全不匹配，9:25 竞价同步必抛异常 | data-service 运行时错误 | data-pipeline-refactor |
| P0-2 | **全部微服务无 RBAC** — screener/signal/trade/strategy 零 `require_role` 调用，所有端点公开无保护 | 8 个微服务安全敞口 | 全部（auto-trading, live-trading 含实盘资金操作） |
| P0-3 | **`packages/kronos-auth/` 缺失** — ADR-001 要求的共享 RBAC 包不存在，P0-2 修复缺基础组件 | 架构依赖缺失 | 全部 |

#### P1 发现（4 项，ADR-006/ADR-001 合规不足）

| ID | 问题 |
|---|---|
| P1-1 | auth 内嵌 backend (9001) 而非独立 auth-service (8010)，ADR-001 未记录此决策变更 |
| P1-2 | `sync_to_pg.py` 缺 `# LEGACY` 标记（ADR-006 决策 3 未完成） |
| P1-3 | `ths_daily` 表无 PG 直写函数（ADR-006 决策 2 P1 范围缺失） |
| P1-4 | `materialized_views.sql` 独立文件不存在，物化视图 DDL 内联在 `init_postgres.sql` |

#### 对 gap 清单的影响

- P0-1 直接关联 data-pipeline-refactor，应在 E2E 前修复
- P0-2/P0-3 是平台级安全 gap：auto-trading/live-trading 的实盘交易 API 当前无任何访问控制，即使代码功能正确，**安全合规不通过则产品不可对外交付**
- P1-2/P1-3 补充了 code review 未发现的 ADR-006 合规缺口

---

## 4. 综合差距清单

| # | 类别 | 严重级 | 描述 | 影响 feature |
|---|---|---|---|---|
| G-1 | PRD 质量 | High | auto-trading 和 live-trading 缺少独立 10 节 PRD，仅为轻量 spec | auto-trading, live-trading |
| G-2 | Stage Gate | **Critical** | auto-trading CR BLOCK 后违规推进 E2E/UAT，UAT 签字无效 | auto-trading |
| G-3 | Stage Gate | **Critical** | live-trading 5 个 blocker 未修复即推进 E2E/UAT，UAT 签字无效 | live-trading |
| G-4 | Open Questions | High | live-trading 3 个 OQ 无 Owner，含生产部署和安全关键问题 | live-trading |
| G-5 | AC 完整性 | Medium | AC-11.5/AC-11.6 在 live-trading spec 中缺失；auto-trading 仅引用 AC ID 未摘录原文 | auto-trading, live-trading |
| G-6 | 签字链 | Medium | data-pipeline-refactor §10 缺 backend-dev 签字；E2E/UAT 报告签字人非 product-lead | 全部 |
| G-7 | 测试策略 | Medium | 无跨 feature 集成测试，数据管道变更对交易链路的影响未验证 | data-pipeline-refactor → auto-trading/live-trading |
| G-8 | Code Review | Medium | data-pipeline-refactor F#1（写入顺序）+ F#3（string parsing）需修后 re-review 才能 E2E | data-pipeline-refactor |
| G-9 | 报告规范 | Low | E2E/UAT 报告未使用 `agf-writing-qa-report` skill，格式不标准 | auto-trading, live-trading |
| G-10 | 角色执行 | Medium | E2E/UAT 由 "team-lead" 执行而非 "qa-engineer"，违反角色分工 | auto-trading, live-trading |
| G-11 | 运行时 bug | **Critical** | stk_auction_o schema 冲突，9:25 竞价同步必抛异常（tech-lead P0-1） | data-pipeline-refactor |
| G-12 | 安全合规 | **Critical** | 全部微服务无 RBAC，实盘交易 API 零访问控制（tech-lead P0-2/P0-3） | 全部 feature |
| G-13 | ADR-006 合规 | Medium | sync_to_pg.py 缺 LEGACY 标记 + ths_daily 缺 PG 直写（tech-lead P1-2/P1-3） | data-pipeline-refactor |

---

## 5. 建议补救措施

### 5.1 立即（P0，阻断 E2E/UAT 或安全合规）

1. **回退 auto-trading 和 live-trading 的 E2E/UAT 状态** — CR gate 未通过，现有 UAT 签字无效
2. **修复 auto-trading CR criticals** 并 re-review（尤其是前端 API path mismatch）
3. **修复 live-trading 5 个 blockers** 并 re-review
4. **为 live-trading 3 个 OQ 分配 Owner** 并推进决议
5. **修复 stk_auction_o schema 冲突**（tech-lead P0-1）— 否则 9:25 竞价同步必抛异常
6. **新建 `packages/kronos-auth/` 共享 RBAC 包**（tech-lead P0-3）— 此后方能修复 P0-2

### 5.2 短期（P1，本 sprint 内）

7. 补齐 auto-trading 和 live-trading 的独立 PRD（10 节），或将母 PRD 的 AC 逐条摘录到子 spec
8. 修复 data-pipeline-refactor F#1 + F#3 + P1-2 + P1-3，backend-dev re-review 后推进 E2E
9. 补全 AC-11.5/AC-11.6 定义
10. **微服务逐批加 RBAC**（tech-lead P0-2）— 结合 kronos-auth 包，按服务优先级分阶段

### 5.3 中期（P2，下 sprint）

11. 建立跨 feature 集成测试用例（数据管道 → 选股/信号/交易链路）
12. E2E/UAT 报告统一使用 `agf-writing-qa-report` skill + qa-engineer 角色执行
13. 补齐 data-pipeline-refactor §10 backend-dev 签字
14. 更新 ADR-001 记录 auth 内嵌 backend 决策（tech-lead P1-1）

---

## Changelog

- 2026-06-12: 初稿，覆盖 3 feature 的 PRD 质量 + 交付状态 + 跨 feature 差距
- 2026-06-12: v1.1 — 纳入 tech-lead 架构合规审查（3 P0 + 4 P1），新增 §3.5；G-11~G-13 入差距清单；补救措施 5.1 新增 P0-1/P0-3 两条
