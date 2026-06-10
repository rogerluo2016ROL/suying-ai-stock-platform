# 实盘交易 API 契约（草案）

> 状态：草案（2026-06-10）
> 关联 ADR：待建（`docs/adr/002-live-trading-broker.md`）
> 关联 PRD：待建
> 依赖：`services/trade-service/app/` 现有模拟交易 API

---

## 1. 核心设计原则

### 1.1 与模拟交易共享 API 层

实盘与模拟交易共用 `POST /api/v1/trade/order` / `GET /api/v1/trade/orders` 等端点，通过 `trade_mode` 区分目标执行引擎。前端无需感知后端 Broker 实现差异。

```
┌──────────────────────────────────────────────────┐
│                FastAPI Router                     │
│  POST /order  DELETE /order  GET /orders         │
│  GET /positions  GET /account  PUT /mode         │
│  POST /broker/connect  GET /broker/status        │
│  GET /audit-log                                  │
└──────────┬────────────────────┬──────────────────┘
           │                    │
     ┌─────▼──────┐      ┌─────▼──────┐
     │ PaperEngine │      │ LiveEngine │
     │ (MockBroker)│      │(XtquantBroker)│
     └─────────────┘      └─────┬───────┘
                                │ implements
                         ┌──────▼──────┐
                         │BrokerInterface│ (ABC)
                         └─────────────┘
```

### 1.2 实盘独有模块

以下模块仅实盘模式下生效：

| 模块 | 职责 | 模拟盘 |
|---|---|---|
| `RiskGateway` | 下单前风控校验 | 跳过 |
| `CircuitBreaker` | 日亏损阈值自动暂停 | 跳过 |
| `AuditLogger` | append-only 操作日志 | 跳过 |
| `BrokerConnector` | 券商连接生命周期管理 | 跳过 |
| `PositionSync` | 从券商实时同步持仓 | 跳过 |

---

## 2. 数据库 Schema

### 2.1 券商连接配置表 `broker_configs`

```sql
CREATE TABLE IF NOT EXISTS broker_configs (
    id              SERIAL PRIMARY KEY,
    broker_name     TEXT NOT NULL UNIQUE,             -- 'xtquant' | 'qmt' | 'ths'
    account_id      TEXT NOT NULL,                    -- 券商资金账号
    server_ip       TEXT NOT NULL,
    server_port     INTEGER NOT NULL DEFAULT 6001,
    trade_password  TEXT,                             -- 交易密码（加密存储，生产用 Vault）
    auto_reconnect  BOOLEAN NOT NULL DEFAULT TRUE,
    reconnect_max   INTEGER NOT NULL DEFAULT 5,       -- 最大重连次数
    reconnect_interval_sec INTEGER NOT NULL DEFAULT 10,
    status          TEXT NOT NULL DEFAULT 'disconnected', -- connected | connecting | disconnected | error
    last_heartbeat  TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_broker_configs_status ON broker_configs(status);
```

### 2.2 审计日志表 `trade_audit_log`（append-only, immutable）

```sql
CREATE TABLE IF NOT EXISTS trade_audit_log (
    id              SERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,                    -- 'order_place' | 'order_cancel' | 'order_fill'
                                                     -- 'broker_connect' | 'broker_disconnect'
                                                     -- 'risk_reject' | 'circuit_breaker'
                                                     -- 'mode_switch' | 'position_sync'
                                                     -- 'config_change'
    trade_mode      TEXT NOT NULL,                    -- 'paper' | 'live'
    operator_id     INTEGER,                          -- users.id，NULL = 系统自动
    target_order_id TEXT,                             -- 关联委托单号
    target_code     TEXT,                             -- 关联股票代码
    detail          JSONB NOT NULL DEFAULT '{}',      -- 完整操作上下文（请求体、响应体、风控结果）
    client_ip       INET,                             -- 来源 IP
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 审计日志不可修改、不可删除（权限控制 + 应用层禁止 UPDATE/DELETE）
-- 仅允许 INSERT 和 SELECT
-- 索引按时间范围查询（审计回溯）
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON trade_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_event ON trade_audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_operator ON trade_audit_log(operator_id);

-- 禁止 UPDATE/DELETE 的触发器（数据库层兜底）
CREATE OR REPLACE FUNCTION prevent_audit_mutate()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % not allowed on trade_audit_log', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER no_audit_update
    BEFORE UPDATE ON trade_audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_mutate();

CREATE TRIGGER no_audit_delete
    BEFORE DELETE ON trade_audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_mutate();
```

### 2.3 风控规则配置表 `risk_rules`

