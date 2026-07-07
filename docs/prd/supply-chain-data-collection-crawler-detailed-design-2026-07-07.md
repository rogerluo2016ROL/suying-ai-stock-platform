# 产业链三层数据采集与爬虫中心详细设计

- **日期**：2026-07-07
- **状态**：Draft
- **关联 PRD**：`docs/prd/supply-chain-data-collection-crawler-2026-07-07.md`
- **关联既有方案**：
  - `docs/prd/supply-chain-evidence-chain-tracking-prd-2026-07-03.md`
  - `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md`

## 1. 设计边界

本模块只负责“数据采集、原文留存、结构化抽取、质量审计、证据同步”。它不直接做选股、不直接生成交易信号。

数据流是：

```text
数据源 -> 采集器 -> 原始文档 -> 文本解析 -> 结构化事实 -> L8证据 -> 阶段/三高/预期差更新
```

选股模型和 ChatBI 只消费后面的结构化结果。

## 2. 三层数据源

### 2.1 第一层：强证据

| 数据源 | 类型 | 更新频率 | 证据作用 | 第一阶段处理方式 |
|---|---|---:|---|---|
| 巨潮/交易所公告全文 | strong | 每日盘后 | 年报、半年报、订单、募投、问询 | 自动采集 + 原文留存 |
| 互动易/上证 e 互动 | mid/strong 辅助 | 每日 | 业务进展、客户、订单、量产口径 | 复用现有表 + 增量采集 |
| 公司官网/投资者关系 | mid | 每日/每周 | 产品发布、客户合作、产能建设 | 先做候选公司定向采集 |
| 招投标/政府采购 | strong | 每日 | 中标、采购、客户、订单 | 第一阶段先走巨潮订单/中标/合同公告 PDF 的标题预筛和正文抽取，公共招采网站作为后续增强 |
| 专利/知识产权 | strong | 每周 | 技术壁垒、研发方向、卡脖子 | 第一阶段先从已采公告 PDF、互动问答、官网/IR 原文抽取明确专利事件；国家知识产权公共查询或授权 API 后续接入 |
| 政府项目公示 | strong | 每周 | 示范项目、补贴、产能 | 先接工信部/发改委/地方公示 |

### 2.2 第二层：预期和景气

| 数据源 | 类型 | 更新频率 | 证据作用 | 第一阶段处理方式 |
|---|---|---:|---|---|
| 券商研报/一致预期 | mid | 每日/每周 | 市场预期、盈利预测、覆盖度 | 先复用本地已落库 `research_reports`、`forecast_data`，授权源 Wind/Choice/iFinD 仍单独标记 |
| 权威财经新闻 | mid | 每日 | 产业事件、市场预期变化 | 先复用本地已落库 `stock_news_tushare`、`ts_raw_major_news`；综合新闻按候选公司名标题匹配并限制短名称误匹配 |
| 产业价格/供需 | mid | 每日/每周 | 景气度、涨价、供需缺口 | 第一阶段先复用本地东方财富板块指数作为景气代理；SMM/Mysteel/百川等商品价格源后续授权接入 |
| 政策项目/产业名单 | strong/mid | 每周 | 政策催化、项目落地 | 先复用候选公司公告中的政府补助、专项资金、技术改造、产业化项目；国家政策法规表数据少，后续补公开源 |

### 2.3 第三层：弱信号

| 数据源 | 类型 | 更新频率 | 证据作用 | 限制 |
|---|---|---:|---|---|
| 招聘 | weak | 每周 | 研发投入、产线扩张线索 | 不直接升级阶段 |
| 公众号/自媒体 | weak | 每日/每周 | 早期线索 | 需交叉验证 |
| 社区/论坛 | weak | 每日 | 情绪和热度 | 只做预警 |
| 展会/会议资料 | weak/mid | 每周 | 产品展示线索 | 需官网或公告验证 |

## 3. 模块架构

