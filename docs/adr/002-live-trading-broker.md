# ADR-002: 券商实盘交易集成 — BrokerInterface 抽象与短期方案选型

- 状态：Proposed
- 日期：2026-06-10
- 决策者：tech-lead
- 影响范围：trade-service（重构） + PostgreSQL（新增审计表） + 前端 Trade 页面（模式切换）

## 上下文

速赢 AI 证券投资管理平台当前仅支持模拟交易（Paper Trading Engine）。模拟交易引擎（`services/trade-service/app/engine.py`）实现了线程安全的内存订单撮合——订单即时成交于 mock 价格，维护持仓/账户/盈亏计算。前端 Trade 页面（`frontend/src/pages/Trade.tsx`）已有 `mode` 状态（`paper` / `live`）和对应的 UI Tag，但 `switch_mode` API 仅为占位（直接返回 `{"mode": mode, "status": "ok"}` 无实际切换逻辑）。

PRD AC-11.2 要求短期支持券商实盘接入，具体约束：
- 优先支持 A 股市场券商接口
- 同一交易界面，用户可在模拟盘与实盘之间切换
- 实盘交易必须通过风控网关，所有操作留审计日志
- 短期目标：支持 1 家券商；长期可扩展至多家

不做此决策的后果：
- 实盘交易代码将直接耦合券商 SDK，无抽象层保护 → 换券商 = 重写交易逻辑
- 无风控网关 → 可能发出超额/超价/超仓的异常订单，造成资金损失
- 无审计日志 → 合规风险，无法追溯"谁在什么时间以什么价格下了什么单"
- 模拟/实盘切换无统一接口 → 前端需要两套代码路径，增加维护成本

## 决策

### 决策 1：BrokerInterface 抽象层设计

| 维度 | 选型 | 理由 |
|------|------|------|
| 抽象模式 | **Python Protocol 类（`typing.Protocol`）+ ABC** | 既支持静态类型检查（mypy/Pylance），又允许无需显式继承的 duck typing；结合 `@abstractmethod` 确保接口契约。否决纯 ABC：限制灵活性；否决纯 duck typing：无编译期契约校验 |
| 接口粒度 | 6 个核心方法 + 事件回调 | 覆盖下单/撤单/查持仓/查账户/查委托/查成交 + 订单状态变更回调，与现有 PaperTradingEngine 方法签名兼容 |

**BrokerInterface 设计**（`services/trade-service/app/broker/interface.py`）：

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass
from abc import ABC, abstractmethod
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"       # 限价
    MARKET = "MARKET"     # 市价

class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class OrderRequest:
    symbol: str           # 证券代码（统一格式：000001.SZ / 600519.SH）
    side: OrderSide
    order_type: OrderType
    quantity: int         # 股
    price: float = 0.0    # 限价单价格，市价单=0

@dataclass
class OrderResult:
    order_id: str         # 本地订单 ID
    broker_order_id: str  # 券商系统订单 ID（如 xtquant 返回的 int）
    status: OrderStatus
    filled_qty: int = 0
    filled_avg_price: float = 0.0
    message: str = ""

@dataclass
class Position:
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    pnl: float = 0.0

@dataclass
class AccountInfo:
    total_assets: float       # 总资产
    available: float          # 可用资金
    frozen: float             # 冻结资金
    market_value: float       # 持仓市值
    total_pnl: float          # 累计盈亏
    daily_pnl: float          # 当日盈亏

@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    trade_time: str
    commission: float = 0.0   # 佣金
    stamp_tax: float = 0.0    # 印花税

@runtime_checkable
class BrokerInterface(Protocol):
    """券商接入抽象协议。新券商只需实现此接口。"""

    def connect(self) -> bool: ...
    def disconnect(self) -> bool: ...

    def place_order(self, req: OrderRequest) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> bool: ...

    def query_positions(self) -> list[Position]: ...

    def query_account(self) -> AccountInfo: ...

    def query_orders(self) -> list[OrderResult]: ...

    def query_trades(self) -> list[Trade]: ...

    def subscribe_callbacks(self, handler: "OrderCallback") -> None: ...
