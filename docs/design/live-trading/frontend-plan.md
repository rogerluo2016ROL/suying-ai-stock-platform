# 实盘交易 — 前端页面方案

> **版本**: v1.0  
> **日期**: 2026-06-10  
> **状态**: Draft — 待 tech-lead / product-lead 确认  
> **关联文档**: [投资管理平台_PRD_产品需求文档.md](../../Kronos/docs/投资管理平台_PRD_产品需求文档.md) §3.11 AC-11.1~11.9

---

## 1. 概述

在现有模拟交易页面（`Trade.tsx`，186 行）基础上，增加实盘交易能力。PRD AC-11.9 明确要求：**实盘和模拟盘的界面和操作逻辑完全一致，仅资金是真是假的区别**。因此本方案不创建独立实盘页面，而是在现有 Trade.tsx 中追加实盘专属的开关、状态指示、风控确认和审计入口。

---

## 2. 技术基线

| 项 | 当前选型 | 说明 |
|---|---|---|
| 框架 | React 18.3 + TypeScript 5.6 | 已有 |
| 构建 | Vite 6.0 | 已有 |
| UI 库 | Ant Design 5.22 + @ant-design/icons 5.5 | 已有 |
| 路由 | react-router-dom 6.28 | 已有 |
| 状态管理 | React Context | 已有 AuthContext，不新增状态库 |
| 主题 | Ant Design ConfigProvider（light 主色调 `#1677ff`） | 已有暗色切换 UI（Drawer 中），当前未生效 |

---

## 3. 模拟/实盘模式切换（AC-11.9）

### 3.1 设计方案

**不做页面跳转**。在现有 Trade.tsx Header 区域，将当前只读 Tag 替换为 `antd Segmented` 或 `Switch` 组件，用户一键切换。

### 3.2 现有代码对比

```
// 现有一行 Tag (Trade.tsx:69)：
<Tag color={mode === 'paper' ? 'blue' : 'red'}>{mode === 'paper' ? '📝 模拟交易' : '🔴 实盘交易'}</Tag>

// 替换为：
<Segmented
  value={mode}
  onChange={(v) => handleModeSwitch(v)}
  options={[
    { label: '📝 模拟盘', value: 'paper' },
    { label: '🔴 实盘', value: 'live' },
  ]}
/>
```

### 3.3 切换行为

- 切换时调用 `POST /api/v1/trade/mode` 或本地 setState（后端决定是否切换数据源）
- 实盘模式下自动开始轮询券商连接状态（见 §4）
- 页面所有数据（KPI Banner、持仓、委托、成交）根据当前模式从不同后端 endpoint 拉取：
  - 模拟盘：`/api/v1/trade/account` 等（现有）
  - 实盘：`/api/v1/live-trade/account` 等（新增）

### 3.4 数据源切换策略

```typescript
// 模式 → API 前缀映射
const API_PREFIX = mode === 'paper' ? '/api/v1/trade' : '/api/v1/live-trade';

// 所有 fetch 调用统一使用
fetch(`${API_PREFIX}/account`);
fetch(`${API_PREFIX}/positions`);
fetch(`${API_PREFIX}/orders`);
```

> 此策略保证 AC-11.9（界面/逻辑一致）——同一个 Trade.tsx 组件，仅 API 前缀不同。

---

## 4. 券商连接状态指示器（AC-11.2）

### 4.1 设计方案

在 Header 区域 Segmented 切换器右侧，放置一个带颜色的状态指示器（Badge/Dot + 文字）。

### 4.2 状态枚举

| 状态 | 视觉 | 含义 |
|---|---|---|
| `connected` | 🟢 绿色圆点 + "已连接" | 券商接口正常，可以下单 |
| `disconnected` | 🔴 红色圆点 + "已断开" | 券商接口不可用，下单将被拒绝 |
| `connecting` | 🟡 黄色圆点 + "连接中" | 正在建立券商连接 |
| `error` | ⚠️ 橙色三角 + "异常" | 连接存在但返回异常（如认证过期） |

