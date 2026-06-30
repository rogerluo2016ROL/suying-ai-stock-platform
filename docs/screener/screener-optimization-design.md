# 速赢AI 选股模型优化 — 设计文档

> **文档版本**: v1.0  |  **编写日期**: 2026-06-30
> **决策阶段**: 设计评审（尚未决定是否实施，仅呈现方案）
> **参考来源**: 证监会主席吴清 2026陆家嘴论坛主题演讲 + 项目现有 11 个选股引擎
> **阅读方式**: 先读第一章整体方案（15分钟），再决定是否需要深入第二、三章

---

## 目录

- 第一章：整体方案（架构图 + 模块划分 + 数据流）
- 第二章：详细方案（每个新模块的接口、算法、数据结构）
- 第三章：优化点清单（现状缺陷 → 改进方向 → 优先级）
- 附录：实施路线图与 ROI 估算

---

# 第一章：整体方案

## 1.1 现状全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                     当前选股系统架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [前端]  Screener / ScreenerV2 / NewUiModulePage               │
│              │                                                  │
│              ▼                                                  │
│  [Service] screener-service (8001)                             │
│    │   main.py ── API 入口                                     │
│    │                                                            │
│    └── orchestrator.py ── 调度器 (run_screening / run_fusion)  │
│            │                                                    │
│            ├── _get_engine(mode)  ← 引擎注册表                  │
│            │       │                                            │
│            │       ├── leader_scalp     (2019行, 7因子)         │
│            │       ├── leader_auction   (leader_auction.py, 9因子) │
│            │       ├── leader_intraday  (1735行, 9因子)         │
│            │       ├── leader_afternoon (1157行, 8因子)         │
│            │       ├── leader_closing   (1299行, 9因子)         │
│            │       ├── bi_trend_launch  (2316行, 13因子)        │
│            │       ├── bi_trend_full_market (2096行, 13因子)    │
│            │       ├── short_mode       (modes.py, 12因子)      │
│            │       ├── chokepoint       (568行, 卡脖子)         │
│            │       ├── supply_chain     (产业链, 5维评级)       │
│            │       ├── cb_floor         (可转债底价, 12因子)    │
│            │       ├── cb_intraday      (可转债盘中)            │
│            │       └── cb_auction       (可转债竞价)            │
│            │                                                    │
│            └── merge_picks()  ← V4.0 共识融合 (简单加权)       │
│                  base_score + 10 × (每多一个模式命中)           │
│                  + 5 (leader_scalp 加权)                        │
│                                                                 │
│  [数据层]  PostgreSQL (Kronos)                                  │
│    ├── daily_kline           ── 日线行情                       │
│    ├── stk_auction_o         ── 竞价快照                        │
│    ├── stk_mins              ── 5分钟K线                       │
│    ├── rt_sw_k / rt_sw_daily ── 实时资金/日线                  │
│    ├── stock_profiles        ── 个股基本面                      │
│    ├── analyst_reports       ── 研报                            │
│    ├── limit_list_d          ── 涨跌停                          │
│    └── mv_daily_composite_ranking ── 物化视图                  │
└─────────────────────────────────────────────────────────────────┘
```

## 1.2 现状问题汇总

| # | 问题 | 影响 | 严重度 |
|---|------|------|--------|
| P1 | 11 个引擎完全独立，无统一融合语义 | 共识投票只靠简单计数，无模式差异性 | 🔴 高 |
| P2 | factor_breakdown 仅 bi_trend_launch 输出 | 其他 10 个引擎的评分黑盒 | 🔴 高 |
| P3 | merge_picks 权重硬编码 (10/5/固定) | 牛市/震荡市用相同权重，环境不适配 | 🔴 高 |
| P4 | 无实时情绪层 | 完全依赖历史行情，对新闻/政策/监管事件零感知 | 🟡 中 |
| P5 | 无板块热度聚合 | 无法识别当日热点，龙头战法选出的不是真龙头 | 🟡 中 |
| P6 | 无仓位动态调整 | 固定 max_position，无风险平价 | 🟡 中 |
| P7 | 无可解释性归因 | 用户无法理解"为什么选这只股" | 🟢 低 |

## 1.3 目标架构图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      目标架构: V5.0 选股系统                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  [前端]                                                                  │
│    ScreenerV3                                                            │
│      ├── FusionHeatmap        (板块热度 + 模式共振)                      │
│      ├── SentimentPanel       (实时情绪过滤)                             │
│      └── FactorExplanation    (SHAP 因子归因)                            │
│                                                                          │
│  [Service] screener-service (8001)                                       │
│    │                                                                     │
│    └── V5Orchestrator (重构)                                             │
│          │                                                               │
│          ├── ① EngineRegistry (原有 11 个引擎, 不修改)                   │
│          │     └── 11 engines (leader_scalp, bi_trend, ...)              │
│          │                                                               │
│          ├── ② SectorHeatmapEngine (新增)                                │
│          │     └── 实时板块热度 (涨停率/炸板率/换手率)                   │
│          │                                                               │
│          ├── ③ LLMIntelligenceEngine (新增)                              │
│          │     └── 情绪 NLP (DeepSeek API) + 事件流                      │
│          │                                                               │
│          ├── ④ WeightedFusionEngine (新增, 替代 merge_picks)             │
│          │     └── mode_profiles (动态权重) + 因子去冗余                 │
│          │                                                               │
│          └── ⑤ RiskParityAllocator (新增)                                │
│                └── 动态仓位 (波动率倒数分配)                             │
│                                                                          │
│  [数据层] PostgreSQL + Redis                                             │
│    ├── 原有表 (不修改)                                                   │
│    ├── mv_sector_heatmap        ── 板块热度物化视图 (新增)               │
│    ├── mv_mode_profiles         ── 模式画像 (新增)                       │
│    └── Redis: 情绪缓存 (TTL 1h)                                         │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## 1.4 数据流（请求驱动）

```
POST /api/v1/screener/run?mode=fusion_v5&top_n=30

         ┌──────────────────────────────────────────────────┐
         │           V5Orchestrator.run_fusion_v5()          │
         └───────────────────────┬──────────────────────────┘
                                 │
          ┌──────────────────────┴───────────────────────┐
          │                                              │
          ▼                                              ▼
   [并行执行层]                                [串行环境感知层]
   │                                             │
   ├── leader_scalp.run()                        ├── SectorHeatmapEngine
   ├── leader_auction.run()                      │     .get_market_state()
   ├── bi_trend_launch.run()                     │         │
   ├── supply_chain.run()                        │         ▼
   └── ... (ThreadPoolExecutor max_workers=8)    │   market_env: BULL/NEUTRAL/BEAR
          │                                      │         │
          ▼                                      ▼
   各模式 picks: list[dict]                hot_sectors: list[str]
          │                                      │
          └──────────────┬───────────────────────┘
                         │
                         ▼
          [融合层: WeightedFusionEngine]
          │
          ├── Step 1: 按 mode_profiles 动态加权
          ├── Step 2: 因子相关性去冗余 (Pearson > 0.8 → 合并)
          ├── Step 3: 板块热度过滤 (非 hot_sector 权重 ×0.5)
          │
          ▼
   consensus: list[dict]  (含 reduced_breakdown)
          │
          ▼
          [可选: LLMIntelligenceEngine]
          │
          ├── scan_news_sentiment() × top_n
          ├── sentiment_filter() (confidence > 0.6 保留)
          │
          ▼
   enriched_picks: list[dict]  (含 sentiment_score)
          │
          ▼
          [可选: RiskParityAllocator]
          │
          └── 按波动率倒数分配 weight
                  │
                  ▼
   final_picks: list[dict]  (含 weight, shap_explanation)
