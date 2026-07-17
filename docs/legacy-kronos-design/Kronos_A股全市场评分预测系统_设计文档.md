# Kronos A股全市场智能评分预测系统 — 架构与详细设计

> 基于 Kronos K线大模型 + 多因子量化评分 + 现有优化架构
> 文档版本：v1.0 | 日期：2026-05-29

---

# 第一部分：流程与架构大纲

## 1. 系统愿景

在现有 Kronos WebUI 架构基础上，构建 **A股全市场智能评分 → Top40精选 → K线预测 → 操作建议** 的完整投资决策辅助系统。

## 2. 核心处理流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    A股全市场智能评分预测流程                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Phase 1: 全市场数据采集 (Scheduler 定时/手动触发)        │     │
│  │  ├── akshare 获取全A股列表 (~5000只)                     │     │
│  │  ├── 逐只获取日线数据 (open/high/low/close/volume/amount)│     │
│  │  ├── 基本面数据 (PE/PB/市值/换手率)                       │     │
│  │  └── 存入 stock_screening.db (SQLite)                    │     │
│  └────────────────────────────────────────────────────────┘     │
│        ↓                                                         │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Phase 2: 多因子智能评分 (Screener Engine)               │     │
│  │  ├── 五因子量化评分 (M动量/V量能/T技术/Q质量/R风险)       │     │
│  │  ├── Kronos 趋势预测评分 (短期K线预测 → 趋势方向打分)     │     │
│  │  ├── 综合评分 = 五因子×0.5 + Kronos趋势×0.3 + 基本面×0.2 │     │
│  │  ├── 操作建议生成 (强烈买入/买入/观望/规避)               │     │
│  │  └── 排序 → Top40 精选股票池                              │     │
│  └────────────────────────────────────────────────────────┘     │
│        ↓                                                         │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Phase 3: 深度K线预测 (Kronos Predictor)                 │     │
│  │  ├── Top40 股票逐只加载最近400天日线                      │     │
│  │  ├── Kronos-base 预测未来60天K线 (OHLCV完整)             │     │
│  │  ├── 批量并行预测 (predict_batch)                        │     │
│  │  └── 预测结果持久化到 prediction_results/                │     │
│  └────────────────────────────────────────────────────────┘     │
│        ↓                                                         │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Phase 4: 前端展示 (Dashboard)                           │     │
│  │  ├── 市场全景面板 (指数/A股总数/评分分布/板块热力图)       │     │
│  │  ├── Top40 排行表 (评分/等级/操作建议/趋势预测/收益率)     │     │
│  │  ├── 个股详情 (五因子拆解 + Kronos预测K线图 + 建议)       │     │
│  │  ├── 预测对比 (多股预测K线叠加对比)                       │     │
│  │  └── 历史回溯 (过去筛选结果 vs 实际表现)                   │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        展示层 (Frontend)                         │
│  dashboard.html  —  React SPA / 原生 Tab 架构                    │
│  ├── 📊 市场全景    ├── 🏆 Top40排行   ├── 🔍 个股深度          │
│  ├── 📈 K线预测     ├── 📋 历史回溯    └── ⚙️ 系统设置          │
├─────────────────────────────────────────────────────────────────┤
│                      API 层 (Routes)                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │screener  │ │predict   │ │portfolio │ │history   │          │
│  │_routes   │ │_routes   │ │_routes   │ │_routes   │          │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
├───────┴────────────┴────────────┴────────────┴─────────────────┤
│                        安全层 (auth.py)                          │
├─────────────────────────────────────────────────────────────────┤
│                       服务层 (Services)                          │
│  ┌──────────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ ScreenerService  │ │Predictor     │ │ PortfolioService   │  │
│  │ • 全市场评分      │ │Service       │ │ • Top40管理        │  │
│  │ • 五因子模型      │ │ • Kronos预测  │ │ • 历史追踪         │  │
│  │ • Kronos趋势打分  │ │ • 批量并行    │ │ • 绩效统计         │  │
│  │ • 综合排名        │ │ • 结果缓存    │ │                   │  │
│  └────────┬─────────┘ └──────┬───────┘ └────────┬──────────┘  │
│           │                  │                   │              │
├───────────┴──────────────────┴───────────────────┴──────────────┤
│                       数据层 (Database)                          │
│  ┌────────────────────────────────────────────────────────┐     │
│  │              stock_screening.db (SQLite)                 │     │
│  │  stocks │ scores │ picks │ predictions │ history │      │     │
│  └────────────────────────────────────────────────────────┘     │
├─────────────────────────────────────────────────────────────────┤
│                      模型核心层 (Model)                           │
│  KronosTokenizer → Kronos (自回归Transformer) → KronosPredictor │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 文档结构大纲

### 第一部分：流程与架构大纲 (本文)

### 第二部分：详细设计
- **2.1 前端架构设计** — 页面结构、组件树、数据流、交互设计、技术选型
- **2.2 数据库设计** — 完整DDL、ER图、索引策略、数据量估算
- **2.3 全市场评分引擎设计** — 五因子模型参数、Kronos趋势评分、综合加权公式、操作建议规则
- **2.4 预测模型设计** — Kronos批量预测管线、Top40筛选流程、缓存策略
- **2.5 API接口设计** — 完整接口定义、请求/响应格式、错误码
- **2.6 定时调度设计** — 全市场扫描频率、增量更新策略、交易日历

