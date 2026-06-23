---
reviewer: code-reviewer
code_verdict: approve with changes
sit_audit_verdict: N/A (read-only audit, no PR SIT evidence to audit)
critical_count: 4
warning_count: 11
suggestion_count: 9
feature: frontend-full-audit
date: 2026-06-22
---

# 速赢AI 前端代码审计报告

> 范围：`frontend/src/` 全量 30 个 `.ts/.tsx` 文件（约 9711 行）。read-only 审计，不改代码。
> 命令证据：`npx tsc --noEmit` 0 错误；`npx vite build` 成功（单 chunk 2698.80 kB / gzip 861.66 kB）。
> 严重度：P0=阻断功能/数据错误/安全漏洞；P1=功能缺陷/显著体验/类型堆积；P2=质量/可维护性/性能。

## §1 概览

| 维度 | 结果 |
|---|---|
| 扫描文件 | 30 个 `.ts/.tsx`（含 3 个测试文件） |
| `tsc --noEmit` | ✅ 0 错误 |
| `vite build` | ✅ 成功（⚠️ 单 chunk 2.7 MB，触发 chunk size 警告） |
| 依赖版本对 CLAUDE.md | ✅ React 18.3 / Vite 6 / TS 5.6 / Antd 5.22 / ECharts 5.5 / RR 6.28 全部对齐 |
| 问题总数 | **P0=4 / P1=11 / P2=9（共 24 条）** |
| ErrorBoundary | ❌ 全局 0 个（见 P1-08） |
| 代码分割 / 懒加载 | ❌ 0 处 `React.lazy`（见 P1-09） |
| 单元/SIT 测试覆盖 | ⚠️ 仅 3 个文件（AuthContext / ProtectedRoute / auth-flow SIT），业务页面 0 测试 |

## §2 问题清单

