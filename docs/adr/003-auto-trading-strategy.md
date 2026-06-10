# ADR-003: 量化自动交易策略引擎 — 执行架构与状态管理

- 状态：Proposed
- 日期：2026-06-10
- 决策者：tech-lead
- 影响范围：strategy-service（新增 auto_trading_engine + auto_trading_executor） + trade-service（复用 CircuitBreaker） + signal-service（信号数据消费） + 前端 AutoTrade/Strategy 页面

## 上下文

速赢 AI 证券投资管理平台已完成方案生成（strategy-service PlanStore）和交易执行层（trade-service BrokerInterface + MockBroker + XtquantBroker，见 ADR-002）。PRD AC-10.6~10.8 要求从确认方案自动生成量化交易策略，AC-11.5~11.6 要求支持策略的启停/暂停/恢复生命周期管理。

核心链路为：确认方案（PlanStore） → 自动生成策略配置（StrategyConfig） → 启动异步执行器（ExecutorManager） → 定时轮询信号服务（signal-service）评估买卖条件 → 调用交易服务（trade-service）下单 → 日亏损超限自动熔断（复用 trade-service CircuitBreaker）。

不做此决策的后果：方案确认后停留在"报告生成"阶段，无法自动执行交易，量化策略沦为纸上谈兵；用户需手动盯盘、手动下单，失去"量化自动交易"的核心价值主张。

## 决策

### 决策 1：策略执行引擎架构 — asyncio 定时轮询

| 维度 | 选型 | 理由 |
|------|------|------|
| 执行模型 | **asyncio 定时轮询（`_executor_loop`）** | 每个策略一个独立的 `asyncio.Task`，按配置间隔（默认 300s）顺序执行"拉取信号 → 评估条件 → 下单"循环。asyncio 协程在单个进程内天然支持数千个并发策略；无需引入 Celery/Redis 等额外基础设施；暂停/恢复通过 `asyncio.Event` 实现零开销等待。否决 Celery 异步任务：引入 Redis/RabbitMQ 中间件、Beat 调度器、Worker 进程管理，运维复杂度与 Phase A 阶段策略数量（预计 < 50）严重不匹配。否决纯事件驱动（WebSocket 行情推送触发）：需要改造 signal-service 和 Kronos Data pipeline 为推送模式，工程量大且当前信号生成本身是拉取模式（REST API）。 |

**实现细节**（`auto_trading_executor.py:206-242`）：

```python
async def _executor_loop(state: ExecutorState, strategy: StrategyConfig):
    interval = strategy.check_interval_sec
    while not state._stop_event.is_set():
        await state._pause_event.wait()       # 阻塞等待恢复
        if state._stop_event.is_set(): break
        await _run_one_check(state, strategy)
        # 分段等待，每秒检查 stop/pause 事件，避免长时间阻塞无法响应控制指令
        waited = 0
        while waited < interval:
            if state._stop_event.is_set(): break
            await asyncio.sleep(1)
            waited += 1
```

**检查周期**：每次检查顺序执行：(1) 从 trade-service 拉取当前持仓和账户信息；(2) 检查日亏损熔断；(3) 对已持仓标的逐一评估卖出条件并下单；(4) 对未持仓的 picks 逐一评估买入条件并下单。

**备选方案**：

- **A. Celery + Redis Beat 定时任务调度** — 成熟的分布式任务队列，支持定时调度、任务重试、结果后端。否决理由：(1) 引入 Redis + Celery Worker 两个额外进程，运维成本增加；(2) 暂停/恢复语义在 Celery 中需要撤销/重新调度任务，不如 asyncio.Event 直观；(3) 当前策略数量（预计 < 50）不需要分布式任务队列的水平扩展能力；(4) Phase A 快速迭代阶段，asyncio 内建方案零外部依赖，开发/调试效率更高。若未来策略数量增长到数百个且需要跨机器分布执行，可通过新 ADR 迁移到 Celery。

- **B. 事件驱动（WebSocket 行情推送触发）** — 每次行情 tick 到来时评估条件，实现最低延迟的响应。否决理由：(1) 信号生成（signal-service）是拉取模式，不是推送模式；改造为推送需重构 Kronos Data pipeline；(2) 股票级别的 tick 事件量大（A 股 5000+ 只），大部分不在策略关注范围内，事件过滤成本高；(3) 对于分钟级别的策略检查间隔（5 分钟默认），定时轮询已足够，微秒级延迟无实际收益。

