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
