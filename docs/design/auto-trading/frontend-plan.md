# 量化自动交易 -- 前端方案文档

> 基于已实现代码反写。日期：2026-06-10。

---

## 1. 页面架构

量化自动交易功能分布在两个页面中：

| 页面 | 路由 | 文件 | 职责 |
|------|------|------|------|
| 方案管理 (Strategy) | `/strategy` | `frontend/src/pages/Strategy.tsx` | 方案生命周期管理 + 生成量化策略入口 |
| 量化交易 (AutoTrade) | `/auto-trade` | `frontend/src/pages/AutoTrade.tsx` | 策略 CRUD + 编辑器 + 监控面板 |

### 1.1 路由注册 (App.tsx)

```tsx
// 侧边栏菜单项
{ key: '/strategy',    icon: <BulbOutlined />,  label: '方案管理', roles: ['admin','internal_analyst','external_analyst','user'] },
{ key: '/auto-trade',  icon: <RobotOutlined />, label: '量化交易', roles: ['admin','internal_analyst','user'] },

// 路由映射
{ path: '/strategy',   element: <Strategy />,   roles: [...] },
{ path: '/auto-trade', element: <AutoTrade />, roles: ['admin','internal_analyst','user'] },
```

- 方案管理对所有角色开放；量化交易仅对 `admin`、`internal_analyst`、`user` 开放（`external_analyst` 不可见）。
- 两个页面通过 React Router 受 `ProtectedRoute` 包裹，校验角色权限。
- 页面跳转：Strategy 页面"生成量化策略"成功后调用 `navigate('/auto-trade')`。

### 1.2 布局框架

沿用 `App.tsx` 的 Ant Design Layout 套件：
- 固定左侧 Sider（256px / 收起 80px），带 `StockOutlined` Logo + "速赢AI" 品牌名。
- 右侧 `Layout` 包含 sticky Header（48px）+ Content（margin: 16px）+ Footer。
- 页面内容区使用 `margin: 16px` 外边距，内容直接以 `<div>` 包裹，不额外嵌套 Layout。

---

## 2. 组件树

### 2.1 Strategy 页面组件树

```
Strategy
├── Typography.Title ("方案管理")
├── Steps (方案生命周期 6 步条)
│    选股 → 预方案 → 预测验证 → 回测验证 → 确认方案 → 执行交易
├── Card (方案列表)
│   └── Table
│       ├── 方案ID (code 样式)
│       ├── 名称
│       ├── 状态 (Tag: draft=blue, confirmed=green, active=red, archived=default)
│       ├── 标的数
│       ├── 资金 (万元)
│       ├── 创建时间
│       └── 操作按钮组
│           ├── 查看 → Modal (方案详情 Descriptions)
│           ├── 确认 (draft 状态)
│           ├── 报告 (confirmed 状态) → Modal (选股报告)
│           ├── 回测 (confirmed 状态)
│           ├── 量化策略 (confirmed 状态) → 跳转 AutoTrade
│           └── 删除
├── Modal (方案详情)
│   └── Descriptions (方案ID/名称/状态/模型/资金/最大持仓/标的列表)
└── Modal (选股报告)
    ├── Descriptions (方案/模型/资金/最大持仓)
    ├── List (推荐标的: 代码/名称/评级/入场价/止损/目标/仓位)
    ├── Descriptions (量化策略: 买入条件/卖出条件/执行模式)
    └── Tags (风险提示)
```

### 2.2 AutoTrade 页面组件树

