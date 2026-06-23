# 测试计划 — PaperTradingEngine（模拟盘记账）

> 来源：2026-06-23 codegraph 调查发现 `trade-service` 下单/记账路径**无正确性测试**（`tests/` 仅有 `test_circuit_breaker_concurrency.py`）。实盘 Xtquant 当前未接（走 `_place_order_stub`），故**测试重心 = 模拟盘 `engine.py` 的纯计算记账逻辑**。
> 被测文件：`services/trade-service/app/engine.py`（135 行）
> 适用角色：`backend-dev`（涉及交易代码 → 按 CLAUDE.md 走 **Plan Mode + tech-lead review**）

---

## 1. 读代码挖出的可疑点 / 疑似 bug（先测，红测试会证实）

> 下表为人工审查 `engine.py` 推断的可疑点，**需用测试证实**。判定以测试结果为准。

| # | 严重度 | 位置 | 触发条件 | 后果 |
|---|---|---|---|---|
| **B1** | 🔴 P0 | `place_order` L78-83 + `_update_position_sell` L111 | 卖出**不存在**的持仓（卖空） | `available += trade_amount` 已执行（L82），但 `_update_position_sell` 因 `code not in positions` 静默跳过 → **available / total_capital 凭空虚增**，无持仓扣减、无 pnl |
| **B2** | 🔴 P0 | `_update_position_sell` L113,116 | 卖出量 **超过** 持仓量（如持 100 卖 150） | pnl 按 `min(vol,pos.vol)`=100 算（L113），但 `pos.volume -= volume` 减全量 150（L116）→ volume=-50 后被 del（L117）；`available += 150*price`（L82）→ **超卖部分钱进 available，无对应** |
| **B3** | 🟠 P1 | `place_order` L78,81 | `direction` 非 `BUY`/`SELL`（如 `"HOLD"`、拼写错误） | `else` 兜底当 SELL 处理 → 触发 B1 卖空链路 |
| **B4** | 🟠 P1 | `Position` dataclass L24-31 | 任何路径 | `current_price` / `market_value` / `pnl` / `pnl_pct` **从未被更新**，恒为初始 0 → `get_positions()` 返回死值，前端/API 可能显示 0 浮盈 0 市价 |
| **B5** | 🟡 P2 | `_recalc_account` L121 | 任何持仓 | `market_value = sum(avg_cost * volume)` 用**成本价**非市价 → `total_capital` 不反映浮盈亏（与 B4 同源：缺 current_price 机制） |
| **B6** | 🟡 P2 | `get_orders`/`get_positions`/`get_account` L97-99 | 并发读 | 读方法**不加 `_lock`**，`place_order` 写时并发读可能读到不一致状态 |
| **B7** | 🟡 P2 | 文件 docstring L1 vs `place_order` L72 | 当日买当日卖 | docstring 声称 "T+1 simulation"，实现是 T+0（立即 fill，SELL 不校验是否当日买入）→ A 股 T+1 规则未实现 |

**最严重是 B1/B2/B3：资金凭空产生。** 即便模拟盘，错误的 `available`/`total_capital` 会让回测/模拟结果失真，下游依赖（如策略评估）会被污染。

---

## 2. 测试用例矩阵

> 优先级：P0 = 暴露资金 bug，必须先写（红测试）；P1 = 核心正确性；P2 = 语义/并发/规则。
> 全部为**纯 pytest 单元测试**，无外部依赖（不碰 Xtquant/PG/网络）。

### A. `_update_position_buy`（加仓成本计算，P1）
- **A1** 首次买入 → 新建 Position，`volume`/`avg_cost=price`
- **A2** 加仓 → 加权 `avg_cost = (旧avg*旧vol + price*vol) / 新vol` 正确
- **A3** 连续多次加仓 → `avg_cost` 迭代正确（与手算一致）
- **A4** 加仓后 `pos.volume` 累加正确

