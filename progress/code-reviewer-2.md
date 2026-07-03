# progress / code-reviewer-2 — Batch A 第一波 质量+SIT Audit

## 审查对象

commit `48d47535`（feat(ui): 行情决策 Batch A 第一波 — Dashboard/Screener/Signals preview 落地 + PrototypeRoutes 修复），12 文件 +881/-89。

## 复跑证据（reviewer 自跑，非 dev 声明）

| 项 | 命令 | 结果 |
|---|---|---|
| tsc | `cd frontend && npx tsc -b --noEmit` | **TSC_EXIT=0（0 错）** ✅ |
| vitest 全量 | `cd frontend && npx vitest run` | **51 files / 327 tests 全绿** ✅ |
| SIT precheck (dev-1) | `bash .claude/scripts/agf-sit-precheck.sh progress/frontend-dev-1.md` | ✅ 无机械问题 |
| SIT precheck (dev-5) | 同上 dev-5 | ⚠️ 未找到 `**SIT 证据**` 段（dev-5 用 `## SIT 证据` 二级标题，advisory） |

dev 声明的 "tsc 0 错 + 327/327 绿" 复跑一致。

---

## 代码 verdict: approve with changes

3 个 warning（token 一致性局部缺口，非阻断）+ 2 个 suggestion。**无 critical**。

### W-1 [warning] Dashboard.tsx:220-224 signalLevelMeta 4 档色值未 token 化（只改了 2 档）

本次 commit 把 `STRONG_BUY`（→`lightTokens.up`）和 `HOLD`（→`lightTokens.accent`）token 化，但同对象其余 4 档仍是裸 hex：

```
frontend/src/pages/Dashboard.tsx:220  BUY:      color: '#fa8c16'   // 应 lightTokens.warn
frontend/src/pages/Dashboard.tsx:222  REDUCE:   color: '#faad14'   // 应 lightTokens.warn 变体
frontend/src/pages/Dashboard.tsx:223  SELL:     color: '#8c8c8c'   // 应 lightTokens.neutral
frontend/src/pages/Dashboard.tsx:224  TIMING_ALERT: color: '#722ed1' // 紫，token 无对应
```

问题：AC④「内联 style token 化 ~20 处」声称全 token 化，但同一 record 内 4/6 档漏改，半 token 化比全裸更不一致。
修复：BUY→`lightTokens.warn`、SELL→`lightTokens.neutral`；REDUCE/TIMING_ALERT 若需区分档位，在 `lightTokens` 补 `warn2`/`accent2` 常量（避免新增裸色）。

### W-2 [warning] Signals.tsx buildHistoryTrendOption areaStyle + markLine 仍写裸 rgba

```
frontend/src/pages/Signals.tsx:141  areaStyle colorStops: 'rgba(61,139,255,0.18)' / 'rgba(61,139,255,0)'
frontend/src/pages/Signals.tsx:149  markLine 强买: 'rgba(255,77,79,0.35)'
frontend/src/pages/Signals.tsx:150  markLine 买入: 'rgba(245,166,35,0.35)'
frontend/src/pages/Signals.tsx:151  markLine 持有: 'rgba(61,139,255,0.35)'
```

这些 rgba 是 `accent`(3d8bff)/`up`(ff4d4f)/`warn`(f5a623) 的带透明度变体——AC④ 声称「echarts option 全部走 lightTokens，不硬编码裸色值」，但带 alpha 的渐变 / 虚线仍是裸 rgba 字面量。
修复：在 `tokens.ts` 补 `accentDim18`/`upDim35`/`warnDim35` 派生常量（或导出 `withAlpha(token, a)` helper），markLine/areaStyle 引用之。Dashboard.tsx:354 gauge 5-stop 里 `#237804`/`#52c41a`/`#fa8c16` 同类问题（既有，本次只 token 化了 2 个 stop），归入本 warning。

### W-3 [warning] suying-app.css 新增 .rc-badge / risk-check-card 用裸 rgba

```
frontend/src/styles/suying-app.css:405  .rc-badge.pass  background: rgba(46,194,126,.12)
frontend/src/styles/suying-app.css:406  .rc-badge.warn  background: rgba(245,166,35,.12)
frontend/src/styles/suying-app.css:407  .rc-badge.reject background: rgba(255,77,79,.12)
```

设计 token 纪律要求视觉值引用 DESIGN.md token / CSS 变量。这些 badge 背景是 down/warn/up 的 12% alpha，本可走 `var(--down-bg)`/`var(--warn-bg)`/`var(--up-bg)`（既有 `--*-bg` 语义变量，见 sectorColor 同款用法 Dashboard.tsx:418-421）。
修复：把 3 个 badge background 改成 `var(--down-bg)`/`var(--warn-bg)`/`var(--up-bg)`，与既有 `.sector-cell.strong` 同源。

### S-1 [suggestion] Signals.tsx mapRiskCheckCards 用 emoji 当 icon（rc-icon）

```
frontend/src/pages/Signals.tsx:180-183  '✅' / '⚠️' / '🟢'
frontend/src/pages/Signals.tsx:467     <span className="rc-icon">{card.icon}</span>
```

审美纪律（agf-design-discipline AI Tells §4）禁「emoji 当 icon」——应走 lucide / antd icon（项目已 `@ant-design/icons` 在用）。`mapRiskCheckCards` 的 emoji 是 fallback 装饰，影响度低，列 suggestion。
修复：换 `CheckCircleFilled`/`WarningFilled`/`ExclamationCircleFilled`（antd），status→icon 映射。

### S-2 [suggestion] Screener.tsx:504-508 双空行 + addToCandidatePool 注释合理

`addToCandidatePool` 函数后双空行（Screener.tsx:528-529），风格 nit。逻辑正确：scope 走 client 拦截器头、前端不传明文 tenant/owner、catch detail 降级、recordingPool 防重入、query 刷新失败不阻断主链路——**认可**。无 scope 明文泄漏（team-lead 关注点已通过）。

---

## 认可的良好设计

