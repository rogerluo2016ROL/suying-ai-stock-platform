# 实盘交易 Frontend Code Review

> **日期**: 2026-06-10
> **审查范围**: BrokerStatus.tsx, LargeTradeConfirm.tsx, RiskCheckModal.tsx, CircuitBreakerAlert.tsx, useLiveTrade.ts, liveTrade.ts (api)
> **审查人**: code-reviewer
> **基准契约**: `docs/design/live-trading/api-contract.md`（草案）
> **Verdict**: **APPROVE WITH CHANGES** — UI 组件质量良好，但 useLiveTrade hook 存在 2 个 blocker 级别的风控流程问题和契约不一致

---

## 1. 概要

Frontend 实盘交易模块包含 4 个 UI 组件和 1 个核心 hook + API 层。组件层代码整洁、复用 Ant Design 模式得当。useLiveTrade hook 实现了完整的三步下单流程（风控预检 -> 大额确认 -> 提交订单）。

主要问题集中在：
- 前端与后端的风控字段契约不一致（`passed`/`block` vs `level`）
- Paper 模式下单使用 GET 式 query params（安全/日志问题）
- 熔断提示文案与后端行为不一致
- 大额确认组件中 `estimatedAmount` 属性未实际使用

---

## 2. 发现列表

### 2.1 Blocker（上线前必须修复）

#### B-1: `RiskCheckModal` 与后端 `RiskResult` 字段契约不匹配

**文件**: `RiskCheckModal.tsx:16-17`、`useLiveTrade.ts:21-29`、`risk_gateway.py:30-71`

前端 `PreCheckResult` 接口定义：

```typescript
export interface PreCheckResult {
  passed: boolean
  checks: Array<{
    name: string       // 规则名称
    passed: boolean    // 该项是否通过
    message: string
    block: boolean     // true = 拦截, false = 仅警告
  }>
}
```

后端 `RiskResult` / `RiskCheckItem` 结构：

```python
class RiskCheckItem:
    rule: str           # 规则名称（如 "资金充足"）
    level: RiskCheckLevel  # PASS / WARN / REJECT
    message: str
    detail: dict
```

**问题**: 字段名完全不一致：
- 前端期望 `name`，后端返回 `rule`
- 前端期望 `passed` (boolean) + `block` (boolean)，后端返回 `level` (PASS/WARN/REJECT)
- 前端 `RiskCheckModal` 按 `block` 区分拦截项和警告项（`blockingChecks` vs `warningChecks`），后端没有对应的字段

当前没有任何转换层。如果 API 返回后端格式，前端无法正确渲染风控结果。

**建议**:
1. 在 `useLiveTrade` hook 的 `preCheck` 调用后添加字段映射：

```typescript
const mapped = {
  passed: !result.checks.some(c => c.level === 'reject'),
  checks: result.checks.map(c => ({
    name: c.rule,
    passed: c.level !== 'reject',
    message: c.message,
    block: c.level === 'reject',
  })),
}
```

2. 或者统一后端响应格式，直接返回 `passed` + `block`

#### B-2: Paper 模式使用 URL query params 发送 POST 下单请求

**文件**: `useLiveTrade.ts:191-195`

```typescript
const r = await fetch(
  `/api/v1/trade/order?code=${encodeURIComponent(params.code)}&direction=${params.direction}&price=${params.price}&volume=${params.volume}`,
  { method: 'POST' },
)
```

**问题**:
1. 下单参数（股票代码、方向、价格、数量）暴露在 URL 中 —— 可被浏览器历史、代理服务器日志、CDN 日志、Nginx access log 记录，违反金融数据安全最佳实践
2. 使用原生 `fetch` 而非项目统一的 `api` client（`import api from './client'`），可能绕过：
   - Auth token 自动注入
   - 请求/响应拦截器
   - 统一错误处理
3. 与 api-contract 规定的 JSON body 格式不一致（api-contract §5.2 定义 `POST /api/v1/trade/order` 使用 JSON body）
4. `encodeURIComponent` 对中文和特殊字符处理不当可能导致乱码或请求失败

**建议**: 统一使用 JSON body POST 通过项目 `api` client：

```typescript
const r = await api.post('/api/v1/trade/order', {
  code: params.code,
  direction: params.direction,
  price: params.price,
  volume: params.volume,
})
```

---

### 2.2 High Severity

