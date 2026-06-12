---
reviewer: code-reviewer
code_verdict: block
sit_audit_verdict: redo_sit
critical_count: 2
warning_count: 3
suggestion_count: 3
feature: repair-sprint-w2-frontend
tasks: T-306
date: 2026-06-12
---

# 代码审查报告: Wave 2 Line C — T-306 Backtest.tsx

**日期**: 2026-06-12
**审查范围**: `frontend/src/pages/Backtest.tsx` (947 行全新重写), `frontend/src/api/client.ts` (backtestApi 段), `services/backtest-service/app/routes.py`

**代码 Verdict**: **block** (2 Critical)
**SIT Audit Verdict**: **Redo SIT** (证据不可信 — 无任何真实工具输出片段)

---

## Task Verdict

| Task | 代码 Verdict | SIT Audit | 关键发现 |
|---|---|---|---|
| T-306 (Backtest.tsx) | **block** | Redo SIT | 2 Critical: fetch 绕过 auth interceptor + 4 个表单字段为无声 no-op |

---

## Critical（必须修复）

### C-1: 策略方案加载绕过认证拦截器 — `fetch()` 替代 `strategyApi.getPlans()`

- **位置**: `frontend/src/pages/Backtest.tsx:359`
- **严重性**: critical
- **问题**: 
  - 第 359 行使用原生 `fetch('/api/v1/strategy/plans')` 加载策略方案列表，绕过了 `client.ts` 中 axios 实例的 JWT 认证拦截器（request interceptor 注入 `Authorization: Bearer <token>` header）
  - 同时绕过了 401 → refresh token → retry 自动恢复链（response interceptor）
  - `client.ts:100` 已定义等价方法 `strategyApi.getPlans()`（调用 `api.get('/strategy/plans')`，走完整认证链），但被忽略
  - **复现步骤**：
    1. 以登录用户身份打开 Backtest 页面
    2. 打开浏览器 DevTools Network 面板
    3. 观察 `/api/v1/strategy/plans` 请求 → 缺少 `Authorization: Bearer ...` header
    4. 若后端对应端点要求认证 → 返回 401 → 静默失败（`.catch(() => {})` 吞掉错误）→ 策略下拉框永远为空
- **修复建议**:
  ```typescript
  // 删除 Line 358-363 的 useEffect，替换为：
  useEffect(() => {
    strategyApi.getPlans()
      .then(r => setStrategyPlans(r.data.plans || r.data.items || []))
      .catch(() => {})
  }, [])
  ```
  并从 `client.ts` 导入 `strategyApi`（第 15 行可改为 `import { backtestApi, strategyApi } from '../api/client'`）。

### C-2: 4 个表单字段 UI 可见但 API 未消费 — 无声 no-op

- **位置**: `frontend/src/pages/Backtest.tsx:367-397` (`handleRun`) vs `frontend/src/pages/Backtest.tsx:582-627` (表单 UI)
- **严重性**: critical
- **问题**:
  - 表单渲染了 4 个交互式字段：`date_range`（回测日期范围, Line 582）、`strategy_id`（参考策略, Line 586）、`initial_capital`（初始资金, Line 597）、`benchmark`（基准指数, Line 621）
  - `form.validateFields()` 会校验这些字段（Line 369），但 `handleRun` 只从 `values` 中提取了 `mode`、`windows`、`top_n`、`forward_days`（Lines 375-378），其余 4 个字段被**静默丢弃**
  - `backtestApi.run()` (client.ts:127-136) 只接受 `{ mode, windows, top_n, forward_days }` 四个参数，完全不支持 `date_range` / `strategy_id` / `initial_capital` / `benchmark`
  - 后端 `POST /api/v1/backtest/run` (routes.py:61-66) 也仅接受 `mode`、`windows`、`top_n`、`forward_days` 四个 Query 参数
  - **复现步骤**：
    1. 打开回测页面，修改"回测日期范围"为任意区间，选择"参考策略"，修改"初始资金"为 500 万，选择"基准指数"为"创业板指"
    2. 点击"运行回测"
    3. 打开 DevTools Network 面板，检查 `POST /api/v1/backtest/run` 请求的 query string
    4. 实际发送的参数只有 `mode=all&windows=5&top_n=30&forward_days=60` — 日期范围、策略、资金、基准指数全部丢失
    5. 用户感觉功能"不生效"但没有任何错误提示