```
AutoTrade
├── 页头
│   ├── Title "量化交易" (RobotOutlined 图标)
│   ├── Button "刷新" (ReloadOutlined)
│   └── Button "新建策略" (PlusOutlined, primary)
│
├── Card (策略列表)
│   └── Table (1100px 横向滚动, pageSize=10)
│       ├── 策略名称 (可点击进入详情 + ID 前12位)
│       ├── 关联方案 (Tag: blue=方案名, default=自定义)
│       ├── 执行模式 (Tag: green=全自动, orange=半自动)
│       ├── 状态 (Tag: green=运行中, gold=暂停, red=已终止, blue=已完成)
│       ├── 累计盈亏 (¥ + %, 颜色: 绿涨红跌)
│       ├── 今日收益 (¥ + %, 颜色同上)
│       ├── 下次调仓 (倒计时: m分s秒 / 即将调仓)
│       └── 操作 (240px fixed右)
│           ├── 启动 (paused/terminated/completed 状态)
│           ├── 暂停 (running 状态)
│           ├── 终止 (running/paused 状态, Popconfirm)
│           ├── 重新启动 (terminated/completed 状态)
│           ├── 编辑
│           ├── 删除 (Popconfirm)
│           └── 详情
│
├── Drawer (策略详情, 720px 宽)
│   ├── 状态标签 + 执行模式标签
│   ├── Row (3 列 KPI 卡片)
│   │   ├── Statistic "累计盈亏" (¥ + %)
│   │   ├── Statistic "今日收益" (¥ + %)
│   │   └── Statistic "下次调仓" (倒计时)
│   ├── Card "当前持仓"
│   │   └── Table (代码/名称/数量/成本/现价/盈亏)
│   └── Card "策略日志"
│       └── Timeline (info/success/warning/error 四种级别图标)
│
└── Drawer (新建/编辑策略, 640px 宽)
    └── Form (vertical layout, size=small)
        ├── Divider "基本信息"
        │   ├── Input "策略名称" (required)
        │   ├── Radio.Group "执行模式" (full_auto | semi_auto)
        │   ├── InputNumber "最大总仓位 (%)" (0-100, default 80)
        │   └── InputNumber "单票最大仓位 (%)" (0-100, default 20)
        ├── Divider "买入条件" (ThunderboltOutlined)
        │   └── Form.List
        │       └── Card (每行一个条件, #fafafa 背景)
        │           ├── Switch (启用/禁用)
        │           ├── Select "指标" (MA/EMA/MACD/RSI/KDJ/BOLL/VOL/OBV)
        │           ├── Select "运算符" (>/</>=/<=/上穿/下穿)
        │           ├── InputNumber "数值"
        │           └── InputNumber "周期" (1-250, 可选)
        ├── Divider "卖出条件" (FallOutlined)
        │   └── Form.List (同买入条件结构)
        └── Divider "风控规则" (ExclamationCircleOutlined)
            └── Form.List
                └── Card (每行一个规则)
                    ├── Switch (启用/禁用)
                    ├── Select "规则类型" (单日最大亏损/总回撤上限/连续止损次数/最低现金比例)
                    └── InputNumber "阈值"
```

---

## 3. 状态管理

两个页面均使用 React 本地 `useState` + `useEffect` + `useCallback`，无第三方状态库。数据流为单向：**API → setState → 组件重渲染**。

### 3.1 AutoTrade 状态变量

```tsx
const [strategies, setStrategies] = useState<QuantStrategy[]>([])   // 策略列表
const [loading, setLoading] = useState(false)                       // 列表加载态
const [drawerOpen, setDrawerOpen] = useState(false)                  // 新建/编辑 Drawer
const [editingStrategy, setEditingStrategy] = useState<QuantStrategy | null>(null)  // 当前编辑的策略
const [detailStrategy, setDetailStrategy] = useState<QuantStrategy | null>(null)    // 当前查看详情的策略
const [logEntries, setLogEntries] = useState<LogEntry[]>([])        // 策略日志
const [logsLoading, setLogsLoading] = useState(false)               // 日志加载态
const [form] = Form.useForm()                                       // Ant Design 表单实例
const [, setTick] = useState(0)                                     // 倒计时 ticker (每秒 +1)
```

**倒计时机制**：`useEffect` 中 `setInterval(() => setTick(t => t + 1), 1000)` 每 1 秒触发一次重渲染，`countdownText()` 函数在渲染时计算 `next_rebalance_at` 距离当前时间的差值。

### 3.2 Strategy 状态变量

```tsx
const [plans, setPlans] = useState<any[]>([])           // 方案列表
const [loading, setLoading] = useState(false)           // 列表加载态
const [detailPlan, setDetailPlan] = useState<any>(null) // 方案详情 Modal
const [report, setReport] = useState<any>(null)         // 选股报告 Modal
```

### 3.3 加载时机

