# Repair Sprint — 5 角色审查修复计划

- **Date**: 2026-06-12
- **Owner**: product-lead
- **Trigger**: 5 角色全量审查（product-lead / tech-lead / backend-dev / frontend-dev / qa-engineer）
- **Total findings**: 13 gaps (product-lead) + 7 P0/P1 (tech-lead) + 6 P0/P1/P2 (backend-dev) + 25 issues (frontend-dev) + E2E/UAT 42% coverage (qa-engineer)

---

## 1. 修复优先矩阵

### Critical（5 项，阻断交付）

| # | 发现 | 来源 | 影响范围 |
|---|------|------|---------|
| C1 | stk_auction_o schema 冲突 — 9:25 竞价同步必抛异常 | tech-lead P0-1 | data-service |
| C2 | 全部微服务无 RBAC — 实盘交易 API 零访问控制 | tech-lead P0-2/P0-3 | 全平台 8 服务 |
| C3 | auto-trading CR BLOCK → 违规推进 E2E/UAT | product-lead G-2 | strategy-service + frontend |
| C4 | live-trading CR 5 blocker → 违规推进 E2E/UAT | product-lead G-3 | trade-service + frontend |
| C5 | data-pipeline-refactor 8 AC 全未测试，E2E/UAT 空白 | qa-engineer | data-service |

### P0（8 项，各 feature 内部阻断）

| # | 发现 | 来源 |
|---|------|------|
| P0-1 | data-pipeline code review F#1 (write order) + F#3 (string parsing) | product-lead G-8 |
| P0-2 | migrate_data.py 端口 5432 + 缺 5 张新表 | backend-dev |
| P0-3 | auto-trading frontend API path `/auto-trade` → `/strategy` 全量不匹配 | frontend-dev |
| P0-4 | auto-trading backend ExecutorManager double-execution + pnl_pct 零除 | frontend-dev/backend-dev |
| P0-5 | model training frontend: Rollback/Cancel/Archive 3 端点 404/422 | frontend-dev |
| P0-6 | diagnosis frontend: TypeScript 类型 vs 后端 DiagnosisReport 完全不兼容 | frontend-dev |
| P0-7 | live-trading 3 Open Questions 无 Owner | product-lead G-4 |
| P0-8 | live-trading 前后端 5 个 blocker（B-1/B-2/B-3/B-1/B-2）| frontend-dev/backend-dev |

### P1（8 项，质量/合规）

| # | 发现 | 来源 |
|---|------|------|
| P1-1 | sync_to_pg.py 缺 LEGACY 标记 | tech-lead P1-2 |
| P1-2 | ths_daily 表无 PG 直写函数 | tech-lead P1-3 |
| P1-3 | ETL CB 写法不一致 | backend-dev |
| P1-4 | Gateway httpx → urllib 规范 | backend-dev |
| P1-5 | 端口 8000 → 8080 | backend-dev |
| P1-6 | PRD auto-trading/live-trading 缺独立 10 节结构 | product-lead G-1 |
| P1-7 | AC-11.5/AC-11.6 缺失 | product-lead G-5 |
| P1-8 | auth 内嵌 backend 未记录于 ADR-001 | tech-lead P1-1 |

### P2（5 项，测试/文档/远期）

| # | 发现 | 来源 |
|---|------|------|
| P2-1 | 跨 feature 集成测试空白 | product-lead G-7 |
| P2-2 | E2E/UAT 报告格式非 agf-writing-qa-report skill | product-lead G-9 |
| P2-3 | screener/prediction/signal/backtest/alert 5 服务无 E2E/UAT | qa-engineer |
| P2-4 | Backtest.tsx 51 行空壳 | frontend-dev |
| P2-5 | 5 服务无 Unit 测试 | backend-dev |

---

## 2. 依赖关系图

