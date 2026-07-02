# 大葱产业链解构 V2 数据支撑评估与落地计划

日期：2026-07-02

关联方案：

```text
docs/prd/supply-chain-business-tag-tracking-2026-07-02.md
```

## 判断

这份文档完全按 V2 方案拆。上一版更多是在做数据盘点，没有把 V2 方案里的 10 步流程、L1 到 L8 层级、四种拆法逐项展开。本版改成同构设计：方案怎么拆，数据和工程就怎么落。

现有数据可以支撑第一版，但不能支撑最终版。可立即启动的是“业务标签、证据事件、研发/商用阶段、初版三高评分、初版预期差”。暂时不能做准的是“全市场标签收入占比、标签毛利占比、研报正文证据、公告正文证据、严格预期差回测”。

核心限制有三条：

```text
fina_mainbz 只有 276 行、50 个代码，biz_ratio 全空，且多数代码不能直接匹配 stocks
announcements 有 23034 行，但 content 为空
research_reports_tushare 有 116266 条，但主要是标题级证据
```

所以第一版不能假装已经能精确拆每家公司每个标签的收入和毛利。第一版要先把证据链和阶段跟踪做起来，再补主营构成和正文解析。

## 按 V2 10 步流程拆解

V2 方案的完整流程是：

```text
1. 定政策主题
2. 定产业方向
3. 按四种方法拆产业链
4. 拆到细粒度节点
5. 映射公司业务分部
6. 归因收入、毛利和围墙证据
7. 判断研发阶段和商用阶段
8. 跟踪公告、研报、互动问答证据
9. 计算三高和预期差
10. 输出排序、分池和解释
```

### 1. 定政策主题

目标：

```text
把产业链节点放到未来产业主攻方向、新质生产力、科技自立自强之下。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `policy_themes` | 1 条，未来产业主攻方向 | 不够 |
| `packages/kronos-factors/configs/supply_chain_bom_v4.json` | 有 3 类主题和节点种子 | 可作为配置源 |
| `policy_sources` | 4 条 | 不够 |
| `policy_law` | 5 条 | 可补政策来源 |

缺口：

```text
数据库只落了一个政策主题
新质生产力、科技自立自强没有完整落库
政策主题和节点的多标签关系没有标准表
```

落地设计：

```text
补齐 policy_themes
新增 node_policy_tags
每个节点只设一个 primary_policy_theme
副标签存 secondary_policy_themes
评分时主标签归档，副标签只做政策共振，不重复加分
```

第一版输出：

```text
每个节点能显示主政策标签和副政策标签
每个标签能显示来源配置或政策来源
```

### 2. 定产业方向

目标：

```text
把政策主题拆到产业方向，例如 AI算力、半导体设备、量子通信、脑机接口。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `supply_chain_bom_nodes` | 49 个节点 | 可作为产业方向种子 |
| `chain_nodes` | 56 个节点 | 可复用 |
| `supply_chains.json` | 有传统 supply_chain 产业配置 | 可复用 |
| `docs/strategy/产业-重点方向维度.md` | 有 8 战新 + 6 未来产业 | 应转为配置 |

缺口：

```text
产业方向和政策主题之间还不是统一数据结构
节点粒度不一致，有的到产业，有的到组件
部分配置在文档里，数据库没有结构化
```

落地设计：

```text
新增 industry_directions
字段包括 direction_id、policy_theme_id、category、name、keywords、evidence_rules
从 docs/strategy/产业-重点方向维度.md 抽取首批 8+6 方向
```

第一版输出：

```text
政策主题下能展开产业方向
产业方向下能看到已有 BOM 节点和候选公司数量
```

### 3. 按四种方法拆产业链

目标：