### 决策 2：策略状态机 — 双层状态模型

| 维度 | 选型 | 理由 |
|------|------|------|
| 状态模型 | **双层状态：StrategyConfig.status + ExecutorState.status** | 策略配置的 `status` 表示生命周期阶段（`draft` / `active` / `paused` / `stopped` / `archived`），独立于运行时进程状态；执行器的 `ExecutorState.status` 表示运行时状态（`idle` / `running` / `paused` / `stopped`），两者通过 ExecutorManager 保持同步。双层设计解决"重启服务后策略状态丢失"问题——策略配置持久化到存储，执行器状态为运行时重建。 |

**状态转换图**：

```
StrategyConfig.status:
  draft ──[start]──> active ──[pause]──> paused ──[resume]──> active
    │                   │                    │
    │                   └──[stop]──> stopped  └──[stop]──> stopped
    │                                                  │
    └──[delete]──> (removed)          stopped ──[start]──> active

ExecutorState.status (运行时):
  idle ──[start]──> running ──[pause]──> paused ──[resume]──> running
                       │                    │
                       └──[stop]──> stopped  └──[stop]──> stopped
```

**同步规则**：`ExecutorManager.start()` 将策略 `status` 设为 `active`；`pause()` 设为 `paused`；`resume()` 恢复为 `active`；`stop()` 设为 `stopped`。删除策略时（`api_delete_strategy`）先停止执行器再删除配置。

**自动暂停**：日亏损超限时（`daily_loss_pct >= risk_rules.daily_max_loss_pct`），执行器自动调用 `mgr.pause()`，无需人工干预。

**备选方案**：

- **A. 单层状态（仅在 ExecutorState 维护）** — 简单直接。否决理由：重启服务后执行器状态丢失，无法区分"策略从未启动"和"策略之前被暂停"；前端需要展示策略状态，没有持久化状态需要从日志推断，不可靠。

- **B. 引入中间状态（`starting` / `stopping` / `pausing`）** — 更精确反映异步操作的过渡期。否决理由：当前操作（启动/暂停/恢复/停止）是同步的内存操作 + 异步事件设置，过渡期极短（毫秒级），引入中间状态增加状态机复杂度但无实际可观测价值。如果未来执行器启动涉及券商连接（如 xtquant connect）等秒级操作，可通过新 ADR 引入 `starting` 状态。

### 决策 3：策略存储方案 — 内存存储（Phase A），目标 PostgreSQL JSONB

| 维度 | 选型 | 理由 |
|------|------|------|
| Phase A 存储 | **In-memory `StrategyStore` + `threading.Lock`** | `StrategyConfig` 是 dataclass 对象，非 ORM 模型；策略数量少（< 50），重启丢失可接受（Phase A 为开发验证阶段）；零数据库依赖降低迭代成本。 |
| 目标存储 | **PostgreSQL JSONB 列存储策略配置** | `StrategyConfig` 的 `buy_conditions` / `sell_conditions` / `position_rules` / `risk_rules` 都是嵌套结构，JSONB 天然适合；支持 JSONB 路径查询（如 `WHERE config->'risk_rules'->>'daily_max_loss_pct' > '0.05'`）；与现有 PostgreSQL 15-alpine 基础设施一致。否决独立的策略配置表（规范化列）：买入/卖出条件数量可变，需要一对多关联表，查询需多表 JOIN，复杂度高而收益低——这些条件只被策略引擎解析，不会被业务查询条件化利用。 |

**实现细节**（`auto_trading_engine.py:166-205`）：

```python
class StrategyStore:
    def __init__(self):
        self._strategies: dict[str, StrategyConfig] = {}
        self._lock = threading.Lock()
    def create(self, strategy): ...
    def get(self, strategy_id): ...
    def list_all(self): ...
    def update(self, strategy_id, **kwargs): ...
    def delete(self, strategy_id): ...
```