```sql
CREATE TABLE IF NOT EXISTS risk_rules (
    id                  SERIAL PRIMARY KEY,
    rule_name           TEXT NOT NULL UNIQUE,
    rule_type           TEXT NOT NULL,                -- 'daily_loss_limit' | 'single_order_limit'
                                                     -- 'position_concentration' | 'max_positions'
                                                     -- 'blacklist' | 'order_frequency'
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    threshold_value     NUMERIC NOT NULL,             -- 阈值（金额/数量/百分比）
    threshold_unit      TEXT NOT NULL DEFAULT 'absolute', -- 'absolute' | 'percent' | 'count'
    scope               TEXT NOT NULL DEFAULT 'global', -- 'global' | 'per_user' | 'per_stock'
    action              TEXT NOT NULL DEFAULT 'reject',  -- 'reject' | 'warn' | 'circuit_break'
    cooldown_seconds    INTEGER NOT NULL DEFAULT 0,   -- 触发后冷却时间，0 = 无冷却
    description         TEXT,
    created_by          INTEGER,                      -- users.id
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_rules_enabled ON risk_rules(enabled);

-- 预制规则
INSERT INTO risk_rules (rule_name, rule_type, threshold_value, threshold_unit, scope, action, description) VALUES
    ('日亏损熔断', 'daily_loss_limit', 5, 'percent', 'global', 'circuit_break', '当日累计亏损超过初始资金的5%时自动暂停交易'),
    ('单笔下单上限', 'single_order_limit', 100000, 'absolute', 'global', 'reject', '单笔委托金额不超过10万元'),
    ('单票集中度', 'position_concentration', 30, 'percent', 'per_stock', 'reject', '单只股票持仓不超过总资金的30%'),
    ('最大持仓数', 'max_positions', 10, 'count', 'global', 'warn', '同时持仓股票不超过10只'),
    ('黑名单', 'blacklist', 0, 'absolute', 'global', 'reject', '禁止交易的股票列表（ST、退市整理等）')
ON CONFLICT (rule_name) DO NOTHING;
```

### 2.4 熔断状态表 `circuit_breaker_state`

```sql
CREATE TABLE IF NOT EXISTS circuit_breaker_state (
    id                  SERIAL PRIMARY KEY,
    breaker_type        TEXT NOT NULL,                -- 'daily_loss' | 'consecutive_loss'
    status              TEXT NOT NULL DEFAULT 'closed', -- 'closed' | 'open' | 'half_open'
    triggered_at        TIMESTAMP,                    -- 最近触发时间
    triggered_by_rule   TEXT,                         -- 触发规则名称 → risk_rules.rule_name
    triggered_value     NUMERIC,                      -- 触发时的实际值
    daily_pnl           NUMERIC NOT NULL DEFAULT 0,   -- 当日累计盈亏
    daily_initial_capital NUMERIC NOT NULL,           -- 当日初始资金
    remaining_cooldown  INTEGER DEFAULT 0,            -- 剩余冷却秒数
    override_by         INTEGER,                      -- users.id，管理员手动解除
    override_at         TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 每个类型只保留一条记录
CREATE UNIQUE INDEX IF NOT EXISTS idx_breaker_type ON circuit_breaker_state(breaker_type);
```

### 2.5 委抭/持仓表（扩展现有）

在 `PaperTradingEngine` 内存数据基础上，实盘增加持久化：

```sql
CREATE TABLE IF NOT EXISTS live_orders (
    id                  SERIAL PRIMARY KEY,
    order_uuid          TEXT NOT NULL UNIQUE,          -- 本地 ID（UUID v7）
    broker_order_id     TEXT,                          -- 券商返回的委托编号
    user_id             INTEGER NOT NULL REFERENCES users(id),
    trade_mode          TEXT NOT NULL DEFAULT 'live',  -- 'paper' | 'live'
    code                TEXT NOT NULL,
    direction           TEXT NOT NULL,                  -- 'BUY' | 'SELL'
    order_type          TEXT NOT NULL DEFAULT 'limit', -- 'market' | 'limit'
    price               NUMERIC NOT NULL,
    volume              INTEGER NOT NULL,
    filled_volume       INTEGER NOT NULL DEFAULT 0,
    filled_avg_price    NUMERIC,
    fee                 NUMERIC NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'filled'|'partial'|'cancelled'|'rejected'
    reject_reason       TEXT,
    risk_check_result   JSONB,                         -- 风控检查结果快照
    submitted_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    filled_at           TIMESTAMP,
    cancelled_at        TIMESTAMP,
    broker_sync_at      TIMESTAMP,                     -- 最后一次与券商同步时间
    
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_orders_user ON live_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_live_orders_status ON live_orders(status);
CREATE INDEX IF NOT EXISTS idx_live_orders_code ON live_orders(code);
CREATE INDEX IF NOT EXISTS idx_live_orders_created ON live_orders(created_at DESC);

CREATE TABLE IF NOT EXISTS live_positions (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    code                TEXT NOT NULL,
    volume              INTEGER NOT NULL,
    available_volume    INTEGER NOT NULL,              -- 可用股数（扣冻结）
    avg_cost            NUMERIC NOT NULL,
    current_price       NUMERIC,
    market_value        NUMERIC,
    pnl                 NUMERIC,
    pnl_pct             NUMERIC,
    broker_sync_at      TIMESTAMP,

    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    
    UNIQUE(user_id, code)
);

CREATE INDEX IF NOT EXISTS idx_live_positions_user ON live_positions(user_id);
```

---

## 3. BrokerInterface 抽象（Python Protocol）

### 3.1 接口定义