```text
同一条产业链支持 BOM、上下游、价值链、竞争格局四种视角。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `/api/v1/screener/chain/deconstruct` | 已存在 | 可复用 |
| 前端 `chainApi.deconstructChain` | 已存在 | 可复用 |
| `chain_nodes.upstream_nodes` | 已有字段 | 可用于上下游 |
| `chain_nodes.value_chain` | 已有字段 | 可用于价值链 |
| `chain_nodes.competition` | 已有字段 | 可用于竞争格局 |

缺口：

```text
BOM 视图没有单独成为第一等视图
价值链和竞争格局字段内容不够细
四种视图没有统一的数据来源和评分口径
```

落地设计：

```text
新增 chain_deconstruct_views
method 取值：bom、upstream_downstream、value_chain、competition
每个 method 都返回同一批 node_id，但附带不同解释字段
```

第一版输出：

```text
同一产业方向能切换四种视图
节点能显示该视图下的解释、关键证据和候选公司
```

### 4. 拆到细粒度节点

目标：

```text
从政策主题一路拆到产品型号、材料、客户场景和证据事件。
```

V2 方案要求 8 层：

| 层级 | 名称 | 示例 |
|---:|---|---|
| L1 | 政策主题 | 新质生产力 |
| L2 | 产业方向 | AI算力 |
| L3 | 产业链 | 光模块产业链 |
| L4 | 环节 | 光芯片、光器件、光模块、测试设备 |
| L5 | BOM 节点 | EML、硅光芯片、TOSA、ROSA、DSP |
| L6 | 产品/技术路线 | 400G、800G、1.6T、CPO、LPO |
| L7 | 公司业务分部 | 高速数通光模块业务 |
| L8 | 证据事件 | 客户验证、订单、量产、毛利改善 |

现有数据支撑：

| 层级 | 当前来源 | 支撑度 |
|---:|---|---|
| L1 | `policy_themes`、配置文件 | 中 |
| L2 | `supply_chain_bom_v4.json`、策略文档 | 中 |
| L3 | `supply_chains.json`、`chain_nodes` | 中 |
| L4 | `supply_chain_bom_nodes`、`company_bom_mapping.node_id` | 中 |
| L5 | 当前较少，部分来自 `product_name` | 弱 |
| L6 | 研报标题和互动问答可抽取，例如 800G、1.6T | 弱到中 |
| L7 | `fina_mainbz` 不够，`stock_profiles.main_business` 可粗拆 | 弱 |
| L8 | `company_evidence`、互动问答、研报标题 | 中 |

缺口：

```text
没有统一的 L1-L8 层级表
L5 和 L6 细节点主要靠文本抽取，还没结构化
L7 业务分部依赖主营构成，当前数据不足
L8 证据事件还没从所有来源结构化生成
```

落地设计：

```text
新增 supply_chain_layer_nodes
新增 layer_level 字段，取 L1 到 L8
新增 parent_layer_node_id，保证层层下钻
新增 canonical_name 和 aliases，支持产品型号和技术路线归一
```

第一版输出：

```text
页面能从 L1 点到 L4
L5-L8 先展示已抽取内容和数据缺口
光模块、具身智能先做样板链
```

### 5. 映射公司业务分部

目标：

```text
把公司具体业务分部映射到产业链标签，而不是直接把公司整体贴标签。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `stock_profiles.main_business` | 6294 只公司 | 可粗拆 |
| `company_bom_mapping` | 15642 行，4632 只股票 | 可做候选映射 |
| `company_chain_mapping` | 15606 行，4631 只股票 | 可做候选映射 |
| `fina_mainbz` | 276 行，50 个代码，匹配差 | 不够 |

缺口：

```text
没有 company_business_segments
没有业务分部到标签的映射表
fina_mainbz 代码需要标准化
大量公司没有分业务收入
```

落地设计：

```text
新增 company_business_segments
新增 business_tag_mapping
先用 main_business 切分候选业务
有 fina_mainbz 的公司使用分部数据
没有分部数据的公司标记 segment_source=profile_inferred
```

第一版输出：

```text
每家公司至少能展示业务标签候选
有分部数据时展示收入
没有分部数据时标记为不可用，不能进核心池
```

### 6. 归因收入、毛利和围墙证据

目标：

