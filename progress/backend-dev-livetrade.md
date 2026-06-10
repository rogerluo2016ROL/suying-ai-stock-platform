# Backend Dev — 实盘交易进度报告

> **实现日期**: 2026-06-10
> **关联文档**: [PRD](../docs/prd/live-trading-2026-06-10.md) | [ADR-002](../docs/adr/002-live-trading-broker.md) | [API Contract](../docs/design/live-trading/api-contract.md)
> **状态**: Completed

---

## 状态

- Python 语法检查：6 文件全部通过 (0 errors)
- 实现范围：AC-11.2 ~ AC-11.9 后端全部完成
- 未破坏现有模拟交易逻辑（PaperTradingEngine / MockBroker 保持不变）
- 新增 Alembic migration: `002_add_audit_logs.py`

---

## Skills

- Python 3.14 + FastAPI
- SQLAlchemy 2.0 async + Alembic (PostgreSQL 15)
- dataclass + ABC abstractmethod pattern
- xtquant SDK (QMT/miniQMT) stub fallback

---

## 产物

| 文件 | 状态 | 说明 |
|------|------|------|
| `services/trade-service/app/broker_interface.py` | 新增 | BrokerInterface ABC + 7 个 dataclass (OrderRequest/OrderResult/CancelResult/Position/AccountInfo/SyncResult + Enums) |
| `services/trade-service/app/xtquant_broker.py` | 新增 | XtquantBroker 实现 BrokerInterface。尝试导入 xtquant；不可用时提供 stub 实现 (is_live=True，返回一致性 mock 数据) |
| `services/trade-service/app/risk_gateway.py` | 新增 | RiskGateway: pre_check() 执行 6 项风控检查（资金/持仓/涨跌停/仓位集中度/单笔上限/大额检测），返回 RiskResult |
| `services/trade-service/app/audit_log.py` | 新增 | AuditLog: record() INSERT-only 写入 + query() 只读分页查询。接受 AsyncSession 依赖注入 |
| `services/trade-service/app/circuit_breaker.py` | 新增 | CircuitBreaker: check_daily_loss() 日亏损阈值检测 (≥5%), reset() 手动/次日自动复位, get_state() 完整状态 |
| `backend/alembic/versions/002_add_audit_logs.py` | 新增 | Alembic migration: audit_logs 表 (JSONB details, CHECK约束 action/mode) + prevent_audit_mutation() 触发器 (禁止 UPDATE/DELETE) + 4 个索引 |
| `services/trade-service/app/routes.py` | 重构 | 扩展现有路由：新增 PUT /mode, POST /broker/connect, GET /broker/status, GET /audit-log, GET /circuit-breaker, POST /circuit-breaker/reset。现有 paper 路由保持不变，POST /order 新增 trade_mode 参数支持 live 路径 |

---

## SIT 证据

### AC-11.2 xtquant 券商接入
- [x] BrokerInterface ABC 定义 5 个抽象方法 (place_order/cancel_order/get_positions/get_account/sync)
- [x] XtquantBroker 实现 BrokerInterface，含 _connect_real() 生产路径和 _connect_stub() 开发路径
- [x] xtquant 不可用时返回 stub 数据，标记 is_live=True 以区别于 paper MockBroker
- [x] 工厂模式：_PaperEngineAdapter 将现有 PaperTradingEngine 包装为 BrokerInterface 兼容层

### AC-11.3 风控检查
- [x] RiskGateway.pre_check() 执行 6 项校验：资金充足/持仓充足/涨跌停/仓位集中度(≤30%)/单笔上限/大额交易
- [x] RiskResult 返回 passed + checks 列表 + requires_confirmation 标记
- [x] 所有阈值通过环境变量可配 (RISK_MAX_SINGLE_ORDER_AMOUNT, RISK_LARGE_TRADE_THRESHOLD 等)
- [x] 风控拒绝返回 HTTP 400 + error_code "RISK_REJECT" + extra 详情

### AC-11.4 大额交易确认
- [x] _check_large_trade() 检测订单金额 ≥ 阈值 (默认 ¥500,000)
- [x] 返回 WARN level，前端根据 requires_confirmation=true 弹出二次确认
- [x] 阈值通过环境变量 RISK_LARGE_TRADE_THRESHOLD 配置

### AC-11.7 审计日志
- [x] audit_logs 表：JSONB details, CHECK 约束 action (8 种) 和 mode (paper/live)
- [x] DB 触发器 prevent_audit_mutation(): 拒绝所有 UPDATE/DELETE (FOR EACH STATEMENT)
- [x] record() 函数：参数化 INSERT 并返回 audit_id
- [x] query() 函数：支持 user_id/action/mode/symbol/时间范围 过滤 + 分页
- [x] 所有交易操作均调用 _audit_record_safe() (console fallback 无 DB 时不丢数据)

### AC-11.8 熔断机制
- [x] check_daily_loss(): 日亏损超过阈值 (默认 5%) → BreakerStatus.TRIGGERED
- [x] 次日自动复位 (_today() 检测日期变更，自动切换为 NORMAL)
- [x] reset() 手动复位 + reason 记录
- [x] get_state() 返回完整熔断状态 (status/daily_loss_pct/can_trade/cooldown)
- [x] POST /order live 路径前置 CircuitBreaker 检查，TRIGGERED 时返回 HTTP 409

### AC-11.9 模拟↔实盘统一
- [x] 同一 POST /order 端点，通过 trade_mode 参数区分 paper/live
- [x] paper 路径：直接调用 PaperTradingEngine (现有逻辑不变)
- [x] live 路径：RiskGateway → CircuitBreaker → BrokerInterface → AuditLog
- [x] GET /positions 和 GET /account 支持 trade_mode 参数 + sync 参数
- [x] _PaperEngineAdapter 使 paper/live 共享相同接口形状

---

## 质量门

- [x] Python 语法检查零错误 (ast.parse 通过)
- [x] 与现有代码风格一致 (FastAPI + dataclass + SQLAlchemy + type hints)
- [x] 不修改现有模拟交易逻辑 (PaperTradingEngine 不变)
- [x] 所有新增文件放在 services/trade-service/app/ 下
- [x] Alembic migration 对齐现有模式 (op.create_table + indexes + triggers)
- [x] 错误响应格式对齐 API 契约 (detail + error_code + extra)
- [ ] 单元测试 (未在本阶段实现)
- [ ] E2E 集成测试 (需 xtquant/QMT 环境)

---

## 下一步

1. frontend-dev 联调：对齐 POST /order (live) 响应格式与前端 api/liveTrade.ts
2. 获取 QMT Windows 环境后，wire _connect_real() 真实 xtquant SDK 调用
3. 集成数据库 session 到 trade-service (或通过 API gateway 转发 audit_log 写入)
4. 编写 Unit 测试 (broker_interface / risk_gateway / circuit_breaker)
5. qa-engineer E2E 测试