### 4.3 前端实现

```tsx
// 状态指示器组件（内联在 Trade.tsx Header 中）
const [brokerStatus, setBrokerStatus] = useState<'connected' | 'disconnected' | 'connecting' | 'error'>('disconnected');

// 仅实盘模式显示
{mode === 'live' && (
  <Space>
    <Badge status={statusMap[brokerStatus]} />
    <Text style={{ fontSize: 12 }}>{brokerTextMap[brokerStatus]}</Text>
  </Space>
)}
```

### 4.4 轮询策略

- 实盘模式下每 10 秒轮询 `GET /api/v1/live-trade/broker/status`
- 状态变化时通过 `antd message` 提示（"券商连接已断开" 等）
- 断开时所有下单按钮置灰 + tooltip "券商未连接"

---

## 5. 大额交易二次确认弹窗（AC-11.4）

### 5.1 触发条件

下单前，计算 `price × volume`（市价单用最新行情价 × volume），超过阈值时弹出确认弹窗。

### 5.2 设计方案

使用 `antd Modal.confirm` 或自定义 Modal：

```
┌────────────────────────────────────────┐
│  ⚠️ 大额交易确认                        │
│                                        │
│  本次交易金额较大：                      │
│                                        │
│  股票代码    000001                     │
│  方向        买入                       │
│  价格        ¥12.50                     │
│  数量        50,000 股                   │
│  预估金额    ¥625,000.00                 │
│                                        │
│  ───────────────────────────────────   │
│                                        │
│  [取消]              [确认下单]          │
└────────────────────────────────────────┘
```

### 5.3 阈值配置

- 默认阈值：**¥500,000**（50 万）
- 阈值来源：`GET /api/v1/live-trade/risk-config` 返回 `{ large_order_threshold: 500000 }`
- 页面首次加载时获取并缓存在 state 中

### 5.4 下单流程变更

```
用户点击"下单"
  → 风控检查（见 §6）
    → 通过 → 检查金额是否超阈值
      → 未超阈值 → 直接下单
      → 超阈值 → 弹出确认弹窗 → 用户确认 → 下单
    → 未通过 → 显示风控拦截提示（见 §6）
```

---

## 6. 风控拦截提示（AC-11.3）

### 6.1 风控检查项

下单前（先于大额确认），前端调用 `POST /api/v1/live-trade/order/pre-check`，传入下单参数。后端返回检查结果。

| 检查项 | 失败提示文案 | 对应 AC |
|---|---|---|
| 资金不足 | "可用资金不足，当前可用 ¥{X}，所需 ¥{Y}" | AC-11.3 |
| 超持仓上限 | "持仓已达上限，{stock} 当前仓位 {X}%，上限 {Y}%" | AC-11.3 |
| 涨跌停限制 | "{stock} 当前处于涨停/跌停状态，无法交易" | AC-11.3 |
| 超单笔上限 | "单笔交易金额超过上限 ¥{X}" | AC-11.3 |
| 熔断中 | "当日亏损已达熔断阈值，交易已暂停" | AC-11.8 |

### 6.2 拦截展示

使用 `antd Modal.error` 或自定义 Modal：

```
┌────────────────────────────────────────┐
│  🛑 风控拦截                            │
│                                        │
│  以下风控规则未通过：                     │
│                                        │
│  ❌ 资金不足                             │
│  可用资金 ¥120,000，本笔所需 ¥625,000    │
│                                        │
│  ❌ 超单笔上限                           │
│  单笔上限 ¥500,000，本笔 ¥625,000       │
│                                        │
│              [知道了]                    │
└────────────────────────────────────────┘
```

### 6.3 非阻塞提示（仅警告）

某些检查仅作风险提示，不阻止下单：

| 检查项 | 提示类型 | 文案 |
|---|---|---|
| 高仓位提醒 | Warning（可继续） | "当前仓位 {X}%，接近仓位上限 {Y}%" |
| 高波动提醒 | Warning（可继续） | "{stock} 今日波动率 {X}%，高于正常水平" |

