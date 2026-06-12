# Repair Sprint Wave 2 — P1 清理 + E2E/UAT 覆盖率补齐 + 前端收尾

- **Date**: 2026-06-12
- **Owner**: product-lead
- **Trigger**: Wave 1 签字交付，遗留 P1 + E2E 覆盖率 42% + 前端空壳 + follow-up
- **Wave 1 baseline**: `docs/reviews/repair-sprint-signoff-2026-06-12.md`（Approve，21/21 AC）

---

## 1. 范围（4 条工作线）

### Line A: P1 清理（backend-dev，3 task）

| # | 发现 | 来源 | 服务 |
|---|------|------|------|
| A1 | ETL CB 写法不一致（`_Db` 封装统一） | backend-dev P1 | packages/kronos-data |
| A2 | Gateway httpx → urllib + 端口 8000→8080 | backend-dev P1 | api-gateway (8080) |
| A3 | ADR-001 架构漂移更新（auth 内嵌 backend） + materialized_views.sql 独立文件 | tech-lead P1-1/P1-4 | docs/adr/ + services/sql/ |

### Line B: E2E/UAT 补齐（qa-engineer，5 task）

| 服务 | 端口 | 风险 | 优先级 |
|------|:---:|------|:---:|
| screener-service | 8001 | HIGH — 全角色选股入口 | B1 |
| prediction-service | 8002 | HIGH — AI 核心能力 | B2 |
| signal-service | 8004 | MEDIUM — 被 strategy 依赖 | B3 |
| backtest-service | 8007 | MEDIUM — 选股→回测闭环 | B4 |
| alert-service | 8005 | MEDIUM — 实时通知 | B5 |

### Line C: 前端收尾（frontend-dev，3 task）

| # | 发现 | 来源 |
|---|------|------|
| C1 | Backtest.tsx 空壳实现（51 行占位） | frontend-dev |
| C2 | Dashboard + DataUpdate 代码审查 | frontend-dev |
| C3 | 测试补充（Unit + SIT，目标 10+ 文件） | frontend-dev |

### Line D: Follow-up（backend-dev + product-lead，3 task）

| # | 发现 | 来源 |
|---|------|------|
| D1 | CORS wildcard → 白名单（trade + strategy） | code-review W-2 |
| D2 | trade_password Query→Body | code-review W-1 |
| D3 | LIM-1 scheduler status 统一（API 触发也走 `_run_job`） | PL sign-off |

---

## 2. 依赖关系

```
Line A (独立):
  A1 || A2 || A3 → code-review → (no E2E needed, doc/config changes)

Line B (独立于 A/C/D):
  B1 → B2 → B3 → B4 → B5 (顺序执行，qa-engineer 单实例)

Line C (独立):
  C1 → C2 → C3 → code-review → E2E (frontend)

Line D (独立):
  D1 || D2 || D3 → code-review → E2E (D2 only)
```

**关键**：四条线之间无依赖，可完全并行。

---

## 3. Task 分解

### T-301: ETL CB 写法统一 + Gateway httpx→urllib + 端口修正

- 任务描述：修复 backend-dev 审计发现的 3 项 P1 问题（ETL CB 封装、Gateway 依赖规范、端口对齐）
- 任务类型：重构
- 上下文：
  - 技术栈: Python 3.10+, urllib, FastAPI
  - 涉及: packages/kronos-data/kronos_data/etl.py, services/api-gateway/app/main.py
  - 关联: CLAUDE.md 微服务间 HTTP 调用规范
- 上游产物（必读）：
  - progress/backend-dev.md P1 项（backend-dev 审计）
  - CLAUDE.md "微服务间 HTTP 调用使用 urllib async wrapper"
- 验收标准：
  - [ ] AC-301.1: ETL CB 写法统一为 `_Db` 封装
  - [ ] AC-301.2: Gateway 移除 httpx 依赖，改用 urllib async wrapper
  - [ ] AC-301.3: Gateway 端口 8000 → 8080
- 预期产物：
  - packages/kronos-data/kronos_data/etl.py (修改)
  - services/api-gateway/app/main.py (修改)
  - progress/backend-dev-w2-1.md (SIT 证据)

### T-302: ADR-001 架构漂移 + materialized_views.sql 独立文件

- 任务描述：更新 ADR-001 记录 auth 内嵌 backend 决策 + 提取物化视图 DDL 到独立文件
- 任务类型：文档
- 上下文：
  - 关联: ADR-001, ADR-006
- 上游产物（必读）：
  - progress/tech-lead.md P1-1 + P1-4
  - docs/adr/001-user-auth-rbac.md
- 验收标准：
  - [ ] AC-302.1: ADR-001 补充 "auth 合并入 backend (9001)，不独立部署 auth-service (8010)" 决策记录
  - [ ] AC-302.2: services/sql/materialized_views.sql 独立文件，含 4 个物化视图 DDL