1. **Dashboard.buildSentimentReasons**（Dashboard.tsx:243-291）：从真实 market_sentiment/八维/快照派生 3 条支撑原因，缺字段标 `fallback: true` + 文案，**不空白不演示**——这正是 AC② 要的「不引入演示数据」。
2. **Dashboard fallback Dimensions**（Dashboard.tsx:165-176）：用 `fallbackDimTone = lightTokens.border2` 渐变替代 8 处裸 `#d8dee8`，token 化彻底。
3. **Screener.tsx scoreColor/factorColor**（:149-159）：ind-bar-fill 背景全走 `var(--up/down/warn/accent)`，Screener.tsx **零硬编码色值**（grep 0 hit）。
4. **EmptyState 兜底全覆盖**：Dashboard 历史 4 MetricCard 显式 fallback_reason（:1059-1062）+ 2 EmptyState（:1070/1076）+ 资金全景 4 分项占位（:1040）；Signals risk-scan 缺数据走 EmptyState；Screener wb-empty（:664）。team-lead 第 4 项**全部命中**。
5. **候选池 scope 注入**：Screener `addToCandidatePool` payload 仅业务字段，scope 全 Header 注入，**无明文**——team-lead 关注点通过。

---

## SIT Audit verdict: ✅ Pass

### 4 项 audit

1. **progress 完整性** ✅
   - `progress/frontend-dev-1.md` 含 `BatchA-Dashboard` 完整 SIT 证据段（7 AC + 质量门 5 命令 + 改动文件清单 + worktree 纪律自检 + 已知 pre-existing 失败说明）。
   - `progress/frontend-dev-5.md` 含 `## SIT 证据` 段（AC 自验 6 条 + tsc/vitest/dev server 三段证据 + 8 用例 SIT 文件说明 + 全量回归说明）。
   - `progress/frontend-dev-3.md` 仅有 T-206 旧记录，**本次 Screener 候选池解禁无独立 SIT 段**——但 Screener 改动小（42 行，2 处按钮 onClick + 1 handler + token 化），`Screener.test.tsx` 候选池写入断言已在 commit 内（+40 行），全量 vitest 327 绿覆盖。判 Pass with concern：dev-3 应补一行 Screener SIT 条目，非阻断。

2. **AC 覆盖** ✅
   - Dashboard 7 AC（1.1×4 区块 + 1.3×2 + token 化 + 契约）逐条对应 SIT `dashboard-preview.test.tsx`（1.1×4 + 1.3×2，6 SIT 用例）。
   - Signals 6 AC（四 preview sub-tab + EmptyState + token + tsc + progress）逐条对应 `signals-preview.test.tsx` 8 用例（含 sub-tab 切换逐一点击断言）。
   - Screener 候选池写入有 `Screener.test.tsx` 断言。

3. **证据可信度** ✅
   - 命令 + 真实输出片段齐全：`tsc -b --noEmit` exit 0、`vitest run` 给出 `Test Files X passed / Tests Y passed` 计数、dev server `curl /src/pages/Signals.tsx → HTTP 200`、`openwolf designqc` 路由尝试。
   - **非** "通过/OK" placeholder——是真实工具真实输出。
   - reviewer 自跑 tsc=0 / vitest 327 绿**复现一致**（最强可信度背书）。

4. **失败/阻塞标记真实性** ✅
   - dev-1 如实标记 `PrototypeRoutes.test.tsx` pre-existing `marketApi` mock 缺口（非本 task，临界区未擅改）。
   - dev-5 如实标记全量 70 failed 全在 `PrototypeRoutes.test.tsx`（同根因），scope 内 22/22 绿。
   - 本 commit 的 `PrototypeRoutes.test.tsx +5` 正是修这个 mock 缺口（bug-010），commit message 「70 failed→72 绿」与 dev 记录的 pre-existing 一致——**问题被如实追踪并修复**，非掩盖。

### 结论

4 项主体全过，dev-3 Screener SIT 段缺失属局部瑕疵（Screener.test.tsx 断言 + 全量 vitest 已覆盖），不构成 Redo。verdict **✅ Pass**。

---

## verdict 推导

- critical_count: 0
- warning_count: 3（W-1 Dashboard signalLevelMeta 半 token 化 / W-2 Signals+Dashboard ECharts 裸 rgba / W-3 suying-app.css rc-badge 裸 rgba）
- suggestion_count: 2（S-1 emoji icon / S-2 双空行）
- code_verdict: **approve with changes**（3 warning 全是 token 一致性局部缺口，非正确性/安全性/契约问题，tsc+vitest 全绿，可在 follow-up 收口；不阻断 fan-in 后续 E2E）
- sit_audit_verdict: **✅ Pass**

## 下一步

回 team-lead：verdict **approve with changes**——可继续推进，3 个 token warning 建议在 Batch B 或独立 token 收口 task 一并修（补 `tokens.ts` alpha 派生常量 + signalLevelMeta 剩余 4 档 + rc-badge 改 `var(--*-bg)`）。SIT Audit ✅ Pass，无 Redo。

---

# 第二波 commit 223189b6 — 质量+SIT Audit（W-1 复核重点）

## 审查对象

commit `223189b6`（feat(ui): 行情决策 Batch A 第二波 — OpenDecision 2.1/2.4 + Predictions 5.0 preview 落地），9 文件 +819/-43。

## 复跑证据（reviewer 自跑）

| 项 | 命令 | 结果 |
|---|---|---|
| tsc | `cd frontend && npx tsc -b --noEmit` | **TSC_EXIT=0（0 错）** ✅ |
| vitest 全量 | `cd frontend && npx vitest run` | **53 files / 341 tests 全绿** ✅ |
| OpenDecision 裸色 grep | `grep -nE '#[0-9a-fA-F]{3,8}\|rgba?\(\|rgb\(' src/pages/OpenDecision.tsx` | **exit 1（0 hit）** ✅ |
| Predictions 裸色 grep | 同上 src/pages/Predictions.tsx | **exit 1（0 hit）** ✅ |

dev 声明的 "tsc 0 + 341/341 绿" 复跑一致。

## W-1 复核结论：✅ 真落实（第二波零裸色，教训吸取）

第一波我标了 W-1（Dashboard signalLevelMeta 半 token 化：6 档只改 2 档）。第二波 dev 明确声称「吸取 W-1，零裸 hex」，复核**实证通过**：

