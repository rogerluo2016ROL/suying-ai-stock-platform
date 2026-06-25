# 速赢AI 前后端拉通优化方案

> 版本: 2026-06-25  
> 适用范围: 前端设计系统迁移 + 后端API契约修复 + 页面改造顺序

## 一、执行摘要

基于 `docs/design/new front/` 设计规范文档与现有 `frontend/src` 代码的对比分析，识别出**六大差异领域**：

1. 视觉系统（深色交易终端 vs 浅色管理后台）
2. 信息架构（双导航分工 vs 单一左侧导航）
3. 布局密度（高密度交易终端 vs 传统SaaS布局）
4. 字体系统（等宽行情数字 vs 系统默认）
5. 状态规范（完整状态处理 vs 部分实现）
6. 可访问性（完整aria规范 vs 部分实现）

后端API与前端调用对接存在**三类契约问题**：

1. 字段名不一致（price/close/current_price等）
2. TypeScript类型缺失（大量 `any` 类型）
3. 错误处理不完整（HealthCheckError等）

本方案提供**三阶段迁移路径**，预计完成时间 **4-6周**。

---

## 二、设计系统差异清单（任务1）

### 2.1 视觉系统差异

| 维度 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **主题模式** | 深色交易终端（#0b0e14背景）+ 浅色可选 | 仅浅色模式（#f5f7fa背景） | P0 |
| **色彩token** | 25个设计token（--bg/--surface/--up/--down等） | Ant Design默认色彩系统 | P0 |
| **A股惯例** | 红涨绿跌（--up: #ff4d4f, --down: #2ec27e） | 无明确A股色彩约定 | P0 |
| **强调色** | 单一电光蓝（--accent: #3d8bff） | Ant Design蓝色（#1677ff） | P1 |
| **网格背景** | 终端网格（rgba(255,255,255,.045)） | 无网格背景 | P2 |
| **光晕效果** | 单一低透明度蓝色光晕 | 无光晕效果 | P2 |

**修复方案**：

```css
/* frontend/src/styles/design-tokens.css */
:root {
  /* 深色模式（默认） */
  --bg: #0b0e14;
  --surface: #101620;
  --surface-2: #151d2a;
  --surface-3: #1a2433;
  --fg: #e8edf4;
  --fg-2: #a8b3c3;
  --muted: #667286;
  --border: rgba(255,255,255,.08);
  --border-strong: rgba(255,255,255,.14);
  --accent: #3d8bff;
  --accent-dim: rgba(61,139,255,.14);
  --up: #ff4d4f;  /* A股涨 */
  --up-dim: rgba(255,77,79,.14);
  --down: #2ec27e;  /* A股跌 */
  --down-dim: rgba(46,194,126,.14);
  --warn: #f5a623;
  --warn-dim: rgba(245,166,35,.14);
  
  /* 字体 */
  --font-display: "SF Pro Display", "PingFang SC", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --font-body: "SF Pro Text", "PingFang SC", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  
  /* 布局 */
  --sidebar-w: 236px;
  --header-h: 52px;
  --radius: 8px;
}

/* 浅色模式（可选） */
:root[data-theme="light"] {
  --bg: #f4f6fa;
  --surface: #ffffff;
  --surface-2: #f7f9fc;
  --surface-3: #eef2f8;
  --fg: #1a2230;
  --fg-2: #52617a;
  --muted: #8a96a8;
  --border: #e6eaf0;
  --border-strong: #d4dbe6;
}

/* 终端网格背景 */
body {
  background:
    linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px),
    linear-gradient(180deg, rgba(255,255,255,.045) 1px, transparent 1px),
    radial-gradient(circle at 62% 12%, rgba(61,139,255,.08), transparent 34%),
    var(--bg);
  background-size: 48px 48px, 48px 48px, auto, auto;
}
```

### 2.2 信息架构差异

