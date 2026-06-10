# Auto-Trading API 契约文档

> 基于已实现代码反写 (`services/strategy-service/app/`)
> 生成时间：2026-06-10

---

## 1. 概览

Strategy-Service 提供两类核心 API：

| 类别 | 前缀 | 说明 |
|------|------|------|
| 方案管理 (Plan) | `/api/v1/strategy/plans` | 选股方案 CRUD，确认，报告生成 |
| 自动交易策略 (Strategy) | `/api/v1/strategy/` | 策略 CRUD，从方案生成策略，启停执行器 |

---

## 2. 端点总览（22 个端点）

### 2.1 方案管理（10 个端点）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | `POST` | `/api/v1/strategy/plans` | 创建新方案 |
| 2 | `POST` | `/api/v1/strategy/plans/{plan_id}/picks` | 添加标的 |
| 3 | `GET` | `/api/v1/strategy/plans` | 列出所有方案 |
| 4 | `GET` | `/api/v1/strategy/plans/{plan_id}` | 获取方案详情 |
| 5 | `PUT` | `/api/v1/strategy/plans/{plan_id}` | 更新方案 |
| 6 | `DELETE` | `/api/v1/strategy/plans/{plan_id}` | 删除方案 |
| 7 | `POST` | `/api/v1/strategy/plans/{plan_id}/confirm` | 确认方案 |
| 8 | `POST` | `/api/v1/strategy/plans/{plan_id}/optimize` | 优化方案 |
| 9 | `GET` | `/api/v1/strategy/plans/{plan_id}/report` | 生成选股报告 |
| 10 | `GET` | `/api/v1/strategy/templates` | 列出方案模板 |

### 2.2 自动交易策略（12 个端点）

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 11 | `POST` | `/api/v1/strategy/generate-from-scheme/{scheme_id}` | 从方案生成策略 |
| 12 | `POST` | `/api/v1/strategy/custom` | 创建自定义策略 |
| 13 | `GET` | `/api/v1/strategy/list` | 列出所有策略 |
| 14 | `GET` | `/api/v1/strategy/{strategy_id}` | 获取策略详情 |
| 15 | `PUT` | `/api/v1/strategy/{strategy_id}` | 更新策略 |
| 16 | `DELETE` | `/api/v1/strategy/{strategy_id}` | 删除策略 |
| 17 | `POST` | `/api/v1/strategy/{strategy_id}/start` | 启动策略执行 |
| 18 | `POST` | `/api/v1/strategy/{strategy_id}/pause` | 暂停策略执行 |
| 19 | `POST` | `/api/v1/strategy/{strategy_id}/resume` | 恢复策略执行 |
| 20 | `POST` | `/api/v1/strategy/{strategy_id}/stop` | 停止策略执行 |
| 21 | `GET` | `/api/v1/strategy/{strategy_id}/status` | 查询执行状态 |
| 22 | `GET` | `/api/v1/strategy/{strategy_id}/log` | 查询执行日志 |

---

## 3. 端点详细契约

### 3.1 POST /api/v1/strategy/plans -- 创建选股方案

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `name` | string | 否 | `"未命名方案"` | -- | 方案名称 |
| `model_name` | string | 否 | `"all"` | -- | 选股模型 |
| `capital` | float | 否 | `1_000_000` | `ge=100_000` | 初始资金 |
| `max_positions` | int | 否 | `5` | `1..20` | 最大持仓数 |
| `single_max_pct` | float | 否 | `0.2` | `0.05..0.5` | 单票最大仓位比例 |

**Response 200:**

```json
{
  "plan": {
    "id": "PLAN-A1B2C3D4",
    "name": "示例方案",
    "status": "draft",
    "picks_count": 0,
    "capital": 1000000.0,
    "max_positions": 5,
    "created_at": "2026-06-10T12:00:00"
  },
  "message": "方案 PLAN-A1B2C3D4 创建成功"
}
```

---

### 3.2 POST /api/v1/strategy/plans/{plan_id}/picks -- 添加标的

**Path Parameters:** `plan_id: str`

**Request Body:** `list[dict]` -- 标的列表

```json
[
  {"code": "600519", "name": "贵州茅台", "price": 1800.0, "score": 85, "grade": "BUY"},
  {"code": "000858", "name": "五粮液", "price": 150.0, "score": 78, "grade": "BUY"}
]
```

每个 pick dict 的字段由前端自由定义，至少需包含 `code`。

**Response 200:**

```json
{
  "plan_id": "PLAN-A1B2C3D4",
  "picks_count": 2,
  "message": "已添加 2 只标的"
}
```

**Error 404:** 方案不存在

---

### 3.3 GET /api/v1/strategy/plans -- 列出所有方案

**Response 200:**