```
Chain A (数据管道):
  A1(stk_auction_o) + A2(F#1 write order) + A3(F#3 string parsing)
  + A4(P1-1 LEGACY) + A5(P1-2 ths_daily) + A6(migrate port+tables)
  → A7(re-review) → A8(E2E) → A9(UAT)

Chain B (自动交易):
  B1-B4(frontend: API path+fields+status+form) || B5-B6(backend: executor+pnl)
  → B7(re-review) → B8(E2E) → B9(UAT)

Chain C (实盘交易):
  C1-C3(backend: xtquant+audit+breaker) || C4-C5(frontend: RiskCheck+Paper GET)
  → C6(OQ owners) → C7(re-review) → C8(E2E) → C9(UAT)

Chain D (模型训练):
  D1-D4(frontend: Rollback+Cancel+Archive+Deploy) → D5(re-review) → D6(E2E) → D7(UAT)

Chain E (个股诊断):
  E1-E5(frontend: types+PDF+history+grade+mock) → E6(re-review) → E7(E2E) → E8(UAT)

Chain F (RBAC 安全):
  F1(kronos-auth 包) → F2-F6(逐服务加 Depends) → F7(review) → F8(E2E) → F9(UAT)

Chain G (清理):
  G1-G3(ETL/Gateway/port) || G4(tests) || G5(Backtest.tsx)

Chain H (测试覆盖):
  H1(screener) → H2(prediction) → H3(signal) → H4(backtest) → H5(alert)
```

**关键依赖**:
- Chain F（RBAC）应在 Chain B/C/D/E re-E2E/UAT 之前完成，否则重新验证的仍是"无鉴权"版本
- Chain A（数据管道）完全独立，可最先推进
- Chain B/C/D/E 的 frontend 修复可并行（不同文件，无冲突）
- Chain B/C 的 backend 修复涉及不同服务（strategy-service vs trade-service），可并行

---

## 3. Wave 1 任务分解（Critical + P0，本次 Sprint）

### Task 分配总览

| Task ID | 描述 | 角色 | 优先级 | 依赖 |
|---------|------|------|--------|------|
| T-201 | data-pipeline-refactor 修复包（6 项）| backend-dev | Critical | — |
| T-202 | auto-trading + live-trading backend 修复（5 项）| backend-dev | Critical | — |
| T-203 | kronos-auth 共享包 + RBAC 首服务 | backend-dev | Critical | tech-lead 方案确认后 |
| T-204 | auto-trading frontend 修复（7 项）| frontend-dev | Critical | — |
| T-205 | live-trading frontend 修复（5 项）| frontend-dev | Critical | — |
| T-206 | model-training frontend 修复（4 项）| frontend-dev | Critical | — |
| T-207 | diagnosis frontend 修复（5 项）| frontend-dev | Critical | — |
| T-208 | live-trading OQ 分配 Owner | product-lead | P0 | — |

### 详细 Task 定义

---

**T-201: data-pipeline-refactor 修复包**

- 任务描述：修复 data-pipeline-refactor 的 6 项 Critical/P0/P1 问题
- 任务类型：bugfix
- 上下文：
  - 技术栈: Python 3.10+, psycopg2, data-service
  - 涉及模块: `services/data-service/app/sync/pg_writer.py`, `tushare.py`, `stocks.py`, `scheduler.py`, `routers/data.py`
  - 关联: ADR-006, PRD `data-pipeline-refactor-2026-06-12.md`, review `data-pipeline-refactor-2026-06-12.md`
  - **本 task 强制单实例处理，理由：涉及 data-service 同文件多处改动（pg_writer/scheduler/stocks），不可并行**
- 上游产物（必读）：
  - `docs/reviews/data-pipeline-refactor-2026-06-12.md` F#1/F#3（product-lead code review）
  - `progress/tech-lead.md` P0-1 + P1-2 + P1-3（tech-lead 架构审查）
  - `progress/backend-dev.md` P0 migrate_data.py 端口（backend-dev 审计）
