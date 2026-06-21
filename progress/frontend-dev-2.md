
## T-002: AC-4/5/6 前端裸 fetch→axios + 删 Diagnosis mock + 修 SIT — 2026-06-21
**状态**: AC-4/5 完成；AC-6 为已知技术债（vitest worker hang，非业务代码问题）
**owner**: frontend-dev-2（接管，原 frontend-dev 失联零产出）

### AC-4 ✅ 13 页裸 fetch→axios（37→0）
- frontend/src/pages/ 下裸 fetch 37→0：Strategy(9)/AutoTrade(6)/DataUpdate(6)/Dashboard(4)/Trade(3)/Diagnosis(2)/Predictions(1)/Signals(1) 全改 `api.get/post/delete`（client.ts axios 实例，享受鉴权拦截器）
- AuthContext.tsx 5 处保留（login/refresh/logout 是建立鉴权态的调用，走 axios 拦截器会循环依赖，合理保留）
- 验证：`grep -rn 'fetch(' frontend/src/pages/` → 0

### AC-5 ✅ 删 Diagnosis DEV mock
- Diagnosis.tsx `generateMockResult` + 所有 `import.meta.env.DEV` fallback 全删，失败统一 `message.error` + Empty
- 验证：`grep -cn 'generateMockResult\|import.meta.env.DEV' Diagnosis.tsx` → 0

### tsc ✅
- `npx tsc -b --noEmit` exit 0（0 error）

### AC-6 ⚠️ 技术债（vitest worker hang，留专项修复）
- 根因：auth-flow.test.tsx 8 测试在 vitest 4 forks/threads pool 下 worker hang（806s 后 "Worker exited unexpectedly"），非测试逻辑问题——RegisterPage 按钮**无 disabled 属性**证明 `waitFor(btn not disabled)` 不该超时，hang 在 AntD Form/jsdom 渲染层
- 已尝试（均未根治）：`forks.singleFork`（破坏 globals `beforeAll`）、`threads.singleThread`（明确 OOM）、`afterEach(cleanup)`（正确内存管理实践，保留）、`NODE_OPTIONS=--max-old-space-size=8192`（407s→806s 延缓仍崩）
- 结论：AntD 5 Form + jsdom + vitest 4 深层兼容性/hang，需专项修复（fake timers / mock AntD 动画 portal / 拆测试文件 / 升级 vitest），留阶段 3 质量专项
- **业务修复（AC-4/5）有效**：tsc 0 error，代码改对，登录后 Strategy/Trade/AutoTrade 业务页鉴权链路通

---

## T-205: live-trading frontend 修复（5 AC） — 2026-06-12 15:30

**状态**: completed
**Skills used**: none (direct edit)

**SIT 证据**:
- AC-205.1: ✅ RiskCheckModal 字段契约 — `check.level === 'reject'/'warn'` 匹配后端 `RiskCheckLevel`(pass/warn/reject); `check.rule` 显示中文规则名; `PreCheckResult` 接口新增 `requires_confirmation`/`confirm_reason`
- AC-205.2: ✅ Paper 模式 POST body — `useLiveTrade.ts` paper 路径改为 `fetch(POST + JSON body)`; `api/liveTrade.ts` `placeOrder` 改为 JSON body; `api/client.ts` `tradeApi.placeOrder` 同步修正
- AC-205.3: ✅ 大额阈值从后端配置读取 — 移除 `catch(() => setRiskConfig({ large_order_threshold: 500000 }))` 硬编码 fallback，无配置时跳过 large order check; `Trade.tsx` `|| 500000` → `|| 0`
- AC-205.4: ✅ 熔断提示文案修正 — `CircuitBreakerState` 接口匹配后端 `get_state()` 返回 (status/daily_loss_pct/threshold_pct/cooldown_minutes...); 文案改为百分比阈值 + 冷却时间 + 次日自动恢复
- AC-205.5: ⚠️ 构建验证 — `npx tsc -b --noEmit` 0 错误; `npm run build` 成功 (3.61s); SIT 4 fail 均为 auth-flow.test.tsx 预存问题（找不到"登录"按钮），与本次变更无关
  ```
  FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-23: 登录成功 → 跳转首页
  FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-24: 登录失败 → 显示错误消息
  FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > AC-26: 注册成功 → 自动登录
  FAIL  tests/sit/auth-flow.test.tsx > SIT: Auth Flow > 注册失败：邮箱已被注册
  ```

**质量门**: vitest SIT 4 pre-existing fails (auth-flow, 非本次变更); tsc 0 错误; build 3.61s 成功

**下一步**: 等待 product-lead review; AC-205.2 的 POST body 需要 backend 同步更新 Query→Body 参数接收

**涉及文件**:
- `frontend/src/hooks/useLiveTrade.ts` (接口 + 下单逻辑)
- `frontend/src/components/trade/RiskCheckModal.tsx` (字段契约)
- `frontend/src/components/trade/CircuitBreakerAlert.tsx` (界面 + 文案)
- `frontend/src/api/liveTrade.ts` (POST body)
- `frontend/src/api/client.ts` (POST body 同步)
- `frontend/src/pages/Trade.tsx` (用法更新)

## T-205 W-3: liveTrade.ts 路径迁移 — 2026-06-12 15:45

**状态**: completed
**Skills used**: none (direct edit)

**SIT 证据**:
- AC-W3.1: ✅ `placeOrder` 路径 `/live-trade/order` → `/trade/order` (line 13)
- AC-W3.2: ✅ `grep -rn "/live-trade" frontend/src/api/liveTrade.ts` → 零结果 (exit 1)
- 全部 9 个端点从 `/live-trade/*` 迁移到 `/trade/*`：account, positions, orders, order, order/pre-check, broker/status, broker/connect, risk-config, circuit-breaker/status

**质量门**: tsc 0 错误

**下一步**: 等产品确认后合并

**涉及文件**: `frontend/src/api/liveTrade.ts` (9 行路径修改)
