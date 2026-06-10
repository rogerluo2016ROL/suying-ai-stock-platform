# 实盘交易 Backend Code Review

> **日期**: 2026-06-10
> **审查范围**: broker_interface.py, xtquant_broker.py, risk_gateway.py, audit_log.py, circuit_breaker.py, 002_add_audit_logs.py
> **审查人**: code-reviewer
> **基准契约**: `docs/design/live-trading/api-contract.md`（草案）
> **Verdict**: **APPROVE WITH CHANGES** — 核心架构合理，但存在 3 个 blocker、5 个 high-severity 问题需在实盘上线前解决

---

## 1. 概要

Backend 实现了实盘交易的 5 个核心模块：BrokerInterface 抽象层（ABC）、XtquantBroker（含 stub fallback）、RiskGateway（6 项风控检查）、AuditLog（append-only 审计日志）、CircuitBreaker（日内亏损熔断）。

整体代码质量良好：类型注解完整、dataclass 封装清晰、环境变量配置化。但存在以下需关注的问题：

- **审计日志表名**与 api-contract 不一致（`audit_logs` vs `trade_audit_log`）
- **风控字段契约**前后端不匹配（`level` vs `passed`/`block`）
- **熔断状态机**简化过度，缺失 HALF_OPEN 状态和数据库持久化
- **XtquantBroker 在真实环境下的错误处理**存在静默 fallback 到 stub 的风险
- **TRUNCATE 绕过审计触发器**的风险

---

## 2. 发现列表

### 2.1 Blocker（上线前必须修复）

#### B-1: XtquantBroker 在 xtquant SDK 可用但未连接时静默 fallback 到 stub

**文件**: `xtquant_broker.py:119-123`

```python
async def place_order(self, order: OrderRequest) -> OrderResult:
    if _XTQUANT_AVAILABLE and self._trader is not None:
        # TODO: wire to xtquant.xttrader.order_stock(...)
        logger.info("xtquant place_order not yet wired — falling back to stub")
    return self._place_order_stub(order)
```

**问题**: 当 xtquant SDK 已安装（`_XTQUANT_AVAILABLE = True`）但 `connect()` 未被调用或连接失败（`_trader is None`）时，下单仍然会执行并返回 stub 成交。生产环境中这意味着：**在没有真实券商连接的情况下，系统会静默执行虚假成交**，用户以为交易成功，实际上券商侧并未收到任何委托。

**建议**:
1. 当 `_XTQUANT_AVAILABLE = True` 且 `_trader is None` 时，`place_order()` 应抛出异常或返回 `OrderResult(status=OrderStatus.REJECTED, message="broker not connected")`
2. 同样的问题存在于 `cancel_order()`、`get_positions()`、`get_account()` 中

#### B-2: 审计日志表名不一致 — 与 api-contract 冲突

**文件**: `002_add_audit_logs.py:27`、`audit_log.py:24`、`api-contract.md:76`

| 来源 | 表名 |
|---|---|
| api-contract.md | `trade_audit_log` |
| alembic migration | `audit_logs` |
| audit_log.py | `audit_logs` |

**问题**: api-contract 明确指定表名为 `trade_audit_log`，但实现使用 `audit_logs`。这会导致：
- 其他模块引用时产生歧义
- 与 api-contract 中定义的 `trade_audit_log` 索引、触发器名称不一致
- 如果将来有另一个 `audit_logs` 表（如登录审计），会产生命名冲突

**建议**: 统一为 `trade_audit_log` 或更新 api-contract。推荐统一到 `trade_audit_log`（更精确，避免与通用审计日志混淆）。

#### B-3: 风控结果字段契约前后端不一致

**文件**: `risk_gateway.py:30-71`（后端）、`RiskCheckModal.tsx:16-17`（前端）、`useLiveTrade.ts:21-29`（前端 PreCheckResult 接口）

| 后端 `RiskCheckItem` | 前端 `PreCheckResult.checks[]` |
|---|---|
| `level: RiskCheckLevel` (PASS/WARN/REJECT) | `passed: boolean` + `block: boolean` |
| `rule: str` | `name: str` |

**问题**: 后端返回 `level` 三态枚举，前端期望 `passed` (boolean) + `block` (boolean) 两个字段。当前没有任何转换层，前后端无法正确对接。

**建议**:
- 在 API 响应序列化层添加转换：`REJECT -> {passed: false, block: true}`, `WARN -> {passed: true, block: false}`, `PASS -> {passed: true, block: false}`
- 或者统一字段命名，建议后端响应直接使用 `passed` + `block`

---

### 2.2 High Severity

#### H-1: 熔断状态机缺失 HALF_OPEN 状态，与 api-contract 三态模型不一致

