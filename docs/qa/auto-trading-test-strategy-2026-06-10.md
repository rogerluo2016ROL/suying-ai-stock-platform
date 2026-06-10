# QA Report -- 量化自动交易 -- E2E + UAT 测试策略

- **Date**: 2026-06-10
- **Stage**: Strategy（E2E + UAT 测试策略框架，非执行报告）
- **Tester**: qa-engineer
- **Branch**: HEAD（当前实现已合入 main）
- **Environment**: local docker-compose（PostgreSQL + strategy-service :8003 + signal-service :8004 + trade-service :8006 + React frontend :5173）
- **PRD**: Kronos/docs/投资管理平台_PRD_产品需求文档.md SS3.10 AC-10.6~10.8 + SS3.11 AC-11.5~11.6
- **Codebase Reviewed**:
  - Backend: `services/strategy-service/app/auto_trading_engine.py` (StrategyConfig + Store + Generator)
  - Backend: `services/strategy-service/app/auto_trading_executor.py` (ExecutorManager + async loop + circuit breaker)
  - Backend: `services/strategy-service/app/routes.py` (REST API: plans + strategies + execution control)
  - Backend: `services/strategy-service/app/plan_store.py` (Plan data model + in-memory store)
  - Frontend: `frontend/src/pages/AutoTrade.tsx` (策略列表 + 创建/编辑 + 详情抽屉 + 操作控制)
  - Frontend: `frontend/src/pages/Strategy.tsx` (方案管理 + 确认 + 生成策略)
- **Mock Dependencies**: signal-service / trade-service 使用 Mock 响应（不依赖真实行情和券商）

---

## Summary

> 本文件为**量化自动交易 E2E + UAT 测试策略框架**，基于实际已实现代码编写。覆盖从方案确认 → 策略生成 → 自动执行 → 手动干预 → 日志审计的完整闭环。

- **Total E2E Scenarios**: 14
- **Total UAT Scenarios**: 7
- **AC Coverage**: AC-10.6, AC-10.7, AC-10.8, AC-11.5, AC-11.6（全部 5 条验收条件）
- **Status**: 等待 code-review 通过

---

## AC 覆盖矩阵

| AC | 描述 | E2E 场景 | UAT 场景 |
|----|------|----------|----------|
| AC-10.6 | 量化自动模拟交易：从确认方案自动生成策略 → 自动执行买卖 | E2E-1, E2E-9 | UAT-1, UAT-5 |
| AC-10.7 | 量化策略执行状态实时可见（当前持仓、下次调仓时间、策略日志） | E2E-7, E2E-12 | UAT-1, UAT-4 |
| AC-10.8 | 用户可手动干预（暂停/恢复/终止量化策略） | E2E-3, E2E-4, E2E-5 | UAT-2 |
| AC-11.5 | 量化实盘交易：从确认方案自动生成量化策略 → 自动执行（全自动/半自动可选） | E2E-11 | UAT-1, UAT-3 |
| AC-11.6 | 用户可自定义量化交易策略：配置买入条件/卖出条件/仓位规则/风控规则 | E2E-2, E2E-10 | UAT-1, UAT-6 |

---

## Pre-conditions Checked

> 执行测试前必须全部勾选。

- [ ] 单元测试 + lint + typecheck 全绿
- [ ] code-reviewer 报告已存在且 verdict != Block
- [ ] PRD SS3.10 + SS3.11 可访问
- [ ] 测试数据库已启动（`docker compose up -d`）
- [ ] strategy-service 已启动（FastAPI on localhost:8003）
- [ ] signal-service Mock 已启动（localhost:8004，返回模拟信号数据）
- [ ] trade-service Mock 已启动（localhost:8006，返回模拟账户/持仓/下单数据）
- [ ] 前端服务已启动（React on localhost:5173）
- [ ] 测试用户已登录（`test_admin` / `test_user_a`）
- [ ] chrome-devtools-mcp 可用于浏览器截图

---

## 测试环境准备

### 1. Mock Signal Service 预设响应

```
GET /api/v1/signal/analyze/{code}
  → 返回模拟信号：
    {
      "code": "000001",
      "signal": {"score": 85, "level": "BUY"},
      "components": {
        "kronos_confidence": {"score": 72, "trend": "up"},
        "factor_resonance": {"score": 3}
      },
      "price": 13.50,
      "kronos_trend": 72
    }
```