| 页面 | 触发时机 | 方法 |
|------|---------|------|
| Strategy | `useEffect([], [])` 首次挂载 | `loadPlans()` → `GET /api/v1/strategy/plans` |
| AutoTrade | `useEffect([loadStrategies], [loadStrategies])` 首次挂载 | `loadStrategies()` → `GET /api/v1/auto-trade/strategies` |
| AutoTrade | 手动点击"刷新"按钮 | `loadStrategies()` |
| AutoTrade | 新建/编辑保存成功后 | `loadStrategies()` |
| AutoTrade | start/pause/resume/stop/delete 成功后 | `loadStrategies()` |
| AutoTrade | 打开策略详情 | `viewDetail(id)` → `GET /api/v1/auto-trade/strategies/${id}` + `loadLogs(id)` |
| Strategy | 确认/删除成功后 | `loadPlans()` |
| Strategy | 手动点击"刷新"按钮 | `loadPlans()` |

---

## 4. 用户交互流程

```
┌─────────────────┐
│ 智能选股页面      │  运行选股模型
│ /screener       │  勾选标的 → 生成预方案
└────────┬────────┘
         │ POST /api/v1/strategy/plans
         ▼
┌─────────────────┐
│ 方案管理页面      │  草稿 → 确认
│ /strategy       │  确认后可见: 报告 / 回测 / 量化策略 按钮
└────────┬────────┘
         │ 点击 "量化策略" 按钮
         │ POST /api/v1/strategy/generate-from-scheme/${scheme_id}
         │ 成功后 navigate('/auto-trade')
         ▼
┌─────────────────┐
│ 量化交易页面      │  查看已生成的策略列表
│ /auto-trade     │
│                 │  新建策略 (手动配置)
│                 │  ├── 设置名称 / 执行模式 / 仓位限制
│                 │  ├── 配置买入条件 (指标+运算符+数值+周期)
│                 │  ├── 配置卖出条件 (同上)
│                 │  └── 配置风控规则 (类型+阈值)
│                 │  POST /api/v1/auto-trade/strategies
│                 │
│                 │  编辑策略
│                 │  PUT /api/v1/auto-trade/strategies/${id}
│                 │
│                 │  启动策略
│                 │  POST /api/v1/auto-trade/strategies/${id}/start
│                 │  → 状态: paused → running
│                 │
│                 │  监控运行
│                 │  ├── 点击策略名称 → Drawer 详情
│                 │  │   ├── KPI 卡片 (累计盈亏/今日收益/下次调仓)
│                 │  │   ├── 当前持仓表格
│                 │  │   └── 策略日志 Timeline
│                 │  └── 表格中实时倒计时 (每秒刷新)
│                 │
│                 │  暂停策略
│                 │  POST /api/v1/auto-trade/strategies/${id}/pause
│                 │  → 状态: running → paused
│                 │
│                 │  恢复策略
│                 │  POST /api/v1/auto-trade/strategies/${id}/resume
│                 │  → 状态: paused → running
│                 │
│                 │  终止策略
│                 │  POST /api/v1/auto-trade/strategies/${id}/stop
│                 │  → 状态: running/paused → terminated
│                 │  (带 Popconfirm 二次确认)
│                 │
│                 │  删除策略
│                 │  DELETE /api/v1/auto-trade/strategies/${id}
│                 │  (带 Popconfirm 二次确认)
│                 │
│                 │  重新启动 (已终止/已完成策略)
│                 │  POST /api/v1/auto-trade/strategies/${id}/start
│                 └── → 状态: terminated/completed → running
└─────────────────┘
```

### 4.1 状态转换图

```
                    ┌──────────┐
           ┌───────│  paused  │◄────────┐
           │ pause └──────────┘ resume  │
           ▼                             │
      ┌─────────┐    stop     ┌──────────┴──┐
      │ running │───────────►│ terminated  │
      └─────────┘            └──────┬───────┘
           │                        │
           │ complete               │ start (重新启动)
           ▼                        ▼
      ┌──────────┐            ┌─────────┐
      │ completed│            │ running │
      └──────────┘            └─────────┘
```

- `running` 可暂停 (`pause`) 或终止 (`stop`)
- `paused` 可恢复 (`resume`)、启动 (`start`) 或终止 (`stop`)
- `terminated` 和 `completed` 可重新启动 (`start`)
- 终止和删除操作均需 `Popconfirm` 二次确认

---

## 5. 暗色主题一致性

当前实现使用 **Ant Design 浅色默认主题**（`App.tsx` 中 `Radio.Group defaultValue="light"`）。

