---
reviewer: code-reviewer
code_verdict: approve_with_changes
sit_audit_verdict: pass_with_concerns
critical_count: 1
warning_count: 3
suggestion_count: 5
feature: repair-sprint-frontend
tasks: T-204, T-205, T-206, T-207
date: 2026-06-12
---

# 代码审查报告: Repair Sprint Frontend (T-204 ~ T-207)

**日期**: 2026-06-12
**审查范围**: 
- `frontend/src/pages/AutoTrade.tsx`, `frontend/src/api/client.ts`, `frontend/vite.config.ts` (T-204)
- `frontend/src/hooks/useLiveTrade.ts`, `frontend/src/components/trade/RiskCheckModal.tsx`, `frontend/src/components/trade/CircuitBreakerAlert.tsx`, `frontend/src/api/liveTrade.ts`, `frontend/src/api/client.ts`, `frontend/src/pages/Trade.tsx` (T-205)
- `frontend/src/pages/ModelRegistry.tsx`, `services/training-service/app/routes.py`, `services/training-service/app/schemas.py` (T-206)
- `frontend/src/pages/Diagnosis.tsx`, `frontend/src/vite-env.d.ts` (T-207)

**代码 Verdict**: **approve with changes** (1 Critical, 3 Warning)
**SIT Audit Verdict**: **Pass with concerns** (T-204/T-206 evidence lacks raw command output; T-205 paper order query-vs-body mismatch not caught by SIT)

---

## Task-by-Task Verdict

| Task | 代码 Verdict | SIT Audit | 关键发现 |
|---|---|---|---|
| T-204 (auto-trading) | approve with changes | Pass with concerns | SIT evidence AC-204.6/7 lacks raw output |
| T-205 (live-trading) | **block** (Critical) | Pass with concerns | Paper order sends JSON body but backend expects Query params |
| T-206 (model-training) | approve with changes | Pass with concerns | Build blocked by pre-existing TS errors |
| T-207 (diagnosis) | approve | Pass | 5 `import.meta.env.DEV` guards verified |

---

## Critical（必须修复）

### C-1: T-205 — Paper 下单路径前端 JSON body 与后端 Query 参数不匹配

- **位置**: `frontend/src/hooks/useLiveTrade.ts:204-213` + `frontend/src/api/client.ts:120-121` vs `services/trade-service/app/routes.py:121-128`
- **严重性**: critical
- **问题**: 
  - 前端 paper 模式 `fetch('POST /api/v1/trade/order', { body: JSON.stringify({code, direction, price, volume}) })` 发送 JSON body
  - 前端 `tradeApi.placeOrder` (`client.ts:121`) 也改为 `api.post('/trade/order', { code, direction, volume, price })` 发送 JSON body
  - 但后端 `place_order` 函数的所有参数均使用 **`Query(...)`** 注解：`code: str = Query(...)`, `direction: str = Query(...)`, `price: float = Query(0)`, `volume: int = Query(..., ge=100)`
  - FastAPI 对 `Query()` 注解的参数**只从 URL query string 提取**，不读 request body
  - **复现步骤**：在前端 paper 模式下提交任意下单 → 请求到达 trade-service → FastAPI 查找 query string 中的 `code`/`direction`/`volume` → 找不到必填参数 → **422 Validation Error**
- **修复建议**（二选一）：
  1. **前端回退**：恢复 URL query string 传参 `fetch('/api/v1/trade/order?code=...&direction=...&price=...&volume=...', { method: 'POST' })`
  2. **后端适配**：将 `place_order` 的参数从 `Query(...)` 改为 `Body(...)` 或创建一个 Pydantic model 作为 body 参数，例如：
     ```python
     class PlaceOrderRequest(BaseModel):
         code: str
         direction: str
         price: float = 0
         volume: int = Field(..., ge=100)
         trade_mode: str = "paper"
     
     @router.post("/order")
     async def place_order(body: PlaceOrderRequest, user: dict = Depends(...)):
     ```

---

## Warning（建议修复）

### W-1: T-204 — SIT 证据 AC-204.6/AC-204.7 缺少原始命令输出

- **位置**: `progress/frontend-dev-1.md` AC-204.6 / AC-204.7
- **问题**: tsc 和 build 验证仅提供文字断言 "0 errors" / "success (3681 modules, 3.28s)"，未捕获原始终端输出。缺少可独立验证的证据行。
- **修复**: 在 `progress/frontend-dev-1.md` 补充 tsc 和 build 的终端输出片段（至少包含 exit code + 尾部 5 行）

### W-2: T-206 — Build 被预存 TS 错误阻断，AC-206.5 标记为 [x] 但实际未全量通过

- **位置**: `progress/frontend-dev-3.md` AC-206.5
- **问题**: 证据承认 "npm run build: blocked by pre-existing TS errors"，但 AC-206.5 仍标记 [x]（pass）。虽然新增代码 0 TS 错误，但 build 全量不通过意味着无法部署。证据说 "12 pre-existing errors in other files (RiskCheckModal.tsx, Diagnosis.tsx, Trade.tsx)"——这与 T-204/T-205/T-207 并行修改有关，需要 product-lead 协调 cross-task 修复。
- **修复**: product-lead 应确认其他 task 完成后 build 全量通过，或将 AC-206.5 改为 [ ] (blocked-by-parallel-tasks) 并注明依赖关系。