1. **OpenDecision.tsx 全文 0 裸色**（grep exit 1）——语义色走 className（`.up/.down/.t-up/.t-down/.t-warn/.t-mute/.od-card-up/.od-card-down`），见 :653/:699/:748/:757-760/:773/:782-784。本页无 ECharts，故无 ECharts 色配置需要 token 化。
2. **Predictions.tsx 全文 0 裸色**（grep exit 1）——ECharts `buildTrajectoryOption` 6 处原裸 hex（`#8a96a8`/`#52617a`/`#e6eaf0`/`#ff4d4f`/`#2ec27e`/`#3d8bff`）**全部** → `lightTokens.muted/fg2/border/up/down/accent`（:138-151），A 股红涨绿跌用 `lightTokens.up`（红）/`down`（绿）配 `color/color0`。
3. **suying-app.css 新增 .alert-\*/.mt6 全 token 化**（W-3 教训也吸取）：`.alert-dot/.alert-dot.warn/.down/.up` 全走 `var(--accent)/--warn/--down/--up`，`.alert-copy strong/span` 走 `var(--fg)/--fg-2`，`.alert-time` 走 `var(--muted)`——**零裸 rgba**（对比第一波 .rc-badge 的 W-3 裸 rgba，本波纠正）。

**对比第一波**：W-1（半 token 化）/W-2（ECharts 裸 rgba）/W-3（CSS 裸 rgba）三个 token warning 在第二波**均未复现**。dev 把第一波 feedback 真正内化进第二波实现，不是口头声称。第一波遗留的 W-1/W-2/W-3 已进 task #10（Batch B token 收口），不阻塞第二波。

## 代码 verdict: approve

**无 critical / 无 warning / 0 suggestion**。

### 认可的良好设计

1. **OpenDecision buildAiSentimentReasons**（OpenDecision.tsx:293-325）：从 signal/live 评分 + 板块共振 + 候选数派生 3 条支撑原因，缺字段显式 `fallback_reason：…`（:308/:315/:322），**不空白不演示**——与第一波 Dashboard.buildSentimentReasons 同款诚实降级模式，复用得当。
2. **OpenDecision 候选池消费契约 §9.3**（OpenDecision.tsx:432-433）：`screenerApi.queryCandidatePool({ source_module: 'open-decision', page: 1, page_size: 50 })`——入参**只** source_module/page/page_size，**无** tenant/owner/trade_account 明文（reviewer grep 入参 shape 确认）；scope 由后端拦截器头注入。与 chain 候选多源融合按 code 去重（candidateRowsFromPool）。
3. **Predictions 候选池预测排行**（Predictions.tsx:278）：`queryCandidatePool({ source_module: 'screener', page_size: 20 })`——同样无明文 scope。两处消费均守契约。
4. **Predictions 2 KPI 诚实降级**（Predictions.tsx:202-208）：今日预测任务=`poolCandidates.length`（真实计数）、近30次方向正确率=backtest direction_accuracy 字段未齐 → `'--'` + `overviewKpiFallback`（"后端命中率/预测数字段尚未就绪，先以候选池条目计数展示"），**不展示假数**（W-1 同款诚实降级）。
5. **EmptyState 兜底全覆盖**（team-lead 第 4 项）：OpenDecision 候选池空 → `EmptyState` + `empty_state.reason`（:1116-1120，含 error/poolEmptyReason/默认 fallback 三级文案）；Predictions 候选池空 → "暂无候选池预测排行"、预警空 → "暂无预警"。

### 临界区零越界

dev-1b / dev-3b 各自独立 worktree，独占自家 page；临界区（`api/client.ts`/`api/types.ts`/`components/prototype/*`/`tokens.ts`）**未触碰**——`queryCandidatePool`/`CandidatePoolQueryResponse`/`lightTokens` 均 HEAD 已就绪仅 import 消费。per-file git add（未 stash/add -A）。

## SIT Audit verdict: ✅ Pass

### 4 项 audit

1. **progress 完整性** ✅
   - `progress/frontend-dev-1.md` 含 `BatchA-OpenDecision` 完整 SIT 段（8 AC + 质量门 3 命令 + 契约纪律自检 + worktree 纪律自检）。
   - `progress/frontend-dev-3b.md` 含 `## SIT 证据` 段（7 AC + tsc/vitest/dev server 三段证据 + 全仓回归）。
   - 两段均非空、按 AC 列条目。

2. **AC 覆盖** ✅
   - OpenDecision 8 AC（2.1×3 区块/AI 原因/token + 2.4×3 契约/去重/EmptyState + tsc/vitest/SIT）逐条对应 `opendecision-preview.test.tsx`（2.1×3 + 2.4×3，6 SIT 用例）+ `OpenDecision.test.tsx` +3 unit。
   - Predictions 7 AC（5.0 区块/fallback/token/tsc/vitest/SIT/回归）逐条对应 `predictions-preview.test.tsx` 3 用例 + `Predictions.test.tsx` +2 unit。

3. **证据可信度** ✅
   - 命令 + 真实输出片段齐全：tsc exit 0、vitest `Test Files X passed / Tests Y passed` 计数（dev-3b 给到全仓 332/332 + 本波 7/7 + 3/3 分层计数）、dev server `curl /src/pages/Predictions.tsx → HTTP 200` + `curl /predictions → HTTP 200`。
   - **非** placeholder——真实工具真实输出。
   - reviewer 自跑 tsc=0 / vitest 341 绿**复现一致**（commit message 341 = 第一波 327 + 第二波 14，账对得上）。
   - 注：dev-3b 自报"全仓 332/332"，但那是其 worktree base `48d47535`（第一波）时刻数；commit 223189b6 fan-in 后主仓全量是 341（含第二波 14 新增）——**非矛盾**，是 worktree base vs fan-in 后的时间差，dev-3b 已标注"本仓前端 API client 手写 typed wrapper（无 orval/MSW），SIT 用 vitest + vi.mock client"如实说明契约现实。

4. **失败/阻塞标记真实性** ✅
   - dev-1 OpenDecision 段延续标记 PrototypeRoutes pre-existing（第一波已知，本波未触碰临界区）。
   - dev-3b 如实标注本仓无 orval/`*.msw.ts`（手写 typed wrapper），SIT 用 vi.mock client 而非 MSW——**如实暴露契约现实**，非粉饰。
   - 无 fail 伪装 pass；无 placeholder 伪装证据。

### 结论

4 项全过，verdict **✅ Pass**。

## verdict 推导（第二波）