与 QuantDinger 品牌一致性要点：

| 维度 | 当前实现 | 备注 |
|------|---------|------|
| 主色调 | `#1677ff` (Ant Design 默认蓝) | RobotOutlined、BulbOutlined、StockOutlined 均使用此色 |
| 盈亏颜色 | 涨 `#52c41a` (绿) / 跌 `#ff4d4f` (红) | PnL、今日收益、持仓盈亏统一 |
| 状态标签 | green / gold / red / blue (Ant Design 预设) | statusConfig 对象统一管理 |
| 卡片圆角 | `borderRadius: 8` | 所有 Card 统一 |
| 条件卡片背景 | `#fafafa` | 买入/卖出/风控条件卡片 |
| 侧边栏 | 白色背景 `#fff`，阴影 `2px 0px 8px rgba(29,35,41,0.05)` | 收起/展开切换带过渡动画 |
| 字体 | Ant Design 默认字体栈 | 12px (辅助文本) / 13px (正文) / 14px (标签) / 16px (标题) |
| 间距 | 16px 页面外边距，8px/12px 组件内间距 | 统一使用 8 的倍数 |

暗色主题开关已预留（Drawer > 页面风格设置 > 主题模式），当前未激活。后续激活时需：
- 将所有硬编码颜色（`#fafafa`、`#fff`、`#000000d9`、状态颜色等）改为 CSS 变量或 `theme.useToken()` 动态值。
- 盈亏颜色 `#52c41a` / `#ff4d4f` 保留硬编码（投资领域红涨绿跌为业务约定，暗色模式下通常不反转）。

---

## 6. API 调用清单

### 6.1 AutoTrade 页面

| 方法 | 端点 | 何时调用 | 请求体 / 参数 |
|------|------|---------|-------------|
| `GET` | `/api/v1/auto-trade/strategies` | 页面挂载、刷新按钮、CRUD 成功后 | -- |
| `GET` | `/api/v1/auto-trade/strategies/{id}` | 点击策略名称查看详情 | -- |
| `GET` | `/api/v1/auto-trade/strategies/{id}/logs` | 打开策略详情 Drawer | -- |
| `POST` | `/api/v1/auto-trade/strategies` | 填写表单并点击"创建策略" | `{ name, execution_mode, max_position_pct, max_single_pct, buy_conditions[], sell_conditions[], risk_rules[] }` |
| `PUT` | `/api/v1/auto-trade/strategies/{id}` | 编辑策略并点击"保存修改" | 同 POST body |
| `DELETE` | `/api/v1/auto-trade/strategies/{id}` | Popconfirm 确认删除 | -- |
| `POST` | `/api/v1/auto-trade/strategies/{id}/start` | 点击启动/重新启动按钮 | -- |
| `POST` | `/api/v1/auto-trade/strategies/{id}/pause` | 点击暂停按钮 | -- |
| `POST` | `/api/v1/auto-trade/strategies/{id}/resume` | 点击恢复按钮 (Drawer 内) | -- |
| `POST` | `/api/v1/auto-trade/strategies/{id}/stop` | Popconfirm 确认终止 | -- |

**请求体结构 (POST/PUT)**：
```json
{
  "name": "策略名称",
  "execution_mode": "full_auto | semi_auto",
  "max_position_pct": 80,
  "max_single_pct": 20,
  "buy_conditions": [
    { "id": "xxx", "enabled": true, "indicator": "MA", "operator": "cross_above", "value": 0, "period": 20 }
  ],
  "sell_conditions": [
    { "id": "xxx", "enabled": true, "indicator": "RSI", "operator": ">=", "value": 70, "period": 14 }
  ],
  "risk_rules": [
    { "id": "xxx", "enabled": true, "rule_type": "max_daily_loss", "value": 3 }
  ]
}
```

