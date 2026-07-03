# 产业链证据链补全详细方案

- **日期**：2026-07-03
- **状态**：Draft
- **关联 PRD**：`docs/prd/supply-chain-evidence-chain-tracking-prd-2026-07-03.md`
- **目标**：把产业链模块从标签映射升级为业务证据跟踪系统。

## 1. 设计原则

系统只承认有来源的证据。模型可以做抽取、归类、匹配和建议，但不能生成没有来源的业务结论。

最小跟踪单元是：

```text
公司 + 业务分部 + L5/BOM 标签 + L6 技术路线 + L8 证据事件
```

证据分三层：

| 层级 | 定义 | 能做什么 | 不能做什么 |
|---|---|---|---|
| strong | 公告、财报、招投标、专利、政府项目、问询函回复 | 支撑阶段升级、三高强证据、核心池准入 | 不能绕过业务标签匹配 |
| mid | 互动问答、调研纪要、官网、权威财经新闻、券商研报、行业数据 | 支撑待复核、预期差、景气度、辅助评分 | 不能单独自动升级到收入兑现阶段 |
| weak | 社区、招聘、公众号转载、展会零散信息、自媒体 | 触发预警和人工复核 | 不能直接改变阶段和三高结论 |

## 2. 数据源规划

### 2.1 第一批：强证据底座

| 来源 | source_type | source_level | 采集频率 | 用途 |
|---|---|---|---|---|
| 巨潮资讯公告全文 | announcement | strong | 每日 | 年报、半年报、临时公告、合同、募投、问询 |
| 交易所公告全文 | exchange_announcement | strong | 每日 | 上交所、深交所、北交所公告 |
| 财报正文 | financial_report | strong | 财报季重点，每日增量 | 收入占比、毛利、业务分部 |
| 招投标和政府采购 | tender | strong | 每日 | 中标、采购、订单、客户证据 |
| 专利和标准 | patent_standard | strong | 每周 | 技术壁垒、研发方向、卡脖子 |
| 政府项目公示 | government_project | strong | 每周 | 示范项目、补贴、产能、国产替代 |
| 人工导入公告/强证据文本 | announcement | strong | 按需 | 用于接入暂未自动采集但已人工核验的公告、调研或正式材料 |

### 2.2 第二批：半强证据和景气度

| 来源 | source_type | source_level | 采集频率 | 用途 |
|---|---|---|---|---|
| 财联社、证券时报 e 公司、中证报、上证报、第一财经 | financial_news | mid | 每日 | 产业事件、订单、扩产、客户合作 |
| Wind、Choice、iFinD 研报 | broker_report | mid | 每日或每周 | 产业链拆解、盈利预测、业务占比估算 |
| 慧博、发现报告、萝卜投研 | research_aggregator | mid | 每日或每周 | 补充行业研报和观点 |
| SMM、Mysteel、百川盈孚、卓创、隆众 | industry_price | mid | 每日或每周 | 价格、供需、景气度 |
| 行业协会数据 | industry_association | mid | 每周 | 出货量、标准、竞争格局 |

### 2.3 第三批：弱信号

| 来源 | source_type | source_level | 采集频率 | 用途 |
|---|---|---|---|---|
| 雪球、东方财富股吧、同花顺社区 | market_community | weak | 每日 | 市场认知、热度、预期过热 |
| 招聘网站 | recruiting | weak | 每周 | 研发团队扩张、产线建设线索 |
| 公司公众号、展会新闻 | social_official | weak | 每日或每周 | 产品发布、会议展示、客户合作线索 |
| 行业自媒体 | industry_media | weak | 每日或每周 | 线索发现 |

## 3. 数据模型

### 3.1 `evidence_source_catalog`

用途：管理数据源和证据权重。

核心字段：

```text
source_id
source_name
source_type
source_level：strong / mid / weak
source_reliability_score
confidence_cap
is_official
is_third_party_estimate
is_market_sentiment
requires_cross_validation
license_status
update_frequency
crawl_method
enabled
metadata
```

### 3.2 `raw_evidence_documents`

用途：保存原始文档，保证证据可追溯。

核心字段：