### 2. Mock Trade Service 预设响应

```
GET /api/v1/trade/positions?trade_mode=paper
  → {"positions": []}  // 初始空仓

GET /api/v1/trade/account?trade_mode=paper
  → {"total_capital": 1000000, "available": 1000000, "daily_pnl": 0}

POST /api/v1/trade/order?code=...&direction=BUY&price=...&volume=...
  → {"order_id": "ORD-<random>", "status": "filled", "message": "下单成功"}
```

### 3. 测试方案 Seed Data

```
POST /api/v1/strategy/plans?name=测试方案A&model_name=all&capital=1000000&max_positions=5&single_max_pct=0.2
  → {"plan": {"id": "PLAN-XXXXXXXX", ...}}

POST /api/v1/strategy/plans/{plan_id}/picks
  body: [
    {"code": "000001", "name": "平安银行", "price": 13.50, "score": 88, "grade": "A", "entry_price": 13.00},
    {"code": "600519", "name": "贵州茅台", "price": 1680.00, "score": 92, "grade": "S", "entry_price": 1650.00},
    {"code": "000858", "name": "五粮液", "price": 148.00, "score": 85, "grade": "A", "entry_price": 145.00}
  ]

POST /api/v1/strategy/plans/{plan_id}/confirm
```

---

## E2E 测试场景

### E2E-1: 从方案生成策略 → 策略列表可见

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6 |
| **优先级** | P0 |
| **前置** | 已有一个 confirmed 状态的方案（PLAN-XXXXXXXX），包含 3 只标的 |
| **步骤** | |
| | 1. 浏览器访问 `/strategy` 方案管理页面 |
| | 2. 找到 confirmed 状态的方案，点击"量化策略"按钮 |
| | 3. 观察页面跳转到 `/auto-trade` |
| | 4. 在策略列表中确认新策略出现 |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/generate-from-scheme/{plan_id}` 返回 200，`strategy.status === "draft"` |
| | - [ ] 返回的 strategy 包含 `source_type: "scheme"`，`source_scheme_id` 正确 |
| | - [ ] buy_conditions 包含 3 条默认条件（signal≥60, kronos_return>8%, factor_resonance≥2） |
| | - [ ] sell_conditions 包含 4 条默认条件（signal≤20, kronos bearish, stop_loss≥3%, take_profit≥15%） |
| | - [ ] position_rules 包含 max_positions=5, single_max_pct=0.20, total_position_cap_pct=0.80 |
| | - [ ] risk_rules 包含 daily_max_loss_pct=0.03 |
| | - [ ] 策略名称自动生成为 `自动策略-测试方案A` |
| | - [ ] `GET /api/v1/strategy/list` 返回的 strategies 数组中包含新策略 |
| | - [ ] 前端策略列表中可见新策略行，状态为 `draft` |

---

### E2E-2: 编辑策略条件（买入/卖出/仓位/风控）

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.6 |
| **优先级** | P0 |
| **前置** | 策略列表中已有一个 draft 状态的策略（STR-XXXXXXXX） |
| **步骤** | |
| | 1. 在 `/auto-trade` 策略列表中点击编辑按钮 |
| | 2. 编辑抽屉打开，验证原有数据已回填 |
| | 3. 修改策略名称为 `均线金叉策略 v2` |
| | 4. 修改买入条件：signal_strength >= 70 |
| | 5. 修改卖出条件：stop_loss >= 5% |
| | 6. 修改仓位规则：max_positions=3, single_max_pct=0.15 |
| | 7. 修改风控规则：daily_max_loss_pct=0.05 |
| | 8. 切换执行模式为 `full_auto` |
| | 9. 点击保存 |
| **验证点** | |
| | - [ ] `PUT /api/v1/strategy/{strategy_id}` 返回 200，message="策略已更新" |
| | - [ ] `GET /api/v1/strategy/{strategy_id}` 返回的 name 为 `均线金叉策略 v2` |
| | - [ ] buy_conditions[0].threshold === 70 |
| | - [ ] sell_conditions 中 stop_loss 的 threshold === 5.0 |
| | - [ ] position_rules.max_positions === 3, single_max_pct === 0.15 |
| | - [ ] risk_rules.daily_max_loss_pct === 0.05 |
| | - [ ] trade_mode === "paper"（未修改时保持原值） |
| | - [ ] 前端显示"策略已更新"成功提示 |

---

### E2E-3: 启动策略 → 状态变为 active

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P0 |
| **前置** | 策略列表中有一个 draft 或 paused 状态的策略，有 picks 数据 |
| **步骤** | |
| | 1. 在策略列表中点击"启动"按钮 |
| | 2. 观察策略状态变化 |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/{strategy_id}/start?mode=paper` 返回 200 |
| | - [ ] 返回 status="running"，包含 started_at 时间戳 |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/status` 返回 executor_running=true, status="running" |
| | - [ ] 策略 store 中 status 更新为 "active" |
| | - [ ] 前端策略列表状态 Tag 变为 🟢 运行中 |
| | - [ ] 执行器日志第一条为 "策略执行器已启动 (mode=paper)" |
| | - [ ] 5 分钟内至少执行 1 轮检查（checks_completed >= 1） |

---

### E2E-4: 暂停策略 → 状态变为 paused

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P0 |
| **前置** | 策略正在运行中（status=running） |
| **步骤** | |
| | 1. 在运行中的策略行点击"暂停"按钮（⏸） |
| | 2. 观察策略状态变化 |
| | 3. 等待 1 分钟，确认不再有新日志产生 |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/{strategy_id}/pause` 返回 200，status="paused" |
| | - [ ] 执行器日志新增 "策略执行已暂停" |
| | - [ ] 策略 store 中 status 更新为 "paused" |
| | - [ ] 前端状态变为 🟡 暂停 |
| | - [ ] 暂停期间不再执行新检查（checks_completed 不再增加） |
| | - [ ] 暂停期间不产生新的 BUY/SELL 日志 |