文件位置：`services/trade-service/app/brokers/base.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol


@dataclass
class BrokerOrder:
    """券商返回的委托标准化结构"""
    broker_order_id: str
    code: str
    direction: str           # 'BUY' | 'SELL'
    price: float
    volume: int
    filled_volume: int
    filled_avg_price: float
    fee: float
    status: str              # 'pending'|'filled'|'partial'|'cancelled'|'rejected'
    status_msg: str          # 券商原始状态描述
    submitted_at: str        # ISO 8601
    updated_at: str          # ISO 8601


@dataclass
class BrokerPosition:
    """券商返回的持仓标准化结构"""
    code: str
    volume: int
    available_volume: int    # 可卖数量
    avg_cost: float
    current_price: float
    market_value: float
    pnl: float


@dataclass
class BrokerAccount:
    """券商返回的账户标准化结构"""
    account_id: str
    total_assets: float      # 总资产
    available_cash: float    # 可用资金
    frozen_cash: float       # 冻结资金
    market_value: float      # 持仓市值
    total_pnl: float         # 累计盈亏
    daily_pnl: float         # 当日盈亏


@dataclass
class BrokerConnectionStatus:
    connected: bool
    broker_name: str
    account_id: str
    last_heartbeat: str | None
    error_message: str | None
    reconnect_count: int


class BrokerInterface(ABC):
    """券商接口抽象基类。

    所有实盘 Broker 实现必须实现此接口。
    模拟交易使用 MockBroker（空实现，直接返回成功）。
    """

    @abstractmethod
    async def connect(self, config: dict) -> bool:
        """建立券商连接。返回 True 表示成功。"""
        ...

    @abstractmethod
    async def disconnect(self) -> bool:
        """断开券商连接。"""
        ...

    @abstractmethod
    async def get_status(self) -> BrokerConnectionStatus:
        """获取当前连接状态。"""
        ...

    @abstractmethod
    async def place_order(
        self,
        code: str,
        direction: str,
        price: float,
        volume: int,
        order_type: str = "limit",
    ) -> BrokerOrder:
        """下委托单。price=0 表示市价单。

        Raises:
            BrokerConnectionError: 券商连接断开
            BrokerOrderRejectedError: 券商拒绝（含拒绝原因）
            BrokerTimeoutError: 超时
        """
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """撤单。返回 True 表示撤单成功。"""
        ...

    @abstractmethod
    async def query_order(self, broker_order_id: str) -> BrokerOrder:
        """查询单笔委托状态。"""
        ...

    @abstractmethod
    async def query_orders(self) -> list[BrokerOrder]:
        """查询当日所有委托。"""
        ...

    @abstractmethod
    async def query_positions(self) -> list[BrokerPosition]:
        """查询当前持仓（含市价）。"""
        ...

    @abstractmethod
    async def query_account(self) -> BrokerAccount:
        """查询账户资金信息。"""
        ...


class MockBroker(BrokerInterface):
    """模拟券商 — 所有操作直接返回成功，用于模拟交易和测试。"""
    # 每个方法返回固定 mock 数据，不执行真实操作
    # 具体实现略
```

### 3.2 异常层级

文件位置：`services/trade-service/app/brokers/exceptions.py`

```python
class BrokerError(Exception):
    """券商基础异常"""
    pass

class BrokerConnectionError(BrokerError):
    """连接失败"""
    pass

class BrokerAuthenticationError(BrokerError):
    """认证失败（密码/证书错误）"""
    pass

class BrokerOrderRejectedError(BrokerError):
    """委托被拒绝"""
    def __init__(self, message: str, reject_reason: str):
        super().__init__(message)
        self.reject_reason = reject_reason

class BrokerTimeoutError(BrokerError):
    """请求超时"""
    pass

class BrokerCircuitBreakerOpen(BrokerError):
    """熔断器开启，拒绝交易"""
    pass
```

### 3.3 Broker 工厂

文件位置：`services/trade-service/app/brokers/factory.py`

```python
from app.brokers.base import BrokerInterface
from app.brokers.mock_broker import MockBroker
# from app.brokers.xtquant_broker import XtquantBroker  # 实盘实现时导入


def create_broker(mode: str, config: dict | None = None) -> BrokerInterface:
    """根据 trade_mode 创建 Broker 实例。

    Args:
        mode: 'paper' | 'live'
        config: 券商连接配置（live 模式必需）

    Returns:
        BrokerInterface 实例
    """
    if mode == "paper":
        return MockBroker()
    elif mode == "live":
        broker_name = (config or {}).get("broker_name", "xtquant")
        if broker_name == "xtquant":
            # return XtquantBroker(config)
            raise NotImplementedError("XtquantBroker not yet implemented")
        raise ValueError(f"Unknown broker: {broker_name}")
    raise ValueError(f"Unknown mode: {mode}")
```

---

## 4. 风控规则配置 Schema (Pydantic)

文件位置：`services/trade-service/app/schemas/risk.py`