```

## 1.5 模块依赖关系

```
V5Orchestrator
  ├── ① EngineRegistry        ── 无外部依赖 (纯引擎调度)
  ├── ② SectorHeatmapEngine   ── 仅依赖 PG (limit_list_d + daily_kline)
  ├── ③ LLMIntelligenceEngine ── 依赖 DeepSeek API (http, 无本地依赖)
  ├── ④ WeightedFusionEngine  ── 依赖 mv_mode_profiles (PG 物化视图)
  └── ⑤ RiskParityAllocator   ── 仅依赖 PG (daily_kline 波动率)
```

**关键设计原则**: 每个模块可独立启用/禁用，通过环境变量控制：
- `ENABLE_SECTOR_HEATMAP=true`
- `ENABLE_LLM_INTELLIGENCE=false`
- `ENABLE_RISK_PARITY=false`

---

# 第二章：详细方案

## 2.1 模块②: SectorHeatmapEngine — 板块实时热度

### 2.1.1 职责

聚合当日涨停板/炸板/换手数据，输出每只股票所属板块的热度评分。
为 WeightedFusionEngine 提供板块过滤上下文（是否属于当日热点板块）。

### 2.1.2 接口

```python
class SectorHeatmapEngine:
    """板块实时热度引擎."""

    def __init__(self, pg_url: str | None = None): ...

    def get_sector_dashboard(self, trade_date: str) -> SectorDashboard:
        """返回全市场板块热度。

        Returns:
            SectorDashboard:
                sectors: list[SectorStat]   # 每个板块的热度指标
                market_state: MarketState   # 全市场环境
        """

    def get_hot_sectors(
        self, top_n: int = 15, min_hit_rate: float = 0.6
    ) -> list[str]:
        """返回热度达标板块列表（用于过滤）。

        热度标准: hit_rate >= min_hit_rate AND avg_gain_pct >= 2.0%
        """

    def get_stock_sector_heat(self, code: str) -> SectorStat | None:
        """单只股票的板块热度查询（用于 enrich 每个 pick）。"""