**响应结构 (列表)**：
```json
{
  "strategies": [
    {
      "id": "xxx",
      "name": "策略名称",
      "plan_id": "方案ID (可选)",
      "plan_name": "关联方案名",
      "status": "running | paused | terminated | completed",
      "pnl": 1234.56,
      "pnl_pct": 5.67,
      "execution_mode": "full_auto | semi_auto",
      "current_positions": [{ "code": "000001", "name": "平安银行", "volume": 100, "cost": 12.5, "price": 13.2, "pnl": 70 }],
      "next_rebalance_at": "2026-06-10T15:00:00",
      "today_return": 100.00,
      "today_return_pct": 0.5,
      "created_at": "2026-06-10T10:00:00",
      "buy_conditions": [...],
      "sell_conditions": [...],
      "risk_rules": [...],
      "max_position_pct": 80,
      "max_single_pct": 20
    }
  ]
}
```

**响应结构 (日志)**：
```json
{
  "logs": [
    { "id": "xxx", "time": "2026-06-10T10:05:00", "action": "买入信号", "detail": "MA 上穿触发买入条件", "level": "info | success | warning | error" }
  ]
}
```

### 6.2 Strategy 页面

| 方法 | 端点 | 何时调用 | 说明 |
|------|------|---------|------|
| `GET` | `/api/v1/strategy/plans` | 页面挂载、刷新按钮、CRUD 成功后 | 方案列表 |
| `GET` | `/api/v1/strategy/plans/{id}` | 点击"查看"按钮 | 方案详情 |
| `DELETE` | `/api/v1/strategy/plans/{id}` | 点击"删除"按钮 | -- |
| `POST` | `/api/v1/strategy/plans/{id}/confirm` | 点击"确认"按钮 (draft 状态) | -- |
| `GET` | `/api/v1/strategy/plans/{id}/report` | 点击"报告"按钮 (confirmed 状态) | 选股报告 |
| `POST` | `/api/v1/strategy/generate-from-scheme/{id}` | 点击"量化策略"按钮 (confirmed 状态) | 生成策略后跳转 /auto-trade |
| `POST` | `/api/v1/backtest/run?mode=all` | 点击"回测"按钮 | 触发回测 |

### 6.3 错误处理模式

两个页面采用统一的错误处理：

```tsx
// 模式 1: then/catch + message.error
fetch('/api/...')
  .then(r => {
    if (r.ok) { message.success('...'); loadData(); }
    else { r.json().then(err => message.error(err.detail || '操作失败')); }
  })
  .catch(() => message.error('服务未连接'));

// 模式 2: async/await + try/catch
try {
  const r = await fetch('/api/...', { method: 'POST', ... });
  if (r.ok) { message.success('...'); navigate('/auto-trade'); }
  else { message.error((await r.json().catch(()=>({detail:'失败'}))).detail); }
} catch { message.error('服务未连接'); }
```

- 网络异常统一显示 `message.error('服务未连接')`
- 业务异常读取响应体 `detail` 字段显示
- 加载态通过 `loading` 状态控制 Table 的 `loading` 属性和按钮的 `loading` 属性

---

## 7. 类型定义

### 7.1 AutoTrade 核心类型

```tsx
interface Condition {
  id: string           // 唯一标识 (Date.now().toString(36) + random)
  enabled: boolean     // 启用/禁用开关
  indicator: string    // 指标: MA | EMA | MACD | RSI | KDJ | BOLL | VOL | OBV
  operator: string     // 运算符: > | < | >= | <= | cross_above | cross_below
  value: number        // 阈值
  period?: number      // 周期 (可选, 1-250)
}

interface RiskRule {
  id: string           // 唯一标识
  enabled: boolean     // 启用/禁用开关
  rule_type: string    // 规则类型: max_daily_loss | max_drawdown | max_consecutive_stops | min_cash_ratio
  value: number        // 阈值
}

interface QuantStrategy {
  id: string
  name: string
  plan_id?: string
  plan_name: string
  status: 'running' | 'paused' | 'terminated' | 'completed'
  pnl: number
  pnl_pct: number
  execution_mode: 'full_auto' | 'semi_auto'
  current_positions: { code: string; name: string; volume: number; cost: number; price: number; pnl: number }[]
  next_rebalance_at?: string
  today_return: number
  today_return_pct: number
  created_at: string
  buy_conditions: Condition[]
  sell_conditions: Condition[]
  risk_rules: RiskRule[]
  max_position_pct: number
  max_single_pct: number
}

interface LogEntry {
  id: string
  time: string
  action: string
  detail: string
  level: 'info' | 'success' | 'warning' | 'error'
}
```

### 7.2 常量定义

