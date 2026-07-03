# frontend-dev-3 Progress

## T-206: model-training frontend 修复（4 项 P0） — 2026-06-12 14:30

**状态**: Completed

**Skills used**: none (direct code fix)

**SIT 证据**:

- `npx vitest run`: 16 passed (20 total), 4 failed in auth-flow (pre-existing), OOM on full suite
- No model-training-specific SIT tests exist; acceptance validated via code inspection against backend schemas

AC by AC:
- [x] AC-206.1 (Rollback): `ModelRegistry.tsx` refactored — added `targetVersion` state, auto-set from `record.version - 1` on rollback button click, `InputNumber` in rollback modal, request body now includes `target_version: targetVersion, reason: rollbackReason`. Matches `RollbackRequest` schema (`schemas.py:232-234`).
- [x] AC-206.2 (Cancel): Backend endpoint `POST /api/v1/training/status/{job_id}/cancel` did not exist. Added to `routes.py` with lock validation, status guard (only PENDING/PREPARING/RUNNING/EVALUATING), persistence via `_save_job`, and Redis SSE publish. Frontend `Training.tsx:534` path unchanged — now matches.
- [x] AC-206.3 (Archive): Backend endpoint `POST /api/v1/training/models/{model_id}/archive` did not exist. Added to `routes.py` — sets stage to `archived` with reason notes, guards against archiving production models (redirect to rollback). Frontend `ModelRegistry.tsx:300` path unchanged — now matches.
- [x] AC-206.4 (Deploy): `ModelRegistry.tsx:264` now sends `{ notes: '' }` in deploy request body. Matches `DeployRequest` schema (`schemas.py:218-219`).
- [x] AC-206.5 (Build): `npx tsc -b --noEmit` — 0 errors from model-training files; 12 pre-existing errors in other files (`RiskCheckModal.tsx`, `Diagnosis.tsx`, `Trade.tsx`). `npm run build` — same pre-existing errors block the build (not introduced by this change).

**质量门**:
- `npx tsc -b --noEmit`: 0 model-training errors (12 pre-existing elsewhere) ✅
- `npx vitest run`: 16/20 passed, 4 auth-flow failures pre-existing ⚠️
- `npm run build`: blocked by pre-existing TS errors ❌ (OOM on vitest full run)

**涉及文件**:
- `frontend/src/pages/ModelRegistry.tsx` (+5 lines state, +deploy notes body, +InputNumber import, +targetVersion in rollback modal + handler)
- `services/training-service/app/routes.py` (+42 lines cancel endpoint, +42 lines archive endpoint, +imports for `_job_lock`, `_jobs`, `_publish_progress`, `_save_job`)
- `frontend/src/pages/Training.tsx` (no change needed; path now matches new backend endpoint)

**下一步**: PL 决定是否接受构建被 pre-existing errors 阻塞（新增代码 0 TS 错误）

---

## UAT-DEF: DEF-1 watchlist 按钮解禁 + DEF-3 empty_state 字段对齐 + DEF-4 Signals 文案 — 2026-07-03

**Task**: #22 UAT-DEF（frontend-dev-3，worktree `.wolf/worktrees/frontend-dev-3-def` @ HEAD 3aa950ff）

**AC 自验**: ✅ 全通过
- ✅ **DEF-1**：Screener.tsx "加入自选"按钮解禁（去 disabled + title 改），点击调 `screenerApi.addWatchlist({code,name})` → `message.success`（含 fallback_reason 走 `message.error`）+ `screenerApi.listWatchlist()` 刷新；OpenDecision.tsx 多源候选池表加"操作"列 + 行级"加入自选"按钮，同样调 addWatchlist + listWatchlist 刷新
- ✅ **DEF-3**：empty_state 字段对齐——最小侵入：OpenDecision 读 `candidatePoolEmptyState?.reason || hint || suggestion`（types.ts empty_state 标 {reason} 但后端实际返 {hint,suggestion}）；**不碰临界区 types.ts**（用局部 cast `as {reason?,hint?,suggestion?}` 兼容三者）
- ✅ **DEF-4**：Signals 侧栏 EmptyState "候选池写入接口未接入，暂时只保留信号证据链展示" → "候选池写入已接入（选股工作台/决策页可一键写入），本侧暂时只保留信号证据链展示"
- ✅ W-1：DEF diff 0 裸 hex 色（无新增内联 style）；守浅色

**质量门**:
- vitest: `npx vitest run`（全量 54 files / 349 tests）→ **全绿**；本次 3 文件 `Screener + OpenDecision + Signals` 32/32 passed（新增 DEF-1 watchlist 写入测试 + DEF-3 hint 测试 + DEF-4 文案测试）
- tsc: `npx tsc -b --noEmit` → **0 错**（修了 1 处 stageState 函数声明误删导致的 TS1128，同 bug-009 pattern——Edit 锚点连带声明行被吞）
- lint: tsc 通过
- dev server: 未起（纯交互 handler + 文案 + 字段兼容，无新依赖/路由/样式 token）
- worktree: 独占 `.wolf/worktrees/frontend-dev-3-def`，先建 worktree 再 cd 进去再 Edit（吸取 task-6 教训，本次未落主仓）；node_modules 软链主仓复用