```

### 2.1.3 数据结构

```python
@dataclass
class SectorStat:
    sector: str              # 板块名称 (industry 字段)
    total_stocks: int        # 板块内总股票数
    upstocks: int            # 当日上涨股票数
    hit_stocks: int          # 涨停股票数 (limit_type='U')
    limit_up_count: int      # 炸板数 (曾经涨停后回落)
    hit_rate: float          # 涨停率 = hit_stocks / total_stocks
    avg_gain_pct: float      # 板块平均涨幅
    volume_ratio: float      # 板块量比 (相对 5 日均量)
    trend: str               # "strong_up" | "exploring" | "flat" | "down"


@dataclass
class MarketState:
    limit_up_count: int      # 全市场涨停数
    limit_down_count: int    # 全市场跌停数
    breadth: float           # 涨跌比 = 涨股数 / 总股数
    circulation_heat: int    # 流通热度 (0-100)
```

### 2.1.4 核心 SQL

```sql
-- 涨停板分板块统计
SELECT
    sp.industry AS sector,
    COUNT(*) AS hit_stocks,
    AVG(dk.pct_chg) AS avg_gain_pct
FROM limit_list_d ll
JOIN stock_profiles sp ON sp.code = ll.code
JOIN daily_kline dk ON dk.code = ll.code AND dk.trade_date = ll.trade_date
WHERE ll.trade_date = %s AND ll.limit_type = 'U'
  AND sp.industry IS NOT NULL
GROUP BY sp.industry
ORDER BY hit_stocks DESC

-- 全市场涨跌比
SELECT
    SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) AS up_count,
    COUNT(*) AS total,
    SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END)::float / COUNT(*) AS breadth