- critical_count: 0
- warning_count: 0
- suggestion_count: 0
- code_verdict: **approve**
- sit_audit_verdict: **✅ Pass**

## 下一步

回 team-lead：第二波 **verdict approve**（零 finding），W-1 教训真落实（两页零裸色 + ECharts 全 lightTokens + CSS 全 var(--*)），tsc 0 + vitest 341/341 自跑复现。SIT Audit ✅ Pass。可与第一波合并推进 E2E。第一波 W-1/W-2/W-3 + S-1 仍走 task #10 Batch B token 收口。

---

# Batch B — #11 watchlist + #12 产业链 + #13 schema fix 质量+SIT Audit

## 审查对象

- `610c1c00` #11 watchlist 表 + REST（POST/GET/DELETE）— 6 文件 +1011
- `aa78d31f` #12 产业链 SupplyChainBom 4.2 chain-deconstruct 三模式 + token 化 — 3 文件 +468/-72
- `3e7a13c5` #13 alembic 006/008 幂等修复（UAT crash-loop 解除）— 3 文件 +75/-14

## 复跑证据（reviewer 自跑）

| 项 | 命令 | 结果 |
|---|---|---|
| tsc | `cd frontend && npx tsc -b --noEmit` | **TSC_EXIT=0（0 错）** ✅ |
| vitest 全量 | `cd frontend && npx vitest run` | **54 files / 346 tests 全绿** ✅ |
| pytest watchlist | `pytest tests/test_watchlist_api.py -v` | **12/12 passed**（含 scope 隔离 ×3）✅ |
| pytest screener 全量 | `pytest tests/` | **185 passed / 5 failed** |
| SupplyChainBom 裸色 grep | `grep -nE '#[0-9a-fA-F]{3,8}\|rgba?\(\|rgb\('` | **2 hit**（ACCENT_OVERLAY 命名常量，token 派生注释）|

**5 failed 性质裁定**：`test_candidate_contract.py::test_screener_contract_adds_model_metadata_freshness_and_fallback`（硬编码 trade_date=2026-06-21 日期漂移）+ `test_llm_multi_provider.py` ×4（环境无 openai 包）。`git show 610c1c00 aa78d31f 3e7a13c5 --name-only | grep` 确认 Batch B **未触碰**这两个文件，最后改动在无关 commit `64a8c572`——**pre-existing，非本批引入**，与 dev-1 M0 段已记录的 5 pre-existing 同源（dev-1 已做 stash 验证）。

## #12 产业链 token 一致性（W-1 复核）：✅ Pass（透明披露 2 命名常量）

dev-5 声称「0 裸 #hex/rgba，echarts lightTokens」。复核**实证通过**：

1. **SupplyChainBom.tsx 全文仅 2 处 rgba**（:42-43）——且**非内联散落字面量**，是模块顶命名常量 `ACCENT_OVERLAY`/`ACCENT_OVERLAY_SOFT`，带显式注释「token 派生自 lightTokens.accent #3d8bff」。这是 W-2（alpha 变体）的**正确缓解形态**——比第一波 Signals.tsx 内联裸 rgba（W-2 finding）更规范：集中、命名、可追溯。仍建议进 task #10 在 tokens.ts 补 `accentAlpha45`/`accentAlpha28` 派生常量彻底收口，但**非本批阻断项**。
2. **lightTokens 引用 39 处**（grep 计数）——echarts option + 容器 border/surface/radius 全走 `lightTokens.*`；原重灾区 `#f0f0f0`/`#fff`/`#722ed1`/`#d4380d`/`#1677ff` 等 14 个裸色 dev-5 声称全清，spot-check inline style=（:775/:802/:832/:836/:853）确认 border/background/color 均读 lightTokens，**认可**。
3. **EmptyState 兜底**（team-lead 第 4 项）：`filteredNodes.length === 0`（:831）走占位 EmptyState，命中。

**W-1 教训第三次落实**——dev-5 在本批主动把「2 命名常量」如实写进 AC②（非声称"零裸色"），是诚实降级，非粉饰。

## #11 watchlist scope 隔离：✅ Pass

`services/screener-service/app/routers/screener.py:6953/7101/7232` 三个端点 scope 全部从 `X-Tenant-Id`/`X-Owner-User-Id`/`X-Trade-Account-Id` Header 注入，**前端不传明文**（:6953/7162 注释「scope 全部从认证头注入，前端绝不传明文」）。scope 隔离 3 测试 reviewer 自跑全绿：
- `test_get_scope_isolation_account_a_invisible_to_account_b`（账户 A private 自选 → B 查 total=0）
- `test_get_public_visibility_cross_account_visible`（public 跨账户可见）
- `test_delete_by_code_blocked_for_other_scope`（A 加的 B 删不掉 deleted=0，不泄露存在性）

DELETE scope 归属校验在 store 层（WHERE scope 过滤），不靠 router 层判断——**纵深防御得当**。watchlist_store 仿 candidate_pool_store 的 visibility/data_scope 矩阵，复用成熟模式。migration 022 幂等处理 latent bug（DB 已有 4 列 legacy watchlist 表）——dev 发现并处理，**非踩坑后补**。

## #13 schema fix（UAT 解阻塞）：✅ Pass

UAT crash-loop 根因诊断清晰（init_postgres.sql 预建表 + alembic 006/008 重复定义 → DuplicateColumn/multiple PK → 迁移回滚 → 无 alembic_version/auth 表 → seed admin 失败）。治标 A 修复手法正确：
- **006**：`op.add_column` → `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` + 显式 PG 类型映射（Double→DOUBLE PRECISION 等）
- **008**：PG 的 `ADD CONSTRAINT` 无 `IF NOT EXISTS`，用 `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE contype='p')` 守卫——**PG 方言正确处理**

治本 B（init SQL 不预建表）已诚实标为 follow-up issue，不混入本 task。**修复手法专业，非 hack**。

## 代码 verdict: approve（#11/#12/#13 三项）

**无 critical / 无 warning / 0 suggestion**。

唯一可记项：SupplyChainBom.tsx:42-43 的 2 个 ACCENT_OVERLAY 命名常量——但这是 W-2 的规范缓解形态（集中+命名+注释），非散落内联，**不构成 warning**，归 task #10 tokens.ts alpha 派生常量收口。