#### H-1: 前端大额确认阈值与后端风控阈值独立配置，可能不一致

**文件**: `useLiveTrade.ts:79-84`、`risk_gateway.py:77`

前端：
```typescript
liveTradeApi.getRiskConfig()
  .then(r => setRiskConfig(r.data))
  .catch(() => {
    setRiskConfig({ large_order_threshold: 500000 })
  })
```

后端：
```python
_LARGE_TRADE_THRESHOLD = float(os.environ.get("RISK_LARGE_TRADE_THRESHOLD", "500000"))
```

**问题**:
1. 前端的 `RiskConfig` 来自 `/live-trade/risk-config` API，但 fallback 值为 500000 硬编码。如果 API 不可用，前端用硬编码的 500000，但后端可能配置了不同的阈值
2. 前端也有自己的大额检查逻辑（`useLiveTrade.ts:176-187`），而后端 `risk_gateway.py` 也有 `_check_large_trade()`。如果两端阈值不同：
   - 前端阈值大于后端：后端 WARN 但前端不弹确认 → 用户不知情
   - 前端阈值小于后端：后端 PASS 但前端弹确认 → 用户体验差

**建议**:
1. 前端的大额检查应从后端统一获取阈值，不要在前端重复实现风控逻辑
2. 或者只保留后端风控 + 后端返回 `requires_confirmation` 标志，前端根据该标志决定是否弹窗
3. Fallback 默认值应使用环境变量或配置文件统一管理

#### H-2: `useLiveTrade` 中大额确认对市价单的处理存在逻辑漏洞

**文件**: `useLiveTrade.ts:177-187`

```typescript
const estimatedAmount = params.price > 0
  ? params.price * params.volume
  : 0 // Market order - cannot estimate, always confirm

if (estimatedAmount === 0 || estimatedAmount >= riskConfig.large_order_threshold) {
  const confirmed = await callbacks.onLargeOrderConfirm?.(params)
  if (!confirmed) {
    return { success: false, error: '用户取消大额交易' }
  }
}
```

**问题**:
1. `estimatedAmount === 0` 对所有市价单（`price === 0`）触发大额确认，包括买入 100 股的小额市价单。这不符合"大额交易确认"的设计意图 —— 小额市价单不应该弹出确认
2. 市价单虽然无法预估精确金额，但可以根据市价预估（如使用最新成交价或行情快照计算参考金额），仅对参考金额超过阈值的市价单弹确认
3. 如果 `riskConfig` 为 null（API 失败且无 fallback），`riskConfig.large_order_threshold` 会抛出 TypeError

**建议**:
1. 市价单不应无条件触发大额确认，仅当有合理预估金额且超过阈值时才弹窗
2. 为市价单获取最新行情价格作为预估基准
3. 添加 `riskConfig?.large_order_threshold` 的安全访问

#### H-3: `CircuitBreakerAlert` 文案与后端实际行为不一致

**文件**: `CircuitBreakerAlert.tsx:42`

```tsx
<Text type="secondary" style={{ fontSize: 12 }}>
  如需恢复，请联系管理员或等待次日自动重置。
</Text>
```

**后端实际行为** (`circuit_breaker.py:110-118`):

```python
if state.status == BreakerStatus.TRIGGERED and state.triggered_at is not None:
    elapsed = (datetime.now(timezone.utc) - state.triggered_at).total_seconds()
    if elapsed >= _COOLDOWN_MINUTES * 60:
        logger.info("Circuit breaker cooldown expired...")
        # Don't auto-reset to NORMAL — require manual reset for safety.
```

**问题**: 前端告诉用户"等待次日自动重置"，但后端：
1. 不会自动重置（注释明确说 "require manual reset for safety"）
2. 即使次日，也仅当 `_get_or_create()` 检测到日期变更时才重置（这是唯一自动重置路径）
3. 冷却时间（默认 30 分钟）到期后不会自动恢复，仅记录日志

这会导致用户误以为熔断会在次日自动解除，但实际上除非恰好跨天，否则熔断会一直持续到管理员手动 reset。

**建议**: 文案改为"如需恢复，请联系管理员手动重置。系统将在下一交易日自动重置。"

---

### 2.3 Medium Severity

#### M-1: `LargeTradeConfirm` 组件中 `estimatedAmount` prop 未被使用

**文件**: `LargeTradeConfirm.tsx:17-76`

