---
reviewer: code-reviewer
code_verdict: approve
sit_audit_verdict: pass
critical_count: 0
warning_count: 2
suggestion_count: 3
feature: repair-sprint-w2-frontend
tasks: T-306, T-306-fix
date: 2026-06-12
---

# 代码审查报告: Wave 2 Line C — T-306 Backtest.tsx

**日期**: 2026-06-12
**审查范围**: `frontend/src/pages/Backtest.tsx` (947 行全新重写), `frontend/src/api/client.ts` (backtestApi 段), `services/backtest-service/app/routes.py`

**代码 Verdict**: **block** (2 Critical) → **approve** (经 re-review，2 Critical 均已修复)
**SIT Audit Verdict**: **Redo SIT** → **Pass** (经 re-review，修复证据通过)

---

## Task Verdict

| Task | 代码 Verdict | SIT Audit | 关键发现 |
|---|---|---|---|
| T-306 (Backtest.tsx) | **approve** | Pass | 初版 2 Critical 已修复: fetch→移除 + 4 无声 no-op 字段清除 |
| T-306-fix | **approve** | Pass | C-1/C-2 修复验证通过，tsc 0 错误 + build 成功 |

---

## Critical（必须修复）

### C-1: 策略方案加载绕过认证拦截器 — `fetch()` 替代 `strategyApi.getPlans()` ✅ 已修复

- **位置**: ~~`frontend/src/pages/Backtest.tsx:359`~~ （该行已不存在）
- **修复方式**: `fetch('/api/v1/strategy/plans')` 调用已移除；`strategyPlans` state 与对应 `useEffect` 一并清理。因 `strategy_id` 字段随 C-2 一并移除，策略加载逻辑成为死代码，合理消除。

### C-2: 4 个表单字段 UI 可见但 API 未消费 — 无声 no-op ✅ 已修复

- **位置**: ~~`frontend/src/pages/Backtest.tsx:582-627`~~ （已重写）
- **修复方式**: Run 表单仅保留 `mode`/`windows`/`top_n`/`forward_days` 四个受支持的字段（Lines 559-577）。`date_range` 现仅用于 Compare Tab 的 `compareForm`，其对应的 `backtestApi.compare()` 实际支持 `start_date`/`end_date`，属正确使用。`DatePicker` import、`BENCHMARK_OPTIONS` 等死代码已清理。

---

## Warning（建议修复）

### W-1: 因子与策略加载失败静默吞错

- **位置**: `frontend/src/pages/Backtest.tsx:333-335` (因子)
- **问题**: `catch { }` 静默吞掉因子加载错误，用户无法获知加载失败，也无法手动重试
- **状态**: 仍存在，非本次 Critical 修复范围

### W-2: 因子表格"操作"列无意义

- **位置**: `frontend/src/pages/Backtest.tsx:475`
- **问题**: 因子列表表格定义了"操作"列但渲染内容始终为 `—`
- **状态**: 仍存在，非本次 Critical 修复范围

---

## Suggestion（可选优化）

- S-1: `computeSharpe` / `computeMaxDrawdown` 可提取为共享工具函数（`frontend/src/utils/finance.ts`）
- S-2: `STRATEGY_OPTIONS` 与后端 `FACTORS` 字典重复，可利用 `backtestApi.getFactors()` 响应做单一来源
- S-3: 图表区域缺少加载骨架屏（`Skeleton`）

---

## 安全检查

- [x] **SQL 注入**: 无风险
- [x] **XSS**: 无风险
- [x] **命令注入**: 无风险
- [x] **认证与授权**: 无风险（C-1 已修复，`fetch()` 已移除）
- [x] **硬编码凭证**: 无风险
- [x] **敏感数据日志**: 无风险
- [x] **输入验证**: 低风险（Run 表单仅含 4 个受支持字段）
- [x] **限流**: 不在本次审查范围
- [x] **CORS**: 不在本次审查范围
- [x] **依赖安全**: 无新增依赖

---

## SIT Audit

**Audit 对象**: `progress/frontend-dev-w2.md` T-306 SIT 证据段（初版）+ `progress/frontend-dev-w2-fix.md`（修复版）