**文件**: `circuit_breaker.py:20-22`、`api-contract.md:900-913`

```python
class BreakerStatus(StrEnum):
    NORMAL = "NORMAL"        # closed — trading allowed
    TRIGGERED = "TRIGGERED"  # open — all live orders blocked
```

**问题**:
1. api-contract 定义了三态状态机：CLOSED -> OPEN -> HALF_OPEN -> CLOSED/OPEN。实现只有 NORMAL / TRIGGERED 两态
2. HALF_OPEN 允许一笔试探订单的设计完全缺失
3. 冷却时间到期后不会自动进入 HALF_OPEN，仅记录日志（`circuit_breaker.py:117`），必须手动 reset
4. 前端 `CircuitBreakerAlert.tsx:42` 文案写"等待次日自动重置"，但实际不会自动重置

**建议**: 实现完整三态状态机，或明确在 ADR 中记录简化决策并更新 api-contract。

#### H-2: 熔断状态仅内存存储，服务重启后丢失

**文件**: `circuit_breaker.py:43`

```python
_breakers: dict[str, BreakerState] = {}
```

**问题**:
1. 服务重启后所有熔断状态丢失，日亏损计数归零，已触发的熔断会解除
2. api-contract 定义了 `circuit_breaker_state` 持久化表（含 `breaker_type`, `status`, `daily_pnl`, `triggered_at` 等字段），但未实现
3. 如果交易服务发生 OOM/crash/重启，熔断保护完全失效

**建议**: 将 `BreakerState` 持久化到 `circuit_breaker_state` 表，每次状态变更写入 DB，启动时从 DB 恢复。

#### H-3: `pre_check()` 无调用强制保障 — 风控可被绕过

**文件**: `risk_gateway.py:82-138`

**问题**: `risk_gateway.pre_check()` 是一个独立的 async 函数，没有任何机制强制 trade router 在下单前调用它。如果未来有新开发者或新路径直接调用 `broker.place_order()`，所有风控检查会被完全绕过。

**建议**:
1. 将对 `pre_check()` 的调用内聚到 trade router 的下单处理函数中，作为不可跳过的步骤
2. 或者将 RiskGateway 封装为 `BrokerInterface` 的装饰器/代理（Decorator pattern），使 `place_order()` 自动经过风控
3. 添加集成测试验证：绕过 pre_check 直接调用 broker 的下单请求应被拒绝

#### H-4: 审计日志 TRUNCATE 可绕过 append-only 触发器

**文件**: `002_add_audit_logs.py:72-83`

```sql
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE ON audit_logs
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_audit_mutation();

CREATE TRIGGER trg_audit_no_delete
    BEFORE DELETE ON audit_logs
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_audit_mutation();
```

**问题**: 触发器仅拦截 UPDATE 和 DELETE，但 PostgreSQL 的 `TRUNCATE` 语句不会触发 `BEFORE UPDATE` 或 `BEFORE DELETE` 触发器。拥有足够权限的用户可以通过 `TRUNCATE audit_logs` 清空整个审计日志表。

**建议**: 添加 `BEFORE TRUNCATE` 触发器：

```sql
CREATE TRIGGER trg_audit_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT
    EXECUTE FUNCTION prevent_audit_mutation();
```

注意：TRUNCATE 触发器需要 `FOR EACH STATEMENT` 且在 PostgreSQL 中需要显式创建。

#### H-5: `OrderRequest.quantity` 未校验 A 股 100 股整数倍

**文件**: `broker_interface.py:36`

```python
quantity: int               # shares
```

**问题**: api-contract 的 `PlaceOrderRequest` Pydantic schema 包含 `@model_validator` 校验 `volume % 100 != 0`（A 股委托股数必须为 100 的整数倍）。但 `BrokerInterface` 的 `OrderRequest` dataclass 没有此校验。这意味着不合规的股数可以通过 dataclass 直接传入 broker。

**建议**: 在 `OrderRequest` 的 `__post_init__` 中添加校验，或者在上层 trade router 的 schema 层强制校验（推荐后者，保持 dataclass 简洁）。

---

### 2.3 Medium Severity

#### M-1: BrokerInterface 与 api-contract 方法签名不一致

**文件**: `broker_interface.py:97-155`、`api-contract.md:294-357`

