## T-204: auto-trading frontend 修复 - 2026-06-12 16:30
**状态**: 已完成
**Skills**: agf-running-sit-tests

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:
- [x] AC-204.1 ✅ API path: 全部 `/api/v1/strategy/*`，vite.config.ts proxy 已覆盖 strategy→8003
- [x] AC-204.2 ✅ request body 字段对齐: Condition(field/operator/threshold/description)，position_rules 嵌套，risk_rules 嵌套对象
- [x] AC-204.3 ✅ status enum: running→active, terminated→stopped, completed→archived, 追加 draft/archived
- [x] AC-204.4 ✅ form 补充: trade_mode(paper/live), check_interval_sec, capital, picks + Form.List
- [x] AC-204.5 ✅ log 字段: action→message, detail→details, time→timestamp
- [x] AC-204.6 ✅ npx tsc -b --noEmit: 0 errors
- [x] AC-204.7 ✅ npm run build: success (3681 modules, 3.28s)

**质量门**: lint ✅ / typecheck ✅ / build ✅ / SIT ✅（all AC pass）

**下一步**: 等待 product-lead review / 无阻塞

---

## BatchA-Dashboard: 落地 1.1 sentiment + 1.3 signal-overview - 2026-07-02 23:50
**状态**: 已完成
**Skills**: agf-running-sit-tests
**实例**: frontend-dev-1（worktree `.wolf/worktrees/frontend-dev-1b`，分支 `feat/md-ui-dashboard-dev1b`）
**改动文件**:
- `frontend/src/pages/Dashboard.tsx`（独占，per-file 改动）
- `frontend/tests/sit/dashboard-preview.test.tsx`（新增 SIT）

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:

- [x] AC① 1.1 sentiment 逐区块比对（情绪仪表盘/八维分解/市场快照/资金全景/AI解读/历史情绪/板块共振）✅ Dashboard.tsx 已含全部 7 区块；历史子页 4 MetricCard 占位（当前分位/情绪斜率/回撤风险/历史相似）走 fallback 文案不空白
- [x] AC② AI解读补 3 支撑原因（backend 字段未齐用 fallback_reason）✅ 新增 `buildSentimentReasons()` 从真实 market_sentiment/八维/市场快照派生 3 条支撑原因（趋势/资金/赚钱效应），缺字段标 `· 待补齐` + fallback_reason 文案，**不空白**（替换原 `dimensions.slice(0,3)` 裸维度切片）
- [x] AC③ 资金全景缺实时字段用 EmptyState+fallback_reason（不要空白）✅ 资金全景卡从纯 `prototype-fallback` 文本升级为 4 分项占位（北向/主力/融资/两市成交，均 `--`）+ `prototype-empty-state` 结构化空状态含 `fallback_reason` 文案
- [x] AC④ 内联 style token 化（~20 处）✅ ECharts 配置色（buildGaugeOption/buildTrendOption/buildSignalTrendOption/buildSignalBubbleOption）+ signalLevelMeta + fallbackDimensions tone + sectorColor 全部读 `lightTokens.*` 常量；A股红涨绿跌走 `.up/.down` className（未改 token 语义）；动态值(width/flex)留 inline
- [x] AC⑤ 保持浅色 ✅ 全程用 `lightTokens`（用户决策），未引入 dark-only 硬编码；gauge 5-stop 语义渐变（绿→蓝→橙→红）与 preview 1.1 一致
- [x] AC⑥ 契约走生成产物（无手写 fetch/类型/mock）✅ Dashboard 仅 import `signalApi`（orval 生成 client），SIT mock 走 `vi.mock('../api/client')` 与既有 Dashboard.test.tsx 同源
- [x] AC⑦ 交互完整性 ✅ 筛选条 5 按钮（全部/买入/卖出/拐点/自选）均绑 `setSignalFilter`；子页 tab 切换绑 `setSentimentPage`；板块格/Top5 卡片绑选中 + Drawer

**质量门**（vitest / tsc / build / dev server 四项）:
```
$ cd frontend && npx tsc -b --noEmit                         # exit 0，0 errors
$ npx vitest run src/__tests__/Dashboard.test.tsx tests/sit/dashboard-preview.test.tsx
  Test Files  2 passed (2) | Tests 17 passed (17)   # 11 unit（含新增 fallback_reason 用例）+ 6 SIT
$ npx vitest run src/__tests__/PrototypeFidelityGuard.test.ts # 1 passed（修订 fallback 文案避开 "接入后展示" 黑词后未回归）
$ npm run build   # ✓ built（Dashboard chunk 正常）
$ openwolf designqc --url http://localhost:3000 --routes / /dashboard/signals
  → / 渲染登录页（ProtectedRoute 守卫，backend auth 9001 未启无法登录看 Dashboard 内页；
    登录页浅色 token 系统正常）。Dashboard 内页区块/空状态由 SIT+unit 覆盖。
```