- 验收标准：
  - [ ] AC-201.1: `stk_auction_o` 表 schema 与 `scheduler.py:136` INSERT 列一致（tech-lead P0-1）
  - [ ] AC-201.2: `sync_stock_list()` PG 写入在 SQLite 之前（review F#1 write order violation）
  - [ ] AC-201.3: `pg_write_status` 由结构化字段提取，非 regex string-parsing（review F#3）
  - [ ] AC-201.4: `sync_to_pg.py` 文件头加 `# LEGACY: use data-service for daily sync`（tech-lead P1-2）
  - [ ] AC-201.5: `pg_writer.py` 新增 `write_ths_daily()` 函数（tech-lead P1-3）
  - [ ] AC-201.6: `migrate_data.py` 端口 5432 → 6432，确保覆盖所有新增表
  - [ ] AC-201.7: `grep -rn "sync_daily_to_pg" services/data-service/` 返回空（AC-7 再验证）
- 预期产物：
  - `services/data-service/app/sync/pg_writer.py`（修改）
  - `services/data-service/app/sync/stocks.py`（修改）
  - `services/data-service/app/routers/data.py`（修改）
  - `services/sql/init_postgres.sql` 或 `services/data-service/app/scheduler.py`（修改，二选一修复 stk_auction_o schema）
  - `Kronos/tools/sync_to_pg.py`（加 LEGACY 注释）
  - `services/sql/migrate_data.py`（修改端口）
  - `progress/backend-dev-1.md`（SIT 证据，template: free）

---

**T-202: auto-trading + live-trading backend 修复包**

- 任务描述：修复 auto-trading 2 Critical + live-trading 3 Blocker
- 任务类型：bugfix
- 上下文：
  - 技术栈: Python 3.10+, FastAPI, asyncio
  - 涉及模块: `services/strategy-service/app/auto_trading_executor.py`, `services/trade-service/app/xtquant_broker.py`, `audit_log.py`, `circuit_breaker.py`, `risk_gateway.py`
  - 关联: ADR-002, ADR-003
  - **本 task 强制单实例处理，理由：跨 strategy-service 和 trade-service 两个微服务，需协调修复**
- 上游产物（必读）：
  - `docs/reviews/auto-trading-backend-2026-06-10.md` C-1/C-2（code-reviewer）
  - `docs/reviews/live-trading-backend-2026-06-10.md` B-1/B-2/B-3（code-reviewer）
- 验收标准：
  - [ ] AC-202.1: `ExecutorManager.start()` 拒绝 paused 状态 re-start，仅允许 stopped→start 或 paused→resume
  - [ ] AC-202.2: `auto_trading_executor.py` pnl_pct 计算无零除风险
  - [ ] AC-202.3: `XtquantBroker.place_order()` 在 SDK 可用但未连接时抛出异常/返回 REJECTED，不静默 fallback 到 stub
  - [ ] AC-202.4: `audit_logs` 表名与 api-contract 一致（`trade_audit_log` 或统一为 `audit_logs`）
  - [ ] AC-202.5: `CircuitBreaker` 状态机新增 HALF_OPEN 状态 + DB 持久化
- 预期产物：
  - `services/strategy-service/app/auto_trading_executor.py`（修改）
  - `services/trade-service/app/xtquant_broker.py`（修改）
  - `services/trade-service/app/audit_log.py` 或 migration（修改）
  - `services/trade-service/app/circuit_breaker.py`（修改）
  - `progress/backend-dev-2.md`（SIT 证据）

---

**T-204: auto-trading frontend 修复包**

- 任务描述：修复 auto-trading frontend 1 Critical + 3 High + 3 Medium
- 任务类型：bugfix
- 上下文：
  - 技术栈: React 18 + TypeScript 5.6 + Vite 6
  - 涉及模块: `frontend/src/pages/AutoTrade.tsx`, `Strategy.tsx`, `vite.config.ts`
  - 关联: ADR-003, `docs/design/auto-trading/frontend-plan.md`
- 上游产物（必读）：
  - `docs/reviews/auto-trading-frontend-2026-06-10.md` C-1/H-1~H-3（code-reviewer）
  - `progress/frontend-dev.md` §二-2（frontend-dev 审计）