```json
{
  "plans": [
    {
      "id": "PLAN-A1B2C3D4",
      "name": "示例方案",
      "status": "draft",
      "picks_count": 5,
      "model_name": "all",
      "capital": 1000000.0,
      "created_at": "2026-06-10T12:00:00"
    }
  ],
  "total": 1
}
```

---

### 3.4 GET /api/v1/strategy/plans/{plan_id} -- 获取方案详情

**Response 200:**

```json
{
  "id": "PLAN-A1B2C3D4",
  "name": "示例方案",
  "status": "draft",
  "model_name": "all",
  "capital": 1000000.0,
  "max_positions": 5,
  "single_max_pct": 0.2,
  "picks": [
    {"code": "600519", "name": "贵州茅台", "price": 1800.0, "score": 85, "grade": "BUY"}
  ],
  "created_at": "2026-06-10T12:00:00",
  "updated_at": "2026-06-10T12:30:00"
}
```

**Error 404:** 方案不存在

---

### 3.5 PUT /api/v1/strategy/plans/{plan_id} -- 更新方案

**Query Parameters:** `name: str | None`, `status: str | None`

其中 `status` 仅允许 `"draft"`, `"confirmed"`, `"archived"`。

**Response 200:**

```json
{
  "plan_id": "PLAN-A1B2C3D4",
  "updates": {"name": "新名称"},
  "status": "ok"
}
```

**Error 400:** 非法 status 值
**Error 404:** 方案不存在

---

### 3.6 DELETE /api/v1/strategy/plans/{plan_id} -- 删除方案

**Response 200:** `{"plan_id": "...", "status": "deleted"}`
**Error 404:** 方案不存在

---

### 3.7 POST /api/v1/strategy/plans/{plan_id}/confirm -- 确认方案

将方案状态从 `draft` 变更为 `confirmed`。

**Response 200:**

```json
{
  "plan_id": "PLAN-A1B2C3D4",
  "status": "confirmed",
  "picks_count": 5,
  "message": "方案已确认: 5 只标的"
}
```

**Error 404:** 方案不存在

---

### 3.8 POST /api/v1/strategy/plans/{plan_id}/optimize -- 优化方案

使用 Kronos 预测对方案标的进行优化（当前为占位实现）。

**Response 200:**

```json
{
  "plan_id": "PLAN-A1B2C3D4",
  "status": "optimized",
  "message": "优化完成 (Kronos预测对接中)"
}
```

**Error 404:** 方案不存在

---

### 3.9 GET /api/v1/strategy/plans/{plan_id}/report -- 生成选股报告

**前置条件:** plan.status 必须为 `"confirmed"`

**Response 200:** (结构较复杂，核心字段如下)

```json
{
  "title": "选股报告 — 示例方案",
  "generated_at": "2026-06-10T12:00:00",
  "plan": {
    "id": "PLAN-A1B2C3D4",
    "name": "示例方案",
    "model": "all",
    "capital": 1000000.0,
    "max_positions": 5,
    "single_max_pct": 0.2
  },
  "market_analysis": {
    "sentiment_cycle": "情绪上升期",
    "sector_rotation": "科技+消费主线",
    "index_status": "上证指数多头排列"
  },
  "picks": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "price": 1800.0,
      "score": 85,
      "grade": "BUY",
      "tech_analysis": "均线多头排列，MACD金叉",
      "capital_analysis": "主力净流入，北向增持",
      "fundamental_analysis": "PE合理区间，ROE优秀",
      "kronos_prediction": "预测30日上涨趋势",
      "operation": {
        "entry_price": 1710.0,
        "stop_loss": 1656.0,
        "target_price": 2070.0,
        "position_pct": 4.0,
        "hold_period": "1-4周"
      }
    }
  ],
  "quant_strategy": {
    "buy_conditions": ["信号强度 ≥ 🟡买入", "Kronos预测收益 > 8%", "因子共振数 ≥ 2", "单票仓位上限 20%"],
    "sell_conditions": ["信号强度 ≤ 🔴卖出", "止损: 浮亏 ≥ 3%", "止盈: 浮盈 ≥ 15%"],
    "risk_rules": ["最大持仓数 5 只", "日最大亏损 3% 暂停交易", "总仓位上限 80%"],
    "execution_mode": "半自动(信号提醒+手动确认)"
  },
  "risk_warnings": [
    "本报告仅供参考，不构成投资建议",
    "量化策略存在失效风险",
    "请结合个人风险承受能力独立决策"
  ]
}
```

**Error 400:** 方案未确认 (`"请先确认方案后再生成报告"`)
**Error 404:** 方案不存在

---

### 3.10 GET /api/v1/strategy/templates -- 列出方案模板

**Response 200:**