```text
doc_id
source_id
source_type
source_level
company_code
company_name
title
publish_time
crawl_time
url
content_text
content_hash
doc_status
license_status
metadata
```

去重规则：

```text
content_hash = sha256(source_id + url + title + normalized_content)
```

同一 hash 不重复入库。

### 3.3 `evidence_extracted_facts`

用途：把文本变成业务标签级事实。

核心字段：

```text
fact_id
doc_id
mapping_id
company_code
chain_id
l5_tag
l6_route
business_segment
fact_type
fact_nature
fact_value
original_quote
source_level
confidence
confidence_cap
research_stage_signal
commercial_stage_signal
growth_signal
profit_signal
moat_signal
risk_signal
validation_status
evidence_event_id
metadata
```

`fact_nature` 取值：

```text
confirmed_fact
company_claim
analyst_estimate
media_report
market_signal
rumor_signal
```

`validation_status` 取值：

```text
confirmed
pending
contradicted
expired
rejected
```

### 3.4 `business_tag_stage_transition_log`

用途：记录阶段变化，避免阶段被静默覆盖。

核心字段：

```text
transition_id
mapping_id
old_research_stage
new_research_stage
old_commercial_stage
new_commercial_stage
trigger_fact_id
trigger_event_id
change_reason
review_status
created_at
```

### 3.5 `business_tag_evidence_freshness`

用途：判断证据是否过期。

核心字段：

```text
mapping_id
last_strong_evidence_date
last_mid_evidence_date
last_weak_signal_date
last_any_evidence_date
days_since_update
freshness_status：fresh / stale / expired / unknown
next_review_date
stale_reason
updated_at
```

建议规则：

| 状态 | 规则 |
|---|---|
| fresh | 30 天内有 strong 或 mid 证据 |
| stale | 31 到 90 天无 strong 或 mid 证据 |
| expired | 超过 90 天无 strong 或 mid 证据 |
| unknown | 没有任何证据 |

Implementation note: 新鲜度刷新必须覆盖全部 `business_tag_mapping`。没有结构化事实的映射也要写入 `unknown`，否则前端和复核中心看不到“缺证据”的业务标签。

### 3.6 `business_tag_expectation_monitor`

用途：跟踪研报、新闻、互动问答提出的预期是否兑现。

核心字段：

```text
monitor_id
mapping_id
claim_text
claim_date
claim_source_type
expected_result
expected_date
actual_progress
gap_status：pending / fulfilled / partially_fulfilled / missed / contradicted
market_price_change
evidence_ids
source_doc_id
review_status
```

## 4. 采集流程

每日任务流程：

```text
1. 读取 business_tag_mapping，生成公司、L5、L6、产业链关键词
2. 按数据源目录筛选 enabled = true 的来源
3. 拉取原始文档或接收人工导入文档
4. 用 content_hash 去重
5. 写入 raw_evidence_documents
6. 对正文做公司、L5、L6、阶段、三高、风险抽取
7. 写入 evidence_extracted_facts
8. 对可用事实生成 business_tag_evidence_events
9. 更新 business_tag_l8_evidence_status
10. 更新 business_tag_stage_transition_log 和 business_tag_stage_tracking
11. 更新 business_tag_evidence_freshness
12. 更新 business_tag_expectation_monitor
13. 输出待复核清单
```

## 5. 抽取规则

### 5.1 L5/L6 匹配

优先级：

```text
公司代码精确匹配
公司简称匹配
业务分部匹配
L5 标签关键词匹配
L6 技术路线关键词匹配
产业链关键词匹配
```

匹配必须至少满足：

```text
公司命中 + L5 或 L6 命中
```

只命中公司、不命中业务标签的文档，进入公司级素材，不进入业务标签事实。

### 5.2 阶段抽取

研发阶段：

| 阶段 | 关键词 |
|---|---|
| R0 | 概念、关注、布局 |
| R1 | 研发、立项、技术储备、研发项目 |
| R2 | 样品、原型机、样机、实验室 |
| R3 | 测试、验证、性能验证、内部测试 |
| R4 | 送样、客户认证、导入客户 |
| R5 | 验证通过、进入供应链、客户定点 |
| R6 | 产品定型、具备量产、研发完成 |