```

**与现有代码的关系**：现有 `PaperTradingEngine`（`engine.py:42-129`）的方法签名（`place_order` / `cancel_order` / `get_orders` / `get_positions` / `get_account`）已接近 BrokerInterface，重构成本低——将 dataclass 字段对齐，`PaperTradingEngine` 显式实现 `BrokerInterface` 协议即可。

### 决策 2：短期方案 — xtquant (QMT/miniQMT)

| 维度 | 选型 | 理由 |
|------|------|------|
| 短期券商接入 | **xtquant（QMT / miniQMT，迅投）** | Python 原生 API，无需 HTTP 通信开销；完整覆盖下单/撤单/查持仓/查账户/查成交 + 实时回调；免费（随券商账户提供）；A 股生态最成熟的量化交易接口之一。否决同花顺 iFinD：iFinD 的核心价值在行情数据/财务数据，交易执行能力弱（主要依赖 HTTP REST API，无可直接调用的交易 SDK） |

**技术细节**：
- **SDK**：`xtquant` Python 包，包含 `xttrader`（交易模块）和 `xtdata`（行情模块）。本项目仅使用 `xttrader`，行情数据继续使用现有 Kronos Data pipeline
- **连接方式**：miniQMT 模式——QMT 客户端运行于本地/NAS/云服务器，xtquant 通过本地 socket（mini 模式不依赖 QMT 主程序 GUI）连接交易服务器
- **核心调用链**：
  ```
  XtQuantTrader(path, session_id) → .start() → .connect()
  → .subscribe(StockAccount)  // 绑定资金账号
  → .order_stock(acc, code, order_type, qty, price_type, price)  // 下单
  → .cancel_order_stock(acc, order_id)  // 撤单
  → .query_stock_asset(acc) / .query_stock_positions(acc) / .query_stock_orders(acc) / .query_stock_trades(acc)
  ```
- **回调系统**：继承 `XtQuantTraderCallback` 实现 `on_stock_order` / `on_stock_trade` / `on_stock_asset` / `on_stock_position` / `on_disconnected` / `on_order_error`
- **部署约束**：需要一台运行 Windows 的机器（或 Windows Server/NAS 虚拟机）承载 QMT 客户端；trade-service 通过 `XtQuantTrader` 本地 socket 连接同一台机器的 miniQMT（路径参数指向 `userdata_mini` 目录）。若 trade-service 部署于 Linux Docker，需通过网络转发或单独 Windows 网关机器桥接

**备选方案**：

- **A. 同花顺 iFinD** — HTTP REST API，Token 鉴权，主要用于行情和财务数据。否决理由：(1) 交易能力不成熟，iFinD 的定位是数据终端而非交易终端，其 API 主要覆盖 `real_time_quotation`、`basic_data_service`、`date_sequence` 等数据接口，无原生 `order_stock` / `cancel_order` / `query_positions` 交易方法；(2) HTTP 延迟不适合交易场景（下单→券商→交易所→成交回报链路中额外增加 HTTP 层延迟）；(3) 需要付费订阅。iFinD 更适合作为未来**数据源**补充（财报、一致预期等），而非交易执行通道。

- **B. 直接对接券商柜台（CTP / XTP / 恒生等）** — CTP 是期货市场标准协议，XTP 是中泰证券的极速交易柜台，恒生是传统券商主流柜台。否决理由：(1) 每种柜台协议不同，接入成本高（CTP C++ API、XTP C++ API），需要大量封装工作；(2) 申请门槛高——CTP 需要期货公司推荐码，XTP 需要中泰证券账户，均不适合"快速支持 1 家券商"的短期目标；(3) QMT 作为中间层已经封装了主流柜台协议，向上提供统一 Python API，短期内复用 QMT 的封装是合理的选择。

- **C. Easytrader（开源，对接同花顺/东方财富客户端）** — GitHub 开源项目，通过操作券商客户端 GUI 来实现自动交易。否决理由：(1) GUI 自动化极其脆弱，券商客户端更新即可能破坏；(2) 无官方支持，API 不稳定；(3) 合规风险——模拟点击绕过券商安全机制。

### 决策 3：风控网关 — BrokerInterface 上层中间件

| 维度 | 选型 | 理由 |
|------|------|------|
| 风控架构 | **BrokerInterface 上层装饰器/中间件链（Risk Gateway）** | 风控逻辑独立于具体券商实现，可对 PaperBroker 和 LiveBroker 统一生效；符合单一职责——Broker 只管执行，RiskGateway 只管校验。否决"内嵌于 Broker"：风控逻辑与券商 SDK 耦合，换券商需重写风控；否决"独立微服务"：增加网络跃点延迟，下单链路不应引入额外外部依赖 |

**风控网关设计**（`services/trade-service/app/risk/gateway.py`）：

```
                   ┌─────────────┐
  Trade Routes  →  │ RiskGateway │ → BrokerInterface.place_order()
                   │  ┌────────┐ │
                   │  │ PreChecks│    Pre-check 链（可插拔）:
                   │  │  ·限额   │     1. MaxOrderAmountCheck    单笔最大金额
                   │  │  ·涨跌停 │     2. PositionLimitCheck     单票仓位上限
                   │  │  ·频控   │     3. PriceDeviationCheck    价格偏离校验
                   │  │  ·黑白名 │     4. DailyTradeCountCheck   日内交易频控
                   │  └────────┘ │     5. BlacklistCheck         黑名单校验
                   │  Broker.call │     6. CircuitBreakerCheck    熔断（连续亏损 N 笔）
                   │  ┌────────┐ │
                   │  │PostCheck│    Post-check（可选）:
                   │  │  ·成交价 │     1. SlippageCheck          滑点告警
                   │  └────────┘ │
                   └─────────────┘