使用 `antd notification.warning`，不阻塞下单流程。

---

## 7. 熔断状态提示（AC-11.8）

### 7.1 设计方案

熔断是全局状态，影响所有实盘交易操作。在 KPI Banner 下方（或 Header 下方）显示醒目的全局提示条。

### 7.2 视觉设计

使用 `antd Alert` 组件（`type="error"`，可关闭但轮询会重新显示）：

```
┌──────────────────────────────────────────────────────────────┐
│ ⚡ 日内熔断已触发                                               │
│ 今日亏损 ¥-52,300 已超过熔断阈值 ¥50,000，实盘交易已暂停。        │
│ 如需恢复，请联系管理员或等待次日重置。                    [详情]  │
└──────────────────────────────────────────────────────────────┘
```

### 7.3 行为

- 轮询 `GET /api/v1/live-trade/circuit-breaker/status`（间隔 30 秒）
- 熔断状态下：
  - 下单按钮置灰 + tooltip "熔断保护中，交易暂停"
  - 量化策略自动暂停（如有运行中的策略）
  - 页面顶部的 Alert 持续显示
- 熔断恢复后：
  - Alert 消失
  - 下单按钮恢复，需用户手动恢复量化策略

---

## 8. 审计日志查看页（AC-11.7）

### 8.1 设计方案

新建独立路由页面 `LiveTradeAuditLog.tsx`，仅展示审计日志，**不可删除、不可编辑**。入口放在 Trade 页面 Header 区域（实盘模式下显示"审计日志"链接/按钮）。

### 8.2 路由

`/trade/audit-log`（或 `/live-trade/audit-log`）

### 8.3 页面布局

```
┌──────────────────────────────────────────────────────────────┐
│  ← 返回交易中心         审计日志                                │
│                                                              │
│  [日期筛选: 2026-06-01 ~ 2026-06-10]  [操作类型 ▼]  [股票代码]  │
│  [查询]  [重置]                                               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 时间          操作        股票    详情          操作人    │  │
│  ├────────────────────────────────────────────────────────┤  │
│  │ 06-10 14:32  买入下单    000001  ¥12.50×5000  张三    │  │
│  │ 06-10 14:30  风控拦截    000002  资金不足      系统    │  │
│  │ 06-10 14:28  大额确认    000001  ¥625,000     张三    │  │
│  │ 06-10 13:15  熔断触发    —       亏损超阈值    系统    │  │
│  │ 06-10 10:00  模式切换    —       模拟→实盘     张三    │  │
│  │ 06-10 09:30  券商连接    —       已连接        系统    │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│                    共 128 条记录  [< 1 2 3 ... >]             │
└──────────────────────────────────────────────────────────────┘
```

### 8.4 表格列定义

| 列 | 字段 | 宽度 | 说明 |
|---|---|---|---|
| 时间 | `created_at` | 160px | 精确到秒 |
| 操作类型 | `action_type` | 120px | 标签形式（买入/卖出/风控/熔断/配置等） |
| 股票代码 | `stock_code` | 100px | 无股票相关的记为 "---" |
| 详情 | `detail` | auto | JSON 或文字描述 |
| 操作人 | `operator` | 100px | 用户姓名或 "系统" |
| IP 地址 | `ip_address` | 130px | 可选列，默认隐藏 |

### 8.5 筛选器

- 日期范围：`antd DatePicker.RangePicker`
- 操作类型：`antd Select` 多选（买入下单 / 卖出下单 / 撤单 / 风控拦截 / 大额确认 / 熔断触发 / 券商连接 / 模式切换 / 策略操作）
- 股票代码：`antd Input` 模糊搜索
- 操作人：`antd Select`（管理员可见全部操作人）

### 8.6 只读保障