| 编号 | 标题 | 位置 file:line | 严重度 | 描述 | 修复建议 |
|---|---|---|---|---|---|
| P0-01 | 模拟盘下单绕过 axios 拦截器（无鉴权 / 无 401 刷新） | `src/hooks/useLiveTrade.ts:204-222` | P0 | `placeOrder` 在 `mode === 'paper'` 分支用裸 `fetch(${apiPrefix}/order)` 调 `/api/v1/trade/order`，**完全绕过** `client.ts` 的 axios 实例：不带 `Authorization: Bearer` 头、不触发 401 自动 refresh、`credentials: 'include'` 也未设置。后端若对 paper 下单也要求 JWT，该路径将直接 401 且无刷新机会；即便后端放行，也是鉴权口径不一致。 | 删除 paper/live 双分支，统一走 `liveTradeApi.placeOrder(...)`（已封装 axios）。如需区分 paper/live，加 query/body 字段让后端判断，不要在前端 fork 两套 HTTP 调用。 |
| P0-02 | LoginPage 在 render 体内调用 `navigate()`（副作用） | `src/components/auth/LoginPage.tsx:17-20` | P0 | `if (isAuthenticated) { navigate('/', { replace: true }); return null }` 写在函数组件渲染期间。React 严禁在 render 体内触发副作用——`navigate` 会触发状态更新，StrictMode 双调用下会引发 "Cannot update during render" 警告，且可能在并发渲染下被丢弃，导致已登录用户停在登录页。 | 改为 `useEffect(() => { if (isAuthenticated) navigate('/', { replace: true }) }, [isAuthenticated])`；render 期间返回 `null` 占位即可。 |
| P0-03 | `App.tsx` 未登录用户访问受保护路由直接落到登录页，丢失目标路由 + 重定向参数 | `src/App.tsx:141-149` 与 `src/components/auth/ProtectedRoute.tsx:25-28` | P0 | App 在 `!isAuthenticated` 时整块替换为 auth Routes（`<Route path="*" element={<LoginPage/>}/>`），**完全不走** `ProtectedRoute` 的 `?redirect=` 逻辑。用户从 `/backtest` 直接刷新 → 落到 `/login` 无 redirect 参数 → 登录后回不到原页。`ProtectedRoute` 里精心写的 `encodeURIComponent(redirect)` 形同虚设。 | 让 App 在未认证时也渲染 `protectedRoutes`（包 `ProtectedRoute`），由 `ProtectedRoute` 统一负责重定向到 `/login?redirect=...`；或 App 的 catch-all 显式带 `location.pathname` 跳 `/login?redirect=`。 |
| P0-04 | 熔断器轮询取 `r.data.breakers[0]`，但 broker/circuit-breaker 接口契约未在前端校验，且 `setCircuitBreaker(null)` 静默吞错 | `src/hooks/useLiveTrade.ts:123-138` | P0 | `.catch(() => setCircuitBreaker(null))` 把所有错误（含 401/403/500）都置空，UI 上熔断器告警消失，用户会以为"风控正常"。真实熔断状态下若网络抖动一次，告警直接消失，实盘下单可能撞穿熔断。 | 错误分级：网络错误保留上一次有效状态（不重置为 null），仅 404/明确"无熔断器"才置 null；UI 用 `circuitBreaker?.status` 判定时区分"未知"与"NORMAL"两种态。 |
| P1-01 | `any` 类型大面积滥用（≥30 处），削弱编译期保护 | `src/api/client.ts:98,105`；`src/pages/Diagnosis.tsx:119,536,540,905`；`src/pages/Dashboard.tsx:92-98,735,739,777`；`src/pages/Trade.tsx:40-42,84,93`；`src/pages/AuditLog.tsx:66,114,138,181,245`；`src/pages/Screener.tsx` 多处；`src/hooks/useLiveTrade.ts:35,60,162,179,229` | P1 | 后端响应、表单 values、Table record、catch err 几乎全是 `any`，IDE 无法提示字段名，重命名后端字段时前端不会报错。`api/client.ts` 里 `strategyApi.generate(picks: any[])`、`addPicks(planId, picks: any[])` 把核心入参也丢了类型。 | (1) 为每个后端响应定义 TS interface（Diagnosis 已部分做了 `DiagnosisReport`，照抄到 screener/trade/strategy）；(2) catch 改 `catch (e: unknown)` 后 `axios.isAxiosError(e)` 收窄；(3) Antd Table 用 `ColumnsType<T>` 泛型。 |
| P1-02 | 全局 0 个 `ErrorBoundary`，任何子组件抛错直接白屏 | `src/main.tsx` / `src/App.tsx` | P1 | React 18 默认会卸载整棵树。ECharts option 构造、Table render、JSON 解析任何一处抛错 → 全站白屏，只能刷新。 | 在 `App` 外层包一个 `<ErrorBoundary fallback={<Result status="500" extra={<Button onClick={reload}>刷新</Button>}>}>`；ECharts 容器再单独包一层。 |
| P1-03 | 零代码分割，首屏加载 2.7 MB JS（gzip 861 KB） | `src/App.tsx:19-31`（同步 import 14 个页面）+ `vite build` 输出 | P1 | 所有 14 个页面 + ECharts（约 1MB）全部打进 `index-BUkaTm6F.js`，首屏白屏时间显著。ECharts 只在 Diagnosis/Backtest/Training/ModelRegistry 4 页用，却强制全量加载。 | (1) 把 14 个页面用 `React.lazy(() => import(...))` + `<Suspense fallback={<Spin/>}>`；(2) `vite.config.ts` 加 `build.rollupOptions.output.manualChunks` 把 echarts / antd / vendor 拆 chunk；(3) 目标：首屏 < 300 KB gzip。 |
| P1-04 | `App.tsx` 的 alert 轮询用裸 `fetch` + `.then(r => r.json())`，非 JSON 响应会抛未捕获异常 | `src/App.tsx:111-116` | P1 | 30s 轮询 `/api/v1/alert/unread-count`，若网关 502 返回 HTML 错误页，`r.json()` 抛异常。虽然外层有 `.catch(() => {})` 兜住，但 (a) 走的是裸 fetch 不带 token，依赖 cookie 转发鉴权，与项目主链路（axios + 拦截器）口径不一致；(b) `alertApi` 里根本没有 `unread-count` 这个方法，契约散落。 | 把 `alertApi` 补 `getUnreadCount: () => api.get('/alert/unread-count')`，App 改用之，复用 401 拦截。 |
| P1-05 | `App.tsx` 的 `/settings` 菜单项点击无路由，Drawer 打开后所有 Switch/ Radio 都无 `onChange`（死控件） | `src/App.tsx:60-62,244-260` | P1 | 主题/弱色/多标签三个 Switch + Radio.Group 全是装饰件，无 state、无 onChange、无持久化，点击无效。"系统设置"菜单也只是把 `settingsOpen` 置 true，没有任何设置项。 | 要么删除 Drawer（避免误导），要么接 `ConfigProvider` 的 `theme.algorithm` 真做暗色切换 + localStorage 持久化。当前形态属"假交互"，违反前后端对接强制覆盖项 #2（控件无有效 handler）。 |
| P1-06 | `AuthContext.doRefresh` 在组件卸载后仍 `setAccessToken/setUser`（race） | `src/contexts/AuthContext.tsx:44-72,93-101` | P1 | mount effect 用 `cancelled` 标志守了 `setIsLoading`，但 `doRefresh` 内部的 `setAccessToken(token)` / `setUser(...)` 没守。快速切页面时 refresh 还在飞，组件已卸载 → React 18 警告 "Can't perform a state update on unmounted component"。 | `doRefresh` 接受 `signal`/`cancelled` 参数，或把 fetch 结果先存局部变量，`cancelled` 为真就不 setState。 |
| P1-07 | `Trade.tsx` 表单 `code` 字段无格式校验、无股票代码白名单，`direction` 无枚举约束 | `src/pages/Trade.tsx:276-290` | P1 | `code` 只 `required`，用户可输 `abc123`；`price` 允许 0（市价）但无提示；`volume` min=100 但不强制 100 的倍数（A股必须 100 股一手）。下单到实盘会触发后端 422 或更糟。 | code 加 `pattern: /^\d{6}$/`；volume 加 `validator` 校验 `% 100 === 0`；price=0 加 Tooltip "市价单"。 |
| P1-08 | `AuditLog.handleReset` 用 `setTimeout(() => fetchLogs(1, pageSize), 0)` 等 state 更新——反模式 | `src/pages/AuditLog.tsx:101-109` | P1 | 重置筛选用 `setTimeout(...,0)` 等 React state 异步刷新后再 fetch，时序脆弱（React 18 batching 下可能拿不到新值）。`fetchLogs` 的 `useCallback` 依赖里已含 `dateRange/actionType/...`，正确做法是把这些筛选条件做成 `useEffect` 依赖。 | 拆一个 `useEffect(() => fetchLogs(1, pageSize), [dateRange, actionType, stockCode, operator])`，`handleReset` 只 setState，自动触发 fetch，删 setTimeout。 |
| P1-09 | `Predictions.tsx` 的 K 线图用 200 行手写 div + 内联 style 画，而非 ECharts（项目已装 echarts-for-react） | `src/pages/Predictions.tsx:92-132` | P1 | 手写 div 拼蜡烛图，无坐标轴、无 tooltip、无缩放、无图例，30 根 K 线挤压在 `traj.length*22` px，移动端溢出。项目其他 4 个页面都用 `ReactECharts`，唯独此页重复造轮子且功能更弱。 | 改用 `ReactECharts option={buildCandlestickOption(result.pred_trajectory)}`，复用 Diagnosis 里现成的 K 线 option 构造函数。 |
| P1-10 | `Screener.tsx` sortBy state 定义了但完全没用（数据从不按它重排） | `src/pages/Screener.tsx:19,138-141` | P1 | UI 有"按评分/按价格排序"下拉，`sortBy` 存了值，但 `picks` 从不根据它 sort，`runScreening` 也不传给后端。用户切换排序无任何效果。 | 在 `useEffect([sortBy, picks])` 里 `[...picks].sort(...)`，或 render 时 `picks.sort(...)`（注意不可变）。 |
| P1-11 | `Dashboard.fetchDashboard` 用 `catch { /* silent */ }` 吞所有错误，失败态无任何 UI 反馈 | `src/pages/Dashboard.tsx:108` 等 10+ 处 `.catch(() => {})` | P1 | 后端挂掉时用户看到空白看板无任何提示，无法区分"无数据"与"加载失败"。全站普遍模式。 | 加 `error` state，catch 里 `setError(true)`，render 失败态给 `<Result status="warning" extra={<Button onClick={retry}>重试</Button>}>`。 |
| P2-01 | `useLiveTrade` 把 `trade_mode` 存 localStorage 但不加密、不校验合法值 | `src/hooks/useLiveTrade.ts:64-66,76-83` | P2 | `localStorage.getItem('trade_mode') as TradeMode` 直接强转，用户改 localStorage 为 `'foobar'` 会污染状态。虽不涉及敏感数据（mode 不是 secret），但缺白名单校验。 | 读取时 `const m = localStorage.getItem('trade_mode'); setModeState(m === 'live' \|\| m === 'paper' ? m : 'paper')`。 |
| P2-02 | `RiskConfig` / `CircuitBreakerState` 等接口字段全可选，但使用处直接 `circuitBreaker.daily_loss_pct` 不判空 | `src/hooks/useLiveTrade.ts:8-25` + `src/pages/Trade.tsx:179-188` | P2 | 类型宽松 + 使用处无 `?.`，TS 不报错但运行时若后端字段缺失会渲染 `undefined%`。 | 把后端契约字段设非可选（与 Pydantic 对齐），使用处用可选链兜底。 |
| P2-03 | 4 个 ECharts 页面无 `onEvents` 卸载，依赖 echarts-for-react 内部 dispose；但 option 每次渲染都是新对象，触发全量重绘 | `src/pages/Diagnosis.tsx:1030,1231,1429,1515`；`src/pages/Backtest.tsx:701,710,723,864` | P2 | option 构造函数（`buildKlinePredictionOption` 等）每次 render 重新生成新对象，ReactECharts 默认 `notMerge=false` 会做 diff 但仍可能频繁 setOption。大表 + 多图页面切 tab 时内存可能上涨。 | option 用 `useMemo(() => buildXxx(data), [data])`；图表容器加 `shouldComponentUpdate` 隔离。 |
| P2-04 | `main.tsx` 用 `React.StrictMode` 但业务代码多处依赖"mount 只跑一次"的副作用（AuthContext refresh、Diagnosis URL 自动诊断），StrictMode 双调用会触发两次 API | `src/main.tsx:11` + `src/contexts/AuthContext.tsx:93-101` + `src/pages/Diagnosis.tsx:717-724` | P2 | 开发环境 StrictMode 下 `doRefresh()` 会跑两次（两次 `/auth/refresh`），Diagnosis 的 `runDiagnosis(urlCode)` 也会跑两次（两次 `/diagnosis/analyze`）。生产无此问题但 dev 体验差 + 浪费 LLM token。 | 给这些 mount-only effect 加 ref 守卫：`const didInit = useRef(false); useEffect(() => { if (didInit.current) return; didInit.current = true; ... }, [])`。 |
| P2-05 | `App.tsx` Header 的"刷新"按钮（`<ReloadOutlined />`）`onClick` 完全没绑 | `src/App.tsx:221` | P2 | 死按钮，点击无反应。 | 绑 `onClick={() => window.location.reload()}` 或当前页的 refetch 函数（需通过 context 暴露）。 |
| P2-06 | `App.tsx` 的 "语言"/"GithubOutlined"/"GlobalOutlined" 等图标按钮均无 onClick + 无 title 无障碍属性 | `src/App.tsx:228,286-288` | P2 | 装饰按钮，点击无反应，违反"可交互控件须绑有效 handler"。 | 删除或补功能；至少加 `aria-label` / `title`。 |
| P2-07 | `Screener` 的"浏览策略市场"/"前往方案管理"/`RightOutlined` 等多个 `<Button type="link">` 无 onClick | `src/pages/Trade.tsx:227,242,304` | P2 | 同 P2-06，假交互按钮。 | 绑 `navigate('/strategy')` 等。 |
| P2-08 | `Diagnosis.tsx` 单文件 1559 行，超长组件（项目阈值 300 行的 5 倍） | `src/pages/Diagnosis.tsx` | P2 | 一个文件包含 5+ 个 ECharts option 构造、transformer、对比模态、历史 tab，难维护。 | 拆 `Diagnosis/` 目录：`transformers.ts` / `chartOptions.tsx` / `CompareModal.tsx` / `HistoryTab.tsx` / `index.tsx`。同理 Backtest(896) / Dashboard(843) / AutoTrade(838) / ModelRegistry(821) / Training(788) 都超 300 行。 |
| P2-09 | 业务页面 0 单元测试 / 0 组件测试 | `frontend/src/__tests__/` 仅 2 文件，`tests/sit/` 仅 1 文件 | P2 | 14 个业务页面（含涉及真实资金的 Trade/AutoTrade）无任何测试，重构即裸奔。 | 至少为 `useLiveTrade.placeOrder` 的 paper/live 分支、熔断器禁用逻辑、大额确认阈值补 vitest；Trade 下单表单补交互测试（RTL）。 |