```json
{
  "templates": [
    {"id": "aggressive", "name": "激进型", "risk": "high", "max_positions": 3, "single_max": 0.20},
    {"id": "balanced", "name": "均衡型", "risk": "medium", "max_positions": 5, "single_max": 0.12},
    {"id": "conservative", "name": "保守型", "risk": "low", "max_positions": 8, "single_max": 0.08}
  ]
}
```

---

### 3.11 POST /api/v1/strategy/generate-from-scheme/{scheme_id} -- 从方案生成策略

**Path Parameters:** `scheme_id: str`

**前置条件:** 方案存在且 status 为 `"confirmed"` 或 `"active"`

**默认注入条件（来自 `DEFAULT_BUY_CONDITIONS` / `DEFAULT_SELL_CONDITIONS`）：**

| 类型 | field | operator | threshold | 说明 |
|------|-------|----------|-----------|------|
| BUY | `signal_strength` | `>=` | 60 | 信号强度 >= BUY(60分) |
| BUY | `kronos_return` | `>` | 8.0 | Kronos 预测收益 > 8% |
| BUY | `factor_resonance` | `>=` | 2 | 因子共振数 >= 2 |
| SELL | `signal_strength` | `<=` | 20 | 信号强度 <= SELL(20分) |
| SELL | `kronos_trend` | `==` | 1 | Kronos 转为下跌趋势 |
| SELL | `stop_loss` | `>=` | 3.0 | 止损: 浮亏 >= 3% |
| SELL | `take_profit` | `>=` | 15.0 | 止盈: 浮盈 >= 15% |

**Response 200:**

```json
{
  "strategy": {
    "id": "STR-A1B2C3D4",
    "name": "自动策略-示例方案",
    "description": "由方案 PLAN-A1B2C3D4 自动生成。模型: all",
    "status": "draft",
    "source_type": "scheme",
    "source_scheme_id": "PLAN-A1B2C3D4",
    "buy_conditions": [
      {"field": "signal_strength", "operator": ">=", "threshold": 60.0, "description": "信号强度 >= BUY (60分)"}
    ],
    "sell_conditions": [
      {"field": "signal_strength", "operator": "<=", "threshold": 20.0, "description": "信号强度 <= SELL (20分)"}
    ],
    "position_rules": {
      "max_positions": 5,
      "single_max_pct": 0.2,
      "total_position_cap_pct": 0.8
    },
    "risk_rules": {
      "daily_max_loss_pct": 0.03,
      "stop_loss_pct": 0.03,
      "take_profit_pct": 0.15,
      "trailing_stop_pct": 0.0
    },
    "trade_mode": "paper",
    "check_interval_sec": 300,
    "capital": 1000000.0,
    "picks_count": 5,
    "created_at": "2026-06-10T12:00:00",
    "updated_at": "2026-06-10T12:00:00"
  },
  "message": "策略 STR-A1B2C3D4 已从方案 PLAN-A1B2C3D4 生成"
}
```

**Error 400:** 方案不存在 或 方案状态非法（需 confirmed/active）

---

### 3.12 POST /api/v1/strategy/custom -- 创建自定义策略

**Request Body (JSON):** `CustomStrategyRequest`

```json
{
  "name": "我的自定义策略",
  "description": "基于技术指标的自定义策略",
  "buy_conditions": [
    {"field": "signal_strength", "operator": ">=", "threshold": 70.0, "description": "信号强度 >= 70"}
  ],
  "sell_conditions": [
    {"field": "stop_loss", "operator": ">=", "threshold": 5.0, "description": "止损5%"}
  ],
  "position_rules": {
    "max_positions": 3,
    "single_max_pct": 0.25,
    "total_position_cap_pct": 0.75
  },
  "risk_rules": {
    "daily_max_loss_pct": 0.05,
    "stop_loss_pct": 0.05,
    "take_profit_pct": 0.20,
    "trailing_stop_pct": 0.03
  },
  "trade_mode": "paper",
  "check_interval_sec": 600,
  "capital": 500000.0,
  "picks": [
    {"code": "600519", "name": "贵州茅台", "price": 1800.0}
  ]
}
```

**Request Schema -- `CustomStrategyRequest` (Pydantic):**

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `name` | string | **是** | -- | `1..100` 字符 | 策略名称 |
| `description` | string | 否 | `""` | -- | 策略描述 |
| `buy_conditions` | list[dict] | 否 | `[]` | -- | 买入条件，每个 dict: `{field, operator, threshold, description}` |
| `sell_conditions` | list[dict] | 否 | `[]` | -- | 卖出条件，格式同上 |
| `position_rules` | dict/None | 否 | `null` | -- | `{max_positions, single_max_pct, total_position_cap_pct}` |
| `risk_rules` | dict/None | 否 | `null` | -- | `{daily_max_loss_pct, stop_loss_pct, take_profit_pct, trailing_stop_pct}` |
| `trade_mode` | string | 否 | `"paper"` | `"paper"` 或 `"live"` | 交易模式 |
| `check_interval_sec` | int | 否 | `300` | `30..3600` | 检查间隔 |
| `capital` | float | 否 | `1_000_000` | `ge=100_000` | 初始资金 |
| `picks` | list[dict] | 否 | `[]` | -- | 标的列表 |

