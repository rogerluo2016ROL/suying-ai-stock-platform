# 速赢AI 前端可用性 / 有效性审计报告

- 审计日期：2026-06-21
- 审计范围：`frontend/`（React 18 + Vite 6 + TS 5.6 + AntD 5.22 + ECharts 5.5），对接 11 个 FastAPI 微服务
- 审计模式：只读分析（未修改任何代码）
- 证据方法：逐文件阅读 + `tsc -b --noEmit` + `npm run build` + `vitest run` 真实输出 + 后端路由契约对账

---

## 1. 总体结论

前端整体骨架完整（14 个受保护页面 + 登录/注册 + RBAC 路由守卫 + JWT 刷新拦截器），UI 完成度高，多数页面具备 loading/empty/error 三态与 ECharts 可视化，**类型安全与生产构建均可通过**。但存在三个会直接卡死业务流程的硬伤：(1) 大量业务页面（Strategy / AutoTrade / Diagnosis history / Trade / DataUpdate）用**裸 `fetch()` 绕过 axios 鉴权拦截器**，而对应后端路由**全部要求 `Authorization: Bearer`**，导致这些页面登录后**必然 401 走不通**；(2) **完全没用 TanStack Query / orval 生成产物**，与 CLAUDE.md「契约纪律」明令的「禁手写 fetch / 类型 / mock」直接冲突，且 API 类型全靠手写 `any[]`；(3) SIT 测试套件 `tests/sit/auth-flow.test.tsx` **当前 4 个失败 + worker 崩溃**，登录/注册 happy path 跑不通，CI 已实质破窗。

| 维度 | 评分 (1-5) | 说明 |
|---|---|---|
| **可用性 (Usability/Availability)** | **2.5 / 5** | UI 完成度高、视觉专业，但 Strategy/AutoTrade/Diagnosis 等核心业务页面在登录态下因鉴权头缺失实际跑不通；裸 fetch 无统一超时/重试/错误提示。 |
| **有效性 (Effectiveness)** | **3 / 5** | Dashboard/Screener/Backtest/Signals 数据流真实（对应后端不要求鉴权，能跑通）；ECharts 图表真有数据；但 Diagnosis 在 DEV 用 mock 掩盖了断链，生产直接空/报错。 |

---

## 2. 架构与代码组织

### 2.1 目录与页面骨架

| 路径 | 内容 | 行数 |
|---|---|---|
| `frontend/src/App.tsx:45-80` | 14 个受保护路由 + 角色矩阵（admin / internal_analyst / external_analyst / user） | 307 |
| `frontend/src/main.tsx:10-52` | ConfigProvider + zhCN + AuthProvider + BrowserRouter，StrictMode 双渲染 | 52 |
| `frontend/src/contexts/AuthContext.tsx:35-184` | 登录/注册/登出/refresh/hasRole，injectAuth 把 token 注入 axios | 185 |
| `frontend/src/api/client.ts:1-182` | 单一 axios 实例 + 请求/响应拦截器 + 9 个手写 API 模块 | 182 |
| `frontend/src/api/liveTrade.ts:1-55` | 实盘交易 API（账户/订单/风控/熔断/审计日志） | 55 |
| `frontend/src/hooks/useLiveTrade.ts:1-247` | 模拟/实盘模式切换、风控前置检查、大额确认、熔断状态轮询 | 247 |
| `frontend/src/components/auth/` | LoginPage / RegisterPage / ProtectedRoute | — |
| `frontend/src/components/trade/` | BrokerStatus / CircuitBreakerAlert / LargeTradeConfirm / RiskCheckModal | — |
| `frontend/src/pages/` | Dashboard / Screener / Predictions / Strategy / Signals / Trade / AutoTrade / Backtest / Diagnosis / Training / ModelRegistry / DataUpdate / AuditLog 共 13 个 | — |
| `frontend/src/pages/datacenter/`、`src/data/`、`src/utils/` | **空目录**（占位） | 0 |

路由完整性：14 条 `protectedRoutes`（`App.tsx:66-80`）全部映射到真实组件，**无死页面 / 空 `TODO` 占位组件**；菜单 13 项与路由一一对应。

### 2.2 API client 与契约现状