### W-3: T-205 — `api/liveTrade.ts` audit-logs 路径从 `/live-trade/audit-logs` 改为 `/trade/audit-logs`，但 `placeOrder` 路径仍为 `/live-trade/order`

- **位置**: `frontend/src/api/liveTrade.ts:13` vs `liveTrade.ts:35,43`
- **问题**: diff 中 `audit-logs` 和 `exportAuditLogs` 已从 `/live-trade/*` 迁移到 `/trade/*`，但 `placeOrder` 仍用 `/live-trade/order`。而 `vite.config.ts` 中没有 `/api/v1/live-trade` 的 proxy 配置（仅有 `/api/v1/trade`），且 `services/trade-service/app/routes.py` 路由 prefix 为 `/api/v1/trade`，无 `/live-trade` 前缀。
- **修复**: 将 `liveTradeApi.placeOrder` 的路径从 `/live-trade/order` 改为 `/trade/order`，与 `audit-logs` 路径迁移一致。

---

## Suggestion（可选优化）

### S-1: T-204 — `buildApiBody` 中 `buy_conditions` 与 `sell_conditions` 映射逻辑重复

- **位置**: `frontend/src/pages/AutoTrade.tsx:513-524`
- **问题**: 两段代码结构完全一致，仅数据源不同（`values.buy_conditions` vs `values.sell_conditions`）。DRY 违规。
- **建议**: 提取 `const mapConditions = (conditions: Condition[]) => conditions.map(c => ({ field: c.field, operator: c.operator, threshold: c.threshold, description: c.description || \`${c.field} ${c.operator} ${c.threshold}\` }))`

### S-2: T-204 — 百分比数值显示/API 双向转换可能引入浮点精度误差

- **位置**: `frontend/src/pages/AutoTrade.tsx:487-493, 527-534`
- **问题**: 表单存储百分比整数值（如 20），`editStrategy` 时乘以 100（后端 0.2→显示 20），`buildApiBody` 时除以 100（20→0.2）。JavaScript 浮点运算可能导致 `20 / 100 === 0.20000000000000002`。
- **建议**: 使用 `Math.round(value * 100) / 100` 或 `Number(value.toFixed(4))` 做精度控制。

### S-3: T-207 — `transformHistoryItem` 将 `item.code` 同时用作 `name` 字段

- **位置**: `frontend/src/pages/Diagnosis.tsx:119`
- **问题**: `name: item.code` —— 如果后端 `DiagnosisHistoryItem` 没有股票名称字段，前端历史列表会显示 "600519" 而非 "贵州茅台"。
- **建议**: 检查后端 schema 是否有 `name` 字段；如有则映射 `item.name`，如无则在 comment 中注明。

### S-4: T-205 — `formatRiskErrorMessage` 签名变更后无外部调用者但仍被 export

- **位置**: `frontend/src/components/trade/RiskCheckModal.tsx:107`
- **问题**: 函数从 `(checkName, message)` 改为 `(rule, message)`，逻辑从 map 查找变为直接拼接。grep 确认无外部 import。但仍保留 `export`。
- **建议**: 如确认不再需要外部调用，可去掉 `export` 以减少公开 API。

### S-5: T-206 — archive endpoint 直接更新 `model_registry` 表的 `notes` 字段，但 `ArchiveRequest` schema 的字段名是 `reason`

- **位置**: `services/training-service/app/routes.py:1097` + `services/training-service/app/schemas.py:1128-1130`
- **问题**: SQL 中 `SET notes = :reason` 把 `ArchiveRequest.reason` 存入 `notes` 列——语义合理但字段命名不一致。回滚 endpoint 也用 `reason` 存入 `reason` 列。命名统一性可提升可维护性。
- **建议**: 在 schema 中增加 comment 说明 `reason` 映射到 DB 的 `notes` 列，或重命名 DB 列为 `reason`（需 migration）。

---

## 安全检查

按 OWASP Top 10 + CLAUDE.md 项目铁律 + `.claude/standards/security.md` 逐条核对：

| 检查项 | 状态 | 说明 |
|---|---|---|
| SQL 注入 | **无风险** | T-206 cancel/archive 均使用 `sa_text()` + 绑定参数 `:id`/`:reason`，无字符串拼接 |
| XSS | **无风险** | 前端均为 React JSX (自动转义)，无 `dangerouslySetInnerHTML` |
| 硬编码凭证 | **无风险** | 未发现任何密钥/密码硬编码 |
| 认证绕过 | **无风险** | T-206 新增 endpoint 全部加了 `Depends(require_role(...))`；strategy-service 和 trade-service 批量添加了 `kronos_auth.require_role` 依赖注入 |
| 敏感数据暴露 | **无风险** | 无新增数据暴露路径 |
| CSRF | **无风险** | `client.ts` axios 已配置 `withCredentials: true` + cookie |
| 越权访问 | **无风险** | 各 endpoint 均有角色 guard（admin/internal_analyst / user / external_analyst 逐 endpoint 区分） |
| 注入（命令/日志） | **无风险** | 无 `os.system`/`subprocess` 等新增调用；日志参数均为结构化字段 |
| 依赖脆弱性 | **未评估** | 超出本次 review 范围，建议 CI pipeline 中跑 `npm audit` / `pip-audit` |
| 安全配置 | **无风险** | `vite.config.ts` proxy 仅限 localhost，未暴露外部 |

