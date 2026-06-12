# Repair Sprint Wave 1+2 — 最终交付报告

- **Date**: 2026-06-12
- **Scope**: 两轮修复 Sprint（14 tasks + 8 CR + 12 E2E/UAT 报告）
- **Status**: **完成交付，screener /run hang 进 Wave 3**

---

## Wave 1 交付（已签字）

| 指标 | 修复前 | 修复后 |
|------|:--:|:--:|
| Critical | 5 | 0 |
| P0 | 8 | 0 |
| 无效 UAT | 2 | 已作废重签 |
| data-pipeline E2E/UAT | 未测试 | 8/8 AC |
| RBAC 保护 | 0 服务 | 2 服务 + kronos-auth 包 18/18 test |
| 前端 API 契约 | 大面积断裂 | 全部对齐 |

签字: `docs/reviews/repair-sprint-signoff-2026-06-12.md` (product-lead, Approve)

---

## Wave 2 交付

### 代码修复
| Line | Task | 内容 | Verdict |
|------|------|------|:--:|
| A | T-301 | ETL CB _Db 封装 + Gateway httpx→urllib + 端口 8000→8080 | ✅ CR approve |
| A | T-302 | ADR-001 架构漂移更新 + materialized_views.sql 独立 | ✅ CR approve |
| C | T-306 | Backtest.tsx 51行→947行完整实现 | ✅ CR approve (re-review) |
| D | T-307 | CORS 白名单 + trade_password Body + LIM-1 | ✅ UAT 8/8 |

### E2E/UAT 补齐
| 服务 | 状态 | 备注 |
|------|:--:|------|
| screener-service (8001) | ⚠️ Wave 3 | 启动不阻塞，/run sync-in-async hang（已有架构问题） |
| prediction-service (8002) | ✅ | DEF-PRED-1 404 已修复 |
| signal-service (8004) | ⚠️ Conditional | 核心 10/13 通过 |
| backtest-service (8007) | ✅ Promote | 5/5 AC |
| alert-service (8005) | ✅ Promote | 9/9 AC |

### 成功指标
| 指标 | Sprint 前 | Sprint 后 |
|------|:--:|:--:|
| Critical | 5 | 0 |
| P0 | 8 | 0 |
| P1 | 6 | 0 |
| E2E/UAT 覆盖率 | 42% (5/12) | 92% (11/12) |
| 无效 UAT | 2 | 0 |
| RBAC | 0 服务 | 2 + kronos-auth |
| Backtest 页面 | 51 行空壳 | 947 行 |
| CORS | `*`+credentials | 白名单 |
| trade_password | Query 泄露 | Body 安全 |

---

## Wave 3 待办

1. **screener /run sync-in-async hang** — async handler 直接调同步 `_run_multifactor_mode()` 阻塞 event loop
2. signal-service Conditional AC 补齐
3. screener-service E2E/UAT（blocked by #1）

---

## 产物索引

| 类别 | 路径 |
|------|------|
| Wave 1 签字 | `docs/reviews/repair-sprint-signoff-2026-06-12.md` |
| Wave 1 后端 CR | `docs/reviews/repair-sprint-backend-2026-06-12.md` |
| Wave 1 前端 CR | `docs/reviews/repair-sprint-frontend-2026-06-12.md` |
| Wave 1 data-pipeline E2E | `docs/qa/data-pipeline-refactor-e2e-2026-06-12.md` |
| Wave 1 data-pipeline UAT | `docs/qa/data-pipeline-refactor-uat-2026-06-12.md` |
| Wave 1 trade E2E | `docs/qa/repair-sprint-trade-e2e-2026-06-12.md` |
| Wave 1 trade UAT | `docs/qa/repair-sprint-trade-uat-2026-06-12.md` |
| Wave 2 后端 CR | `docs/reviews/repair-sprint-w2-backend-2026-06-12.md` |
| Wave 2 前端 CR | `docs/reviews/repair-sprint-w2-frontend-2026-06-12.md` |
| Wave 2 后端 UAT | `docs/qa/repair-sprint-w2-uat-2026-06-12.md` |
| Line B QA 报告 (10份) | `docs/qa/{screener,prediction,signal,backtest,alert}-{e2e,uat}-2026-06-12.md` |
| 初始审视 | `docs/reviews/refactor-completeness-review-2026-06-12.md` |
