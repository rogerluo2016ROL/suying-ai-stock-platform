# 产业链研究与选股模型 V2 设计

**日期：** 2026-07-11

**状态：** 已确认设计，待实施计划

**目标模型：** `supply_chain_research_selection_v2`

**兼容模型：** `supply_chain_expectation_gap_v1`

## 1. 背景

现有系统已经具备：

- L1-L8 产业链层级；
- 复杂科技产业链模板；
- 公司—业务标签映射；
- 研究阶段 R0-R6、商业阶段 C0-C7；
- 高增长、高盈利、高围墙“三高”评分；
- 证据事件、证据重评、新鲜度和预期兑现跟踪；
- 产业链预期差选股模型 V1；
- `screening_snapshots`、`screening_models`、`model_registry` 和模型版本记录。

现有模型的主要问题不是缺少产业目录，而是产业研究与公司选股仍有混用：

1. L1-L8 能表达需求到商业变现的纵向传导，但节点内部的技术、BOM、价值量、壁垒、供需、证据和市场预期缺少统一横向结构；
2. 产业重要性、公司业务真实性、公司业绩受益度和股票交易机会没有拆成独立判断；
3. 三高同时承担经营质量和最终选股功能，且高围墙在 V1 排名中存在重复计权；
4. 技术验证、客户验证、业绩兑现和概念相关公司使用同一排序口径；
5. 缺失数据容易被当成零分，无法区分“差”和“不知道”；
6. 同一股票命中多个标签时，简单累加可能奖励概念数量，而非真实业绩；
7. 新模型是否更有效尚未经过 V1/V2 并行和样本外消融验证。

本设计保留现有 L1-L8、证据体系和 V1 模型，新建“双引擎”：产业链研究引擎与公司选股引擎。灵巧手（含轴向磁通电机）作为首个完整验收案例，但底层能力必须适用于全部复杂产业链。

## 2. 目标与非目标

### 2.1 目标

1. 保留 L1-L8 纵向主链，为每个节点增加八个横向研究维度；
2. 显式表达产品流、价值流、技术流、数据流四类传导关系；
3. 将产业节点吸引力、业务真实性、公司产业受益度、市场预期差、风险和可信度分开计算；
4. 将三高升级为公司相关业务的经营质量模块，不再直接代表最终选股结论；
5. 建立 A 业绩兑现、B 客户验证、C 技术卡位、D 概念观察四个股票池及状态迁移；
6. 所有关键分数能够下钻到因子、事实、证据原文、来源和日期；
7. V1/V2 并行，V2 首次只注册为 `staging`；
8. 通过灵巧手案例验证轴向磁通电机不会仅凭“可用于机器人”进入高等级股票池。

### 2.2 非目标

- 不替换或重命名现有 L1-L8；
- 不删除或覆盖 V1 模型和历史快照；
- 不让 LLM 自动批准证据、升级阶段或提升股票池；
- 不把产业空间预测、券商观点或互动问答当成已兑现收入；
- 不自动产生买卖建议或接入实盘交易；
- 不在首版训练机器学习权重；
- 不因本设计顺带重构无关页面和服务。

## 3. 核心设计原则

### 3.1 两个引擎、五道判断

```text
产业链研究引擎
  L1-L8 × 横向八维 × 四类传导边
  → 节点吸引力

公司选股引擎
  公司—节点映射
  → 业务真实性硬门槛
  → 公司产业受益度
  → 市场预期与催化修正
  → 风险和可信度约束
  → 四股票池
```

五道判断严格分开：

1. 产业节点是否重要；
2. 公司是否真实参与；
3. 公司能否形成收入和利润；
4. 市场是否已充分定价；
5. 当前证据是否足以支持该结论。

### 3.2 缺失不等于零分

- 已证实表现差：保存 `0-100` 的低分；
- 数据缺失：保存 `NULL`，状态为 `unknown`；
- 使用代理数据：保存分数，同时标记 `estimated` 或 `proxy` 并限制上限；
- 评分聚合时只使用有效子项，并输出 `coverage_ratio`；
- 覆盖率不足不会自动得到高分，必须降低可信度并限制准入池。

### 3.3 事实、推断和市场信号分离

- `confirmed_fact` 可以支持阶段和股票池升级；
- `company_claim` 需要后续验证；
- `analyst_estimate` 只能进入估算字段；
- `market_signal` 只能进入市场预期维度；
- `rumor_signal` 不参与真实性准入分。