```python
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, field_validator


class RiskRuleType(StrEnum):
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    SINGLE_ORDER_LIMIT = "single_order_limit"
    POSITION_CONCENTRATION = "position_concentration"
    MAX_POSITIONS = "max_positions"
    BLACKLIST = "blacklist"
    ORDER_FREQUENCY = "order_frequency"


class ThresholdUnit(StrEnum):
    ABSOLUTE = "absolute"    # 绝对金额/数量
    PERCENT = "percent"      # 百分比
    COUNT = "count"          # 计数


class RiskAction(StrEnum):
    REJECT = "reject"           # 拒绝单笔
    WARN = "warn"               # 仅警告，放行
    CIRCUIT_BREAK = "circuit_break"  # 触发熔断


class RiskScope(StrEnum):
    GLOBAL = "global"
    PER_USER = "per_user"
    PER_STOCK = "per_stock"


# ── Request schemas ──

class RiskRuleCreate(BaseModel):
    rule_name: str = Field(min_length=1, max_length=100)
    rule_type: RiskRuleType
    enabled: bool = True
    threshold_value: float = Field(gt=0)
    threshold_unit: ThresholdUnit
    scope: RiskScope = RiskScope.GLOBAL
    action: RiskAction = RiskAction.REJECT
    cooldown_seconds: int = Field(ge=0, default=0)
    description: str | None = None


class RiskRuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold_value: float | None = Field(default=None, gt=0)
    action: RiskAction | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0)
    description: str | None = None


# ── Response schemas ──

class RiskRuleResponse(BaseModel):
    id: int
    rule_name: str
    rule_type: RiskRuleType
    enabled: bool
    threshold_value: float
    threshold_unit: ThresholdUnit
    scope: RiskScope
    action: RiskAction
    cooldown_seconds: int
    description: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RiskCheckResult(BaseModel):
    """风控检查结果"""
    passed: bool
    checks: list[RiskCheckItem]
    overall_action: RiskAction  # 最严格的动作


class RiskCheckItem(BaseModel):
    rule_name: str
    rule_type: RiskRuleType
    passed: bool
    action: RiskAction
    current_value: float | None = None
    threshold_value: float
    message: str


class CircuitBreakerStatus(BaseModel):
    breaker_type: str
    status: str              # 'closed' | 'open' | 'half_open'
    triggered_at: datetime | None
    triggered_by_rule: str | None
    triggered_value: float | None
    daily_pnl: float
    daily_initial_capital: float
    daily_loss_pct: float    # 计算字段
    remaining_cooldown: int
    can_trade: bool          # 计算字段：status != 'open'
```

---

## 5. API 契约

所有端点前缀：`/api/v1/trade`

### 5.1 通用约定

- **Content-Type**: `application/json`
- **认证方式**: `Authorization: Bearer <access_token>`（所有端点受保护）
- **错误响应** 统一格式：

```json
{
  "detail": "人类可读错误描述",
  "error_code": "RISK_REJECT_DAILY_LOSS",
  "extra": {}
}
```

| HTTP Status | 场景 |
|---|---|
| 200 | 成功 |
| 201 | 委托已创建 |
| 400 | 参数校验失败 / 风控拒绝 |
| 401 | 未认证或 token 过期 |
| 403 | 无权限（非 admin 访问管理端点）|
| 409 | 重复委托 / 熔断器开启 |
| 500 | 内部错误 |
| 502 | 券商连接错误（上游故障）|
| 503 | 券商不可用（熔断/维护）|

### 5.2 端点明细

#### POST /api/v1/trade/order — 下单（模拟 + 实盘统一入口）

```
请求:
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "code": "000001",
  "direction": "BUY",
  "price": 0,                    // 0 = 市价单
  "volume": 100,
  "order_type": "market",        // "market" | "limit"
  "trade_mode": "live"           // "paper" | "live" — 缺省取全局 mode
}

响应 201:
{
  "order_uuid": "018f4e2a-...",
  "broker_order_id": "XT20260610001",   // 实盘返回券商委托编号，模拟盘为 null
  "code": "000001",
  "direction": "BUY",
  "order_type": "market",
  "price": 12.34,
  "volume": 100,
  "status": "filled",                   // live 模式 initial status = "pending"
  "fee": 5.00,
  "risk_check": {                       // 风控检查结果快照
    "passed": true,
    "checks": [...]
  },
  "submitted_at": "2026-06-10T14:30:00+08:00"
}

错误:
400 — 风控拒绝 {"detail": "单笔下单超过上限", "error_code": "RISK_REJECT_SINGLE_ORDER", "extra": {"rule": "单笔下单上限", "threshold": 100000, "actual": 150000}}
400 — 黑名单股票 {"detail": "000001 在黑名单中", "error_code": "RISK_REJECT_BLACKLIST"}
409 — 熔断器中 {"detail": "交易已暂停（日亏损熔断触发）", "error_code": "CIRCUIT_BREAKER_OPEN", "extra": {"daily_loss_pct": 5.2, "cooldown_remaining": 1800}}
502 — 券商连接错误 {"detail": "券商连接失败，请稍后重试", "error_code": "BROKER_CONNECTION_ERROR"}
```

