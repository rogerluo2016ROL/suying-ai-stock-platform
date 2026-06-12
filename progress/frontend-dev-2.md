
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