| 模块 | 职责 |
|---|---|
| Source Registry | 管理数据源、证据等级、权重上限、授权状态、频率 |
| Scheduler | 定时任务、手动任务、失败重试、并发控制 |
| Crawler Adapter | 每个来源一个适配器，统一输出 RawDocument |
| Raw Store | 原始文档、URL、hash、正文、采集时间 |
| Parser | 正文清洗、PDF/HTML 解析、表格提取 |
| Extractor | 抽取公司、产品、客户、订单、专利、金额、日期、阶段信号；订单/中标金额必须靠近“中标金额、合同金额、采购金额、折合人民币”等上下文，不能抓第一串数字 |
| Mapper | 把事实映射到 `business_tag_mapping` 和 L1-L8 路径 |
| Evidence Writer | 写入 `business_tag_evidence_events` 和 L8 状态 |
| Scoring Trigger | 触发阶段、三高、预期差重算 |
| Quality Audit | 统计成功率、重复率、失败原因、待授权、待复核 |

## 4. 数据表设计

### 4.1 `evidence_source_catalog`

来源目录。已有证据链方案中已规划，本模块需要扩展采集字段。

关键字段：

```text
source_id
source_name
source_type
source_level: strong / mid / weak
confidence_cap
license_status: available / not_configured / license_required / blocked
update_frequency
crawl_method: api / html / rss / pdf / manual_import
base_url
robots_policy
rate_limit_per_minute
enabled
metadata
```

### 4.2 `evidence_collection_jobs`

采集任务表。

```text
job_id
source_id
job_type: scheduled / manual / backfill / dry_run
scope_type: all_market / candidate_pool / company / chain
scope_payload
status: pending / running / success / partial_success / failed / skipped
started_at
finished_at
fetched_count
inserted_count
duplicate_count
failed_count
error_message
metadata
```

### 4.3 `raw_evidence_documents`

原始文档表。

```text
doc_id
source_id
source_level
company_code
company_name
title
publish_time
crawl_time
url
content_text
content_hash
doc_type
doc_status
license_status
metadata
```

唯一键建议：

```text
unique(source_id, content_hash)
unique(source_id, url) where url is not null
```

### 4.4 `evidence_extracted_facts`

结构化事实表。