| 维度 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **左侧导航** | 三组分类（行情决策/交易执行/模型系统） | 单一扁平列表 | P0 |
| **顶部工作流** | 页面内流程导航（总览→候选池→K线预测等） | 无顶部工作流导航 | P0 |
| **交易上下文条** | 交易日/执行模式/风控闸门/数据状态 | 无交易上下文条 | P1 |
| **当前态标识** | aria-current="page" + 左侧指示条 | 仅selectedKeys | P1 |

**修复方案**：

```tsx
// frontend/src/components/layout/Navigation.tsx
const NAV_GROUPS = [
  {
    title: '行情决策',
    items: [
      { key: '/', label: 'AI智能看板', icon: <DashboardOutlined /> },
      { key: '/screener', label: '智能选股', icon: <SearchOutlined /> },
      { key: '/supply-chain-bom', label: '产业链拆解', icon: <ApartmentOutlined /> },
      { key: '/predictions', label: 'K线预测', icon: <LineChartOutlined /> },
      { key: '/strategy', label: '方案管理', icon: <BulbOutlined /> },
      { key: '/signals', label: '交易信号', icon: <ThunderboltOutlined /> },
    ]
  },
  {
    title: '交易执行',
    items: [
      { key: '/trade', label: '交易中心', icon: <DollarOutlined /> },
      { key: '/auto-trade', label: '量化交易', icon: <RobotOutlined /> },
      { key: '/backtest', label: '回测分析', icon: <ExperimentOutlined /> },
      { key: '/diagnosis', label: '个股诊断', icon: <FundOutlined /> },
    ]
  },
  {
    title: '模型/系统',
    items: [
      { key: '/training', label: '模型训练', icon: <ExperimentOutlined /> },
      { key: '/model-registry', label: '模型注册', icon: <ApiOutlined /> },
      { key: '/data-update', label: '数据更新', icon: <ClockCircleOutlined /> },
    ]
  },
];
```

### 2.3 布局密度差异

| 维度 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **推荐宽度** | 1366px+，最佳1440-1920px | 无明确宽度要求 | P1 |
| **左侧宽度** | 固定236px | 可折叠256px/80px | P1 |
| **面板圆角** | 8px | Ant Design默认4px | P2 |
| **信息密度** | 首屏可见候选股、K线、交易票、服务状态 | 多卡片滚动布局 | P0 |

**修复方案**：

```tsx
// frontend/src/pages/Dashboard.tsx — 高密度布局示例
<div className="dashboard-grid" style={{
  display: 'grid',
  gridTemplateColumns: 'minmax(260px, 0.78fr) minmax(520px, 1.45fr) minmax(360px, 1fr)',
  gap: 14,
  alignItems: 'start',
}}>
  {/* 左侧：候选池 */}
  <CandidatePanel />
  {/* 中间：K线预测 */}
  <PredictionPanel />
  {/* 右侧：交易票 + 服务健康 */}
  <TradeTicketPanel />
</div>
```

### 2.4 字体系统差异

| 维度 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **Display字体** | SF Pro Display / PingFang SC | 系统默认sans-serif | P1 |
| **Body字体** | SF Pro Text / PingFang SC | 系统默认sans-serif | P1 |
| **Mono字体** | SF Mono / JetBrains Mono（行情数字） | 无专用等宽字体 | P0 |
| **数字对齐** | font-variant-numeric: tabular-nums | 无专门对齐 | P0 |

**修复方案**：

```css
/* frontend/src/styles/design-tokens.css */
.mono {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

/* 所有价格、涨跌幅、评分使用.mono类 */
.price-cell, .change-cell, .score-cell {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
```

### 2.5 状态规范差异

| 状态 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **加载态** | aria-busy="true" + 文案变化 | 仅Spin组件 | P0 |
| **空态** | role="status" + aria-live="polite" + 恢复方法 | 部分实现 | P0 |
| **错误态** | 模块内显示 + 多处同步 | toast依赖 | P0 |
| **当前态** | aria-current="page"/"true"/"pressed" | 仅selectedKeys | P1 |

**修复方案**：