**实现要点**：
- 实盘下单走 `RiskGateway.validate(order)` → `CircuitBreaker.check()` → `BrokerInterface.place_order()` → `AuditLogger.log()`
- 模拟盘下单走 `RiskGateway.validate(order)`（可选，可配置跳过）→ `PaperTradingEngine.place_order()` → 仍然记 `AuditLogger.log()`
- `trade_mode` 参数可覆盖全局 mode：单笔下到模拟盘 vs 实盘（调试用）

#### DELETE /api/v1/trade/order/{order_uuid} — 撤单

```
请求:
Authorization: Bearer <access_token>
Path: order_uuid — 本地委托 UUID（非券商委托编号）

响应 200:
{
  "order_uuid": "018f4e2a-...",
  "broker_order_id": "XT20260610001",
  "status": "cancelled",
  "cancelled_at": "2026-06-10T14:31:00+08:00"
}

错误:
404 — 委托不存在或已完成
502 — 券商撤单失败 {"detail": "撤单失败：券商返回 XXX", "error_code": "BROKER_CANCEL_FAILED"}
```

**实现要点**：
- 查找 `live_orders` / `orders` 中 `order_uuid` → 获取 `broker_order_id` → 调用 `BrokerInterface.cancel_order(broker_order_id)`
- 仅 `pending` 或 `partial` 状态可撤
- 已完全成交的订单返回 400（不是 404）

#### GET /api/v1/trade/orders — 委托列表

```
请求:
Authorization: Bearer <access_token>
Query params:
  ?trade_mode=live            // "paper" | "live" | "all"，缺省取全局 mode
  &status=pending             // "all" | "pending" | "filled" | "partial" | "cancelled" | "rejected"
  &code=000001                // 可选，按股票代码过滤
  &page=1&page_size=20
  &start=2026-06-09T00:00:00 // 可选，起始时间
  &end=2026-06-10T23:59:59   // 可选，结束时间

响应 200:
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "trade_mode": "live",
  "orders": [
    {
      "order_uuid": "018f4e2a-...",
      "broker_order_id": "XT20260610001",
      "code": "000001",
      "direction": "BUY",
      "order_type": "market",
      "price": 12.34,
      "volume": 100,
      "filled_volume": 100,
      "filled_avg_price": 12.34,
      "fee": 5.00,
      "status": "filled",
      "reject_reason": null,
      "submitted_at": "2026-06-10T14:30:00+08:00",
      "filled_at": "2026-06-10T14:30:01+08:00"
    }
  ]
}
```

#### GET /api/v1/trade/positions — 持仓列表（加实盘同步）

```
请求:
Authorization: Bearer <access_token>
Query params:
  ?trade_mode=live           // "paper" | "live" | "all"
  &sync=true                // true = 先从券商实时拉取再返回（实盘）
                            // false = 返回缓存/内存数据

响应 200:
{
  "trade_mode": "live",
  "synced_at": "2026-06-10T14:35:00+08:00",
  "positions": [
    {
      "code": "000001",
      "volume": 1000,
      "available_volume": 800,
      "avg_cost": 12.00,
      "current_price": 12.34,
      "market_value": 12340.00,
      "pnl": 340.00,
      "pnl_pct": 2.83
    }
  ]
}

错误:
502 — 券商同步失败 {"detail": "持仓同步失败", "error_code": "BROKER_SYNC_FAILED"}
```

**实现要点**：
- `sync=true` 时触发 `BrokerInterface.query_positions()` → 覆盖/合并本地 `live_positions` 表 → 返回最新数据
- `sync=false` 仅返回本地库中最后同步的快照
- 模拟盘直接返回 `PaperTradingEngine.get_positions()`，忽略 sync 参数

#### GET /api/v1/trade/account — 账户信息

```
请求:
Authorization: Bearer <access_token>
Query params:
  ?trade_mode=live
  &sync=true                // 实盘：是否从券商实时拉取

响应 200:
{
  "trade_mode": "live",
  "broker_name": "xtquant",
  "account_id": "88888888",
  "total_assets": 1050000.00,
  "available_cash": 350000.00,
  "frozen_cash": 50000.00,
  "market_value": 650000.00,
  "total_pnl": 50000.00,
  "total_pnl_pct": 5.00,
  "daily_pnl": 3200.00,
  "daily_pnl_pct": 0.32,
  "synced_at": "2026-06-10T14:35:00+08:00",
  "circuit_breaker": {
    "status": "closed",
    "daily_loss_pct": 0.32,
    "can_trade": true
  }
}
```

**实现要点**：
- 实盘返回真实券商余额（`BrokerInterface.query_account()`）
- 模拟盘返回 `PaperTradingEngine.get_account()` 计算值
- `circuit_breaker` 子对象实时反映熔断状态

#### PUT /api/v1/trade/mode — 切换交易模式

```
请求:
Authorization: Bearer <access_token>  // 需要 admin 或 analyst
Content-Type: application/json

{
  "trade_mode": "live"                // "paper" | "live"
}

响应 200:
{
  "previous_mode": "paper",
  "current_mode": "live",
  "switched_at": "2026-06-10T14:40:00+08:00",
  "broker_status": {
    "connected": true,
    "broker_name": "xtquant",
    "account_id": "88888888"
  }
}

错误:
400 — "trade_mode 必须为 paper 或 live"
403 — 权限不足（viewer 不可切换）
503 — 切换到 live 但券商未连接 {"detail": "请先连接券商", "error_code": "BROKER_NOT_CONNECTED"}
```