### 认可的良好设计

1. **#13 根因诊断 + 方言正确**：PG `ADD CONSTRAINT` 无 `IF NOT EXISTS` 用 DO 块守卫——比硬试 `ADD CONSTRAINT IF NOT EXISTS`（PG 不支持会炸）专业。
2. **#11 migration 022 幂等 + latent bug 前置处理**：发现 legacy 4 列 watchlist 表，改 create_table 为 ADD COLUMN + alter_column，避免 CREATE INDEX 因列不存在炸——**先于测试发现**。
3. **#11 scope 纵深防御**：DELETE 归属校验在 store 层 WHERE，不靠 router；不泄露存在性（deleted=0 而非 404）。
4. **#12 三模式专属渲染**：upstream graph / value_chain bar / competition scatter 三 echarts option 类型互不相同（SIT 断言），非通用壳套数据。
5. **#12 诚实降级披露**：dev-5 AC② 主动写「仅剩 2 处命名常量（token 派生）」，非声称"零裸色"——诚实度高于第一波。

## SIT Audit verdict: ✅ Pass

### 4 项 audit

1. **progress 完整性** ✅
   - `progress/backend-dev.md` 含 #13（顶部 §1）+ #11（§BatchB-watchlist）两段完整 SIT，按 AC 列条目 + 真实命令 + 输出片段。
   - `progress/frontend-dev-5.md` 含 #12（顶部 §BatchB task #12）完整 SIT，AC② 诚实披露 2 命名常量。
   - 三段均非空、按 AC 列。

2. **AC 覆盖** ✅
   - #11：6 AC（migration 022/POST/GET/DELETE/scope 隔离/前端临界区）逐条对应 12 测试 + 真实 PG round-trip。
   - #12：5 AC（三模式专属/token 化/tsc/vitest/EmptyState）逐条对应 chain-decompose-preview SIT 5 用例 + 16 unit。
   - #13：根因诊断 + 5 步正向路径验证（fresh DB → init SQL → alembic upgrade head 001→022 → 戳/auth 表/列/PK 验证 → backend seed admin + /health 200）。

3. **证据可信度** ✅（**本批最强项**）
   - **#13 是真实 PG fresh scratch db 全正向路径**：`DROP/CREATE DATABASE scratch_schema_test` → `psql -f init_postgres.sql` → `alembic upgrade head`（001→022 全通，原 006 DuplicateColumn / 008 multiple PK 已消）→ `alembic_version: 022` 戳 → auth 表齐 → `outcome_at present: True` → `pledge_detail_pkey` → backend `GET /api/health → 200 {"status":"healthy"}` + `admin user seeded`。**非 mock，非 fixture，真实 PG round-trip**——可信度顶级。
   - **#11 真实 PG round-trip**：ADD/UPSERT/query(A=1,B=0)/delete 全跑出预期值，migration upgrade/downgrade 可逆验证（`alembic downgrade -1 && upgrade head`）。
   - **#12** tsc exit 0 + vitest 21/21 + 全量 346/346 + dev server curl HTTP 200。
   - reviewer 自跑 tsc=0 / vitest 346 / pytest watchlist 12/12 **复现一致**。

4. **失败/阻塞标记真实性** ✅
   - dev-1 #11 段如实标记全量 5 pre-existing failed（candidate_contract 日期漂移 + llm_multi_provider 无 openai 包），与 M0 段同源 stash 验证记录一致。
   - #13 如实标「治本 B follow-up issue，不在本 task」——不冒充彻底解决。
   - #12 如实披露 2 ACCENT_OVERLAY 命名常量未彻底 token 化——非声称零裸色。
   - 无 fail 伪装 pass；无 placeholder 伪装证据。

### 结论

4 项全过，verdict **✅ Pass**。#13 的真实 PG fresh-db 正向路径证据是本批（乃至本会话三批 review 中）可信度最高的 SIT 证据。

## verdict 推导（Batch B）

- critical_count: 0
- warning_count: 0
- suggestion_count: 0
- code_verdict: **approve**（#11/#12/#13 三项全 approve）
- sit_audit_verdict: **✅ Pass**

## 下一步

回 team-lead：Batch B **verdict approve（零 finding）**，tsc 0 + vitest 346/346 + pytest watchlist 12/12（含 scope 隔离 ×3）自跑复现；screener 全量 185 passed / 5 failed 经裁定为 pre-existing（Batch B 未触碰，无关 commit 64a8c572 引入）。W-1 第三次落实（SupplyChainBom 2 命名常量诚实披露）。SIT Audit ✅ Pass（#13 真实 PG fresh-db 正向路径证据可信度顶级）。#13 UAT crash-loop 已解除，可继续 UAT/E2E。SupplyChainBom 2 ACCENT_OVERLAY 常量归 task #10 tokens.ts alpha 派生收口（非本批阻断）。

---

# Batch C — #23 Screener 3.2/3.3 + #24 Predictions 5.1/5.2/5.3 质量+SIT Audit（W-1 第三次复核）

## 审查对象

- `47422493` #23 Screener 3.2 model-compare + 3.3 factor-analysis 专属渲染 + token 化
- `533038df` #24 Predictions 5.1 single-stock + 5.2 multi-compare + 5.3 backtest

## 复跑证据（reviewer 自跑）

| 项 | 命令 | 结果 |
|---|---|---|
| tsc | `cd frontend && npx tsc -b --noEmit` | **TSC_EXIT=0（0 错）** ✅ |
| vitest 全量 | `cd frontend && npx vitest run` | **57 files / 371 tests 全绿** ✅ |
| Screener 裸色 grep | `grep -nE '#[0-9a-fA-F]{3,8}\|rgba?\(\|rgb\(' src/pages/Screener.tsx` | **exit 1（0 hit）** ✅ |
| Predictions 裸色 grep | 同上 src/pages/Predictions.tsx | **exit 1（0 hit）** ✅ |
| tokens.ts #10 收口 | grep signalLevelTokens/alpha | **已落地**（tokens.ts:59,69）✅ |

**注**：dev-5 #23 自报全仓 "363/363（56 files）"，dev-1 #24 自报 vitest "Predictions 11 + SIT 4"；reviewer 自跑主仓（#23+#24 都已 fan-in）371/371（57 files）= 363 + #24 新增 8（11-3 净增+4 SIT 等对得上）——同前两波 worktree-base vs fan-in 后时间差，**非矛盾**。

