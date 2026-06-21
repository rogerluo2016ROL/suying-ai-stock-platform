# T-002 frontend-dev-2 — AC-4/5/6 进度

## 任务
AC-4：37 处裸 fetch → axios（pages + contexts）
AC-5：删 Diagnosis.tsx 的 generateMockResult + DEV fallback
AC-6：修 tests/sit/auth-flow.test.tsx 让 vitest 24/24 全绿

## 实际改动文件
- frontend/src/api/client.ts （tradeApi.getOrders + diagnosisApi.getHistory/getReportPdf 三个方法补齐）
- frontend/src/pages/Strategy.tsx（9 处 fetch → axios）
- frontend/src/pages/AutoTrade.tsx（6 处 fetch → axios）
- frontend/src/pages/DataUpdate.tsx（6 处 fetch → axios）
- frontend/src/pages/Dashboard.tsx（4 处 fetch → axios）
- frontend/src/pages/Trade.tsx（3 处 fetch → axios，从 useLiveTrade 解构中移除 apiPrefix）
- frontend/src/pages/Diagnosis.tsx（2 处 fetch → axios + 删 generateMockResult 函数 137 行 + 删 isDemo state + 删 DEMO 水印 JSX + 删 4 处 import.meta.env.DEV fallback）
- frontend/src/pages/Predictions.tsx（1 处 fetch → axios，引入 predictionApi）
- frontend/src/pages/Signals.tsx（1 处 fetch → axios，复用已 import 的 signalApi）
- frontend/tests/sit/auth-flow.test.tsx（fireEvent.change → userEvent.type；fillLoginForm + fillRegisterForm 两个 helper）

## 5 段汇报

### 实际改动
按 team-lead 指令的"机械替换模式"逐文件完成 32 处 pages 级 fetch → axios 转换；AuthContext.tsx 保留 5 处（指令明示"应只剩 AuthContext.tsx 或 0"，且 /auth/refresh 必须避开 refresh-retry 拦截器，是设计上的保留）。Diagnosis.tsx 一次性清理：删 generateMockResult（137 行）、isDemo state、DEMO 水印 Card、所有 4 处 import.meta.env.DEV 分支，失败统一走 message.error。

### AC 自验

**AC-4 ✅ pages 裸 fetch 清零**
```
$ grep -rn "fetch(" src/pages/ src/contexts/
src/contexts/AuthContext.tsx:46:      const refreshRes = await fetch('/api/v1/auth/refresh', {
src/contexts/AuthContext.tsx:57:      const meRes = await fetch('/api/v1/auth/me', {
src/contexts/AuthContext.tsx:106:    const res = await fetch('/api/v1/auth/login', {
src/contexts/AuthContext.tsx:124:    const res = await fetch('/api/v1/auth/register', {
src/contexts/AuthContext.tsx:143:      await fetch('/api/v1/auth/logout', {
```
src/pages/ 命中 = 0。AuthContext 5 处保留符合指令例外（"应只剩 AuthContext.tsx 或 0"），且这 5 处是 token 生命周期入口，必须避开 axios 的 401-refresh 拦截器以防死循环。

**AC-5 ✅ Diagnosis mock 完全清除**
```
$ grep -n "generateMockResult\|import.meta.env.DEV\|isDemo\|setIsDemo" src/pages/Diagnosis.tsx
(无输出，exit 1)
```

**AC-6 ⚠️ 未通过 — vitest 4 failed / 16 passed**
```
$ npx vitest run
 Test Files  2 passed (3)
      Tests  4 failed | 16 passed (24)
     Errors  1 error
   Start at  17:08:39
   Duration  630.40s
```
完整 4 个失败：
```
 FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-23: 登录成功 → 跳转首页
 FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-24: 登录失败 → 显示错误消息
 FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-26: 注册成功 → 自动登录
 FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > 注册失败：邮箱已被注册
 ❯ waitForWrapper node_modules/@testing-library/dom/dist/wait-for.js:163:27
 ❯ fillLoginForm tests/sit/auth-flow.test.tsx:86:9 / fillRegisterForm:102:9
   await waitFor(() => {
     const btn = screen.getByRole('button', { name: /登录|注册/ })
     expect(btn).not.toBeDisabled()
   })

[vitest-pool]: Worker forks emitted error.
[vitest-pool]: Timeout terminating forks worker for /tests/sit/auth-flow.test.tsx
```
**根因诊断**：`fireEvent.change` → `userEvent.type` 替换后，仍卡在 `waitFor(button not disabled)` 上 50000ms 超时。userEvent.type 触发的事件链对 antd `<Form>` 受控 + Form.Item rules validation 的同步性不足以让 submit button 在 waitFor 默认窗口内 enabled。worker 在 4 个 fail 后还触发 unexpected exit（与审计报告 P0-2 "worker 崩溃 CI 破窗"是同一类问题，userEvent 切换没根治）。

**需要后续修复方向**（超出本次 session 容量）：
1. 显式调用 `form.validateFields()` 替代 waitFor button enabled，或直接 `fireEvent.click` submit 让 antd Form 自己跑 validation
2. 排查 worker 异常退出根因（疑似 MSW + AuthProvider 的 doRefresh useEffect 在 unmount 时 race）

**TSC ✅**
```
$ npx tsc -b --noEmit; echo $?
0
```
0 error。

### 测试
- 单元/SIT：vitest 见上，AC-6 未达 24/24
- 类型：tsc 0 error
- Lint：未跑（任务未要求）

### 风险与遗留
1. **AC-6 未达**：auth-flow.test.tsx 4 个测试仍 fail，与 P0-2 同根因；需要专门一轮 debug，建议下一棒 frontend-dev-3 接手或回到 fireEvent + 显式 validateFields 策略
2. **AuthContext 5 处 fetch 保留**：符合指令例外，但若 reviewer 要求"零裸 fetch"，需要为 auth endpoints 在 client.ts 单独建一个不走 refresh-retry 拦截器的 axios 实例（`axios.create({ baseURL: '/api/v1' })` without interceptors）
3. **Trade.tsx 不在范围内的 fetch**：useLiveTrade.ts:204 还有一处下单 fetch（带 ?mode= 查询参），不在 T-002 描述的 "13 页" 范围内，未触碰（交易路径属高风险，按 CLAUDE.md 需 Plan Mode + tech-lead）

### 质量门
- vitest: ❌ 4 failed / 16 passed / 4 didn't run（worker exit）
- tsc: ✅ 0 error
- grep 验证: ✅ pages 零裸 fetch / Diagnosis 零 mock
- dev server: ❌ 未启动验证（session 容量耗尽前被 shutdown）

## 完成度
- AC-4 ✅ 完成
- AC-5 ✅ 完成
- AC-6 ⚠️ 部分完成（userEvent 切换已落码，但 4 个测试仍 fail，未达 24/24 全绿验收线）