### 第三部分：实施路线图

---

# 第二部分：详细设计

## 2.1 前端架构设计

### 2.1.1 技术选型

| 决策 | 选择 | 理由 |
|------|------|------|
| 框架 | **原生 JS + Tab 架构** (与智能看板一致) | 零依赖、快速迭代、与现有项目风格统一 |
| K线图 | **ECharts 5** (替代 Canvas 自绘) | 更专业的金融图表、内置 Candlestick + 技术指标 |
| 数据交互 | Fetch API + 轮询 (大盘) + WebSocket (预测进度) | 实时性 + 简洁性 |
| 样式 | 内联 CSS + CSS Variables (暗色主题) | 与智能看板风格一致 |

### 2.1.2 页面结构

```
dashboard.html
├── Header
│   ├── 系统标题 "Kronos A股智能评分预测系统"
│   ├── 市场状态指示器 (🟢交易中 / 🔴已收盘)
│   ├── 数据更新时间 + 倒计时
│   └── 用户信息 + 设置按钮
│
├── Ticker Bar (涨停股票滚动条)
│
├── Tab Navigation
│   ├── 📊 市场全景 (market)
│   ├── 🏆 Top40 精选 (top40)
│   ├── 🔍 个股深度 (stock)
│   ├── 📈 K线预测 (predict)
│   ├── 📋 历史回溯 (history)
│   └── ⚙️ 系统设置 (settings)
│
└── Tab Content
```

### 2.1.3 Tab 详细设计

#### Tab 1: 📊 市场全景

```
┌──────────────────────────────────────────────────────────┐
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │ 上证指数     │ │ 深证成指     │ │ 创业板指     │        │
│  │ 3,250.50    │ │ 11,200.30   │ │ 2,150.80    │        │
│  │ +0.85% 🟢   │ │ -0.32% 🔴   │ │ +1.20% 🟢   │        │
│  └─────────────┘ └─────────────┘ └─────────────┘        │
│                                                          │
│  ┌──────────────────────┐ ┌──────────────────────────┐  │
│  │ 评分分布饼图           │ │ 板块热力图                │  │
│  │ S: 12 | A: 45 |       │ │ 银行 ████████ 12只      │  │
│  │ B: 230 | C: 4723      │ │ 半导体 ██████ 8只        │  │
│  │                       │ │ 医药 █████ 6只           │  │
│  └──────────────────────┘ └──────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ 评分摘要                                          │   │
│  │ 全市场: 5,012只 | 已评分: 4,980只 | S级: 12 |     │   │
│  │ A级: 45 | 均分: 8.5 | 更新: 2026-05-29 15:00    │   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

#### Tab 2: 🏆 Top40 精选 (核心Tab)

```
┌──────────────────────────────────────────────────────────────────┐
│ 筛选栏: [模型: 短线 ▼] [板块: 全部 ▼] [排序: 综合评分 ▼]        │
│ [🔄 重新筛选] [📥 导出CSV] [📊 批量预测]                        │
├──────────────────────────────────────────────────────────────────┤
│ # │ 代码    │ 名称    │ 评分 │ 等级 │ 操作建议  │ 预期收益 │ 趋势 │
├───┼─────────┼─────────┼──────┼──────┼───────────┼──────────┼──────┤
│ 1 │ 000001  │ 平安银行 │ 18.5 │  S   │ 🔥强烈买入 │ +12.3%  │ 📈  │
│ 2 │ 600519  │ 贵州茅台 │ 17.2 │  S   │ 🔥强烈买入 │ +8.5%   │ 📈  │
│ 3 │ 300750  │ 宁德时代 │ 16.8 │  S   │ ✔️ 买入    │ +15.2%  │ 📈  │
│...│  ...    │  ...    │ ...  │ ...  │  ...      │  ...    │ ... │
│40 │ 002594  │ 比亚迪   │ 12.1 │  A   │ ✔️ 买入    │ +5.1%   │ 📈  │
├───┴─────────┴─────────┴──────┴──────┴───────────┴──────────┴──────┤
│ 详情面板 (点击行展开):                                            │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ 平安银行(000001) — 评分 18.5/S                                │ │
│ │ M:▇▇▇▇▇▇▇ 7/8 | V:▇▇▇▇▇▇ 6/7 | T:▇▇▇▇ 4/5 | Q:▇▇ 2/3 | R:+0.5│ │
│ │ 操作建议: 🔥强烈买入 — 五因子共振，趋势向上，量价配合良好         │ │
│ │ Kronos预测收益: +12.3% | 目标价: 14.20 | 止损价: 11.80        │ │
│ │ [📈 查看K线预测] [➕ 加入自选] [📋 查看详情]                    │ │
│ └──────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

#### Tab 3: 🔍 个股深度