### 3.4 按时间截面计算

所有选股分数必须有 `trade_date` 或 `as_of_date`，只允许使用该日期及之前发布、且当时可获得的证据，防止后验信息泄漏。

## 4. L1-L8 纵向主链

| 层级 | 名称 | 研究问题 |
|---|---|---|
| L1 | 需求层 | 谁愿意为什么问题付费？ |
| L2 | 任务层 | 需求需要转化为哪些具体任务？ |
| L3 | 核心产品层 | 什么产品直接完成任务？ |
| L4 | 底层支撑层 | 哪些技术和部件决定产品性能？ |
| L5 | 集成层 | 如何把零部件变成可交付模组或系统？ |
| L6 | 配套层 | 规模制造依赖哪些材料、设备和服务？ |
| L7 | 基础设施层 | 生产、训练、测试、运维依赖什么底座？ |
| L8 | 商业变现层 | 谁付费、如何收费、收入和利润如何形成？ |

现有层级名称、`layer_id`、模板读取和 `/chain/deconstruct` 旧字段保持兼容。

### 4.1 四类传导边

| `flow_type` | 含义 | 示例 |
|---|---|---|
| `product_flow` | 材料、零部件、产品的物理流动 | 磁材 → 电机 → 执行器 |
| `value_flow` | 收入、成本和利润的转移 | 整手订单 → 执行器采购收入 |
| `technology_flow` | 性能或技术能力向下游传导 | 转矩密度 → 低减速比 → 回驱性 |
| `data_flow` | 数据、模型和反馈闭环 | 触觉数据 → 操作模型 → 任务成功率 |

每条边保存：

- 上下游节点；
- `transmission_logic`；
- `transmission_strength`；
- `transmission_lag_days`；
- `failure_conditions`；
- `leading_metric_ids`；
- `evidence_ids`；
- 证据覆盖率和复核状态。

### 4.2 传导强度

全部子项归一到 0-100：

```text
edge_score = demand_certainty
           × indispensability
           × contribution
           × effective_share
           × evidence_freshness
```

数据库中各项按 0-1 保存，最终 `transmission_strength` 转为 0-100。任何一项未知时不填零，输出 `NULL` 和覆盖率；至少四项有效且包含一条强证据时才形成正式边分数。

## 5. 八个横向研究维度

每个 L1-L8 节点均可保存以下八维。维度是横向视角，不是 L9-L16。

| 维度ID | 名称 | 核心内容 |
|---|---|---|
| `function_value` | 功能与任务价值 | 必要性、任务价值、付费意愿、替代方案 |
| `technology_route` | 技术路线与成熟度 | 路线分叉、性能、成熟度、量产难度、失效条件 |
| `physical_bom` | 物理BOM与供给结构 | 材料、部件、设备、单机用量、供应集中度 |
| `value_pool` | 价值量与利润池 | ASP、单机价值量、成本占比、毛利、降价、更换周期 |
| `competition_moat` | 竞争格局与壁垒 | 良率、认证、切换成本、数据、规模、知识产权 |
| `supply_demand_cycle` | 供需与产业周期 | 有效产能、利用率、库存、价格、交期、渗透率 |
| `evidence_validation` | 证据与商业验证 | 产品、客户、订单、收入、利润及证据质量 |
| `market_expectation` | 市场预期与交易状态 | 涨幅、换手、估值、覆盖、盈利预测和拥挤度 |

每个维度统一输出：

```json
{
  "dimension_id": "value_pool",
  "status": "known|estimated|proxy|unknown|contradicted",
  "score": 0,
  "coverage_ratio": 0.0,
  "confidence_score": 0,
  "payload": {},
  "evidence_ids": [],
  "as_of_date": "2026-07-11",
  "review_status": "pending_review"
}
```

## 6. 技术路线模型

技术路线不能只作为关键词保存在 `segments` 中。每条路线需要独立生命周期和替代关系：

- `route_id`、`route_name`；
- 所属链和节点；
- `maturity_stage`：`concept`、`prototype`、`engineering_sample`、`customer_validation`、`small_batch`、`mass_production`、`mature`、`declining`；
- 性能指标、量产难度、成本趋势；
- `substitutes_route_ids`；
- `failure_conditions`；
- 代表产品和公司映射；
- 最近强证据日期。

