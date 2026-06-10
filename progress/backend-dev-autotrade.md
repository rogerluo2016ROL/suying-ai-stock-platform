# Backend Dev — 量化自动交易进度报告

> **实现日期**: 2026-06-10
> **关联文档**: [PRD](../docs/prd/) | AC-10.6~10.8 + AC-11.5~11.6
> **状态**: Completed

---

## 状态

- Python 语法检查：3 文件全部通过 (0 errors)
- 实现范围：AC-10.6 ~ AC-10.8 + AC-11.5 ~ AC-11.6 后端全部完成
- 未破坏现有策略服务逻辑（PlanStore 和现有 routes 保持不变）
- 与现有 FastAPI + dataclass + in-memory store 风格一致

---

## Skills

- Python 3.14 + FastAPI
- asyncio 异步循环 (executor loop)
- urllib HTTP client (async wrapper)
- dataclass + threading.Lock pattern
- Pydantic v2 请求校验

---

## 产物

| 文件 | 状态 | 说明 |
|------|------|------|
| `services/strategy-service/app/auto_trading_engine.py` | 新增 | Strategy Engine: StrategyConfig/BuyCondition/SellCondition/PositionRule/RiskRule dataclass + StrategyStore + generate_strategy_from_scheme() + create_custom_strategy() |
| `services/strategy-service/app/auto_trading_executor.py` | 新增 | Strategy Executor: ExecutorManager + ExecutorState + _executor_loop() 异步循环 + 条件评估 + 调用 trade-service/signal-service HTTP API |
| `services/strategy-service/app/routes.py` | 扩展 | 新增 12 个 API 端点：generate-from-scheme、custom、list、CRUD、start/pause/resume/stop、status、log |

---

## AC 证据

### AC-10.6 方案生成策略
- [x] `generate_strategy_from_scheme(scheme_id)` 从 PlanStore 读取已确认方案
- [x] 自动生成 StrategyConfig，包含 buy_conditions / sell_conditions / position_rules / risk_rules
- [x] 买入条件：信号强度 ≥ BUY(60) / Kronos 预测收益 > 8% / 因子共振 ≥ 2
- [x] 卖出条件：信号强度 ≤ SELL(20) / Kronos 转为下跌 / 止损浮亏 ≥ 3% / 止盈浮盈 ≥ 15%
- [x] 风控：最大持仓 5 只 / 日最大亏损 3% 暂停 / 总仓位上限 80%
- [x] POST /api/v1/strategy/generate-from-scheme/{scheme_id} 返回完整策略配置

### AC-10.7 自定义策略
- [x] `create_custom_strategy()` 支持完全自定义条件
- [x] BuyCondition / SellCondition / PositionRule / RiskRule 均可配置
- [x] POST /api/v1/strategy/custom 接收 CustomStrategyRequest body
- [x] 支持自定义检查间隔 (check_interval_sec)、交易模式 (trade_mode)、初始资金 (capital)

### AC-10.8 策略 CRUD
- [x] GET /api/v1/strategy/list — 策略列表
- [x] GET /api/v1/strategy/{id} — 策略详情
- [x] PUT /api/v1/strategy/{id} — 编辑策略（支持部分更新）
- [x] DELETE /api/v1/strategy/{id} — 删除策略（自动停止执行器）
- [x] 删除前自动检查并停止运行中的执行器

### AC-11.5 启动执行
- [x] POST /api/v1/strategy/{id}/start 启动异步执行循环
- [x] `run_strategy(strategy_id, mode="paper"|"live")` 返回 ExecutorState
- [x] ExecutorManager 单例管理所有执行器生命周期
- [x] 执行循环：检查条件 → 调用 trade-service 下单 → 等待间隔 → 重复

### AC-11.6 执行控制
- [x] POST /api/v1/strategy/{id}/pause — 暂停（保存状态，使用 asyncio.Event）
- [x] POST /api/v1/strategy/{id}/resume — 恢复
- [x] POST /api/v1/strategy/{id}/stop — 终止（设置 stop_event）
- [x] GET /api/v1/strategy/{id}/status — 执行状态（含 checks_completed/orders_placed/errors）
- [x] GET /api/v1/strategy/{id}/log — 执行日志（支持 level 过滤和 limit 分页）
- [x] 日亏损超限自动暂停策略执行

---

## 质量门

- [x] Python 语法检查零错误 (ast.parse 通过)
- [x] 与现有代码风格一致 (FastAPI + dataclass + threading.Lock + in-memory store)
- [x] 不修改现有模拟交易逻辑 (PaperTradingEngine 不变)
- [x] 不修改现有 PlanStore 和 /plans 路由
- [x] 所有新增文件放在 services/strategy-service/app/ 下
- [x] 路由前缀正确避免冲突（静态路径先于参数化路径注册）
- [x] HTTP 错误响应格式对齐 (HTTPException + detail)
- [ ] 单元测试 (未在本阶段实现)
- [ ] 集成测试 (需 trade-service + signal-service 联调)

---

## 下一步

1. 启动 trade-service (8006) + signal-service (8004) + strategy-service (8003) 联调
2. 通过 POST /custom 创建策略 → POST /{id}/start 验证自动下单
3. 验证日亏损自动暂停逻辑
4. 编写 Unit 测试 (auto_trading_engine / auto_trading_executor)
5. frontend-dev 联调：AutoTrade.tsx 对接新增 API