商用阶段：

| 阶段 | 关键词 |
|---|---|
| C0 | 尚未商业化、未形成收入 |
| C1 | 试产、试订单、小批试制 |
| C2 | 小批交付、小批量出货 |
| C3 | 量产爬坡、产线建设、产能释放 |
| C4 | 批量订单、框架协议、批量供货 |
| C5 | 收入占比、分业务收入、收入贡献 |
| C6 | 毛利率改善、利润贡献、盈利改善 |
| C7 | 稳定收入、成熟业务、持续贡献 |

Implementation note: C5 需要“收入占比达到、收入占比为、收入占比可见、分业务收入、收入贡献”等可见收入信号。仅出现“收入占比提升”但没有具体业务收入或占比披露时，不能直接判 C5；如果同时出现批量供货、批量出货，先判 C4。

### 5.3 三高事实

高增长事实：

```text
收入增长
订单增长
产能扩张
客户增加
产品升级
收入占比提升
业绩预告明确受益
```

高盈利事实：

```text
分业务毛利率
高端产品占比
成本下降
单价提升
客户结构改善
利润贡献改善
```

高围墙事实：

```text
国产替代
客户认证
专利标准
卡脖子环节
工艺难度
良率
交付能力
客户绑定
```

## 6. 阶段升级规则

| 来源和事实 | 处理 |
|---|---|
| strong 来源明确披露量产、批量订单、收入占比 | 可自动生成阶段升级候选，核心池可进入待复核或自动通过 |
| mid 来源披露送样、订单、预计放量 | 写入待复核，不自动升级 |
| weak 来源披露招聘、社区热议、传闻 | 写入弱信号池，不升级 |
| 专利授权 | 增强围墙，不直接升级商用 |
| 行业价格上涨 | 增强景气度，不直接提高公司盈利 |
| 研报估算收入占比 | 标记 analyst_estimate，不替代财报披露 |

阶段只允许同级或向上变化。若出现否认、延期、收入不及预期，可以写入风险事实和预期差，但不能直接删除历史阶段，需要形成新的反向事件。

## 7. 预期差模型

预期来源：

```text
研报盈利预测
新闻订单和扩产描述
互动问答公司声明
社区热度和股价表现
```

兑现验证来源：

```text
公告
财报
调研纪要
互动问答
招投标结果
客户或项目公示
```

状态：

| 状态 | 含义 |
|---|---|
| pending | 还未到验证窗口 |
| fulfilled | 已兑现 |
| partially_fulfilled | 部分兑现 |
| missed | 未兑现 |
| contradicted | 被否定或反向 |

## 8. 待复核队列

进入待复核的情况：

```text
mid 来源提示阶段升级
strong 来源和现有阶段冲突
研报预期和公告事实不一致
同一事实被多个来源重复提及但未有强证据
证据超过 90 天未更新
弱信号热度显著上升
```

复核动作：

```text
确认
驳回
降权
改标签
改阶段
标记为仅观察
```

Implementation note: P1 已新增 `generate-search-terms` dry-run。检索词从 `business_tag_mapping` 生成，组合公司名、证券代码、标签名、L1-L8 路径名称、chain_id 和 node_id；`l1_l8_path` 为对象数组时只取 `name`，不把对象字符串写入查询词。

Implementation note: 新增证据通过 `ingest-text` 入库时，同步 upsert `business_tag_evidence_events`，并刷新 `business_tag_evidence_freshness`。这样新增证据同时进入新证据链表和旧证据时间线，避免前端不同入口看到的数据不一致。

## 9. 前端展示规划

后续前端需要 5 个模块：

| 模块 | 内容 |
|---|---|
| 证据链总览 | 按产业链、L5 标签、公司统计证据覆盖和过期情况 |
| 公司业务标签卡 | 研发阶段、商用阶段、三高、证据、预期差 |
| 阶段时间线 | 展示 R/C 阶段变化和触发证据 |
| 待复核中心 | 新证据、弱信号、阶段候选、过期证据 |
| 预期差看板 | 研报和新闻声明、后续兑现状态、股价反应 |