```tsx
// frontend/src/components/ui/StatefulPanel.tsx
interface StatefulPanelProps {
  loading?: boolean;
  empty?: boolean;
  error?: string;
  onRetry?: () => void;
}

const StatefulPanel: React.FC<StatefulPanelProps> = ({ 
  loading, empty, error, onRetry, children 
}) => {
  if (loading) {
    return (
      <div role="status" aria-busy="true" aria-live="polite">
        <Spin /> 刷新中...
      </div>
    );
  }
  
  if (error) {
    return (
      <div role="alert" aria-live="assertive">
        <Alert type="error" message={error} />
        {onRetry && <Button onClick={onRetry}>重试</Button>}
      </div>
    );
  }
  
  if (empty) {
    return (
      <div role="status" aria-live="polite">
        <Empty description="没有匹配的候选股" />
        <Button onClick={onRetry}>清除筛选</Button>
      </div>
    );
  }
  
  return children;
};
```

### 2.6 可访问性差异

| 维度 | 设计文档要求 | 现有代码实现 | 优先级 |
|------|-------------|-------------|--------|
| **全局focus-visible** | 2px solid var(--accent) 聚焦环 | Ant Design默认 | P0 |
| **aria-label** | 搜索框、导航、按钮 | 部分实现 | P0 |
| **role="switch"** | 二次确认开关 | role="checkbox" | P1 |
| **aria-pressed** | 可切换按钮 | 部分实现 | P1 |
| **prefers-reduced-motion** | 禁用动画 | 无处理 | P2 |

**修复方案**：

```css
/* frontend/src/styles/accessibility.css */
:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* 减少动效兜底 */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.001ms !important;
    transition-duration: 0.001ms !important;
  }
}
```

---

## 三、后端API契约清单（任务2）

### 3.1 字段名不一致

| 后端字段 | 前端期望 | 出现位置 | 修复方案 |
|---------|---------|---------|---------|
| `close` | `price` | screener picks | 后端 `_normalize_picks()` 已处理 |
| `current_price` | `price` | leader_auction模式 | 后端 `_normalize_picks()` 已处理 |
| `change_pct` | `chg` | 前端显示 | 前端映射 `{ chg: record.change_pct }` |
| `vol_ratio` | `vr` | 前端显示 | 前端映射 `{ vr: record.vol_ratio }` |
| `turnover_rate` | `to` | 前端显示 | 前端映射 `{ to: record.turnover_rate }` |

**现状**：后端已在 `screener.py` 的 `_normalize_picks()` 中统一字段名，前端无需额外处理。

### 3.2 TypeScript类型缺失

| API模块 | 现状 | 修复方案 |
|--------|------|---------|
| `screenerApi.run()` | 返回 `any` | 定义 `ScreenerRunResponse` 类型 |
| `predictionApi.predict()` | 返回 `any` | 定义 `PredictionResponse` 类型 |
| `signalApi.getLive()` | 返回 `any` | 定义 `SignalLiveResponse` 类型 |
| `tradeApi.placeOrder()` | 返回 `any` | 定义 `OrderResponse` 类型 |
| `backtestApi.run()` | 返回 `any` | 定义 `BacktestRunResponse` 类型 |

**修复示例**：

```typescript
// frontend/src/api/types.ts
export interface ScreenerPick {
  code: string;
  name: string;
  price: number;
  score: number;
  grade: string;
  industry: string;
  is_at_limit: boolean;
  entry_price?: number;
  stop_loss?: number;
  target_price?: number;
  resonance_score?: number;
  hard_tech?: {
    track: string;
    tier: 'core' | 'strategic' | 'supply';
  };
  factor_breakdown?: {
    technical: number;
    fundamental: number;
    money_flow: number;
  };
}

export interface ScreenerRunResponse {
  picks: ScreenerPick[];
  total_scored: number;
  total_excluded: number;
  elapsed: number;
  sector_resonance: SectorResonance[];
  market_env: string;
}
```

### 3.3 错误处理契约