- 预期产物：
  - docs/adr/001-user-auth-rbac.md (修改)
  - services/sql/materialized_views.sql (新建)
  - progress/backend-dev-w2-2.md

### T-303: screener-service E2E + UAT

- 任务描述：执行 screener-service (8001) 端到端 + 用户验收测试
- 任务类型：测试
- 上下文：
  - 服务: screener-service (8001)，6 模式选股 + 多因子排序
  - 关联: qa-engineer 风险 HIGH
- 上游产物（必读）：
  - progress/qa-engineer.md §二（未覆盖清单）
  - docs/prd/repair-sprint-wave2-2026-06-12.md
- 验收标准：
  - [ ] AC-303.1: screener-service 全部端点 curl E2E 通过（>= 10 scenarios）
  - [ ] AC-303.2: UAT 报告提交，含 RBAC 角色测试
- 预期产物：
  - docs/qa/screener-e2e-2026-06-12.md
  - docs/qa/screener-uat-2026-06-12.md

### T-304: prediction-service E2E + UAT

- 任务描述：执行 prediction-service (8002) E2E + UAT
- 任务类型：测试
- 上游产物（必读）：progress/qa-engineer.md
- 验收标准：
  - [ ] AC-304.1: prediction-service 全部端点 curl E2E 通过
  - [ ] AC-304.2: UAT 报告提交
- 预期产物：docs/qa/prediction-e2e-2026-06-12.md + uat

### T-305: signal-service + backtest-service + alert-service E2E+UAT（批量）

- 任务描述：执行 3 个 MEDIUM 服务的 E2E + UAT
- 任务类型：测试
- 验收标准：
  - [ ] AC-305.1: signal-service (8004) E2E+UAT 通过
  - [ ] AC-305.2: backtest-service (8007) E2E+UAT 通过
  - [ ] AC-305.3: alert-service (8005) E2E+UAT 通过
- 预期产物：docs/qa/signal/backtest/alert-e2e+uat 各 2 份

### T-306: Backtest.tsx 空壳实现

- 任务描述：实现 Backtest.tsx 回测分析页面（当前仅 51 行占位）
- 任务类型：新功能
- 上下文：
  - 技术栈: React 18 + TypeScript + Ant Design + ECharts
  - 关联: backtest-service (8007), ADR-006
- 验收标准：
  - [ ] AC-306.1: Backtest.tsx 含回测参数配置表单（日期/策略/基准）
  - [ ] AC-306.2: 回测结果图表（收益曲线 + IC/ICIR）
  - [ ] AC-306.3: tsc 0 错误 + build 成功
- 预期产物：frontend/src/pages/Backtest.tsx (重写), progress/frontend-dev-w2-1.md

### T-307: CORS 白名单 + trade_password Body 化 + LIM-1

- 任务描述：修复 3 项 follow-up（CORS wildcard、trade_password Query→Body、scheduler status 统一）
- 任务类型：bugfix
- 上下文：
  - CORS: trade-service + strategy-service main.py
  - trade_password: trade-service routes.py
  - LIM-1: data-service scheduler.py
- 验收标准：
  - [ ] AC-307.1: CORS allow_origins 改为环境变量白名单，移除 "*"
  - [ ] AC-307.2: trade_password 从 Query→Body
  - [ ] AC-307.3: POST /sync/post_market 后 scheduler status 正确更新
- 预期产物：
  - services/trade-service/app/main.py, strategy-service/app/main.py (修改)
  - services/trade-service/app/routes.py (修改)
  - services/data-service/app/scheduler.py (修改)

---

## 4. 并行策略

```
Wave 2 (本次 Sprint):
┌──────────────────────────────────────────────────────────────┐
│ Line A: backend-dev-w2 (T-301 + T-302)                       │
│ Line B: qa-engineer (T-303 → T-304 → T-305, 顺序)           │
│ Line C: frontend-dev-w2 (T-306)                              │
│ Line D: backend-dev-w2 (T-307)                               │
│                                                              │
│ A || B || C || D — 四条线完全并行，无文件冲突                │
└──────────────────────────────────────────────────────────────┘
```

- **backend-dev-w2**：T-301 + T-302 + T-307（3 个 task，不同模块，可串行由一个实例完成）
- **qa-engineer**：T-303 → T-304 → T-305（5 服务顺序测试，单实例）
- **frontend-dev-w2**：T-306（1 个 task，Backtest.tsx 实现）

---

## 5. 成功指标

- [ ] E2E/UAT 覆盖率：42% → **100%**（12/12 服务）
- [ ] P1 清理：3/3 完成（ETL + Gateway + ADR-001）
- [ ] 前端：Backtest.tsx 从 51 行空壳 → 功能完整页面
- [ ] Follow-up：CORS 白名单 + trade_password Body + LIM-1

---

## Changelog

- 2026-06-12: 初稿，基于 Wave 1 签字报告遗留项