Implementation note: 前端公司业务标签卡必须以 `mapping_id` 为入口查询证据链。候选股接口需要透传 `business_tag_mapping.mapping_id`；如果缺少该字段，页面只能显示“缺少业务标签映射 ID”的空态，不能用公司整体数据或静态文案冒充标签级证据。证据链展示字段以接口真实响应为准：事实状态使用 `validation_status`，原文使用 `original_quote`，阶段信号使用 `research_stage_signal` 和 `commercial_stage_signal`，新鲜度为单个 `freshness` 对象。

Implementation note: 工作台候选池增加真实数据兜底。若模型候选池返回空，则从 `business_tag_mapping` 读取公司业务标签映射，并附带 `mapping_id`、节点、证据数量、新鲜度和映射状态，`data_status.candidate_pool` 标记为 `mapping_fallback`。该兜底只使用已落库真实映射，不生成静态假候选。

## 10. 风险控制

| 风险 | 控制 |
|---|---|
| 模型抽取误判 | 保留原文摘录、置信度和复核状态 |
| 新闻噪声过高 | 新闻为 mid，默认待复核 |
| 弱信号误导 | weak 不能改变阶段 |
| 数据版权 | 付费研报先保存元信息和摘要，全文按授权处理 |
| 重复采集 | URL、标题、正文 hash 去重 |
| 多标签重复加分 | 同一事实可关联多个标签，但评分要去重 |

## 11. 第一版交付边界

第一版只做底座和最小闭环：

```text
数据源目录
原始文档库
结构化事实表
阶段变化日志
证据新鲜度
预期差监控表
从现有证据事件回填原始文档和结构化事实
从人工导入文本生成事实和证据事件
```

外部付费源先预留，不伪造数据。

## 12. 自动化编排和验收规则

新增统一编排脚本：

```text
tools/run_18chains_incremental_refresh.py
```

职责：

| 阶段 | 处理内容 |
|---|---|
| 源数据增量 | 行情、资金流、公告、互动问答、研报、券商推荐、主营构成、财务表 |
| 证据目录 | 初始化/更新证据来源目录 |
| 18 链拆解 | 基于 `business_tag_mapping` 全量生成标签级证据事件、L8 状态、三高、预期差 |
| 结构化回填 | 将旧证据事件转为 `raw_evidence_documents` 和 `evidence_extracted_facts` |
| 阶段刷新 | 从结构化事实刷新研发阶段和商用阶段 |
| 验收输出 | 统计 18 链覆盖、事实数量、评分数量、新鲜度分布，并输出 JSON 报告 |

财报类数据采用披露滞后窗口，而不是按自然日强行追最新：

```text
expected_financial_period(today, lag_days=75)
```

示例：2026-07-03 的可验收财务期为 2026-03-31。如果 `financial_income` 或 `financial_indicator` 已达到该期间，则跳过全市场慢速重拉。

日志治理规则：

```text
直接调用的数据同步函数必须经过输出捕获包装，只保留 stdout/stderr 尾部摘要。
编排脚本默认关闭无效 SQLite fallback，真实写入以 PostgreSQL 为准。
外部源失败时记录错误并继续后续步骤，但验收报告必须暴露失败步骤。
```

最终验收最低条件：

| 检查项 | 最低要求 |
|---|---:|
| 产业链数量 | 18 |
| 标签映射 | 大于 0 |
| 原始证据文档 | 大于 0 |
| 结构化事实 | 大于 0 |
| L8 证据状态 | 大于 0 |
| 三高评分 | 大于 0 |