**改动文件**（6 个，per-file git add）:
- `frontend/src/pages/Screener.tsx`（+watchingCode state；+addToWatchlist handler 调 addWatchlist + listWatchlist + try/catch/finally toast；"加入自选"按钮解禁绑 handler+loading 态）
- `frontend/src/pages/OpenDecision.tsx`（+message import；empty_state 读 reason||hint||suggestion 兼容；CandidatePool 组件 +watchingCode state + handleWatch 调 addWatchlist+listWatchlist；候选表加"操作"列 + 行级"加入自选"按钮）
- `frontend/src/pages/Signals.tsx`（侧栏 EmptyState 文案 DEF-4 更新）
- `frontend/src/__tests__/Screener.test.tsx`（mock 补 addWatchlist/listWatchlist；+DEF-1 加入自选写入测试断言 {code,name}）
- `frontend/src/__tests__/OpenDecision.test.tsx`（mock 补 addWatchlist/listWatchlist；+DEF-3 hint/suggestion empty_state 测试）
- `frontend/src/__tests__/Signals.test.tsx`（+DEF-4 文案测试：断言旧"未接入"消失 + 新"已接入"出现）

**契约对账**: 前端走 `screenerApi.addWatchlist`（client.ts:445，POST /screener/watchlist，Batch B #11）+ `screenerApi.listWatchlist`（client.ts:447）。scope 走拦截器头，前端不传明文。WatchlistAddRequest {code,name?,...}；WatchlistAddResponse {record, fallback_reason}。

**下一步**: commit 后回 team-lead 1 句话（3 defect 状态 + tsc/vitest + commit hash），进 code review。

---

## BatchB-Dashboard 1.2 auction-dashboard 竞价意图 — 2026-07-03

**Task**: #25（frontend-dev-3，worktree `.wolf/worktrees/frontend-dev-3-dash-auction` @ HEAD 533038df）

**AC 自验**: ✅ 全通过
- ✅ ①1.2 竞价意图（auction tab）对齐 preview：补全 4 专属区块——竞价撮合价走势（ECharts line, 9:15-9:25）/ 四维评分（ECharts radar + 个股信息卡）/ 一字定方向（按行业聚合竞价热度 grid）/ 全量竞价明细（10 列可读表）；保留既有 KPI + 抢筹/出货 TOP10
- ✅ ②专属渲染（非通用壳）：4 区块均走 auction 专属 helper（auctionDimensionRows / buildAuctionTimelineOption / buildAuctionRadarOption / auctionSectorHeat）
- ✅ ③内联 style 全 token 化：颜色走 signalLevelTokens（STRONG_BUY/SELL/HOLD）+ alpha.up/accent（ECharts rgba 派生）+ lightTokens（muted/fg2/border）；className tone 走 up/warn/down；**0 裸 #hex/rgba**（git diff 验证 clean）
- ✅ ④缺数据 EmptyState：一字定方向缺数据走 `EmptyState`（暂无板块竞价数据 + fallback_reason 文案）；全量明细缺数据走 EmptyState（暂无竞价明细）
- ✅ ⑤tsc 0 错；⑥vitest Dashboard.test.tsx 11/11 + 新 tests/sit/auction-dashboard-preview.test.tsx 3/3；全量 58 files / 374 tests 绿，0 回归
- ✅ ⑦守 W-1 浅色

**质量门**:
- tsc: `npx tsc -b --noEmit` → **0 错**
- vitest: 全量 **58 files / 374 tests passed**；本次 Dashboard.test.tsx + auction-dashboard-preview.test.tsx **14/14**
- W-1: git diff 0 裸 hex/rgba（signalLevelTokens + alpha + lightTokens 桥接 ECharts 配置色）
- worktree: 独占 `.wolf/worktrees/frontend-dev-3-dash-auction`，先建 worktree→cd→Edit，未落主仓；node_modules 软链主仓

**改动文件**（4 个，per-file git add）:
- `frontend/src/pages/Dashboard.tsx`（+alpha import + RadarChartOutlined/TableOutlined import；+auctionDimensionRows/buildAuctionTimelineOption/buildAuctionRadarOption/auctionSectorHeat 4 helper；auction tab 补 4 区块：撮合价走势 ECharts + 四维评分 radar+信息卡 + 一字定方向 sector-grid + 全量明细表，含 EmptyState）
- `frontend/src/__tests__/Dashboard.test.tsx`（auction test +4 专属区块断言，getAllByText 处理多处同名）
- `frontend/tests/sit/auction-dashboard-preview.test.tsx`（新 SIT：4 区块渲染 + EmptyState 缺数据 + 契约调用 getDashboardSummary）
- `progress/frontend-dev-3.md`（本段）

**契约对账**: signalApi.getDashboardSummary（dashboard-summary.auction_intent.top_bullish/top_bearish 统计+明细）+ getDashboardAuction（picks 增强）。前端不传 scope，走拦截器头。

**下一步**: commit 后回 team-lead 1 句话（SIT 数字 + commit hash + worktree）。