## W-1 第三次复核结论：✅ 真落实 + task #10 token 收口已闭环

本批是验证「W-1 教训是否制度性沉淀」的关键，复核**全过**：

1. **task #10 token 收口已落地**（tokens.ts:59-72）：
   - `signalLevelTokens` 把第一波 W-1 的 6 档信号评级色（STRONG_BUY/BUY/HOLD/REDUCE/SELL/TIMING_ALERT）统一收口为 token 常量——STRONG_BUY→`lightTokens.up`、BUY→`lightTokens.warn`、HOLD→`lightTokens.accent`、SELL→`lightTokens.down`（A 股语义），REDUCE/TIMING_ALERT 仍 hex 但**作为 token 定义层合规**（注释「page 层禁裸 hex 统一走此组；本处是 token 定义，hex 合规」）。
   - `alpha` 工具函数（`accent/up/down/warn: (a) => rgba(...)`）——**根治 W-2**：ECharts 透明叠层（置信带/阴影/柱底纹）不再写裸 rgba，统一走 `alpha.accent(0.12)` / `alpha.up(0.55)`。
2. **Screener.tsx 全文 0 裸色**（grep exit 1）——3.2/3.3 echarts（IC 柱图/相关性热力图）走 `lightTokens` + `alpha.accent(0.5)`（shadowColor）；模型 chip 4 档色走 `signalLevelTokens`（Screener.tsx:20 import / :296 注释 / :565 alpha 用法）。
3. **Predictions.tsx 全文 0 裸色**（grep exit 1）——5.1 ±1σ 置信带 `alpha.accent(0.12)`、K线 candlestick `alpha.up(0.55)`/`alpha.down(0.55)`、5.2 叠加曲线、5.3 偏离带 `alpha.accent(0.08)` 全走 alpha 工具（Predictions.tsx:135/152/159/200）；信号评级色走 `signalLevelTokens`（:622 注释）。

**W-1/W-2 三批演进闭环**：第一波（W-1 半 token 化 + W-2 内联裸 rgba）→ 第二波（吸取，两页零裸色但 alpha 变体仍内联或命名常量）→ 第三波（task #10 收口 `alpha` 工具 + `signalLevelTokens`，本批两页全用）。**教训从 ad-hoc 修复升级为 token 体系制度**——这是 review 期望的最佳终态。

## 代码 verdict: approve（#23/#24 两项）

**无 critical / 无 warning / 0 suggestion**。

### 认可的良好设计

1. **task #10 token 收口设计**（tokens.ts:59-72）：`alpha` 函数式工具比 Batch B 的 `ACCENT_OVERLAY` 命名常量更通用（任意 alpha 值），`signalLevelTokens` 把散落页面的评级色集中到 SSOT。**W-1/W-2 的根治方案**。
2. **#23 3.3 factor-analysis 数据源诚实降级**（dev-5 设计决策 :71）：screener-service 无独立 IC 接口（training_mock 返空），factors tab 复用 model-compare picks 的 `factor_breakdown` 派生 IC/ICIR/t-stat——**如实标注数据源限制**，非假装有独立接口。
3. **#24 5.3 backtest 不展示假图**（Predictions.tsx:255-279）：后端 metrics 暂无逐日序列 → 预测/实际走势 + 最近命中序列走 EmptyState；4 项统计后 3 项字段未齐 → `'--'` + fallback_reason——**诚实降级，不伪造回测曲线**。
4. **#24 三 sub-tab 专属渲染**：single（信号一致性/因子贡献卡）/ compare（置信度列+叠加曲线）/ backtest（命中序列/预测vs实际）各有专属区块，SIT 断言切换 tab 各自渲染。
5. **#23 echarts formatter 类型处理**（dev-5 :74）：`TopLevelFormatterParams` union 用 `(p as unknown as {...}).value` unknown 中转 cast——tsc strict 通过，非 `any` 逃避。

### EmptyState 兜底（team-lead 第 4 项）

- **Screener**：3.2/3.3 每段缺数据走 `prototype-fallback` 类（与 EmptyState 同款结构化占位）——模型无候选（:1387）、矩阵空（:1436）、IC 无数据（:1471）、ICIR 无（:1501）、相关性 <2 因子（:1512）、分层不足（:1544）、行业缺字段（:1575）**7 处覆盖**。
- **Predictions**：5.1 三卡（信号一致性/因子贡献/辅助特征）+ 5.2 空结果 + 5.3（预测vs实际/命中序列/3 档误差）全走 `EmptyState` + fallback_reason（dev-1 AC⑧ :122）。

判：Screener 用 `prototype-fallback` 类（非 EmptyState 组件）是临界区风格选择——两者均为合规结构化空状态，语义等价，**不构成 warning**。若 team-lead 要求统一 EmptyState 组件可作 Batch D polish，非本批阻断。

## SIT Audit verdict: ✅ Pass

### 4 项 audit

1. **progress 完整性** ✅
   - `progress/frontend-dev-5.md` 含 #23 完整 SIT（8 AC + tsc/vitest/dev server 三段 + 21 测试分层计数 + 设计决策 + 改动文件）。
   - `progress/frontend-dev-1.md` 含 #24 完整 SIT（8 AC + 质量门 6 命令 + 契约/worktree 纪律自检）。
   - 两段均非空、按 AC 列条目。

2. **AC 覆盖** ✅
   - #23：8 AC（3.2 模型对比/3.3 因子分析/专属渲染/token 化/EmptyState/tsc/vitest/SIT）逐条对应 `model-compare-preview.test.tsx` 7 用例 + `factor-analysis-preview.test.tsx` 7 用例 + Screener unit 7。
   - #24：8 AC（5.1 single/5.2 compare/5.3 backtest/专属渲染/token/tsc/vitest/EmptyState）逐条对应 `Predictions.test.tsx` 11（7+4）+ `predictions-subtabs-preview.test.tsx` 4。