### B. `_update_position_sell`（卖出与盈亏，含红测试）
- **B1-t** 清仓卖出（卖=持仓）→ pnl 正确、Position 删除
- **B2-t** 部分卖出 → pnl 按比例、`volume` 递减、Position 保留
- 🔴 **B3-t** 超卖（卖 > 持仓）→ **预期失败**：暴露 B2（volume 变负/超卖钱虚增）。修复后应：拒绝超卖或只卖持仓量
- 🔴 **B4-t** 卖空（无持仓卖出）→ **预期失败**：暴露 B1（available 虚增）。修复后应：拒绝卖空并报错

### C. `place_order` 端到端（P1 + 红测试）
- **C1** 限价 BUY → `available` 减少 `price*vol`、持仓建立、`filled_price=price`
- **C2** 限价 SELL → `available` 增加、持仓减少
- **C3** 市价单（`price=0`）→ `filled_price=50.0`（`_mock_price` 默认值）
- **C4** 大小写归一化：`code="aapl"`/`direction="buy"` → 内部 `"AAPL"`/`"BUY"`
- **C5** `order.id` 自增格式 `ORD0001`/`ORD0002`…
- **C6** `status="filled"`、`filled_at` 非空
- 🔴 **C7** 非法方向（`"HOLD"`）→ **预期失败**：暴露 B3（被当 SELL）。修复后应：拒绝未知方向
- 🔴 **C8** 卖空端到端 → **预期失败**：暴露 B1（`available`/`total_capital` 虚增）
- 🔴 **C9** 超卖端到端 → **预期失败**：暴露 B2

### D. `_recalc_account`（账户汇总，P2）
- **D1** BUY 后 `total_capital = available + market_value` 守恒（无浮盈亏时 = 初始 100 万）
- **D2** 所有金额 `round(..., 2)`
- 🟡 **D3** `market_value` 用 `avg_cost`（确认 B5 行为，决定是否需引入 current_price）
- 🟡 **D4** `get_positions()` 的 `current_price/market_value/pnl/pnl_pct` 恒 0（确认 B4）

### E. 并发（P2，进阶）
- 🟡 **E1** N 线程并发 `place_order` → `order_counter` 无重复、`account` 终态一致（可能暴露 B6 读无锁，但写有锁所以金额应一致）

### F. T+1 业务规则（P2，需产品确认）
- 🟡 **F1** 当日买当日卖 → 当前允许（确认 B7）。**需 product-lead 确认**：模拟盘是否要强制 A 股 T+1

---

## 3. 测试约定（避免坑）

1. **不要用 `get_engine()`**：`engine.py` L132 是模块级 singleton，测试间会共享状态污染。**每个用例 `engine = PaperTradingEngine()` 独立实例**，或用 fixture 每次重建。
2. **资金断言用 `round()` 比较**：`_recalc_account` 对 available/total_capital 做了 `round(2)`，浮点直接 `==` 可能踩坑，用 `pytest.approx` 或 round 后比。
3. **B 类红测试先写、先跑**：让 P0 bug 用失败测试"立案"，再交 backend-dev 修复 → 测试转绿即修复验证。
4. **文件位置**：`services/trade-service/tests/test_engine_accounting.py`（与现有 `test_circuit_breaker_concurrency.py` 同目录）。

---

## 4. 修复优先级建议（交 backend-dev）

1. **先修 B1/B2/B3**（资金凭空产生）→ 在 `place_order` SELL 分支前置校验：持仓存在且 `volume <= pos.volume`，否则拒绝（返回 `status="rejected"` 或抛 `InsufficientPositionError`）。
2. **再修 B4/B5**：决定 `Position.current_price` 来源（`_mock_price` 或外部行情注入），更新 `market_value/pnl/pnl_pct`，`_recalc_account` 改用市价。
3. **B6**：读方法加 `with self._lock`（或返回快照副本）。
4. **B7**：待 product-lead 确认 T+1 需求后再定。

> 修复 + 测试完成后，跑 `cd services/trade-service && pytest tests/ -v`，证据落 `progress/backend-dev.md` 的 **SIT 证据** 段，由 code-reviewer audit。