```
┌──────────────────────────────────────────────────────────┐
│ 输入框: [股票代码] [🔍 分析]                               │
├──────────────────────────────────────────────────────────┤
│ 左栏 (60%)                          │ 右栏 (40%)         │
│ ┌────────────────────────────┐      │ 基本信息            │
│ │ ECharts 交互K线图           │      │ 价格: 12.50        │
│ │ • 日/周/月K切换             │      │ 涨跌: +5.2%        │
│ │ • MA/布林带叠加             │      │ PE: 6.2            │
│ │ • Kronos预测区间 (阴影)      │      │ PB: 1.8            │
│ │ • 十字光标悬停              │      │ 市值: 2800亿       │
│ └────────────────────────────┘      │ 换手率: 3.5%       │
│                                      ├───────────────────│
│ ┌────────────────────────────┐      │ 五因子评分          │
│ │ MACD/RSI/KDJ 副图          │      │ M:▇▇▇▇▇▇▇ 7/8     │
│ │ + 成交量柱状图              │      │ V:▇▇▇▇▇▇ 6/7      │
│ └────────────────────────────┘      │ T:▇▇▇▇ 4/5         │
│                                      │ Q:▇▇ 2/3           │
│ ┌────────────────────────────┐      │ R:+0.5             │
│ │ 操作建议卡片                 │      ├───────────────────│
│ │ 🔥 强烈买入                 │      │ Kronos预测         │
│ │ 趋势向上，量价配合，         │      │ 60天收益: +12.3%   │
│ │ PE合理，建议分批建仓         │      │ 目标价: 14.20      │
│ │ 目标: 14.20 止损: 11.80    │      │ 止损价: 11.80      │
│ └────────────────────────────┘      │                     │
└──────────────────────────────────────────┴─────────────────┘
```

#### Tab 4: 📈 K线预测 (批量)

```
┌──────────────────────────────────────────────────────────┐
│ 选择股票: [☑ 全选] [Top10] [Top20] [Top40]               │
│ 预测参数: 天数[60 ▼] 温度[1.0] top_p[0.9] 路径[5]         │
│ [🚀 开始预测] [📊 对比视图]                                │
├──────────────────────────────────────────────────────────┤
│ 预测进度: ████████████░░░░ 25/40 (webSocket 实时推送)     │
│                                                          │
│ 预测结果网格 (2×2 or 3×3):                                │
│ ┌─────────────────┐ ┌─────────────────┐                  │
│ │ 平安银行(000001) │ │ 贵州茅台(600519) │                  │
│ │ 预测K线图(小)    │ │ 预测K线图(小)    │                  │
│ │ 收益率: +12.3%   │ │ 收益率: +8.5%   │                  │
│ └─────────────────┘ └─────────────────┘                  │
│ ┌─────────────────┐ ┌─────────────────┐                  │
│ │ 宁德时代(300750) │ │ 比亚迪(002594)  │                  │
│ │ 预测K线图(小)    │ │ 预测K线图(小)    │                  │
│ │ 收益率: +15.2%   │ │ 收益率: +5.1%   │                  │
│ └─────────────────┘ └─────────────────┘                  │
│                                                          │
│ [点击任一卡片 → 放大到 Tab3 个股深度]                       │
└──────────────────────────────────────────────────────────┘
```

#### Tab 5: 📋 历史回溯

```
┌──────────────────────────────────────────────────────────┐
│ 日期选择: [2026-05-22 ▼] [🔄 加载]                       │
├──────────────────────────────────────────────────────────┤
│ 历史筛选表现:                                             │
│ ┌────────────────────────────────────────────────────┐  │
│ │ 日期: 2026-05-22 | Top40 筛选结果 vs 实际表现        │  │
│ │                                                    │  │
│ │ Top40 平均收益率: +3.2% | 同期沪深300: +1.1%        │  │
│ │ 超额收益: +2.1%                                     │  │
│ │                                                    │  │
│ │ 表格: 排名 │ 代码 │ 名称 │ 筛选评分 │ 实际收益 │ 命中 │  │
│ │      1  │000001│平安银行│ 18.5/S  │ +5.2%   │ ✅  │  │
│ │      2  │600519│贵州茅台│ 17.2/S  │ -1.3%   │ ❌  │  │
│ │      ...│ ...  │ ...   │ ...     │ ...     │ ... │  │
│ └────────────────────────────────────────────────────┘  │
│                                                          │
│ 累计表现曲线 (ECharts 折线图):                             │
│ ┌────────────────────────────────────────────────────┐  │
│ │ Top40累计收益 vs 沪深300基准                          │  │
│ │ (多日期对比折线图)                                    │  │
│ └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 2.1.4 数据流设计

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ 用户操作  │────▶│ API 请求      │────▶│ Service 处理  │
│ (点击/输入)│     │ (fetch/ws)   │     │ (评分/预测)   │
└──────────┘     └──────────────┘     └──────┬───────┘
                                             │
                    ┌────────────────────────┘
                    ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐
│ UI 更新   │◀────│ JSON 响应    │◀────│ 结果缓存/    │
│ (DOM渲染) │     │ (data/chart) │     │ DB持久化     │
└──────────┘     └──────────────┘     └──────────────┘

WebSocket 通道 (预测进度):
  Server ──ws──▶ Client: {"type":"progress","current":25,"total":40,"stock":"000001"}
  Server ──ws──▶ Client: {"type":"complete","results":[...]}
```