**迁移路径**：当 `StrategyStore.list_all()` 返回策略数超过阈值（如 > 20）或需要跨服务重启持久化时，将 `StrategyStore` 的内部存储从 `dict` 替换为 PostgreSQL JSONB 表，外部 API（`create/get/list_all/update/delete`）保持不变。迁移时增加 Alembic migration + 启动时从 DB 加载到内存缓存（write-through 模式）。

**备选方案**：

- **A. 直接使用 PostgreSQL JSONB（跳过内存阶段）** — 避免未来的迁移成本。否决理由：Phase A 策略引擎频繁迭代（条件字段、规则结构可能变化），内存存储允许快速修改 dataclass 无需数据库 migration；策略数量极少时数据库读写延迟反而高于内存字典查找；开发阶段重启清理旧数据是期望行为，不是 bug。

- **B. SQLite 文件存储** — 单文件零配置数据库。否决理由：项目已有 PostgreSQL（docker-compose），增加 SQLite 引入第二套数据库运维；JSONB 查询是 PostgreSQL 原生能力，SQLite JSON 函数较弱（无 GIN 索引，路径查询效率低）。

### 决策 4：执行模式 — 模拟/实盘统一抽象，前端差异化 UI

| 维度 | 选型 | 理由 |
|------|------|------|
| 交易模式 | **`trade_mode: paper | live`，通过 trade-service BrokerInterface 切换** | 策略引擎不关心底层是 MockBroker 还是 XtquantBroker；所有下单统一调用 `trade-service POST /api/v1/trade/order`，由 trade-service 的 `get_broker()` 工厂根据 TRADE_MODE 选择实现。与 ADR-002 决策 5（同一 BrokerInterface 不同实现）对齐。 |
| 用户确认模式 | **`full_auto`（全自动）和 `semi_auto`（半自动，信号提醒 + 手动确认）** | 前端 AutoTrade 页面提供 `execution_mode` Radio 选择（`full_auto` / `semi_auto`）。当前实现中两种模式共享同一执行引擎，`semi_auto` 模式下仅暂停执行等待用户确认——实际确认 UI 为 Phase B 范围。 |

**实现细节**（`auto_trading_executor.py:34-35`）：

```python
TRADE_SERVICE_URL = os.environ.get("TRADE_SERVICE_URL", "http://localhost:8006")
SIGNAL_SERVICE_URL = os.environ.get("SIGNAL_SERVICE_URL", "http://localhost:8004")
```

策略引擎通过 HTTP 调用 trade-service 和 signal-service，与具体 Broker 实现解耦。交易模式切换时只需更新策略的 `trade_mode` 字段，无需重启执行器。

**备选方案**：

- **A. 策略引擎直接实例化 BrokerInterface（内嵌交易能力）** — 减少 HTTP 调用开销。否决理由：(1) 违反单一职责——策略引擎负责条件评估和调度，交易执行应归 trade-service；(2) 策略引擎需要引入 xtquant SDK 依赖和 Windows 部署约束（见 ADR-002）；(3) 风控网关和审计日志已在 trade-service 层实现，直接调用 Broker 会绕过这些安全机制。

- **B. 单独建立 `full_auto_executor` 和 `semi_auto_executor` 两套引擎** — 两种模式独立优化。否决理由：两种模式的核心逻辑（拉取信号 → 评估条件 → 生成买卖决策）完全相同，差异仅在于下单前是否需要人工确认。共用引擎 + 模式标志（`execution_mode` 字段）保持 DRY，确认 UI 差异由前端处理。

### 决策 5：风控熔断 — 复用 trade-service CircuitBreaker

| 维度 | 选型 | 理由 |
|------|------|------|
| 风控机制 | **复用 trade-service `CircuitBreaker`（`check_daily_loss`）** | trade-service 已实现日亏损熔断器（`services/trade-service/app/circuit_breaker.py`），支持 NORMAL/TRIGGERED 状态 + 按日自动重置 + 手动恢复。策略引擎在每次检查周期开始时调用 `check_daily_loss()`，超限自动 `pause()` 策略。否决策略引擎自建熔断器：逻辑重复，且 trade-service 熔断器已有账户维度的日盈亏跟踪（从交易记录实时计算），策略引擎侧无法准确获取日盈亏总额。 |