**当 `buy_conditions` / `sell_conditions` / `position_rules` / `risk_rules` 为空时，使用默认值。**

**Response 200:**

```json
{
  "strategy": { /* StrategyConfig.to_dict() 同上 */ },
  "message": "自定义策略 STR-A1B2C3D4 创建成功"
}
```

**Error 400:** 参数校验失败

---

### 3.13 GET /api/v1/strategy/list -- 列出所有策略

**Response 200:**

```json
{
  "strategies": [ /* StrategyConfig.to_dict() 列表 */ ],
  "total": 3
}
```

---

### 3.14 GET /api/v1/strategy/{strategy_id} -- 获取策略详情

**Response 200:** `StrategyConfig.to_dict()` (同 3.11 中的 `strategy` 字段)

**Error 404:** 策略不存在

---

### 3.15 PUT /api/v1/strategy/{strategy_id} -- 更新策略

**Request Body (JSON):** `StrategyUpdateRequest`

所有字段均为可选（`None` 表示不更新）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string/None | 否 | `1..100` 字符 |
| `description` | string/None | 否 | -- |
| `buy_conditions` | list[dict]/None | 否 | -- |
| `sell_conditions` | list[dict]/None | 否 | -- |
| `position_rules` | dict/None | 否 | -- |
| `risk_rules` | dict/None | 否 | -- |
| `trade_mode` | string/None | 否 | `"paper"` 或 `"live"` |
| `check_interval_sec` | int/None | 否 | `30..3600` |
| `capital` | float/None | 否 | `ge=100_000` |
| `picks` | list[dict]/None | 否 | -- |

**Response 200:**

```json
{
  "strategy": { /* 更新后的 StrategyConfig.to_dict() */ },
  "message": "策略已更新"
}
```

**Error 404:** 策略不存在

---

### 3.16 DELETE /api/v1/strategy/{strategy_id} -- 删除策略

自动停止正在运行的执行器（如果存在）。

**Response 200:** `{"strategy_id": "...", "status": "deleted"}`
**Error 404:** 策略不存在

---

### 3.17 POST /api/v1/strategy/{strategy_id}/start -- 启动策略执行

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `mode` | string | 否 | `"paper"` | `"paper"` 或 `"live"` |

启动后策略状态从 `draft`/`paused` 变为 `active`；执行器开始按 `check_interval_sec` 周期运行条件检查循环。

**内部行为:** `run_strategy()` 会覆盖 strategy 的 `trade_mode`（如果 mode 参数指定了 paper/live）。

**Response 200:**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "running",
  "started_at": "2026-06-10T12:00:00+00:00",
  "trade_mode": "paper",
  "message": "策略 STR-A1B2C3D4 已启动"
}
```

**Error 400:** 策略不存在 或 策略已在运行

---

### 3.18 POST /api/v1/strategy/{strategy_id}/pause -- 暂停策略执行

**前置条件:** 执行器状态为 `"running"`

暂停后策略状态变为 `"paused"`，执行循环挂起（通过 `asyncio.Event` 实现）。

**Response 200:**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "paused",
  "message": "策略已暂停"
}
```

**Error 400:** 执行器未找到 或 状态不是 `running`

---

### 3.19 POST /api/v1/strategy/{strategy_id}/resume -- 恢复策略执行

**前置条件:** 执行器状态为 `"paused"`

恢复后策略状态变为 `"active"`，执行循环继续。

**Response 200:**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "running",
  "message": "策略已恢复"
}
```

**Error 400:** 执行器未找到 或 状态不是 `paused`

---

### 3.20 POST /api/v1/strategy/{strategy_id}/stop -- 停止策略执行

**前置条件:** 执行器状态为 `running` 或 `paused`

停止后策略状态变为 `"stopped"`，执行循环退出（通过 `asyncio.Event` 信号）。

**Response 200:**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "stopped",
  "stopped_at": "2026-06-10T13:00:00+00:00",
  "message": "策略已终止"
}
```

**Error 400:** 执行器未找到 或 已停止

---

### 3.21 GET /api/v1/strategy/{strategy_id}/status -- 查询执行状态

如果策略存在但执行器未启动，返回策略的静态 status 和 `executor_running: false`。

**Response 200 (运行中):**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "running",
  "started_at": "2026-06-10T12:00:00+00:00",
  "stopped_at": null,
  "last_check_at": "2026-06-10T12:05:00+00:00",
  "next_check_at": "2026-06-10T12:10:00+00:00",
  "checks_completed": 6,
  "orders_placed": 2,
  "errors": 0,
  "trade_mode": "paper",
  "check_interval_sec": 300
}
```

**Response 200 (未启动):**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "status": "draft",
  "executor_running": false
}
```