2026-07-03 真实库最终验收报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/eighteen_chains_incremental_refresh_20260703/18chains-incremental-20260703-130007_acceptance_report.json
```

## 13. 数据质量体检设计

后端落库完成后，需要再做一层质量体检，解决两个问题：

```text
不是只看有没有落库，而是看每条产业链的数据是否足够支撑排序和推荐。
不是只看公司整体，而是看标签级证据、L8 细分证据、研发/商用阶段、三高和新鲜度是否完整。
```

体检脚本：

```text
tools/audit_supply_chain_data_quality.py
```

核心聚合对象：

| 主表/事实表 | 用途 |
|---|---|
| business_tag_mapping | 产业链、公司、标签映射底座 |
| business_tag_evidence_events | 旧证据事件覆盖 |
| evidence_extracted_facts | 标签级结构化事实 |
| business_tag_l8_evidence_status | L8 级证据覆盖 |
| business_tag_evidence_freshness | 证据新鲜度 |
| business_tag_stage_tracking | 研发/商用阶段覆盖 |
| business_tag_three_high_scores | 三高评分覆盖 |
| business_tag_expectation_gap_scores | 预期差覆盖 |

质量分结构：

| 维度 | 权重 | 达标含义 |
|---|---:|---|
| 映射深度 | 20 | 产业链不只是少数样例公司 |
| 公司广度 | 10 | 候选池有足够横向比较 |
| 结构化证据 | 25 | 有标签级事实，不只靠公司整体数据 |
| L8 覆盖 | 20 | 细粒度证据足够支撑 L8 判断 |
| 阶段覆盖 | 10 | 能区分研发阶段和商用阶段 |
| 三高评分覆盖 | 5 | 增长、盈利、围墙已按标签计算 |
| 新鲜度 | 10 | 近期证据没有明显过期 |

风险等级：

| 等级 | 含义 |
|---|---|
| high | 数据底座或新鲜度不足，不能直接做强推荐 |
| medium | 可看，但排序前需要补映射或刷新证据 |
| low | 可进入日更跟踪和候选排序 |

补数动作由规则生成：

```text
mapping_count < 10 => 补公司/标签映射
facts_per_mapping < 3 => 补结构化证据
l8_per_mapping < 6 => 补 L8 级证据状态
stage_coverage < 80% => 补研发/商用阶段证据
stale/expired/unknown > 10% => 刷新过期/未知证据
```

最新体检报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703/chain_quality_audit_20260703-131200.md
```

## 14. 候选池补全和证据刷新设计

质量体检发现某条产业链映射太薄或证据过期时，不能用静态列表补齐，也不能让模型直接编公司。补数流程必须从已落库资料里找证据。

新增工具：

```text
tools/repair_priority_supply_chains.py
```

输入来源：

| 来源表 | 用途 |
|---|---|
| stock_profiles | 公司主营、业务范围、公司简介 |
| announcements | 公告标题和内容 |
| interact_qa | 互动问答 |
| research_reports_tushare | 研报标题、券商、评级 |

候选规则：

```text
1. 按产业链维护 L5 标签关键词。
2. 证券代码统一规范为 6 位代码，去掉 .SZ/.SH。
3. 无效代码不入库。
4. 单条宽泛主题研报不入库，例如只命中“人形机器人”但没有公司业务证据。
5. 新增映射状态为 candidate。
6. 新增映射不伪造 company_business_segments 外键；business_segment_id 置空。
7. 每条链先限制 Top N 候选，避免一次性灌入噪声。
```

落库对象：

| 表 | 写入内容 |
|---|---|
| business_tag_mapping | 新候选映射，保留 chain_id、node_id、L1-L8 路径、confidence |
| business_tag_evidence_events | 本地来源命中的证据事件，source_type 以 `repair_local_` 开头 |

后续复用既有管道：

```text
backfill_ai_compute_all_mapped.py：重算 L8、三高、阶段、预期差。
supply_chain_evidence_pipeline.py backfill-existing-events：转原始文档和结构化事实。
refresh-stage-transitions：刷新研发/商用阶段迁移。
refresh-expectation-monitor：刷新预期差监控。
audit_supply_chain_data_quality.py：复测质量。
```

外键安全规则：

```text
business_tag_evidence_events 一旦被 evidence_extracted_facts 引用，不允许批量删除。
批量回填脚本只删除未被事实引用的 batch_10y_% 事件。
已结构化事件通过 ON CONFLICT 更新，保持证据链可追溯。
```

2026-07-03 第一批修复范围：

| chain_id | 修复动作 |
|---|---|
| future_materials | 补候选映射，刷新近期证据 |
| industrial_software | 补候选映射，刷新近期证据 |
| embodied_intelligence | 补候选映射，刷新近期证据 |