灵巧手中的轴向磁通电机首先属于 L4 底层支撑层。只有实际证据支持时，才能通过 `technology_flow` 连接到 L5 低减速比执行器、掌内腱绳执行器或腕部模组，不能把汽车轴向磁通电机直接视为灵巧手产品。

## 7. 产业节点吸引力

### 7.1 公式

```text
node_attractiveness =
    demand_certainty          × 0.20
  + value_pool_score          × 0.15
  + bottleneck_score          × 0.15
  + supply_demand_score       × 0.15
  + technology_maturity_score × 0.10
  + commercialization_score   × 0.10
  + transmission_score        × 0.10
  + evidence_quality_score    × 0.05
```

### 7.2 上限规则

- 无真实下游需求证据：`demand_certainty <= 40`；
- 无产品样机：`technology_maturity_score <= 35`；
- 只有市场空间预测：`commercialization_score <= 30`；
- 单机价值量无法估算：`value_pool_score <= 50`；
- 没有强证据：节点可展示，但 `score_status=insufficient_evidence`，不参与正式候选筛选。

## 8. 业务真实性

### 8.1 证据等级

| 等级 | 含义 | 允许进入的最高股票池 |
|---|---|---|
| E0 | 只有传闻 | 不入池 |
| E1 | 理论或概念相关 | D 概念观察池 |
| E2 | 有明确产品、型号或样机 | C 技术卡位池 |
| E3 | 已送样、测试或客户联合验证 | B 客户验证池 |
| E4 | 有定点、订单或小批量交付 | A 业绩兑现候选池 |
| E5 | 财报可识别相关收入 | A 业绩兑现池 |
| E6 | 可识别相关利润贡献 | A 业绩兑现池 |

### 8.2 真实性评分

```text
authenticity_score =
    product_evidence_score       × 0.30
  + customer_evidence_score      × 0.25
  + order_revenue_evidence_score × 0.25
  + source_reliability_score     × 0.10
  + freshness_score              × 0.10
```

`rumor_signal` 不参与任何子项。真实性作为公司受益分的乘数，而不是普通加分项。

## 9. 三高 V2：经营质量模块

三高继续针对“公司—业务标签”，不能使用公司整体指标直接替代目标业务。

### 9.1 高增长

```text
growth_v2 =
    realized_revenue_growth × 0.30
  + backlog_growth          × 0.25
  + customer_share_growth   × 0.20
  + delivery_growth         × 0.15
  + growth_sustainability   × 0.10
```

上限规则：

- 只有扩产无订单：最高 55；
- 只有送样无定点：最高 45；
- 只有产业预测无公司证据：最高 30；
- 增长来自非目标业务：不计入。

### 9.2 高盈利

```text
profit_v2 =
    segment_gross_margin        × 0.30
  + incremental_margin          × 0.20
  + price_cost_trend            × 0.15
  + cashflow_collection_quality × 0.15
  + profit_sustainability       × 0.10
  + capex_efficiency            × 0.10
```

数据上限：披露值 100、可靠估算 80、公司整体代理 60、同行代理 40；不可用时为 `NULL`。

### 9.3 高围墙

```text
moat_v2 =
    technical_performance × 0.20
  + yield_consistency     × 0.20
  + certification_switch × 0.20
  + supply_scarcity       × 0.15
  + data_ecosystem        × 0.10
  + scale_cost            × 0.10
  + intellectual_property × 0.05
```

专利数量、“国产替代”“龙头”“稀缺”等文本标签不能单独形成高围墙分。

### 9.4 三高总分

```text
operating_quality_score = growth_v2 × 0.35
                        + profit_v2 × 0.30
                        + moat_v2   × 0.35
```

只聚合有效子项并输出覆盖率。覆盖率低于 60% 时，经营质量总分不得用于 A 池准入。

## 10. 公司产业受益度

### 10.1 收入暴露度

```text
revenue_exposure = disclosed_business_revenue_ratio
                 × target_chain_relevance_ratio
                 × evidence_reliability_factor
```

不能把机器人业务收入全部视为灵巧手收入，也不能把汽车轴向磁通电机收入视为灵巧手收入。

### 10.2 利润弹性

```text
profit_elasticity = expected_incremental_revenue
                  × incremental_gross_margin
                  × (1 - incremental_expense_ratio)
                  / normalized_current_net_profit
```