**实现要点**：
- 修改全局 `TRADE_MODE` 环境变量/配置（影响后续所有请求的默认 mode）
- 切换时检测：若切到 `live`，券商必须已连接
- 切换记录到审计日志（`event_type = 'mode_switch'`）

#### POST /api/v1/trade/broker/connect — 连接券商

```
请求:
Authorization: Bearer <access_token>  // 需要 admin
Content-Type: application/json

{
  "broker_name": "xtquant",
  "account_id": "88888888",
  "server_ip": "192.168.1.100",
  "server_port": 6001,
  "trade_password": "encrypted_placeholder"
}

响应 200:
{
  "broker_name": "xtquant",
  "account_id": "88888888",
  "status": "connected",
  "connected_at": "2026-06-10T14:45:00+08:00"
}

错误:
400 — 缺少必填字段
401 — 券商认证失败 {"detail": "账号或密码错误", "error_code": "BROKER_AUTH_FAILED"}
502 — 连接超时 {"detail": "连接券商服务超时", "error_code": "BROKER_TIMEOUT"}
409 — 已有活动连接 {"detail": "已存在活动连接，请先断开", "error_code": "BROKER_ALREADY_CONNECTED"}
```

**安全约束**：`trade_password` 传输时加密（TLS + 应用层 AES），存储时加密（生产环境用 Vault / KMS，开发环境用 Fernet 对称加密）。

#### GET /api/v1/trade/broker/status — 券商连接状态

```
请求:
Authorization: Bearer <access_token>

响应 200:
{
  "connected": true,
  "broker_name": "xtquant",
  "account_id": "88888888",
  "status": "connected",
  "last_heartbeat": "2026-06-10T14:46:00+08:00",
  "heartbeat_interval_sec": 30,
  "reconnect_count": 0,
  "reconnect_max": 5,
  "error_message": null,
  "uptime_seconds": 3600
}
```

#### GET /api/v1/trade/audit-log — 审计日志

```
请求:
Authorization: Bearer <access_token>  // 需要 admin 或 analyst
Query params:
  ?event_type=order_place    // 可选过滤
  &operator_id=1             // 可选，操作人
  &code=000001               // 可选，股票代码
  &trade_mode=live           // 可选
  &page=1&page_size=50
  &start=2026-06-09T00:00:00
  &end=2026-06-10T23:59:59

响应 200:
{
  "total": 128,
  "page": 1,
  "page_size": 50,
  "records": [
    {
      "id": 1,
      "event_type": "order_place",
      "trade_mode": "live",
      "operator_id": 1,
      "operator_name": "zhangsan",       // JOIN users
      "target_order_id": null,
      "target_code": "000001",
      "detail": {
        "request": {"code": "000001", "direction": "BUY", "volume": 100, "price": 0},
        "risk_check": {"passed": true},
        "result": {"status": "filled", "broker_order_id": "XT20260610001"}
      },
      "client_ip": "192.168.1.50",
      "created_at": "2026-06-10T14:30:00+08:00"
    }
  ]
}

错误:
403 — 权限不足（viewer 不可查看审计日志）
```

**安全约束**：
- 审计日志**只读**，不提供任何 UPDATE/DELETE 端点
- 数据库层由触发器 `prevent_audit_mutate()` 兜底保护
- 管理员不可删除审计日志（防止内鬼擦除痕迹）

---

## 6. 熔断配置（Circuit Breaker）

### 6.1 熔断状态机

```
   ┌─────────┐    日亏损达到阈值     ┌─────────┐
   │ CLOSED  │ ───────────────────> │  OPEN   │
   │ (正常)  │                       │ (暂停)  │
   └────┬────┘                       └────┬────┘
        ^                                 │
        │      冷却时间 + 手动恢复         │
        │    ┌───────────────────────────┘
        │    v
   ┌────┴────────┐
   │  HALF_OPEN  │ ──── 下一笔若失败 ──> OPEN
   │  (试探)     │ ──── 下一笔若成功 ──> CLOSED
   └─────────────┘
```

### 6.2 配置参数（环境变量）

```bash
# backend/.env（gitignored）
CIRCUIT_BREAKER_DAILY_LOSS_PCT=5.0     # 日亏损阈值（%，占初始资金）
CIRCUIT_BREAKER_COOLDOWN_MINUTES=30    # 熔断后冷却时间（分钟）
CIRCUIT_BREAKER_AUTO_RESET=true        # 冷却后自动进入 HALF_OPEN
CIRCUIT_BREAKER_HALF_OPEN_MAX_ORDERS=1 # HALF_OPEN 阶段最多允许 N 笔委托
```

### 6.3 手动管理端点

#### POST /api/v1/trade/circuit-breaker/reset — 手动重置熔断