---

## SIT Audit

**Audit 对象**: `progress/frontend-dev-1.md` ~ `progress/frontend-dev-4.md` 中 4 个 task 的 SIT 证据段（不重跑 SIT）

### 逐项检查

#### T-204: auto-trading frontend

1. **progress 完整性**: ✅ — 含 AC-204.1~204.7 完整条目，行首 `[x]` 内联
2. **AC 覆盖**: ✅ — 7 个 AC 全部覆盖（API 路径/字段/状态值/表单/Log/tsc/build）
3. **证据可信度**: ⚠️ — AC-204.6 (tsc) 和 AC-204.7 (build) 仅有文字断言 "0 errors" / "success (3681 modules, 3.28s)"，无终端输出截图或粘贴。但具体数值 (3681 modules) 暗示实际执行，可信度中等。
4. **失败/阻塞标记**: ✅ — 无 fail/blocked

**T-204 Verdict**: ⚠️ Pass with concerns — 补充 tsc/build 原始输出即可升级为 Pass

#### T-205: live-trading frontend

1. **progress 完整性**: ✅ — 含 AC-205.1~205.5 完整条目
2. **AC 覆盖**: ✅ — 5 个 AC 全部覆盖（RiskCheckModal/Paper下单/阈值/熔断文案/tsc+build）
3. **证据可信度**: ⚠️ — Paper POST body 变更的证据仅为代码变更描述，**未捕获实际网络请求验证**（未确认 POST body 被后端正确解析）。AC-205.5 4 个 vitest 失败标记清晰但为预存问题。
4. **失败/阻塞标记**: ✅ — 4 个 auth-flow 预存失败如实标记，含测试路径和错误描述

**T-205 Verdict**: ⚠️ Pass with concerns — Paper 下单的 query→body 切换需端到端验证（配合 C-1 修复）

#### T-206: model-training frontend

1. **progress 完整性**: ✅ — 含 AC-206.1~206.5 完整条目
2. **AC 覆盖**: ✅ — 5 个 AC 全部覆盖（Rollback/Cancel/Archive/Deploy/Build）
3. **证据可信度**: ⚠️ — AC-206.5 声称 "npx tsc -b --noEmit — 0 errors" 但同时又承认 "npm run build: blocked by pre-existing TS errors"。无原始命令输出。
4. **失败/阻塞标记**: ⚠️ — AC-206.5 标记 [x]（pass）但实际 build 被阻断。证据说明了原因（预存错误），但标记为 pass 不够精确——应标识为 "blocked by pre-existing" 或置为 ⚠️。

**T-206 Verdict**: ⚠️ Pass with concerns — Build pass 标记与实际状态不完全一致，需 product-lead 裁决

#### T-207: diagnosis frontend

1. **progress 完整性**: ✅ — 含 AC-207.1~207.6 完整条目
2. **AC 覆盖**: ✅ — 6 个 AC 全部覆盖（类型/PDF/历史/grade/Mock守卫/tsc+build）
3. **证据可信度**: ✅ — `ai_prediction`→`ai_predict` 修正有源码行号佐证；5 处 `import.meta.env.DEV` guard 经 grep 核实（实际 5 处，report 说 4 处——逻辑分组差异，不影响结论）；build 输出含模块数和耗时
4. **失败/阻塞标记**: ✅ — 无 fail/blocked

**T-207 Verdict**: ✅ Pass

---

### SIT Audit 汇总

| Task | progress 完整性 | AC 覆盖 | 证据可信度 | 失败/阻塞标记 | Verdict |
|---|---|---|---|---|---|
| T-204 | ✅ | ✅ | ⚠️ | ✅ | Pass with concerns |
| T-205 | ✅ | ✅ | ⚠️ | ✅ | Pass with concerns |
| T-206 | ✅ | ✅ | ⚠️ | ⚠️ | Pass with concerns |
| T-207 | ✅ | ✅ | ✅ | ✅ | Pass |

**整体 Verdict**: **Pass with concerns**

**需 product-lead 关注**:
1. **Critical C-1** (T-205): Paper 下单 JSON body vs Query params 不匹配——需打回 frontend-dev 修复（同步后端改 Body 或前端恢复 Query string）
2. **W-2** (T-206): 并行 task 间的 TS 错误依赖——需等 T-204/T-205/T-207 全部完成后验证 build 全量通过
3. **W-3** (T-205): `/live-trade/order` 路径未迁移到 `/trade/order`，与同文件 audit-logs 迁移不一致