- **修复建议**（三选一，按难度排序）:
  1. **最小修复（推荐）**: 移除这 4 个尚未被后端支持的字段，避免误导用户。保留数据结构以免后续加回。
  2. **中间方案**: 保留字段但加 `disabled` + tooltip "即将支持"，明确告知用户当前不可用。
  3. **完整方案**: 后端 `POST /run` 增加 `start_date` / `end_date` / `benchmark` Query 参数，前端 `backtestApi.run()` 同步增加这些字段的传参逻辑。`strategy_id` 和 `initial_capital` 需要确认后端是否准备支持。

---

## Warning（建议修复）

### W-1: 因子与策略加载失败静默吞错

- **位置**: `frontend/src/pages/Backtest.tsx:348-349` (因子), `frontend/src/pages/Backtest.tsx:362` (策略)
- **问题**: `catch { }` 和 `.catch(() => {})` 静默吞掉所有加载错误，用户无法获知因子/策略列表是否加载失败，也无法手动重试
- **修复建议**: 至少设置一个 error state 并在 UI 中展示（如 `Empty` 组件的 description 中显示"加载失败，请刷新重试"），同时提供手动重试按钮

### W-2: 因子表格"操作"列无意义

- **位置**: `frontend/src/pages/Backtest.tsx:498-503`
- **问题**: 因子列表表格定义了"操作"列（width 100），但渲染内容始终为 `<Text type="secondary">—</Text>`，每个因子行都显示一个无意义的破折号
- **修复建议**: 直接删除该列定义（从 `factorColumns` 数组中移除），或替换为有实际功能的操作（如"查看 IC 历史"链接）

### W-3: `useEffect` 依赖缺失 — 静默 lint 告警

- **位置**: `frontend/src/pages/Backtest.tsx:358-363`
- **问题**: `useEffect` 内部使用了 `setStrategyPlans`，但没有声明依赖数组（当前为 `[]`）。React 严格模式下 lint 规则 `react-hooks/exhaustive-deps` 会报 warning（`setStrategyPlans` 是 stable setter，实际上可以省略，但显式声明更符合规范）
- **修复建议**: 采用 C-1 的修复（切换到 `strategyApi.getPlans()`）后，该 useEffect 可合并到 loadFactors 逻辑中或保持当前形式。当前不算 bug 但显式依赖声明更安全。

---

## Suggestion（可选优化）

### S-1: `computeSharpe` / `computeMaxDrawdown` 可提取为共享工具函数

- **位置**: `frontend/src/pages/Backtest.tsx:110-130`
- **问题**: 夏普比率和最大回撤计算逻辑是通用金融指标，可能在策略服务、信号服务页面复用
- **建议**: 提取到 `frontend/src/utils/finance.ts`，导出 `computeSharpe(returns, forwardDays)` 和 `computeMaxDrawdown(returns)`

### S-2: `STRATEGY_OPTIONS` 硬编码重复

- **位置**: `frontend/src/pages/Backtest.tsx:132-147` vs `services/backtest-service/app/routes.py:17-32`
- **问题**: 前端 `STRATEGY_OPTIONS` 与后端 `FACTORS` 字典内容完全一致（14 个策略）。后端已提供 `GET /api/v1/backtest/factors` 端点返回因子列表，但前端没有利用
- **建议**: 后续重构时让策略选择下拉框的数据源来自 `backtestApi.getFactors()` 响应，保持前后端策略列表单一来源

### S-3: 图表区域缺少加载骨架屏

- **位置**: `frontend/src/pages/Backtest.tsx:743-764` (收益曲线 + IC 图表区)
- **问题**: 当前仅通过 `result?.details && result.details.length > 0` 条件渲染来决定是否显示图表。在 `runLoading === true` 期间图表区域直接消失，页面出现空白
- **建议**: 在 `runLoading` 状态下使用 Ant Design `Skeleton` 组件保持图表区域的占位，避免页面跳动

---

## 安全检查

逐条核对 OWASP Top 10 + 项目安全基线（`.claude/standards/security.md`）:

- [x] **SQL 注入**: 无风险。后端 `routes.py` 所有 SQL 均使用 `psycopg2` 参数化查询 `cur.execute("...", (param1, param2))`，无字符串拼接
- [x] **XSS**: 无风险。React JSX 自动转义，`dangerouslySetInnerHTML` 未使用
- [x] **命令注入**: 无风险。代码中无 shell 命令执行
- [ ] **认证与授权**: 有风险 — 见 C-1（`fetch()` 绕过 JWT interceptor）。`backtestApi.*` 方法正确走 axios 实例，仅策略计划加载受影响
- [x] **硬编码凭证**: 无风险。检查所有新增代码，无硬编码密钥/密码
- [x] **敏感数据日志**: 无风险。前端无日志输出；后端 `logger.error("Backtest failed: %s", e)` 未泄露敏感信息
- [x] **输入验证**: 低风险。Ant Design Form validation 提供了基本校验；后端 FastAPI Query 参数校验（`ge=1, le=12` 等）覆盖了边界。但 C-2 提到的 4 个 no-op 字段的校验结果未消费
- [x] **限流**: 不在本次审查范围（后端中间件层面）
- [x] **CORS**: 不在本次审查范围（gateway/部署层面）
- [x] **依赖安全**: 无新增依赖。`echarts-for-react` 和 `dayjs` 为已有依赖

---

## SIT Audit

**Audit 对象**: `progress/frontend-dev-w2.md` 中 T-306 的 `**SIT 证据**` 段（不重跑 SIT）

### 逐项核查

| # | 检查项 | 结果 | 说明 |
|---|---|---|---|
| 1 | **progress 完整性** | **Fail** | SIT 证据段存在，但 3 条 AC 均为纯文本特征描述（"XXX — 组件A + 组件B + 组件C"格式），无任何测试命令或输出。不符合 `ac-lifecycle.md` 要求的"pass 单行结论"——当前行是功能清单复述，不是验证结论 |
| 2 | **AC 覆盖** | **Fail** | 3 条 AC 均已列出，但覆盖仅为文字声明。AC-306.1（表单配置）和 AC-306.2（可视化）在 integration 层无验证证据（如 curl 调用 backtest-service 返回的实际 JSON、ECharts 截图描述、浏览器 console 输出等）。AC-306.3（tsc/build）有数字声称（3.63s, 3681 modules）但无粘贴的命令输出 |
| 3 | **证据可信度** | **Fail** | **零条真实工具输出片段**。无 `curl` 响应、无 `vitest` 输出、无 `npm run build` 日志、无浏览器 console 截图描述。全部证据为 `[x] AC-XXX ✅ <功能描述>` 格式的自述文本，属于"无证据文本"范畴（标准明确排除的 "通过"/"OK"/`<placeholder>` 类证据） |
| 4 | **失败/阻塞标记** | **Pass** | 无失败或阻塞声明，不存在虚假 pass |

### Verdict: **Redo SIT**

**需重跑的 AC**: AC-306.1, AC-306.2, AC-306.3 全部需要补充真实工具输出

**重跑要求**（minimal bar）:
- AC-306.1: 至少 1 条 `curl -s http://localhost:8001/api/v1/backtest/run?mode=all&windows=3&top_n=30&forward_days=60 | jq .` 的真实 JSON 响应片段（证明 backtest-service 可连通并返回数据）
- AC-306.2: 至少 1 条验证前端渲染的 vitest 测试输出 或 `npm run build` 成功日志粘贴
- AC-306.3: `npx tsc -b --noEmit` + `npm run build` 的真实终端输出复制粘贴（不含省略）

**备注**: 我本地验证了 `npx tsc -b --noEmit` 返回 0 errors，该 AC 的代码层是正确的；但 SIT 证据格式仍需真实输出片段才能通过 audit。

---

## 代码优点

1. **组件结构清晰**: Run / Factors / Compare 三 Tab 分离，每个 Tab 有独立的加载状态、错误状态和空状态，符合 React 最佳实践
2. **ECharts 图表配置细致**: `buildReturnChartOption` / `buildIcChartOption` / `buildHitRateGaugeOption` / `buildCompareChartOption` 纯函数分离，颜色编码（正收益绿/负收益红）一致
3. **`useCallback` 使用得当**: handleRun / handleCompare / handleCalibrate 三个事件处理器均正确使用 `useCallback` 避免不必要的子组件重渲染
4. **表单 + 滑块双向绑定**: 使用 Ant Design Slider 作为 InputNumber 的辅助输入，提升参数调整的交互体验
5. **错误/空状态完整**: 每个 Tab 都有 Empty 占位、错误信息展示和成功消息反馈，用户体验边界处理良好