## §3 修复优先级建议

### 批次 1：必修（P0，4 条）—— 合并前阻断
1. **P0-01** `useLiveTrade` paper 分支裸 fetch → 统一走 axios（**涉及实盘/模拟下单鉴权**，最高优先）
2. **P0-02** LoginPage render 内 navigate → 移到 useEffect
3. **P0-03** App 未登录路由替换丢失 redirect → 让 ProtectedRoute 统一负责重定向
4. **P0-04** 熔断器轮询 `.catch(() => setCircuitBreaker(null))` → 错误分级，不静默清空（**实盘风控**）

### 批次 2：建议修（P1，11 条）—— 下一迭代内
- **P1-02** ErrorBoundary（白屏兜底，1 小时工作量，收益巨大）
- **P1-03** 代码分割（首屏体积从 861 KB gzip 降到 ~300 KB）
- **P1-01** any 类型清理（分页面渐进推进，先 client.ts + Trade + AuditLog）
- **P1-04 / P1-05** App alert 轮询 + 假交互 Drawer
- **P1-06 / P1-07 / P1-08 / P1-10 / P1-11** 各页面局部缺陷
- **P1-09** Predictions K 线图改 ECharts

### 批次 3：可缓（P2，9 条）—— 技术债 backlog
- 代码质量：拆超长组件（P2-08）、StrictMode 双调用守卫（P2-04）、ECharts option memo（P2-03）
- 死按钮清理（P2-05 / P2-06 / P2-07）
- 类型与校验加固（P2-01 / P2-02）
- 测试补齐（P2-09，建议 Trade/AutoTrade 优先，涉及资金）

---

## agf-verdict

```yaml
code_verdict: approve with changes
critical_count: 4
warning_count: 11
suggestion_count: 9
verdict_derivation: |
  4 个 P0 中 3 个（P0-01 鉴权绕过、P0-02 render 副作用、P0-03 路由重定向丢失）
  直接破坏核心功能（下单 / 登录跳转），P0-04 涉及实盘风控静默失效；
  但 tsc 0 错误 + build 成功 + 现有代码可运行，未达 "block"（无法编译/启动）门槛。
  → approve with changes：合并前必须修 P0-01~P0-04，P1 进下一迭代。
sit_audit_verdict: N/A
sit_audit_reason: 本次为 read-only 全量审计，非针对某 PR 的 code review；
  无对应 task 的 progress/<role>.md SIT 证据段可 audit。
```