修复后报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/priority_chain_repair_20260703/priority_chain_repair_20260703-133930.md
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703_after_repair/chain_quality_audit_20260703-134337.md
```

## 15. 候选公司总榜设计

候选公司总榜用于回答：

```text
18 条产业链里，哪些公司在标签级证据、三高、卡脖子、研发/商用阶段和预期差上更值得优先研究？
```

新增工具：

```text
tools/build_supply_chain_candidate_ranking.py
```

聚合层级：

```text
business_tag_mapping 层：每个公司-产业链-标签先独立评分。
company-chain 层：同一公司在同一产业链有多个标签时，取最高分标签作为代表，同时保留 tag_count 和 mapping_ids。
global 层：所有公司-产业链组合统一排序。
chain 层：每条产业链单独输出 Top 5，避免大链压制小链。
```

评分公式：

| 维度 | 权重 | 说明 |
|---|---:|---|
| 三高总分 | 35% | 标签级三高综合 |
| 围墙分 | 15% | 卡脖子、壁垒、国产替代 |
| 阶段分 | 12% | 研发/商用阶段 |
| 证据分 | 12% | 证据数量和质量 |
| L8 覆盖 | 10% | L8 维度命中率 |
| 新鲜度 | 8% | 证据是否近期有效 |
| 预期差 | 6% | 实际进展与市场预期差 |
| 20 日涨幅 | 2% | 行情辅助项 |

信号分层：

| 信号 | 条件 |
|---|---|
| 重点候选 | rank_score >= 80，且新鲜度 >= 70%，且 L8 覆盖 >= 50% |
| 观察 | rank_score >= 65 |
| 暂缓 | rank_score < 65 |

注意：

```text
总榜不是买入建议。
总榜只表示产业链证据和标签级评分优先级。
交易层仍需结合行情、风控、买卖点模型。
```

最新总榜报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.md
```

## 16. 候选总榜产品化接入设计

目的：

```text
把离线候选总榜变成可在产业链拆解页面直接查看、筛选和下钻证据的真实数据页面。
```

后端接口：

```text
GET /api/v1/screener/supply-chain/candidate-ranking
```

查询参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `top_n` | 100 | 返回全局排序数量，上限 200 |
| `chain_id` | 空 | 可选，按产业链过滤 |
| `signal` | 空 | 可选，按重点候选/观察/暂缓过滤 |

接口聚合规则：

| 层级 | 规则 |
|---|---|
| mapping | 每个 `business_tag_mapping.mapping_id` 读取三高、预期差、L8、新鲜度和阶段数据 |
| company-chain | 同一公司同一产业链取最高分标签为 `best_mapping_id`，保留 `tag_count` 和 `mapping_ids` |
| global | 按 `rank_score` 输出全局排序 |
| by_chain | 每条产业链输出 Top 列表，避免大链压制小链 |

前端页面：

```text
/supply-chain-bom/ranking
```

页面结构：

| 区块 | 内容 |
|---|---|
| KPI | 映射行、公司-产业链组合、产业链数量、重点候选数 |
| 筛选 | 产业链筛选、信号筛选 |
| 表格 | 公司、产业链标签、三高、研发/商用阶段、L8 证据、预期差、行情 |
| 下钻 | 点击“查看证据”，把 `best_mapping_id` 传入既有 `CompanyResearchDrawer` |

关键约束：

```text
页面不得写死候选公司。
页面不得用公司整体情况替代标签级三高、阶段和证据。
证据链入口必须来自 `best_mapping_id`。
行情字段只作为辅助展示，不改变产业链证据主逻辑。
```

2026-07-03 实现状态：

| 项目 | 状态 |
|---|---|
| 后端接口 | 已完成 |
| 前端 API 类型 | 已完成 |
| 候选总榜页签 | 已完成 |
| 查看证据下钻 | 已完成 |
| 路由 `/supply-chain-bom/ranking` | 已完成 |
| 后端测试 | 已通过 |
| 前端组件测试 | 已通过 |
| 前端路由测试 | 已通过 |
| 前端类型检查 | 已通过 |