```

- **Pre-check 链**：任何一步拒绝则直接返回 `OrderResult(status=REJECTED, message=...)`,不调用 Broker
- **Post-check 链**：订单提交后异步检查（滑点、成交价偏离），告警但不阻塞
- **配置方式**：环境变量 + 可动态加载的 JSON/YAML 配置，支持不同用户/角色的差异化风险参数
- **熔断机制**：连续 N 笔亏损 → 自动暂停实盘交易 N 分钟 → 需人工确认恢复

### 决策 4：审计日志 — PostgreSQL append-only table

| 维度 | 选型 | 理由 |
|------|------|------|
| 审计存储 | **PostgreSQL append-only 表 + 触发器防篡改** | 与现有基础设施一致（docker-compose 已运行 postgres:15-alpine）；append-only 保证不可篡改性；触发器层防止 UPDATE/DELETE。否决"写入普通日志文件"：无结构化查询能力，出问题时难以搜索和聚合；否决"独立审计服务"：过度设计，单表足够 |

**审计表设计**：

```sql
-- 交易审计日志（append-only，不可篡改）
CREATE TABLE IF NOT EXISTS trade_audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,          -- ORDER_PLACED / ORDER_FILLED / ORDER_CANCELLED / ORDER_REJECTED
    order_id TEXT NOT NULL,
    broker_order_id TEXT,
    user_id INTEGER,                   -- FK → users(id)，来自 JWT sub
    symbol TEXT NOT NULL,              -- 证券代码
    side TEXT NOT NULL,                -- BUY / SELL
    order_type TEXT NOT NULL,          -- LIMIT / MARKET
    quantity INTEGER NOT NULL,
    price NUMERIC(12, 4),
    filled_qty INTEGER DEFAULT 0,
    filled_avg_price NUMERIC(12, 4),
    commission NUMERIC(12, 4) DEFAULT 0,
    stamp_tax NUMERIC(12, 4) DEFAULT 0,
    risk_check_result JSONB,           -- 风控网关检查结果详情
    request_ip INET,                   -- 请求来源 IP
    broker_response JSONB,             -- 券商原始响应（用于问题排查）
    error_message TEXT,
    mode TEXT NOT NULL DEFAULT 'paper', -- paper / live
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 防篡改触发器：拒绝 UPDATE 和 DELETE
CREATE OR REPLACE FUNCTION prevent_audit_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'trade_audit_log is append-only: UPDATE/DELETE not allowed';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE OR DELETE ON trade_audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_modification();

-- 索引：按时间、用户、订单 ID 查询
CREATE INDEX idx_audit_created ON trade_audit_log(created_at DESC);
CREATE INDEX idx_audit_user ON trade_audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_order ON trade_audit_log(order_id);
CREATE INDEX idx_audit_symbol ON trade_audit_log(symbol, created_at DESC);
```

**写入时机**：交易路由层在调用 BrokerInterface 前后各写一条——`ORDER_SUBMITTED`（下单前）和 `ORDER_FILLED` / `ORDER_REJECTED`（下单后），形成完整的因果链。

### 决策 5：模拟盘/实盘切换 — Strategy 模式 + 工厂函数

| 维度 | 选型 | 理由 |
|------|------|------|
| 切换机制 | **同一 BrokerInterface，不同实现（PaperBroker / QmtLiveBroker），通过 `TRADE_MODE` 环境变量 + API 切换** | 前端无需感知底层实现差异；`GET /account` / `GET /positions` / `POST /order` 等端点保持不变；只有 `PUT /mode` 切换时底层 Broker 实例替换 |

**实现方案**：

```python
# services/trade-service/app/broker/__init__.py
from app.broker.interface import BrokerInterface
from app.engine import PaperTradingEngine
from app.broker.qmt_broker import QmtLiveBroker