| 方法 | api-contract | 实际实现 |
|---|---|---|
| `connect()` | `connect(config: dict) -> bool` | 未定义在 ABC 中（仅在 XtquantBroker 中） |
| `disconnect()` | `disconnect() -> bool` | 未定义在 ABC 中（仅在 XtquantBroker 中） |
| `get_status()` | `get_status() -> BrokerConnectionStatus` | 未定义 |
| `place_order()` | `place_order(code, direction, price, volume, order_type) -> BrokerOrder` | `place_order(order: OrderRequest) -> OrderResult` |
| `cancel_order()` | `cancel_order(broker_order_id) -> bool` | `cancel_order(order_id: str) -> CancelResult` |
| `query_order()` | `query_order(broker_order_id) -> BrokerOrder` | 未定义 |
| `query_orders()` | `query_orders() -> list[BrokerOrder]` | 未定义 |
| `query_positions()` | `query_positions() -> list[BrokerPosition]` | `get_positions() -> list[Position]` |
| `query_account()` | `query_account() -> BrokerAccount` | `get_account() -> AccountInfo` |

**问题**: 实际实现与 api-contract 存在显著偏差。虽然简化设计有其合理性（使用 dataclass 封装参数、减少方法数量），但需要记录决策并更新 api-contract。

**建议**: 更新 api-contract 以反映实际实现，或在 ADR 中记录偏差原因。

#### M-2: 价格涨跌停检查为"尽力而为"，未实现真正的 ±10% 限制

**文件**: `risk_gateway.py:185-203`

```python
def _check_price_limit(order: OrderRequest) -> RiskCheckItem:
    # Best-effort: flag extremely large prices
    if order.price > 10000:
        return RiskCheckItem(..., level=RiskCheckLevel.WARN, ...)
    return RiskCheckItem(rule="涨跌停", level=RiskCheckLevel.PASS)
```

**问题**: 注释说明"Without real-time quotes this is a best-effort check"，仅对 >10000 的价格发出 WARN，而非真正的 ±10% 涨跌停校验。这导致：
1. 可以以偏离市价 50% 的价格下单而不被拦截
2. 在实盘环境可能造成严重损失（如误将 10.00 输成 100.00 不会被拦截，因为 100.00 < 10000）

**建议**: 在下单流程中注入实时行情（从 xtquant 或 K 线数据获取 `latest_price`），基于 `latest_price` 计算 ±10% 区间进行校验。在实时行情可用前，至少将 WARN 阈值从 10000 降到更合理的值（如单价的 2 倍偏离）。

#### M-3: XtquantBroker 无法在实例化时区分"SDK 未安装"和"SDK 已安装但未连接"

**文件**: `xtquant_broker.py:90`

```python
self._is_live = _XTQUANT_AVAILABLE
```

**问题**: `is_live` 在 `__init__` 中被设置为 `_XTQUANT_AVAILABLE`（模块级导入检测结果），而不是反映实际连接状态。这意味着：
1. SDK 已安装但从未调用 `connect()` 时 → `is_live = True, connected = False` 
2. SDK 已安装且连接失败时 → `is_live = True, connected = False`
3. 只有 `_connect_real()` 成功后才会设置 `self._is_live = True`（再次确认）

`is_live` 的语义应为"当前是否使用真实券商执行"，应在 `connect()` 成功后才设为 True。

**建议**: `is_live` 初始值应为 `False`，仅在 `_connect_real()` 返回 True 后设为 True。

#### M-4: Paper 模式前端下单使用 GET 式 query params 而非 JSON body

**文件**: `useLiveTrade.ts:192-194`

```typescript
const r = await fetch(
  `/api/v1/trade/order?code=${encodeURIComponent(params.code)}&direction=...&price=...&volume=...`,
  { method: 'POST' },
)
```

**问题**: 
1. 敏感参数（下单信息）暴露在 URL 中，可被浏览器历史、代理日志、服务器访问日志记录
2. 与 api-contract 规定的 JSON body 格式不一致
3. 使用原生 `fetch` 而非项目统一的 `api` client，可能绕过 auth interceptor

**建议**: 统一使用 JSON body POST，通过项目 `api` client 发送。

---

### 2.4 Low Severity

#### L-1: `_stub_*` 变量为类变量，注释说明多实例共享但实现有歧义

**文件**: `xtquant_broker.py:64-78`

类变量 `_stub_orders`、`_stub_positions`、`_stub_account` 等通过类名和 `self` 混合访问。例如 `_connect_stub()` 中 `self._stub_connected = True` 实际上是在实例上创建了一个同名实例属性，会遮蔽类变量。

**建议**: 统一使用 `XtquantBroker._stub_connected` 或 `cls._stub_connected` 访问类变量。

#### L-2: `record()` 未刷新/提交 session

**文件**: `audit_log.py:39-99`

`record()` 执行 INSERT 后不调用 `await db.commit()`，依赖调用方管理事务。这是合理的设计（让调用方控制事务边界），但需在 docstring 中明确说明。

**建议**: 在 docstring 中补充："调用方负责 commit/flush session"。

#### L-3: `_check_concentration()` 对卖出单直接返回 PASS