---

### E2E-5: 恢复策略 → 继续执行

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P0 |
| **前置** | 策略处于 paused 状态 |
| **步骤** | |
| | 1. 在暂停的策略行点击"恢复"按钮（▶） |
| | 2. 等待检查间隔过后查看日志 |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/{strategy_id}/resume` 返回 200，status="running" |
| | - [ ] 执行器日志新增 "策略执行已恢复" |
| | - [ ] 策略 store 中 status 更新为 "active" |
| | - [ ] 前端状态变回 🟢 运行中 |
| | - [ ] 恢复后继续产生新检查日志（checks_completed 递增） |
| | - [ ] 恢复后 check_interval 正确重置（不是立即触发而是按间隔执行） |

---

### E2E-6: 终止策略 → 状态变为 stopped

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P0 |
| **前置** | 策略处于 running 或 paused 状态 |
| **步骤** | |
| | 1. 点击策略行的"终止"按钮（⏹） |
| | 2. 在 Popconfirm 中确认 |
| | 3. 观察状态变化 |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/{strategy_id}/stop` 返回 200 |
| | - [ ] 返回 stopped_at 时间戳 |
| | - [ ] 执行器日志新增 "策略执行已终止" |
| | - [ ] 策略 store 中 status 更新为 "stopped" |
| | - [ ] 前端状态变为 🔴 已终止 |
| | - [ ] 终止后不再产生新日志（checks_completed 停止增长） |
| | - [ ] 终止后重新启动可以恢复执行（状态变回 running） |

---

### E2E-7: 策略执行日志可查询

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.7 |
| **优先级** | P1 |
| **前置** | 策略已启动运行至少 2 轮检查（产生多条日志） |
| **步骤** | |
| | 1. 点击策略行的"详情"按钮打开详情抽屉 |
| | 2. 查看"策略日志"区域的 Timeline |
| | 3. 刷新页面后重新查看 |
| | 4. 通过 API 按 level 过滤日志 |
| **验证点** | |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/log` 返回 200 |
| | - [ ] 返回 total_logs >= 2（至少有启动日志 + 检查日志） |
| | - [ ] 启动日志 level="INFO", message 包含 "策略执行器已启动" |
| | - [ ] 检查日志 level="INFO", message 包含 "开始执行检查" 和 "检查完成" |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/log?level=INFO` 只返回 INFO 级别日志 |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/log?level=ERROR` 返回空或只有 ERROR 级别 |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/log?limit=10` 最多返回 10 条 |
| | - [ ] 前端 Timeline 正确展示日志时间线，含图标和详情 |
| | - [ ] 日志按时间倒序排列 |
| | - [ ] 日志上限 1000 条触发截断（保留最近 500 条） |