**本实例（frontend-dev-1b 重启）实际改动**（在 HEAD 5c71087a 已 token 化基础上收口）:
- `frontend/src/pages/Dashboard.tsx`：① 新增 `EmptyState` import；② 历史情绪子页 4 MetricCard 占位从 `-`/通用文案升级为显式 `fallback_reason` sub（补齐后展示…）；③ 历史相似场景 / 周期状态表 2 卡从裸 `prototype-fallback` 文本升级为结构化 `EmptyState`（title+detail）。其余 7 区块 + 八维分解 + 资金全景 + AI 解读 3 支撑原因（`buildSentimentReasons`）+ token 化均在 HEAD 已就绪。
- `frontend/src/__tests__/Dashboard.test.tsx`：+1 用例「history 页 4 占位 + 2 EmptyState 显式 fallback_reason，缺数据不空白」。
- `frontend/tests/sit/dashboard-preview.test.tsx`：采编前任 frontend-dev-1 未提交的 SIT 用例（1.1 ×4 + 1.3 ×2，覆盖区块渲染 + signalApi 契约调用 + 筛选交互）。

**已知 pre-existing 失败（非本任务范围，临界区未擅改）**：`src/__tests__/PrototypeRoutes.test.tsx` 全量跑报 `No "marketApi" export is defined on the "../api/client" mock`——`App.tsx:19,391` 引用 `marketApi`，但该测试 `vi.mock('../api/client')` 未导出。根因在 `App.tsx` + `api/client.ts`（临界区），非 Dashboard 改动引入（`git diff --name-only` 仅 Dashboard 相关 3 文件）。已 SendMessage team-lead 知会，不在本任务擅改。