3. **证据可信度** ✅
   - 命令 + 真实输出片段齐全：tsc EXIT 0、vitest `Test Files X passed / Tests Y passed` 分层计数、dev server `curl /screener/{models,factors} → 200` + `curl /predictions/{single,compare,backtest} → 200/200/200`、`grep ... → ZERO`（W-1 机检）。
   - **非** placeholder——真实工具真实输出，含 grep 命令+结果这种可复现的机检证据。
   - reviewer 自跑 tsc=0 / vitest 371 / 两页 grep exit 1 **复现一致**。
   - dev-1 #24 AC⑤ 的 grep 命令（`'#[0-9a-fA-F]{3,8}\b|rgba?\('`）与 reviewer 用的同款，结果一致（ZERO）。

4. **失败/阻塞标记真实性** ✅
   - dev-5 #23 如实标注数据源限制（screener-service 无独立 IC 接口，复用 model-compare 派生）——**诚实暴露后端缺口**，非假装接口齐全。
   - dev-1 #24 如实标注 5.3 后端逐日/逐次字段未齐 → EmptyState + fallback——**不展示假图**。
   - dev-5 #23 标注 `NewUiModulePage.test.tsx` 旧标题断言随 preview 对齐更新（模型评分差异→共识矩阵）——**回归由 dev 主动修复并记录**。
   - 无 fail 伪装 pass；无 placeholder 伪装证据。

### 结论

4 项全过，verdict **✅ Pass**。

## verdict 推导（Batch C）

- critical_count: 0
- warning_count: 0
- suggestion_count: 0
- code_verdict: **approve**（#23/#24 两项全 approve）
- sit_audit_verdict: **✅ Pass**

## 下一步

回 team-lead：Batch C **verdict approve（零 finding）**，tsc 0 + vitest 371/371（57 files）+ 两页 grep 0 裸色自跑复现。**W-1 第三次落实 + task #10 token 收口闭环**——`signalLevelTokens` + `alpha` 工具把 W-1/W-2 从 ad-hoc 修复升级为 token 体系制度（三批演进：半 token 化 → 零裸色但内联 alpha → alpha 工具+signalLevelTokens SSOT）。SIT Audit ✅ Pass（两段证据含 grep 机检 + dev server 多路由 200 + 后端字段缺口诚实降级）。Batch A/B/C 三批全 approve，可推进 UAT/E2E。

---

# Batch B 补 6 — #25 Dashboard 1.2 auction + #26 OpenDecision subtabs SIT + #27 SupplyChainBom 4.1/4.3 质量+SIT（W-1 第四次复核）

## 审查对象

- `746ff6cd` #25 Dashboard 1.2 auction-dashboard 竞价意图 preview（dev-3）
- `e3fb8ad4` #26 OpenDecision 2.2/2.3/2.5 sub-tab SIT 补覆盖（dev-1b）
- `7e7d1dbe` #27 SupplyChainBom 4.1 policy-analysis + 4.3 company-analysis（dev-5 代码 PL 接手）

## 复跑证据（reviewer 自跑）

| 项 | 命令 | 结果 |
|---|---|---|
| tsc | `cd frontend && npx tsc -b --noEmit` | **TSC_EXIT=0（0 错）** ✅ |
| vitest 全量 | `cd frontend && npx vitest run` | **59 files / 380 tests 全绿** ✅ |
| #25 auction-dashboard SIT 用例数 | `grep -cE "it\(\|test\("` | **3**（dev 声称 3/3 一致）✅ |
| #26 opendecision-subtabs SIT 用例数 | 同上 | **6**（dev 声称 6 一致）✅ |
| #27 policy/company SIT 文件 | `ls tests/sit/\|grep -iE 'policy\|company'` | **CONFIRMED MISSING** |
| SupplyChainBom unit | `grep -cE "it\(\|test\("` | **16**（PL 声称 16/16 一致）✅ |

## W-1 第四次复核结论：✅ 真落实（#25/#27 零新裸色；Dashboard 残留是第一波 task #10 既知项）

1. **#25 Dashboard.tsx**：`git show 746ff6cd -- Dashboard.tsx | grep '^\+' | grep -E '#hex|rgba'` → **0 hit**（新增代码零裸色）。auction 4 区块 echarts（buildAuctionTimelineOption/buildAuctionRadarOption）走 `signalLevelTokens` + `alpha.up/accent` + `lightTokens`（progress AC③ 明示）。Dashboard.tsx 现存的 `#1a7a4c`/`#237804`/`rgba(82,97,122,0.45)`/`#b75d00` 等（grep 8 hit）是**第一波 W-1/W-2 既知残留**（toneFromScore/gauge 5-stop/sectorColor），**本批未触碰这些行**（git diff clean），仍归 task #10 收口——**非本批引入，不构成本批 finding**。
2. **#27 SupplyChainBom.tsx**：`git show 7e7d1dbe -- SupplyChainBom.tsx | grep '^\+' | grep -E '#hex|rgba'` → **0 hit**（新增 175 行零裸色）。全文唯一 hit 是 :41 `ACCENT_OVERLAY` 命名常量注释（Batch B #12 既知，token 派生，归 task #10 alpha 工具收口）。
3. **#26** 纯 SIT 测试补覆盖，无代码改动，token 不涉及。

**W-1 第四次落实**：dev-3 #25 + dev-5 #27 新增代码均零裸色，token 体系（signalLevelTokens + alpha + lightTokens）在第四批仍被严格遵守。task #10 的 `alpha`/`signalLevelTokens` 工具继续生效，证明第三波的制度化收口稳定。

## 代码 verdict: approve（#25/#26/#27 三项）

**无 critical / 无 warning / 0 suggestion**。

### 认可的良好设计

1. **#25 auction 4 专属区块**（Dashboard.tsx:597 auctionDimensionRows / :660 auctionSectorHeat / buildAuctionTimelineOption / buildAuctionRadarOption）：4 区块均走 auction 专属 helper，非通用壳；ECharts radar 四维评分（竞量比/委比/涨幅缺口/综合评分）+ line 撮合价走势 + sector-grid 行业热度。
2. **#25 EmptyState 兜底**（Dashboard.tsx:1390 `暂无板块竞价数据` + :1418 `暂无竞价明细`）：缺数据走 EmptyState + fallback_reason 文案，不空白。
3. **#26 SIT 补覆盖**：2.2 auction / 2.3 signal-scan / 2.5 execution 三 sub-tab 此前无 SIT（既有仅 2.1/2.4），本批补 `opendecision-subtabs-preview.test.tsx` 6 用例——**补既有 SIT 漏洞，非粉饰**。临界区零越界（sub-tab 渲染在 HEAD 533038df 已就绪，本任务仅补测试）。
4. **#27 policy/company 专属渲染**（SupplyChainBom.tsx:45 policy helpers / :102 company helpers / :220-222 tabs）：4.1 policy-analysis 走 TextArea+LLM 解读交互流（placeholder + `disabled={!policyText.trim()}` 输入守卫），4.3 company-analysis 走 CompanyResearchDrawer——**输入工具型流程**，非数据展示型，空状态表现为输入区+placeholder（可接受）。

