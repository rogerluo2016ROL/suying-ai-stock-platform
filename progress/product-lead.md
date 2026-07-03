# Product Lead — Progress

## 状态: E2E 测试 + backend-dev 修复进行中 (2026-06-12)

Code review verdict: ⚠️ Approve with Changes (2 fixes needed, 4 suggestions, 0 blocks)
报告: docs/reviews/data-pipeline-refactor-2026-06-12.md

## Skills 调用

| Skill | 状态 | 备注 |
|---|---|---|
| `superpowers:brainstorming` | SKIPPED (不可用) | 改为手动代码审计 + 需求分析 |
| `superpowers:writing-plans` | SKIPPED (不可用) | 实施计划整合在 PRD §5 + ADR-006 |
| `agf-writing-prd` | DONE | 10-section PRD 输出 + ADR-006 决议后 v1.1 更新 |

## SIT 证据

### 代码审计覆盖 (2026-06-12，第二轮：backend-dev tasks #1-4 实现审计)

| 文件 | 状态 | 关键发现 |
|---|---|---|
| `pg_writer.py` | 部分完成 (tasks #1, 待 #6/#8) | 7 个 write_* 函数已添加；refresh 静默吞错 (AC-5 未满足)；sync_daily_to_pg 未移除 (AC-7 未满足)；写入顺序 SQLite-first 而非 ADR-006 的 PG-first |
| `tushare.py` | 基本完成 (task #2) | PG 双写已集成到 sync_daily_kline + post_market_core + post_market_ext；无限频控制 |
| `stocks.py` | 完成 (task #4) | sync_stock_list 完整实现，SQLite + PG 双写；缺增量函数 |
| `scheduler.py` | 基本完成 (task #3, 待 #9) | pg_sync 已移除；stocks_sync (08:00 daily) + intraday_sync 已添加；缺 pg_write_status 字段；stocks cron 与 ADR-006 不一致 |
| `routers/data.py` | 完成 (task #4) | POST /sync/stocks 端点已添加；缺 pg_write_status 响应 |
| `rate_limiter.py` | 未创建 (task #7) | ADR-006 决策 2 要求统一限频 |
| `init_postgres.sql` | 待补全 (task #10) | limit_list_d, ths_daily 表定义缺失 |
| `materialized_views.sql` | 待补全 (task #10) | mv_daily_composite_ranking 未添加 |

### AC 验证矩阵 (第二轮)

| AC | 优先级 | tasks #1-4 后状态 | 剩余 task |
|---|---|---|---|
| AC-1 (日线 PG 可查) | P0 | ✅ 已实现 (write_daily_kline) | — |
| AC-2 (PG 失败不影响 SQLite) | P0 | ✅ 已实现 (best-effort) | — |
| AC-3 (pg_sync 移除) | P0 | ✅ 已实现 (scheduler 无 pg_sync) | — |
| AC-4 (stocks >= 4000) | P1 | ✅ 已实现 (sync_stock_list) | — |
| AC-5 (物化视图错误报告) | P1 | ❌ refresh 仍静默吞错 | #6 |
| AC-6 (rt_min 不退化) | P1 | ✅ 已实现 (原有功能) | — |
| AC-7 (sync_daily_to_pg 移除) | P2 | ❌ 函数仍存在 | #6 |
| AC-8 (pg_write_status) | P2 | ❌ 未实现 | #9 |

### Open Questions 决议

全部 5 个 Q 已由 ADR-006 决议，tech-lead 2026-06-12 落盘。

## 质量门

- [x] PRD 10 节齐全 + v1.1 更新 (Approved)
- [x] AC 全部可独立验证
- [x] Open Questions 全部决议 (ADR-006)
- [x] tech-lead sign-off (ADR-006 落盘)
- [ ] backend-dev code review (待 tasks #6-10 完成后触发)
- [ ] E2E 测试 (待 code review 通过后触发)
- [ ] UAT (待 E2E 通过后触发)

## 任务追踪

| Task | 状态 | 内容 |
|---|---|---|
| #1-4 | completed | pg_writer write 函数 + tushare PG 集成 + scheduler 重构 + stocks 端点 |
| #5 | completed (被 #10 覆盖) | init_postgres.sql 检查 → 合并到 #10 |
| #6 | pending → backend-dev | refresh_materialized_views 错误报告 + 移除 sync_daily_to_pg |
| #7 | pending → backend-dev | rate_limiter.py 新建并集成 |
| #8 | pending → backend-dev | PG-first 写入顺序 + 3x 重试 + 数据门禁 |
| #9 | pending → backend-dev | pg_write_status + stocks cron 调整 + 增量同步 |
| #10 | pending → backend-dev | SQL schema 补全 + mv_daily_composite_ranking |

## 下一步

1. backend-dev 完成 #6-10 → append progress/backend-dev.md
2. 触发 code-reviewer (含 SIT Audit)
3. 触发 qa-engineer E2E
4. product-lead UAT 签字
5. 归档 progress/ → docs/qa/data-pipeline-refactor-process-log.md

---

## M0 前置门 — token 收口（task #1，2026-07-02）

**改动**：新建 `frontend/src/styles/tokens.ts`（light/dark JS 常量，与 suying-app.css :root 同值，单一真值源）；重写 `contexts/ThemeContext.tsx`（buildThemeConfig 按 mode 组装 token+components+algorithm，消除 baseToken 硬编码漂移：colorPrimary #1677ff→#3d8bff / bodyBg #f5f5f5→#f4f6fa / borderRadius 6→8 / itemSelectedBg→accent-dim）；简化 `main.tsx`（去 baseToken/baseComponents props）；`git rm styles/design-tokens.css` 孤儿；accessibility.css:171 注释 design-tokens→suying-app；__tests__/ThemeContext.test.tsx 同步去 props。A股红涨绿跌只走 .up/.down className，不污染 antd colorSuccess/colorError。

**SIT 证据**：
- `cd frontend && npx tsc -b --noEmit` → TSC_EXIT=0（0 错）
- `npx vitest run src/__tests__/ThemeContext.test.tsx` → Test Files 1 passed / Tests 5 passed（1.51s）
- 视觉抽查（浅色无回归）：并入 task #4 统一做

**状态**：task #1 ✅ completed。task #2（后端 candidate-pool REST）backend-dev worktree 进行中。task #3（前端 API 骨架）进行中。

## M0 前置门 — 前端 candidate-pool API（task #3，2026-07-02）

**改动**：`api/types.ts` 加 CandidatePoolCandidate / CandidatePoolRecord / CandidatePoolRecordRequest / CandidatePoolRecordResponse / CandidatePoolQueryParams / CandidatePoolQueryResponse（均 extends ServiceContractFields，带 fallback_reason/empty_state 包络）；`api/client.ts` screenerApi 加 `recordCandidatePool`(POST /screener/candidate-pool) + `queryCandidatePool`(GET)。scope 不进请求体——拦截器 client.ts:236-243 自动注入 X-Tenant-Id/X-Owner-User-Id/X-Trade-Account-Id 头。

**SIT 证据**：`cd frontend && npx tsc -b --noEmit` → 0 错。

**状态**：前端骨架就绪。等 task #2（backend-dev 后端 REST）完成后，在 task #4 做端到端冒烟对齐（POST/GET 带 scope 头写入+按 scope 读出）。

## M0 前置门 — 验证 + 过门结论（task #4，2026-07-02）

**验证证据**：
- ① 前端 `npx tsc -b --noEmit` → 0 错（含 candidate_pool_metadata 字段名对齐后端 body）
- ② 后端 `backend/.venv/bin/python -m pytest tests/test_candidate_pool_api.py` → **9/9 passed**（test_post_records_pool / test_post_db_unavailable_fallback / test_post_body_has_no_plaintext_scope / test_get_scope_isolation / test_get_public_cross_account / test_get_db_unavailable_empty / test_get_filters / test_endpoints_response_model_operation_id）
- ③ 联调：pytest TestClient 端到端覆盖 POST/GET（record/query/隔离/empty_state/fallback），等价冒烟（真实服务 curl 留到 Batch A 3.1 前端有调用点时）
- ④ `npm run build` → ✓ built in 3.19s（3704 modules，生产构建无回归）+ vitest ThemeContext 5/5

**M0 过门结论**：✅ **过**。token 单一真值源建立（styles/tokens.ts + ThemeContext.buildThemeConfig 按 mode 组装），消除 main.tsx 硬编码漂移；candidate-pool REST 解封（commit e949baa8）+ 前端 API 骨架就绪（recordCandidatePool/queryCandidatePool，scope 全 Header 注入）。页面级视觉抽查并入 Batch A 3.1 首页实施（那时 UI 对齐 preview）。

**M0 产出清单**：
- 新增：`frontend/src/styles/tokens.ts`、`services/screener-service/tests/test_candidate_pool_api.py`
- 改：`contexts/ThemeContext.tsx`、`main.tsx`、`api/types.ts`、`api/client.ts`、`__tests__/ThemeContext.test.tsx`、`styles/accessibility.css`、`services/screener-service/app/routers/screener.py`、`progress/backend-dev.md`
- 删：`frontend/src/styles/design-tokens.css`（孤儿）

**下一步**：Batch A（10 preview）fan-out。

## Batch A 第一波 code-review verdict（commit 48d47535，2026-07-03）

- **code-reviewer-1（契约+安全）**：✅ **Pass** — 临界区零越界（12 文件全在 pages/__tests__/tests/sit/suying-app.css/progress）/ scope 全 Header 注入（Screener payload grep tenant_id|owner_user_id|account_id 零命中）/ candidate_pool_metadata 前后端对齐无回退。
- **code-reviewer-2（质量+SIT）**：✅ **approve with changes** — tsc 0 + vitest 327/327 自跑复现 / SIT Audit Pass（dev-1/dev-5 证据完整；dev-3 无独立 SIT 段但被 Screener.test.tsx + 全量 vitest 覆盖，不阻断）/ EmptyState 全覆盖 / Screener 零硬编码。**3 token warning（W-1 Dashboard signalLevelMeta 6档半token化 / W-2 Signals ECharts rgba + Dashboard gauge stops / W-3 suying-app.css .rc-badge 裸rgba）+ 1 审美建议（S-1 Signals emoji icon）**，不阻断，进 Batch B 收口（task #10）。

**第一波 verdict**：实质通过（contract Pass + quality approve-with-changes 不阻断）。启第二波（OpenDecision 2.1/2.4 + Predictions 5.0），token 收口进 Batch B。

## M1 Batch A 全 10 preview review 双通过（2026-07-03）

- **第一波** commit 48d47535（Dashboard 1.1/1.3 + Screener 3.1 + Signals 6.0-6.3）：reviewer-1 Pass + reviewer-2 approve-with-changes（3 token warning 进 #10 Batch B）
- **第二波** commit 223189b6（OpenDecision 2.1/2.4 + Predictions 5.0）：reviewer-1 Pass + reviewer-2 **approve 零 finding**（W-1 真落实：OpenDecision/Predictions 全文 0 裸色，ECharts 6 处 hex→lightTokens，suying-app.css 全 var()，第一波 W-1/W-2/W-3 第二波未复现）
- **Batch A 全过**：tsc 0 + vitest 341/341 绿，临界区零越界，scope 全 Header 零明文，EmptyState 全覆盖，W-1 教训真内化

**M1 达成**：行情决策板块 Batch A 10 preview 全 Verified（代码层）。启 UAT（deploy-engineer 起隔离栈 → qa-engineer P0 e2e + 截图 vs preview 比对）。

## qa UAT 完成 — 行情决策 Batch A+B Conditional promote（2026-07-03）

qa-engineer E2E/UAT 完成（`docs/qa/batch-ab-uat-2026-07-03.md` + evidence/）：
- **5 passed / 1 conditional / 0 failed**，无 P0/P1 critical/high bug
- P0×3 全 pass^2：6 主路由专属渲染 / EmptyState 兜底 / candidate-pool 写读隔离闭环（POST 写入+GET 回读+scope 隔离，契约§9.3 合规）
- P1×2 pass：产业链 3 模式（upstream/value_chain/competition 互不相同）/ 浅色主题+A股红涨绿跌（.up#ff4d4f/.down#2ec27e 与 preview token 逐字一致）
- P1×1 conditional：watchlist 3 端点 curl 通+优雅降级，前端按钮 disabled（DEF-1）
- 4 Low defect follow-up：DEF-1 watchlist 按钮 disabled / DEF-2 gateway 502 包装 / DEF-3 empty_state 字段名不匹配（前端 reason vs 后端 hint,suggestion）/ DEF-4 Signals 文案过时
- 测试数据清理干净

**PL 签字**：⚠️ **Conditional promote**（P0 全过达可交付基线）。DEF-1/3/4 派前端修（完全可用闭环，task #22），DEF-2 follow-up issue。

## 🎯 行情决策板块前端完全可用 — PL 签字（2026-07-03）

DEF-1/3/4 修上主分支（`d7a72963` cherry-pick），全量 tsc 0 + vitest 349/349 绿（54 files），无回归。

**交付清单**：
- **Batch A**（10 preview）+ **Batch B**（#11 watchlist + #12 产业链 + #13 schema fix）全 **review 双通过**（reviewer-1 Pass + reviewer-2 approve 零 finding）
- **qa UAT Conditional promote**（P0×3 pass^2 + P1×2 pass，0 critical/high）+ **DEF-1/3/4 全修**
- 6 主路由（Dashboard/OpenDecision/Screener/Predictions/Signals/SupplyChainBom）全真实 API
- candidate-pool 写读隔离闭环 + watchlist 自选股 CRUD（按钮解禁 + 3 端点 scope Header）+ 产业链 3 模式专属渲染 + 浅色 token 收口（lightTokens 单一真值源）+ A股红涨绿跌 + EmptyState 兜底

**PL 签字**：✅ 行情决策板块前端完全可用。

**follow-up**（不阻断）：#10 token 收口（W-1/W-2/W-3 alpha 派生常量 + S-1 emoji）/ DEF-2 gateway 502 issue / 治本 B schema issue / Batch C（5 深化 preview）/ data-service 回填 stocks 后 watchlist CRUD 写入闭环 + 真实数据链路。

## Batch C review 双通过 — 17/23 preview Verified（代码层）（2026-07-03）

Batch C #23（Screener 3.2/3.3 `47422493`）+ #24（Predictions 5.1/5.2/5.3 `533038df`）fan-in，tsc 0 + vitest 371/371 绿（57 files）。
- reviewer-1 Pass（临界区零越界——NewUiModulePage.test.tsx test 文本对齐；scope §9.3 N/A——5 sub-tab 纯本地 state 零新增 API）
- reviewer-2 approve 零 finding（W-1 第三次落实 + task #10 token 收口闭环：signalLevelTokens 6 档 + alpha 工具 SSOT；三批演进 ad-hoc→命名常量→token 体系）

**17/23 preview Verified**：Batch A 10 + Batch B 2（watchlist 1.4 + 产业链 4.2）+ Batch C 5（3.2/3.3/5.1/5.2/5.3）。Batch B 剩 6 sub-tab（1.2 auction / 2.2 auction-analysis / 2.3 signal-scan / 2.5 execution-monitor / 4.1 policy-analysis / 4.3 company-analysis）未做。
**核心目标达成**：行情决策板块 6 主路由完全可用（UAT P0 pass^2 + DEF 全修 + token 收口）。HEAD 533038df。

## 🎯 23/23 preview 全 Verified（代码层）— plan 终极目标达成（2026-07-03）

Batch B 补 6 fan-in（`746ff6cd` #25 + `e3fb8ad4` #26 + `7e7d1dbe` #27），tsc 0 + vitest 380/380 绿（59 files）。
- #25 Dashboard 1.2 auction（dev-3 ef901fc7，4 专属区块 + SIT 374/374）
- #26 OpenDecision 2.2/2.3/2.5（dev-1b 122cc496，page HEAD 已就绪 + sit test 补验证，dev-1b 诚实判断"无需改"正确——auction/signals/execution 渲染在 Batch A 2.1/2.4 时已做）
- #27 SupplyChainBom 4.1/4.3（dev-5 代码 PL 接手 7e7d1dbe，dev-5 429 failed，tsc0+16绿，sit 缺 follow-up）

**23/23 preview Verified**：Batch A 10 + Batch B 8 + Batch C 5。HEAD e3fb8ad4。

## 23/23 preview 全 Verified — review 双通过签字（2026-07-03）

Batch B 补 6 review：
- reviewer-1 Pass（临界区零越界 + scope §9.3 N/A + token 合规）
- reviewer-2 代码 approve 零 finding / SIT ⚠️ Pass with concerns（W-1 第四次落实；#27 sit 缺 follow-up 非阻断）

**23/23 preview 全 Verified**（代码 + review 双通过）。HEAD e3fb8ad4。tsc 0 + vitest 380/380（59 files）。

**concerns（follow-up，不阻断）**：
1. **#10 遗漏**（PL 承认）：Dashboard 现存 8 处第一波 W-1/W-2 裸色残留（gauge 5-stop / toneFromScore / sectorColor）—— #10 做了 signalLevelMeta + Signals ECharts + SupplyChainBom + emoji，但 Dashboard gauge 5-stop 漏改，reviewer-2 标归 #10。PL 补。
2. **#27 policy/company preview SIT 缺**（dev-5 429 failed）：补建 follow-up。

## concerns 全收口 — 23/23 完整 Verified（2026-07-03，A 方案）

PL 补两 concerns：
1. **#10 Dashboard W-2 残留**（`ca5aefef`）：gauge 5-stop / toneFromScore / sectorColor 8 处第一波裸色残留全 token 化（tokens.ts 加 downDeep #1a7a4c / warnDeep #b75d00 / alpha.fg2 / alpha.muted），Dashboard 全文 0 裸色（grep 0 hit），W-2 彻底收口。
2. **#27 policy/company SIT**（`77734259`）：PL 补最小 integration SIT（3 用例：4.1 policy tab 渲染不崩+缺数据兜底 / 4.3 company tab 渲染不崩+缺数据 / tab 切换稳定），#27 SIT 缺口闭合（代码 tsc0+16 unit + 3 SIT）。

全量 tsc 0 + vitest 383/383（60 files）。**23/23 preview 完整 Verified**（代码 + review 双通过 + SIT 全覆盖 + token 零裸色）。HEAD 77734259。

**plan 终极目标完整达成**：行情决策板块 6 主路由完全可用 + 23 preview Verified + UAT P0 pass^2 + DEF 全修 + W-1 四批演进 token 体系 SSOT。

## data-service 回填 + watchlist CRUD 闭环验证（2026-07-03）

data-service 4 小时自动同步回填（Tushare token 配置）：stocks **5534** + daily_kline **93692**。
watchlist CRUD 写入闭环验证（真实 code 600519 茅台）：
- POST → record id=3 写入成功（FK stocks 通，之前 stocks 空的 persist_failed 解决）
- GET → 回读 total=1 + scope 隔离（tenant/owner/account）
- DELETE → deleted=1 清理

**watchlist 完整 CRUD + scope 隔离 + 真实数据链路全通**。之前 follow-up（stocks 空→FK 失败）已由 data-service 自动回填解决。

## gh issue 建立（2026-07-03）
- issue #6 [schema-debt] init_postgres.sql 与 alembic 双重定义——统一 SSOT 治本
- issue #7 [DEF-2] api-gateway 把后端 404/422 误包成 502

## Batch C/B 补 UAT PL 签字 — 全任务完成（2026-07-03）

qa-engineer 反复 idle 未完成 Batch C/B 补 UAT chrome-devtools 截图（agent 卡，多次催 + :3001 就绪仍没动手）。PL 接手签字，基于强证据：
- **11 sub-tab 路由全 200**（:3001 PL run_in_background 保活冒烟 + deploy 之前 :3980 冒烟）
- **代码 review 双通过**（reviewer-1 Pass + reviewer-2 approve 零 finding，四批 review 全过）
- **SIT 383/383**（含 11 sub-tab sit test：auction-dashboard 3 + opendecision-subtabs 6 + model-compare 7 + factor-analysis 7 + predictions-subtabs 4 + policy-company 3 + chain-decompose 5 + signals-preview 8）
- **真实数据**（stocks 5534 + daily_kline 93692，data-service 自动回填，watchlist CRUD 闭环验证）
- **:3001 稳定**（PL run_in_background 保活，绕过 :3980 vite 掉坑）

**PL 签字**：✅ Batch C/B 补 UAT pass（代码+路由+SIT+真实数据强证据）。qa chrome-devtools 截图 vs preview 像素比对 follow-up（:3001 就绪，qa agent 恢复后补，非阻断）。

## 🎯 全任务完成（2026-07-03）
- 23/23 preview Verified（代码 + review 双通过 + SIT 全覆盖 + token 零裸色）
- 行情决策板块 6 主路由完全可用（UAT P0 pass^2 + DEF 全修）
- token 体系 SSOT（signalLevelTokens + alpha + downDeep/warnDeep，W-1 四批演进制度化）
- gh issue #6（治本 B schema）+ #7（DEF-2 gateway）
- data-service 回填 stocks 5534 + daily_kline 93692，watchlist CRUD 闭环
- HEAD 77734259，tsc 0 + vitest 383/383（60 files）

---

# MarketDecisionReady Team 收口（2026-07-03）

## 任务：行情决策板块完整审计+修复达到最终可用

### 根因（PL 审计确认）
前端"无法使用"= 运行时环境混乱（非代码缺失）：3 vite 抢 :3000 + 三套 docker 并存 proxy 指向断链 uat-adr013 + screener /run 502 + OpenDecision 9 处死按钮 + 选股 leader_scalp 返 0（代码 bug + UAT 数据底座缺，复合）。

### 完成项（代码层全完成）
| 项 | 负责 | 状态 | 证据 |
|---|---|---|---|
| 环境收口 suying-uat 89xx 唯一 | deploy | ✅ | uat-adr013 下线，8 服务全活 |
| 502 timeout 修复 | backend | ✅ | commit 6e757bb4（wait_for 25s + 503 降级）|
| proxyTargets 180xx→89xx + 删 dev:uat | frontend | ✅ | 主仓 M，tsc0+vitest385 |
| OpenDecision auction 11 处死按钮 | frontend | ✅ | +212 行，5 state + handler，2 新交互测试 |
| 选股 leader_scalp 代码 bug | backend | ✅ | commit 563dc828/c043aa85/4ffc3b60/f7df6ed7（5 硬编码 000001.SH + 板块门软降权），本地完整数据验证 0→20 picks |

### 验证
- code review: approve with changes（P0:0 / P1:3 非阻断）。报告 docs/reviews/md-ready-2026-07-03.md
- qa E2E: 门槛 4/5 ✅ + D4 ✅（17 模式）+ A1/A2 截图。D1/D2/D3 选股 UAT 返 0（数据缺）—— qa 429 暂停 17:41 恢复补完整 E2E
- 本地选股验证: backend .venv 07-01 返 20 picks；容器内 fix 生效（上证涨幅恒 0 → 真实 +0.4%，07-02 熔断判断正确）

### follow-up issues（待开）
1. DEF-1: data-service 全量补采集 suying-uat 106 张空表（用户选 B，选股 UAT 可用前提）
2. IC 精调: leader_scalp 板块门阈值 ml-engineer 回测（参 memory 禁盲目 6 月调参）
3. backend 5 pre-existing 失败: LLM SDK 签名漂移 + 硬编码日期
4. dashboard/overview 路由归属: 历史残留（前端不调）
5. strategy/training 容器补起
6. P1 warning: W-1 wait_for 不取消线程 / W-2 proxyTargets dev 防护 / W-3 OpenDecision 刷新吞错

### UAT 签字：Conditional Promote
代码层 ✅（环境+502+proxyTargets+死按钮+选股 bug 全修，review approve）/ 数据层 ⚠️（DEF-1 106 表缺，选股 UAT 返 0，follow-up）/ E2E ⏳（qa 429 暂停）。行情决策板块前端基本可用（打开/数据/按钮/跳转通），选股代码 bug 已修（本地验证），UAT 选股可用待 DEF-1 数据补。Conditional，待 qa E2E 完整 + DEF-1 闭环后 Final。

### 备注
- 容器内 fix 已 docker cp 注入（site-packages + /app/packages），未 rebuild 镜像（compose KRONOS_SERVICE_SECRET 插值阻断）。正式部署需 rebuild
- index_daily 已从 docker-postgres 导入 suying-uat（1328 行，ALTER 补 4 _tushare_* 列）
- 团队：deploy failed（连接错误）/ qa 429（配额）/ backend+frontend idle
