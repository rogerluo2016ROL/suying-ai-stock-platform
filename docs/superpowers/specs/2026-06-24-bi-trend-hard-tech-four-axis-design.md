# 毕师傅趋势启动硬核科技选股：四轴增强设计

## 1. 设计结论

本次优化采用“四轴分层增强”，保留现有 `BiTrendLaunchEngine` 主链路，不重写整套策略。实现范围集中在 `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py` 的真实调用路径：

```text
BiTrendLaunchEngine.run
  -> run_bi_screening
    -> _score_bi_trend_arrays
```

目标是同时强化四件事：

| 目标 | 改造层 | 结果 |
|---|---|---|
| 少踩坑 | `startup_quality` | 降低假启动、追高、弱市单日反弹误选 |
| 抓爆发 | `ignition_power` | 提高刚点火、点火后蓄力、WR 压缩反转票的排序 |
| 更硬核科技 | `hard_tech_conviction` | 明确赛道强弱、卡脖子稀缺和行业匹配原因 |
| 解释更清楚 | `explainability` | 每只票输出分项分数、入选原因和风险旗标 |

本次不做大规模拆文件。`bi_trend_launch.py` 目前已有 M15 参数抽离和 M02/M09 审计约束，函数级拆分会扩大回归面。四轴增强先以小函数方式落地，新增测试锁住行为。

## 2. 当前实现依据

现有硬核科技选股由 `services/screener-service/app/routers/screener.py` 的 `_run_bi_trend_mode` 调用 `BiTrendLaunchEngine.run`。`BiTrendLaunchEngine.run` 默认 `hard_tech_only=True`，最终由 `run_bi_screening` 过滤股票池，再调用 `_score_bi_trend_arrays` 评分。

当前策略已经具备这些能力：

| 能力 | 现状 |
|---|---|
| 趋势启动 | OBV 天数倒置、WR 三日轨迹、缩量、ADX、均线、区间位置 |
| 弱市控制 | 涨跌比熔断、弱市缩小 `effective_n`、部分 S 级降权 |
| 硬科技过滤 | `HARD_TECH_INDUSTRY_KW` 行业关键词和 `_get_hard_tech_track` 赛道标签 |
| 卡脖子辅助 | `_get_industry_peers` 按同行数给 0/1/2 稀缺分 |
| 输出字段 | 总分、评级、信号、OBV/WR/量能/均线/ADX 等分项 |

主要短板：

| 短板 | 影响 |
|---|---|
| 质量过滤分散在主函数内 | 很难看出一只票为什么被降级 |
| 点火和蓄力加分散落在评分中 | 抓爆发能力不易调试，也不易测试 |
| 硬科技赛道只有简单字符串匹配 | 不能区分强硬科技、泛科技和疑似误匹配 |
| 输出解释缺少结构 | 前端和人工复核需要自己拼原因 |

## 3. 方案边界

### 3.1 本次要做

新增四个轻量评分辅助函数，供 `_score_bi_trend_arrays` 调用：

```python
_score_startup_quality(...)
_score_ignition_power(...)
_score_hard_tech_conviction(...)
_build_bi_trend_explanation(...)
```

这些函数只消费 `_score_bi_trend_arrays` 已经算出的中间变量，尽量不新增数据库查询。`run_bi_screening` 只负责把行业、同行数、赛道信息传入评分函数。

### 3.2 本次不做

| 不做项 | 原因 |
|---|---|
| 不重写 `run_bi_screening` | 涉及市场环境、实时日线 fallback、候选排序和仓位控制，回归面大 |
| 不修改卖出决策树 | 用户目标是选股优化，卖出系统属于另一条风险链路 |
| 不引入新外部依赖 | 项目规则要求微服务间调用和因子引擎保持轻依赖 |
| 不做新的回测调参 | M02/M09 已标明不能基于样本内反复调参；本次只做结构化信号增强和测试 |

## 4. 四轴增强设计

### 4.1 `startup_quality`：少踩坑

该层把“看起来启动但容易失败”的条件收拢成一个质量分和风险旗标。

输入来自已有变量：

```text
breadth / regime
annual_vol / vol_regime
obv_days_above / obv_slope / obv[-1]
wr_now / wr_d1 / wr_level / wr_fast_v10
vol_ratio / vol_rebound_ratio
price_to_ma20 / distribution_penalty / dead_cat / weekly_bearish
```

输出：

```python
{
    "score_adj": -12..4,
    "quality_flags": ["weak_market_single_pop", "ma20_extension", ...],
    "risk_flags": ["distribution_day", "high_volatility", ...],
}
```

规则方向：

| 场景 | 处理 |
|---|---|
| 弱市里单日急弹，但无两日确认 | 降分并标记 `weak_market_single_pop` |
| WR 已到高位且近 5 日涨幅过大 | 降分并标记 `late_rebound` |
| MA20 偏离过大 | 保留现有惩罚，同时加入解释旗标 |
| 最大量日为阴线 | 降级逻辑不变，加入 `distribution_day` |
| 高波动或极端波动 | 保留原衰减，加入 `high_volatility` 或 `extreme_volatility` |

### 4.2 `ignition_power`：抓爆发

该层奖励“刚启动且还有弹性”的组合，而不是奖励已经涨完的趋势延续。

输入来自已有变量：

```text
obv_days_above / obv_slope / obv_accel_score
wr_now / wr_level / wr_freshness_bonus
ignition_bonus / coiling_bonus / compression_reversal_bonus
range_pos / higher_low / two_day_up / rebound_confirmed
vol_ratio / vol_rebound_ratio
```

输出：

```python
{
    "score_adj": 0..10,
    "power_flags": ["fresh_obv_breakout", "coiling_after_ignition", ...],
}
```