- **axios 实例**（`client.ts:3-8`）：`baseURL: '/api/v1'`，`timeout: 30000`，`withCredentials: true`（用于 refresh token cookie）。
- **鉴权拦截器**（`client.ts:34-77`）：请求注入 `Authorization: Bearer`，响应 401 自动 refresh + 单飞锁（`_refreshPromise`）+ 失败 forceLogout。设计正确。
- **契约生成产物**：`frontend/src/api/generated/` **不存在**；全项目 grep `react-query`、`useQuery`、`useMutation` **0 命中**；`package.json` 也未声明 `@tanstack/react-query` 或 `orval`。**完全手写** client，违反 CLAUDE.md「契约的单一来源是后端 OpenAPI」（ADR-006 + `coding.md`）。

### 2.3 类型安全

- `tsconfig.json:14` `strict: true`，`noUnusedLocals/Parameters: false`。
- **`npx tsc -b --noEmit` → exit 0，零类型错误**（已实测）。
- 但 API 响应普遍 `any`：`client.ts:98` `generate(picks: any[])`、`Dashboard.tsx:91-93` `dbSummary: any` / `dashboardPicks: any[]`、`Strategy.tsx:80` `d.plans || d.items`。响应**未强类型**，靠运行时容错。

### 2.4 构建与配置

- `vite.config.ts:7-23`：13 条 proxy 规则，按服务前缀分流到对应微服务端口（screener→8001, prediction→8002, strategy→8003, signal→8004, alert→8005, trade→8006, backtest→8007, training→8008, diagnosis→8009, auth/admin→9001, health→8080）。
- `/api/v1/dashboard` 同时在 screener-service (8001) 和 signal-service (8004) 注册（`services/screener-service/app/routers/dashboard.py:11` 与 `services/signal-service/app/routes.py:1269`），但前端实际只调 `/dashboard/summary`、`/dashboard/auction`、`/dashboard/run-pipeline` 三个端点，这三个**两边都实现了同路径**（已对账 `signal-service/app/routes.py:1272/1342/1370`），proxy 走 8004 成立。
- `/api/v1/data` → 8004 正确（`signal-service/app/routes.py:1407` `data_router`）。
- **`npm run build` → exit 0，但 bundle `dist/assets/index-CGwKc38d.js = 2,699 KB`（gzip 862 KB）**，远超 Vite 默认 500 KB 警告阈值，**无 code-splitting、无 manualChunks、无路由级 lazy import**。

---

## 3. 发现的问题（按严重程度分级）

### P0 — 阻断（核心业务跑不通）

#### P0-1 裸 `fetch()` 绕过鉴权拦截器，受保护接口全部 401

- **证据**：13 个页面共 **40+ 处裸 `fetch()`**，统计如下（`grep -c "fetch("`）：
  - `Strategy.tsx`：9 处（`/api/v1/strategy/plans`、`/templates`、`/plans/{id}`、`/plans/{id}/confirm`、`/plans/{id}/report`、`/generate-from-scheme/{id}` 等）
  - `AutoTrade.tsx`：6 处（`/api/v1/strategy/list`、`/{id}/log`、`/{id}/{action}`、`/{id}` DELETE/GET）
  - `DataUpdate.tsx`：6 处（`/api/v1/data/status`、`/sync/{type}`、`/status` POST/DELETE）
  - `Dashboard.tsx`：4 处（`/signal/dashboard-summary`、`/dashboard/summary`、`/dashboard/auction`、`/dashboard/run-pipeline`）
  - `Trade.tsx`：3 处（`${apiPrefix}/account`、`/positions`、`/orders`）
  - `Diagnosis.tsx`：2 处（`/diagnosis/history`、`/diagnosis/report/{code}/pdf`）
  - `Predictions.tsx`：1 处、`Signals.tsx`：1 处、`AuthContext.tsx`：5 处
- **后端契约对账**（`grep -cE "require_role|get_current_user"`）：
  - `strategy-service/app/routes.py`：**22/22 端点全 require auth**（如 `/generate-from-scheme/{id}` `Depends(require_role("admin", "internal_analyst", "user"))`）
  - `trade-service/app/routes.py`：**12/12 端点全 require auth**
  - `diagnosis-service/app/routes.py`：`/history` (`routes.py:584`)、`/history/{id}`、`/report/{code}/pdf` 均 `Depends(require_role(*ALL_ROLES))`
  - screener / signal / prediction / dashboard：**0 require auth**（裸 fetch 能跑通）