---

### E2E-8: 策略执行时调用 trade-service 下单

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6 |
| **优先级** | P0 |
| **前置** | Mock signal-service 返回信号强度 >= 60（满足买入条件）；Mock trade-service 返回空持仓 |
| **步骤** | |
| | 1. 确保 Mock signal-service 对 picks 中每只股票返回 score >= 85 |
| | 2. 启动策略执行 |
| | 3. 等待检查周期（默认 5 分钟，测试时可调短 check_interval_sec=30） |
| | 4. 查看执行日志和 trade-service 订单记录 |
| **验证点** | |
| | - [ ] 执行日志中出现 level="BUY" 的条目，包含 "触发买入条件" |
| | - [ ] BUY 日志 details 包含 code, reason, price, volume |
| | - [ ] `POST /api/v1/trade/order` 被正确调用，参数包含 code/direction=BUY/price/volume |
| | - [ ] 买入 volume 计算正确：`int((capital * position_pct) / entry_price)` 且为 100 的整数倍 |
| | - [ ] 买入后 orders_placed 计数正确递增 |
| | - [ ] 单票买入不超过 single_max_pct |
| | - [ ] 总持仓数不超过 max_positions（达到上限后不再买入新标的） |
| | - [ ] 已持仓标的不重复买入 |
| | - [ ] 价格无效时（entry_price <= 0）记录 WARN 日志并跳过 |
| | - [ ] 计算股数 < 100 时记录 WARN 并跳过 |

---

### E2E-9: 卖出条件触发 → 自动下单卖出

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6 |
| **优先级** | P0 |
| **前置** | Mock trade-service 返回已有持仓（如 000001），Mock signal-service 返回信号强度 <= 20（满足卖出条件） |
| **步骤** | |
| | 1. 设置 Mock trade-service positions 包含 `000001` 持仓 |
| | 2. 设置 Mock signal-service 对 `000001` 返回 score <= 20（触发 SELL） |
| | 3. 启动策略执行 |
| | 4. 等待检查周期 |
| **验证点** | |
| | - [ ] 执行日志中出现 level="SELL" 的条目，包含 "触发卖出条件" |
| | - [ ] SELL 日志 details 包含 code, reason, pnl_pct |
| | - [ ] `POST /api/v1/trade/order` 被调用，direction=SELL, volume=持仓量 |
| | - [ ] 卖出理由正确（如 "信号强度 ≤ SELL" 或 "止损: 浮亏 ≥ 3%"） |
| | - [ ] 止盈条件（浮盈 >= 15%）触发时正确卖出 |
| | - [ ] 止损条件（浮亏 >= 3%）触发时正确卖出 |
| | - [ ] Kronos trend bearish（kronos_trend < 50）触发时正确卖出 |
| | - [ ] 卖出后 orders_placed 计数递增 |

---

### E2E-10: 自定义策略创建

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.6 |
| **优先级** | P1 |
| **前置** | 无 |
| **步骤** | |
| | 1. 在 `/auto-trade` 页面点击"新建策略" |
| | 2. 填写策略名称 "我的自定义策略" |
| | 3. 选择执行模式 "半自动" |
| | 4. 设置买入条件：MA >= 20, VOL >= 1000000 |
| | 5. 设置卖出条件：MA <= 10 |
| | 6. 设置风控规则：max_daily_loss = 2% |
| | 7. 点击"创建策略" |
| **验证点** | |
| | - [ ] `POST /api/v1/strategy/custom` 返回 200 |
| | - [ ] 返回 strategy.source_type === "custom" |
| | - [ ] 返回 strategy.name === "我的自定义策略" |
| | - [ ] 返回 strategy.trade_mode === "paper"（默认） |
| | - [ ] buy_conditions 包含 2 条自定义条件 |
| | - [ ] sell_conditions 包含 1 条自定义条件 |
| | - [ ] risk_rules.max_daily_loss === 2% |
| | - [ ] 不传 buy_conditions 时使用默认条件（3 条） |
| | - [ ] 不传 sell_conditions 时使用默认条件（4 条） |
| | - [ ] 不传 position_rules 时使用默认仓位规则（max_positions=5, single_max_pct=0.20） |
| | - [ ] 前端显示"策略已创建"成功提示，列表刷新可见 |

