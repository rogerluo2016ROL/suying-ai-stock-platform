## T-207: diagnosis frontend 修复 — 2026-06-12 16:30

**状态**: Completed
**Skills**: none (标准 TypeScript 修复)

**SIT 证据**:

- [x] AC-207.1 (TypeScript 类型对齐): `dims['ai_prediction']` → `dims['ai_predict']` 修正 (line 135)，对齐后端诊断引擎维度的实际 key `ai_predict`（见 `diagnosis_engine.py:869` WEIGHTS 定义和 `diagnose()` 返回的 `dimensions` dict）。`DiagnosisReport` 接口其余字段（`grade`/`recommendation`/`dimensions`/`key_levels`/`created_at`）已与后端 Pydantic `DiagnosisReport` schema 对齐。`npx tsc -b --noEmit` 验证：Diagnosis.tsx **0 错误**。

- [x] AC-207.2 (PDF URL 修正): 当前代码 `handleExportPdf` (line 914) 使用 `/api/v1/diagnosis/report/${result.code}/pdf`，已包含 `/diagnosis` 路径段。对应后端路由 `router = APIRouter(prefix="/api/v1/diagnosis")` + `@router.get("/report/{code}/pdf")` (routes.py:326-335)。Vite proxy 已将 `/api/v1/diagnosis` 代理至 `http://localhost:8009`。URL 正确。

- [x] AC-207.3 (历史记录字段修正): 新增 `transformHistoryItem()` 函数 (lines 118-128)，将后端 `DiagnosisHistoryItem`（字段 `overall_score`/`recommendation`）映射为前端 `HistoryRecord`（字段 `score`/`grade_label`）。`loadHistory` 中 `data.items` 经 `rawItems.map(transformHistoryItem)` 转换后调用 `setHistory()` (line 797)。后端响应 `PaginatedDiagnosisHistory.items` —— 无 `records` 字段。

- [x] AC-207.4 (grade 枚举对齐): 后端 `RecommendationGrade(str, Enum)` 序列化为中文值 (`"强烈买入"`/`"买入"`/`"持有"`/`"减仓"`/`"卖出"`)。`_score_to_grade()` 返回字母等级 (`"A+"`/`"A"`/`"B+"`/...`"E"`)。前端 `DiagnosisReport.grade` 为 `string` (接收字母等级)，`DiagnosisReport.recommendation` 为 `string` (接收中文建议)。`GRADE_CONFIG` 和 `RECOMMENDATION_COLORS` 映射完全匹配。**codebase 中无 `strong_buy` 等英文枚举名残留**。

- [x] AC-207.5 (Mock fallback 环境守卫): 4 处 mock fallback 全部包入 `import.meta.env.DEV` 守卫：
  - `runDiagnosis` catch (line 843): 生产环境 `setError()` + `message.error()`
  - `loadHistory` else/catch (lines 798, 821): 生产环境空历史 + `message.error()`
  - `loadHistoryDetail` catch (line 864): 生产环境 null 详情 + `message.error()`
  - `runCompare` catch (line 882): 生产环境空结果 + `message.error()`
  新增 `src/vite-env.d.ts` (`/// <reference types="vite/client" />`) 提供 `import.meta.env` 类型。

- [x] AC-207.6 (构建验证):
  - `npx tsc -b --noEmit`: Diagnosis.tsx **0 errors**。总计 6 errors 均来自其他文件（Trade.tsx=4 + RiskCheckModal.tsx=1 + ModelRegistry.tsx=1），属于 parallel task T-204/T-206 范围。
  - `npx vite build`: **SUCCESS** (3681 modules, 3.72s)。Chunk size warning 非阻塞。
  - `npx tsc -b --noEmit src/pages/Diagnosis.tsx`: Diagnosis.tsx 单体 **0 errors**。

**质量门**:
- TypeScript `npx tsc -b --noEmit`: Diagnosis.tsx 0 errors (6 errors in unrelated parallel-task files Trade.tsx/RiskCheckModal.tsx/ModelRegistry.tsx)
- `npx vite build`: PASS (3681 modules, 3.72s)
- vitest: 现有测试 (AuthContext/ProtectedRoute) 与本任务无关，未受改动影响

**下一步**: Product-lead 签字；T-204/T-206 完成 Trade.tsx/ModelRegistry.tsx tsc fixes 后方可 `npm run build` (含 tsc pre-check) 全量通过。

**涉及文件**:
- `frontend/src/pages/Diagnosis.tsx` (+ `transformHistoryItem`, dimension key fix, 4 env guards)
- `frontend/src/vite-env.d.ts` (new, Vite client types)