- 表格无 `rowSelection`、无可编辑单元格、无行内操作按钮
- 后端 `GET /api/v1/live-trade/audit-logs` 仅支持 GET 请求，无 DELETE/PUT/PATCH
- 右上角提供"导出 CSV"按钮（`GET /api/v1/live-trade/audit-logs/export`）

---

## 9. 与 QuantDinger 暗色主题风格一致

### 9.1 当前主题状态

现有项目（`main.tsx`）使用 Ant Design `ConfigProvider`，当前为浅色主题（白底 sidebar、白底 header、`#f5f5f5` body）。设置抽屉中包含暗色/浅色切换 Radio，但**未接入 ConfigProvider 的 `theme.algorithm`**。

### 9.2 本功能不改变主题框架

实盘交易相关的所有新增 UI 组件（Toggle、状态指示器、Modal、Alert、审计日志页）均使用 Ant Design 原生组件，自动继承 `ConfigProvider` 的主题 token。不引入额外的 CSS Module 或 styled-components。

### 9.3 暗色适配注意点

- Modal/Alert 的高亮文字使用 `colorPrimary` token（`#1677ff`），而非硬编码颜色
- 自定义金额颜色复用现有 KPI Banner 的规则（正数绿 `#52c41a`，负数红 `#ff4d4f`）
- 状态指示器的 Badge 颜色使用 Ant Design 内置 `Badge status`（`success`/`error`/`warning`/`processing`）
- 审计日志页面的 Table/Card 使用默认 `Card` 组件，无需额外背景色

---

## 10. 组件树与文件结构

### 10.1 新增/修改文件

```
frontend/src/
├── pages/
│   ├── Trade.tsx                    # [修改] 添加模式切换、状态指示器、风控弹窗、审计入口
│   └── LiveTradeAuditLog.tsx        # [新增] 审计日志只读页面
├── components/
│   └── trade/
│       ├── BrokerStatus.tsx         # [新增] 券商连接状态指示器（可选独立组件）
│       ├── LargeOrderConfirm.tsx    # [新增] 大额交易确认弹窗
│       ├── RiskCheckModal.tsx       # [新增] 风控拦截结果展示弹窗
│       └── CircuitBreakerAlert.tsx  # [新增] 熔断状态提示条
├── hooks/
│   └── useLiveTrade.ts             # [新增] 实盘交易状态管理 hook（模式、券商状态、熔断、风控阈值）
├── api/
│   └── liveTrade.ts                # [新增] 实盘交易 API 封装
├── App.tsx                          # [修改] 新增 /trade/audit-log 路由
```

### 10.2 组件关系图

```
Trade.tsx
├── Header
│   ├── Segmented (模拟盘 / 实盘)           ← 替换现有 Tag
│   ├── BrokerStatus (仅实盘)              ← 新增
│   └── Button "审计日志" (仅实盘)          ← 新增跳转入口
├── CircuitBreakerAlert (仅实盘 + 熔断中)   ← 新增
├── KPI Banner (复用现有，数据源切换)
├── Strategy Cards (复用现有)
├── Orders Table (复用现有，数据源切换)
├── Order Panel (复用现有，增加风控流程)
│   └── 下单按钮 onClick → useLiveTrade.placeOrder()
│       ├── 1. preCheck() → RiskCheckModal (如有拦截)
│       ├── 2. checkLargeOrder() → LargeOrderConfirm (如超阈值)
│       └── 3. submitOrder() → API

LiveTradeAuditLog.tsx (独立路由页面)
├── 返回按钮 + 标题
├── 筛选器 (DatePicker + Select + Input)
├── Table (只读，无可操作列)
└── 导出 CSV 按钮
```

### 10.3 `useLiveTrade` Hook 设计

```typescript
interface UseLiveTradeReturn {
  // 模式
  mode: 'paper' | 'live';
  setMode: (m: 'paper' | 'live') => void;

  // 券商状态
  brokerStatus: 'connected' | 'disconnected' | 'connecting' | 'error';

  // 风控配置
  riskConfig: { large_order_threshold: number; /* ... */ } | null;

  // 熔断状态
  circuitBreaker: { triggered: boolean; loss_amount: number; threshold: number } | null;

  // 下单（含完整风控流程）
  placeOrder: (params: OrderParams) => Promise<void>;
}
```