**实现细节**（`auto_trading_executor.py:261-278`）：

```python
daily_pnl = account.get("daily_pnl", 0)
daily_loss_pct = abs(daily_pnl) / strategy.capital if daily_pnl < 0 else 0
if daily_loss_pct >= strategy.risk_rules.daily_max_loss_pct:
    state.add_log("WARN", f"日亏损 {daily_loss_pct:.2%} 超过阈值...")
    mgr.pause(strategy.id)  # 自动暂停
    return
```

**多层防护**：
1. **策略级**（strategy-service）：`RiskRule.daily_max_loss_pct`（默认 3%）— 策略引擎检查周期触发，超限自动暂停；
2. **账户级**（trade-service）：`CircuitBreaker._DAILY_LOSS_PCT`（默认 5%）— 在 trade-service 下单前检查，超限拒绝所有实盘订单；
3. **单票级**：`RiskRule.stop_loss_pct`（默认 3%）— 卖出条件中包含 `stop_loss >= 3%`，由条件评估自动触发卖单。

三层防护形成纵深防御：策略级保护单个策略不失控，账户级保护整体账户不爆仓，单票级保护单个持仓不深度套牢。

**备选方案**：

- **A. 策略引擎自建独立的熔断器** — 策略引擎维护自己的日盈亏跟踪。否决理由：(1) 日盈亏的权威来源是 trade-service 的交易记录和账户快照，策略引擎自算的日盈亏与真实数据必然存在偏差（交易延迟、手续费、滑点等）；(2) 重复逻辑，trade-service 已有成熟的 CircuitBreaker 实现（含按日自动重置、手动恢复、状态查询 API）；(3) 策略引擎自建熔断器只在单策略维度生效，而 trade-service 熔断器在账户维度生效——两者互补而非替代。

- **B. 单独的风控微服务** — 独立服务统一管理所有风控规则。否决理由：同 ADR-002 决策 3——增加网络跃点延迟，下单链路不应引入额外外部依赖；当前风控逻辑轻量（几个数值比较），独立微服务过度设计。

## 影响

- **对现有代码**：
  - `strategy-service`：新增 `auto_trading_engine.py`（StrategyConfig dataclass + StrategyStore + 策略生成函数，~380 行）+ `auto_trading_executor.py`（ExecutorState + ExecutorManager + 异步执行循环 + 条件评估 + HTTP 客户端，~630 行）
  - `strategy-service/app/routes.py`：扩展策略 CRUD（`POST /custom`、`GET /list`、`PUT /{id}`、`DELETE /{id}`）+ 启停路由（`POST /{id}/start`、`/pause`、`/resume`、`/stop`）+ 状态查询（`GET /{id}/status`、`GET /{id}/log`），~320 行新增
  - `trade-service`：无修改，策略引擎通过 HTTP 调用其现有 API（`/api/v1/trade/account`、`/positions`、`/order`）
  - `signal-service`：无修改，策略引擎通过 HTTP 调用其现有 API（`/api/v1/signal/analyze/{code}`）
  - `frontend/src/pages/AutoTrade.tsx`：新页面，策略表格 + 创建/编辑 Drawer + 详情 Drawer，~735 行
  - `frontend/src/pages/Strategy.tsx`：新增「量化策略」按钮，从确认方案可一键跳转到 AutoTrade 页面

- **对团队**：
  - 后端开发者需理解 asyncio 协程生命周期（`asyncio.Task` + `Event` 暂停/恢复）和跨服务 HTTP 调用的异步包装（`loop.run_in_executor`）
  - 前端开发者需理解策略状态机（双层状态：策略状态 vs 执行器状态）和两种执行模式（`full_auto` / `semi_auto`）的 UI 差异

- **对成本**：
  - 无新增基础设施费用——asyncio 在现有 FastAPI uvicorn 事件循环内运行，不增加进程数
  - 信号/交易 API 调用频率：每策略每 5 分钟约 (1 + picks_count + positions_count) 次 HTTP 请求。5 只持仓 + 5 只 picks = 约 12 次请求/5 分钟 = ~144 次/小时。均在局域网内通信，延迟 < 10ms
  - 日志内存占用：每策略最多保留 1000 条 ExecutionLogEntry（~500 条旧日志滚动淘汰），单条 ~200 字节，内存 < 200KB/策略