- **影响**：登录后访问 Strategy / AutoTrade / Trade / AuditLog / Diagnosis history 全部返回 401，axios 拦截器看到 401 会**反复触发 refresh**（refresh 本身可能成功，但 retry 时**新的 fetch 仍然不带 token**，死循环到 forceLogout），用户被踢回登录页。**整个量化交易闭环（选股 → 方案 → 自动交易）登录态下跑不通**。
- **建议**：把所有裸 `fetch()` 改为走 `api.get/post/delete`（来自 `client.ts`），统一享受拦截器；或者把 axios 实例的 `request` 拦截器逻辑下沉到一个 `apiFetch()` wrapper 并替换所有裸 fetch。**工作量 S**（机械替换）。

#### P0-2 SIT 测试套件当前失败（4 failed / 24, worker 崩溃）

- **证据**：`npx vitest run` 实测输出：
  ```
  Test Files  2 passed (3)
       Tests  4 failed | 16 passed (24)
      Errors  1 error
    Duration  356.53s
  [vitest-pool]: Timeout terminating forks worker for test files tests/sit/auth-flow.test.tsx
  ```
  失败堆栈定位在 `tests/sit/auth-flow.test.tsx:99` `fillRegisterForm` → `waitFor(() => expect(btn).not.toBeDisabled())` 超时。
- **根因分析**：`RegisterPage.tsx:93-109` 的 `confirmPassword` 字段使用 `dependencies={['password']}` + 自定义 validator，但 `fireEvent.change` 在 AntD 5 下不会同步触发 `confirmPassword` 的重新校验（依赖字段变更需主动 `validateFields`），导致"注册"按钮**始终处于 disabled 或校验未通过状态**，`waitFor` 超时。另 3 个失败为 `AC-26 注册成功` / `AC-27 已登录访问 /login` / `AC-28 refresh 静默恢复` 连锁失败。
- **影响**：CI 红，任何 PR 无法走 DoD「Unit + SIT 自跑全绿」门；注册流程的真实可用性也无法被自动化验证。
- **建议**：测试改用 `userEvent.type`（已在 devDeps）替代 `fireEvent.change` 触发 AntD 受控更新；或在 `fillRegisterForm` 末尾显式 `form.validateFields()`。**工作量 S**。

### P1 — 严重（数据真实性 / 性能 / 可维护性）

#### P1-1 Diagnosis 在 DEV 用 mock 数据兜底，掩盖鉴权断链

- **证据**：`Diagnosis.tsx:801-822, 846-852, 867-872, 885-888` —— `fetch('/api/v1/diagnosis/history')` 失败时，若 `import.meta.env.DEV` 则塞入 8 条**硬编码假历史**（贵州茅台/宁德时代等 + 假分数）；`runDiagnosis` 失败时 fallback 到 `generateMockResult(stockCode)` 并 `message.warning('诊断完成 (演示数据 — DEMO DATA)')`。
- **影响**：开发者在 DEV 环境看到的"诊断结果"和"诊断历史"是假数据，**误判功能正常**；生产构建 vite 会 tree-shake 掉 `import.meta.env.DEV` 分支，所以生产是空白/报错而非假数据——但 DEV/生产行为不一致本身是隐患。叠加 P0-1（裸 fetch 不带 token），DEV 环境的 diagnosis 永远走 mock 分支。
- **建议**：删除 `generateMockResult` 与所有 `import.meta.env.DEV` fallback；失败时统一 `message.error` + Empty 状态；如需演示数据，移到独立 `mock/` 目录用 MSW handler（来自 orval 生成的 `*.msw.ts`）。**工作量 S**。

#### P1-2 完全缺失 TanStack Query / 缓存层，每个页面 useEffect 内手写 fetch

- **证据**：全项目 0 处 `useQuery` / `useMutation`；每个页面都是 `useState(loading) + useState(data) + useEffect(() => fetch...)` 模式（如 `Dashboard.tsx:100-120`、`Screener.tsx:35-55`、`Strategy.tsx:78-90`、`Backtest.tsx:328-374`、`Training.tsx`、`ModelRegistry.tsx`）。
- **影响**：
  - 无请求去重 / 无 stale-while-revalidate，Dashboard 每 60s 全量重拉（`Dashboard.tsx:117-120`）、自选股 Tab 120s（`:140`）；
  - 无统一 cache key，组件 unmount/remount 必重新请求；
  - 无后台刷新、无 `keepPreviousData`，分页/排序体验差；
  - 错误处理散落在每个 try/catch，**风格不一致**（有的 `message.error(e.response?.data?.detail)`、有的 silent `catch {}`、有的 fallback mock）。