**Error 404:** 策略不存在

---

### 3.22 GET /api/v1/strategy/{strategy_id}/log -- 查询执行日志

**Query Parameters:**

| 参数 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|------|------|------|--------|------|------|
| `limit` | int | 否 | `50` | `10..500` | 返回最多 N 条 |
| `level` | string/None | 否 | `null` | `"INFO"`, `"WARN"`, `"ERROR"`, `"BUY"`, `"SELL"` | 按级别过滤 |

**Response 200:**

```json
{
  "strategy_id": "STR-A1B2C3D4",
  "total_logs": 150,
  "filtered": 3,
  "logs": [
    {
      "timestamp": "2026-06-10T12:05:00+00:00",
      "level": "BUY",
      "message": "触发买入条件: 600519 — 全部条件满足: 信号强度 >= BUY (60分), Kronos预测收益 > 8%",
      "details": {
        "code": "600519",
        "reason": "全部条件满足: 信号强度 >= BUY (60分), Kronos预测收益 > 8%",
        "price": 1710.0,
        "volume": 2100
      }
    }
  ]
}
```

**Error 404:** 执行器未找到（策略可能未启动）

---

## 4. StrategyConfig 完整字段定义

### 4.1 dataclass 定义

```python
@dataclass
class StrategyConfig:
    id: str                        # "STR-XXXXXXXX" (8位 hex)
    name: str                      # 策略名称 (1-100字符)
    description: str = ""          # 策略描述
    status: str = "draft"          # draft | active | paused | stopped | archived

    # 来源
    source_type: str = "custom"    # "scheme" | "custom"
    source_scheme_id: str = ""     # 若来自方案，记录方案 ID

    # 条件
    buy_conditions: list[BuyCondition]   # 买入触发条件
    sell_conditions: list[SellCondition] # 卖出触发条件

    # 规则
    position_rules: PositionRule    # 仓位管理规则
    risk_rules: RiskRule            # 风控规则

    # 运行时
    trade_mode: str = "paper"       # paper | live
    check_interval_sec: int = 300   # 检查间隔(秒)，范围 30-3600
    capital: float = 1_000_000       # 初始资金

    # 标的
    picks: list[dict]               # 标的列表 [{code, name, price, score, grade, ...}]

    # 元数据
    created_at: str = ""            # ISO 8601
    updated_at: str = ""            # ISO 8601
```

### 4.2 BuyCondition

```python
@dataclass
class BuyCondition:
    field: str          # 字段名: signal_strength | kronos_return | factor_resonance | ...
    operator: str       # 比较符: >= | <= | > | < | == | !=
    threshold: float    # 阈值
    description: str    # 人类可读说明
```

### 4.3 SellCondition

```python
@dataclass
class SellCondition:
    field: str          # 字段名: signal_strength | kronos_trend | stop_loss | take_profit | ...
    operator: str       # 比较符: >= | <= | > | < | == | !=
    threshold: float    # 阈值
    description: str    # 人类可读说明
```

### 4.4 PositionRule

```python
@dataclass
class PositionRule:
    max_positions: int = 5          # 最大同时持仓数
    single_max_pct: float = 0.20    # 单票最大仓位比例
    total_position_cap_pct: float = 0.80  # 总仓位上限比例
```

### 4.5 RiskRule

```python
@dataclass
class RiskRule:
    daily_max_loss_pct: float = 0.03    # 日亏损上限（触发自动暂停）
    stop_loss_pct: float = 0.03         # 单票止损比例
    take_profit_pct: float = 0.15       # 单票止盈比例
    trailing_stop_pct: float = 0.0      # 移动止损（0 = 禁用）
```

### 4.6 to_dict() 序列化

`StrategyConfig.to_dict()` 将 `picks` 字段折叠为 `picks_count`（不返回完整标的列表到策略详情）。完整的 picks 需要通过方案 API 获取。

---

## 5. 策略状态机

### 5.1 状态定义

```
draft → active → paused → stopped
  ↓                ↑ ↓       ↑
  └────────────────┴─────────┘
  (可以从 draft 直接 start → active)
```

| 状态 | 含义 | 进入方式 |
|------|------|----------|
| `draft` | 草稿，创建后初始状态 | `generate_from_scheme()` 或 `create_custom_strategy()` |
| `active` | 运行中，执行循环活跃 | `POST /{id}/start` 或 `POST /{id}/resume` |
| `paused` | 已暂停，执行循环挂起（保留状态） | `POST /{id}/pause` 或日亏损超限自动暂停 |
| `stopped` | 已终止，执行循环退出 | `POST /{id}/stop` 或在运行中删除策略 |
| `archived` | 已归档（代码定义但路由未实现入口） | -- |

