# 速赢AI 证券投资管理平台 — 完整设计文档

> 版本: V2.0 | 更新: 2026-06-17 | 分支: `速赢AI-选股V2-大版本`

---

## 目录

1. [PRD — 产品需求文档](#1-prd)
2. [业务架构设计](#2-业务架构设计)
3. [技术架构设计](#3-技术架构设计)
4. [概念设计](#4-概念设计)
5. [详细模型设计](#5-详细模型设计)
6. [数据管道设计](#6-数据管道设计)
7. [前端设计](#7-前端设计)
8. [部署与运维](#8-部署与运维)

---

## 1. PRD

### 1.1 产品定位

速赢AI 是一站式 AI 驱动量化证券投资管理平台，覆盖 **选股发现 → 方案生成 → 回测验证 → 自动交易 → 个股诊断** 全链路量化工作流。核心用户为证券分析师、量化交易员与个人投资者。

### 1.2 核心价值主张

> **"AI 替代人工盯盘与主观决策"**

| 痛点 | 解决方案 |
|---|---|
| 5000+ 只 A 股人工筛选不可行 | 12 个 AI 模型自动选股，1-60s 出结果 |
| 主观交易情绪化 | OBV/WR/量能/均线多因子量化打分 |
| 回测繁琐 | 滚动窗口前向回测，一键 IC/ICIR 校准 |
| 信息过载 | 五维个股诊断（技术/资金/基本面/AI/情绪） |

### 1.3 用户角色

| 角色 | 权限 |
|---|---|
| `admin` | 全部功能 + 模型训练 + 系统管理 |
| `internal_analyst` | 选股/方案/回测/诊断/交易/信号 |
| `external_analyst` | 选股/方案/回测/诊断（不含交易） |
| `user` | 选股/方案/诊断/交易 |

### 1.4 功能全景

```
┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│  数据采集  │ →  │  智能选股  │ →  │  方案生成  │ →  │  回测验证  │ →  │  自动交易  │
│  (15张表)  │    │  (12模型)  │    │  (LLM)     │    │  (IC/ICIR) │    │  (QMT券商) │
└───────────┘    └───────────┘    └───────────┘    └───────────┘    └───────────┘
                      │                                                   │
                      ▼                                                   ▼
               ┌───────────┐                                      ┌───────────┐
               │  个股诊断  │ ←────────────────────────────────── │  交易信号  │
               │  (5维度)   │                                      │  (50维)   │
               └───────────┘                                      └───────────┘
```

---

## 2. 业务架构设计

### 2.1 核心业务流程

```
Tushare数据源 → data-service(定时采集) → PostgreSQL(主库) + SQLite(备库)
                                              ↓
                    ┌─────────────────────────┼─────────────────────────┐
                    ↓                         ↓                         ↓
           screener-service           signal-service            prediction-service
           (12选股模型)                (50维交易信号)            (Kronos K线预测)
                    ↓                         ↓                         ↓
                    └─────────────────────────┼─────────────────────────┘
                                              ↓
                                     strategy-service
                                   (LLM方案生成+自动交易)
                                              ↓
                              ┌───────────────┼───────────────┐
                              ↓               ↓               ↓
                      trade-service    backtest-service  diagnosis-service
                      (模拟/实盘)      (回测+IC校准)     (五维诊断)
```

### 2.2 选股模式分类

#### 股票选股（9 个）

| 模式 | 风格 | 周期 | 引擎文件 | 行数 |
|---|---|---|---|---|
| 🔥 leader_auction | 竞价 | 1-3天 | leader_auction.py | 398 |
| leader_scalp | 激进 | 1-5天 | leader_scalp.py | 2018 |
| leader_intraday | 激进 | 1-2天 | leader_intraday.py | 1659 |
| leader_closing | 顺势 | 1-2天 | leader_closing.py | 1299 |
| short | 积极 | 1-4周 | modes.py (ShortModeEngine) | — |
| long | 稳健 | 3-12月 | modes.py (LongModeEngine) | — |
| all | 中性 | 1-6月 | modes.py (AllModeEngine) | — |
| chokepoint | 主题 | 1-3月 | modes.py (ChokepointEngine) | — |
| bi_trend_launch | 趋势 | 5-20天 | bi_trend_launch.py | 1745 |

#### 可转债选债（3 个）

| 模式 | 风格 | 周期 | 引擎文件 |
|---|---|---|---|
| cb_floor | 稳健 | 1-4周 | cb_floor.py |
| cb_intraday | 激进 | 1-2天 | cb_intraday.py |
| cb_auction | 竞价 | 1-2天 | cb_auction.py |

### 2.3 因子体系

#### 14 因子多因子体系（short/long/all 共用）

```
_compute_shared_factors(code, df)
  ├── F1: 五因子评分 (动量/量能/质量/技术/风险)  → five_factor.py
  ├── F2: 资金流向 (主力/游资/散户)              → advanced_factors.py
  ├── F3: 均值回归 (布林带位置)                  → advanced_factors.py
  ├── F4: 趋势强度 (ADX)                         → advanced_factors.py
  ├── F5: 反转信号 (RSI+MACD)                    → advanced_factors.py
  ├── F6: 流动性 (换手率+成交额)                 → advanced_factors.py
  ├── F7: 短线技术 (MA排列+放量突破+MACD金叉)    → screening_scorers.py
  ├── F8: 长线价值 (PE/PB/股息率)                → screening_scorers.py
  ├── F9: 成长性 (营收/利润增速)                 → screening_scorers.py
  ├── F10: 硬科技 (行业匹配+专利+研发)            → advanced_factors.py
  ├── F11: Tushare增强 (龙虎榜/机构/分析师)       → advanced_factors.py
  ├── F12: 股票主题 (概念+赛道)                   → screening_scorers.py
  ├── F13: Kronos AI预测 (30日K线预测)           → kronos_prediction.py [opt-in]
  └── F14: 卡脖子稀缺 (供应链垄断程度)             → screening_scorers.py
```

#### 10 因子趋势体系（bi_trend_launch 专用）

见[毕师傅战法规则手册](#)（上文已详细输出）。

#### 3 因子可转债体系

| 模型 | 核心因子 |
|---|---|
| cb_floor | 底价偏离度 + 转股溢价率 + 纯债价值 |
| cb_intraday | 日内量价突破 + 正股联动 + 转股套利空间 |
| cb_auction | 竞价量比 + 概念热度 + 开盘溢价 |

---

## 3. 技术架构设计

### 3.1 微服务拓扑

```
                    ┌──────────────────────────────────────────┐
                    │           api-gateway :8080              │
                    │     (反向代理 + 限流 + CORS)             │
                    └────┬───┬───┬───┬───┬───┬───┬───┬───────┘
                         │   │   │   │   │   │   │   │
    ┌────────────────────┼───┼───┼───┼───┼───┼───┼───┼───────────────┐
    │                    │   │   │   │   │   │   │   │               │
    ▼                    ▼   ▼   ▼   ▼   ▼   ▼   ▼   ▼               ▼
┌─────────┐   ┌─────────┬─────────┬─────────┬─────────┬─────────┐  ┌─────────┐
│ backend │   │screener │prediction│strategy │ signal  │  alert  │  │  trade  │
│  :9001  │   │ :8001   │  :8002  │ :8003   │ :8004   │ :8005   │  │  :8006  │
│ JWT+RBAC│   │ 12模型  │ Kronos  │ LLM方案 │ 50维信号│ 多通道  │  │ 模拟/实盘│
└─────────┘   └─────────┴─────────┴─────────┴─────────┴─────────┘  └─────────┘
                    │                                               │
              ┌─────┴─────┐                                   ┌─────┴─────┐
              ▼           ▼                                   ▼           ▼
        ┌─────────┐ ┌─────────┐                         ┌─────────┐ ┌─────────┐
        │backtest │ │diagnosis│                         │training │ │  data   │
        │  :8007  │ │  :8009  │                         │ :8008   │ │ :manual │
        │回测+校准│ │ 五维诊断│                         │模型训练  │ │数据采集 │
        └─────────┘ └─────────┘                         └─────────┘ └─────────┘
```

### 3.2 技术栈

| 层级 | 技术 | 版本 |
|---|---|---|
| **前端** | React + Vite + TypeScript + Ant Design + ECharts | React 18, Vite 6, TS 5.6, Antd 5.22 |
| **API 网关** | FastAPI + urllib async wrapper | Python ≥3.10 |
| **微服务** | FastAPI + uvicorn + Pydantic v2 | 13 服务 |
| **数据库** | PostgreSQL 15 (主) + SQLite (备) + Redis 7 (缓存) | PG:6432, Redis:7379 |
| **ML 预测** | Kronos-mini (公开模型托管推理, PyTorch — M05/M10: ONNX Runtime 死代码已删, 非自研) | HuggingFace |
| **ML 训练** | LightGBM + CatBoost + MLflow | — |
| **LLM** | DeepSeek (方案生成) | API |
| **行情数据** | Tushare 1.4.29 + mootdx (fallback) | — |
| **券商交易** | Xtquant (QMT) | — |
| **认证** | PyJWT HS256 + Argon2id + httpOnly Cookie | — |
| **部署** | Docker Compose (10+ 容器) | — |

### 3.3 数据流架构

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ Tushare  │ →  │  data-service │ →  │  PostgreSQL   │ ←  │  所有微服务   │
│  API     │    │  (定时采集)    │    │  (主存储)      │    │  (只读查询)   │
└──────────┘    └──────┬───────┘    └──────┬───────┘    └──────────────┘
                       │                   │
                       │ (fallback)        │ (fallback)
                       ▼                   ▼
                ┌──────────────┐    ┌──────────────┐
                │   SQLite     │    │    Redis      │
                │  (备存储)     │    │  (L1-L5缓存)  │
                └──────────────┘    └──────────────┘
```

### 3.4 数据分层调度

| 层级 | 频率 | 任务 |
|---|---|---|
| **L0 实时** | 每分钟/9:25 | 分钟线采集、竞价快照 |
| **L1 日内** | 每 30 分钟/13:00 | 涨跌停增量、盘中午间同步 |
| **L2 盘后** | 15:30/16:00/18:00 | 日线、资金流、技术因子、可转债、指数 |
| **L3 周级** | 每周一/每月1日 | 股票列表、沪深港通、概念映射 |
| **L4 按需** | 每日 4:00 | 数据完整性检查 + 自动回补 + 质量周检 |

### 3.5 PG ↔ SQLite 列名映射

| SQLite 列名 | PG 列名 | 涉及表 |
|---|---|---|
| `pct_chg` | `change_pct` | index_daily, moneyflow |
| `ts_code` | `code` | stk_mins, stk_limit, cb_* |
| `float_mv` | COALESCE(market_cap, float_mv) | stocks |

---

## 4. 概念设计

### 4.1 领域模型

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Stock     │────→│   Kline      │────→│   Factor     │
│  股票基本信息 │     │  OHLCV日线   │     │  因子评分     │
└──────────────┘     └──────────────┘     └──────┬───────┘
      │                                          │
      │                                    ┌─────▼──────┐
      │                                    │   Signal   │
      │                                    │  交易信号    │
      │                                    └─────┬──────┘
      │                                          │
      ▼                                          ▼
┌──────────────┐                          ┌──────────────┐
│   Strategy   │←────────────────────────│    Plan      │
│  策略配置     │                          │  交易方案     │
└──────┬───────┘                          └──────┬───────┘
       │                                         │
       ▼                                         ▼
┌──────────────┐                          ┌──────────────┐
│    Order     │                          │   Position   │
│    订单      │                          │    持仓       │
└──────────────┘                          └──────────────┘
```

### 4.2 选股模型概念层级

```
                     ┌─────────────────────┐
                     │    ScreeningMode    │  ← 抽象基类
                     │  (StrategyEngine)   │
                     └──────────┬──────────┘
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   LeaderMode     │  │ MultiFactorMode  │  │   CBTrendMode    │
│  龙头战法系列      │  │  多因子系列       │  │  可转债系列       │
├──────────────────┤  ├──────────────────┤  ├──────────────────┤
│ leader_scalp     │  │ ShortModeEngine  │  │ CbFloorEngine    │
│ leader_intraday  │  │ LongModeEngine   │  │ CbIntradayEngine │
│ leader_auction   │  │ AllModeEngine    │  │ CbAuctionEngine  │
│ leader_closing   │  │ ChokepointEngine │  │                  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
          │                     │
          │    ┌────────────────┤
          ▼    ▼                ▼
┌──────────────────────────────────────┐
│        BiTrendLaunchEngine           │
│        毕师傅趋势启动战法              │
│   (独立体系: OBV+WR+10因子)          │
└──────────────────────────────────────┘
```

### 4.3 信号概念层级

```
Signal (信号)
├── strong_buy    🔥 强买 (三层确认+连阳)
├── buy           🟢 买入 (深度回踩/连阳确认)
│   ├── premium   优选 (回踩新鲜+反弹强+非追高)
│   ├── standard  标准
│   └── weak      弱买 (减仓信号)
├── watch         🟡 观察 (中等回踩/无连阳)
├── no_signal     ⚪ 无信号
└── sell          🔴 卖出
```

---

## 5. 详细模型设计

### 5.1 毕师傅趋势启动战法（bi_trend_launch）V5.9

> 详见上文完整规则手册（10因子 + 三层确认信号 + 五档仓位）

**核心文件**: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` (1745行)

**关键参数**:

| 参数 | 值 | 类别 |
|---|---|---|
| HARD_TECH_ONLY | True | 硬科技门控 |
| MIN_TREND_20D | 0% | 趋势过滤 |
| STRONG_OBV_DAYS | 10 | 强信号 |
| STRONG_WR_DROP | -25 | WR急跌确认 |
| MIN_WR_DEPTH_FOR_BUY | -50 | 买入门槛 |
| GRADE_THRESHOLDS | S≥70, A≥55, B≥40 | 等级 |
| WEIGHTS | OBV:30, WR:28, 量:8, 均线:10, ADX:8 | 权重 |

### 5.2 龙头战法系列

#### leader_scalp（秋神龙头战法-盘后）2018行

**核心逻辑**: 板块龙头识别 + 涨幅排序 + 7 条件筛选
- 流通市值 ≥ 20 亿
- 当日涨幅 ≥ 3%
- 板块排名前 3
- 换手率 2-25%
- 非 ST/新股/一字板
- 均线多头排列
- 量能确认

#### leader_intraday（盘中）1659行
- 14:40 实时快照
- 板块龙头 + 分时强度
- 追涨/低吸双模式

#### leader_auction（竞价）398行
- 9:25 竞价数据
- 竞价量比 + 开盘溢价
- Tushare stk_auction → mootdx fallback

#### leader_closing（尾盘）1299行
- 14:40 顺势筛选
- 尾盘量价异动捕捉

### 5.3 多因子系列（modes.py）549行

#### ShortModeEngine
- 14 因子 ICIR 加权
- Hard filter: 周线+月线多头
- 自适应市场 regime（quality_defensive / momentum_weighted）

#### LongModeEngine (V2)
- 6 因子 + 机构资金确认
- 市值预过滤 ≥ 50B
- 价格≥5元 + 日均量≥50万

#### AllModeEngine (V2)
- 14 因子全量
- 市值预过滤 ≥ 2B
- 批量 K 线预取

#### ChokepointEngine (V2)
- 卡脖子稀缺评分
- 行业垄断 + 研报关键词 + 硬科技赛道 + 券商覆盖 + 北向资金
- 阈值 4.0（弱市放宽）

### 5.4 可转债系列

| 模型 | 核心逻辑 | 行数 |
|---|---|---|
| CbFloorEngine | 底价偏离 + 转股溢价率 + 纯债价值锚定 | 683 |
| CbIntradayEngine | 日内量价突破 + 正股联动 + 5档止盈 | 816 |
| CbAuctionEngine | 竞价概念热度 + 开盘溢价 + 量比排序 | 466 |

### 5.5 Kronos Transformer 预测模型

**架构**: KronosTokenizer (BSQuantizer) + KronosPredictor (Transformer)

**文件**: `packages/kronos-core/kronos/model/kronos.py`

```
KronosTokenizer: 编码器-解码器 Transformer
  ├── d_in → d_model → n_heads → ff_dim
  ├── n_enc_layers × TransformerBlock
  ├── n_dec_layers × TransformerBlock  
  └── BSQuantizer (Binary Spherical Quantization)

KronosPredictor: 时序预测
  ├── HierarchicalEmbedding (层次嵌入)
  ├── TemporalEmbedding (时间嵌入)
  ├── DependencyAwareLayer (依赖感知层)
  └── DualHead (双头输出: OHLCV)
```

**部署**: 
- 预训练模型从 HuggingFace (`NeoQuasar/Kronos-mini`) 加载
- Fine-tuned checkpoint 从本地 `Kronos/outputs/models/` 加载
- 支持 MPS/CPU 推理，首次推理 JIT 编译预热

### 5.6 数据模型（PostgreSQL 核心表）

#### 行情数据 (8 表)

| 表名 | 主键 | 核心字段 |
|---|---|---|
| `stocks` | code | name, industry, market_cap, is_st, listed_date |
| `daily_kline` | code+trade_date | open, high, low, close, volume, amount, change_pct |
| `weekly_kline` | code+trade_date | open, high, low, close, volume |
| `monthly_kline` | code+trade_date | open, high, low, close, volume |
| `daily_basic` | code+trade_date | pe, pb, total_mv, circ_mv, turnover_rate |
| `stk_limit` | code+trade_date | pre_close, up_limit, down_limit |
| `index_daily` | code+trade_date | open, high, low, close, change_pct |
| `sw_daily` | code+trade_date | open, high, low, close, change_pct |

#### 资金流数据 (5 表)

| 表名 | 核心字段 |
|---|---|
| `moneyflow` | buy_sm/lg/elg_amount, net_mf_amount |
| `moneyflow_hsgt` | 沪深港通净流入 |
| `hk_holdings` | 北向持仓比例 |
| `margin_detail` | 融资融券明细 |
| `top_list` / `top_inst` / `block_trade_data` | 龙虎榜/机构/大宗交易 |

#### 基本面数据 (3 表)

| 表名 | 核心字段 |
|---|---|
| `financial_income` | total_revenue, net_profit, yoy_growth |
| `financial_balance` | total_assets, equity, debt_ratio |
| `adj_factor` | 复权因子 |

---

## 6. 数据管道设计

### 6.1 数据采集架构

```
data-service (asyncio scheduler)
  ├── L0: rt_min (mootdx 实时分钟线, 每分钟)
  ├── L0: auction (竞价快照, 9:25)
  ├── L1: limit_list_d (涨跌停, 每30分钟)
  ├── L2: post_market_core (P0: daily/moneyflow/stk_limit, 15:30)
  ├── L2: post_market_ext (P1: daily_basic/ths_daily/limit_list, 15:35)
  ├── L2: cb_daily/cb_factor (可转债, 18:00)
  ├── L2: sw_daily/stk_factor_pro (申万行业/技术因子, 16:05)
  ├── L3: stocks_sync (全量同步, 每周六 2:00)
  ├── L3: stocks_incremental (新股检测, 每日 8:00)
  ├── L3: moneyflow_hsgt (沪深港通, 每周一 8:30)
  └── L4: data_integrity + data_quality (每日 4:00)
```

### 6.2 写入策略

```
Tushare API → sync_*() → PG 直写 (主路径)
                       → SQLite 写入 (fallback)
                       → refresh_materialized_views (PG 物化视图)
```

**限流**: 滑动窗口 450 req/min（Tushare 上限 500）

### 6.3 数据质量保障

- **L4 完整性检查**: 每日 4:00，检测 14 张核心表的数据滞后天数
- **L4 自动回补**: 检测到缺口（超过 gap_threshold）→ 触发 `kronos_data.etl` 回补
- **L4 质量周检**: 每周六 4:30，检测异常值（close≤0, RSI 越界, 重复记录, 新鲜度）
- **交易日历**: 使用 `trade_cal` 表计算真实交易日缺口

---

## 7. 前端设计

### 7.1 页面结构

```
App.tsx (Layout + AuthContext)
├── /                 Dashboard       AI 智能看板 (41KB)
├── /screener         Screener        智能选股 (9KB)
├── /predictions      Predictions     K线预测 (8KB)
├── /strategy         Strategy        方案管理 (14KB)
├── /signals          Signals         交易信号 (6KB)
├── /trade            Trade           交易中心 (14KB)
├── /auto-trade       AutoTrade       量化交易 (34KB)
├── /backtest         Backtest        回测分析 (31KB)
├── /diagnosis        Diagnosis       个股诊断 (68KB)
├── /training         Training        模型训练 (29KB)
├── /model-registry   ModelRegistry   模型注册 (30KB)
└── /data-update      DataUpdate      数据更新 (17KB)
```

### 7.2 API Client 模块

```typescript
api/client.ts (统一 Axios 封装)
├── screenerApi    → /screener/*
├── predictionApi  → /prediction/*
├── strategyApi    → /strategy/*
├── signalApi      → /signal/*
├── alertApi       → /alert/*
├── tradeApi       → /trade/*
├── backtestApi    → /backtest/*
├── diagnosisApi   → /diagnosis/*
└── healthApi      → /{service}/health
```

### 7.3 认证机制

- **JWT**: HS256, Access Token 15min, Refresh Token 7d
- **Refresh Token**: httpOnly + Secure + SameSite=Strict Cookie
- **密码哈希**: Argon2id (time=3, memory=64MiB, parallelism=2)
- **RBAC**: 4 角色 (admin/internal_analyst/external_analyst/user)
- **自动刷新**: Axios interceptor 401 → refresh → retry

---

## 8. 部署与运维

### 8.1 Docker Compose 服务清单

| 服务 | 端口 | Dockerfile | 依赖 |
|---|---|---|---|
| postgres | 6432 | docker hub | — |
| redis | 7379 | docker hub | — |
| api-gateway | 8080 | ✅ | postgres |
| backend | 9001 | ✅ | postgres |
| screener-service | 8001 | ✅ | postgres, redis |
| prediction-service | 8002 | ✅ | — |
| strategy-service | 8003 | ✅ | postgres |
| signal-service | 8004 | ✅ | postgres |
| alert-service | 8005 | ✅ | postgres |
| trade-service | 8006 | ✅ | postgres |
| backtest-service | 8007 | ✅ | postgres |
| diagnosis-service | 8009 | ✅ | postgres |

### 8.2 CI/CD

```yaml
.github/workflows/ci.yml
  ├── python-tests: kronos-factors + kronos-auth (pytest + PG service)
  ├── frontend-tests: TypeScript + vitest
  └── docker-build: 8个微服务 Docker build 检查
```

### 8.3 关键环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `KRONOS_PG_URL` | ✅ | PG 连接串 |
| `TUSHARE_TOKEN` | ✅ | Tushare 数据源 |
| `DEEPSEEK_API_KEY` | — | LLM 方案生成 |
| `USE_KRONOS_PREDICTION` | — | Kronos AI 预测因子开关 |
| `REDIS_URL` | — | Redis 缓存 |
| `JWT_SECRET_KEY` | ✅ | JWT 签名密钥 |

### 8.4 一键启动

```bash
# 基础设施
docker start docker-postgres-1 docker-redis-1

# 全部微服务
cd docker && docker compose up -d

# 前端
cd frontend && npm run dev

# 健康检查
curl localhost:8001/api/v1/health
curl localhost:8080/health
```

---

## 附录 A: 文件清单

| 目录 | 文件数 | 代码行数 |
|---|---|---|
| `packages/kronos-factors/engine/` | 12 | 10,584 |
| `packages/kronos-factors/scorer/` | 6 | 3,337 |
| `services/screener-service/` | 7 | ~500 |
| `services/data-service/` | 10 | ~1,500 |
| `services/backtest-service/` | 3 | ~500 |
| `frontend/src/pages/` | 14 | ~300KB |
| `frontend/src/api/` | 2 | ~200 lines |
| **合计** | — | **~20,000 行** |

## 附录 B: 版本历史

| 版本 | 日期 | 关键变更 |
|---|---|---|
| V2.0 | 2026-06-17 | 批量K线预取、市值预过滤、chokepoint降级、numpy序列化修复、弱市适配 |
| V1.0 | 2026-06-12 | 12模型选股、数据管道L0-L4、回测+IC校准、全链路贯通 |