FROM daily_kline
WHERE trade_date = %s
```

### 2.1.5 性能估算

| 操作 | 数据规模 | 耗时 |
|------|---------|------|
| 板块统计 | ~30 板块 × 5000 股 | < 100ms |
| 涨跌比 | ~5000 股 | < 50ms |
| **合计** | — | **< 200ms** |

---

## 2.2 模块③: LLMIntelligenceEngine — 实时情绪情报

### 2.2.1 职责

对候选股进行新闻/公告的 LLM 情绪分析，输出 sentiment_score (0-100)。
作为可选层，仅在 fusion 后对 top_n 候选调用，避免全市场扫描。

### 2.2.2 接口

```python
class LLMIntelligenceEngine:
    """LLM 情绪情报引擎."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ): ...

    def scan_news_sentiment(
        self,
        stock_code: str,
        query_days: int = 3,
    ) -> SentimentResult:
        """扫描单只股票近 N 日新闻，返回情绪。

        Returns:
            SentimentResult:
                sentiment: "positive" | "negative" | "neutral"
                confidence: float (0-1)
                keywords: list[str]
                summary: str (≤50字)
                event_count: int
        """

    def batch_scan(
        self,
        stock_codes: list[str],
        concurrency: int = 5,
    ) -> dict[str, SentimentResult]:
        """批量扫描（并发限制，避免限流）。

        使用 semaphore 控制并发，结果缓存到 Redis (TTL 1h)。
        """

    def filter_by_sentiment(
        self,
        picks: list[dict],
        min_confidence: float = 0.6,
        exclude_negative: bool = True,
    ) -> list[dict]:
        """基于情绪过滤候选池。

        规则:
          - sentiment="negative" 且 confidence > 0.7 → 排除
          - sentiment="positive" 且 confidence > min_confidence → 加分 +5
        """
```

### 2.2.3 数据结构

```python
@dataclass
class SentimentResult:
    sentiment: str           # "positive" | "negative" | "neutral"
    confidence: float        # 0-1
    keywords: list[str]      # ["机构调研", "技术突破"]
    summary: str             # "公司宣布Q3营收增长50%"
    event_count: int         # 正面事件 + 负面事件总数
    scanned_at: str          # ISO 时间戳


@dataclass
class SentimentCacheEntry:
    stock_code: str
    result: SentimentResult
    cached_at: float         # Unix timestamp
    ttl_seconds: int = 3600  # 1h 缓存
```

### 2.2.4 LLM Prompt 设计

```python
SENTIMENT_PROMPT = """
你是一名专业的证券分析师。请对以下股票【{stock_code}】近 {query_days} 日的公开信息（新闻、公告、研报）进行情绪分析。

请严格按照以下 JSON 格式返回，不要包含任何其他内容：
{{
  "sentiment": "positive" | "negative" | "neutral",
  "confidence": <0-1 之间的浮点数>,
  "keywords": ["事件关键词1", "事件关键词2", "事件关键词3"],
  "summary": "<50字以内的事件摘要>",
  "event_count": <正面事件数 + 负面事件数>
}}

判断标准：
- positive: 利好消息为主（业绩超预期/机构调研/技术突破/政策支持/并购重组）
- negative: 利空消息为主（财务暴雷/监管处罚/商誉减值/机构减持/诉讼纠纷）
- neutral: 无显著事件或正负抵消