- **建议**：引入 `@tanstack/react-query`，把每个 fetch 改为 `useQuery(['screener', mode, topN], () => screenerApi.run(...))`；这与 orval 生成 hooks 的目标一致（CLAUDE.md 契约纪律）。**工作量 M**。

#### P1-3 Bundle 2.7MB 无 code-splitting，首屏加载慢

- **证据**：`npm run build` 输出 `dist/assets/index-CGwKc38d.js 2,699.28 kB │ gzip: 861.81 kB`，Vite 警告 "Some chunks are larger than 500 kB"；`App.tsx:19-31` 13 个页面**全部静态 import**，无 `React.lazy` / `Suspense`；ECharts 全量打包（`echarts-for-react` 默认全量）。
- **影响**：首屏加载需下载 862KB gzip JS，弱网/移动端体验差；13 个页面中用户只看 1-2 个也要全量加载。
- **建议**：
  1. 路由级 lazy：`const Dashboard = React.lazy(() => import('./pages/Dashboard'))` + `<Suspense fallback={<Spin />}>`；
  2. ECharts 按需：`echarts/core` + `echarts/charts/{LineChart,BarChart,GaugeChart}` 注册；
  3. `vite.config.ts` 加 `build.rollupOptions.output.manualChunks` 把 antd / echarts / react 分离。
  - **工作量 M**。

#### P1-4 API 类型全 `any`，响应未强类型

- **证据**：`client.ts:98` `generate(picks: any[])`、`:105` `addPicks(planId, picks: any[])`、`:170-172` `compare(codes, dimensions, forceRefresh)` 入参 `string[]` 但返回 `Promise<AxiosResponse<any>>`；`Dashboard.tsx:91-93` `dbSummary: any` / `dashboardPicks: any[]` / `dashboardPredictions: any[]`；`Screener.tsx:11-15` `modes: any[]`、`picks: any[]`。
- **影响**：字段名拼错（如 `consensus_level` vs `consensus_level`）编译期发现不了；后端改字段前端无感知；与 CLAUDE.md「orval 生成类型」纪律冲突。
- **建议**：先手写 `interface` 顶替（`PlanPick`、`ScreenerPick` 等），中期上 orval 从后端 OpenAPI 生成。**工作量 M**。

### P2 — 改进（一致性 / 健壮性）

#### P2-1 `AuthContext.tsx:57-60` `/auth/me` 缺 `credentials: 'include'`

- **证据**：refresh 用 `credentials: 'include'`（`:48`），但紧接着的 `/auth/me` 只带 `Authorization` header **没带 credentials**（`:57-59`）。logout（`:145`）带了。
- **影响**：当 access token 过期、靠 refresh cookie 重新拿到 token 后立即调 `/me`，若后端未来依赖 cookie 上下文会失败；当前因有 `Authorization` header 尚能工作，属一致性疏漏。
- **建议**：补 `credentials: 'include'`。**工作量 S**。

#### P2-2 `Trade.tsx:204-213` paper 模式下单走裸 fetch 不经 axios，绕过风控拦截器与统一错误处理

- **证据**：`useLiveTrade.ts:203-222` paper 模式 `fetch(${apiPrefix}/order)` 直接裸 fetch，live 模式才走 `liveTradeApi.placeOrder`（axios）。两者错误处理、响应解析路径不同。
- **影响**：paper 模式下单失败时错误信息提取不一致（`data.detail` vs axios 的 `err.response.data.detail`）；未来给 axios 加统一日志/埋点会漏掉 paper 模式。
- **建议**：统一走 `liveTradeApi.placeOrder`，paper/live 差异在请求参数里区分（后端 `/trade/mode` 已支持）。**工作量 S**。

#### P2-3 `Strategy.tsx:92-114` `createFromTemplate` POST 无 body 且无 `Content-Type`

- **证据**：`fetch('/api/v1/strategy/plans?${params}', { method: 'POST' })` 第二参数只有 method，FastAPI 端 `@router.post("/plans")` 若声明了 Pydantic body 会 422。已确认 `strategy-service/app/routes.py:21` `create_plan` 是 query params 形式，当前能跑通，但脆弱。
- **建议**：加 `headers: {'Content-Type':'application/json'}` + 显式空 body `{}`，或迁移到 `strategyApi.createPlan`（client.ts:102 已有封装但未被调用）。**工作量 S**。