```text
计算标签相关业务的收入、毛利和护城河证据。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `financial_indicator.gross_margin` | 公司级毛利率可用 | 公司级够用 |
| `financial_income.total_revenue` | 公司级收入可用 | 公司级够用 |
| `fina_mainbz.biz_income` | 有收入，但覆盖太少 | 不够 |
| `fina_mainbz.biz_ratio` | 全空 | 不可用 |
| `company_evidence` | 有少量护城河和商业化证据 | 不够 |
| 互动问答和研报标题 | 可抽取护城河线索 | 可作为初版 |

缺口：

```text
分业务收入占比不能全市场计算
分业务毛利基本不可用
护城河证据还没有结构化到业务标签
```

落地设计：

```text
收入归因分为 disclosed、estimated、unavailable
毛利归因分为 disclosed、estimated、proxy、unavailable
围墙证据必须来自 business_tag_evidence_events
只有公司级毛利率时，高盈利分设置上限
```

第一版输出：

```text
标签收入和毛利显示数据状态
无分部数据时不给精确占比
围墙证据能点开原文
```

### 7. 判断研发阶段和商用阶段

目标：

```text
研发阶段看技术推进，商用阶段看收入和订单兑现。
```

现有数据：

| 数据 | 当前情况 | 判断 |
|---|---|---|
| `interact_qa` | 118631 行 | 可用 |
| `ts_raw_irm_qa_sh` | 11986 行 | 可用 |
| `ts_raw_irm_qa_sz` | 13196 行 | 可用 |
| `research_reports_tushare.title` | 116266 行 | 可用 |
| `announcements.title` | 23034 行 | 可用 |
| `announcements.content` | 空 | 不可用 |

缺口：

```text
没有 business_stage_tracking
阶段判断还没有标准化事件触发
公告正文缺失导致正式公告证据不足
```

落地设计：

```text
新增 business_stage_tracking
新增 research_stage：R0 到 R6
新增 commercial_stage：C0 到 C7
阶段变化必须绑定 source_event_id
互动问答可触发 pending_review 阶段，公告正文可触发 approved 阶段
```

第一版输出：

```text
每张业务标签卡显示研发阶段和商用阶段
阶段旁边显示依据和证据状态
```

### 8. 跟踪公告、研报、互动问答证据

目标：

```text
把文本来源转成业务事件，持续跟踪业务变化。
```

现有数据：

| 来源 | 当前情况 | 第一版用途 |
|---|---|---|
| 互动问答 | 数据较足 | 阶段、客户验证、产品进展 |
| 研报标题 | 数据较足 | 业务预期、放量、毛利线索 |
| 公告标题 | 数据较足 | 风险、股权、活动、部分业务事件 |
| 公告正文 | 空 | 待修复 |
| 研报正文 | 不在结构化表 | 待补 |

缺口：

```text
没有 business_tag_evidence_events
没有事件类型标准
没有人工复核闭环
```

落地设计：

```text
新增 business_tag_evidence_events
event_type 包括 research、sample、validation、order、mass_production、income、margin、moat、risk
review_status 包括 pending_review、approved、rejected
```

第一版输出：

```text
公司业务标签下有证据时间线
每条证据能看到来源、日期、原文、影响维度和复核状态
```

### 9. 计算三高和预期差

目标：

```text
按标签相关业务计算高增长、高盈利、高围墙，并单独计算预期差。
```

现有数据：

| 能力 | 当前支撑 | 判断 |
|---|---|---|
| 高增长 | 研报标题、问答、财务公司级增长 | 初版可做 |
| 高盈利 | 公司级毛利、研报标题 | 弱 |
| 高围墙 | 问答、研报标题、company_evidence | 初版可做 |
| 预期差 | 行情、资金、研报覆盖、概念热度 | 初版可做 |

缺口：

```text
没有 business_tag_three_high_scores
没有 business_expectation_gap
没有历史快照
没有兑现链路
```

落地设计：

```text
新增三高评分表
新增预期差表
三高全部落到 mapping_id
预期差分开记录声明、实际进展和市场反应
```

第一版输出：

```text
高增长、高盈利、高围墙三项分数
预期差类型：正预期差、负预期差、兑现差、隐性预期差、风险预期差
```

### 10. 输出排序、分池和解释

目标：

```text
把好业务和有预期差的业务分开排序。
```

现有数据：

| 能力 | 当前情况 | 判断 |
|---|---|---|
| 候选池 | `company_bom_mapping` 和 `company_chain_mapping` 覆盖广 | 可用 |
| 分池 | 当前有观察、关注等信号 | 可复用 |
| 排序 | 当前是公司级或节点级 | 需改造 |

缺口：

```text
没有业务标签级排序
没有产业链价值排序和预期差排序分离
没有数据质量门槛
```

落地设计：

```text
rank_type=value 输出产业链价值排序
rank_type=expectation_gap 输出预期差排序
分池规则绑定业务标签，不绑定公司整体
```

第一版输出：

```text
核心池
进展池
预期差池
观察池
剔除池
```

## L1 到 L8 层级实施设计

这一节专门补齐上一版缺失的层级拆解。

### L1 政策主题

字段：

```text
policy_theme_id
name
category
policy_weight
keywords
source_ids
```

当前支撑：

```text
配置文件有 3 类主题
数据库 policy_themes 只落了 1 类
```

计划：

```text
补齐未来产业主攻方向、新质生产力、科技自立自强
把政策来源写入 policy_sources
```

### L2 产业方向

字段：

```text
direction_id
policy_theme_id
industry_category
direction_name
keywords
strategy_logic
```

当前支撑：

```text
docs/strategy/产业-重点方向维度.md 有 8 战新 + 6 未来产业
数据库还没有标准方向表
```

计划：

```text
新增 industry_directions
首批导入 AI算力、半导体设备、机器人、量子、脑机、氢能、核聚变、6G 等方向
```

### L3 产业链

字段：

```text
chain_id
direction_id
chain_name
chain_keywords
default_deconstruct_methods
```

当前支撑：

```text
supply_chains.json 有 AI算力、半导体、机器人等链
supply_chain_bom_v4.json 有未来产业节点
```

计划：

```text
新增或扩展 supply_chain_catalog
把链和方向统一关联
```

### L4 环节

字段：

```text
segment_node_id
chain_id
segment_name
position
keywords
```

示例：

```text
光芯片
光器件
光模块
测试设备
```

当前支撑：

```text
supply_chain_bom_nodes 和 chain_nodes 有部分环节
company_bom_mapping.node_id 已能挂公司
```

计划：

```text
清洗 node_id，把产业、环节、组件分开
每个 L4 节点必须挂 L3
```

### L5 BOM 节点

字段：

```text
bom_node_id
segment_node_id
bom_name
node_type
keywords
technical_barrier
```

示例：

```text
EML
硅光芯片
TOSA
ROSA
DSP
陶瓷基板
```

当前支撑：

```text
现有 BOM 节点偏粗
product_name 有少量产品名
研报标题和互动问答能抽部分节点
```

计划：

```text
新增 supply_chain_bom_detail_nodes
按光模块和具身智能先做样板节点库
```

### L6 产品和技术路线

字段：

```text
product_route_id
bom_node_id
route_name
generation
keywords
commercial_maturity
```

示例：

```text
400G
800G
1.6T
CPO
LPO
硅光
```

当前支撑：

```text
研报标题里已有 800G、1.6T、CPO 等线索
结构化表还没有产品路线层
```

计划：

```text
新增 supply_chain_product_routes
从研报标题、互动问答、公告中抽取 route_name
```

### L7 公司业务分部

字段：

```text
segment_id
code
report_period
segment_name
segment_type
income
income_ratio
gross_profit
gross_margin
data_status
```

当前支撑：

```text
fina_mainbz 覆盖弱
stock_profiles.main_business 可以做粗推断
```

计划：

```text
新增 company_business_segments
先用 main_business 拆候选业务
修复 fina_mainbz 代码匹配
补全主营构成同步
```

### L8 证据事件

字段：

```text
event_id
mapping_id
source_type
source_date
event_type
dimension
excerpt
confidence
review_status
```

当前支撑：

```text
company_evidence 有 211 条
互动问答和研报标题可抽取大量事件
```

计划：

```text
新增 business_tag_evidence_events
全部阶段变化、三高变化、预期差变化都必须挂证据事件
```

## 四种拆法实施设计

### BOM 拆解

目标输出：

```text
系统/整机
核心模块
关键零部件
核心材料
专用设备
关键工艺
测试验证
```

数据来源：

```text
supply_chain_bom_nodes
supply_chain_bom_edges
chain_nodes
business_tag_mapping
business_tag_evidence_events
```

缺口：

```text
L5、L6 节点不足
产品型号和技术路线还没有标准表
```

实施：

```text
先补光模块和具身智能两条样板链
再用 LLM 或规则扩展其他链
```

### 上下游拆解

目标输出：

```text
上游材料
上游设备和零部件
中游制造和集成
下游客户
最终应用场景
```

数据来源：

```text
chain_nodes.upstream_nodes
chain_nodes.downstream_nodes
company_bom_mapping
公告、互动问答里的客户和供应链证据
```

缺口：

```text
上下游关系较粗
客户和供应商证据没有结构化
```

实施：

```text
新增 chain_supply_relations
从证据事件中抽 customer_type、supplier_role、application_scene
```

### 价值链拆解

目标输出：

```text
收入空间
毛利率
价格传导能力
客户议价能力
价值量占比
```

数据来源：

```text
financial_indicator
financial_income
company_business_segments
研报标题和互动问答
```

缺口：

```text
分业务毛利不足
价值量占比需要人工或研报抽取
```

实施：

```text
新增 node_value_chain_metrics
字段包括 margin_level、pricing_power、value_added、data_status
缺分业务毛利时，显示公司级代理并降权
```

### 竞争格局拆解

目标输出：

```text
市场份额
竞争对手数量
客户认证门槛
国产替代空间
价格战压力
进入壁垒
```

数据来源：

```text
研报标题
互动问答
company_evidence
dc_member、ths_member、kpl_concept_cons
```

缺口：

```text
市场份额和竞争对手关系没有结构化
研报正文缺失导致竞争格局证据偏弱
```

实施：

```text
新增 node_competition_metrics
先用概念成员数量、研报覆盖、证据关键词做代理
后续接研报正文和人工复核
```

## 公司多业务和三高归因

### 多业务拆分规则

```text
先拆业务分部
再映射标签
最后归因三高
```

处理规则：

| 场景 | 处理 |
|---|---|
| 有披露分业务收入 | 直接归因 |
| 只有主营业务文本 | 标记为推断 |
| 一项业务命中多个标签 | 按 mapping_confidence 分摊 |
| 没有收入证据 | 只能进观察池 |
| 没有分业务毛利 | 高盈利分设上限 |

### 高增长

数据来源：

```text
分业务收入增长
订单、客户导入、产能扩张
研报标题里的放量、增长、超预期
业绩预告和财务增长
```

第一版规则：

```text
有业务级收入或订单证据，最高 100
只有研报标题，最高 75
只有公司级增长，最高 60
只有概念热度，最高 40
```

### 高盈利

数据来源：

```text
分业务毛利率
公司级毛利率
研报标题里的毛利改善、产品结构改善
```

第一版规则：

```text
有分业务毛利，最高 100
有公司级毛利和业务收入证据，最高 75
只有研报标题，最高 65
毛利不可用，最高 50
```

### 高围墙

数据来源：

```text
客户认证
头部客户供应链
专利
国产替代
卡脖子
少数供应商
独供
行业标准
```

第一版规则：

```text
公告或互动问答明确客户验证，最高 100
研报明确证据，最高 80
只有概念标签，最高 40
```

## 证据和预期差链路

### 证据事件链

一条证据必须能挂到：

```text
L8 证据事件
L7 公司业务分部
L6 产品或技术路线
L5 BOM 节点
L4 环节
L3 产业链
L2 产业方向
L1 政策主题
```

如果证据只能挂到公司，不能挂到业务标签，就只能作为公司背景信息。

### 预期差链

预期差必须分三条线：

```text
公司声明线
研报预期线
实际进展线
```

再加市场认知：

```text
研报覆盖数量
概念热度
股价反应
成交和资金反应
```

第一版可用数据：

```text
research_reports_tushare.title
announcements.title
interact_qa
daily_kline
daily_basic
moneyflow
ts_raw_ths_hot
```

缺口：

```text
公告正文和研报正文不足
预期声明里的时间点需要文本抽取
```

## 数据表设计

### 层级节点表

```text
supply_chain_layer_nodes
```

字段：

```text
layer_node_id
layer_level
parent_layer_node_id
canonical_name
aliases
node_type
policy_theme_id
direction_id
chain_id
source
confidence
status
```

用途：

```text
承载 L1 到 L8 的统一层级
解决目前节点粒度混乱的问题
```

### 四种拆法视图表

```text
chain_deconstruct_views
```

字段：

```text
view_id
method
layer_node_id
parent_view_node_id
display_name
explanation
metrics
evidence_ids
```

用途：

```text
同一个节点在 BOM、上下游、价值链、竞争格局下展示不同解释
```

### 业务分部表

```text
company_business_segments
```

字段沿用 V2：

```text
segment_id
code
report_period
segment_name
segment_type
income
income_ratio
gross_profit
gross_margin
data_status
source_table
source_ref
review_status
```

### 业务标签映射表

```text
business_tag_mapping
```

关键字段：

```text
mapping_id
code
segment_id
tag_id
layer_node_id
node_id
policy_theme_ids
income_attribution_ratio
profit_attribution_ratio
mapping_confidence
mapping_source
status
evidence_ids
```

### 证据事件表

```text
business_tag_evidence_events
```

关键字段：

```text
event_id
mapping_id
source_type
source_date
source_table
source_key
excerpt
event_type
dimension
stage_before
stage_after
confidence
review_status
```

### 阶段跟踪表

```text
business_stage_tracking
```

关键字段：

```text
tracking_id
mapping_id
research_stage
commercial_stage
stage_reason
source_event_id
stage_updated_at
```

### 三高评分表

```text
business_tag_three_high_scores
```

关键字段：

```text
score_id
mapping_id
trade_date
growth_score
profit_score
moat_score
stage_score
evidence_score
expectation_gap_score
total_score
data_quality_flags
```

### 预期差表

```text
business_expectation_gap
```

关键字段：

```text
gap_id
mapping_id
declared_expectation
declared_source_event_id
expected_timeline
actual_progress
actual_event_ids
market_attention_score
price_reaction_score
gap_type
gap_score
```

## API 设计

### 层级和拆解

```text
GET /api/v1/screener/supply-chain/layers
GET /api/v1/screener/supply-chain/layer/{layer_node_id}
GET /api/v1/screener/chain/deconstruct?theme_id=&method=bom
GET /api/v1/screener/chain/deconstruct?theme_id=&method=upstream_downstream
GET /api/v1/screener/chain/deconstruct?theme_id=&method=value_chain
GET /api/v1/screener/chain/deconstruct?theme_id=&method=competition
```

### 公司业务标签

```text
GET /api/v1/screener/supply-chain/company/{code}/business-tags
GET /api/v1/screener/supply-chain/business-tag/{mapping_id}
```

### 证据和阶段

```text
GET /api/v1/screener/supply-chain/business-tag/{mapping_id}/evidence
GET /api/v1/screener/supply-chain/business-tag/{mapping_id}/stage
POST /api/v1/screener/supply-chain/evidence/{event_id}/review
```

### 排序

```text
GET /api/v1/screener/supply-chain/rankings?rank_type=value
GET /api/v1/screener/supply-chain/rankings?rank_type=expectation_gap
```

### 数据可用度

```text
GET /api/v1/screener/supply-chain/data-readiness
```

返回：

```json
{
  "layer_coverage": {"L1": "ready", "L7": "weak", "L8": "partial"},
  "business_segments": {"status": "weak", "reason": "fina_mainbz coverage low"},
  "announcement_body": {"status": "missing"},
  "research_body": {"status": "title_only"},
  "evidence_events": {"status": "partial"}
}
```

## 前端设计

### 产业链解构页

必须按四种拆法展示：

```text
BOM 拆解
上下游拆解
价值链拆解
竞争格局拆解
```

左侧：

```text
L1 到 L8 层级树
```

中部：

```text
当前拆法图谱
```

右侧：

```text
节点解释
数据支撑度
核心公司
证据覆盖率
缺口提示
```

### 公司业务标签页

展示多张业务标签卡：

```text
业务分部
产业链标签
L1-L8 路径
收入归因
毛利归因
研发阶段
商用阶段
高增长
高盈利
高围墙
预期差
最新证据
数据质量
```

### 预期差页

展示：

```text
公司声明
研报预期
实际进展
市场认知
预期差类型
证据链
```

## 实施路线

### Phase 0：数据修复和层级底座

目标：

```text
先把 L1-L8 的底座建起来，避免后续又变成公司清单。
```

任务：

```text
补齐 policy_themes 三类主题
新增 industry_directions
新增 supply_chain_layer_nodes
导入 L1-L4 种子节点
光模块和具身智能补 L5-L6 样板节点
修复 fina_mainbz 代码匹配
修复公告正文或建立公告正文抓取任务
```

验收：

```text
页面或接口能展示 L1-L8 层级结构
至少两条样板链能下钻到 L6
data-readiness 能提示 L7、L8 的数据缺口
```

### Phase 1：四种拆法视图

目标：

```text
让同一条产业链能按 BOM、上下游、价值链、竞争格局查看。
```

任务：

```text
新增 chain_deconstruct_views
扩展 /chain/deconstruct 支持 method=bom
补 value_chain 和 competition 的节点指标
前端补 BOM 拆解标签
```

验收：

```text
四种拆法都能返回同一主题下的树
每个节点能展示该视角的解释和数据支撑
```

### Phase 2：公司业务标签

目标：

```text
把公司整体标签拆成业务标签。
```

任务：

```text
新增 company_business_segments
新增 business_tag_mapping
从 company_bom_mapping 和 company_chain_mapping 迁移初始映射
从 stock_profiles.main_business 拆候选业务
有 fina_mainbz 的公司补收入
```

验收：

```text
公司详情能显示多张业务标签卡
每张卡能显示 L1-L8 路径
没有业务级证据的标签不能进核心池
```

### Phase 3：证据事件和阶段跟踪

目标：

```text
让公告、研报、互动问答持续更新业务阶段。
```

任务：

```text
新增 business_tag_evidence_events
新增 business_stage_tracking
从 interact_qa、ts_raw_irm_qa、research_reports_tushare.title、announcements.title 抽事件
建立人工复核接口
```

验收：

```text
每次研发阶段或商用阶段变化都有证据事件
阶段变化能显示原文和来源
```

### Phase 4：三高评分

目标：

```text
高增长、高盈利、高围墙全部落到业务标签。
```

任务：

```text
新增 business_tag_three_high_scores
实现数据质量门槛
高盈利受分业务毛利可用度限制
高围墙必须有证据事件
```

验收：

```text
三高评分不得直接使用公司整体指标替代
缺分业务收入或毛利时必须降权或标记不可用
```

### Phase 5：预期差模型

目标：

```text
区分公司声明、研报预期、实际进展和市场认知。
```

任务：

```text
新增 business_expectation_gap
抽取声明事件和兑现事件
用行情、资金、研报覆盖、热度计算市场关注
输出预期差排序
```

验收：

```text
能输出正预期差、负预期差、兑现差、隐性预期差、风险预期差
预期差排序和产业链价值排序分开
```

### Phase 6：历史快照和样本外验证

目标：

```text
验证新评分是否有研究价值。
```

任务：

```text
保存每日业务标签评分
保存预期差评分
做 cutoff-aware 回测
对比旧 supply_chain、BOM V4、新业务标签模型
```

验收：

```text
历史评分不能读取未来公告、未来研报、未来财报
输出 10 日、20 日、60 日 rankIC 和命中率
```

## 数据支撑优先级

必须先补：

```text
L1-L8 层级表
fina_mainbz 代码标准化
主营构成覆盖率
公告正文
证据事件表
业务标签映射表
```

可以第二批补：

```text
研报正文
专利和招投标
客户供应商外部数据
分业务毛利率
竞争格局人工复核
```

## 验收标准

| 编号 | 验收项 |
|---|---|
| AC-1 | 实施计划覆盖 V2 方案 10 步流程 |
| AC-2 | 系统能展示 L1 到 L8 层级 |
| AC-3 | 四种拆法都能通过接口返回 |
| AC-4 | 公司业务标签能显示 L1-L8 路径 |
| AC-5 | 业务标签能显示研发阶段和商用阶段 |
| AC-6 | 三高评分落到业务标签，不套公司整体 |
| AC-7 | 标签收入和毛利必须显示数据状态 |
| AC-8 | 阶段变化必须绑定证据事件 |
| AC-9 | 预期差分开记录声明、进展和市场认知 |
| AC-10 | 产业链价值排序和预期差排序分开 |
| AC-11 | 缺公告正文、研报正文、分业务毛利时必须降权 |
| AC-12 | 样本外验证不能读取 cutoff 之后的数据 |

## 落地判断

按 V2 方案完整落地，当前数据还不够。按本计划分阶段落地，可以马上启动。

第一批不要直接做全市场精确排名。第一批要先把 L1-L8 层级、四种拆法、业务标签、证据事件和阶段跟踪建起来。等主营构成、公告正文、研报正文补齐后，再把标签收入、标签毛利、三高评分和预期差排序放进核心评分。