组件接受 `estimatedAmount` prop，但在 JSX 中显示预估金额时直接计算：

```tsx
<Descriptions.Item label="预估金额">
  <Text type="danger" strong>
    ¥{orderParams.price > 0
      ? (orderParams.price * orderParams.volume).toLocaleString()
      : '市价成交，金额待定'}
  </Text>
</Descriptions.Item>
```

**问题**: `estimatedAmount` prop 传入但从未用于显示。如果调用方传入的 `estimatedAmount` 与组件内部计算不一致（如包含了手续费），用户看到的是组件内部计算值而非传入值，造成显示偏差。

**建议**: 使用 `estimatedAmount` prop 进行显示，移除内联计算：

```tsx
¥{estimatedAmount > 0 ? estimatedAmount.toLocaleString() : '市价成交，金额待定'}
```

#### M-2: 前端 API 路径与 api-contract 不完全一致

**文件**: `liveTrade.ts:5-49`、`api-contract.md:545-887`

| 功能 | 前端实际路径 | api-contract 路径 |
|---|---|---|
| 下单 | `POST /live-trade/order?code=...` | `POST /api/v1/trade/order` (JSON body) |
| 券商状态 | `GET /live-trade/broker/status` | `GET /api/v1/trade/broker/status` |
| 券商连接 | `POST /live-trade/broker/connect` | `POST /api/v1/trade/broker/connect` |
| 风控预检 | `POST /live-trade/order/pre-check` | 无独立端点（内嵌在 POST /order 流程中） |
| 风控配置 | `GET /live-trade/risk-config` | 无对应端点 |
| 熔断状态 | `GET /live-trade/circuit-breaker/status` | `GET /api/v1/trade/circuit-breaker` |
| 模式切换 | `POST /trade/mode` | `PUT /api/v1/trade/mode` |

**问题**:
1. 前缀不一致：前端用 `/live-trade`，api-contract 用 `/api/v1/trade`。如果 API gateway 做了 rewrite，需确认
2. HTTP method 不一致：模式切换前端用 `POST`，api-contract 规定 `PUT`
3. `preCheck` 和 `risk-config` 端点在 api-contract 中无对应定义 —— 属于实现超出契约范围

**建议**: 统一路径，或在 api-contract 中更新以反映实际实现。

#### M-3: `useLiveTrade` 中 `apiPrefix` 定义但未用于实际请求

**文件**: `useLiveTrade.ts:65`

```typescript
const apiPrefix = mode === 'paper' ? '/api/v1/trade' : '/api/v1/live-trade'
```

`apiPrefix` 在 hook 中定义，但：
1. 不在 return 值中暴露
2. 不在 hook 内部的任何请求中使用（所有请求硬编码路径）
3. 删除它不会影响任何功能

**建议**: 如果 `apiPrefix` 是给组件使用的，应在 return 中暴露并确保文档说明；否则删除。

---

### 2.4 Low Severity

#### L-1: `BrokerStatus` 缺少"重试中"和"已过期"状态

**文件**: `BrokerStatus.tsx:7-16`

```typescript
const statusConfig: Record<BrokerStatusType, {...}> = {
  connected:    { status: 'success', ... },
  disconnected: { status: 'error', ... },
  connecting:   { status: 'processing', ... },
  error:        { status: 'warning', ... },
}
```

api-contract 的 `BrokerConnectionStatus` 包含 `reconnect_count` 和 `reconnect_max` 字段，暗示存在自动重连中状态。当前 UI 无法区分"初始断开"和"重试中"。

#### L-2: `RiskCheckModal` 中 `onOk` 和 `onCancel` 行为相同

**文件**: `RiskCheckModal.tsx:27-31`

```tsx
onOk={onClose}
onCancel={onClose}
cancelButtonProps={{ style: { display: 'none' } }}
```

隐藏 Cancel 按钮的同时绑定 `onCancel` 是无害冗余，但 `onCancel` 绑定可移除（cancel 按钮已隐藏，用户无法触发）。

#### L-3: `formatRiskErrorMessage` 规则名映射与后端不一致

**文件**: `RiskCheckModal.tsx:107-122`

```typescript
const nameMap: Record<string, string> = {
  insufficient_funds: '资金不足',
  position_limit: '超持仓上限',
  circuit_breaker: '熔断保护',
  ...
}
```