_broker: BrokerInterface = None

def get_broker() -> BrokerInterface:
    global _broker
    if _broker is None:
        mode = os.environ.get("TRADE_MODE", "paper")
        _broker = _create_broker(mode)
    return _broker

def switch_mode(mode: str) -> BrokerInterface:
    global _broker
    _broker = _create_broker(mode)
    return _broker

def _create_broker(mode: str) -> BrokerInterface:
    if mode == "live":
        return QmtLiveBroker(
            path=os.environ["QMT_USERDATA_PATH"],
            account=os.environ["QMT_ACCOUNT"],
        )
    return PaperTradingEngine()
```

**风险**：切换模式时当前持仓/订单不同步——PaperBroker 的持仓和 LiveBroker 的持仓是独立的。解决方案：(1) `PUT /mode` 切换时返回两套持仓数据供前端对比；(2) 资产面板增加 `mode` indicator 避免混淆；(3) 实盘模式下禁用"重置账户"按钮。

## 备选方案

- **A. 不引入 BrokerInterface，直接修改 PaperTradingEngine 支持实盘** — 否决理由：违反单一职责，PaperTradingEngine（~130 行）会膨胀到 ~500+ 行，包含 QMT SDK 调用、回调处理、风控逻辑，所有逻辑混在一起，测试和维护都困难。

- **B. 新建独立 live-trade-service 微服务** — 否决理由：不符合"同一界面"的 PRD 要求；增加部署复杂度（新增 Dockerfile、端口、健康检查）；模拟/实盘切换需要跨服务调用，引入网络延迟。在同一服务内通过不同 Broker 实现切换更简洁。

- **C. 风控网关放在券商 SDK 调用层（Drivers 层）** — 否决理由：每个券商 SDK 的错误语义不同（xtquant 返回 int code，iFinD 返回 HTTP status），在券商层做风控需要理解每种 SDK 的错误模型，难以统一。在上层 BrokerInterface 之后做风控，面对的是统一的 `OrderRequest` / `OrderResult` dataclass。

## 影响

- **对现有代码**：
  - `trade-service`：新增 `app/broker/`（BrokerInterface + QmtLiveBroker）+ `app/risk/`（RiskGateway）+ `app/audit.py`（审计日志写入）；重构 `app/engine.py` → `app/broker/paper_broker.py`，使 PaperTradingEngine 实现 BrokerInterface
  - `app/routes.py`：路由层从直接调用 `engine.place_order()` 改为 `get_broker().place_order()`，中间经过 RiskGateway
  - PostgreSQL：新增 `trade_audit_log` 表（Alembic migration）
  - 前端：Trade 页面 `mode` 状态与后端 `TRADE_MODE` 对齐；`PUT /mode` 实际生效
  - 其他微服务：不受影响
- **对团队**：
  - 后端开发者需了解 xtquant SDK API 和 QMT 客户端部署
  - 需要一台 Windows 环境（物理机/虚拟机）运行 QMT 客户端，或使用支持 miniQMT 的 Linux 方案
- **对成本**：
  - xtquant SDK 免费（随券商账户提供）
  - QMT 客户端需在 Windows 环境运行（现有 Mac/Linux 开发环境外额外需求）
  - PostgreSQL 审计表预计每日 ~100-1000 行（取决于交易频率），存储成本可忽略
  - 无第三方服务费用
- **对运维**：
  - 新增监控点：QMT 连接状态（`on_disconnected` 回调告警）、风控拒绝率（>10% 告警）、订单提交延迟 p99（>500ms 告警）、撤单失败率
  - QMT 客户端健康检查（进程存活 + socket 可达）
  - 审计日志定期归档策略（按年分区，3 年以上归档至对象存储）

## 本 ADR 不覆盖的决策

- **多券商支持**：本 ADR 仅覆盖 1 家券商（xtquant/QMT）。多券商路由、智能路由（选择最优成交券商）留给后续 ADR
- **交易密码/二次确认**：实盘交易的交易密码独立于登录密码，本 ADR 不定义密码策略（由后续安全 ADR 覆盖）
- **Level-2 行情集成**：现有行情数据 pipeline（Kronos Data）不因实盘交易而改变，本 ADR 不覆盖行情源的切换
- **算法交易**（TWAP/VWAP/Iceberg）：留给 Phase B
- **期权/期货/港股通**：本 ADR 仅覆盖 A 股现货交易
- **QMT Linux 部署方案**：当前 miniQMT 官方仅支持 Windows。若有 Linux 部署硬需求，需在后续 ADR 中评估 Windows 虚拟机方案 vs 网络桥接方案 vs 对接支持 Linux 的券商柜台

## 后续工作

- [ ] backend-dev: 创建 `services/trade-service/app/broker/interface.py` — BrokerInterface Protocol 定义与 dataclass，预计 0.5d
- [ ] backend-dev: 重构 `app/engine.py` → `app/broker/paper_broker.py`，使 PaperTradingEngine 实现 BrokerInterface，预计 0.5d
- [ ] backend-dev: 创建 `app/broker/qmt_broker.py` — QmtLiveBroker 实现（xtquant 封装），预计 2d
- [ ] backend-dev: 创建 `app/risk/gateway.py` — 风控网关（Pre-check 链 + Post-check 链），预计 1.5d
- [ ] backend-dev: 创建 `app/audit.py` — 审计日志写入模块 + Alembic migration（trade_audit_log 表），预计 0.5d
- [ ] backend-dev: 重构 `app/routes.py` — 路由层接入 BrokerInterface + RiskGateway + Audit，预计 0.5d
- [ ] backend-dev: 实现 `PUT /mode` 实际切换逻辑 + 模式切换安全校验，预计 0.5d
- [ ] frontend-dev: Trade 页面 mode 状态持久化（localStorage）+ 实盘模式 UI 差异化（显示风控状态、禁止重置账户），预计 1d
- [ ] tech-lead: 协调获取 QMT 客户端安装包和券商资金账号（需联系合作券商开通量化交易权限）
- [ ] tech-lead: 回填本 ADR `## 版本与查证` 表中的 xtquant 版本号（首次安装后）

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。新增技术或大版本升级时必填。