规则方向：

| 场景 | 处理 |
|---|---|
| OBV 0 到 3 天且 OBV 为正 | 加分，标记 `fresh_obv_breakout` |
| 点火后缩量横盘 | 加分，标记 `coiling_after_ignition` |
| WR 压缩反转且区间底部 | 加分，标记 `compression_reversal` |
| 低点抬高、反弹确认、量能不过热 | 加分，标记 `higher_low_rebound` |
| OBV 超过 12 天且 WR 高位 | 不加爆发分，交给质量层降风险 |

### 4.3 `hard_tech_conviction`：更硬核科技

现有 `_get_hard_tech_track` 只返回一个赛道名。本次新增 conviction 层，给出赛道强度和匹配原因。

输出：

```python
{
    "score_adj": 0..6,
    "track": "AI算力",
    "tier": "core" | "strategic" | "broad",
    "matched_keywords": ["光模块", "CPO"],
    "conviction_reason": "AI算力核心链条",
}
```

建议分层：

| 层级 | 赛道示例 | 加分 |
|---|---|---|
| `core` | AI算力、半导体、机器人、低空经济、信创国产、工业母机 | 4 到 6 |
| `strategic` | 锂电储能、新材料、军工、通信、医疗器械 | 2 到 4 |
| `broad` | 泛新能源、泛电子、泛制造等宽口径匹配 | 0 到 2 |

卡脖子稀缺性继续使用同行数量，但解释从单一数值升级为：

```python
{
    "chokepoint_level": "scarce" | "oligopoly" | "normal",
    "peer_count": 3,
    "chokepoint_reason": "同行数 <= 3，赛道供给稀缺",
}
```

### 4.4 `explainability`：解释清楚

每只票新增稳定解释字段：

```python
{
    "factor_breakdown": {
        "obv": 26,
        "wr": 28,
        "volume": 6,
        "ma": 8,
        "adx": 6,
        "sector": 5,
        "startup_quality": -3,
        "ignition_power": 7,
        "hard_tech_conviction": 5,
    },
    "entry_reason": "OBV 新近翻强，WR 压缩后反弹，点火后缩量蓄力，属于 AI算力核心链条",
    "quality_flags": ["fresh_obv_breakout", "coiling_after_ignition"],
    "risk_flags": ["weak_market"],
    "hard_tech": {
        "track": "AI算力",
        "tier": "core",
        "matched_keywords": ["光模块"],
        "chokepoint_level": "oligopoly",
    },
}
```

已有字段保持兼容，包括 `total_score`、`grade`、`signal`、`hard_tech_track`、`chokepoint_score`、`checklist_score`、`ignition_bonus`。

## 5. 排序和信号影响

四轴增强不能直接推翻现有排序。建议影响方式如下：

| 分数来源 | 影响 |
|---|---|
| `startup_quality.score_adj` | 直接进入 `total_raw`，范围控制在 -12 到 +4 |
| `ignition_power.score_adj` | 直接进入 `total_raw`，范围控制在 0 到 +10 |
| `hard_tech_conviction.score_adj` | 替代或补充原 `ht_score + cp_score`，总上限 8 |
| `explainability` | 不影响排序，只负责输出 |

信号分层保持现有 `strong_buy`、`buy`、`watch`、`no_signal`。只增加两个降级条件：

| 条件 | 处理 |
|---|---|
| `risk_flags` 包含 `late_rebound` 且信号为 `strong_buy` | 降为 `buy` |
| `risk_flags` 包含 `distribution_day` 且信号为 `buy` 或 `strong_buy` | 维持现有派发降级，并在解释字段显示 |

## 6. 测试设计

新增测试文件：

```text
packages/kronos-factors/tests/test_bi_trend_four_axis.py
```

测试覆盖：

| 用例 | 断言 |
|---|---|
| 核心硬科技赛道匹配 | AI算力、半导体、机器人等返回 `tier=core` 和正向加分 |
| 泛科技误匹配不过度加分 | 宽泛行业不会拿到核心赛道分 |
| 点火蓄力加分 | 构造点火后缩量横盘数组，`ignition_power.score_adj > 0` |
| 高位假启动降级 | 构造 WR 高位、MA20 偏离、放量反弹，出现风险旗标 |
| 解释字段稳定 | `_score_bi_trend_arrays` 返回 `factor_breakdown`、`entry_reason`、`risk_flags`、`hard_tech` |

已有测试也要跑：

```text
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v
cd packages/kronos-factors && pytest tests/test_m15_params_extraction.py tests/test_calc_obv_wr_vectorized.py -v
```

如果本地依赖环境允许，再跑：

```text
cd packages/kronos-factors && pytest tests/ -v
```

## 7. 验收标准

实现完成后，应满足：

| 验收项 | 标准 |
|---|---|
| 兼容性 | 现有调用 `BiTrendLaunchEngine().run(...)` 不需要改参数 |
| 输出稳定 | 原有字段保留，新字段只新增不破坏 |
| 少踩坑 | 假启动样本在单测中被降级或标记风险 |
| 抓爆发 | 点火蓄力样本在单测中获得正向爆发分 |
| 硬科技 | 核心硬科技赛道有更明确的 `tier`、关键词和原因 |
| 可解释 | 每只返回票能说明入选原因和主要风险 |
| 测试 | 新增测试通过，相关回归测试通过 |

## 8. 自检

本设计没有新增数据库 schema，没有要求前端同步改版，也没有引入新依赖。改动集中在策略评分和返回字段，符合当前“先强优化模型输出，再决定 UI 展示”的节奏。

设计避免基于单月回测重新调参。新增分数有上限，风险降级有明确旗标，测试会覆盖关键路径。