后端 `RiskCheckItem.rule` 使用中文名称（如"资金充足"、"持仓充足"、"仓位上限"），前端 nameMap 使用英文 key（如 `insufficient_funds`、`position_limit`）。如果 API 不返回这些英文 key，nameMap 永远不会匹配，`formatRiskErrorMessage` 的效果等于直接拼接。

#### L-4: `useLiveTrade` 定时器未清理时的内存泄漏风险

**文件**: `useLiveTrade.ts:88-127`

两个 `useEffect` 每 10s/30s 轮询一次，且有 `clearInterval` 清理。实现正确。

但 `connectBroker` 是 async callback，如果在 `setBrokerStatus('connecting')` 后组件卸载，状态更新会触发 React warning。建议添加 `AbortController` 或检查组件挂载状态。

---

## 3. 契约一致性检查

| 检查项 | 状态 | 说明 |
|---|---|---|
| 下单使用 JSON body | FAIL | Paper 模式用 URL query params（**B-2**） |
| API 路径前缀 `/api/v1/trade` | PARTIAL | 前端使用 `/live-trade` 前缀（**M-2**） |
| 模式切换用 PUT | FAIL | 前端用 POST（**M-2**） |
| 风控字段 `passed`/`block` | FAIL | 后端返回 `level`（**B-1**） |
| 熔断三态 UI | PARTIAL | 前端仅展示 triggered/not triggered（**H-3**） |
| 审计日志查看权限 | OK | `useLiveTrade` 导出 `getAuditLogs` / `exportAuditLogs` |
| 下单二次确认 | OK | `LargeTradeConfirm` 实现完整 |
| 风控拦截弹窗 | PARTIAL | `RiskCheckModal` 实现到位但字段名不匹配（**B-1**） |

---

## 4. 错误处理审查

| 场景 | 处理情况 | 评级 |
|---|---|---|
| 风控 API 不可用 | catch 后返回错误，阻止下单 | OK |
| 风控配置 API 不可用 | catch 后使用硬编码 fallback（500000） | MEDIUM — 见 **H-1** |
| 券商状态 API 不可用 | catch 后设为 `disconnected` | OK |
| 熔断状态 API 不可用 | catch 后设为 null（不显示 alert） | MEDIUM — 静默隐藏熔断信息 |
| 下单 API 失败 | catch 后显示错误 message | OK |
| 大额确认被取消 | 返回 `{ success: false }` | OK |
| `onLargeOrderConfirm` 回调未提供 | 使用 `?.` 安全调用，返回 undefined（falsy）→ 不发送订单 | OK |
| BrokerStatus 断开检测 | 轮询时检测状态变更并 message.warning | OK |

---

## 5. 组件质量评估

| 组件 | 代码整洁度 | 可访问性 | 边界处理 | 备注 |
|---|---|---|---|---|
| `BrokerStatus` | 干净 | 基本 | 好 | 简单紧凑 |
| `LargeTradeConfirm` | 好 | 好 | 中等 | **M-1**: `estimatedAmount` 未使用 |
| `RiskCheckModal` | 好 | 好 | 好 | **B-1**: 字段契约不匹配 |
| `CircuitBreakerAlert` | 干净 | 好 | 好 | **H-3**: 文案不准确 |
| `useLiveTrade` | 中等 | N/A | 有缺陷 | **B-2** + **H-1** + **H-2** |
| `liveTrade` (api) | 干净 | N/A | 好 | **M-2**: 路径不一致 |

---

## 6. Verdict

**APPROVE WITH CHANGES**

Frontend 组件层（BrokerStatus、LargeTradeConfirm、RiskCheckModal、CircuitBreakerAlert）代码整洁，UI/UX 设计合理，Ant Design 模式使用得当。

**必须修复（Blocker）**:
1. **B-1**: 风控结果字段映射 — `RiskCheckModal` 与后端字段不匹配，当前无法正确展示风控结果
2. **B-2**: Paper 模式 POST 下单改用 JSON body + 统一 `api` client — 敏感参数不应暴露在 URL 中

**强烈建议（High）**:
1. **H-1**: 统一前后端大额阈值来源 — 避免两端阈值不一致导致的行为差异
2. **H-2**: 修复市价单无条件触发大额确认的逻辑
3. **H-3**: 修正熔断文案 — "等待次日自动重置" 与后端行为不符