```text
fact_id
doc_id
mapping_id
company_code
chain_id
node_id
l5_tag
l6_route
fact_type
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

### 4.5 专项事件表

为方便后续分析，强证据建议补专项表：

| 表 | 用途 |
|---|---|
| `patent_events` | 专利申请、授权、IPC、摘要、权利人；当前先保存官方原文中的明确专利事件，缺失的专利号/IPC 不硬填 |
| `tender_award_events` | 招标、中标、采购、项目金额、客户；第一阶段事件来自公告 PDF 强证据，标题噪声过滤现金管理、合同资产减值、募投、质押等非商业订单事项 |
| `official_site_events` | 官网、公众号、IR、产品发布 |
| `industry_price_series` | 价格、库存、供需、产能、景气；当前先写入产业链指数景气代理，商品价格/库存字段等待授权源补齐 |

专项表不是替代 L8 证据，而是提供更适合检索和统计的结构化事实。

## 5. 采集流程

### 5.1 每日增量

```text
1. 读取 source_catalog 中 enabled=true 的来源
2. 读取 18 个产业链候选公司和业务标签关键词
3. 生成 source + company + keyword 的采集任务
4. 执行采集器，拉取 HTML/API/PDF/文本
5. 标准化正文并计算 hash
6. 幂等写入 raw_evidence_documents
7. 对新增文档执行解析和事实抽取
8. 事实映射到业务标签和 L8 维度
9. 写入业务标签证据事件
10. 触发 L8 状态、阶段、三高、预期差刷新
11. 输出质量审计报告
```

### 5.2 回溯采集

回溯只针对第一层和第二层高价值数据：

```text
公告全文：近5-10年
互动问答：近3-5年
专利：近10年
招投标：近5年
研报/盈利预测：近5年
产业价格：按可获取周期
```

### 5.3 手动导入

手动导入用于授权受限数据和人工核验材料：

```text
source_id = manual_verified_document
source_level 由上传人选择，但不能超过来源目录上限
必须填写 title、publish_time、source_url 或来源说明、content_text
```

## 6. 解析和证据映射规则

### 6.1 L8 事实类型

| L8 维度 | 关键词示例 | 阶段影响 |
|---|---|---|
| 研发进展 | 研发、开发、技术突破、验证平台 | 可提升 R 阶段 |
| 样机/小批量 | 样品、送样、小批量、试制 | 可提升 R/C 早期 |
| 客户验证 | 认证、导入、测试、客户验证 | 可提升商用前阶段 |
| 订单/中标 | 订单、中标、合同、定点、采购 | 强证据可提升 C 阶段 |
| 量产/交付 | 量产、出货、批量供货、投产 | 强证据可提升 C 阶段 |
| 收入/毛利 | 收入、营收、毛利率、贡献 | 支撑增长和盈利 |
| 专利/标准 | 专利、标准、知识产权、认证 | 支撑围墙 |

### 6.2 证据等级约束

```text
strong: 可触发阶段升级候选，必要时自动通过或进入复核
mid: 只能辅助阶段判断，默认进入待复核
weak: 只进入线索池，不直接改变阶段、三高或预期差主分
```

### 6.4 研报和盈利预测处理

```text
本地研报/盈利预测来源：broker_expectation_local
来源范围：已落库 research_reports、forecast_data
事实性质：analyst_estimate
作用：进入 business_tag_expectation_monitor，衡量市场预期和覆盖度
限制：不能替代公告、订单、专利等强证据；不能单独提升研发/商用阶段
去重：正文 hash 必须包含股票代码和公司名称，避免“预增/略增 + 日期”跨公司误合并
```

### 6.5 权威财经新闻处理

```text
来源：financial_news_authoritative
来源范围：已落库 stock_news_tushare、ts_raw_major_news
匹配方式：股票新闻按 code 匹配；综合财经新闻按候选公司名标题匹配
质量边界：综合新闻公司名长度小于 4 的暂不做标题模糊匹配，避免“数字人/数字人才”等误伤
事实性质：media_report
作用：作为市场事件、热度和预期线索；包含“预计/有望/放量”等词时进入 expectation_monitor
限制：新闻不能单独提升研发阶段、商用阶段或三高主分
```

### 6.6 产业指数景气代理处理

```text
来源：industry_index_proxy_local
来源范围：已落库 ts_raw_dc_index 东方财富板块指数
落库表：industry_price_series
指标：dc_index_pct_change、dc_index_up_num、dc_index_down_num、dc_index_turnover_rate、dc_index_total_mv
匹配方式：按产业链 chain_id 维护关键词表，匹配板块指数名称
质量边界：这是景气代理，不是商品现货价格、库存或真实供需；不能替代 SMM/Mysteel/百川等产业价格数据
缺口处理：本地指数库无匹配时不硬造，例如脑机接口当前保留 skipped
```

### 6.7 政府项目和政策公示处理

```text
来源：government_project_notice
来源范围：候选公司公告标题、policy_law 政策法规表
当前有效数据：候选公司公告中的政府补助、财政补贴、专项资金、技术改造、产业化项目
过滤规则：剔除募投、募集资金、问询函、核查意见、股权激励名单、会计师事务所项目变更、中标等噪音
作用：作为政策支持、项目落地和外部资金支持证据，写入 business_tag_evidence_events
限制：政策/项目线索不能替代收入、毛利或订单兑现证据
```

### 6.8 预期差刷新

采集新增事实后触发：

```text
实际进展分 = 阶段分 * 0.50 + 证据强度分 * 0.32 + 景气分 * 0.18
市场预期分 = 研报/盈利预测覆盖 + 新闻预期热度 + 20 日股价反应
景气分 = 产业指数最新涨跌幅和近 5 日均值的代理分
证据增量分 = 已审核通过 L8 证据数量、置信度、增长/围墙维度
风险扣分 = 风险证据 + 20 日负向价格反应
预期差分 = 实际进展分 - 市场预期分 + 证据增量分 * 0.22 + 景气偏离 * 0.20 - 风险扣分 * 0.40
```

当前实现命令：

```bash
python3 tools/supply_chain_data_collection_center.py refresh-expectation-scores --pg-url "$DATABASE_URL" --limit 3000
```

落库位置：

```text
business_tag_three_high_scores.score_detail.prosperity_score
business_tag_expectation_gap_scores.market_expectation_score
business_tag_expectation_gap_scores.score_detail.prosperity_score
business_tag_expectation_gap_scores.score_detail.price_change_20d
```

边界：景气分目前使用本地东方财富板块指数代理，不等于商品价格、库存或真实供需；市场预期分越高，表示市场可能已经反应更多，不代表业务事实更强。

### 6.9 弱信号导入

弱信号只用于预警和待复核，不直接改变研发阶段、商用阶段、三高主分或强证据结论。

当前实现命令：

```bash
python3 tools/supply_chain_data_collection_center.py import-weak-signals --pg-url "$DATABASE_URL" --file weak_signals.jsonl --source market_community_signal
```

JSONL 每行格式：

```json
{"title":"来源标题","content_text":"原文片段或摘要","company_code":"002708.SZ","company_name":"光洋股份","url":"https://example.com/source","publish_time":"2026-07-07"}
```

安全规则：

```text
1. source 必须是 weak 来源，例如 recruiting_signal、official_social_signal、market_community_signal。
2. 每行必须有 title、content_text、company_code。
3. 导入后写入 raw_evidence_documents 和 evidence_extracted_facts。
4. 同步到 business_tag_evidence_events 时 review_status 固定为 pending_review。
5. 弱信号的 research_stage_signal 和 commercial_stage_signal 固定为空，不能触发阶段升级。
```

## 7. 调度策略

| 任务 | 频率 | 时间建议 |
|---|---:|---|
| 行情/资金同步 | 交易日 | 盘后 |
| 公告全文增量 | 每日 | 20:00、23:30 |
| 互动问答增量 | 每日 | 21:00 |
| 新闻增量 | 每日多次 | 09:00、12:00、16:00、21:00 |
| 招投标 | 每日 | 22:00 |
| 专利 | 每周 | 周末 |
| 官网/IR | 每周 + 重点公司每日 | 20:30 |
| 研报/盈利预测 | 每日/每周 | 盘后 |
| 质量审计 | 每日 | 所有任务后 |

## 8. 验收策略

第一阶段验收不看页面，先看数据闭环：

```text
1. 能生成三层来源目录
2. 能对一个产业链候选池 dry-run 生成关键词
3. 能真实采集至少两个来源的数据
4. 能原文落库并去重
5. 能抽取 L8 证据
6. 能同步更新业务标签证据
7. 能生成采集质量报告
8. 能跑一次 18 个产业链候选池增量试跑
```

## 9. 风险和控制

| 风险 | 控制 |
|---|---|
| 数据源反爬或授权限制 | 合法公开采集 + 频率控制 + 未授权标记 |
| PDF/网页解析失败 | 原文先落库，解析失败进入队列 |
| 弱信号误导 | 弱信号不直接改变阶段和三高 |
| 重复采集 | URL + content_hash 双重去重 |
| 模型幻觉 | 只允许引用原文摘录，不允许生成无来源事实 |
| 数据延迟 | 每个源记录更新时间和新鲜度 |

## 10. 分阶段交付

| 阶段 | 范围 | 交付物 |
|---|---|---|
| P0 | 来源目录、任务表、原文表、事实表、质量审计 | 可跑 CLI 和 SQL 验收 |
| P1 | 公告、互动、官网/IR、专利、招投标 | 第一层强证据闭环 |
| P2 | 研报、盈利预测、新闻、产业价格 | 预期和景气数据 |
| P3 | 招聘、公众号、社区、展会 | 弱信号预警 |
| UAT | 18 个产业链全量增量试跑 | 数据覆盖、证据新增、预期差刷新报告 |
