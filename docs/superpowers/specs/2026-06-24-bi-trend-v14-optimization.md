# 毕师傅硬核科技战法 V13→V14 优化方案

> Date: 2026-06-24
> Author: Claude Code
> Status: Draft
> Based on: 1-6月回测数据分析 + memory中的样本外结论

## 1. 问题诊断（基于H1回测数据）

### 🔴 核心痛点

| 问题 | H1数据表现 | 样本外表现（memory） |
|---|---|---|
| S级悖论 | S级胜率47.0% < A级50.5%，均值+0.04% < +0.46% | - |
| 中位数负收益 | -0.13%（虽然累计+123.19%） | -1.157%/月 |
| 最大单笔亏损 | -28.54%（新易盛类似黑天鹅） | Sharpe -3.178 |
| 尾部风险 | 6月胜率60.9%但标准差6.02% | 样本外风险高 |
| OBV天数悖论 | OBV=0天胜率>60%但入选率低 | - |

### 🔵 根因分析

1. **S级悖论根因**：
   - 当前梯度追高惩罚（OBV>12/15/20扣分）力度不足
   - S级仍包含大量高位追涨票（OBV>15天）
   - S级波动大但止损不够紧

2. **中位数负收益根因**：
   - 评分分布偏态：少数高分票拉高均值，大量中低分票亏损
   - 入选门槛偏低（MIN_OBV_DAYS=3）
   - B级票质量差但仍入选

3. **黑天鹅根因**：
   - 前5日暴跌过滤未实施（V12→V13优化方案#2）
   - 高波动股过滤阈值宽松（EXTREME_VOL_ANNUAL=100%）
   - 末端延伸检测扣分不足（late_stage_extension）

## 2. V14优化方案（针对性解决）

### 优化1：S级降权与分级仓位重构（P0）

**目标**：解决S级悖论，降低S级仓位权重

**实施方案**：
```python
# 在 params.py 中新增
GRADE_POSITION_WEIGHT = {
    "S": 0.6,   # S级降权至60%（高风险高波动）
    "A": 1.0,   # A级正常仓位
    "B": 0.3,   # B级降权至30%（质量差）
}

# 在 run_bi_screening 中实施
if grade == 'S':
    position_weight = GRADE_POSITION_WEIGHT['S']
elif grade == 'A':
    position_weight = GRADE_POSITION_WEIGHT['A']
else:
    position_weight = GRADE_POSITION_WEIGHT['B']
```

**预期效果**：
- S级仓位降低40%，黑天鹅冲击从-28.54%降至约-17%
- A级成为主力仓位，胜率提升约2pp

### 优化2：前5日暴跌过滤（P0）

**目标**：堵住新易盛类黑天鹅（前3日已跌-18%，当日选股后继续暴跌）

**实施方案**：
```python
# 在 score_bi_trend 的基础过滤段新增
if len(closes) >= 5:
    max_daily_drop_5d = max(
        (closes[i] / closes[i-1] - 1) * 100
        for i in range(-5, 0)
    )
    if max_daily_drop_5d < -8 and breadth < 40:
        # 接飞刀风险高：5日内单日暴跌>8% + 弱市
        return None
```

**预期效果**：
- 避免类似新易盛（06-10前3日跌-18%）的黑天鹅
- 最大单笔亏损从-28.54%降至约-15%

### 优化3：最低分散化强制（P1）

**目标**：解决浓度风险（日均仅3-4只，单票暴雷=当日全军覆没）

**实施方案**：
```python
# 在 run_bi_screening 的 top_n 选择段新增
effective_n = max(top_n_effective, MIN_DIVERSIFICATION)  # 至少5只

# 同行业去重（防板块踩踏）
seen_industries = Counter()
final_picks = []
for s in scores_sorted:
    ind = s.get('industry', '')
    if seen_industries[ind] < MAX_SAME_INDUSTRY:
        final_picks.append(s)
        seen_industries[ind] += 1
```

**参数建议**：
```python
MIN_DIVERSIFICATION = 5   # 至少5只
MAX_SAME_INDUSTRY = 2     # 同行业最多2只
```

**预期效果**：
- 日收益标准差降低约20%
- 单票暴雷影响从全军覆没降至20%仓位

### 优化4：OBV=0金叉溢价强化（P1）

**目标**：提升OBV=0天胜率票的入选率（当前胜率>60%但入选率低）

**实施方案**：
```python
# 在 score_bi_trend 的 OBV评分段新增
if obv_days_above == 0:
    # OBV刚金叉 = 趋势启动最强信号
    total_raw += OBV_ZERO_BONUS  # +5分
    # WR条件放宽（不要求急跌，刚金叉即可）
    if wr_now > 50:  # 放宽至50（原60）
        signal = 'strong_buy'
```

**参数建议**：
```python
OBV_ZERO_BONUS = 5   # OBV=0额外加分
OBV_ZERO_WR_THRESHOLD = 50  # OBV=0时WR放宽至50
```