净利润小于等于零、主要利润来自一次性收益、预计收入无订单或产能依据时，不计算该比率，只输出风险状态。

### 10.3 公司受益分

```text
benefit_raw =
    node_attractiveness     × 0.20
  + operating_quality_score × 0.20
  + revenue_exposure_score  × 0.20
  + order_certainty_score   × 0.15
  + profit_elasticity_score × 0.15
  + delivery_capability     × 0.10

benefit_score = benefit_raw × authenticity_score / 100
```

缺失的利润弹性不能按 0 分处理；使用有效因子重标权重，同时降低覆盖率和可信度。A 池仍必须满足经营质量覆盖率门槛。

## 11. 市场预期、催化与风险

### 11.1 预期差分

`expectation_gap_score` 统一为 0-100：0 为显著负预期差，50 为中性，100 为显著正预期差。

```text
expectation_gap_score = clamp(
    50
  + actual_progress_surprise × 0.35
  + strong_evidence_delta    × 0.25
  + progress_momentum        × 0.20
  + validation_proximity     × 0.20
  - market_crowding          × 0.30
  - valuation_overpricing    × 0.25
  - evidence_delay_decay     × 0.20,
  0, 100
)
```

上述正负项先归一到 0-50 的影响区间。股价下跌本身不构成正预期差。

### 11.2 催化分

催化必须有事件、预计日期和验证方式：

- 客户测试完成；
- 定点转订单；
- 产线投产；
- 财报披露收入；
- 产品发布或第三方检测；
- 行业采购或招标。

没有预计时间和验证条件的“未来有望”不计分。

### 11.3 风险分

```text
risk_score =
    technology_route_risk × 0.20
  + customer_concentration × 0.15
  + delivery_risk          × 0.15
  + expansion_risk         × 0.10
  + financial_risk         × 0.10
  + valuation_risk         × 0.10
  + governance_risk        × 0.10
  + liquidity_risk         × 0.10
```

业务映射被证伪、主要证据被澄清否认、重大退市风险、规格不符合目标场景属于否决项，不只做扣分。

### 11.4 最终机会分与可信度

```text
opportunity_score = clamp(
    benefit_score          × 0.55
  + expectation_gap_score × 0.30
  + catalyst_score        × 0.15
  - risk_score            × 0.30,
  0, 100
)

confidence_score =
    evidence_quality   × 0.35
  + evidence_coverage  × 0.25
  + evidence_freshness × 0.20
  + review_quality     × 0.20
```

最终输出必须同时保留 `opportunity_score`、`benefit_score`、`expectation_gap_score`、`risk_score`、`confidence_score`，不能只展示一个总分。

## 12. 四股票池

### 12.1 A：业绩兑现池

硬条件：

- E4 及以上；
- 商业阶段 C4 及以上；
- `authenticity_score >= 75`；
- `confidence_score >= 70`；
- `benefit_score >= 60`；
- 三高覆盖率不低于 60%；
- 至少存在订单、小批量交付或收入强证据；
- 无否决项。

内部排名强调利润弹性、订单确定性、经营质量、预期差和节点吸引力。

### 12.2 B：客户验证池

硬条件：

- E3 或 E4；
- 有送样、测试、定点或联合开发证据；
- `authenticity_score >= 60`；
- 有明确下一验证节点和预计日期；
- 客户验证证据未过期；
- 尚无足够证据进入 A 池。

### 12.3 C：技术卡位池

硬条件：

- E2 及以上；
- 有明确产品、型号或样机；
- 规格与目标应用相符；
- 至少一项可验证技术或制造壁垒；
- 尚无可靠客户商业证据。

### 12.4 D：概念观察池

- E1 或弱 E2；
- 只有“可用于”“正在布局”或产业理论映射；
- 缺少客户、订单和收入证据；
- 不写入正式推荐快照，不进入策略回测持仓。

### 12.5 状态迁移

```text
D --产品/样机确认--> C
C --送样/客户测试--> B
B --定点/订单/收入--> A
A --订单延期/持续性失效--> B
B --验证超期/客户退出--> C
C --产品适配失效--> D
D --映射证伪--> 排除
```

每次迁移保存原池、新池、触发证据、日期、审核状态、下一验证节点和预计日期。