confidence 标准：
- 0.8+: 信息充足且情绪明确
- 0.6-0.8: 信息较少或情绪模糊
- <0.6: 信息不足无法判断
"""
```

### 2.2.5 成本估算

| 场景 | Token 消耗 | DeepSeek 费用 |
|------|-----------|--------------|
| 单只股票 3 日新闻 | ~1500 tokens (input+output) | ¥0.0015 |
| 100 只候选批量 | ~150,000 tokens | ¥0.15 |
| 每日 20 批次 | ~3M tokens | ¥3.0 |
| **月度** | — | **¥90** |

### 2.2.6 降级方案

- DeepSeek API 不可用 → 返回 `sentiment="neutral", confidence=0.0`（不阻塞流程）
- 网络超时 → 使用 Redis 缓存（TTL 1h 内有效）
- 响应格式错误 → 3 次重试，仍失败则降级

---

## 2.3 模块④: WeightedFusionEngine — 加权融合（替代 merge_picks）

### 2.3.1 职责

替代现有 `merge_picks()`，引入：
1. **mode_profiles**: 每个模式的历史 precision/recall 画像（动态权重）
2. **环境适配**: 牛市/震荡市/熊市自动调整模式权重
3. **因子去冗余**: Pearson 相关性 > 0.8 的因子合并

### 2.3.2 接口

```python
class WeightedFusionEngine:
    """加权融合引擎."""

    def __init__(self, mode_profiles_path: str | None = None): ...

    def run(
        self,
        strategy_results: dict[str, list[dict]],
        market_env: str = "neutral",
        hot_sectors: list[str] | None = None,
        top_n: int = 30,
    ) -> FusionResult:
        """执行加权融合。

        Args:
            strategy_results: {mode_name: picks_list}
            market_env: "bull" | "neutral" | "bear" | "crash"
            hot_sectors: 板块热度过滤列表
            top_n: 返回候选数

        Returns:
            FusionResult:
                picks: list[dict]          # 融合后候选
                weights_used: dict         # 实际使用的权重
                factor_redundancy: dict    # 去冗余结果
        """

    def load_mode_profiles(self) -> dict[str, ModeProfile]:
        """从 mv_mode_profiles 或 JSON 加载模式画像。"""

    def compute_dynamic_weights(
        self, market_env: str
    ) -> dict[str, float]:
        """根据市场环境计算动态权重。"""
```

### 2.3.3 数据结构

```python
@dataclass
class ModeProfile:
    """模式画像（从回测历史数据拟合）。"""
    mode: str
    precision: float       # 命中率 (0-1)
    recall: float          # 覆盖率 (0-1)
    speed: str             # "fast" | "moderate" | "slow"
    style: str             # "momentum" | "trend" | "event_driven" | "statistical" | "theme"
    primary_factors: list[str]
    risk_preference: str   # "aggressive" | "moderate" | "conservative"
    env_affinity: dict[str, float]  # {"bull": 1.2, "neutral": 1.0, "bear": 0.7}


@dataclass
class FusionResult:
    picks: list[dict]
    weights_used: dict[str, float]      # {mode: weight}
    factor_redundancy: dict[str, list[str]]  # {主因子: [合并的冗余因子]}
```

### 2.3.4 融合算法

```
输入: strategy_results = {mode: picks}, market_env, hot_sectors

Step 1: 加载 mode_profiles
  └── mv_mode_profiles 表 / JSON 文件

Step 2: 计算动态权重
  base_weight[mode] = (precision + recall) / 2
  env_factor = mode_profiles[mode].env_affinity[market_env]
  weight[mode] = base_weight[mode] × env_factor
  normalize weight 使得 sum = 1.0

Step 3: 加权投票
  对每只出现在 ≥1 个模式中的股票:
    weighted_score = Σ (weight[mode] × pick.score[mode]) / count[mode]
    consensus_count = 出现在几个模式中

Step 4: 板块热度修正
  if hot_sectors and pick.sector not in hot_sectors:
      weighted_score *= 0.5  # 非热点板块惩罚

Step 5: 排序
  primary key: consensus_count DESC
  secondary key: weighted_score DESC

Step 6: 因子去冗余
  对每只 pick 的 factor_breakdown:
    计算 Pearson 相关矩阵
    若 corr(f1, f2) > 0.8:
        保留主因子（权重更高者），丢弃 f2
        factor_redundancy[f1].append(f2)

输出: top_n 只候选，每只含 weighted_score + reduced_breakdown
```

### 2.3.5 模式画像（初始版本）

| 模式 | precision | recall | style | env_affinity |
|------|-----------|--------|-------|--------------|
| leader_scalp | 0.72 | 0.43 | momentum | bull:1.3, neutral:1.0, bear:0.5 |
| leader_auction | 0.65 | 0.35 | event_driven | bull:1.1, neutral:1.0, bear:0.6 |
| leader_intraday | 0.68 | 0.40 | momentum | bull:1.2, neutral:0.9, bear:0.4 |
| bi_trend_launch | 0.55 | 0.78 | trend | bull:0.9, neutral:1.1, bear:1.2 |
| short_mode | 0.48 | 0.62 | statistical | bull:0.8, neutral:1.0, bear:1.3 |
| supply_chain | 0.60 | 0.52 | theme | bull:1.1, neutral:1.0, bear:0.8 |

> 这些数值是初始估算，需通过回测校准。

---

## 2.4 模块⑤: RiskParityAllocator — 风险平价仓位分配

### 2.4.1 职责

对融合后的 top_n 候选，根据波动率倒数分配仓位权重，替代固定 max_position。

### 2.4.2 接口

```python
class RiskParityAllocator:
    """风险平价仓位分配器."""

    def allocate(
        self,
        picks: list[dict],
        total_capital: float,
        max_single_weight: float = 0.15,
        target_volatility: float = 0.15,
        lookback_days: int = 20,
    ) -> AllocationResult:
        """返回建议仓位。

        Returns:
            AllocationResult:
                picks_with_weight: list[dict]  # 每只股票含 weight + target_shares
                total_capital: float
                expected_vol: float             # 组合预期波动率
        """
```

### 2.4.3 数据结构

```python
@dataclass
class AllocationResult:
    picks_with_weight: list[dict]   # 每只 pick 新增 weight + target_shares 字段
    total_capital: float
    expected_vol: float              # 组合预期波动率
    max_single_weight_actual: float  # 实际最大单股权重
```

### 2.4.4 算法

```
输入: picks (含 code), total_capital, max_single_weight

Step 1: 获取历史波动率
  对每只 pick，查询 daily_kline 近 lookback_days 日的 pct_chg
  vol[i] = stddev(pct_chg) / 100

Step 2: 风险平价权重
  inv_vol[i] = 1 / vol[i]
  raw_weight[i] = inv_vol[i] / sum(inv_vol)

Step 3: 仓位上限裁剪
  若 raw_weight[i] > max_single_weight:
      截断为 max_single_weight
      余量重新按比例分配给其他股票

Step 4: 目标股数
  target_amount[i] = raw_weight[i] × total_capital
  target_shares[i] = floor(target_amount[i] / price[i] / 100) × 100

输出: picks_with_weight
```

---

# 第三章：优化点清单

> 按严重度分级：🔴 高 / 🟡 中 / 🟢 低
> 按可行性分级：✅ 现有数据可支持 / ⚠️ 需新增数据 / ❌ 需外部依赖

## 3.1 现有引擎缺陷修复

| # | 优化点 | 现状 | 改进 | 优先级 | 可行性 |
|---|--------|------|------|--------|--------|
| O1 | leader_scalp 无 factor_breakdown | 仅输出 score | 新增 breakdown 字段 | 🔴 | ✅ |
| O2 | leader_auction 无 factor_breakdown | 仅输出 score | 新增 breakdown 字段 | 🔴 | ✅ |
| O3 | bi_trend_launch 样本外亏 -1.075%/月 | 策略逻辑本身无 alpha | 已冻结，作快照保留 | 🔴 | ✅ |
| O4 | 11 引擎参数分散在各文件 | 部分在 params.py | 统一外置 configs/engines/ | 🟡 | ✅ |
| O5 | leader_intraday/leader_closing 权重重复 | 两份几乎相同代码 | 抽取共享基类 | 🟡 | ✅ |
| O6 | supply_chain layer 匹配用硬编码关键词 | 关键词表在源码 | 外置 JSON 配置 | 🟢 | ✅ |
| O7 | cb_floor 评级软扣分无数据源校验 | 直接读 analyst_reports | 加 ORDER BY pub_date DESC | 🟢 | ✅ |

## 3.2 架构层优化

| # | 优化点 | 现状 | 改进 | 优先级 | 可行性 |
|---|--------|------|------|--------|--------|
| A1 | merge_picks 简单加权 | +10/固定计数 | WeightedFusionEngine (动态权重) | 🔴 | ✅ |
| A2 | 无市场环境感知 | 牛市熊市相同权重 | market_env 传入 fusion | 🔴 | ✅ |
| A3 | 因子相关性未处理 | 50+ 因子可能有 70%+ 冗余 | Pearson 去冗余 (>0.8 合并) | 🔴 | ✅ |
| A4 | 无板块热度过滤 | 全市场随机选 | SectorHeatmapEngine | 🔴 | ⚠️ |
| A5 | 无实时情绪层 | 完全依赖历史行情 | LLMIntelligenceEngine | 🟡 | ⚠️ |
| A6 | 无仓位动态调整 | 固定 max_position | RiskParityAllocator | 🟡 | ✅ |
| A7 | factor_breakdown 仅 1 个引擎输出 | 其他 10 引擎无 breakdown | 逐步补齐 | 🟡 | ✅ |
| A8 | orchestrator 无降级机制 | 单引擎异常 → 整体失败 | 增加 engine-level try/catch | 🟢 | ✅ |

## 3.3 可解释性优化

| # | 优化点 | 现状 | 改进 | 优先级 | 可行性 |
|---|--------|------|------|--------|--------|
| X1 | 无自然语言解释 | 仅输出 score + grade | 生成 entry_reason 文本 | 🟡 | ✅ |
| X2 | 无 SHAP 归因 | factor_breakdown 是百分比堆叠 | TreeExplainer 归因 | 🟢 | ⚠️ |
| X3 | 无历史对比 | 每次运行结果独立 | 记录历史 picks 变化 | 🟢 | ✅ |

## 3.4 政策导向对齐

| # | 优化点 | 政策方向 | 改进 | 优先级 | 可行性 |
|---|--------|---------|------|--------|--------|
| D1 | 硬科技赛道权重提升 | 第五套标准扩至 AI | supply_chain 新增 AI/量子赛道 | 🔴 | ✅ |
| D2 | 低空经济候选池 | 区域金融枢纽 | supply_chain 新增低空经济产业链 | 🟡 | ✅ |
| D3 | 宽基指数模式 | 试点主动型 ETF | 新增 MultiIndexEngine | 🟡 | ⚠️ |
| D4 | 财务舞弊过滤 | 全链条执法 | 基本面 filter 新增异常检测 | 🟡 | ⚠️ |
| D5 | 分红约束评分 | 公司治理 + 分红约束 | 高分红因子纳入 multi_factor | 🟢 | ✅ |

---

# 附录：实施路线图

## Phase 0 — 基线验证（1 周）

**目标**: 确认 11 引擎的 historical precision/recall

- [ ] 回测每个模式近 2 年的命中率
- [ ] 生成 mode_profiles.json
- [ ] 建立 baseline: 简单 consensus voting 的命中率

## Phase 1 — 核心融合（4 周）

**目标**: 替换 merge_picks，引入 WeightedFusionEngine

- Week 1: 实现 WeightedFusionEngine + mode_profiles
- Week 2: 实现 compute_dynamic_weights + factor_redundancy
- Week 3: A/B 测试（baseline vs V5.0），评估命中率提升
- Week 4: 合并至 orchestrator（环境变量切换）

**验收标准**: 命中率提升 ≥ 10pct

## Phase 2 — 情绪系统（3 周）

**目标**: LLMIntelligenceEngine 上线

- Week 5: 实现 LLMIntelligenceEngine (DeepSeek API)
- Week 6: SectorHeatmapEngine + sentiment_filter
- Week 7: 前端可视化 + 情绪过滤启动

**验收标准**: 情绪覆盖 top_n 候选，风险信号提前暴露

## Phase 3 — 深度优化（3 周）

**目标**: SHAP + Risk Parity + MultiIndex

- Week 8: SHAP Explainability + 前端组件
- Week 9: RiskParityAllocator + 回测验证
- Week 10: MultiIndexEngine

## Phase 4 — 监控与迭代（2 周）

**目标**: 全链路监控 + 模式画像持续校准

- Week 11: 监控埋点（命中率趋势/情绪生效周期）
- Week 12: mode_profiles 滚动校准（月度更新）

## 成本估算

| 项 | 费用 |
|----|------|
| DeepSeek API（月度） | ¥90 |
| Redis（现有） | ¥0 |
| PG（现有） | ¥0 |
| **总月度成本** | **≈ ¥90** |

## 预期收益

| 指标 | Baseline | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|------|----------|-----------|-----------|-----------|
| 命中率 | 58% | 71% (+13) | 75% (+4) | 76% (+1) |
| 热点捕捉 | 40% | 68% (+28) | 83% (+15) | 85% (+2) |
| 风险识别提前 | -3d | -3d | **+30d** | +30d |
| 可解释性 | 1/5 | 2/5 | 3/5 | 5/5 |

---

**文档状态**: 等待阅读确认后再决定是否实施
**下一步**: 阅读后确认实施范围（全量/部分） → 启动 Phase 0