### 初版 Audit: Redo SIT

| # | 检查项 | 结果 |
|---|---|---|
| 1 | progress 完整性 | Fail — 纯文本特征描述，无测试命令或输出 |
| 2 | AC 覆盖 | Fail — 仅有文字声明，无 integration 层验证证据 |
| 3 | 证据可信度 | Fail — 零条真实工具输出片段 |
| 4 | 失败/阻塞标记 | Pass |

### 修复版 Audit: Pass

| # | 检查项 | 结果 | 说明 |
|---|---|---|---|
| 1 | progress 完整性 | **Pass** | `progress/frontend-dev-w2-fix.md` 含完整 SIT 证据段，按 AC 列出 |
| 2 | AC 覆盖 | **Pass** | C-1/C-2 修复 + tsc/build 均覆盖 |
| 3 | 证据可信度 | **Pass** | tsc EXIT 0、build `✓ built in 3.24s` 3681 modules — reviewer 独立重跑确认 tsc EXIT 0、build `✓ built in 3.09s` 3681 modules |
| 4 | 失败/阻塞标记 | **Pass** | 无失败声明 |

**Verdict**: ✅ Pass

---

## 代码优点

1. **组件结构清晰**: Run / Factors / Compare 三 Tab 分离
2. **ECharts 图表配置细致**: 纯函数分离，颜色编码一致
3. **`useCallback` 使用得当**: 避免不必要重渲染
4. **表单 + 滑块双向绑定**: 提升交互体验
5. **错误/空状态完整**: 边界处理良好

---

## Re-review: T-306 Critical Fix Verification (2026-06-12)

**审查对象**: `progress/frontend-dev-w2-fix.md`
**审查范围**: `frontend/src/pages/Backtest.tsx`

### C-1 验证: `fetch()` 绕过认证拦截器 → **已修复**

| 检查项 | 结果 | 证据 |
|---|---|---|
| `fetch('/api/v1/strategy/plans')` 已移除 | 通过 | `grep -n 'fetch' Backtest.tsx` 零匹配 |
| `strategyPlans` state 已清理 | 通过 | 文件中无 `strategyPlans` 引用 |
| 策略加载逻辑已消除 | 通过 | `strategy_id` 随 C-2 移除，相关代码为死代码，正确消除 |

### C-2 验证: 4 个无声 no-op 表单字段 → **已修复**

| 检查项 | 结果 | 证据 |
|---|---|---|
| `date_range` 已从 Run 表单移除 | 通过 | Run 表单仅含 `mode`/`windows`/`top_n`/`forward_days` (Lines 559-577)。`date_range` 仅在 Compare Tab 的 `compareForm` 中，`backtestApi.compare()` 实际支持 `start_date`/`end_date` (Lines 387-388) |
| `strategy_id` 已移除 | 通过 | 文件中无 `strategy_id` |
| `initial_capital` 已移除 | 通过 | 文件中无 `initial_capital` |
| `benchmark` 已移除 | 通过 | `benchmarkLabel` 仅用于图表显示；`benchmark_pct` 为 API 返回字段 |
| 死代码清理 | 通过 | `DatePicker`、`RangePicker`、`BENCHMARK_OPTIONS` 已清理 |

### 独立验证

| 命令 | 结果 | 与 SIT 证据对比 |
|---|---|---|
| `npx tsc -b --noEmit` | EXIT 0, 零错误 | 一致 |
| `npm run build` | EXIT 0, `✓ built in 3.09s`, 3681 modules, `index-CtKc1L8b.js 2697.94 kB` | 一致（3.24s→3.09s 正常波动） |

### 代码 Verdict: **approve**

C-1 与 C-2 均已正确修复，无新增问题。W-1（因子加载静默吞错）和 W-2（因子表格无意义操作列）仍存在，但不属于本次 Critical 修复范围。

### SIT Audit Verdict: ✅ **Pass**

修复版 SIT 证据含真实 `tsc` 退出码与 `npm run build` 终端输出片段，reviewer 独立复验通过。
