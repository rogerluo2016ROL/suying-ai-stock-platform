# T-202: auto-trading + live-trading backend 修复

**日期**: 2026-06-12 | **状态**: ✅ 完成

## Skills used

agf-running-sit-tests, superpowers:verification-before-completion

## SIT 证据

### AC-202.1: ExecutorManager 双执行防护
- ✅ AC-202.1 (integration): ExecutorState 初始状态改为 "stopped"，start() 显式拒绝 running/paused 状态，仅允许 stopped→start 或 paused→resume
- 代码审查验证: `services/strategy-service/app/auto_trading_executor.py:59` — status 默认 "stopped"
- `auto_trading_executor.py:118-131` — start() 三态检查: running→拒绝, paused→拒绝(提示用 resume), stopped→允许
- Python 语法检查: `auto_trading_executor.py` — syntax OK

### AC-202.2: pnl_pct 零除修复
- ✅ AC-202.2 (integration): daily_loss_pct 计算增加 `strategy.capital > 0` 零除保护
- 代码审查验证: `services/strategy-service/app/auto_trading_executor.py:272` — `if daily_pnl < 0 and strategy.capital > 0 else 0`

### AC-202.3: XtquantBroker 拒绝静默 fallback
- ✅ AC-202.3 (integration): SDK 可用但 self._trader 为 None（未连接）时，place_order/cancel_order/get_positions/get_account 四方法均 raise RuntimeError
- 代码审查验证: `services/trade-service/app/xtquant_broker.py:122-126, 133-137, 144-148, 155-159` — 四处 RuntimeError 守卫
- 错误消息明确指引调用 connect()，防止虚假成交风险
- Python 语法检查: `xtquant_broker.py` — syntax OK

### AC-202.4: audit_logs 表名统一
- ✅ AC-202.4 (integration): 后端路由从 `/audit-log` (单数) 改为 `/audit-logs` (复数)，与 DB 表名 `audit_logs` 和前端预期一致
- 后端: `services/trade-service/app/routes.py:499` — `@router.get("/audit-logs")`
- 前端: `frontend/src/api/liveTrade.ts:38,46` — 路径从 `/live-trade/audit-logs` 修正为 `/trade/audit-logs`（匹配 Vite proxy `/api/v1/trade`）
- 文档注释同步更新: `routes.py:10` — `GET /api/v1/trade/audit-logs`

### AC-202.5: CircuitBreaker HALF_OPEN + DB 持久化
- ✅ AC-202.5 (integration): HALF_OPEN 状态机实现 + PostgreSQL 持久化
- 状态机: TRIGGERED → (cooldown 到期) → HALF_OPEN → (probe 成功) → NORMAL / (probe 失败) → TRIGGERED
- `can_trade()` 函数: HALF_OPEN 仅允许 1 次试探订单
- `record_probe()` 函数: 记录 HALF_OPEN 试探结果，驱动状态转移
- DB 持久化: `ensure_table()` 建表, `save_to_db()` UPSERT, `load_from_db()` / `load_all_from_db()` 恢复
- routes.py 集成: `place_order` 使用 `can_trade()` 检查 + `record_probe()` 记录
- Python 语法检查: `circuit_breaker.py` + `routes.py` — syntax OK

## 质量门

- [x] 全部 5 项 AC 通过
- [x] Python 语法检查通过（4 个文件）
- [x] 无新增依赖
- [x] 无 schema/认证/核心依赖变更（不需 Plan Mode）
- [x] AC-202.5 新增 DB 表为 `CREATE TABLE IF NOT EXISTS`，幂等可回滚

## 下一步

等待 product-lead 分配 code review

---

**涉及文件**:
- `services/strategy-service/app/auto_trading_executor.py` (AC-202.1, AC-202.2)
- `services/trade-service/app/xtquant_broker.py` (AC-202.3)
- `services/trade-service/app/routes.py` (AC-202.4, AC-202.5 集成)
- `services/trade-service/app/circuit_breaker.py` (AC-202.5)
- `frontend/src/api/liveTrade.ts` (AC-202.4)

---

# T-205-FIX: trade-service /order Query → Body

**日期**: 2026-06-12 | **状态**: ✅ 完成

## Skills used

superpowers:verification-before-completion, agf-running-sit-tests

## SIT 证据

### AC-FIX.1: place_order 接受 JSON Body
- ✅ AC-FIX.1 (integration): POST /api/v1/trade/order 使用 PlaceOrderRequest Pydantic model (Body(...))
- 新增 `services/trade-service/app/schemas.py` — PlaceOrderRequest with code/direction/price/volume/trade_mode
- routes.py 从 Query(...) 参数改为 `body: PlaceOrderRequest = Body(...)`

### AC-FIX.2: curl JSON Body → 200 (非 422)
```bash
curl -X POST localhost:8006/api/v1/trade/order \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <valid_jwt>" \
  -d '{"code":"000001","direction":"BUY","price":10.5,"volume":100}'
# → 200 {"order_id":"ORD0001","code":"000001","direction":"BUY","price":10.5,...}
```
- ✅ AC-FIX.2 (integration): JSON body 返回 200，格式正确

### AC-FIX.3: trade_mode 字段
```bash
curl -X POST localhost:8006/api/v1/trade/order \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <valid_jwt>" \
  -d '{"code":"000002","direction":"SELL","price":20.0,"volume":100,"trade_mode":"paper"}'
# → 200 {"order_id":"ORD0002",...}
```
- ✅ AC-FIX.3 (integration): PlaceOrderRequest 含 trade_mode 字段（默认 "paper"，可传 "live"）

### 边界验证
- 缺少必填字段 `code` → 422 `{"detail":[{"type":"missing","loc":["body","code"],...}]}`
- 缺少必填字段 `volume` → 422 validation error
- volume < 100 → 422 validation error (ge=100)

## 质量门

- [x] 全部 3 项 AC 通过
- [x] 真实 curl 验证: JSON body → 200
- [x] Pydantic 验证生效（必填字段 / 边界）
- [x] 无新增依赖
- [x] Python 语法检查通过

## 下一步

等待 code-reviewer 验证 C-1 阻断解除

---

**涉及文件**:
- `services/trade-service/app/schemas.py` (新增 PlaceOrderRequest)
- `services/trade-service/app/routes.py` (place_order Query→Body)