### 5.2 允许的状态转换

| 当前状态 | 允许操作 | 目标状态 |
|----------|----------|----------|
| `draft` | start | `active` |
| `active` | pause | `paused` |
| `active` | stop | `stopped` |
| `active` | delete (自动 stop) | `stopped` → deleted |
| `paused` | resume | `active` |
| `paused` | stop | `stopped` |
| `paused` | delete (自动 stop) | `stopped` → deleted |
| `stopped` | -- | (终态) |

### 5.3 自动暂停

执行循环在每个检查周期计算日亏损比例 `abs(daily_pnl) / capital`，若超过 `risk_rules.daily_max_loss_pct`：
1. 记录 WARN 日志
2. 自动调用 `mgr.pause()` → 策略变为 `paused`
3. 后续不再执行交易直到手动 resume

---

## 6. 策略执行日志格式

### 6.1 ExecutionLogEntry

```python
@dataclass
class ExecutionLogEntry:
    timestamp: str      # ISO 8601 (UTC)
    level: str          # INFO | WARN | ERROR | BUY | SELL
    message: str        # 人类可读日志消息
    details: dict       # 结构化详情 (可为空)
```

### 6.2 日志级别语义

| 级别 | 含义 | 典型场景 |
|------|------|----------|
| `INFO` | 常规信息 | 检查开始、检查完成、仓位上限提示 |
| `WARN` | 警告 | 日亏损超限、价格获取失败、计算量<100 |
| `ERROR` | 异常 | 执行循环中抛出的未捕获异常 |
| `BUY` | 买入事件 | 条件满足触发买入、订单提交成功 |
| `SELL` | 卖出事件 | 条件满足触发卖出、订单提交成功 |

### 6.3 日志容量

执行器维护最近 1000 条日志，超过后保留最后 500 条。

### 6.4 关键日志消息示例

```
"策略执行器已启动 (mode=paper)"
"策略执行已暂停"
"策略执行已恢复"
"策略执行已终止"
"开始执行检查"                     details: {"picks_count": 5}
"日亏损 4.50% 超过阈值 3.00%，跳过本次交易"  details: {"daily_pnl": -45000, "daily_loss_pct": 0.045}
"日亏损超限 — 自动暂停策略执行"
"总仓位 85.0% 已达上限 80.0%"
"持仓数 5 已达上限 5"
"触发买入条件: 600519 — 全部条件满足: ..."  details: {"code": "600519", "reason": "...", "price": 1710.0, "volume": 2100}
"买单已提交: 600519 — order_id=ORD-001"    details: {"code": "600519", "order_id": "ORD-001"}
"触发卖出条件: 600519 — 止损: 浮亏 >= 3%"   details: {"code": "600519", "reason": "...", "pnl_pct": -3.5}
"卖单已提交: 600519 — order_id=ORD-002"    details: {"code": "600519", "order_id": "ORD-002"}
"无法获取 600519 价格，跳过买入"             details: {"code": "600519"}
"600519 计算股数 50 < 100，跳过"            details: {"code": "600519"}
"执行异常: connection timeout"              details: {"error": "connection timeout"}
"检查完成 (第 6 轮)"
```

---

## 7. 与 trade-service 的调用契约

### 7.1 服务发现

策略执行器通过环境变量发现依赖服务：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `TRADE_SERVICE_URL` | `http://localhost:8006` | 交易服务地址 |
| `SIGNAL_SERVICE_URL` | `http://localhost:8004` | 信号服务地址 |

### 7.2 Trade-Service 调用清单

执行器在每个检查周期调用以下 trade-service 端点：

#### 7.2.1 GET /api/v1/trade/positions

```
GET {TRADE_SERVICE_URL}/api/v1/trade/positions?trade_mode={paper|live}
```

**使用方:** `_fetch_positions(trade_mode)`

**期望响应格式:**

```json
{
  "trade_mode": "paper",
  "positions": [
    {
      "code": "600519",
      "volume": 2100,
      "avg_cost": 1710.00,
      "market_value": 3780000.00,
      "pnl": 18900.00,
      "pnl_pct": 0.53
    }
  ]
}
```

**执行器消费字段:** `code`, `volume`, `market_value`, `pnl_pct`

#### 7.2.2 GET /api/v1/trade/account

```
GET {TRADE_SERVICE_URL}/api/v1/trade/account?trade_mode={paper|live}
```

**使用方:** `_fetch_account(trade_mode)`

**期望响应格式:**

```json
{
  "trade_mode": "paper",
  "total_capital": 1000000.00,
  "available": 622000.00,
  "market_value": 378000.00,
  "total_pnl": 18900.00,
  "daily_pnl": 5200.00
}
```

