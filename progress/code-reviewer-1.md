# code-reviewer-1 — 行情决策 Batch A 第一波 fan-in 审查

**commit**: 48d47535 (12 文件 +881/-89)
**维度**: 契约 + 安全 (team-lead 派单)
**日期**: 2026-07-03

## Verdict: ✅ Pass (契约+安全维度)

---

### 1. 临界区越界机检 — ✅ 通过

commit 12 文件清单全部落在允许范围，**未触碰**任何临界区文件：

| 文件 | 范围 | OK |
|---|---|---|
| `frontend/src/pages/{Dashboard,Screener,Signals}.tsx` | pages | ✅ |
| `frontend/src/__tests__/{Dashboard,Screener,Signals,PrototypeRoutes}.test.tsx` | tests | ✅ |
| `frontend/tests/sit/{dashboard,signals}-preview.test.tsx` | sit | ✅ |
| `frontend/src/styles/suying-app.css` | 允许的唯一 style 文件 | ✅ |
| `progress/frontend-dev-{1,5}.md` | progress | ✅ |

**未出现**: `App.tsx` / `main.tsx` / `api/client.ts` / `api/types.ts` / `components/prototype/index.ts` / `package.json` / 其他 styles/*。

> 注: `agf-check-ownership.sh` 因当前 worktree 有未跟踪的 `.wolf/*` / template 文件而 flag, 但这些**不在 commit 48d47535 内**, 与本审查无关。

### 2. scope 明文检查 (契约 §9.3) — ✅ 通过

`Screener.tsx:addToCandidatePool` 构造的 payload 仅含:

```ts
{ source_module, source_mode, name, candidates, trade_date }
```

`git show 48d47535 | grep -E 'tenant_id|owner_user_id|account_id'` → **零命中**。
scope 全部由 `client.ts` 拦截器从 `platformSession` 注入 `X-Tenant-Id` / `X-Owner-User-Id` / `X-Trade-Account-Id` Header, 前端代码零明文 scope, 符合 §9.3。
后端 `CandidatePoolRecordRequest` docstring 也明确声明 "scope 字段不在此处——由后端从认证头注入"。

### 3. candidate-pool 字段对齐 — ✅ 通过

| 层 | 字段名 |
|---|---|
| 后端 `screener.py:6969` | `candidate_pool_metadata` |
| 前端 `types.ts:1177` | `candidate_pool_metadata` (附注释 "勿简写为 metadata") |
| 前端 payload (Screener.tsx) | 未传 (后端 default_factory=dict 兜底) |

M0 修复未回退。前端虽未传 metadata, 但字段名双边一致, 后端有默认值兜底, 契约兼容。

### 4. 交互完整性 (附带, 前后端对接项) — ✅

候选池按钮: `onClick={addToCandidatePool}` 真调 `screenerApi.recordCandidatePool` (生成产物, 非裸 fetch), `disabled` 绑 `recordingPool` loading 态, 有 toast + query 刷新。非空 handler, 符合 ADR-006。

---

## 一句话回 team-lead

**Pass** — 临界区零越界 / scope 全 Header 注入无明文 / candidate_pool_metadata 字段双边对齐无回退, 契约+安全维度放行。

---

## 第二波 223189b6 — OpenDecision 2.1/2.4 + Predictions 5.0 (契约+安全)

**commit**: 223189b6 (9 文件 +819/-43)
**维度**: 契约 + 安全 (team-lead 第二波派单)
**日期**: 2026-07-03

### Verdict: ✅ Pass

### 1. 临界区越界机检 — ✅ 通过

9 文件清单全部落在允许范围, **未触碰**任何临界区:

| 文件 | 范围 | OK |
|---|---|---|
| `frontend/src/pages/{OpenDecision,Predictions}.tsx` | pages | ✅ |
| `frontend/src/__tests__/{OpenDecision,Predictions}.test.tsx` | tests | ✅ |
| `frontend/tests/sit/{opendecision,predictions}-preview.test.tsx` | sit | ✅ |
| `frontend/src/styles/suying-app.css` | 允许的唯一 style 文件 | ✅ |
| `progress/frontend-dev-{1,3b}.md` | progress | ✅ |

**未出现**: `App.tsx` / `main.tsx` / `api/client.ts` / `api/types.ts` / `tokens.ts` / `components/prototype/index.ts` / `package.json` / 其他 styles/*。

dev 声称"临界区零越界, queryCandidatePool / CandidatePoolQueryResponse 仅 import 消费" — **复核属实**: 两文件 grep 到的 `import type { ... CandidatePoolQueryResponse, CandidatePoolRecord ... } from '../api/types'` 是纯消费, types.ts / client.ts 本身零改动。

### 2. scope 明文检查 (契约 §9.3) — ✅ 通过

两处 `screenerApi.queryCandidatePool` 调用点:

```ts
// OpenDecision.tsx (2.4 候选池 tab)
screenerApi.queryCandidatePool({ source_module: 'open-decision', page: 1, page_size: 50 })

// Predictions.tsx (5.0 overview 候选池排行)
screenerApi.queryCandidatePool({ source_module: 'screener', page_size: 20 })
```

入参仅含 `source_module` + 分页 (`page` / `page_size`), **无** `tenant_id` / `owner_user_id` / `account_id`。scope 全走 client.ts 拦截器头 (X-Tenant/Owner/Trade-Account), 符合 §9.3。

> 注: `git show | grep tenant_id` 命中两处, 均为**测试夹具** (OpenDecision.test.tsx 的 `decision_log` mock record) + **负向断言** (`expect(params).not.toHaveProperty('tenant_id')`), 非 queryCandidatePool payload, 不构成 scope 泄露。

### 3. candidate-pool 字段对齐 — N/A (纯查询)

第二波两处均为 `queryCandidatePool` (GET 查询), 无写入路径 (recordCandidatePool)。candidate_pool_metadata 字段对齐项不适用, 跳过。

### 4. 交互完整性 (附带, 前后端对接项) — ✅

候选池消费走 orval 生成 client `screenerApi.queryCandidatePool`, 返回 `CandidatePoolQueryResponse` 经 `candidateRowsFromPool()` 摊平为 `CandidateRow`, 与 chain 候选多源融合按 code 去重。无裸 fetch / 无手写类型 / 无手写 MSW handler, 符合 ADR-006。

---

## 第二波一句话回 team-lead

**Pass** — 临界区零越界 (9 文件全在 pages/__tests__/tests/sit/suying-app.css/progress 内) / queryCandidatePool 两处入参仅 source_module+分页零明文 scope / 纯查询无 candidate_pool_metadata 写入项。契约+安全维度放行。

---

## Batch B — #11 watchlist + #12 产业链 + #13 schema fix (契约+安全)

**commits**: 610c1c00 (#11) / aa78d31f (#12) / 3e7a13c5 (#13)
**维度**: 契约 + 安全 (team-lead Batch B 派单)
**日期**: 2026-07-03

### Verdict: ✅ Pass (三 commit 全部放行)

---

### #11 watchlist (610c1c00, 5 文件 +1110)

**1. 临界区越界** — ✅ 后端范畴, 改动只在 `backend/alembic/versions/022_watchlist.py` + `services/screener-service/{app/routers/screener.py,app/watchlist_store.py,tests/test_watchlist_api.py}` + `progress/backend-dev.md`。未碰 frontend 任何文件, 未碰 api/client.ts/types.ts。

**2. scope 明文 (§9.3)** — ✅ 三端点 (POST/GET/DELETE `/api/v1/screener/watchlist`) 的 `tenant_id` / `owner_user_id` / `account_id` **全部从 Header alias 注入** (`X-Tenant-Id` / `X-Owner-User-Id` / `X-Trade-Account-Id`), body schema 无 scope 字段。请求 body 仅含 `code` / `note` / `visibility` / `data_scope` (后者是可见性声明, 非 identity scope)。docstring 明示 "前端绝不传明文"。store 层 `_scope_where()` 把 scope 编进 WHERE 子句, 与前端 client.ts (3aa950ff 已确认不明文) 一致。

**3. migration 022 幂等 + scope 字段齐** — ✅
- `down_revision=021`, chain 正确。
- 幂等: `_has_table()` + `_has_column()` 双守卫 — legacy 4-col watchlist 表存在则 `ADD COLUMN` 补 scope+business 字段; 不存在则 `create_table`。downgrade 同样守卫, 可逆。
- scope 字段齐: `tenant_id` (NOT NULL) / `owner_user_id` (Optional) / `account_id` (Optional) / `visibility` / `data_scope` 五字段全建入。
- legacy latent bug 处理干净: 保留 legacy `note` 列, 不丢数据; unique index on (code, account_id) 守 account-scope 并发。

**4. 安全 (OWASP)** — ✅
- **SQL 注入**: store 全用 `text()` + `:param` 占位符 (`tenant_id=:tenant_id` 等); f-string 只注入 `TABLE_WATCHLIST` 常量 + `_scope_where()` 内固定子句, 无用户值拼入。
- **越权 (IDOR)**: DELETE (remove_by_id / remove_by_code) 走 `_scope_where()` visibility 矩阵 + `id=:row_id`/`code=:code`, account A 的股票对 account B 不可见不可删 (删返 0 行)。这是关键安全要求, 已落实。
- scope 过滤矩阵: tenant → `visibility='public' OR same tenant`; owner → `visibility IN ('public','tenant_shared') OR same owner`; account → `data_scope!='account' OR account_id IS NULL OR same account`。镜像 candidate_pool_store, 一致。

---

### #12 产业链 (aa78d31f, 3 文件 +468)

**1. 临界区越界** — ✅ 仅改 `frontend/src/pages/SupplyChainBom.tsx` + `tests/sit/chain-decompose-preview.test.tsx` + `progress/frontend-dev-5.md`。未碰 App.tsx / client.ts / types.ts / styles/* / components/prototype/index.ts。

**2. scope 明文** — ✅ N/A。SupplyChainBom 纯前端链路渲染 (消费 `chainDeconstructResult.tree` 叶子 `value_chain`), 无 candidate-pool / watchlist 写入或查询调用, 不涉 scope。

**3. token 合规 (W-1 第二次落实)** — ✅ `git show | grep '^\+.*#hex'` (排除注释/lightTokens) → 零命中。grep 出的 hex 全是 `-` 行 (旧内联 hex 被删除, 替换为 lightTokens token), 净改进。

---

### #13 schema fix (3e7a13c5, 2 migration + progress)

**幂等修复** — ✅ 006/008 migration 把 non-idempotent 的 `op.add_column` 改为 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` (006 还配 `DROP COLUMN IF EXISTS` downgrade)。匹配 `init_postgres.sql:594` 已预建的列, 消除 DuplicateColumn crash-loop。

**不破坏预建表** — ✅ 无 `DROP TABLE` / `CREATE TABLE` (仅 `ADD/DROP COLUMN IF EXISTS`), data-service 等依赖的预建表结构不动。TRUNCATE 注释仅描述 006 前继承的 backfill 顺序, 非新引入的破坏性操作。UAT deploy 报告 (batch-a-uioverhaul-uat-2026-07-03.md) 验证: `psql init_postgres.sql → alembic upgrade head → 001..022 全过, alembic_version=022, auth tables present`。

---

## Batch B 一句话回 team-lead

**Pass** — #11 watchlist scope 全 Header 注入 + store visibility 矩阵 + DELETE IDOR 守卫 + migration 022 幂等 scope 字段齐; #12 产业链纯前端链路零 scope 调用 + W-1 token 净改进; #13 schema fix 用 ADD COLUMN IF NOT EXISTS 幂等, 不破坏预建表 (UAT 验证 alembic 001..022 全过)。契约+安全维度放行。

---

## DEF 修 d7a72963 — DEF-1 scope 轻量复审 (post-signoff)

**commit**: d7a72963 (cherry-pick 自 dev-3 affdd2ce, 7 文件 +148/-4)
**维度**: DEF-1 scope 明文 (§9.3) 单项复核 (DEF-3/4 已 PL 全量 vitest 349 绿验证, 不细审)
**日期**: 2026-07-03
**性质**: post-signoff 流程补全, 板块已 PL 签字完全可用, 不阻塞

### Verdict: ✅ Pass (DEF-1 scope)

两个生产调用点 payload 仅 `{code, name}`, **零明文 scope**:

```ts
// Screener.tsx (addToWatchlist handler)
const response = await screenerApi.addWatchlist({ code, name })

// OpenDecision.tsx (handleWatch 行级按钮)
const response = await screenerApi.addWatchlist({ code: pick.code, name: pick.name })
```

`git show d7a72963 | grep -E 'tenant_id|owner_user_id|account_id'` 在生产 page 文件中零命中 (仅出现在 progress 文档的契约对账说明里, 非代码)。scope 全由 client.ts 拦截器从 platformSession 注入 `X-Tenant-Id` / `X-Owner-User-Id` / `X-Trade-Account-Id` Header (契约 §9.3), 与 Batch B #11 后端三端点 Header alias 接收一致。

测试断言 `mock.calls[0][0]` shape = `{code:'002281', name:'光迅科技'}`, 无 scope 字段, 双向印证。

走 orval 生成 client (`screenerApi.addWatchlist` @ client.ts:445, 非裸 fetch), 符合 ADR-006。

---

## DEF 修一句话回 team-lead

**DEF-1 scope Pass** — Screener + OpenDecision 两处 addWatchlist 调用 payload 仅 {code, name} 零明文 scope, 测试断言同形印证, 走生成 client 符合 §9.3。

---

## Batch C — #23 Screener 3.2/3.3 + #24 Predictions 5.1/5.2/5.3 (契约+安全)

**commits**: 47422493 (#23, 6 文件 +1299/-71) / 533038df (#24, 4 文件 +389/-32)
**维度**: 契约 + 安全 (team-lead Batch C 派单)
**日期**: 2026-07-03

### Verdict: ✅ Pass (两 commit 全放行)

---

### #23 Screener 3.2 model-compare + 3.3 factor-analysis (47422493)

**1. 临界区越界** — ✅ 改动只在 `frontend/src/pages/Screener.tsx` + `styles/suying-app.css` + `__tests__/NewUiModulePage.test.tsx` + `tests/sit/{model-compare,factor-analysis}-preview.test.tsx` + `progress/frontend-dev-5.md`。未碰 `App.tsx` / `main.tsx` / `api/client.ts` / `api/types.ts` / `components/prototype/index.ts` / `package.json`。

**NewUiModulePage.test.tsx 改动性质** — ✅ **test 对齐非越界**。该文件在 `__tests__/` 允许范围内; blob diff 显示只改了 3 行断言文本:
```
- expect(screen.getByText('模型评分差异'))
- expect(screen.getByText('候选池排行'))
+ // 3.2 model-compare preview：共识矩阵 + 跨模型评分对比（专属渲染，非通用壳）
+ expect(screen.getByText('共识矩阵'))
+ expect(screen.getByText('跨模型评分对比'))
```
断言文本跟随 preview 渲染更新 (dev 自述"模型评分差异→共识矩阵"对齐), 非改 critical 渲染壳本身。属合规 test 同步。

**2. scope 明文 (§9.3)** — ✅ **N/A (纯本地渲染, 零新增 API 调用)**。blob diff `^\+.*Api\.` 零命中; 全文 API surface (screenerApi.run/getModes/recordCandidatePool/queryCandidatePool/addWatchlist/listWatchlist + signalApi.triggerSync + watchlistApi.addWatchlist) 全是既有 commit (Batch A/B 已审过的生成 client), 3.2/3.3 专属渲染消费既有 run/modes 返回的本地 state, 不发新请求, 无 scope 可泄。grep `tenant_id|owner_user_id|account_id` 新增行零命中。

**3. token 合规 (附带)** — ✅ #23 CSS/inline 新增行零裸 `#hex` (grep 排除注释/lightTokens 后空), 84 行 suying-app.css 增量走 CSS 变量/token 派生。

---

### #24 Predictions 5.1/5.2/5.3 (533038df)

**1. 临界区越界** — ✅ 仅改 `frontend/src/pages/Predictions.tsx` + `__tests__/Predictions.test.tsx` + `tests/sit/predictions-subtabs-preview.test.tsx` + `progress/frontend-dev-1.md`。未碰任何 critical 文件。dev 自述"worktree frontend-dev-1b-predc 独占 Predictions.tsx, 临界区零越界" 复核属实。

**2. scope 明文 (§9.3)** — ✅ **N/A (纯本地 sub-tab 渲染, 零新增 API 调用)**。blob diff `^\+.*Api\.` 零命中; 全文 API surface (predictionApi.{predict,predictFast,compare,getOverview,getStatus,getAccuracyBacktest} + screenerApi.queryCandidatePool) 全是既有, 5.1/5.2/5.3 sub-tab 消费既有 overview 返回的本地 state, 不发新请求。grep scope 字段新增行零命中。

---

## Batch C 一句话回 team-lead

**Pass** — #23/#24 临界区零越界 (NewUiModulePage.test.tsx 是断言文本对齐 preview 非改 critical 渲染壳, 在 __tests__/ 允许范围); 两 commit blob diff 零新增 API 调用 (3.2/3.3 + 5.1/5.2/5.3 纯本地 state 渲染消费既有 run/overview 返回), scope §9.3 N/A 无可泄; #23 CSS/inline 零裸 hex token 合规。契约+安全维度放行。

---

## Batch B 补 6 — #25 Dashboard 1.2 + #26 OpenDecision sit + #27 SupplyChainBom 4.1/4.3 (契约+安全)

**commits**: 746ff6cd (#25, 4 文件 +332) / e3fb8ad4 (#26, 2 文件 +235) / 7e7d1dbe (#27, 1 文件 +175)
**维度**: 契约 + 安全 (team-lead Batch B 补 6 派单)
**日期**: 2026-07-03

### Verdict: ✅ Pass (三 commit 全放行)

---

### #25 Dashboard 1.2 auction (746ff6cd)

**1. 临界区越界** — ✅ 仅改 `frontend/src/pages/Dashboard.tsx` + `__tests__/Dashboard.test.tsx` + `tests/sit/auction-dashboard-preview.test.tsx` + `progress/frontend-dev-3.md`。未碰 critical 文件。

**2. scope (§9.3)** — ✅ **N/A (纯展示)**。blob diff `^\+.*Api\.|tenant_id|owner_user_id|account_id` 零命中。1.2 全量竞价明细是 10 列表 + EmptyState 兜底, 消费既有 auction 本地 state, 零新增请求。

**3. token 合规** — ✅ 新增行零裸 `#hex`/`rgba` (grep 排除注释/token 后空), 走 signalLevelTokens + alpha + lightTokens。

---

### #26 OpenDecision sit test (e3fb8ad4)

**1. 临界区越界** — ✅ **只 sit test + progress**, 未改任何 page/critical 文件。dev 自述"page 代码在 HEAD 已就绪, 本 commit 仅补 SIT 测试覆盖" 复核属实: `git show e3fb8ad4:frontend/src/pages/OpenDecision.tsx` 在 ~line 543-546 已有 `AuctionAnalysis` / `SignalScan` / `ExecutionMonitor` / `CandidatePool` / `DecisionOverview` 五 sub-tab 渲染 (按 `active` 切换), dev server `/open-decision/{auction,signals,execution}` 200/200/200 印证。本 commit 仅加 `tests/sit/opendecision-subtabs-preview.test.tsx` 覆盖既有渲染, 非改 page。

**2. scope (§9.3)** — ✅ **N/A (纯测试)**。无生产代码改动, 无 API 调用变更。

**3. token 合规** — ✅ commit msg 自述 "OpenDecision.tsx 全文零裸 #hex/rgba (grep 验证)" — page 未改, 无新增样式风险。

---

### #27 SupplyChainBom 4.1/4.3 (7e7d1dbe)

**1. 临界区越界** — ✅ 仅改 `frontend/src/pages/SupplyChainBom.tsx` (+175/-1)。**注意: 本 commit 无 sit test + 无 progress** (dev-5 worktree 写代码后 429 限额未 commit/SIT, PL 接手验证采纳: tsc 0 + SupplyChainBom.test.tsx 16/16 绿)。sit 缺口记 follow-up, 非契约/安全 finding。

**2. scope (§9.3)** — ✅ **N/A (纯展示)**。blob diff `^\+.*Api\.|tenant_id|owner_user_id|account_id` 零命中。4.1 政策梳理 (policy tab 政策证据) + 4.3 多维度分析 (company tab 公司对比) 消费既有 chainDeconstructResult 本地 state, 零新增请求。

**3. token 合规** — ✅ 新增行零裸 `#hex`/`rgba`, 走 signalLevelTokens/alpha/lightTokens, 守 W-1。

---

## Batch B 补 6 一句话回 team-lead

**Pass** — #25/#26/#27 临界区零越界 (无 App.tsx/main.tsx/client.ts/types.ts/components/prototype 触碰); #26 dev 自述"page 在 HEAD 已就绪" 复核属实 (line 543-546 已有 AuctionAnalysis/SignalScan/ExecutionMonitor 等 5 sub-tab 渲染, 本 commit 仅补 SIT); 三 commit scope §9.3 全 N/A (纯本地 state 展示, blob diff 零新增 API 调用 + 零 scope 明文); token 合规 (新增行零裸 hex/rgba, 走 lightTokens/signalLevelTokens)。#27 sit test 缺口 (dev 429 限额) 记 follow-up, 非契约/安全 finding。契约+安全维度放行。