**worktree 纪律自检**: 本实例先 `git worktree list` 自识别（cwd 默认落在 frontend-dev-5 的隔离区是错配），全部 Edit/Write 用 worktree 绝对路径 `.wolf/worktrees/frontend-dev-1b/...`；主仓 Dashboard.tsx 误改后已 `git checkout --` 还原至 HEAD 干净（md5 3b30b91...）。临界区（styles/*、api/client.ts、components/prototype/*）**未触碰**——所有用到的 CSS 类（gauge-panel/snapshot-grid/signal-matrix/ai-sentiment-card 等）已在 suying-app.css 就绪。

**下一步**: 等待 product-lead review / 无阻塞

---

## BatchA-OpenDecision: 落地 2.1 decision-overview + 2.4 candidate-pool - 2026-07-03 00:36
**状态**: 已完成
**Skills**: agf-running-sit-tests
**实例**: frontend-dev-1b（worktree `.wolf/worktrees/frontend-dev-1b-opendecision`，分支 `feat/md-ui-opendecision-dev1b`，基于 HEAD 48d47535）
**改动文件**:
- `frontend/src/pages/OpenDecision.tsx`（独占）
- `frontend/src/__tests__/OpenDecision.test.tsx`（+3 AC 用例 + screenerApi mock）
- `frontend/tests/sit/opendecision-preview.test.tsx`（新增 SIT，2.1 ×3 + 2.4 ×3）

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:

- [x] AC① 2.1 决策概览区块对齐 preview ✅ `DecisionOverview` 已含 6 区块（情绪指数 KPI / 隔夜新闻 / 昨日复盘 / 候选池预加载 / 今日情绪+风控 / 实时板块共振）逐区块比对 2.1 preview 对齐；countdown + footer-bar 同步 preview 文案
- [x] AC② 2.4 候选池消费 screenerApi.queryCandidatePool（scope 不走明文，契约 §9.3）✅ 并行 fetch 新增 `screenerApi.queryCandidatePool({ source_module: 'open-decision', page: 1, page_size: 50 })`（**入参不含 scope/tenant/owner/trade_account**，scope 由后端拦截器头 X-Tenant/Owner/Trade-Account 注入）；返回 records 经 `candidateRowsFromPool()` 摊平为 CandidateRow，与 chain 候选多源融合按 code 去重；SIT 断言入参 shape + 不含 scope
- [x] AC③ AI 解读 3 支撑原因（缺字段显式 fallback_reason）✅ `DecisionOverview` 今日情绪+风控卡新增 `ai-sentiment-card`：`buildAiSentimentReasons()` 从 signal/live 平均评分 + 板块共振 + 强信号/候选数派生 3 条支撑原因（情绪趋势 / 资金面 / 信号-候选共振），缺字段标 `· 待补齐` + 显式 `fallback_reason` 文案（如"signal/live 未返回有效评分…待实时信号补齐"），**不空白**
- [x] AC④ 内联 style 全 token 化（吸取第一波 W-1）✅ OpenDecision.tsx 全文**零裸 #hex**（grep 实证）；语义色走 `.up/.down/.warn/.neu/.t-up/.t-down/.t-warn/.t-mute` className（A 股红涨绿跌）；动态值（bar width%）留 inline 是 M0 契约允许；ECharts 无（本页无图表）；未引入新 signal 语义色 token（无需排队改 tokens.ts）
- [x] AC⑤ tsc 0 错 ✅ `npx tsc -b --noEmit` exit 0
- [x] AC⑥ vitest 含新增 OpenDecision 用例 ✅ OpenDecision.test.tsx 18 passed（15 原有 + 3 新增：候选池消费 queryCandidatePool / 空池 EmptyState+empty_state.reason / AI 解读 3 支撑原因）
- [x] AC⑦ 新增 tests/sit/opendecision-preview.test.tsx ✅ 6 passed（2.1 ×3：多源契约+区块渲染 / AI 3 支撑原因 / token 化 className；2.4 ×3：queryCandidatePool 入参不含 scope / 多源融合去重 / 空池 EmptyState）
- [x] AC⑧ 缺数据不空白 ✅ 候选池空走 `EmptyState`（title=候选池暂无数据 + detail=后端 `empty_state.reason` 或 fallback_reason 文案）；AI 解读每条缺字段显式 fallback_reason；隔夜新闻/昨日复盘/板块共振均有 prototype-panel-note 占位

**质量门**（vitest / tsc / build / dev server 四项）:
```
$ cd frontend && npx tsc -b --noEmit                        # exit 0，0 errors
$ npx vitest run src/__tests__/OpenDecision.test.tsx tests/sit/opendecision-preview.test.tsx
  Test Files  2 passed (2) | Tests 24 passed (24)   # 18 unit（15 原有+3 新增）+ 6 SIT
$ npx vitest run src/__tests__/PrototypeFidelityGuard.test.ts # 1 passed（"AI 开盘解读"/"待补齐" 不在 forbiddenPrototypeCopy 黑名单）
```

**契约纪律自检**: 候选池消费走 `screenerApi.queryCandidatePool`（orval 生成 client，类型 `CandidatePoolQueryResponse`/`CandidatePoolRecord`/`CandidatePoolCandidate` 由 types.ts 生成）；scope 不走明文入参（契约 §9.3，前端只透传 source_module/page/page_size）；无手写 fetch / 手写类型 / 手写 MSW handler。

**worktree 纪律自检**: 独立 worktree `frontend-dev-1b-opendecision` 基于 48d47535；独占 OpenDecision.tsx；临界区（api/client.ts / api/types.ts / components/prototype/index.ts / styles/* / tokens.ts）**未触碰**——`queryCandidatePool` / `CandidatePoolQueryResponse` 等均在 HEAD 已就绪，仅 import 消费；OpenDecision.test.tsx mock 补 `screenerApi` export 避免 PrototypeRoutes 同款 "No export defined" 坑；per-file git add（禁 stash/add -A）。

**下一步**: 等待 product-lead review / 无阻塞

---

## Task #24 — BatchC-Predictions: 5.1 single-stock + 5.2 multi-compare + 5.3 backtest（2026-07-03）

**状态**: ✅ 完成（已 commit），待 product-lead review

**Skills**: agf-running-sit-tests（dev-owned SIT 自跑）

**SIT 证据**

worktree: `.wolf/worktrees/frontend-dev-1b-predc`（分支 `feat/md-ui-predictions-batchc-dev1b`，基于 HEAD 1afa2163）。独占 `Predictions.tsx`。

- ✅ AC① (integration) 5.1 single：点击「开始预测」→ `predictionApi.predict('300750', 30)` → 渲染 30 日 K线路径图（含 ±1σ 置信带）+ 信号一致性 + 因子贡献专属卡片。SIT 断言：
  ```
  fireEvent.click(screen.getByRole('button', { name: '开始预测' }))
  await waitFor(() => expect(predictionApi.predict).toHaveBeenCalledWith('300750', 30))
  expect((await screen.findAllByTestId('mock-chart')).length).toBeGreaterThanOrEqual(1)
  expect(screen.getByText('信号一致性')).toBeInTheDocument()
  ```
- ✅ AC② (integration) 5.2 compare：点击「运行对比」→ `predictionApi.compare(['300750','000001','002594'], 20)` → 渲染对比矩阵（新增置信度列）+ 叠加预测曲线（归一化涨跌幅%）。SIT 断言 `compare` 入参与置信度列/叠加曲线卡片渲染。
- ✅ AC③ (integration) 5.3 backtest：进入即调 `predictionApi.getAccuracyBacktest()` → 预测 vs 实际走势 / 最近命中序列均走 EmptyState（后端逐日/逐次字段未齐，**不展示假图**）；4 项统计（方向正确率/平均误差/最大误差/最长连对）后 3 项字段未齐 → '--' + fallback_reason。
- ✅ AC④ 三 sub-tab 专属渲染（非通用壳）：single（信号一致性/因子贡献）、compare（叠加预测曲线）、backtest（最近命中序列/预测vs实际）各有专属区块，切换 tab 各自渲染。
- ✅ AC⑤ 全 token 化（W-1）：`grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' src/pages/Predictions.tsx` → **ZERO bare hex/rgba**。ECharts 透明叠层走 `alpha.accent/up/down(a)`，实心色走 `lightTokens.up/down/accent/fg/fg2/muted/border`；语义色走 `.up/.down/.t-mute` className。动态值（height/width/fontWeight）保留 inline。
- ✅ AC⑥ tsc 0 错：`npx tsc -b --noEmit` → 0 errors。
- ✅ AC⑦ vitest：`Predictions.test.tsx` 11 passed（7 既有 + 4 新增 AC 用例）；新增 `tests/sit/predictions-subtabs-preview.test.tsx` 4 passed。
- ✅ AC⑧ 缺数据不空白：single 三卡片（信号一致性/因子贡献/辅助特征）+ compare 空结果 + backtest（预测vs实际/命中序列/3 档误差统计）全部走 `EmptyState` + `fallback_reason` 文案，**无空 handler / 无 TODO / 无 console.log 占位**。
- ✅ DoD dev server：`npm run dev`（vite v6.4.3，port 3002 因 3000/3001 被占）→ `/` 200 + title「速赢AI」；`/predictions/single|compare|backtest` 三路由均 200。

**质量门**
```
npx tsc -b --noEmit                                     # 0 errors
npx vitest run src/__tests__/Predictions.test.tsx       # 11 passed（含 4 新增 AC）
npx vitest run tests/sit/                               # 41 passed（8 files，含新增 predictions-subtabs-preview 4）
npx vitest run src/__tests__/PrototypeFidelityGuard.test.ts  # 1 passed（fallback 文案不在黑名单）
npm run dev → curl /predictions/{single,compare,backtest}   # 200 / 200 / 200
grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' Predictions.tsx  # ZERO（W-1 守住）
```

**契约纪律自检**: 全部 API 走 orval 生成 client（`predictionApi` / `screenerApi`），类型 `PredictionPayload`/`CandidatePoolQueryResponse` 等来自 `api/types.ts` 生成产物；无手写 fetch / 手写请求响应类型 / 手写 MSW handler。

**worktree 纪律自检**: 独立 worktree `frontend-dev-1b-predc` 基于 1afa2163；独占 `Predictions.tsx`（1实例=1文件）；临界区（api/client.ts / api/types.ts / styles/tokens.ts / components/prototype/* / main.tsx / App.tsx / package.json）**未触碰**——`alpha` / `signalLevelTokens` 在 HEAD 已就绪仅 import 消费；per-file git add（禁 stash/add -A，参考 memory `no-git-stash-shared-worktree`）。

**下一步**: 等待 product-lead review / 无阻塞

---

## Task #26 — BatchB-OpenDecision: 2.2 auction-analysis + 2.3 signal-scan + 2.5 execution-monitor（2026-07-03）

**状态**: ✅ 完成（已 commit），待 product-lead review

**Skills**: agf-running-sit-tests（dev-owned SIT 自跑）

**任务定位**: 评估 OpenDecision.tsx 现状后发现 3 sub-tab 专属渲染**已在 HEAD 533038df 完整落地**（`AuctionAnalysis` line 675 / `SignalScan` line 926 / `ExecutionMonitor` line 1195），signal-scan tab key=`signals`（path `/open-decision/signals`，line 22）已存在**无需补 tab/路由**，临界区零越界。本任务为**收口+测试覆盖**：补 2.2/2.3/2.5 三 sub-tab 的 SIT 证据（此前 SIT 仅覆盖 2.1/2.4）。

**SIT 证据**

worktree: `.wolf/worktrees/frontend-dev-1b-odb`（分支 `feat/md-ui-opendecision-batchb-dev1b`，基于 HEAD 533038df）。

- ✅ AC① (integration) 2.2 auction-analysis：挂载 `/open-decision/auction` → `signalApi.getDashboardAuction()` 被调 → 渲染竞价引擎条 + 抢筹 TOP10 + 出货预警 TOP10 + 四维评分 + 一字定方向 + 全量竞价明细专属区块。SIT 断言：
  ```
  await waitFor(() => expect(signalApi.getDashboardAuction).toHaveBeenCalled())
  expect(screen.getAllByText(/竞价分析引擎/).length).toBeGreaterThan(0)
  expect(screen.getAllByText(/328/).length).toBeGreaterThan(0)  // total_count
  expect(screen.getAllByText('抢筹 TOP 10').length).toBeGreaterThan(0)
  expect(screen.getAllByText('四维评分').length).toBeGreaterThan(0)
  ```
- ✅ AC① (integration) 2.3 signal-scan：挂载 `/open-decision/signals` → `signalApi.getLive()` 被调 → 渲染验证工作台 + 批量确认 + 选中股票 + Kronos 30日预测 + 风险检查 + 决策分类专属区块；信号行来自 getLive signals（宁德时代/中芯国际）。
- ✅ AC① (integration) 2.5 execution-monitor：挂载 `/open-decision/execution` → `tradeApi.getAccount/getOrders/getPositions/getDecisionContexts` 四契约被调 → 渲染账户条（总资产/可用/今日盈亏/总仓位）+ 今日订单 + 持仓 + 今日方案（plan_id PLAN-OPEN-0925）+ 需关注专属区块。
- ✅ AC④ 三 sub-tab 专属渲染（非通用壳）：auction 独占「抢筹 TOP 10」、signals 独占「验证工作台」、execution 独占「今日订单」，切换 tab 各自渲染且互不串（queryByText 断言非活跃 tab 区块 not.toBeInTheDocument）。
- ✅ AC③ EmptyState：2.2 auction 无抢筹/出货数据 → prototype-panel-note 诚实降级（`暂无抢筹数据`/`暂无出货预警`）；2.5 execution 无订单/持仓 → `暂无订单`/`暂无持仓`，不空白。
- ✅ AC② 全 token 化（W-1）：`grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' src/pages/OpenDecision.tsx` → **ZERO bare hex/rgba**。语义色走 `.up/.down/.warn/.neu/.t-up/.t-down/.t-warn/.t-mute` className + `lightTokens`/`alpha`/`signalLevelTokens`（已在 HEAD import 消费）。
- ✅ AC④ tsc 0 错：`npx tsc -b --noEmit` → 0 errors。
- ✅ AC⑤ vitest：`OpenDecision.test.tsx` 19 passed（既有，含 auction/signal-scan/execution 5 路由 it.each）；新增 `tests/sit/opendecision-subtabs-preview.test.tsx` 6 passed（2.2×1 + 2.3×1 + 2.5×1 + AC④×1 + AC③×2）。
- ✅ DoD dev server：`npm run dev`（vite v6.4.3，port 3001）→ `/open-decision/{auction,signals,execution}` 三路由均 200。

**质量门**
```
npx tsc -b --noEmit                                                          # 0 errors
npx vitest run src/__tests__/OpenDecision.test.tsx                           # 19 passed（既有）
npx vitest run tests/sit/                                                    # 47 passed（13 files，含新增 opendecision-subtabs 6）
npx vitest run src/__tests__/PrototypeFidelityGuard.test.ts                  # 1 passed
npm run dev → curl /open-decision/{auction,signals,execution}               # 200 / 200 / 200
grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' OpenDecision.tsx                      # ZERO（W-1 守住）
git diff --stat HEAD -- App.tsx main.tsx api/ styles/ components/prototype/  # 空（临界区零越界）
```

**契约纪律自检**: 全部 API 走 orval 生成 client（`signalApi`/`chainApi`/`screenerApi`/`tradeApi`），类型由 `api/types.ts` 生成产物承载；无手写 fetch / 手写请求响应类型 / 手写 MSW handler。

**worktree 纪律自检**: 独立 worktree `frontend-dev-1b-odb` 基于 533038df；OpenDecision.tsx 在 HEAD 已完整落地三 sub-tab 专属渲染，本任务仅补 SIT 测试覆盖（新增 `tests/sit/opendecision-subtabs-preview.test.tsx`）；临界区（App.tsx / main.tsx / api/client.ts / api/types.ts / styles/* / components/prototype/* / package.json）**未触碰**——signal-scan tab key=`signals` 已存在无需补 tab/路由；per-file git add（禁 stash/add -A）。

**下一步**: 等待 product-lead review / 无阻塞