默认证据有效期：送样 180 天、客户测试 180 天、定点 365 天、互动问答 90 天；订单和协议按合同期限；行业模板可覆盖默认值。

## 13. 多映射股票聚合

V2 不把同一股票的多个标签得分相加。

1. 每个 `mapping_id` 独立评分和分池；
2. 股票级结果选择 `benefit_score` 最高且证据等级最高的映射作为 `primary_mapping_id`；
3. 只有其他映射拥有独立业务分部或独立收入证据时，才可增加 `diversification_bonus`；
4. `diversification_bonus` 上限 5 分；
5. 同一证据、同一产品、父子节点重复命中不算独立映射；
6. 股票级池等级不得高于主映射允许的最高池；
7. 输出全部次要映射和未采纳原因。

## 14. 数据模型

新增 Alembic 迁移建议使用当前序列之后的下一个有效 revision；实施时必须先检查主分支最新 revision，不在设计中硬编码编号。

### 14.1 `supply_chain_node_dimensions`

按节点、维度和日期保存横向研究结果：

```text
dimension_record_id TEXT PRIMARY KEY
node_id TEXT NOT NULL
chain_id TEXT
template_id TEXT
dimension_id TEXT NOT NULL
as_of_date DATE NOT NULL
status TEXT NOT NULL
score DOUBLE PRECISION
coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
confidence_score DOUBLE PRECISION
payload JSONB NOT NULL DEFAULT '{}'
evidence_ids JSONB NOT NULL DEFAULT '[]'
review_status TEXT NOT NULL DEFAULT 'pending_review'
created_at TIMESTAMP
updated_at TIMESTAMP
UNIQUE(node_id, dimension_id, as_of_date)
```

`dimension_id` 限定为八维；`status` 限定为 `known/estimated/proxy/unknown/contradicted`。

### 14.2 `supply_chain_transmission_edges`

```text
edge_id TEXT PRIMARY KEY
chain_id TEXT NOT NULL
from_node_id TEXT NOT NULL
to_node_id TEXT NOT NULL
flow_type TEXT NOT NULL
transmission_logic TEXT NOT NULL
transmission_strength DOUBLE PRECISION
transmission_lag_days INTEGER
failure_conditions JSONB NOT NULL DEFAULT '[]'
leading_metric_ids JSONB NOT NULL DEFAULT '[]'
evidence_ids JSONB NOT NULL DEFAULT '[]'
coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0
review_status TEXT NOT NULL DEFAULT 'pending_review'
created_at TIMESTAMP
updated_at TIMESTAMP
UNIQUE(chain_id, from_node_id, to_node_id, flow_type)
```

### 14.3 `supply_chain_technology_routes`

保存路线生命周期、替代关系、性能、量产和成本信息。

### 14.4 `supply_chain_node_scores`

按 `node_id + trade_date` 保存节点八项子分、`total_score`、`coverage_ratio`、`score_status`、`score_detail` 和证据列表。

### 14.5 `business_tag_authenticity_scores`

按 `mapping_id + trade_date` 保存 E0-E6、五项真实性子分、总分、覆盖率、最高允许股票池、证据和复核状态。

### 14.6 `business_tag_operating_quality_scores`

新建三高 V2 表，不覆盖 `business_tag_three_high_scores`。保存增长、盈利、围墙的所有子分、数据状态、覆盖率、上限规则命中情况和总分。

### 14.7 `business_tag_benefit_scores`

保存节点吸引力、三高 V2、收入暴露度、订单确定性、利润弹性、交付能力、`benefit_raw`、真实性调整后的 `benefit_score` 和覆盖率。

### 14.8 `business_tag_selection_scores`

按 `mapping_id + trade_date + model_version` 保存：

- `benefit_score`；
- `expectation_gap_score`；
- `catalyst_score`；
- `risk_score`；
- `confidence_score`；
- `opportunity_score`；
- `pool_code`；
- `eligibility_status`；
- `veto_reasons`；
- `factor_detail`；
- `evidence_ids`。

### 14.9 `business_tag_pool_state` 与 `business_tag_pool_transition_log`

状态表保存当前池；日志表保存每次升级、降级和退出。当前状态通过日志驱动，不能直接覆盖而不留记录。

### 14.10 复用现有表