| 状态码 | 后端返回 | 前端处理 | 修复方案 |
|--------|---------|---------|---------|
| 401 | `{detail: "Unauthorized"}` | axios拦截器已处理refresh | ✅ 已修复 |
| 400 | `{detail: "Invalid stock code"}` | `message.error(e.response?.data?.detail)` | ✅ 已处理 |
| 500 | `{detail: "Internal error"}` | 同上 | ✅ 已处理 |
| 服务offline | 无响应（网络错误） | `HealthCheckError` throw | ✅ 已在client.ts实现 |

**现状**：前端已在 `client.ts` 中实现完整的错误处理契约，包括401自动刷新、HealthCheckError语义化错误等。

### 3.4 响应结构一致性

| 服务 | 响应结构 | 前端处理 | 状态 |
|------|---------|---------|------|
| screener | `{picks: [], total_scored, elapsed}` | `r.data.picks` | ✅ 一致 |
| prediction | `{status, predictions, model_path}` | `r.data.predictions` | ✅ 一致 |
| signal | `{signals, summary}` | `r.data.signals` | ✅ 一致 |
| diagnosis | `{dimensions, overall_score}` | `r.data.dimensions` | ✅ 一致 |
| backtest | `{results, windows}` | `r.data.results` | ✅ 一致 |

**现状**：后端响应结构已与前端期望一致，无需修复。

---

## 四、迁移实施计划（三阶段）

### 阶段1：基础设施迁移（1-2周）

**目标**：建立设计系统基础设施，不影响现有功能。

#### 任务清单：

1. **创建设计系统文件**
   - `frontend/src/styles/design-tokens.css` — 25个色彩/字体/布局token
   - `frontend/src/styles/accessibility.css` — focus-visible + reduced-motion
   - `frontend/src/styles/terminal-grid.css` — 终端网格背景
   - `frontend/src/styles/index.css` — 整合以上文件

2. **创建API类型定义**
   - `frontend/src/api/types.ts` — 所有API响应的TypeScript类型
   - 替换 `client.ts` 中的 `any` 为具体类型

3. **创建布局组件**
   - `frontend/src/components/layout/Navigation.tsx` — 三组左侧导航
   - `frontend/src/components/layout/WorkflowNav.tsx` — 顶部工作流导航
   - `frontend/src/components/layout/TradingContextBar.tsx` — 交易上下文条

4. **创建状态组件**
   - `frontend/src/components/ui/StatefulPanel.tsx` — 加载/空/错误态

5. **测试**
   - 验证设计token在所有组件中生效
   - 验证类型定义覆盖所有API调用
   - SIT测试：现有功能无回归

### 阶段2：核心页面迁移（2-3周）

**目标**：按设计文档优先级迁移核心页面。

#### 页面迁移顺序（按设计文档第12节）：

1. **Screener.tsx** — 智能选股（P0最高优先）
   - 套用候选股卡、筛选、空态、加载态
   - 套用策略模式卡联动筛选
   - 套用评分因子分解条
   - 套用批量操作条

2. **Dashboard.tsx** — AI智能看板
   - 套用高密度三列布局
   - 套用服务健康卡
   - 套用市场情绪指标
   - 套用候选池 + K线 + 交易票并排

3. **Predictions.tsx** — K线预测
   - 套用图表、价位标签、研究信号声明
   - 套用等宽数字字体
   - 套用K线预测区三层信息

4. **Signals.tsx** — 交易信号
   - 套用信号来源、置信度、风险状态
   - 套用信号等级标签

5. **Trade.tsx** — 交易中心
   - 套用交易票、风控闸门、二次确认
   - 套用半自动交易票字段（标的/模式/止损线等）
   - 套用风险盒

6. **Backtest.tsx** — 回测分析
   - 套用结果表、失败态、参数复核
   - 套用回测验证流程

#### 每个页面迁移步骤：

1. 替换Ant Design组件为设计系统组件
2. 应用设计token（色彩、字体、布局）
3. 实现完整状态处理（加载、空、错误、当前）
4. 实现可访问性属性（aria-label、aria-current、role）
5. 实现响应式布局（桌面→中等→窄屏→移动）
6. SIT测试 + E2E测试

