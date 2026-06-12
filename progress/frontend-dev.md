## 前端重构状态评估 - 2026-06-12

### 状态: 评估完成 — 4 个 feature 被 BLOCKED，核心修复工作尚未开始

**Skills used**: 无（纯代码审查 + 文档对比）

**SIT 证据**: 仅 `tests/sit/auth-flow.test.tsx` 一个 SIT 测试文件存在；其余 6 个功能模块零 SIT 覆盖。

**质量门**:
- TypeScript: 未跑（未在本次评估中构建）
- vitest: 仅 AuthContext + ProtectedRoute 有 Unit 测试（2 个文件）
- Lint: 未跑
- Dev server: 未启动

**下一步**: 需 product-lead 决定优先修复哪些 BLOCKED feature，以及是否需要重建文档与实现之间的一致性。

---

## 评估详情

### 一、代码现状（行数统计）

| 文件 | 行数 | 状态 |
|------|------|------|
| `pages/Training.tsx` | 788 | 实现完整，但 4 P0 + 1 P1 review 问题未修复 |
| `pages/ModelRegistry.tsx` | 803 | 实现完整，但 3 P0 review 问题未修复 |
| `pages/Diagnosis.tsx` | 1723 | 最大单文件，3 Critical + 3 High 契约断裂 |
| `pages/Dashboard.tsx` | 848 | 无专项 review |
| `pages/AutoTrade.tsx` | 734 | 1 Critical + 3 High 契约断裂 |
| `pages/DataUpdate.tsx` | 407 | 无专项 review |
| `pages/AuditLog.tsx` | 330 | 无专项 review |
| `pages/Trade.tsx` | 319 | 2 Blocker（实盘模块 review） |
| `pages/Strategy.tsx` | 317 | 无专项 review |
| `pages/Screener.tsx` | 202 | 基础实现 |
| `pages/Predictions.tsx` | 152 | 基础实现 |
| `pages/Signals.tsx` | 122 | 基础实现 |
| `pages/Backtest.tsx` | 51 | **空壳** — 仅占位 |
| `components/auth/*` | 274 | APPROVE WITH CHANGES |
| `components/trade/*` | 374 | APPROVE WITH CHANGES (2 Blocker) |
| `hooks/useLiveTrade.ts` | 228 | 含 2 Blocker |
| `api/client.ts` | 143 | 含诊断 API 契约修复（已部分修复 `analyze` signature） |
| `api/liveTrade.ts` | 55 | 路径不一致 |
| `contexts/AuthContext.tsx` | 184 | APPROVE WITH CHANGES |
| **总计** | **~8054** | |

### 二、Review 状态矩阵（按 2026-06-10 结论）

| Feature | Reviewer 结论 | Critical/Blocker | 修复进度 |
|---------|-------------|-------------------|---------|
| Auth/RBAC | APPROVE WITH CHANGES | 0 | 4 Warning + 3 Suggestion 未修复 |
| Model Training | **BLOCKED** | 4 (P0-P1) | 0/5 修复 |
| Auto Trading | **BLOCKED** | 1 Critical + 3 High | 0/7 修复 |
| Live Trading | APPROVE WITH CHANGES | 2 Blocker + 3 High | 0/5 修复 |
| Diagnosis | **BLOCKED** | 3 Critical + 3 High | 0/8 修复 |
| Backtest | 未 review | — | 51 行空壳 |
| Dashboard | 未 review | — | 848 行，待审查 |
| DataUpdate | 未 review | — | 待审查 |
| Screener/Predictions/Signals | 未 review | — | 基础实现，待审查 |

### 三、核心差距（按 feature）

#### 1. 模型训练 (Training + ModelRegistry) — BLOCKED

对照 `docs/design/model-training/frontend-plan.md` §10 AC 覆盖矩阵：

- AC-6.1 (手动触发训练): Training.tsx Modal 存在，前端逻辑正确
- AC-6.2 (自动训练调度): ScheduleConfig Tab 存在
- AC-6.3 (训练可视化): ECharts Loss 曲线 + 特征重要性存在
- AC-6.4 (自动评估 vs 旧模型): A/B 对比 Modal 存在
- AC-6.5 (一键上线): **BROKEN** — Rollback 缺 `target_version`，Deploy 缺 `notes`
- AC-6.6 (保留旧模型): **BROKEN** — Archive 端点不存在 (404)
- AC-6.7 (因子权重校准): 因子分析区存在，但 `loadFactors` 重复调用
- AC-6.8 (训练历史): 模型列表 + 详情 Drawer 基本完整
- AC-6.9 (admin only): 路由 roles: ['admin'] ✅

**未修复 P0**:
1. `ModelRegistry.tsx:281` — Rollback 缺 `target_version`（后端 422 Error）
2. `Training.tsx:534` — Cancel 端点 `/training/status/{id}/cancel` 不存在（404）
3. `ModelRegistry.tsx:300` — Archive 端点 `/training/models/{id}/archive` 不存在（404）
4. `ModelRegistry.tsx:264` — Deploy 应支持 `notes` 参数（P1）