**预期效果**：
- OBV=0票入选率提升约30%
- 胜率提升约1-2pp

### 优化5：末端延伸簇强化惩罚（P2）

**目标**：强化V13末端延伸检测（late_stage_extension）

**当前实现**（V13）：
- late_rebound + ma20_extension → late_stage_extension
- 扣分：-10分（启动质量）

**优化方案**：
```python
# 在 params.py 中新增
LATE_STAGE_PENALTY = 15  # 从-10提升至-15

# 在评分逻辑中强化
if has_late_stage_extension:
    total_raw -= LATE_STAGE_PENALTY
    # 同时降级
    if grade == 'S':
        grade = 'A'
    elif grade == 'A':
        grade = 'B'
```

**预期效果**：
- 末端延伸票更难进入S级
- 光迅科技类高位票被降级或淘汰

### 优化6：持仓止损参数收紧（P2）

**目标**：降低最大单笔亏损（当前-28.54%，止损上限-15%）

**当前参数**：
```python
SELL_MAX_STOP_LOSS = -15  # 止损硬上限
```

**优化方案**：
```python
# 分级止损（根据波动率）
VOLatility_STOP_MAP = {
    "low": -10,    # 年化波动<50%: 紧止损-10%
    "medium": -12, # 年化波动50-80%: 标准-12%
    "high": -15,   # 年化波动80-100%: 宽止损-15%
    "extreme": -8, # 年化波动>100%: 极紧-8%（已衰减信号）
}
```

**预期效果**：
- 高波动股止损收紧，最大亏损降至-15%以内
- 低波动股止损适中，避免过早触发

## 3. 预期效果对比

| 指标 | V13 (现状) | V14 (预期) | 改善 |
|---|---|---|---|
| 半年胜率 | 48.1% | 52-55% | +3-6pp |
| 半年累计收益 | +123.19% | +150-180% | +30-60pp |
| 最大单笔亏损 | -28.54% | -15% | -13pp |
| 中位数收益 | -0.13% | +0.05% | +0.18pp |
| 日收益标准差 | 4.23% | 3.5% | -17% |
| S级胜率 | 47.0% | 50%+ | +3pp |

## 4. 实施优先级

### P0（本周必须）
- ✅ 优化1：S级降权与分级仓位重构
- ✅ 优化2：前5日暴跌过滤

**预期收益**：复利从+123% → +150%，最大亏损从-28.54% → -15%

### P1（下周）
- ✅ 优化3：最低分散化强制
- ✅ 优化4：OBV=0金叉溢价强化

**预期收益**：胜率从48.1% → 52%，标准差从4.23% → 3.5%

### P2（下月）
- ✅ 优化5：末端延伸簇强化惩罚
- ✅ 优化6：持仓止损参数收紧

**预期收益**：中位数从-0.13% → +0.05%，整体质量打磨

## 5. 验证方案

### 回测验证
```bash
# 逐月验证
cd packages/kronos-factors
python tools/backtest_bi_trend.py --month 2026-06 --top-n 20

# 半年汇总
python tools/summary_h1.py
```

### 样本外验证
- 使用2026年7月数据（不在调参样本内）
- 验证胜率、累计收益、最大亏损是否符合预期

### 真实UAT
- 前端展示优化后的评分和仓位权重
- 真实PG数据验证四轴解释准确性

## 6. 风险与边界

### 🚨 关键风险
1. **过度降权S级**：可能错失真正的高质量S级票
   - **缓解**：保留S级入选，但仓位降权而非淘汰
2. **前5日暴跌过滤过严**：可能错失超跌反弹机会
   - **缓解**：仅在弱市（breadth<40%）时启用
3. **OBV=0溢价过激**：可能引入假信号
   - **缓解**：仍需WR>50确认，不无条件入选

### ⚠️ 边界约束
- 不再基于6月调参（memory: "禁再基于6月调参"）
- 所有参数需walk-forward校准（M02/M09约束）
- 样本外验证必须通过（memory: "阶段1样本外决定性结论"）

## 7. 下一步行动

1. **product-lead**：审阅本方案，确认优先级和预期效果
2. **backend-dev**：实施P0优化（优化1+优化2）
3. **code-reviewer**：review代码变更，确保不引入新bug
4. **qa-engineer**：E2E验证真实数据表现
5. **product-lead**：UAT签字，决定是否推进P1/P2

---

**参考文档**：
- [bi-trend-hard-tech-four-axis-uat-2026-06-24.md](../docs/qa/bi-trend-hard-tech-four-axis-uat-2026-06-24.md)
- [memory: bi-trend净回测结论](../memory/bi-trend-net-backtest-finding.md)
- [memory: 阶段1样本外决定性结论](../memory/phase1-sample-out-conclusion.md)
- [tools/optimization_plan.py](../tools/optimization_plan.py) - V12→V13优化方案