- 验收标准：
  - [ ] AC-204.1: 所有 API 调用改用 `/api/v1/strategy/*`（非 `/api/v1/auto-trade/*`），`vite.config.ts` proxy 确认已覆盖
  - [ ] AC-204.2: 请求体字段名与后端 API contract 一致（`indicator`→`field`, `rule_type` 数组→对象）
  - [ ] AC-204.3: 状态值枚举与后端一致（`running/terminated/completed` → `active/stopped/draft`）
  - [ ] AC-204.4: 策略创建表单含 `trade_mode`/`check_interval_sec`/`capital`/`picks` 字段
  - [ ] AC-204.5: Log 条目字段名匹配（`action`+`detail` → `message`+`details`）
  - [ ] AC-204.6: `npx tsc -b --noEmit` 0 错误
  - [ ] AC-204.7: `npm run build` 成功
- 预期产物：
  - `frontend/src/pages/AutoTrade.tsx`（修改）
  - `frontend/src/pages/Strategy.tsx`（修改）
  - `frontend/vite.config.ts`（修改，如需要）
  - `progress/frontend-dev-1.md`（SIT 证据）

---

**T-205: live-trading frontend 修复包**

- 任务描述：修复 live-trading frontend 2 Blocker + 3 High
- 任务类型：bugfix
- 上下文：
  - 涉及模块: `frontend/src/components/trade/RiskCheckModal.tsx`, `LargeTradeConfirm.tsx`, `CircuitBreakerAlert.tsx`; `frontend/src/hooks/useLiveTrade.ts`; `frontend/src/api/liveTrade.ts`
  - 关联: ADR-002, `docs/design/live-trading/frontend-plan.md`
- 上游产物（必读）：
  - `docs/reviews/live-trading-frontend-2026-06-10.md` B-1/B-2/H-1~H-3（code-reviewer）
- 验收标准：
  - [ ] AC-205.1: `RiskCheckModal` 字段契约与后端 `RiskResult` 一致（`level`: PASS/WARN/REJECT 替换 `passed`/`block`）
  - [ ] AC-205.2: Paper 模式下单改用 POST body（非 GET query params），消除 URL 敏感数据泄露
  - [ ] AC-205.3: 大额阈值前端从后端配置读取（`GET /config`），避免前后端独立配置不一致
  - [ ] AC-205.4: 熔断提示文案与后端实际行为一致
  - [ ] AC-205.5: `npx tsc -b --noEmit` 0 错误 + `npm run build` 成功
- 预期产物：
  - `frontend/src/components/trade/RiskCheckModal.tsx`（修改）
  - `frontend/src/hooks/useLiveTrade.ts`（修改）
  - `frontend/src/api/liveTrade.ts`（修改）
  - `progress/frontend-dev-2.md`（SIT 证据）

---

**T-206: model-training frontend 修复包**

- 任务描述：修复 model-training frontend 4 P0
- 任务类型：bugfix
- 上下文：
  - 涉及模块: `frontend/src/pages/ModelRegistry.tsx`, `Training.tsx`
  - 关联: ADR-004, `docs/design/model-training/frontend-plan.md`
- 上游产物（必读）：
  - `docs/reviews/model-training-frontend-2026-06-10.md`（code-reviewer）
  - `progress/frontend-dev.md` §三-1 P0-1~P0-4（frontend-dev 审计）
- 验收标准：
  - [ ] AC-206.1: `ModelRegistry.tsx:281` Rollback 含 `target_version` 参数，不再 422
  - [ ] AC-206.2: `Training.tsx:534` Cancel 端点路径修正（`/training/{id}/cancel` 需后端对齐或改为已有端点）
  - [ ] AC-206.3: `ModelRegistry.tsx:300` Archive 端点路径修正（同上）
  - [ ] AC-206.4: `ModelRegistry.tsx:264` Deploy 支持 `notes` 参数
  - [ ] AC-206.5: `npx tsc -b --noEmit` 0 错误 + `npm run build` 成功
- 预期产物：
  - `frontend/src/pages/ModelRegistry.tsx`（修改）
  - `frontend/src/pages/Training.tsx`（修改）
  - `progress/frontend-dev-3.md`（SIT 证据）

---

**T-207: diagnosis frontend 修复包**