**文件**: `risk_gateway.py:212-213`

```python
if order.side != OrderSide.BUY:
    return RiskCheckItem(rule="仓位上限", level=RiskCheckLevel.PASS)
```

卖出单不检查集中度是合理的，但 api-contract 预设的规则列表中包含 `max_positions`（最大持仓数），当前未实现。

#### L-4: CircuitBreaker 无并发安全保护

**文件**: `circuit_breaker.py:43`

`_breakers` dict 无锁保护。高并发场景下 `_get_or_create()` 和 `check_daily_loss()` 的读写存在 race condition。

**建议**: 使用 `asyncio.Lock` 保护每个 account 的 breaker 状态变更。

---

## 3. 契约一致性检查

| api-contract 元素 | 实现状态 | 偏差说明 |
|---|---|---|
| `trade_audit_log` 表 | 实现为 `audit_logs` | **B-2**: 表名不一致 |
| append-only 触发器 | 已实现 | **H-4**: 缺少 TRUNCATE 防护 |
| `broker_configs` 表 | 未实现 | Phase 4 范围 |
| `risk_rules` 表 | 未实现 | 当前用 env vars 代替 |
| `circuit_breaker_state` 表 | 未实现 | **H-2**: 仅内存存储 |
| `live_orders` / `live_positions` 表 | 未实现 | Phase 5 范围 |
| BrokerInterface ABC | 部分实现 | **M-1**: 方法数量/签名偏差 |
| BrokerException 层级 | 未实现 | api-contract 定义了 5 个异常类 |
| RiskCheckResult 字段 | 字段名不一致 | **B-3**: `level` vs `passed`/`block` |
| CircuitBreaker 三态 | 两态简化 | **H-1**: 缺少 HALF_OPEN |
| `POST /order` JSON body | 未验证 | API 路由层代码未在审查范围内 |

---

## 4. 错误处理审查

| 场景 | 处理情况 | 评级 |
|---|---|---|
| xtquant SDK 未安装 | 自动 fallback 到 stub mode + warning log | OK |
| xtquant 连接失败 | `_connect_real()` 捕获异常返回 False | OK |
| xtquant 已安装但未连接 | 静默 fallback 到 stub（**B-1**） | BLOCKER |
| xtquant 中途断连 | 无检测机制（`connected` 属性仅检查 `_trader is not None`） | HIGH |
| xtquant 下单失败 | 未实现（TODO stubs） | PENDING |
| 风控服务异常 | `pre_check()` 无 try/catch，异常会传播到调用方 | MEDIUM |
| 数据库不可用 | `audit_log.record()` 异常传播到调用方 | OK |

---

## 5. 安全性审查

| 检查项 | 状态 |
|---|---|
| 审计日志 INSERT-only（代码层） | PASS — `record()` 仅 INSERT |
| 审计日志 UPDATE/DELETE 拦截（DB 层） | PARTIAL — 触发器拦截 UPDATE/DELETE，但 TRUNCATE 未拦截（**H-4**） |
| 审计日志无 UPDATE/DELETE API 端点 | NOT IN SCOPE — 路由层代码未审查 |
| 风控检查在下单前强制调用 | FAIL — `pre_check()` 无强制保障（**H-3**） |
| 交易密码加密存储 | NOT IN SCOPE — `broker_configs` 表未实现 |
| 下单参数校验（A 股 100 股倍数） | FAIL — BrokerInterface 层无校验（**H-5**） |

---

## 6. Verdict

**APPROVE WITH CHANGES**

Backend 核心架构（ABC + RiskGateway + AuditLog + CircuitBreaker）设计合理，代码整洁。但在实盘上线前必须解决以下问题：

**必须修复（Blocker）**:
1. **B-1**: XtquantBroker 在未连接时静默 fallback 到 stub — 可能导致虚假成交
2. **B-2**: 审计日志表名统一（`audit_logs` → `trade_audit_log`）
3. **B-3**: 风控结果字段与前端契约对齐（`level` → `passed`/`block`）

**强烈建议（High）**:
1. **H-1**: 实现完整三态熔断状态机（或更新 api-contract 记录偏差）
2. **H-2**: 熔断状态持久化到 DB
3. **H-3**: 风控检查与下单流程强绑定
4. **H-4**: 添加 TRUNCATE 触发器
5. **H-5**: 添加 A 股 100 股倍数校验

**当前阶段可接受（Phase 1 scope）**:
- Xtquant 真实 API 未接线（TODO stubs）— 属于 Phase 5 范围
- `broker_configs`/`risk_rules`/`live_orders` 表未实现 — 属于后续 Phase 范围
- 异常层级未实现 — api-contract 标注为草案，可后续补充