**执行器消费字段:** `daily_pnl` (用于日亏损熔断计算)

#### 7.2.3 POST /api/v1/trade/order

```
POST {TRADE_SERVICE_URL}/api/v1/trade/order?code={code}&direction={BUY|SELL}&price={price}&volume={volume}&trade_mode={paper|live}
```

**使用方:** `_place_order(symbol, direction, volume, trade_mode, price)`

**Query Parameters:**

| 参数 | 类型 | 说明 |
|------|------|------|
| `code` | string | 股票代码 |
| `direction` | string | `BUY` 或 `SELL` |
| `price` | float | 委托价格 (可为 0，含义见 trade-service) |
| `volume` | int | 委托数量 (股) |
| `trade_mode` | string | `paper` 或 `live` |

**期望响应格式:**

```json
{
  "order_id": "ORD-001",
  "broker_order_id": "XTP-12345",
  "code": "600519",
  "direction": "BUY",
  "price": 1710.00,
  "volume": 2100,
  "status": "FILLED",
  "message": "filled (paper)",
  "risk_check": null
}
```

**执行器消费字段:** `order_id`

### 7.3 Signal-Service 调用

#### 7.3.1 GET /api/v1/signal/analyze/{code}

```
GET {SIGNAL_SERVICE_URL}/api/v1/signal/analyze/{code}
```

**使用方:** `_fetch_signal(code)`

**期望响应格式（执行器消费的关键字段）:**

```json
{
  "code": "600519",
  "signal": {
    "level": "BUY",
    "icon": "🟡",
    "score": 72.5
  },
  "components": {
    "kronos_confidence": {"score": 65.0, "weight": 0.30},
    "factor_resonance": {"score": 72.5, "weight": 0.30, "detail": {...}}
  }
}
```

**执行器字段映射 (BuyCondition evaluation):**

| condition.field | 解析路径 |
|-----------------|----------|
| `signal_strength` | `signal.score` |
| `kronos_return` | `components.kronos_confidence.score` |
| `factor_resonance` | `components.factor_resonance.score` |

**执行器字段映射 (SellCondition evaluation):**

| condition.field | 解析来源 |
|-----------------|----------|
| `signal_strength` | `signal.score` |
| `kronos_trend` | 如果 `signal["kronos_trend"]` 存在则用其值；否则 fallback 到 `components.kronos_confidence.score`，< 50 视为趋势=1(下跌) |
| `stop_loss` | 从 position 数据计算：`abs(pnl_pct)` 当 `pnl_pct < 0` |
| `take_profit` | 从 position 数据计算：`pnl_pct` 当 `pnl_pct > 0` |

### 7.4 HTTP 调用实现细节

- 使用 `urllib.request` (同步) + `loop.run_in_executor` (异步包装)
- 默认超时 10 秒
- 所有 HTTP 错误被捕获并返回 `{"error": "..."}` 字典，不向上层抛出异常
- trade-service 返回 `HTTP 400 (RISK_REJECT)` 或 `HTTP 409 (CIRCUIT_BREAKER_OPEN)` 时，执行器将其视为普通错误记录到日志，不中断循环

---

## 8. 条件评估逻辑

### 8.1 买入条件评估

```python
_evaluate_buy_conditions(conditions, signal) -> (should_buy: bool, reason: str)
```

- 所有条件必须**同时满足** (AND 逻辑)
- 若 `conditions` 为空列表，返回 `(True, "无条件买入")`
- 不满足时返回哪些条件失败了

### 8.2 卖出条件评估

```python
_evaluate_sell_conditions(conditions, signal, position) -> (should_sell: bool, reason: str)
```

- 任一条件满足即触发卖出 (OR 逻辑)
- 卖出条件的上下文合并了 signal 数据 + position 数据（`pnl_pct`, `stop_loss`, `take_profit`）
- 若 `conditions` 为空列表，返回 `(False, "")`
- `kronos_trend` 字段有特殊处理逻辑（见 7.3.1）

### 8.3 仓位计算

```python
position_pct = single_max_pct / max_positions      # 单票仓位比例
entry_price = pick.entry_price or pick.price or signal.price  # 优先使用方案中的入场价
volume = int((capital * position_pct) / entry_price)          # 计算股数
volume = (volume // 100) * 100                                # 取整到整手(100股)
```

- 若 `volume < 100`，跳过该标的（记录 WARN）
- 若 `entry_price <= 0`，跳过该标的（记录 WARN）

---

## 9. Plan 模型 (方案)

```python
@dataclass
class Plan:
    id: str                        # "PLAN-XXXXXXXX" (8位 hex)
    name: str                      # 方案名称
    status: str                    # draft | predicting | backtesting | confirmed | active | archived
    picks: list[dict]              # 标的列表
    model_name: str                # 选股模型名称
    capital: float = 1_000_000     # 初始资金
    max_positions: int = 5         # 最大持仓数
    single_max_pct: float = 0.2    # 单票最大仓位比例
    created_at: str = ""           # ISO 8601
    updated_at: str = ""           # ISO 8601
```

