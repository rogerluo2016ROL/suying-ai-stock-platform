# progress / frontend-dev-3b

> 第二波 task #9 Predictions。独占 worktree `.wolf/worktrees/frontend-dev-3b-predictions`（分支 `feat/md-ui-predictions-dev3b`，基于 HEAD `48d47535`）。

---

## 2026-07-03 · task #9 · 落地 5.0 prediction-overview

### 状态

**完成。** Predictions 概览（`active==='overview'`）对齐 5.0 preview：hero 三入口 + 2 KPI（今日预测任务/近30次方向正确率）+ 候选池预测排行 + 模型运行状态 + 预测预警摘要。候选池排行消费 `screenerApi.queryCandidatePool`，2 KPI 后端字段未齐走 fallback_reason（不展示假数），预警摘要按候选 grade 推导。W-1 全 token 化（ECharts 读 lightTokens、alert-dot/语义色走 var(--*) token + .up/.down/.warn/.neu className）。保持浅色。SIT 全绿。

### Skills

`agf-running-sit-tests`

### 产物 / 改动文件

独占 worktree，per-file git add（未 stash / 未 `add -A`）：

- `frontend/src/pages/Predictions.tsx`（重构 overview tab + ECharts token 化）
  - import：加 `screenerApi`、`CandidatePoolQueryResponse`/`CandidatePoolRecord` 类型、`lightTokens`
  - `buildTrajectoryOption`：6 处裸 hex（`#8a96a8`/`#52617a`/`#e6eaf0`/`#ff4d4f`/`#2ec27e`/`#3d8bff`）→ `lightTokens.muted`/`fg2`/`border`/`up`/`down`/`accent`（W-1）
  - 新增 state `poolRecords`/`poolError`/`poolFallback` + overview 挂载时 `screenerApi.queryCandidatePool({source_module:'screener',page_size:20})` effect
  - 派生 `poolCandidates`/`todayPredictionCount`/`hitRateValue`/`overviewKpiFallback`/`overviewAlerts`（按 grade：S/A→信号增强/B→信号偏弱/C→方向相悖）
  - overview JSX 重写：PrototypePageHeader 加 3 actions（单股/对比/回测 navigate）；2 KPI（今日预测任务=`poolCandidates.length`、近30次方向正确率=`backtest.metrics` 近30日 direction_accuracy，未齐 `'--'` + fallback）；候选池预测排行表（标的/评分/等级/一致性/操作 → 单股详情）；模型运行状态卡（保留 getStatus/getOverview 字段）；预测预警摘要 alert-list
  - 缺数据 EmptyState：候选池空 → "暂无候选池预测排行"；预警空 → "暂无预警"
- `frontend/src/styles/suying-app.css`（+13 行）
  - 新增 `.alert-list`/`.alert-item`/`.alert-dot`(+`.warn`/`.down`/`.up`)/`.alert-copy strong`/`.alert-copy span`/`.alert-time` — 全 `var(--*)` token；补 `.prototype-fallback .nm` + `.mt6` helper
- `frontend/src/__tests__/Predictions.test.tsx`
  - mock 加 `screenerApi.queryCandidatePool`；overview 测试标题改 'K线预测总览'；新增 2 用例：候选池排行+预警渲染 / EmptyState（候选池空 + 2 KPI '--'）
- `frontend/tests/sit/predictions-preview.test.tsx`（新）
  - 3 用例：overview 渲染候选池排行+2KPI+预警+queryCandidatePool 正确参数 / EmptyState+KPI fallback / hero 入口可点

### SIT 证据

环境：worktree `frontend-dev-3b-predictions`，node_modules 软链主仓（同 commit base `48d47535`）。本仓前端 API client 手写 typed wrapper（无 orval/`*.msw.ts`），故 SIT 用 vitest + vi.mock client（与既有 Signals/Predictions test 同款），非 orval MSW——本仓契约纪律现实如此，已如实标注。

**SIT 证据**

- ✅ **AC-1 (5.0 概览区块对齐 preview)**：`npx vitest run tests/sit/predictions-preview.test.tsx` → `Test Files 1 passed (1) / Tests 3 passed (3)`；断言 hero 标题"K线预测总览" + 候选池预测排行 + 预测预警摘要 渲染。
- ✅ **AC-2 + AC-7 (缺字段 fallback_reason + EmptyState，缺数据不空白)**：SIT `overview: 候选池空 + 后端命中率字段未齐 → EmptyState + KPI 走 fallback 不展示假数` 绿——断言"暂无候选池预测排行"+"暂无预警"+ 2 KPI 值 `'--'` ×≥2。
- ✅ **AC-3 (内联 style 全 token 化 / W-1)**：ECharts `buildTrajectoryOption` 6 处裸 hex → `lightTokens` 常量（grep 0 裸 hex in buildTrajectoryOption）；alert-dot/语义色走 `var(--up)/--warn/--down/--accent` + `.up/.down/.warn/.neu` className（suying-app.css `.alert-dot` 全 token）；动态 width/value 无 inline。
- ✅ **AC-4 (tsc 0 错)**：`npx tsc -b --noEmit` → exit 0，无输出。
- ✅ **AC-5 (vitest 新增用例)**：`src/__tests__/Predictions.test.tsx` → 7 passed（原 5 + 新增 2 overview）。
- ✅ **AC-6 (新增 tests/sit/predictions-preview.test.tsx)**：3 passed。
- ✅ **AC 回归 (全仓 vitest)**：`npx vitest run` → **Test Files 52 passed (52) / Tests 332 passed (332)**（wave-1 已修 PrototypeRoutes，本波无回归）。
- ✅ **dev server (DoD 真点)**：`npm run dev` 起 :3000；`curl /src/pages/Predictions.tsx` HTTP 200、`curl /predictions` HTTP 200，vite log 无 error/fail/transform；按钮/数据路径由 vitest + RTL 已断言。

### 质量门

| 项 | 结果 |
|---|---|
| vitest（Predictions unit） | ✅ 7/7 |
| vitest（SIT predictions-preview） | ✅ 3/3 |
| vitest（全仓） | ✅ 52/52 file, 332/332 test |
| tsc `--noEmit` | ✅ 0 错 |
| lint | N/A（本仓无 eslint 配置 / 无 lint script） |
| dev server | ✅ vite :3000，Predictions 模块+路由 HTTP 200，无 transform error |

### 下一步

commit 后回 team-lead：SIT 数字（unit 7/7 + SIT 3/3 + 全仓 332/332 + tsc 0）+ commit hash + worktree 路径。