| 常量 | 值 | 用途 |
|------|---|------|
| `statusConfig` | `{ running: green/运行中, paused: gold/暂停, terminated: red/已终止, completed: blue/已完成 }` | 状态标签颜色和文本 |
| `indicatorOptions` | 8 项：MA, EMA, MACD, RSI, KDJ, BOLL, VOL, OBV | 买卖条件指标下拉 |
| `operatorOptions` | 6 项：>, <, >=, <=, cross_above, cross_below | 买卖条件运算符下拉 |
| `riskRuleOptions` | 4 项：max_daily_loss, max_drawdown, max_consecutive_stops, min_cash_ratio | 风控规则类型下拉 |
| `planSteps` | 6 步：选股 → 预方案 → 预测验证 → 回测验证 → 确认方案 → 执行交易 | 方案页流程条 |
| `statusColors` | `{ draft: blue, confirmed: green, active: red, archived: default }` | 方案状态颜色 |

---

## 8. 关键实现细节

### 8.1 ID 生成

```tsx
function makeId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}
```

用于前端生成条件/规则的临时 ID。提交时附带 ID 以支持后端去重和增量更新。

### 8.2 空值初始化

```tsx
function emptyCondition(): Condition {
  return { id: makeId(), enabled: false, indicator: 'MA', operator: '>', value: 0, period: 20 }
}
function emptyRiskRule(): RiskRule {
  return { id: makeId(), enabled: false, rule_type: 'max_daily_loss', value: 0 }
}
```

新建策略时默认注入一个空条件/空规则，避免 Form.List 为空时的空白体验。

### 8.3 倒计时

```tsx
// 每秒 ticker 触发重渲染
useEffect(() => {
  const timer = setInterval(() => setTick(t => t + 1), 1000)
  return () => clearInterval(timer)
}, [])

function countdownText(iso?: string): string {
  if (!iso) return '--'
  const diff = new Date(iso).getTime() - Date.now()
  if (diff <= 0) return '即将调仓'
  const m = Math.floor(diff / 60000)
  const s = Math.floor((diff % 60000) / 1000)
  return `${m}分${s}秒`
}
```

在表格列和详情 KPI 卡片中均使用 `countdownText()`，从服务端返回的 `next_rebalance_at` ISO 时间计算剩余时间。

### 8.4 表单提交

```tsx
const handleSubmit = async () => {
  try {
    const values = await form.validateFields()
    const url = editingStrategy
      ? `/api/v1/auto-trade/strategies/${editingStrategy.id}`
      : '/api/v1/auto-trade/strategies'
    const method = editingStrategy ? 'PUT' : 'POST'
    // ... fetch with JSON body
  } catch { /* validation error handled by antd */ }
}
```

新建和编辑复用同一个 Drawer + Form。通过 `editingStrategy` 是否为 `null` 区分 POST 还是 PUT。`Form.useForm()` 实例在打开 Drawer 时通过 `form.setFieldsValue()` 预填。

### 8.5 策略详情 Drawer 操作按钮

详情 Drawer 右上角 `extra` 区域动态显示暂停/恢复/终止按钮，根据当前策略的 `status` 决定：
- `running`：显示"暂停"+"终止"
- `paused`：显示"恢复"+"终止"

操作完成后自动关闭 Drawer (`setDetailStrategy(null)`)。

### 8.6 空状态处理

- Table 空数据：`locale={{ emptyText: '暂无量化策略，点击"新建策略"创建或从方案管理页面生成。' }}`
- 持仓为空：`<Empty description="暂无持仓" image={Empty.PRESENTED_IMAGE_SIMPLE} />`
- 日志为空：`<Empty description="暂无日志" image={Empty.PRESENTED_IMAGE_SIMPLE} />`
- 方案列表空：`locale={{ emptyText: '暂无方案。请在智能选股页面运行选股后，勾选标的生成预方案。' }}`

---

## 9. 文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `frontend/src/App.tsx` | 297 | 路由注册 (line 67) + 侧边栏菜单项 (line 47) + 主题设置预留 |
| `frontend/src/pages/Strategy.tsx` | 186 | 方案管理：列表/详情/确认/报告/回测/量化策略生成 |
| `frontend/src/pages/AutoTrade.tsx` | 735 | 量化交易：策略列表/新建编辑 Drawer/详情 Drawer/操作按钮 |