### #27 SIT 缺判断：⚠️ Pass with concerns（非阻断，建议 follow-up 补 SIT）

**事实链**：
- dev-5 worktree 写了 +175 行代码（4.1/4.3 专属渲染）但**触发 429 限额 failed**，未 commit、未写 progress、未建 SIT。
- PL 接手验证采纳（7e7d1dbe）：tsc 0 + SupplyChainBom.test.tsx 16/16 绿，代码 token 化合规，commit 入主仓。
- **policy-analysis/company-analysis preview SIT 测试缺**（reviewer `ls tests/sit/` 确认无 policy/company 文件）。
- PL 在 `progress/product-lead.md:171` 如实标注「dev-5 代码 PL 接手 7e7d1dbe，dev-5 429 failed，tsc0+16绿，sit 缺 follow-up」。

**判级推理**：
- 严格按 SIT Audit 第 1 项「progress 完整性：缺失或为空 → block」——#27 dev-5 progress 段确实缺失。但本案例是**dev-5 限额中断 + PL 接手**的特殊情况，非 dev 跳过 SIT：代码已有 unit 覆盖（SupplyChainBom.test.tsx 16 用例，组件级渲染断言）、tsc 0、全量 380 绿、PL 透明记录 + follow-up 计划。
- 代码侧无正确性/安全性/token 缺陷（approve）；SIT 侧 #25/#26 两段证据完整可信（✅），#27 缺 policy/company preview SIT 是**局部瑕疵 + 合理解释**（429 不可控 + PL 接手 + unit 兜底 + follow-up 计划）——符合 3 档 verdict 中「⚠️ Pass with concerns：4 项主体通过但有局部瑕疵，写明 concern + 是否需 PL 决定补救」。
- **concern**：4.1/4.3 preview 对齐与交互在 integration 层未被 SIT 断言（policy LLM 解读流 / company drawer）。建议 PL 将 `policy-analysis-preview.test.tsx` + `company-analysis-preview.test.tsx` 纳入 follow-up（dev-5 限额恢复后补或 PL 建），不阻断当前 fan-in。

## SIT Audit verdict: ⚠️ Pass with concerns

### 4 项 audit（#25/#26/#27 合并）

1. **progress 完整性** ⚠️（#27 局部瑕疵）
   - #25 `progress/frontend-dev-3.md` :66-92 完整 SIT 段（7 AC + 质量门 3 命令 + 改动文件 + 契约对账）✅
   - #26 `progress/frontend-dev-1.md` :143-185 完整 SIT 段（AC + 质量门 + 契约/worktree 纪律自检）✅
   - #27 **dev-5 progress 段缺失**（429 中断未写）；PL 在 `product-lead.md:171` 代为标注 follow-up —— ⚠️ 局部瑕疵，有合理解释。

2. **AC 覆盖** ⚠️（#27 policy/company SIT 缺）
   - #25：7 AC（4 区块/专属渲染/token/EmptyState/tsc/vitest/SIT）逐条对应 `auction-dashboard-preview.test.tsx` 3 用例 ✅
   - #26：AC（2.2/2.3/2.5 integration + EmptyState + vitest）逐条对应 `opendecision-subtabs-preview.test.tsx` 6 用例 ✅
   - #27：4.1/4.3 专属渲染有 unit 覆盖（SupplyChainBom.test.tsx 16 用例组件级）但**无 policy/company 专属 preview SIT** ⚠️

3. **证据可信度** ✅
   - #25：tsc EXIT 0 + vitest `58 files / 374 tests`（dev-3 自报）+ Dashboard.test.tsx 11/11 + auction SIT 3/3 + worktree 独占记录。
   - #26：tsc 0 + vitest `tests/sit/ 47 passed（13 files）` + OpenDecision.test.tsx 19 + subtabs SIT 6 + dev server 多路由 200。
   - reviewer 自跑 tsc=0 / vitest 380 / SIT 用例数 3+6 一致 **复现通过**。
   - **非** placeholder——真实命令+计数+输出片段。

4. **失败/阻塞标记真实性** ✅
   - #27 dev-5 429 中断 + PL 接手**如实记录**（product-lead.md:171，非隐瞒）；sit 缺标 follow-up（非伪装 pass）。
   - #26 如实标注「3 sub-tab 渲染在 HEAD 533038df 已落地，本任务仅补 SIT」（非夸大本任务 scope）。
   - 无 fail 伪装 pass；无 placeholder 伪装证据。

### 结论

#25/#26 主体 ✅ Pass；#27 SIT 缺为 ⚠️ 局部瑕疵（429 不可控 + PL 接手 + unit 兜底 + follow-up 计划）。综合 **⚠️ Pass with concerns**——代码可推进，建议 PL 安排 #27 policy/company preview SIT 补建为 follow-up。

## verdict 推导（Batch B 补 6）

- critical_count: 0
- warning_count: 0
- suggestion_count: 0
- code_verdict: **approve**（#25/#26/#27 三项代码全 approve）
- sit_audit_verdict: **⚠️ Pass with concerns**（#27 policy/company preview SIT 缺，建议 follow-up 补建）

## 下一步

回 team-lead：Batch B 补 6 **代码 verdict approve（零 finding）**，tsc 0 + vitest 380/380（59 files）自跑复现。W-1 第四次落实（#25/#27 零新裸色；Dashboard 残留是第一波 task #10 既知项，本批未触碰）。SIT Audit **⚠️ Pass with concerns**——#25/#26 证据完整可信，#27 policy/company preview SIT 缺（dev-5 429 中断 + PL 接手 + unit 16/16 兜底 + follow-up 计划），建议 PL 安排补建为 follow-up，不阻断当前 fan-in。