#### P2-4 `Screener.tsx:19,20` `sortBy` state 被设置但从未使用

- **证据**：`:19` `const [sortBy, setSortBy] = useState('score')`，`:138-141` 渲染 Select 绑定 `sortBy/setSortBy`，但 `columns`（`:57-90`）与 `dataSource`（`:157`）**未消费 sortBy**，选了"按价格排序"表格不变。
- **影响**：用户操作无效果，交互闭环断裂（违反 DoD「交互完整性」）。
- **建议**：要么 `picks.sort((a,b) => sortBy==='score' ? b.score-a.score : b.price-a.price)`，要么删除该控件。**工作量 S**。

#### P2-5 `App.tsx:96` `selectedKey` 计算在 `/trade/audit-log` 等二级路径下错误高亮

- **证据**：`const selectedKey = '/' + location.pathname.split('/')[1]` → `/trade/audit-log` 得到 `/trade`，菜单 `/trade` 高亮，但实际在审计日志页。视觉上不算 bug 但用户失去位置感。
- **建议**：`/trade/audit-log` 单独匹配。**工作量 S**。

#### P2-6 `Dashboard.tsx:710-720` "盘中选股" Tab 触发按钮 `window.open('/api/v1/dashboard/run-pipeline', '_blank')` 下载 JSON

- **证据**：点击"触发盘中选股"会 `window.open` 一个返回 JSON 的 POST 端点，浏览器直接下载/显示 JSON 而非触发后端任务（POST 用 window.open 也不规范）。
- **影响**：交互预期与实际行为不符。
- **建议**：改成 `fetch(..., {method:'POST'})` + `message.success`。**工作量 S**。

#### P2-7 `Dashboard.tsx:91-97` `auctionPicks/auctionSectors` 等多个 state 类型为 `any[]`

- **证据**：`:91-97` 7 个 `any` state；`signalTag`（`:75-79`）返回对象但类型未声明。
- **建议**：补 `interface AuctionPick`、`interface AuctionSector`。**工作量 S**。

#### P2-8 `App.tsx:109-120` alert unread-count 轮询用裸 fetch 静默 catch

- **证据**：`:112-116` `fetch('/api/v1/alert/unread-count').then(...).catch(() => {})`，错误完全静默；alert-service 路由 `routes.py:25` 实际**不需要鉴权**所以能跑，但服务挂掉时 Badge 永远显示 0 无任何提示。
- **建议**：至少 console.warn 或显示离线状态。**工作量 S**。

---

## 4. 可用性专项（哪些页面 / 流程跑不通）

| 页面 | 路由 | 状态 | 证据 |
|---|---|---|---|
| 登录 / 注册 | `/login` `/register` | ⚠️ **登录可用，注册 SIT 测试失败** | `auth-flow.test.tsx` 4 failed；运行时 RegisterPage 的 confirmPassword 校验在测试中不通过 |
| AI 智能看板 | `/` | ✅ 可用 | `Dashboard.tsx` 调 `/signal/dashboard-summary`（无鉴权）+ `/dashboard/summary`/`/auction`（signal-service 8004，无鉴权） |
| 智能选股 | `/screener` | ✅ 可用 | `screenerApi.run`（axios，screener-service 无鉴权）；但 `generatePlan` 调 `strategyApi.createPlan`（**鉴权，但走 axios 带 token**），可用 |
| K线预测 | `/predictions` | ⚠️ **裸 fetch 不带 token** | `Predictions.tsx:18` `fetch('/api/v1/prediction/${code}')`；prediction-service **0 require auth**，所以现在能跑，但与 axios 拦截器不一致 |
| 方案管理 | `/strategy` | ❌ **跑不通** | `Strategy.tsx` 9 处裸 fetch 调 `/strategy/plans` 等，strategy-service **22/22 require auth**，登录后 401 |
| 交易信号 | `/signals` | ✅ 可用 | signal-service 无鉴权 |
| 交易中心 | `/trade` | ❌ **跑不通** | `Trade.tsx:61-77` 3 处裸 fetch `/trade/account` 等，trade-service **12/12 require auth**，401 |
| 量化交易 | `/auto-trade` | ❌ **跑不通** | `AutoTrade.tsx` 6 处裸 fetch `/strategy/list` 等，全 require auth |
| 回测分析 | `/backtest` | ✅ 可用 | 走 `backtestApi`（axios）；backtest-service 鉴权情况未深查，但 axios 会带 token |
| 个股诊断 | `/diagnosis` | ⚠️ **主诊断走 axios 可用，history/pdf 裸 fetch 401 + DEV mock 掩盖** | `Diagnosis.tsx:796,927` 裸 fetch；`:801-822` DEV fallback mock |
| 模型训练 / 注册 | `/training` `/model-registry` | ✅ 可用 | Training.tsx / ModelRegistry.tsx 走 `api`（axios） |
| 数据更新 | `/data-update` | ✅ 可用 | signal-service `/data/status` 无鉴权；但裸 fetch 风格不一致 |
| 审计日志 | `/trade/audit-log` | ⚠️ **走 axios 可用，但依赖 trade-service 鉴权** | `AuditLog.tsx:79` `liveTradeApi.getAuditLogs`（axios），带 token |