- 任务描述：修复 diagnosis frontend 3 Critical + 3 High
- 任务类型：bugfix
- 上下文：
  - 涉及模块: `frontend/src/pages/Diagnosis.tsx`, `frontend/src/api/client.ts`
  - 关联: ADR-005
- 上游产物（必读）：
  - `docs/reviews/diagnosis-frontend-2026-06-10.md` C1~C3/H1~H3（code-reviewer）
  - `progress/frontend-dev.md` §三-3（frontend-dev 审计）
- 验收标准：
  - [ ] AC-207.1: `Diagnosis.tsx` TypeScript 类型与后端 `DiagnosisReport` 数据模型对齐
  - [ ] AC-207.2: PDF URL 含 `/diagnosis` 路径段
  - [ ] AC-207.3: 历史记录字段 `data.records` → `data.items`
  - [ ] AC-207.4: `grade` 枚举值与后端一致（`strong_buy` → "A"/"B+"）
  - [ ] AC-207.5: Mock fallback 加 `import.meta.env.DEV` 守卫，生产环境不静默降级
  - [ ] AC-207.6: `npx tsc -b --noEmit` 0 错误 + `npm run build` 成功
- 预期产物：
  - `frontend/src/pages/Diagnosis.tsx`（修改）
  - `frontend/src/api/client.ts`（修改，如需要）
  - `progress/frontend-dev-4.md`（SIT 证据）

---

## 4. 阶段门推进计划

```
Wave 1 (本次 Sprint):
┌─────────────────────────────────────────────────────────┐
│ T-201 ──→ code-review-1 ──→ E2E ──→ UAT               │
│ T-202 ──→ code-review-2 ──→ E2E (合并)                 │
│ T-203 ──→ code-review-3 ──→ E2E (合并)                 │
│ T-204 ──→ code-review-4 ──→ E2E (合并)                 │
│ T-205 ──→ code-review-4 ──→ E2E (合并)                 │
│ T-206 ──→ code-review-4 ──→ E2E (合并)                 │
│ T-207 ──→ code-review-4 ──→ E2E (合并)                 │
│ T-208 (product-lead 自闭环)                              │
└─────────────────────────────────────────────────────────┘

Wave 2 (下个 Sprint):
- P1 清理 (Chain G)
- E2E/UAT 覆盖率补齐 (Chain H: screener → prediction → signal → backtest → alert)
- PRD 补齐 (auto-trading + live-trading 10 节)
```

### 并行策略

- **backend-dev-1** (T-201) + **backend-dev-2** (T-202) + **backend-dev-3** (T-203): 三个 backend task 涉及不同文件/服务，可并行（worktree 隔离）
- **frontend-dev-1** (T-204) + **frontend-dev-2** (T-205) + **frontend-dev-3** (T-206) + **frontend-dev-4** (T-207): 四个 frontend task 涉及不同页面文件，可并行（worktree 隔离）
- T-208（product-lead）: 独立，不与其他 task 冲突

### Pool 触发条件

- backend 同 type ≥ 2 (T-201/T-202/T-203 = 3) → 触发 pool，spawn backend-dev-1/2/3
- frontend 同 type ≥ 2 (T-204/T-205/T-206/T-207 = 4) → 触发 pool，spawn frontend-dev-1/2/3/4
- code-review 同 type ≥ 2 → pool code-reviewer-1/2/3/4

---

## 5. 成功指标

- [ ] Wave 1 结束：5 Critical + 8 P0 全部修复并 re-review 通过
- [ ] data-pipeline-refactor E2E + UAT 完成（当前 active feature 闭环）
- [ ] auto-trading + live-trading + model-training + diagnosis 重新 E2E + UAT 通过
- [ ] 微服务 RBAC 覆盖 trade-service + strategy-service（首批，含实盘资金操作）
- [ ] 0 TypeScript 编译错误 + 0 前端 build 失败
- [ ] E2E/UAT 覆盖率从 42% 提升至 ≥ 58%（+data-pipeline + 首批 RBAC 覆盖服务）

---

## Changelog

- 2026-06-12: 初稿，基于 5 角色审查报告汇总