### 2.1.5 前端核心技术点

```javascript
// 1. ECharts K线图渲染
const chart = echarts.init(canvas);
chart.setOption({
    xAxis: { data: dates },
    yAxis: { scale: true },
    series: [
        { type: 'candlestick', data: ohlcData },  // 历史K线
        { type: 'candlestick', data: predData,     // 预测K线
          itemStyle: { color: '#66BB6A', borderColor: '#66BB6A',
                       color0: '#FF7043', borderColor0: '#FF7043' }},
        { type: 'line', data: ma5Data, ... },      // MA均线
    ]
});

// 2. WebSocket 预测进度
const ws = new WebSocket(`ws://${host}:${port}/ws/predict`);
ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'progress') updateProgressBar(msg);
    if (msg.type === 'complete') renderResults(msg.results);
};

// 3. Tab 切换 + 埋点
function switchTab(name) {
    document.querySelectorAll('.tab-content').forEach(t => t.style.display = 'none');
    document.getElementById(`tab-${name}`).style.display = 'block';
    trackEvent('tab_switch', 'dashboard', name);
}

// 4. 自动轮询大盘数据 (30s间隔)
setInterval(() => fetch('/api/market/summary').then(updateMarketPanel), 30000);
```

---

## 2.2 数据库设计

### 2.2.1 数据库选型

**SQLite 3** — `stock_screening.db`

理由：与智能看板项目一致，零配置、单机足够。全市场5000只股票日频数据量可控。

### 2.2.2 完整DDL

```sql
-- ============================================================
-- 1. 股票基础信息表
-- ============================================================
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,              -- 股票代码 e.g. '000001'
    name TEXT NOT NULL,                 -- 股票名称
    board TEXT NOT NULL,                -- 板块 (沪市主板/深市主板/创业板/科创板/北交所)
    industry TEXT,                      -- 申万一级行业
    market_cap REAL,                    -- 总市值(亿)
    float_mv REAL,                      -- 流通市值(亿)
    pe_ratio REAL,                      -- 市盈率
    pb_ratio REAL,                      -- 市净率
    listed_date TEXT,                   -- 上市日期
    is_st INTEGER DEFAULT 0,            -- 是否ST (0/1)
    updated_at TEXT                     -- 数据更新时间
);
CREATE INDEX IF NOT EXISTS idx_stocks_board ON stocks(board);
CREATE INDEX IF NOT EXISTS idx_stocks_industry ON stocks(industry);