---

## 10. 存储实现说明

### 10.1 StrategyStore (策略存储)

- **实现:** 内存字典 `dict[str, StrategyConfig]` + `threading.Lock`
- **持久化:** 无（当前仅在内存中）
- **容量:** 无限制
- **线程安全:** 是（所有读写操作持有锁）

### 10.2 ExecutorManager (执行器管理)

- **实现:** 内存字典 `dict[str, ExecutorState]` + `threading.Lock`
- **单例:** `_executor_manager` 模块级单例
- **生命周期:** 每个策略最多一个 ExecutorState；stop 后不从字典中移除（保留日志以查询）

### 10.3 PlanStore (方案存储)

- **实现:** 内存字典 + `threading.Lock`
- **持久化:** 无

---

## 11. 开放问题

### Q1: 内存存储 vs 持久化

当前 StrategyStore、ExecutorManager、PlanStore 全部为内存存储，服务重启后所有数据丢失。对于生产环境，需要：
- 策略/方案持久化到 PostgreSQL（已有 alembic 配置，但未见 strategy/plan 表迁移）
- 执行器状态、日志同样面临丢失问题
- 是否需要重启后自动恢复之前运行的策略？

### Q2: 执行器与策略更新的竞态条件

`PUT /{strategy_id}` 允许在策略运行期间修改 buy_conditions、sell_conditions、position_rules 等字段。当前实现中，执行循环持有的是启动时的 `strategy` 对象引用。`StrategyStore.update()` 通过 `setattr` 直接修改该对象，这意味着运行中的执行器会"看到"更新后的条件。这是有意设计还是未预期的副作用？是否需要版本号或快照机制？

### Q3: 多实例部署的信号重复

当前 ExecutorManager 是进程内单例。如果 strategy-service 水平扩展为多个实例，同一个策略可能被多个实例同时启动执行，导致重复下单。需要：
- 分布式锁（如 Redis）确保同一策略只有一个执行器实例
- 或者将执行器抽取为独立的 worker 服务

### Q4: trade-mode=live 的完整链路

`run_strategy()` 在 start 时接受 `mode` 参数并覆盖策略的 `trade_mode`。执行器将 `trade_mode` 原样传递给 trade-service 的 `trade_mode` 查询参数。但在 trade-service 侧，`POST /order` 的 `trade_mode` 参数仅影响 broker 选择，而 `GET /positions` 和 `GET /account` 也依赖此参数。当前 trade-service 的 live 模式需要先通过 `POST /broker/connect` 建立连接。执行器启动前是否需要校验 live broker 连接状态？

### Q5: 条件字段名与信号响应结构的契约耦合

执行器的 `_check_condition()` 中 hard-code 了字段映射 `{"signal_strength": "signal.score", "kronos_return": "components.kronos_confidence.score", ...}`。如果 signal-service 的响应结构发生变化（例如 `components.kronos_confidence` 重命名），执行器将静默失败（fallback 到 0 值）。是否需要将字段映射抽到策略配置中，或建立版本化的信号 schema？

---

## 附录 A: 错误码汇总

| HTTP 状态码 | 典型错误信息 | 触发场景 |
|-------------|-------------|----------|
| 400 | `方案状态必须为 confirmed 或 active` | 从未确认的方案生成策略 |
| 400 | `策略已在运行中` | 重复启动 |
| 400 | `执行器状态为 stopped，无法暂停` | 非法状态转换 |
| 400 | `Invalid status: xxx` | 方案更新时传入非法状态 |
| 400 | validation error | Pydantic 请求体校验失败 |
| 404 | `方案不存在` / `策略不存在` / `执行器未找到` | 资源不存在 |
| 503 | (trade-service) `BROKER_NOT_CONNECTED` | live 模式下未连接券商 |

---

## 附录 B: 环境变量参考

| 变量 | 服务 | 默认值 | 说明 |
|------|------|--------|------|
| `TRADE_SERVICE_URL` | strategy-service | `http://localhost:8006` | 交易服务基地址 |
| `SIGNAL_SERVICE_URL` | strategy-service | `http://localhost:8004` | 信号服务基地址 |
| `TRADE_MODE` | trade-service | `paper` | 全局交易模式 |
| `QMT_USERDATA_PATH` | trade-service | `""` | 迅投 QMT userdata 路径 |
| `BROKER_HEARTBEAT_INTERVAL_SEC` | trade-service | `30` | 券商心跳间隔 |
| `BROKER_RECONNECT_MAX` | trade-service | `5` | 券商重连最大次数 |