### 阶段3：次要页面迁移 + 发布（1周）

**目标**：完成次要页面迁移，全系统测试发布。

#### 页面清单：

- Diagnosis.tsx — 个股诊断（五维评分）
- Strategy.tsx — 方案管理
- AutoTrade.tsx — 量化交易
- Training.tsx — 模型训练
- ModelRegistry.tsx — 模型注册
- DataUpdate.tsx — 数据更新
- SupplyChainBom.tsx — 产业链拆解

#### 发布检查：

1. **视觉一致性**：所有页面使用同一套设计token
2. **信息架构一致性**：所有页面左侧导航三组 + 顶部工作流
3. **可访问性合规**：WCAG 2.1 AA级检查
4. **响应式完整性**：1366px/900px/560px断点测试
5. **前后端契约验证**：所有API调用类型正确
6. **性能验证**：首屏加载 < 3s，ECharts按需加载

---

## 五、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **Ant Design组件替换困难** | 延期1-2周 | 优先替换高频组件（Table/Card/Tag），保留低频组件 |
| **设计token与Ant Design冲突** | 样式混乱 | 使用CSS层级覆盖，Ant Design ConfigProvider定制主题 |
| **响应式布局复杂度高** | 延期1周 | 使用媒体查询模板，按设计文档断点直接套用 |
| **可访问性测试不完整** | 合规风险 | 使用axe DevTools自动化检查，配合手工键盘测试 |
| **前后端字段名遗漏** | 显示错误 | 后端 `_normalize_picks()` + 前端类型定义双重保障 |

---

## 六、成功标准

### 6.1 设计系统

- ✅ 所有25个设计token在所有页面生效
- ✅ 左侧导航三组分类 + 顶部工作流导航在所有页面可见
- ✅ A股红涨绿跌色彩惯例在所有行情数据生效
- ✅ 等宽字体在所有价格/涨跌幅/评分生效

### 6.2 可访问性

- ✅ 全局 `:focus-visible` 聚焦环可见
- ✅ 所有输入项有明确 `label for` 或 `aria-label`
- ✅ 所有导航有 `aria-label` + `aria-current`
- ✅ 所有状态变化有 `aria-live` 或 `aria-busy`
- ✅ `prefers-reduced-motion` 媒体查询生效

### 6.3 前后端契约

- ✅ 所有API调用有TypeScript类型定义（无 `any`）
- ✅ 所有错误状态有语义化处理（无通用catch）
- ✅ 所有响应字段名与前端期望一致

### 6.4 测试覆盖

- ✅ SIT测试通过（所有功能无回归）
- ✅ E2E测试通过（核心页面完整流程）
- ✅ axe DevTools可访问性检查通过（WCAG 2.1 AA级）
- ✅ 响应式测试通过（1366px/900px/560px断点）

---

## 七、附录：设计文档禁用清单（第11节）

以下模式**不得**出现在速赢AI交付稿中：

- ❌ 紫蓝渐变英雄区
- ❌ 营销页式大标题和大留白
- ❌ 装饰性卡片堆叠
- ❌ 表情符号图标
- ❌ 设计器控制面板
- ❌ 只靠toast承载错误
- ❌ 虚构收益率/胜率/无来源夸张指标
- ❌ 左侧彩色边框加圆角卡片的模板式信息块
- ❌ 把A股涨跌色做反（红跌绿涨）
- ❌ 把产品导航做成演示用平台切换器

---

## 八、参考文档

- `docs/design/new front/design-spec.md` — 设计规范权威来源
- `docs/design/new front/suying-ai-workbench-redesign.html` — 主工作台原型
- `docs/design/new front/screener.html` — 智能选股原型
- `docs/design/new front/assets/app.css` — 设计系统CSS
- `frontend/src/api/client.ts` — 现有API客户端
- `services/screener-service/app/routers/screener.py` — 后端选股API

---

**文档维护**：本文档随迁移进度更新，每个阶段完成后标记 ✅ 并记录实际耗时。