---

## 11. API 端点汇总

| 方法 | 路径 | 用途 | AC |
|---|---|---|---|
| `GET` | `/api/v1/live-trade/account` | 实盘账户信息 | 11.1/11.9 |
| `GET` | `/api/v1/live-trade/positions` | 实盘持仓列表 | 11.1/11.9 |
| `GET` | `/api/v1/live-trade/orders` | 实盘委托/成交列表 | 11.1/11.9 |
| `POST` | `/api/v1/live-trade/order` | 实盘下单 | 11.1/11.9 |
| `POST` | `/api/v1/live-trade/order/pre-check` | 下单前风控检查 | 11.3 |
| `GET` | `/api/v1/live-trade/broker/status` | 券商连接状态 | 11.2 |
| `GET` | `/api/v1/live-trade/risk-config` | 风控阈值配置 | 11.4 |
| `GET` | `/api/v1/live-trade/circuit-breaker/status` | 熔断状态 | 11.8 |
| `GET` | `/api/v1/live-trade/audit-logs` | 审计日志列表（分页+筛选） | 11.7 |
| `GET` | `/api/v1/live-trade/audit-logs/export` | 审计日志 CSV 导出 | 11.7 |

---

## 12. 实现步骤建议

| 步骤 | 内容 | 依赖 | 改动文件数 |
|---|---|---|---|
| 1 | 与 backend-dev 对齐 API 契约（见 §11） | — | 0 |
| 2 | 创建 `hooks/useLiveTrade.ts`（模式/状态/hook 封装） | §11 API 契约 | 1 |
| 3 | 创建 `api/liveTrade.ts`（实盘 API 封装函数） | §11 API 契约 | 1 |
| 4 | 改造 `Trade.tsx`（模式切换 + 数据源分流 + 状态指示器 + 风控弹窗集成） | useLiveTrade | 1 |
| 5 | 创建 `components/trade/BrokerStatus.tsx`（券商状态指示器） | useLiveTrade | 1 |
| 6 | 创建 `components/trade/LargeOrderConfirm.tsx`（大额确认弹窗） | useLiveTrade | 1 |
| 7 | 创建 `components/trade/RiskCheckModal.tsx`（风控拦截弹窗） | api/liveTrade | 1 |
| 8 | 创建 `components/trade/CircuitBreakerAlert.tsx`（熔断提示条） | useLiveTrade | 1 |
| 9 | 创建 `pages/LiveTradeAuditLog.tsx`（审计日志页） | api/liveTrade | 1 |
| 10 | 修改 `App.tsx`（新增 `/trade/audit-log` 路由 + ProtectedRoute） | LiveTradeAuditLog | 1 |
| 11 | 编写 Unit 测试 + SIT 测试 | 全部完成 | 3 |

---

## 13. 关键交互流程

### 13.1 实盘下单完整流程

```
用户填写下单表单 → 点击"下单"
  │
  ├─ [1] 风控预检 POST /pre-check
  │      ├─ 有拦截 → RiskCheckModal（"知道了"关闭，不下单）
  │      └─ 通过 → 继续
  │
  ├─ [2] 大额判断 (price × volume > threshold)
  │      ├─ 是 → LargeOrderConfirm（"取消"关闭 / "确认下单"继续）
  │      └─ 否 → 继续
  │
  └─ [3] 提交订单 POST /order
         ├─ 成功 → message.success + 刷新数据
         └─ 失败 → message.error（显示后端错误信息）
```

### 13.2 模拟盘下单流程

```
用户填写下单表单 → 点击"下单"
  │
  └─ 直接 POST /api/v1/trade/order（现有流程，不变）
```

---

> **下一步**: product-lead 确认本方案后，frontend-dev 与 backend-dev 对齐 API 契约（见 §11），然后进入实现阶段。