---

### E2E-11: 全自动 vs 半自动模式切换

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.5 |
| **优先级** | P1 |
| **前置** | 已有策略 |
| **步骤** | |
| | 1. 编辑已有策略 |
| | 2. 将执行模式从"全自动"切换为"半自动" |
| | 3. 保存 |
| | 4. 再次编辑，切换回"全自动" |
| | 5. 保存并启动策略 |
| **验证点** | |
| | - [ ] 创建策略时可选择 full_auto 或 semi_auto |
| | - [ ] 编辑时可切换模式并正确保存 |
| | - [ ] 前端列表显示正确的模式 Tag（🟢全自动 / 🟠半自动） |
| | - [ ] 详情抽屉显示正确的模式描述 |
| | - [ ] 启动时 `POST /api/v1/strategy/{id}/start?mode=live` 可覆盖为实盘模式 |
| | - [ ] 半自动模式：后端执行器仍正常检查条件并记录日志（信号提醒由前端展示） |
| | - [ ] 全自动模式：后端执行器自动下单 |

---

### E2E-12: 策略执行状态实时可见

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.7 |
| **优先级** | P1 |
| **前置** | 策略正在运行 |
| **步骤** | |
| | 1. 查看策略列表中的状态列 |
| | 2. 点击"详情"打开详情抽屉 |
| | 3. 查看 KPI 卡片（累计盈亏/今日收益/下次调仓） |
| | 4. 查看当前持仓表格 |
| | 5. 等待 30 秒后刷新页面（或点击刷新按钮） |
| **验证点** | |
| | - [ ] `GET /api/v1/strategy/{strategy_id}/status` 返回 executor_running=true |
| | - [ ] status 返回 last_check_at, next_check_at, checks_completed, orders_placed, errors |
| | - [ ] 前端"下次调仓"倒计时准确（每秒更新） |
| | - [ ] 当前持仓表格正确展示 code/name/volume/cost/price/pnl |
| | - [ ] 空持仓时显示 Empty 占位 |
| | - [ ] 盈亏值正数显示绿色，负数显示红色 |
| | - [ ] 详情抽屉中可执行暂停/恢复/终止操作 |

---

### E2E-13: 策略失控检测（日亏损熔断）

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.8（熔断机制复用于自动交易） |
| **优先级** | P0 |
| **前置** | 策略正在运行，Mock trade-service 返回 daily_pnl = -50000（亏损 5%），risk_rules.daily_max_loss_pct = 0.03 |
| **步骤** | |
| | 1. 设置 Mock trade-service account.daily_pnl = -50000 |
| | 2. 策略 capital = 1000000（亏损 5% > 阈值 3%） |
| | 3. 等待策略执行下一轮检查 |
| | 4. 查看日志和策略状态 |
| **验证点** | |
| | - [ ] 执行日志中出现 WARN 级别 "日亏损 X.XX% 超过阈值 X.XX%，跳过本次交易" |
| | - [ ] 执行日志随后出现 WARN "日亏损超限 — 自动暂停策略执行" |
| | - [ ] 策略自动变为 paused 状态 |
| | - [ ] 策略 store 中 status 变为 "paused" |
| | - [ ] 前端显示 🟡 暂停状态 |
| | - [ ] 亏损在阈值内时（如 daily_pnl = -20000，亏损 2% < 3%）正常执行不中断 |
| | - [ ] 日盈利时（daily_pnl >= 0）正常执行 |

---