- `business_tag_mapping`：公司—节点映射；
- `company_business_segments`：业务分部和收入；
- `business_tag_evidence_events`、`raw_evidence_documents`、`evidence_extracted_facts`：证据；
- `business_tag_stage_tracking`、`business_tag_stage_transition_log`：阶段；
- `business_tag_evidence_freshness`：证据衰减；
- `business_tag_expectation_monitor`：声明兑现；
- `screening_snapshots`：A/B/C 分池快照及未来收益；
- `screening_models`、`model_registry`、`model_versions`：注册和版本。

## 15. 配置结构

`industry_chain_templates.json` 保留现有字段，新增可选结构：

```json
{
  "research_model_version": "v2",
  "dimensions": {},
  "technology_routes": [],
  "transmission_edges": [],
  "scoring_profile": {
    "node_weights": {},
    "benefit_weights": {},
    "opportunity_weights": {},
    "pool_thresholds": {},
    "evidence_expiry_days": {}
  }
}
```

全局默认权重放入独立配置段，行业模板只覆盖确有行业差异的阈值。禁止为每个产业复制一套完全相同的权重。

## 16. API 契约

### 16.1 兼容增强 `/chain/deconstruct`

旧请求和旧字段保持不变。传入 `research_model=v2` 时，每个节点附加：

```json
{
  "research_dimensions": [],
  "technology_routes": [],
  "transmission_edges": [],
  "node_score": {},
  "data_limitations": []
}
```

### 16.2 候选股票池

```text
GET /api/v1/supply-chain/selection/candidates
  ?chain_id=dexterous_hand
  &trade_date=2026-07-11
  &pool=A
  &model_version=v2
```

返回股票级主映射、次要映射、五个核心分数、证据等级、阶段、池状态、迁移历史摘要和限制说明。

### 16.3 公司解释页

```text
GET /api/v1/supply-chain/selection/stocks/{code}
  ?chain_id=dexterous_hand
  &trade_date=2026-07-11
```

返回每个 mapping 的评分路径和证据，不只返回最终排名。

### 16.4 管理端批量计算

批量计算接口必须支持 `dry_run=true`。写入操作返回各表新增、更新、跳过、拒绝的数量；证据不足时返回限制，不自动补造数据。

## 17. 灵巧手验收案例

灵巧手模板使用 L1-L8：

```text
L1 制造业柔性自动化、具身智能、危险作业、服务需求
L2 抓取、捏取、旋拧、插接、工具操作、手内操作
L3 灵巧手整机、工业灵巧末端、遥操作手
L4 电机、丝杠、减速器、腱绳、传感器、编码器、驱动芯片
L5 执行器模组、手指模组、掌内驱动、整手机电和手眼力控集成
L6 磁材、铜材、软磁材料、轴承、柔性电路、线缆、加工检测设备
L7 遥操作、数据采集、仿真训练、测试评价、自动化产线和维修网络
L8 整手销售、机器人配套、RaaS、数据服务、耗材和维护收入
```

轴向磁通电机设置真实性阶梯：

```text
AF0 只有技术概念
AF1 专利或实验室样机
AF2 有机器人规格产品和参数
AF3 装入关节、腕部或灵巧手样机
AF4 机器人客户送样、定点或联合验证
AF5 小批量交付
AF6 形成可识别收入和订单
```

映射规则：AF0 不能入池；AF1 最高 D；AF2-AF3 最高 C；AF4 最高 B；AF5-AF6 才可进入 A 候选，并继续满足 A 池其他硬条件。

### 17.1 必须通过的反例

1. 公司只有汽车轴向磁通电机产品：不能自动进入灵巧手 C/B/A 池；
2. 互动问答称“可用于人形机器人”：最高 D，90 天后未升级则过期；
3. 有专利无样机：最高 D；
4. 有样机无客户：最高 C；
5. 有送样且证据有效：可进入 B，但不能按订单估算收入；
6. 有订单但没有交付能力：A 候选，风险分上升，必要时仍留 B；
7. 灵巧手相关收入已披露但股价拥挤、估值透支：可留 A，机会分下降；
8. 同一公司同时命中“电机”“机器人”“灵巧手”：不得把三个标签分数累加。

## 18. 模型注册与快照

V2 注册参数：

```text
model_key: supply_chain_research_selection_v2
display_name: 产业链研究与选股模型 V2.0
category: 产业链
stage: staging
artifact_uri: 新的 V2 注册脚本
```