-- ============================================================
-- 2. 日线行情数据表
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_kline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    trade_date TEXT NOT NULL,           -- 交易日期 YYYY-MM-DD
    open REAL, high REAL, low REAL, close REAL,
    volume REAL,                        -- 成交量(股)
    amount REAL,                        -- 成交额(元)
    turnover_rate REAL,                 -- 换手率(%)
    change_pct REAL,                    -- 涨跌幅(%)
    amplitude REAL,                     -- 振幅(%)
    UNIQUE(code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_daily_kline_code ON daily_kline(code);
CREATE INDEX IF NOT EXISTS idx_daily_kline_date ON daily_kline(trade_date);
CREATE INDEX IF NOT EXISTS idx_daily_kline_code_date ON daily_kline(code, trade_date);

-- ============================================================
-- 3. 评分结果表 (每轮筛选的核心输出)
-- ============================================================
CREATE TABLE IF NOT EXISTS screening_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,             -- 批次ID (YYYYMMDD-HHMMSS)
    code TEXT NOT NULL,
    score REAL NOT NULL,                -- 综合评分 (0~25)
    grade TEXT NOT NULL,                -- 等级 (S/A/B/C)
    -- 五因子拆解
    momentum REAL,                      -- M动量 (0~8)
    volume_factor REAL,                 -- V量能 (0~7)
    technical REAL,                     -- T技术 (0~5)
    quality REAL,                       -- Q质量 (0~3)
    risk REAL,                          -- R风险 (-3~0)
    -- Kronos趋势评分
    kronos_trend_score REAL,            -- Kronos预测趋势得分
    kronos_pred_return REAL,            -- Kronos预测收益率(%)
    -- 基本面
    fund_score REAL,                    -- 基本面得分
    -- 综合
    signal TEXT,                        -- 操作建议 (强烈买入/买入/观望/规避)
    reason TEXT,                        -- 核心逻辑 (2-3句)
    strategy TEXT,                      -- 操作策略
    target_price REAL,                  -- 目标价
    stop_loss REAL,                     -- 止损价
    -- 元数据
    rank INTEGER,                       -- 排名
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_scores_batch ON screening_scores(batch_id);
CREATE INDEX IF NOT EXISTS idx_scores_code ON screening_scores(code);
CREATE INDEX IF NOT EXISTS idx_scores_rank ON screening_scores(batch_id, rank);

-- ============================================================
-- 4. 批次记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS screening_batches (
    batch_id TEXT PRIMARY KEY,          -- 批次ID
    total_stocks INTEGER,               -- 全市场股票总数
    scored_stocks INTEGER,              -- 成功评分数量
    top40_codes TEXT,                   -- Top40股票代码JSON数组
    elapsed REAL,                       -- 耗时(秒)
    status TEXT,                        -- running/completed/failed
    error_msg TEXT,                     -- 错误信息
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

-- ============================================================
-- 5. 预测结果表
-- ============================================================
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    code TEXT NOT NULL,
    pred_len INTEGER,                   -- 预测天数
    lookback INTEGER,                   -- 历史窗口
    -- 预测概要
    last_close REAL,                    -- 最后收盘价
    pred_last_close REAL,               -- 预测最后收盘价
    pred_return_pct REAL,               -- 预测收益率(%)
    pred_max REAL,                      -- 预测最高价
    pred_min REAL,                      -- 预测最低价
    -- 预测OHLCV完整JSON (60天×6列)
    pred_data_json TEXT,
    -- 参数
    temperature REAL, top_p REAL, sample_count INTEGER,
    elapsed REAL,                       -- 推理耗时
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_predictions_batch ON predictions(batch_id);
CREATE INDEX IF NOT EXISTS idx_predictions_code ON predictions(code);

-- ============================================================
-- 6. 历史回溯表
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,             -- 关联筛选批次
    code TEXT NOT NULL,
    rank INTEGER,                       -- 当时排名
    score REAL,                        -- 当时评分
    signal TEXT,                        -- 当时建议
    pred_return REAL,                   -- 当时预测收益
    -- 实际表现 (N天后回填)
    actual_return_5d REAL,              -- 5日后实际收益
    actual_return_10d REAL,             -- 10日后实际收益
    actual_return_20d REAL,             -- 20日后实际收益
    actual_return_60d REAL,             -- 60日后实际收益
    hit INTEGER,                        -- 方向是否正确 (1/0)
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_backtest_batch ON backtest_records(batch_id);

-- ============================================================
-- 7. 用户自选表 (复用智能看板设计)
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT,
    added_at TEXT DEFAULT (datetime('now','localtime')),
    notes TEXT
);
```

### 2.2.3 ER 关系图

```
stocks (code PK) ──────< daily_kline (code, trade_date)
  │
  ├──< screening_scores (code, batch_id)
  │       │
  │       └── screening_batches (batch_id PK)
  │
  ├──< predictions (code, batch_id)
  │
  ├──< backtest_records (code, batch_id)
  │
  └──< watchlist (code)

每日数据流:
stocks ──→ ScreenerService ──→ screening_scores ──→ Top40
                                    │
                                    ▼
                              predictions (Kronos预测)
                                    │
                                    ▼
                              backtest_records (历史回溯)
```

### 2.2.4 数据量估算

| 表 | 初始量 | 日增量 | 年增长 |
|------|:---:|:---:|:---:|
| stocks | ~5,000 | +5 | ~6,800 |
| daily_kline | ~2,500,000 (500天×5000股) | +5,000 | +1,250,000 |
| screening_scores | - | +5,000/批 | 取决于筛选频率 |
| screening_batches | - | +1/批 | 取决于筛选频率 |
| predictions | - | +40/批 | +10,000 (每日) |
| backtest_records | - | +40/批 | +10,000 (每日) |

> SQLite 单文件可承载亿级数据，5年内无需迁移。

---

## 2.3 全市场评分引擎设计

### 2.3.1 五因子量化评分模型 (继承智能看板)

与 `A股智能看板` 的五因子模型完全一致，确保评分口径统一：

| 因子 | 权重范围 | 核心评估逻辑 |
|------|:---:|------|
| **M 动量** | 0~8 | 涨跌幅绝对值、日内强弱、趋势延续性、均线排列 |
| **V 量能** | 0~7 | 换手率合理性、量比、量价配合确认 |
| **T 技术** | 0~5 | 日内振幅、收盘位置、MACD/RSI/KDJ信号 |
| **Q 质量** | 0~3 | 流通市值、PE估值、PB、量价效率 |
| **R 风险** | -3~0 | 极端换手/振幅惩罚、小市值风险、量价背离 |

```python
# 综合得分
Score_5Factor = clamp(M + V + T + Q + R, 0, 25)

# 等级判定
Grade = "S" if Score >= 16 else "A" if Score >= 12 else "B" if Score >= 7 else "C"
```

### 2.3.2 Kronos 趋势评分 (新增)

对全市场股票运行 Kronos-mini (4.1M参数, 快速) 短期预测，提取趋势信号：

```python
def kronos_trend_score(code: str, df: pd.DataFrame) -> dict:
    """
    用 Kronos-mini 预测未来20天K线，提取趋势评分

    输入:
        df: 最近400天日线数据
    输出:
        {
            "trend_score": 0~10,       # 趋势评分
            "pred_return": float,       # 预测20天收益率(%)
            "trend_direction": "up/down/sideways",
            "volatility": float,        # 年化波动率
            "confidence": 0~1          # 预测置信度
        }
    """
    # 1. 数据准备
    x_df = df.iloc[-400:][['open','high','low','close','volume','amount']]
    x_ts = df.iloc[-400:]['date']
    y_ts = pd.bdate_range(df['date'].iloc[-1]+pd.Timedelta(days=1), periods=20)

    # 2. Kronos-mini 快速预测 (比base快5x)
    pred_df = kronos_mini_predictor.predict(
        x_df, x_ts, y_ts, pred_len=20,
        T=1.0, top_p=0.9, sample_count=3
    )

    # 3. 趋势评分计算
    last_close = df['close'].iloc[-1]
    pred_last = pred_df['close'].iloc[-1]
    pred_return = (pred_last / last_close - 1) * 100

    # 趋势得分 (0~10)
    trend_score = 5.0  # 基础分

    # 预测涨幅贡献
    if pred_return > 10: trend_score += 3
    elif pred_return > 5: trend_score += 2
    elif pred_return > 0: trend_score += 1
    elif pred_return < -10: trend_score -= 3
    elif pred_return < -5: trend_score -= 2
    elif pred_return < 0: trend_score -= 1

    # 趋势一致性贡献
    pred_trend = np.polyfit(range(20), pred_df['close'].values, 1)[0]
    if pred_trend > 0: trend_score += 1
    else: trend_score -= 1

    # 波动率惩罚
    volatility = pred_df['close'].pct_change().std() * np.sqrt(252)
    if volatility > 0.5: trend_score -= 2
    elif volatility > 0.3: trend_score -= 1

    trend_score = max(0, min(10, trend_score))
    direction = "up" if pred_return > 2 else ("down" if pred_return < -2 else "sideways")

    return {
        "trend_score": round(trend_score, 1),
        "pred_return": round(pred_return, 2),
        "trend_direction": direction,
        "volatility": round(volatility, 2),
        "confidence": 0.8 if volatility < 0.3 else (0.6 if volatility < 0.5 else 0.4)
    }
```

### 2.3.3 基本面评分

```python
def fundamental_score(stock_info: dict) -> float:
    """
    基本面评分 (0~10)

    评估维度:
    - PE估值: PE 0~20 → +3, 20~40 → +1, >100 or <0 → -1
    - PB估值: PB 0~3 → +2, 3~6 → +1
    - 市值: >500亿 → +2, 100~500 → +1, <30 → -1
    - 非ST: +1
    - 有PE数据: +1 (排除亏损无法估值)
    """
    score = 5.0
    pe = stock_info.get("pe_ratio", 0) or 0
    pb = stock_info.get("pb_ratio", 0) or 0
    mv = stock_info.get("float_mv", 0) or 0
    is_st = stock_info.get("is_st", 0)

    if 0 < pe <= 20: score += 3
    elif 20 < pe <= 40: score += 1
    elif pe > 100 or pe < 0: score -= 1

    if 0 < pb <= 3: score += 2
    elif 3 < pb <= 6: score += 1

    if mv > 500: score += 2
    elif mv > 100: score += 1
    elif mv < 30: score -= 1

    if not is_st: score += 1
    if pe > 0: score += 1

    return max(0, min(10, score))
```

### 2.3.4 综合评分公式

```python
# 综合评分 = 五因子×0.5 + Kronos趋势×0.3 + 基本面×0.2
# 归一化到25分制

Final_Score = (
    Score_5Factor * 0.5 +          # 0~25 → 0~12.5
    Kronos_Trend_Score * 2.5 +     # 0~10 → 0~25 → ×0.3 → 0~7.5
    Fund_Score * 2.5               # 0~10 → 0~25 → ×0.2 → 0~5
)  # 最终: 0~25
```

### 2.3.5 操作建议生成规则

```python
def generate_signal(final_score, five_factor, kronos_trend, fund):
    """
    操作建议生成矩阵:

    五因子\Kronos趋势 | 看涨(>2%) | 中性(-2~2%) | 看跌(<-2%)
    ─────────────────┼───────────┼────────────┼──────────
    S级 (≥16)        | 🔥强烈买入 | ✔️ 买入     | ⏳ 观望
    A级 (12~15)      | ✔️ 买入   | ⏳ 观望     | ❌ 规避
    B级 (7~11)       | ⏳ 观望   | ⏳ 观望     | ❌ 规避
    C级 (<7)         | ⏳ 观望   | ❌ 规避     | ❌ 规避
    """
    grade = five_factor["grade"]
    trend_dir = kronos_trend["trend_direction"]

    if grade == "S" and trend_dir == "up":
        signal = "🔥 强烈买入"
    elif grade in ("S", "A") and trend_dir in ("up", "sideways"):
        signal = "✔️ 买入"
    elif grade == "S" and trend_dir == "down":
        signal = "⏳ 观望（等企稳）"
    elif grade == "A" and trend_dir == "down":
        signal = "❌ 规避"
    elif grade == "B" and trend_dir == "up":
        signal = "⏳ 观望（等确认）"
    elif grade == "C" and trend_dir == "up":
        signal = "⏳ 观望（信号弱）"
    else:
        signal = "❌ 规避"

    return signal
```

---

## 2.4 预测模型设计

### 2.4.1 两级模型架构

```
全市场评分阶段 (5000只):
  └── Kronos-mini (4.1M, 2048上下文)
      • 每只预测20天
      • 快速模式: T=1.0, top_p=0.9, sample_count=3
      • 单只耗时: ~2s (MPS)
      • 全市场: 可行分批执行 (5000只×2s ≈ 3小时，可每日盘后运行)

Top40深度预测阶段 (40只):
  └── Kronos-base (102M, 512上下文)
      • 每只预测60天
      • 高质量模式: T=1.0, top_p=0.9, sample_count=5
      • 单只耗时: ~8s (MPS)
      • 40只总耗时: ~5分钟
```

### 2.4.2 评分阶段优化策略

```python
# 全市场5000只股票评分 → 不可能全部跑Kronos-mini (太慢)
# 采用分层策略:

Layer 1: 五因子快速初筛 (全部5000只)
  ├── 仅需日线数据，纯数学计算
  ├── 过滤: Score >= 7 (B级以上)
  └── 输出: ~300只候选

Layer 2: Kronos-mini 趋势评分 (300只候选)
  ├── 批量预测，每只20天
  ├── 耗时: 300×2s ≈ 10分钟
  └── 输出: 综合评分 + 排序

Layer 3: Kronos-base 深度预测 (Top40)
  ├── 高精度60天预测
  ├── 耗时: 40×8s ≈ 5分钟
  └── 输出: 完整OHLCV预测

总耗时: ~15分钟 (盘后执行)
```

### 2.4.3 并行预测管线

```python
class BatchPredictionPipeline:
    """Top40 并行预测管线"""

    def __init__(self, predictor_service, websocket=None):
        self.svc = predictor_service
        self.ws = websocket  # 实时推送进度

    async def run(self, top40_codes: list[str], data_dir: str):
        """并行预测 Top40 股票"""
        results = []
        total = len(top40_codes)

        for i, code in enumerate(top40_codes):
            # 推送进度
            if self.ws:
                self.ws.emit('progress', {
                    'current': i + 1, 'total': total, 'code': code
                })

            # 加载数据 + 预测 (支持缓存)
            df = DataService.load(f"{data_dir}/{code}.csv")
            pred_df = self.svc.predict(df, ...)

            results.append({
                'code': code,
                'prediction': pred_df.to_dict('records'),
                'summary': {...}
            })

        # 推送完成
        if self.ws:
            self.ws.emit('complete', {'results': results})

        return results
```

---

## 2.5 API 接口设计

### 2.5.1 新增接口总览

| 路由 | 方法 | 认证 | 说明 |
|------|:---:|:---:|------|
| **筛选相关** | | | |
| `/api/screen/run` | POST | req | 启动全市场筛选 (异步) |
| `/api/screen/status` | GET | req | 查询筛选进度 |
| `/api/screen/result` | GET | req | 获取最新筛选结果 (Top40) |
| `/api/screen/batches` | GET | req | 历史筛选批次列表 |
| `/api/screen/batch/<id>` | GET | req | 指定批次详情 |
| **预测相关** | | | |
| `/api/predict/batch` | POST | req | 批量预测 (指定股票列表) |
| `/api/predict/stock/<code>` | GET | req | 单只股票深度预测 |
| `/api/predict/compare` | POST | req | 多股预测对比 |
| **市场数据** | | | |
| `/api/market/summary` | GET | - | 市场全景摘要 |
| `/api/market/indices` | GET | - | 四大指数实时行情 |
| **历史回溯** | | | |
| `/api/backtest/batch/<id>` | GET | req | 批次回溯结果 |
| `/api/backtest/performance` | GET | req | 累计绩效统计 |
| **自选管理** | | | |
| `/api/watchlist` | GET/POST/DELETE | req | 自选股CRUD |
| **WebSocket** | | | |
| `/ws/predict` | WS | req | 预测进度实时推送 |

### 2.5.2 核心接口详细定义

#### POST /api/screen/run

```json
// 请求
{
    "mode": "full",              // full(全市场) | top300(仅Kronos趋势评分)
    "model": "kronos-mini",      // 趋势评分模型
    "use_cache": true,           // 使用已有日线缓存
    "top_n": 40                  // 输出Top数量
}

// 响应 (202 Accepted)
{
    "batch_id": "20260529-150000",
    "status": "started",
    "estimated_minutes": 15,
    "message": "全市场筛选已启动，预计15分钟完成"
}
```

#### POST /api/predict/batch

```json
// 请求
{
    "codes": ["000001","600519","300750",...],
    "model": "kronos-base",
    "pred_len": 60,
    "temperature": 1.0,
    "top_p": 0.9,
    "sample_count": 5
}

// 响应
{
    "success": true,
    "results": [
        {
            "code": "000001",
            "name": "平安银行",
            "last_close": 12.50,
            "pred_last_close": 14.03,
            "pred_return_pct": 12.24,
            "pred_max": 14.80,
            "pred_min": 12.20,
            "trend": "up",
            "prediction": [
                {"timestamp":"2026-05-30","open":12.60,...},
                ...
            ],
            "elapsed": 8.2
        },
        ...
    ]
}
```

#### GET /api/market/summary

```json
// 响应
{
    "indices": {
        "shanghai": {"price": 3250.50, "change_pct": 0.85},
        "shenzhen": {"price": 11200.30, "change_pct": -0.32},
        "chinext": {"price": 2150.80, "change_pct": 1.20},
        "star": {"price": 980.50, "change_pct": 0.45}
    },
    "screening": {
        "last_batch_id": "20260529-150000",
        "total_scored": 4980,
        "grade_distribution": {"S":12,"A":45,"B":230,"C":4693},
        "avg_score": 8.5,
        "updated_at": "2026-05-29T15:00:00"
    },
    "top40_summary": {
        "avg_pred_return": 8.3,
        "bullish_count": 32,
        "bearish_count": 8
    }
}
```

---

## 2.6 定时调度设计

### 2.6.1 调度策略

```
┌─────────────────────────────────────────────────┐
│  每日调度时间表 (A股交易日)                        │
├─────────────────────────────────────────────────┤
│  15:05  收盘后5分钟                               │
│    ├── 获取全市场日线数据 (akshare增量更新)         │
│    ├── 同步股票基本信息 (新上市/退市/ST变更)         │
│    └── 五因子快速初筛 (全市场5000只, 纯计算)        │
│                                                   │
│  15:15  Kronos-mini 趋势评分                       │
│    ├── 对~300只B级以上候选股运行Kronos-mini         │
│    └── 计算综合评分 + 排序                          │
│                                                   │
│  15:30  Kronos-base 深度预测                       │
│    ├── 对Top40精选股运行Kronos-base 60天预测        │
│    └── 生成操作建议 + 目标价/止损价                  │
│                                                   │
│  16:00  结果入库 + 前端可查                         │
│    ├── screening_scores 写入                       │
│    ├── predictions 写入                            │
│    └── backtest_records 回溯更新 (N天前预测vs实际)   │
│                                                   │
│  次日 09:00  盘前更新                              │
│    ├── 刷新实时价格                                 │
│    └── 更新 Top40 当前涨跌幅                        │
└─────────────────────────────────────────────────┘
```

### 2.6.2 增量更新策略

```python
class ScreeningScheduler:
    """
    定时调度器 — 基于 APScheduler 或 threading.Timer

    配置:
        SCREENING_SCHEDULE: "15:05"  # 盘后自动筛选
        DATA_UPDATE_SCHEDULE: "09:00,15:05"  # 数据更新
    """

    def daily_screening_job(self):
        """每日盘后筛选任务"""
        logger.info("Starting daily screening...")
        batch_id = datetime.now().strftime("%Y%m%d-%H%M%S")

        # Step 1: 增量更新日线数据
        last_date = db.query("SELECT MAX(trade_date) FROM daily_kline")
        today = datetime.now().strftime("%Y-%m-%d")
        if last_date < today:
            update_daily_kline(from_date=last_date, to_date=today)

        # Step 2: 五因子快速初筛
        candidates = five_factor_screen_all()

        # Step 3: Kronos-mini 趋势评分
        for code in candidates:
            kronos_score = kronos_trend_score(code)

        # Step 4: 综合排名 → Top40
        top40 = rank_and_select_top(candidates, n=40)

        # Step 5: Kronos-base 深度预测
        for code in top40:
            deep_predict(code, pred_len=60)

        # Step 6: 回溯更新 (N天前的预测 vs 实际)
        update_backtest_records()

        logger.info(f"Daily screening complete: {batch_id}")
```

---

# 第三部分：实施路线图

## Phase 1: 数据库 + 数据采集 (2天)

- [ ] 创建 `stock_screening.db` + 7张表DDL
- [ ] `services/market_data_service.py` — 全市场数据采集 (akshare)
- [ ] 增量更新机制 + 交易日历
- [ ] 数据质量检查 (停牌/退市/ST标记)

## Phase 2: 评分引擎 (2天)

- [ ] `services/screener_service.py` — 五因子全市场评分
- [ ] `services/kronos_trend_scorer.py` — Kronos-mini 趋势评分
- [ ] `services/ranking_service.py` — 综合评分 + Top40排序
- [ ] 操作建议生成规则

## Phase 3: 批量预测管线 (1天)

- [ ] `services/prediction_pipeline.py` — Top40并行预测
- [ ] WebSocket 进度推送
- [ ] `routes/screener_routes.py` — 筛选API
- [ ] `routes/predict_routes.py` — 增强预测API

## Phase 4: 前端重构 (3天)

- [ ] `templates/dashboard.html` — 新5-Tab布局
- [ ] ECharts K线图集成
- [ ] WebSocket 客户端集成
- [ ] 响应式设计适配

## Phase 5: 历史回溯 (1天)

- [ ] `services/backtest_service.py` — 回溯计算
- [ ] `routes/backtest_routes.py` — 回溯API
- [ ] 前端回溯Tab

## Phase 6: 定时调度 (1天)

- [ ] `scheduler.py` — 每日盘后自动执行
- [ ] macOS LaunchAgent 配置

---

**总预估**: 10个工作日