#### 2. 量化交易 (AutoTrade + Strategy) — BLOCKED

对照 `docs/design/auto-trading/frontend-plan.md`：

- **Critical**: 所有 API 调用使用 `/api/v1/auto-trade/*` 路径，但后端路由在 `/api/v1/strategy/*`，且 vite.config.ts 无对应 proxy
- **High**: 请求体字段名完全不对应（`indicator` vs `field`, `rule_type` 数组 vs 对象）
- **High**: 状态值不匹配（`running/terminated/completed` vs `active/stopped/draft`）
- **High**: 表单缺失 `trade_mode`/`check_interval_sec`/`capital`/`picks`
- **Medium**: Log 条目字段名不匹配（`action`+`detail` vs `message`+`details`）

#### 3. 个股诊断 (Diagnosis) — BLOCKED

对照 ADR-005 + `docs/design/` 下的 API contract：

- **C1**: `analyze` 已修复为 JSON body（`client.ts:132-133`），但 `Diagnosis.tsx` 内部 TypeScript 类型仍与后端不兼容
- **C2**: `DiagnosisResult` 前端类型与后端 `DiagnosisReport` 是两套完全不同的数据模型
- **C3**: PDF URL 缺 `/diagnosis` 路径段
- **H1**: 历史记录 `data.records` vs 后端 `data.items`
- **H2**: `grade` 枚举值（`strong_buy` vs "A"/"B+"）
- **H3**: Mock fallback 在生产环境静默降级，掩蔽所有集成问题

#### 4. 实盘交易 (Trade + liveTrade components) — APPROVE WITH CHANGES

对照 `docs/design/live-trading/frontend-plan.md`：

- **B1**: `RiskCheckModal` 与后端 `RiskResult` 字段契约不匹配（`passed`/`block` vs `level`）
- **B2**: Paper 模式 POST 下单用 URL query params（安全 + 日志泄露风险）
- **H1**: 前后端大额阈值独立配置可能不一致
- **H2**: 市价单无条件触发大额确认（包括 100 股小额单）
- **H3**: 熔断文案"次日自动重置"与后端行为不符

#### 5. 回测分析 (Backtest.tsx) — 空壳

- 仅 51 行，无实际功能
- 无 `docs/design/` 下的独立 frontend-plan
- 无 Unit 测试，无 SIT 测试

### 四、设计与文档覆盖

| 设计文档 | 对应页面 | 实现对齐度 |
|---------|---------|-----------|
| `docs/design/auth-rbac/frontend-plan.md` | LoginPage, RegisterPage, ProtectedRoute, AuthContext | ~90% — 框架正确，细节 warning 待修 |
| `docs/design/model-training/frontend-plan.md` | Training.tsx, ModelRegistry.tsx | ~80% — 结构完整，4 个 P0 契约断裂 |
| `docs/design/auto-trading/frontend-plan.md` | AutoTrade.tsx, Strategy.tsx | ~50% — 结构存在，API 路径/字段全线不匹配 |
| `docs/design/live-trading/frontend-plan.md` | Trade.tsx + 4 trade components + useLiveTrade | ~70% — 组件质量好，2 Blocker 契约问题 |
| `docs/design/model-training/api-contract.md` | — | 前端未同步更新 |
| `docs/design/auto-trading/api-contract.md` | — | 前端未同步更新 |
| `docs/design/live-trading/api-contract.md` | — | 前端未同步更新 |

### 五、测试覆盖

| 层级 | 覆盖范围 | 状态 |
|------|---------|------|
| Unit tests | `AuthContext.test.tsx`, `ProtectedRoute.test.tsx` | 仅 2 个文件 |
| SIT tests | `tests/sit/auth-flow.test.tsx` | 仅 1 个文件 |
| Component tests | 无 | 缺失 |
| Page-level tests | 无 | 缺失 |

### 六、总体完成度评估

- **总页面数**: 14（含 LoginPage, RegisterPage）
- **有专项 review**: 10/14 (约 71%)
- **review 通过无 blocker**: 2/10 (Auth/RBAC, Live Trading) — 20%
- **review BLOCKED**: 4/10 (Model Training, Auto Trading, Diagnosis, Live Trading 的部分)
- **需修复总数**: 约 25 个问题（10 Critical/Blocker + 15 High/Medium/Low）
- **未审查**: 3 个页面（Backtest 空壳, Dashboard, DataUpdate）+ 3 个基础页面（Screener, Predictions, Signals）
- **测试债务**: 仅 2 Unit + 1 SIT 覆盖约 8000+ 行代码

**结论**: 前端代码骨架已搭建完毕（14 页面、4 功能模块），但前后端联调存在大量契约断裂。4 个受审查功能中 3 个处于 BLOCKED 状态，核心修复工作尚未开始。Backtest 页面仍为空壳。建议 product-lead 按优先级排序修复计划。