```
请求:
Authorization: Bearer <access_token>  // 需要 admin
Content-Type: application/json

{
  "breaker_type": "daily_loss",
  "reason": "市场开盘，确认手动恢复"
}

响应 200:
{
  "breaker_type": "daily_loss",
  "previous_status": "open",
  "current_status": "closed",
  "reset_by": 1,
  "reset_at": "2026-06-10T15:00:00+08:00",
  "reason": "市场开盘，确认手动恢复"
}

错误:
403 — 非 admin
404 — 熔断器类型不存在
```

#### GET /api/v1/trade/circuit-breaker — 查询熔断状态

```
请求:
Authorization: Bearer <access_token>

响应 200:
{
  "breakers": [
    {
      "breaker_type": "daily_loss",
      "status": "closed",
      "triggered_at": null,
      "triggered_by_rule": "日亏损熔断",
      "daily_pnl": 3200.00,
      "daily_initial_capital": 1000000.00,
      "daily_loss_pct": -0.32,
      "can_trade": true,
      "remaining_cooldown": 0
    }
  ]
}
```

---

## 7. Pydantic Schema 汇总（`services/trade-service/app/schemas/trade.py`）

```python
from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class Direction(str):
    """BUY / SELL，由 Pydantic validator 校验"""
    pass


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class TradeMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ── Place Order ──

class PlaceOrderRequest(BaseModel):
    code: str = Field(min_length=5, max_length=8, description="股票代码，如 000001")
    direction: str = Field(description="BUY or SELL")
    price: float = Field(default=0, ge=0, description="0 = market order")
    volume: int = Field(ge=1, description="委托股数，A股需100的整数倍")
    order_type: OrderType = OrderType.MARKET
    trade_mode: TradeMode | None = Field(
        default=None, description="None = 使用全局 mode"
    )

    @model_validator(mode="after")
    def validate_volume_multiple(self):
        if self.volume % 100 != 0:
            raise ValueError("A股委托股数必须为100的整数倍")
        return self

    @model_validator(mode="after")
    def validate_direction(self):
        if self.direction.upper() not in ("BUY", "SELL"):
            raise ValueError("direction 必须为 BUY 或 SELL")
        return self


class PlaceOrderResponse(BaseModel):
    order_uuid: str
    broker_order_id: str | None
    code: str
    direction: str
    order_type: OrderType
    price: float
    volume: int
    status: OrderStatus
    fee: float
    risk_check: dict
    submitted_at: str


# ── Cancel Order ──

class CancelOrderResponse(BaseModel):
    order_uuid: str
    broker_order_id: str | None
    status: str
    cancelled_at: str


# ── Order List ──

class OrderItem(BaseModel):
    order_uuid: str
    broker_order_id: str | None
    code: str
    direction: str
    order_type: OrderType
    price: float
    volume: int
    filled_volume: int
    filled_avg_price: float | None
    fee: float
    status: OrderStatus
    reject_reason: str | None
    submitted_at: str
    filled_at: str | None


class PaginatedOrdersResponse(BaseModel):
    total: int
    page: int
    page_size: int
    trade_mode: str
    orders: list[OrderItem]


# ── Position ──

class PositionItem(BaseModel):
    code: str
    volume: int
    available_volume: int
    avg_cost: float
    current_price: float
    market_value: float
    pnl: float
    pnl_pct: float


class PositionsResponse(BaseModel):
    trade_mode: str
    synced_at: str | None
    positions: list[PositionItem]


# ── Account ──

class CircuitBreakerBrief(BaseModel):
    status: str
    daily_loss_pct: float
    can_trade: bool


class AccountResponse(BaseModel):
    trade_mode: str
    broker_name: str | None
    account_id: str | None
    total_assets: float
    available_cash: float
    frozen_cash: float
    market_value: float
    total_pnl: float
    total_pnl_pct: float
    daily_pnl: float
    daily_pnl_pct: float
    synced_at: str | None
    circuit_breaker: CircuitBreakerBrief


# ── Mode Switch ──

class SwitchModeRequest(BaseModel):
    trade_mode: TradeMode


class SwitchModeResponse(BaseModel):
    previous_mode: str
    current_mode: str
    switched_at: str
    broker_status: dict | None


# ── Broker Connect ──

class BrokerConnectRequest(BaseModel):
    broker_name: str
    account_id: str
    server_ip: str
    server_port: int = Field(default=6001, ge=1, le=65535)
    trade_password: str | None = None


class BrokerConnectResponse(BaseModel):
    broker_name: str
    account_id: str
    status: str
    connected_at: str


# ── Broker Status ──

class BrokerStatusResponse(BaseModel):
    connected: bool
    broker_name: str
    account_id: str | None
    status: str
    last_heartbeat: str | None
    heartbeat_interval_sec: int
    reconnect_count: int
    reconnect_max: int
    error_message: str | None
    uptime_seconds: int


# ── Audit Log ──

class AuditLogItem(BaseModel):
    id: int
    event_type: str
    trade_mode: str
    operator_id: int | None
    operator_name: str | None
    target_order_id: str | None
    target_code: str | None
    detail: dict
    client_ip: str | None
    created_at: str


class PaginatedAuditLogResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: list[AuditLogItem]


# ── Common ──

class ErrorResponse(BaseModel):
    detail: str
    error_code: str | None = None
    extra: dict | None = None
```

---

## 8. 实施顺序建议