### E2E-14: 删除策略

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P1 |
| **前置** | 策略列表中存在策略 |
| **步骤** | |
| | 1. 测试删除 stopped 状态的策略 |
| | 2. 测试删除 running 状态的策略（应自动 stop 再删除） |
| | 3. 测试删除不存在的策略 ID |
| **验证点** | |
| | - [ ] `DELETE /api/v1/strategy/{strategy_id}` 返回 200，status="deleted" |
| | - [ ] 删除 stopped 策略：直接删除成功 |
| | - [ ] 删除 running 策略：先自动调用 stop() 终止执行器，再删除策略 |
| | - [ ] 删除 paused 策略：先自动调用 stop() 终止执行器，再删除策略 |
| | - [ ] `GET /api/v1/strategy/list` 不再包含已删除策略 |
| | - [ ] 删除不存在的策略返回 404 |
| | - [ ] 前端列表刷新后已删除策略消失 |

---

## UAT 测试场景

### UAT-1: 端到端完整流程 — 确认方案 → 生成策略 → 启动 → 自动下单 → 查看日志

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6, AC-10.7, AC-11.5, AC-11.6 |
| **优先级** | P0 |
| **角色** | 管理员/普通用户 |
| **前置** | 所有服务就绪，Mock signal-service 对 picks 返回高分信号 |
| **用户故事** | 作为分析师，我已从选股结果中确认了一个方案，希望一键生成量化策略并自动执行模拟交易，实时查看执行状态和持仓变化。 |
| **操作流程** | |
| | 1. 登录系统，进入"方案管理"页面 (`/strategy`) |
| | 2. 确认已有方案（或创建新方案 → 添加标的 → 确认） |
| | 3. 点击"量化策略"按钮生成策略 |
| | 4. 自动跳转到"量化交易"页面 (`/auto-trade`)，看到新策略 |
| | 5. 点击"启动"按钮，策略状态变为 🟢 运行中 |
| | 6. 等待检查周期后，点击"详情"查看策略执行日志 |
| | 7. 确认日志中出现 BUY 级别条目（自动下单） |
| | 8. 查看持仓列表确认已买入标的 |
| **关键证据** | |
| | - [ ] 方案 → 策略生成成功，条件/规则自动填充 |
| | - [ ] 策略启动后自动执行检查 |
| | - [ ] 满足买入条件时自动下单 |
| | - [ ] 日志完整记录每次检查、每笔订单 |
| | - [ ] 持仓实时更新 |
| | - [ ] 整个过程无需手动干预（全自动模式） |

---

### UAT-2: 手动干预 — 暂停/恢复/终止即时生效

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.8 |
| **优先级** | P0 |
| **角色** | 管理员 |
| **前置** | 策略正在运行中 |
| **用户故事** | 作为管理员，当市场出现异常波动时，我需要立即暂停量化策略，待市场稳定后恢复执行；如果策略表现不佳，我需要彻底终止它。 |
| **操作流程** | |
| | 1. 在策略列表中看到正在运行的策略 |
| | 2. 点击"暂停"按钮 → 策略立即变为 🟡 暂停 |
| | 3. 等待 1 分钟，确认没有新的交易日志产生 |
| | 4. 点击"恢复"按钮 → 策略恢复为 🟢 运行中 |
| | 5. 确认恢复后继续产生新的检查日志 |
| | 6. 点击"终止"按钮 → 确认弹窗 → 策略变为 🔴 已终止 |
| | 7. 确认终止后不再产生任何日志 |
| **关键证据** | |
| | - [ ] 暂停操作立即生效（< 1 秒），后台执行器暂停条件检查 |
| | - [ ] 暂停期间无新交易 |
| | - [ ] 恢复后继续按周期执行 |
| | - [ ] 终止后无法恢复（需重新启动） |
| | - [ ] 所有操作在日志中有完整记录 |
| | - [ ] 操作后前端状态立即刷新，无需手动刷新页面 |

---

