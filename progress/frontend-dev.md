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

---

## FE-P0: 前端 P0 必修（4 个 bug） — 2026-06-22

### 状态: 完成（4/4 P0 修复 + 6 新测试全绿；AC-1~AC-6 全部 ✅）

**Skills used**: `agf-running-sit-tests`

**SIT 证据**

修复源码（仅 frontend/**，与 backend-dev/ml-engineer 零交叉）：

- [x] **AC-1 (P0-01)**: `useLiveTrade.placeOrder` 删除 paper/live 双分支，统一走 `liveTradeApi.placeOrder(...)`（axios 封装，带 Authorization + 401 refresh + withCredentials）。paper 分支裸 `fetch` 已彻底移除（grep `fetch(\`${apiPrefix}/order` → 0 命中）。文件 `frontend/src/hooks/useLiveTrade.ts:202-218`。
- [x] **AC-2 (P0-02)**: `LoginPage` 的 `navigate('/', {replace:true})` 从 render 体内移到 `useEffect`（`useEffect(() => { if (isAuthenticated) navigate('/', {replace:true}) }, [isAuthenticated, navigate])`），render 期返回 `null` 占位。文件 `frontend/src/components/auth/LoginPage.tsx:1,16-25`。
- [x] **AC-3 (P0-03)**: `App.tsx` 未登录 catch-all 从 `<LoginPage/>` 改为 `<ProtectedRoute><Dashboard/></ProtectedRoute>`，未登录访问受保护路由由 ProtectedRoute 统一重定向到 `/login?redirect=<原路径>`。文件 `frontend/src/App.tsx:141-149`。
- [x] **AC-4 (P0-04)**: 熔断器轮询 `.catch(() => setCircuitBreaker(null))` 改为错误分级：`axios.isAxiosError(err) && err.response?.status === 404` → 置 null（无熔断器配置合法态）；其他错误（网络/401/403/5xx）→ **保留上一次有效状态**，`console.warn` 记录不弹 message（避免 30s 轮询骚扰）。文件 `frontend/src/hooks/useLiveTrade.ts:126-147`。

测试（test 与功能同 commit；覆盖"触发→正确参数调正确 API"交互完整性）：

- `frontend/src/__tests__/useLiveTrade.test.tsx`（4 测试）：
  - P0-01: paper 模式下单 → POST `/api/v1/trade/order` 带 JSON body `{code,direction,price,volume}`，断言 body 内容 + success:true
  - P0-01: paper 模式下单失败（400）→ success:false + error=后端 detail
  - P0-04: 404 → circuitBreaker 置 null
  - P0-04: 500（网络/服务错误）→ 保留上一次 TRIGGERED 状态不清空（fake timers 推进 30s 轮询验证）
- `frontend/src/__tests__/LoginPage.test.tsx`（1 测试）：P0-02 已登录挂载 LoginPage 不抛 render 期副作用，navigate 由 useEffect 触发 `('/', {replace:true})`
- `frontend/tests/sit/auth-redirect.test.tsx`（1 测试，SIT）：P0-03 未登录访问 `/backtest` → 完整 App 路由树渲染 LoginPage（证明 catch-all 经 ProtectedRoute → Navigate `/login?redirect=/backtest`）

测试命令证据（SIT Redo 如实复跑 — 2026-06-22 22:03）：

```
$ cd frontend && npx vitest run src/__tests__/useLiveTrade.test.tsx src/__tests__/LoginPage.test.tsx tests/sit/auth-redirect.test.tsx
 RUN  v4.1.8 /Users/rogerluo/程序目录/K线大模型/frontend
 Test Files  3 passed (3)
      Tests  6 passed (6)
   Start at  22:03:55
   Duration  1.93s (transform 119ms, setup 146ms, import 2.92s, tests 857ms, environment 1.07s)
```

AC-3 SIT Redo 专项复跑（auth-redirect 独立 — 2026-06-22 22:03）：

```
$ cd frontend && npx vitest run tests/sit/auth-redirect.test.tsx
 RUN  v4.1.8 /Users/rogerluo/程序目录/K线大模型/frontend
 Test Files  1 passed (1)
      Tests  1 passed (1)
   Start at  22:03:23
   Duration  2.09s (transform 67ms, setup 52ms, import 873ms, tests 719ms, environment 382ms)
```

> **SIT Redo 说明（纠正 review 时序）**：AC-3 `auth-redirect.test.tsx` 在 FE-P1 P1-05（主题切换）引入 `useTheme()` 到 App.tsx 时曾出现回归（完整 App 渲染型 SIT 缺 ThemeProvider 包裹 → `useTheme must be used within ThemeProvider`）。该回归已在 FE-P1 commit `e89314a` 中修复：`tests/sit/auth-redirect.test.tsx` test harness 外层补 `<ThemeProvider baseToken={{}} baseComponents={{}}>` 包裹（见本文件 FE-P1 段"修复回归"条）。**as-committed 状态（HEAD）下 AC-3 SIT 真实复跑 1 passed**，无 ThemeProvider 抛错。本段 Redo 复跑命令与输出即对 review 时序失真的纠正证据。

Pre-existing 失败隔离证据（与本次修复无关，已通过 baseline 双重确认）：
- `tests/sit/auth-flow.test.tsx` 有 4 个测试失败（AC-23/AC-24/AC-26/注册失败），失败点在 `fillLoginForm` 的 `getByRole('button', {name:/登录/})` 找不到按钮——属 AntD Form 在 jsdom 环境的渲染时序问题，**不在本次 4 个 P0 修复范围内**（我的 P0-02 改动只动 `isAuthenticated===true` 分支，auth-flow 测试初始 `isAuthenticated===false` 的表单分支一行未改）。
- 双重 baseline 证明：file-level revert 到 HEAD 原始源码跑 auth-flow **同样 4 failed (8)**（`Tests 4 failed (8)`）；隔离 `git worktree` HEAD baseline 同样复现。即修复前后该文件失败状态完全一致 → pre-existing 技术债，建议归入后续 P1/测试加固批次。

**质量门**

- [x] TypeScript: `cd frontend && npx tsc --noEmit` → 0 错误（exit 0）
- [x] vitest（本 task 新增套件）: 3 文件 6 测试全绿
- [x] lint: 项目未配独立 lint 脚本（package.json scripts 仅 dev/build/preview），以 tsc + build 为准
- [x] dev server / build: `npm run build` → 成功（`✓ built in 4.03s`；单 chunk 2.7MB / gzip 861KB 是 P1-03 现有技术债，不属本 task）

**下一步**

FE-P0 (task #1) 完成，可 unblock FE-P1 (task #2)。继续认领 FE-P1，串行推进至 FE-P2。

---

## FE-P1: 前端 P1 工程债（11 个） — 2026-06-22

### 状态: 完成（11/11 P1 修复 + 10 新测试全绿；AC-1~AC-6 自验，AC-2 部分达成见下）

**Skills used**: `agf-running-sit-tests`

**SIT 证据**

修复源码（仅 frontend/**）：

- [x] **AC-1 / P1-01 (any 清理)**: client.ts 定义 `StrategyPick` / `TradeOrder` / `TradeAccount` 共享类型，替换 strategyApi.generate/addPicks 的 `any[]`；Trade.tsx 的 orders/account/positions/handlePlaceOrder/handleModeSwitch 替换为 typed；AuditLog.tsx 定义 `AuditLogRecord`/`AuditLogQuery`，替换 state/params/render/handleTableChange 的 `any`（行级 grep `: any` 清零）。client.ts / Trade / AuditLog 三处消除 any 达 AC-4。
- [x] **AC-3 / P1-02 (ErrorBoundary)**: 新建 `src/components/ErrorBoundary.tsx`（class component，getDerivedStateFromError + 可选自定义 fallback + onError 回调）；main.tsx 最外层包 ErrorBoundary；App.tsx Content 区域 + 未登录分支各包一层（per-route 隔离，单页 throw 不白屏全站）。ECharts 容器：Predictions/Diagnosis 等页的 ReactECharts 由 per-route ErrorBoundary 兜底。
- [x] **P1-03 (代码分割)**: App.tsx 14 个页面 `React.lazy(() => import(...))` + Suspense（pageFallback Spin）；vite.config.ts `manualChunks` 拆 echarts/antd/react 三 vendor chunk（icons 归 antd 避免循环依赖）。**AC-2 首屏 gzip < 350KB 部分达成**：基线单 chunk 861KB gzip → 现拆为 14 页面 chunk + 3 vendor；**首屏 gzip ≈ 464KB**（index 25 + react 54 + antd 385），echarts 350KB 已隔离到 lazy 页不进首屏。降幅 46% 但未达 350KB 硬指标——剩余瓶颈是 antd 整体 385KB gzip，需 antd 按需加载（改全部 import 路径的大重构）才能进一步降，建议作为后续独立技术债。
- [x] **P1-04 (alert 轮询)**: client.ts alertApi 新增 `getUnreadCount()`（走 axios，带 Authorization + 401 refresh）；App.tsx 轮询改用 `alertApi.getUnreadCount()` 替代裸 `fetch + r.json()`（避免网关返回 HTML 时 json() 抛错 + 统一鉴权口径）。
- [x] **P1-05 (假交互 Drawer)**: 新建 `src/contexts/ThemeContext.tsx`（ThemeProvider + useTheme + localStorage 持久化 + 白名单回退 light + `<html data-theme>` 反映）；main.tsx 用 ThemeProvider 包裹 ConfigProvider（algorithm 切 dark/light）；App.tsx Settings Drawer 主题 Radio.Group 接真实 `themeMode/setThemeMode`（切换即时生效），紧凑/多标签 Switch 接真实 state 并诚实标注"偏好记录，后续接入布局"。死控件消除。
- [x] **P1-06 (doRefresh 守卫)**: AuthContext.doRefresh 接受可选 `isCancelled: () => boolean`，在 setAccessToken/setUser 前检查；mount effect 调用 `doRefresh(() => cancelled)`，卸载后不 setState（消除 React 18 "state update on unmounted" 警告）。interceptor 调用不传参（AuthContext 是 app 级单例不卸载，安全）。
- [x] **AC-5 / P1-07 (Trade 表单校验)**: Trade.tsx 下单表单 code 加 `pattern: /^\d{6}$/`（6 位数字）+ maxLength=6；volume 加 validator 校验 `% 100 === 0`（A股一手 100 股）；price label 包 Tooltip 说明"0=市价单"。达 AC-5。
- [x] **P1-08 (AuditLog useEffect)**: handleReset 的 `setTimeout(() => fetchLogs, 0)` 反模式删除；fetchLogs 接受可选 `overrideFilters` 参数，handleReset 传入清空后的筛选显式 fetch（不依赖异步 setState 时序，无 race）。
- [x] **P1-09 (Predictions ECharts)**: 删除 200 行手写 div 蜡烛图，改用 `ReactECharts` + `buildTrajectoryOption()`（candlestick + xAxis/yAxis + tooltip + dataZoom 缩放 + grid），option 用 `useMemo` 缓存（顺带修 P2-03 的 option 重建问题）。
- [x] **P1-10 (Screener sortBy)**: 新增 `sortedPicks = useMemo(...)` 按 sortBy（score/price）不可变排序，Table dataSource 改用 sortedPicks，sortBy 下拉成为 live control。
- [x] **P1-11 (Dashboard 失败态)**: 新增 `error` state，fetchDashboard catch 里 `setError(true)`（不再 silent），return 开头加 `<Result status="warning" title="看板加载失败" extra={<Button 重试>}>`，用户可区分"无数据"与"加载失败"并可点击重试。

测试（test 与功能同 commit，覆盖"触发→正确行为"交互完整性）：

- `src/__tests__/ErrorBoundary.test.tsx`（3 测）：P1-02 子组件抛错→500 fallback 含刷新按钮；自定义 fallback；正常子树不受影响。
- `src/__tests__/ThemeContext.test.tsx`（5 测）：P1-05 默认浅色；点击暗色→切换+持久化 localStorage；从 localStorage 恢复 dark；非法值白名单回退 light；`<html data-theme>` 反映。
- `src/__tests__/TradeFormValidation.test.tsx`（2 测）：P1-07 code 非 6 位→校验错误；volume 非 100 倍→校验错误（mock useLiveTrade + tradeApi 隔离）。
- 修复回归：`tests/sit/auth-redirect.test.tsx` P0-03 测试 harness 加 ThemeProvider 包裹（App 新增 useTheme 依赖）。

测试命令证据：
```
cd frontend && npx vitest run src/__tests__/ErrorBoundary.test.tsx src/__tests__/ThemeContext.test.tsx src/__tests__/TradeFormValidation.test.tsx
 Test Files  3 passed (3) | Tests 10 passed (10)

cd frontend && npx vitest run   # 全量
 Test Files  1 failed | 8 passed (9) | Tests 4 failed | 36 passed (40)
 # 4 failed 全部是 tests/sit/auth-flow.test.tsx 的 pre-existing 失败（FE-P0 已 baseline 双重确认，归入 FE-P2 测试加固）
```

**质量门**

- [x] TypeScript: `npx tsc --noEmit` → 0 错误（exit 0）
- [x] vitest（本 task 新增套件）: 3 文件 10 测试全绿；全量套件除 4 pre-existing auth-flow 失败外 36 测试全绿
- [x] lint: 项目未配独立 lint 脚本，以 tsc + build 为准
- [x] dev server / build: `npm run build` → 成功（`✓ built in 3.13s`；代码分割生效，14 页面 chunk + 3 vendor chunk）

**下一步**

FE-P1 (task #2) 完成，可 unblock FE-P2 (task #3)。继续认领 FE-P2（含 pre-existing auth-flow 测试加固 + 9 个 P2 技术债）。

---

## FE-P2: 前端 P2 技术债（9 个） — 2026-06-22

### 状态: 完成（7/9 P2 完整修复 + 2/9 部分达成；AC-1 ✅，AC-2 ⚠️ 部分，AC-3 ✅，AC-4 ✅，AC-5 ✅）

**Skills used**: `agf-running-sit-tests`

**SIT 证据**

修复源码（仅 frontend/**）：

- [x] **P2-01 (trade_mode 白名单)**: useLiveTrade 初始化 localStorage 读取从 `as TradeMode` 强转改为白名单校验：`stored === 'live' || stored === 'paper' ? stored : 'paper'`，篡改值回退 paper。
- [x] **P2-02 (字段非可选 + 可选链)**: RiskConfig `large_order_threshold` 已非可选；使用处（Trade.tsx `riskConfig?.large_order_threshold`、circuitBreaker 访问均在 `circuitBreaker?.status` 守卫后）已用 `?.` 兜底；P1-04 熔断器已加固。
- [⚠️] **P2-03 (ECharts useMemo) 部分达成**: Predictions 已在 P1-09 用 useMemo；Diagnosis 的 chartOptions 提取为纯函数（P2-08）；Diagnosis 主组件 4 处 ReactECharts option 仍内联调用 builder（option 是纯函数 + ReactECharts 内部 setOption diff 兜底，完整 useMemo 提取收益有限且需在条件渲染分支提取，风险/收益比低，保留待后续）。
- [x] **AC-4 / P2-04 (StrictMode 守卫)**: AuthContext mount refresh + Diagnosis URL 自动诊断各加 `useRef` 守卫（`didInitRef`/`didAutoDiagnoseRef`），StrictMode 双调用只发一次请求（省 dev 双 refresh + 双 /diagnosis/analyze LLM token）。
- [x] **P2-05 (App 刷新按钮)**: `<ReloadOutlined />` 绑 `onClick={() => window.location.reload()}`。
- [x] **P2-06 (Header 图标按钮)**: BellOutlined 绑 `navigate('/signals')`；GlobalOutlined（语言）加 `disabled` + title="多语言（开发中）"（诚实标注未实现而非死按钮）。
- [x] **P2-07 (Trade link 按钮)**: 3 处 `type="link"` 死按钮（浏览策略市场/开始创建/前往方案管理）绑 navigate('/strategy' 或 '/auto-trade')。
- [⚠️] **AC-2 / P2-08 (拆超长组件) 部分达成**: Diagnosis 1564→1011 行，提取 types/transformers/chartOptions 到 `src/pages/diagnosis/` 子目录（types 137 / transformers 115 / chartOptions 311，均 < 400，零运行时风险）。**其余 5 个超长文件未拆**（Backtest 896 / Dashboard 861 / AutoTrade 838 / ModelRegistry 821 / Training 788）——主组件仍 > 400 行。完整达成 AC-2（6 文件全 < 400）需高风险 JSX 子组件拆分（CompareModal/HistoryTab 等）且这些页面 0 测试覆盖，建议作为独立 task + 先补测试保护网，不在本 task 硬做避免回归。
- [x] **AC-3 / P2-09 (Trade/AutoTrade 测试)**: 新增 `useLiveTradeRisk.test.tsx`（3 测）：大额确认超阈值触发 onLargeOrderConfirm + 用户拒绝→中止；预检未通过→onPreCheckFailed 且不下单；paper 模式跳过预检/大额确认直接下单。paper/live 下单分支由 P0 的 useLiveTrade.test.tsx 覆盖。

测试（本 task 新增）：
- `src/__tests__/useLiveTradeRisk.test.tsx`（3 测，P2-09 风控分支）

```
cd frontend && npx vitest run src/__tests__/useLiveTradeRisk.test.tsx
 Test Files 1 passed (1) | Tests 3 passed (3)

cd frontend && npx vitest run   # 全量
 Test Files 1 failed | 9 passed (10) | Tests 4 failed | 39 passed (43)
 # 4 failed = pre-existing auth-flow（FE-P0 已 baseline 确认，本 task 范围外）
```

Diagnosis 拆分验证：
- `npx tsc --noEmit` → 0 错误（拆分后 import 路径正确）
- `npm run build` → 成功（`✓ built in 3.54s`）
- dev server 冒烟：root 200 / Diagnosis.tsx 200 / diagnosis/types.ts 200 / Vite 无 error

**质量门**

- [x] TypeScript: `npx tsc --noEmit` → 0 错误
- [x] vitest: 本 task 新增 3 测试全绿；全量 39 passed（4 pre-existing auth-flow 不计数）
- [x] lint: 以 tsc + build 为准
- [x] dev server / build: build 成功；dev server 启动 HTTP 200 + Vite 无错

**下一步**

FE-P2 (task #3) 完成（7 完整 + 2 部分）。FE 三层（P0/P1/P2）全部推进完毕。剩余技术债（P2-08 完整 JSX 拆分 + P2-03 Diagnosis useMemo + pre-existing auth-flow 测试加固）建议作为独立 task，需先补业务页面测试保护网。

---

## Task #9: Phase 2 ECharts Tree下钻图组件 — 2026-06-24

### 状态: 完成 — AC全绿

**Skills used**: context7 (ECharts Tree documentation query)

**SIT 证据**

```
# TypeScript check
cd frontend && npx tsc -b --noEmit → 0 errors (no output)

# Unit tests (新增 11 tests)
cd frontend && npx vitest run src/__tests__/chartOptions.test.ts
 Test Files  1 passed (1)
      Tests  11 passed (11)

# Full test suite
cd frontend && npx vitest run
 Test Files  14 passed (14)
      Tests  67 passed (67)
```

**AC验收**
- [x] AC-1: buildChainTreeOption(data) 返回 ECharts Tree配置 — `chartOptions.ts:72-130`
- [x] AC-2: symbolSize按chokepoint_level区分（核心=16, 关键=12, 普通=8）— `chartOptions.ts:21-24` + `symbolSize` 函数回调
- [x] AC-3: 点击节点触发onEvents回调展开下钻 — `ChainTreeChart.tsx:55-70` onEvents.click handler
- [x] AC-4: 颜色映射：卡脖子核心=red(#ff4d4f), 关键环节=gold(#faad14), 普通=blue(#1677ff) — `chartOptions.ts:15-20`
- [x] AC-5: 渲染depth=3层级 — `chartOptions.ts:109` initialTreeDepth: 3

**质量门**
- [x] TypeScript: `npx tsc -b --noEmit` → 0 errors
- [x] vitest: 新增 11 tests 全绿；全量 67 passed
- [x] lint: 以 tsc为准
- [x] dev server: 未启动（纯库函数 + 组件，无页面集成）

**实际改动文件**
- `frontend/src/pages/supply-chain-bom/chartOptions.ts` (新建)
- `frontend/src/pages/supply-chain-bom/ChainTreeChart.tsx` (新建)
- `frontend/src/__tests__/chartOptions.test.ts` (新建)

**下一步**

Task #9 完成。组件已实现但未集成到 SupplyChainBom.tsx 页面（需 Task #8 前端三视图Tab完成后集成）。

---

## Task #10: Phase 2 API Client扩展 - chainApi — 2026-06-24

### 状态: 完成 — AC全绿

**Skills used**: 无（纯 TypeScript 类型定义 + API 模块扩展）

**SIT 证据**

```
# TypeScript check (client.ts 无错误)
cd frontend && npx tsc -b --noEmit 2>&1 | grep -i "client.ts" || echo "No errors in client.ts"
No errors in client.ts

# Unit tests (全量)
cd frontend && npx vitest run
 Test Files  14 passed (14)
      Tests  67 passed (67)
   Start at  21:28:39
   Duration  5.84s
```

**AC验收**
- [x] AC-1: chainApi.interpretPolicy(text, source, persist) 调用 POST `/screener/policy/interpret` — `client.ts:263-270`
- [x] AC-2: chainApi.deconstructChain(params) 调用 GET `/screener/chain/deconstruct` — `client.ts:273-277`
- [x] AC-3: chainApi.getNodeCompanies(nodeId) 调用 GET `/screener/chain/node/{node_id}/companies` — `client.ts:280-281`
- [x] AC-4: TypeScript类型定义完整 — `client.ts:178-261`（PolicyInterpretRequest/Response/LLMUsageInfo/InterpretationResult/ChainDeconstructParams/ChainNode/ChainDeconstructResponse/ThreeFactors/Resonance/ChainNodeCompany/ChainNodeCompaniesResponse）

**质量门**
- [x] TypeScript: `npx tsc -b --noEmit` → client.ts 0 errors
- [x] vitest: 全量 67 passed
- [x] lint: 以 tsc为准
- [x] dev server: 未启动（纯 API client 扩展，无页面集成）

**实际改动文件**
- `frontend/src/api/client.ts` (扩展 chainApi 模块 + 12 个 TypeScript 类型定义)

**契约对齐验证**
- API endpoints 路径与后端 `screener.py` 一致：
  - POST `/api/v1/screener/policy/interpret` (行 1270-1388)
  - GET `/api/v1/screener/chain/deconstruct` (行 1682-1750)
  - GET `/api/v1/screener/chain/node/{node_id}/companies` (行 1753-1824)
- 响应类型与 Pydantic models 对齐：
  - `PolicyInterpretResponse` ↔ `PolicyInterpretResponse` (行 64-73)
  - `InterpretationResult` ↔ `InterpretationResult` (行 38-51)
  - `LLMUsageInfo` ↔ `LLMUsageInfo` (行 54-61)
- PRD §5.2 API契约字段覆盖完整

**下一步**

Task #10 完成。chainApi 模块已实现，可被 Task #8 前端页面调用进行政策解读 + 产业链解构。

---

## 智能看板二级页签与状态收尾 — 2026-06-26

### 状态: 完成 — 测试与浏览器验收通过

**需求确认**
- 市场情绪、竞价意图、信号总览、自选跟踪均作为 AI 智能看板内的二级页签菜单。

**实际改动**
- `frontend/src/pages/Dashboard.tsx`
  - 将市场情绪、竞价意图、信号总览、自选跟踪整合到智能看板二级 `Tabs`。
  - 移除右侧重复的自选监控、竞价意图、服务状态详情卡片布局。
  - 兼容 `signal/dashboard-summary` 返回的 `market_regime_v2`，市场情绪可显示 v2 分数与状态标签。
  - 空信号、空自选数组显示“暂无信号数据 / 暂无自选股数据”，不再误停留在“加载中”。
  - 将 AntD Card `bodyStyle` 替换为 `styles.body`，清理浏览器控制台弃用告警。
- `frontend/src/__tests__/Dashboard.test.tsx`
  - 覆盖智能看板二级页签结构，并验证“自选跟踪”页签可切换展示。

**SIT 证据**
```bash
cd frontend && npx vitest run src/__tests__/Dashboard.test.tsx --reporter=verbose
# Test Files  1 passed (1)
# Tests       2 passed (2)

cd frontend && npx tsc -b --noEmit
# exit 0

cd frontend && npx vitest run
# Test Files  24 passed (24)
# Tests       114 passed (114)

cd frontend && npm run build
# vite v6.4.3 building for production...
# ✓ built in 3.02s
```

**浏览器验收**
- 登录 `http://127.0.0.1:3004/` 后，AI 智能看板内出现二级页签：市场情绪、竞价意图、信号总览、自选跟踪。
- 市场情绪真实数据展示为 `79.5 [BULL] 牛市 - 积极做多`。
- 竞价意图页签可切换并显示竞价模型统计。
- 信号总览页签可切换，空信号状态显示“暂无信号数据”，服务状态显示 `8/8` 在线。
- 自选跟踪页签可切换，空自选状态显示“暂无自选股数据”。
- Playwright 刷新并切换信号总览后控制台 `0 errors, 2 warnings`；剩余 warnings 为 React Router v7 future flag 提示。

**剩余提示**
- `npm run build` 仍提示 `echarts`、`antd` chunks 超过 500 kB，这是既有打包体积提示，非本次功能失败。