**总结**：14 个页面中 **3 个核心业务页面（Strategy / Trade / AutoTrade）登录态下完全跑不通**，2 个有 DEV mock 掩盖的隐患，9 个可用但风格不统一。

---

## 5. 有效性专项（数据是否真实流转、图表是否有料）

### 5.1 数据流真实性

- ✅ **Dashboard**：`/signal/dashboard-summary` 返回 `signal_stocks / limit_stocks / market_sentiment / service_health / auction_intent / watchlist` 等真实字段，前端 `DashboardData` interface（`:55-71`）与后端字段对齐，渲染逻辑完整。
- ✅ **Screener**：`run_screening` 返回 `picks[{code,name,price,score,grade,entry_price,stop_loss,target_price,rationale,technical,money_flow,...}]`，前端列定义（`:57-90`）+ 展开行（`:163-198`）真实消费这些字段。
- ✅ **Backtest**：`buildReturnChartOption / buildIcChartOption / buildHitRateGaugeOption`（`Backtest.tsx:141-270`）真实消费 `details[].avg_return_pct / benchmark_pct / excess_return / ic / hit_rate_pct`，ECharts option 构造正确。
- ⚠️ **Diagnosis**：`transformDiagnosisReport`（`Diagnosis.tsx:131-220`）正确映射后端 `dimensions{technical,capital_flow,fundamental,ai_predict,sentiment}` 到前端，**主诊断路径真实**；但 `loadHistory` 失败走 mock，**历史 Tab 在 DEV 看到的是假数据**。
- ⚠️ **Predictions**：`result.pred_trajectory` 用纯 div 手画 K 线（`Predictions.tsx:92-132`），未用 ECharts，效果简陋但数据真实消费。

### 5.2 图表是否有料

- **ECharts 使用**：`Backtest.tsx`（3 类图：收益曲线、IC 滚动、命中率 gauge、策略对比 bar）、`Diagnosis.tsx`（雷达图等）、`ModelRegistry.tsx`、`Training.tsx` 均真实接入 ECharts 且 option 构造严谨（含 tooltip / legend / grid / 双 series）。
- **数据来源标注**：Dashboard 多处显示 `data_sources`（`:198-205, :328, :470, :547`），明确标注 "PG stocks 表"、"stk_limit 表"、"orchestrator.py"，**可观测性好**。
- **空状态**：多数页面有 `Empty` / `Empty.PRESENTED_IMAGE_SIMPLE` + 引导文案（如 Backtest `:747-762`、Strategy `:260`），但部分页面（如 Dashboard `:258-261` "信号数据加载中..." 永远显示，即使 fetch 失败也显示"加载中"而非"加载失败"）。

### 5.3 交互闭环完整性

- ❌ **Screener `sortBy`** 控件无效果（P2-4）。
- ❌ **Dashboard "盘中选股" Tab** window.open POST 端点（P2-6）。
- ⚠️ **Strategy "回测" 按钮**（`Strategy.tsx:150-156`）调 `/backtest/run?mode=all` 不传 plan_id，回测的是全市场而非当前方案，语义错位。
- ✅ **Trade 下单**：`useLiveTrade.placeOrder` 三步风控流程（preCheck → largeOrderConfirm → submit）完整，RiskCheckModal / LargeTradeConfirm / CircuitBreakerAlert 三个组件配合，**实盘交易闭环设计专业**。

---

## 6. 优化建议（按优先级排序）