| Phase | 范围 | 依赖 |
|---|---|---|
| Phase 1 | `BrokerInterface` ABC + `MockBroker` / 审计日志表 `trade_audit_log` + append-only 触发器 | Postgres |
| Phase 2 | `RiskGateway` + `risk_rules` 表 + 风控 Pydantic Schema / 熔断配置 + `circuit_breaker_state` 表 | Phase 1 |
| Phase 3 | `POST /order` 加风控 / `DELETE /order/{uuid}` 撤单 / `GET /orders` `GET /positions` `GET /account` 重构（支持 mode 参数）| Phase 2 |
| Phase 4 | `PUT /mode` 切换 / `POST /broker/connect` `GET /broker/status` 券商连接 | Phase 3 |
| Phase 5 | `XtquantBroker` 真实实现 / `GET /audit-log` 审计查询 / 熔断管理端点 | Phase 4 |

---

## 9. 环境变量（草案）

```bash
# trade-service .env（gitignored）
TRADE_MODE=paper                       # paper | live

# 券商连接
BROKER_NAME=xtquant
BROKER_ACCOUNT_ID=
BROKER_SERVER_IP=
BROKER_SERVER_PORT=6001
BROKER_ENCRYPTION_KEY=                 # Fernet key for trade_password

# 风控
RISK_ENABLED=true                      # 是否启用风控（调试时可关闭）
RISK_DAILY_LOSS_PCT=5.0                # 日亏损阈值

# 熔断
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_COOLDOWN_MINUTES=30
CIRCUIT_BREAKER_AUTO_RESET=true

# 审计
AUDIT_RETENTION_DAYS=365               # 审计日志保留天数（定期归档）

# 连接
BROKER_HEARTBEAT_INTERVAL_SEC=30
BROKER_RECONNECT_MAX=5
BROKER_RECONNECT_INTERVAL_SEC=10
```

---

## 10. 关键决策点（开放问题）

### 决策点 1：trade_password 存储方案

| 方案 | 优点 | 缺点 |
|---|---|---|
| **Fernet 对称加密** | 简单，无外部依赖 | 密钥管理需人工；密钥泄露 = 全部泄露 |
| **Vault / KMS** | 生产级安全，审计 + 轮转 | 增加运维复杂度 |
| **不存密码** | 最安全 | 每次连接需手动输入，不适合自动化 |

**建议**：Phase 1 用 Fernet + env 变量；Phase 2 迁移到 Vault。待 product-lead 确认。

### 决策点 2：实盘委托流 — 同步等待券商回报 vs 异步回调？

| 方案 | 描述 |
|---|---|
| **同步等待** | `POST /order` 阻塞直到券商返回（通常 < 2s），超时返回 pending |
| **异步 + 轮询** | `POST /order` 立即返回 pending，前端轮询 `GET /orders` 或 WebSocket 推送状态更新 |

**建议**：Phase 1 采用**同步等待**（实现简单，Xtquant 局域网延迟可控）；Phase 2 加 WebSocket 推送状态变更。待 product-lead 确认。

### 决策点 3：实盘是否需要确认弹窗（双因素）？

| 方案 | 描述 |
|---|---|
| **无二次确认** | 直接下单，降低操作摩擦 |
| **二次确认** | 前端弹窗 "确认买入 000001 100股 @ 12.34？" |

**建议**：实盘下单前端必须二次确认 + 显示风控检查结果。这是行业最佳实践（避免误操作）。待 product-lead 确认。

---

## 附录 A：与现有代码风格对齐检查清单

- [x] 表名用小写复数 + 下划线（`live_orders`、`live_positions`、`risk_rules`）
- [x] `SERIAL PRIMARY KEY` 对齐 `screening_scores`、`predictions`、`users`
- [x] `TIMESTAMP DEFAULT NOW()` 对齐全部应用层表
- [x] 索引命名 `idx_<table>_<column>` 对齐 `idx_daily_kline_code`、`idx_users_email`
- [x] FastAPI 路由前缀 `/api/v1/trade` 对齐 `routes.py` 现有前缀
- [x] Pydantic `BaseModel` + `Field` + `field_validator` / `model_validator` 对齐 `schemas/auth.py` 风格
- [x] `StrEnum` 枚举对齐 `schemas/auth.py` 中 `VALID_ROLES` 模式
- [x] 错误响应 `{"detail": "..."}` 对齐 FastAPI 默认 `HTTPException` 格式，扩展 `error_code` + `extra`
- [x] 分页响应 `{"total": N, "page": N, "page_size": N, "items": [...]}` 对齐 `PaginatedUsersResponse`
- [x] `model_config = {"from_attributes": True}` 对齐 SQLAlchemy ORM 映射
- [x] `Query()` params for optional filters 对齐 `admin.py` list_users 风格
- [x] `Depends(get_current_user)` / `Depends(require_role("admin"))` 对齐现有 RBAC 依赖注入
- [x] 审计日志设计对齐 `docs/adr/001-auth-rbac.md` 决策点 3（login_audit_log 草案）
- [x] append-only 触发器 `prevent_audit_mutate()` 对齐 PostgreSQL 惯用模式