**查证基线日期**：2026-06-10

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|------|----------|------------|-------------|----------|----------------------|
| xtquant (QMT) | 待首次安装后回填 | 待确认 | — | Active — 迅投持续更新 | [迅投官方知识库](https://dict.thinktrader.net/) — QMT 官方文档，持续更新；miniQMT 模式为官方推荐的 Python 量化接口 |
| PostgreSQL | 15-alpine（已在用） | 17 | 2 个 major 落后 | Active — PG 15 EOL 2027-11 | [docker-compose.yml](../docker/docker-compose.yml) — 已用 `postgres:15-alpine`；不在此 ADR 中强制升级 |
| FastAPI | 0.136.3（已在用） | 0.136.3 | 无差距 | Active | 同 ADR-001 版本查证 |

**备选（被否决）技术的版本记录**：

| 选型 | 当时最新版 | 否决原因 |
|------|-----------|---------|
| 同花顺 iFinD | v2.1 (2025-08-25) | 定位为数据终端而非交易终端；HTTP API 无法原生支持下单/撤单；交易延迟不可控 |
| Easytrader | 开源社区版 | GUI 自动化方案，极其脆弱；无官方支持；合规风险 |
| CTP / XTP | C++ API | 接入门槛高；每种柜台协议不同；不适合"短期支持 1 家券商"目标 |

---

### BrokerInterface 完整定义（参考）

上述决策 1 的接口定义即完整版。补充：`OrderCallback` 协议用于 QMT 回调适配——

```python
class OrderCallback(Protocol):
    """券商回调适配器。QMT 的 XtQuantTraderCallback 方法映射到此协议。"""
    def on_order_update(self, order: OrderResult) -> None: ...
    def on_trade(self, trade: Trade) -> None: ...
    def on_asset_update(self, account: AccountInfo) -> None: ...
    def on_position_update(self, position: Position) -> None: ...
    def on_error(self, error_msg: str) -> None: ...
    def on_disconnected(self) -> None: ...
```

### 模块结构（目标）

```
services/trade-service/app/
├── main.py                 # FastAPI app（不变，仅更新 docstring）
├── routes.py               # 路由层（重构：接入 BrokerInterface + RiskGateway + Audit）
├── broker/
│   ├── __init__.py         # get_broker() / switch_mode() 工厂
│   ├── interface.py        # BrokerInterface Protocol + dataclass 定义
│   ├── paper_broker.py     # PaperTradingEngine 重构版（实现 BrokerInterface）
│   └── qmt_broker.py       # QmtLiveBroker（xtquant 封装，实现 BrokerInterface）
├── risk/
│   ├── __init__.py
│   ├── gateway.py          # RiskGateway 主逻辑（pre-check 链 + post-check 链）
│   └── checks.py           # 具体风控规则实现
└── audit.py                # 审计日志写入（PostgreSQL append-only）
```