- **对运维**：
  - 新增监控点：
    - 策略执行轮次成功率（`checks_completed / (checks_completed + errors)`，告警阈值 < 95%）
    - 单次检查耗时 p99（告警阈值 > 30s，当前默认间隔 5min）
    - 日亏损自动暂停事件（WARN 日志 + 前端 Badge 告警）
    - signal-service / trade-service HTTP 调用失败率（告警阈值 > 10%）
  - 新增环境变量：`TRADE_SERVICE_URL`（默认 `http://localhost:8006`）、`SIGNAL_SERVICE_URL`（默认 `http://localhost:8004`）

## 本 ADR 不覆盖的决策

- **策略执行结果的持久化存储**（PostgreSQL 迁移）：本 ADR 记录 Phase A 的内存存储决策和迁移目标，具体迁移时机和 schema 设计留给后续 ADR
- **`semi_auto` 模式的人工确认 UI**：当前仅预留 `execution_mode` 字段，确认交互（弹窗/通知/超时自动取消）留给 Phase B
- **策略回测结果的自动集成**：回测验证（backtest-service）与策略引擎的联动（如回测通过后自动激活策略）留给后续 ADR
- **多策略并发执行的资源调度**：当前每个策略独立 `asyncio.Task`，未做优先级/资源配额。若策略数量增长到 50+，需评估 asyncio 事件循环负载
- **策略模板市场/分享**：PRD 未定义，不在本 ADR 范围

## 后续工作

- [ ] backend-dev: 实现半自动模式的确认端点 + 超时自动取消逻辑，预计 1d
- [ ] backend-dev: 实现 PostgreSQL JSONB 策略持久化（Alembic migration + StrategyStore write-through），预计 1d
- [ ] backend-dev: 增加策略执行指标 Prometheus 埋点（`strategy_check_duration_seconds`、`strategy_orders_total`、`strategy_errors_total`），预计 0.5d
- [ ] frontend-dev: 实现半自动模式的确认弹窗 UI（信号提醒 + 确认/拒绝 + 超时倒计时），预计 1.5d
- [ ] tech-lead: 在 CLAUDE.md Tech Stack 表中新增 strategy-service 的 auto_trading_engine / auto_trading_executor 条目

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。新增技术或大版本升级时必填。

**查证基线日期**：2026-06-10

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|------|----------|------------|-------------|----------|----------------------|
| Python asyncio | 3.12+ (CPython stdlib) | 3.12.9 | 无差距 | Active — Python 标准库，随 CPython 发布 | [Python 3.12 docs](https://docs.python.org/3.12/library/asyncio.html) — asyncio 是 Python 3.4+ 标准库，3.12 版本事件循环性能和 TaskGroup 显著改进 |
| FastAPI | 0.136.3（已在用） | 0.136.3 | 无差距 | Active — 2026-05-23 发版 | [GitHub Releases](https://github.com/fastapi/fastapi/releases) — 同 ADR-001 版本查证 |
| PostgreSQL | 15-alpine（已在用） | 17 | 2 个 major 落后 | Active — PG 15 EOL 2027-11 | [docker-compose.yml](https://github.com/rogerluo2016ROL/Kronos/blob/main/docker/docker-compose.yml) — 同 ADR-001/002 版本查证 |
| urllib（HTTP 客户端） | Python 3.12 stdlib | 3.12.9 | 无差距 | Active — Python 标准库 | 策略引擎 HTTP 客户端基于 `urllib.request` + `asyncio.run_in_executor` 异步包装，无第三方 HTTP 库依赖 |

**备选（被否决）技术的版本记录**：

| 选型 | 当时最新版 | 否决原因 |
|------|-----------|---------|
| Celery | 5.6.0 (2026-03) | Phase A 策略数量 < 50，不需要分布式任务队列；引入 Redis + Worker 运维成本高；暂停/恢复语义不如 asyncio.Event 直观 |
| Redis | 7.4.x | 当前架构无需共享缓存/消息队列；若仅为了 Celery 引入 Redis 是杀鸡用牛刀 |