注册守则：

- V1 继续激活，保留原快照；
- V2 A/B/C 分池均可写研究快照，`factors.pool_code` 必须存在；
- D 池不写正式策略快照，可写独立观察记录；
- 同一股票同一交易日只以主映射进入同一模型池快照；
- `factors` 保存全部五个核心分数、主映射、证据等级、覆盖率和否决原因；
- 初始 `win_rate`、`mean_return` 为 `NULL`；
- 没有样本外结果前不得升级为 `production`。

## 19. 验证与回测

### 19.1 防止后验泄漏

- 证据使用 `publish_time <= trade_date cutoff`；
- 数据库后补的旧公告按原发布日期使用，但必须证明当时可获得；
- 人工复核时间晚于交易日时，不得回写为当时已批准；
- 行情、财务和复权数据固定版本和截止日期。

### 19.2 回测指标

- T+3、T+5、T+10、T+20收益和超额收益；
- 胜率、盈亏比、最大回撤、换手率；
- A/B/C 分池表现；
- 不同产业链、市值和市场环境分层；
- B→A、C→B 的转化率和平均耗时；
- 高分映射被证伪率；
- 证据过期后未兑现率。

### 19.3 消融实验

1. V1；
2. V2 完整模型；
3. V2 去掉横向八维；
4. V2 去掉市场预期；
5. V2 去掉风险惩罚；
6. 只使用三高 V2；
7. 只使用证据等级与阶段。

新模型复杂度只有在样本外效果、稳定性或可解释性至少一项显著改善且没有不可接受退化时才有价值。

## 20. 错误处理和降级

- 新表不存在：旧接口继续工作，V2接口返回 `503` 和明确缺表列表；
- 节点维度缺失：返回 `unknown` 和 `data_limitations`，不生成假分数；
- 强证据互相矛盾：状态为 `contradicted`，冻结自动升级并进入人工复核；
- 最新交易日或证据截面不存在：批量评分失败，不自动退回陈旧日期；
- 权重配置不合计为 1：启动校验失败；
- 分数超出 0-100：拒绝写入；
- 同一证据被多个子项引用：允许解释复用，但在证据覆盖统计中去重；
- 模型注册失败：评分数据保留，事务回滚注册和快照写入，避免半注册状态。

## 21. 安全与审计

- 所有写入脚本默认支持 `--dry-run`；
- 审核通过、驳回、池迁移和模型注册保留操作者与时间；
- 任何 API 不返回密钥、数据库 DSN 或内部授权信息；
- 模型输出标注“研究候选，不构成自动买卖建议”；
- 自动任务不能把弱证据提升为强证据；
- 对外报告必须区分事实、估算、代理和未知。

## 22. 验收标准

### 22.1 兼容性

- 现有 L1-L8、`complex_tech` 和 18 条产业链模板测试通过；
- V1 注册、快照和查询保持不变；
- 旧 `/chain/deconstruct` 响应结构不删除字段。

### 22.2 数据与评分

- 八维可按节点和日期保存；
- 四类传导边可追溯；
- 技术路线可保存生命周期和替代关系；
- 缺失值为 `NULL/unknown`，不被静默转为零；
- 三高 V2 只针对相关业务；
- 每个总分可还原到子分、权重和证据；
- 同一股票多映射不重复累加。

### 22.3 股票池

- A/B/C/D 准入和最高池上限生效；
- D 池不进入正式策略快照；
- 股票池迁移有完整日志；
- 证据过期能够触发复核或降级；
- 灵巧手八个反例全部通过。

### 22.4 注册与验证

- V2 以 `staging` 注册；
- V1/V2 可并行运行；
- 快照包含 `pool_code`、主映射和五个核心分数；
- T+3/T+5/T+10/T+20 回填可用；
- 没有样本外证据前不能升级 `production`。

## 23. 实施边界

该设计适合拆成四个可独立验收的实施阶段：

1. 节点八维、技术路线、传导边和节点吸引力；
2. 真实性、三高 V2、公司产业受益度；
3. 市场预期、风险、四股票池和迁移；
4. 灵巧手实例、V2 注册、快照、回测和消融实验。

每一阶段都必须有迁移契约测试、纯函数评分测试、数据库集成测试和 API 回归测试。不得在阶段一未形成可审计数据时提前注册 V2。