### UAT-3: 半自动模式 — 信号提醒 + 手动确认流程

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.5 |
| **优先级** | P1 |
| **角色** | 普通用户 |
| **前置** | 策略设置为半自动模式（semi_auto）并已启动 |
| **用户故事** | 作为用户，我选择半自动模式，希望系统在检测到交易信号时提醒我，由我手动确认后再执行下单，而不是完全自动执行。 |
| **操作流程** | |
| | 1. 创建策略时选择"半自动 (信号提醒+手动确认)" |
| | 2. 启动策略 |
| | 3. 系统检测到买入信号后，在前端显示提醒 |
| | 4. 用户查看信号详情后决定是否下单 |
| **关键证据** | |
| | - [ ] 策略创建时可正确选择半自动模式 |
| | - [ ] 半自动模式下后端执行器仍正常检查条件 |
| | - [ ] 日志中记录信号触发信息（但不自动下单） |
| | - [ ] 前端详情抽屉中显示执行模式为"半自动(信号提醒+手动确认)" |
| | - [ ] 用户可通过 Trade 页面手动确认下单 |
| | - [ ] 半自动与全自动切换后即时生效 |

---

### UAT-4: 多策略并行不冲突

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.7, AC-10.8 |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 已创建 3 个策略（针对不同方案或自定义），各有独立 picks |
| **用户故事** | 作为管理员，我需要同时运行多个量化策略（如龙头战法策略 + 网格策略 + 趋势跟踪策略），它们各自独立执行，互不干扰。 |
| **操作流程** | |
| | 1. 创建策略 A（picks: 000001, 600519），启动 |
| | 2. 创建策略 B（picks: 000858, 002415），启动 |
| | 3. 创建策略 C（picks: 300750），启动 |
| | 4. 查看每个策略各自的状态、日志、持仓 |
| | 5. 暂停策略 A，确认策略 B 和 C 仍在运行 |
| | 6. 终止策略 B，确认策略 C 仍在运行 |
| **关键证据** | |
| | - [ ] 3 个策略可同时运行 |
| | - [ ] 每个策略有独立的 ExecutorState（checks_completed, orders_placed, errors） |
| | - [ ] 每个策略有独立的日志流 |
| | - [ ] 一个策略的状态变更不影响其他策略 |
| | - [ ] 删除一个策略不影响其他策略 |
| | - [ ] `GET /api/v1/strategy/list` 返回所有策略，可区分各自状态 |

---

### UAT-5: 策略盈亏统计准确性

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6（引申：策略执行效果可衡量） |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 策略已执行多轮，有买入和卖出记录 |
| **用户故事** | 作为用户，我需要查看量化策略的累计盈亏和今日收益，以评估策略表现并决定是否继续执行。 |
| **操作流程** | |
| | 1. 查看策略列表中的累计盈亏和今日收益列 |
| | 2. 点击详情查看 KPI 卡片 |
| | 3. 将盈亏数据与 trade-service 的账户/持仓数据对比 |
| **关键证据** | |
| | - [ ] 策略列表中累计盈亏（pnl, pnl_pct）显示正确 |
| | - [ ] 今日收益（today_return, today_return_pct）显示正确 |
| | - [ ] 正收益显示绿色 + 前缀 |
| | - [ ] 负收益显示红色 + 前缀 |
| | - [ ] 详情抽屉中 KPI 卡片数据与列表一致 |
| | - [ ] 数据来源于 trade-service 真实账户数据 |

---

### UAT-6: 策略删除后相关数据清理

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-11.6（策略生命周期管理） |
| **优先级** | P1 |
| **角色** | 管理员 |
| **前置** | 存在一个已停止的策略（含执行日志） |
| **用户故事** | 作为用户，当我不再需要某个量化策略时，删除策略应同时清理相关执行器状态，避免残留数据污染。 |
| **操作流程** | |
| | 1. 在策略列表中删除一个 stopped 策略 |
| | 2. 确认删除 |
| | 3. 刷新策略列表 |
| | 4. 尝试通过 API 直接查询已删除策略的状态 |
| **关键证据** | |
| | - [ ] `DELETE /api/v1/strategy/{id}` 成功返回 |
| | - [ ] `GET /api/v1/strategy/list` 不再包含已删除策略 |
| | - [ ] `GET /api/v1/strategy/{id}` 返回 404 |
| | - [ ] `GET /api/v1/strategy/{id}/status` 返回 404 |
| | - [ ] `GET /api/v1/strategy/{id}/log` 返回 404 |
| | - [ ] 删除 running/paused 策略时自动先调用 stop() 终止执行器 |
| | - [ ] 执行器管理器正确清理已删除策略的执行器状态 |

---

### UAT-7: 方案未确认时不能生成策略