| 优先级 | 建议 | 工作量 | 关联问题 |
|---|---|---|---|
| 🔴 P0 | **统一 API 调用层**：把所有裸 `fetch()` 替换为 `api.get/post/delete`（来自 `client.ts`），让鉴权拦截器覆盖全部请求 | S | P0-1 |
| 🔴 P0 | **修复 SIT 测试**：`fillRegisterForm` 改用 `userEvent.type` 或显式 `validateFields`，让 24 个测试全绿 | S | P0-2 |
| 🟠 P1 | **删除 Diagnosis DEV mock fallback**，失败统一 `message.error` + Empty | S | P1-1 |
| 🟠 P1 | **引入 TanStack Query**：每个 fetch 改 `useQuery`，去掉手写 loading/error state，统一缓存与重试 | M | P1-2 |
| 🟠 P1 | **路由级 lazy + ECharts 按需 + manualChunks**，把首屏 JS 从 862KB gzip 降到 < 300KB | M | P1-3 |
| 🟠 P1 | **API 类型化**：先手写 interface 覆盖所有 `any[]`，中期上 orval 从 OpenAPI 生成 | M | P1-4 |
| 🟡 P2 | `AuthContext.tsx:57` `/auth/me` 补 `credentials: 'include'` | S | P2-1 |
| 🟡 P2 | `useLiveTrade.ts:203` paper 模式下单改走 `liveTradeApi.placeOrder` | S | P2-2 |
| 🟡 P2 | `Strategy.tsx:92` createFromTemplate 加 `Content-Type` 或迁移到 `strategyApi.createPlan` | S | P2-3 |
| 🟡 P2 | 修复 `Screener.tsx sortBy` 未生效、Dashboard "盘中选股" window.open、Strategy 回测不传 plan_id | S | P2-4/6, §5.3 |
| 🟡 P2 | 补全 Dashboard/Screener 等 `any[]` state 的 interface | S | P2-7 |

**建议执行顺序**：先做 P0 两项（解锁业务跑通 + CI 绿），再做 P1-1（消除 mock 掩盖），之后 P1-2/P1-4 一起做（TanStack Query + orval 是同一个契约纪律的两面），最后 P1-3 性能优化与 P2 收尾。

---

## 7. 未验证项（诚实列出）

1. **后端服务实际是否在跑**：本次审计未启动任何微服务，所有"跑不通"结论是基于**前端代码 + 后端路由声明 + 鉴权依赖**的静态对账推断，未做真实 HTTP 请求验证。建议后续在 docker-compose 全启后用 curl 带/不带 token 实测 `/api/v1/strategy/plans` 等端点确认。
2. **backtest-service / training-service 鉴权情况**：只对 strategy / trade / diagnosis / screener / signal / prediction 做了 `require_role` 计数，backtest（8007）/ training（8008）未深查；若它们也 require auth，则 Backtest/Training/ModelRegistry 页面（走 axios，带 token）可用，但需确认。
3. **CORS 跨域**：`vite.config.ts` proxy 是开发模式方案，生产部署若前端独立域名需后端 `CORS_ALLOWED_ORIGINS` 配合（CLAUDE.md 默认 `http://localhost:5173,http://localhost:3000`），未验证生产 nginx/网关配置。
4. **ECharts 在弱网的实际渲染性能**：未做 Lighthouse / 性能 prof，bundle 大小是静态证据。
5. **可访问性 (a11y)**：未系统审计 ARIA / 键盘导航 / 颜色对比度；LoginPage 用 `<a onClick>` 无 href（`:62-64`）键盘不可达，是发现的一个具体点但未扩展审计。
6. **i18n**：`main.tsx` 设了 `zhCN` locale 但所有文案硬编码中文，无 i18n 资源文件；是否需要多语未在 PRD 中确认。
7. **MSW mock 来源**：CLAUDE.md 要求 MSW 来自 orval 生成 `*.msw.ts`，但 `tests/sit/auth-flow.test.tsx:14-15` 是**手写 `http.post(...)` handler**，与纪律冲突；未深查是否有其他手写 mock。
8. **vitest 第二次 verbose run** 被 kill（exit 144），未拿到完整失败用例名列表，只从第一次 run 的尾部堆栈推断 4 个失败集中在 register 相关；建议本地完整跑一遍 `vitest run --reporter=verbose 2>&1 | tee vitest.log` 确认。