| 字段 | 值 |
|------|-----|
| **AC 覆盖** | AC-10.6（隐含：只能从 confirmed 方案生成策略） |
| **优先级** | P1 |
| **角色** | 普通用户 |
| **前置** | 存在一个 draft 状态的方案 |
| **用户故事** | 作为用户，我需要先确认方案（经过预测和回测验证）才能生成量化策略，系统应阻止从草稿方案直接生成策略。 |
| **操作流程** | |
| | 1. 尝试对 draft 状态的方案调用生成策略 API |
| | 2. 确认方案后再生成策略 |
| | 3. 对 archived 状态的方案尝试生成策略 |
| **关键证据** | |
| | - [ ] `POST /api/v1/strategy/generate-from-scheme/{draft_plan_id}` 返回 400 |
| | - [ ] 错误信息为 "方案状态必须为 confirmed 或 active，当前: draft。请先确认方案。" |
| | - [ ] 确认方案后生成策略成功（返回 200） |
| | - [ ] 对不存在的 plan_id 返回 "方案不存在" |
| | - [ ] 前端对 draft 方案不显示"量化策略"按钮 |
| | - [ ] 前端仅对 confirmed 方案显示"量化策略"按钮 |

---

## 附录 A: API 端点速查

| Method | Path | 用途 | 相关 AC |
|--------|------|------|---------|
| POST | `/api/v1/strategy/plans` | 创建方案 | - |
| GET | `/api/v1/strategy/plans` | 方案列表 | - |
| POST | `/api/v1/strategy/plans/{id}/confirm` | 确认方案 | - |
| POST | `/api/v1/strategy/generate-from-scheme/{id}` | 从方案生成策略 | AC-10.6 |
| POST | `/api/v1/strategy/custom` | 创建自定义策略 | AC-11.6 |
| GET | `/api/v1/strategy/list` | 策略列表 | AC-10.7 |
| GET | `/api/v1/strategy/{id}` | 策略详情 | AC-10.7 |
| PUT | `/api/v1/strategy/{id}` | 编辑策略 | AC-11.6 |
| DELETE | `/api/v1/strategy/{id}` | 删除策略 | AC-10.8 |
| POST | `/api/v1/strategy/{id}/start` | 启动执行 | AC-11.5 |
| POST | `/api/v1/strategy/{id}/pause` | 暂停执行 | AC-10.8 |
| POST | `/api/v1/strategy/{id}/resume` | 恢复执行 | AC-10.8 |
| POST | `/api/v1/strategy/{id}/stop` | 终止执行 | AC-10.8 |
| GET | `/api/v1/strategy/{id}/status` | 执行状态 | AC-10.7 |
| GET | `/api/v1/strategy/{id}/log` | 执行日志 | AC-10.7 |

## 附录 B: 数据模型速查

**StrategyConfig 状态机**:
```
draft → (start) → active/running → (pause) → paused
                                  → (stop)  → stopped
                paused → (resume) → running
                stopped → (start)  → running (重新启动)
```

**ExecutorState 状态机**:
```
idle → (start) → running → (pause) → paused
                         → (stop)  → stopped
       running ← (resume) ← paused
       (自动熔断: daily_loss >= threshold) → paused
```

**Plan 状态流**:
```
draft → (confirm) → confirmed → (generate strategy) → active
                                → (archive) → archived
```

## 附录 C: 已知限制与测试注意事项

1. **In-memory store**: PlanStore 和 StrategyStore 均为内存存储，服务重启后数据丢失。E2E 测试需在同一 session 内完成。
2. **Mock 依赖**: signal-service 和 trade-service 使用 Mock，实际条件评估依赖 Mock 返回的数据格式。
3. **Async loop 生命周期**: 执行器 loop 在 FastAPI 的 event loop 中运行，需确保测试期间 loop 不退出。
4. **日志截断**: 执行日志上限 1000 条，超过后保留最近 500 条，测试时需注意。
5. **check_interval**: 默认 300 秒（5 分钟），测试时可设置 check_interval_sec=30 以加速。
6. **资金/价格计算**: 买入量按 `int((capital * position_pct) / entry_price)` 计算且向下取整到 100 的倍数，测试需验证边界（如股数 < 100 时跳过）。
