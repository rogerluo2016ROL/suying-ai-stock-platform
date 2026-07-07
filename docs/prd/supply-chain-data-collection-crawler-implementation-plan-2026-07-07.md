# 产业链三层数据采集与爬虫中心实施计划

> 本计划对应 `docs/prd/supply-chain-data-collection-crawler-2026-07-07.md` 和 `docs/prd/supply-chain-data-collection-crawler-detailed-design-2026-07-07.md`。

**Goal:** 建立专门的数据采集和爬虫模块，对三层数据进行高质量定时采集，持续更新产业链证据、阶段、三高和预期差。

**Architecture:** 先做数据库和 CLI 底座，再接第一层强证据，完成 18 条产业链试跑后，再接第二层预期/景气数据和第三层弱信号。

**Tech Stack:** PostgreSQL, Alembic, Python, FastAPI scheduled jobs, existing `business_tag_*` tables.

## Global Constraints

- 不伪造数据，不用模型编造证据。
- 未授权付费源只做预留和状态标记。
- 强证据、半强证据、弱信号必须分层。
- 所有采集写入必须幂等。
- 弱信号不能直接改变研发阶段、商用阶段和三高主分。
- 每条阶段变化必须能追溯原文。

---

## Task 1: PRD、详细设计和计划冻结

**Files:**

- `docs/prd/supply-chain-data-collection-crawler-2026-07-07.md`
- `docs/prd/supply-chain-data-collection-crawler-detailed-design-2026-07-07.md`
- `docs/prd/supply-chain-data-collection-crawler-implementation-plan-2026-07-07.md`

- [x] Step 1: 新增 PRD，明确三层数据源、目标、非目标、AC。
- [x] Step 2: 新增详细设计，明确模块边界、数据流、表结构、调度和验收。
- [x] Step 3: 新增实施计划，按 P0/P1/P2/P3/UAT 推进。
- [x] Step 4: 用户确认文档范围后进入工程实现。

---

## Task 2: 数据库迁移底座

**Files:**

- Create: `backend/alembic/versions/024_supply_chain_data_collection_center.py`
- Modify: migration contract tests if existing test layout supports it.

**Tables:**

- `evidence_collection_jobs`
- `raw_evidence_documents`
- `evidence_extracted_facts`
- `patent_events`
- `tender_award_events`
- `official_site_events`
- `industry_price_series`
- Extend or seed `evidence_source_catalog` if already exists.

- [x] Step 1: 写迁移合同测试，要求上述表和关键字段存在。
- [x] Step 2: 跑测试确认失败。
- [x] Step 3: 新增 Alembic 迁移。
- [x] Step 4: 跑迁移合同测试通过。
- [x] Step 5: 对本地 PostgreSQL 执行迁移并验证表存在。

**Acceptance:**

```sql
select table_name
from information_schema.tables
where table_name in (
  'evidence_collection_jobs',
  'raw_evidence_documents',
  'evidence_extracted_facts',
  'patent_events',
  'tender_award_events',
  'official_site_events',
  'industry_price_series'
);
```

---

## Task 3: 来源目录和采集任务 CLI

**Files:**

- Create: `tools/supply_chain_data_collection_center.py`
- Create: `tools/tests/test_supply_chain_data_collection_center.py`

**CLI:**

```bash
python3 tools/supply_chain_data_collection_center.py seed-sources --pg-url "$DATABASE_URL"
python3 tools/supply_chain_data_collection_center.py dry-run-keywords --pool all-18-chains --pg-url "$DATABASE_URL"
python3 tools/supply_chain_data_collection_center.py run-source --source cninfo_announcement --scope candidate_pool --pg-url "$DATABASE_URL"
python3 tools/supply_chain_data_collection_center.py quality-report --pg-url "$DATABASE_URL"
```

- [x] Step 1: 实现三层默认来源目录。
- [x] Step 2: 写入 `evidence_source_catalog`，支持 upsert。
- [x] Step 3: 从 `business_tag_mapping` 和候选池生成公司 + L5/L6 关键词。
- [x] Step 4: dry-run 输出采集计划，不实际访问外部网站。
- [x] Step 5: 质量报告输出任务成功率、失败率、重复率、待授权源。

**Acceptance:**

- strong/mid/weak 三层来源都有记录。
- dry-run 能列出至少 18 条产业链候选公司的关键词。
- 未授权源显示 `license_required` 或 `not_configured`。

---

## Task 4: 原始文档落库、去重和解析框架

**Files:**

- Modify: `tools/supply_chain_data_collection_center.py`
- Add tests for idempotency and parser.

- [x] Step 1: 定义 `RawDocument`、`ExtractedFact` 数据结构。
- [x] Step 2: 实现 URL + content_hash 去重。
- [x] Step 3: 实现 HTML/text 标准化。
- [x] Step 4: 实现基础规则抽取：研发、样品、客户验证、订单、量产、收入、专利。
- [x] Step 5: 将事实映射到 `business_tag_mapping`。

**Acceptance:**

- 同一文档重复导入不会重复生成事实。
- 样例文本能抽取 L8 维度和原文摘录。
- weak 来源的事实不会产生阶段升级。

---

## Task 5: 第一层强证据接入

**Scope:**

- 公告全文
- 互动问答增量
- 官网/IR 定向采集
- 招投标/中标
- 专利

- [x] Step 1: 复用现有 `announcements` 和 `interact_qa`，先补原文文档和事实回填。
- [x] Step 2: 新增公告全文增量采集器。
- [x] Step 3: 新增官网/IR 候选公司定向采集器。
- [x] Step 4: 新增招投标关键词采集器。
- [x] Step 5: 新增专利关键词采集器。
- [x] Step 6: 将强证据同步到 `business_tag_evidence_events`。

**Acceptance:**

- 至少两个真实来源完成采集落库。
- 至少一个强证据能生成 L8 事件。
- 阶段升级候选写入阶段日志或待复核队列。

Current verification:

```text
2026-07-07: `exchange_interact_qa` 回填 20 篇，新增 raw docs 20，facts 8。
2026-07-07: `cninfo_announcement` 回填 20 篇，新增 raw docs 18，facts 7，重复 2。
2026-07-07: 数据库版本已升级到 024。
2026-07-07: 从采集中心 facts 同步 17 条到 `business_tag_evidence_events`。
2026-07-07: 刷新阶段变更候选，生成 transitions 44 条；刷新预期监控 100 条。
2026-07-07: 新增巨潮公告 PDF 正文采集器 `fetch-cninfo-pdf`；小样本真实抓取 14 份公告 PDF 正文，平均正文约 2528 字。
2026-07-07: 公告 PDF 事实已同步到 L8 证据事件，新增公告侧 patent/research/commercial/business_presence 强证据。
2026-07-07: 新增官网/IR 定向采集器 `fetch-official-ir`；小样本真实抓取 6 页官网/IR 正文，平均正文约 4069 字，作为 mid 级证据进入 `pending_review`。
2026-07-07: 新增 `fetch-cninfo-pdf --title-mode tender`，在数据库层预筛中标/合同/框架协议/采购/订单公告标题，真实抓取 10 份订单/中标类公告 PDF。
2026-07-07: 新增招投标/合同事件抽取 `extract-tender-events`，当前落库 `tender_award_events` 8 条，其中 award 3、contract 3、framework_agreement 1、procurement 1；C4 商用强信号 7 条，C3 采购信号 1 条。
2026-07-07: 修正金额抽取规则：金额必须靠近中标金额/合同金额/采购金额/折合人民币等上下文，已剔除现金管理、合同资产减值、募投、质押等非商业订单误判。
2026-07-07: 新增专利/知识产权事件抽取 `extract-patent-events`，从已采公告 PDF、官网/IR、互动问答原文中抽取明确专利事件；当前落库 `patent_events` 3 条。
2026-07-07: 专利专项表当前不是 CNIPA 全量专利库，只保存可追溯到已采官方原文的知识产权事件，专利号/IPC 等缺失字段不硬填。
```

---

## Task 6: 第一轮 18 条产业链试跑

- [x] Step 1: 读取所有已拆解产业链和候选公司。
- [x] Step 2: 对第一层强证据执行增量采集。
- [x] Step 3: 生成证据新增清单。
- [x] Step 4: 刷新 L8 状态、阶段、三高、预期差。
- [x] Step 5: 输出试跑报告。

**Report fields:**

```text
产业链
候选公司数
新增原始文档数
新增 L8 证据数
阶段升级候选数
预期差分变化 Top20
证据缺口 Top20
失败任务和原因
```

Current verification:

```text
2026-07-07: 新增 `tools/run_supply_chain_collection_uat.py`。
2026-07-07: UAT run `collection-uat-20260707-164514` 覆盖 18 条链、1195 家候选公司、2255 个业务映射。
2026-07-07: 本轮新增 raw docs 152、facts 21、同步 L8 events 21、阶段候选 1。
2026-07-07: UAT run `collection-uat-20260707-164546` 重跑增量为 0，验证去重和幂等生效。
2026-07-07: 报告输出：
  - `outputs/supply_chain_collection_uat/collection-uat-20260707-164514.md`
  - `outputs/supply_chain_collection_uat/collection-uat-20260707-164546.md`
```

---

## Task 7: 第二层预期和景气数据接入

**Scope:**

- 研报和盈利预测
- 权威财经新闻
- 产业价格和供需
- 政府项目和政策名单

- [x] Step 1: 补齐 `profit_forecasts` 或同等一致预期数据源。
- [x] Step 2: 接入权威财经新闻公开源。
- [x] Step 3: 设计并落库产业价格/供需序列。
- [x] Step 4: 接入政府项目公示数据。
- [x] Step 5: 更新市场预期分和景气分。

**Acceptance:**

- 预期差评分能区分“证据新增但市场未反应”和“证据弱但市场已大涨”。
- 新闻和研报只能作为预期和线索，不替代强证据。

Current verification:

```text
2026-07-07: 新增来源 `broker_expectation_local`，代表本地已落库研报/盈利预测表，不等同于 Wind/Choice/iFinD 授权源。
2026-07-07: 复用 `research_reports` 和 `forecast_data`，回填候选公司相关研报/盈利预测 200 条 raw docs、200 条 analyst_estimate facts。
2026-07-07: 其中 `research_report` 141 条、`profit_forecast` 59 条，已刷新 `business_tag_expectation_monitor` 200 条。
2026-07-07: 修正预期类文档去重口径，正文 hash 包含股票代码和公司名称，避免不同公司的“预增/略增 + 日期”误合并。
2026-07-07: 新增 `financial_news_authoritative` 回填逻辑，复用 `stock_news_tushare` 和 `ts_raw_major_news`；真实回填 119 条 raw docs、119 条 media_report facts。
2026-07-07: 权威财经新闻中 11 条因包含“预计/有望/放量”等预期词进入 `business_tag_expectation_monitor`，全部保持 pending 复核状态。
2026-07-07: 综合财经新闻公司名标题匹配已收紧：短于 4 个字的公司名不做模糊匹配，避免“数字人/数字人才”等误匹配。
2026-07-07: 新增 `industry_index_proxy_local`，复用 `ts_raw_dc_index` 东方财富板块指数作为产业链景气代理；真实落库 `industry_price_series` 425 条指标。
2026-07-07: 指数景气代理覆盖 17/18 条产业链，脑机接口因本地指数库无匹配结果保留缺口；该数据不是商品价格/库存/真实供需。
2026-07-07: 修正 AI 算力指数关键词，移除过宽的单独 “AI” 匹配，避免误纳入 AI手机、AI制药等非算力指数。
2026-07-07: 新增 `government_project_notice` 本地回填逻辑，复用候选公司公告中的政府补助、专项资金、技术改造、产业化项目等线索。
2026-07-07: 政府项目/政策公示真实回填 115 条 raw docs、115 条 facts，并同步 115 条 `business_tag_evidence_events`；其中 business_presence 114 条、research_progress 1 条。
2026-07-07: 政府项目过滤已剔除募投、募集资金、问询函、核查意见、股权激励名单、会计师事务所项目变更、中标等噪音；同公司同日期同标题按公告去重。
2026-07-07: 新增 `refresh-expectation-scores` 命令，汇总 L8 强证据、研报/新闻预期监控、产业指数景气代理和 20 日股价反应，刷新市场预期分、景气分、三高评分和预期差评分。
2026-07-07: 按最新行情日 2026-07-06 对 2255 个业务标签真实落库：`business_tag_three_high_scores` 2255 条、`business_tag_expectation_gap_scores` 2255 条。
2026-07-07: 本轮预期差结果中 positive 60 条、negative 503 条；平均预期差分 0.74，平均三高分 14.98，平均景气分 63.01。景气分当前为东方财富板块指数代理，不等同商品价格/库存。
```

---

## Task 8: 第三层弱信号接入

**Scope:**

- 招聘
- 公众号/自媒体
- 社区/论坛
- 展会资料

- [x] Step 1: 建立弱信号来源目录。
- [x] Step 2: 实现人工导入或低频公开采集。
- [x] Step 3: 写入弱信号池和待复核队列。
- [x] Step 4: 验证弱信号不改变阶段和三高主分。

Current verification:

```text
2026-07-07: 来源目录已包含 `recruiting_signal`、`official_social_signal`、`market_community_signal` 等 weak 来源，置信度上限 0.45。
2026-07-07: 新增 `import-weak-signals` JSONL 人工导入入口，强制校验 source 必须为 weak 来源，每行必须包含 title、content_text、company_code。
2026-07-07: 弱信号导入后写入 raw docs、facts，并同步为 `business_tag_evidence_events.pending_review`；不会写入 approved 强证据。
2026-07-07: 单元测试验证 weak 文档不会生成 research_stage_signal 或 commercial_stage_signal，不会触发阶段升级。
2026-07-07: 当前未导入任何虚构弱信号；真实落库需要提供可追溯的招聘、公众号/自媒体、社区/论坛或展会资料 JSONL 文件。
```

**Acceptance:**

- 弱信号能提示“可能有新业务线索”。
- 弱信号不能单独进入选股推荐理由。

---

## Task 9: 定时调度和质量审计

**Files:**

- FastAPI scheduler or existing project scheduler integration.
- Quality report CLI/API.

- [x] Step 1: 配置每日/每周任务。
- [x] Step 2: 记录每次任务状态和耗时。
- [x] Step 3: 失败任务支持重试和跳过。
- [x] Step 4: 每日生成质量审计报告。
- [x] Step 5: 对异常数据源报警或标记。

Current verification:

```text
2026-07-07: 新增 `schedule-plan`，固化 daily_core、weekly_official_and_ip、manual_weak_signal 三类批次。
2026-07-07: 新增 `run-scheduled-batch`，逐项执行采集/刷新任务，单项失败会记录 failed 并继续后续任务，批次状态返回 success 或 partial_success。
2026-07-07: daily_core 小批量真实试跑通过，7 个任务全部 success；研报、新闻、政府项目重复数据正确识别为 duplicate。
2026-07-07: 修正 `industry_price_series` 幂等更新口径，产业指数代理按 `series_id` 主键 upsert，避免 node_id 为 NULL 时组合唯一键无法拦截重复主键。
2026-07-07: 质量报告继续输出 source_level、license_status、job_status，可用于标记待授权和异常来源。
```

**Acceptance:**

- 能看到每个数据源最后成功时间。
- 能看到失败原因和重复率。
- 能禁用某个数据源而不影响其他采集任务。

---

## Task 10: UAT 和全量增量采集

- [x] Step 1: 跑第一层强证据 UAT。
- [x] Step 2: 跑第二层预期和景气 UAT。
- [x] Step 3: 跑第三层弱信号 UAT。
- [x] Step 4: 对 18 条产业链执行一次全量增量采集。
- [x] Step 5: 输出 UAT 报告和数据覆盖报告。

**UAT acceptance:**

- 数据源目录完整。
- 采集任务可重复运行且幂等。
- 至少两个真实外部来源成功采集。
- L8 证据能更新。
- 预期差评分能刷新。
- 没有弱信号直接升级阶段。

Current verification:

```text
2026-07-07: 扩展 `tools/run_supply_chain_collection_uat.py`，覆盖第一层强证据、第二层研报/新闻/政府项目/产业指数代理、第三层弱信号安全检查、评分刷新和质量报告。
2026-07-07: UAT run `collection-uat-20260707-184043` 首次三层回归生成报告，覆盖 18 条产业链、1195 家候选公司、2255 个业务映射。
2026-07-07: UAT run `collection-uat-20260707-184112` 重跑增量为 0，验证 raw docs、facts、产业指数、三高评分、预期差评分均可幂等重跑。
2026-07-07: 最新评分日 2026-07-06：预期差评分 2255 条、三高评分 2255 条；positive 62 条、negative 503 条，平均预期差分 0.81，平均三高分 15.00，平均景气分 63.01。
2026-07-07: UAT 验收项通过：18 条链目录 ready、L8 证据已同步、预期差已刷新、弱信号 approved 数为 0。
2026-07-07: 最新 UAT 报告：
  - `outputs/supply_chain_collection_uat/collection-uat-20260707-184112.md`
  - `outputs/supply_chain_collection_uat/collection-uat-20260707-184112.json`
2026-07-07: 增强 `quality-report`，新增 `source_health` 和 `recent_issue_jobs`，可直接查看每个来源最后状态、重复率、插入率、失败数和最近异常任务。
2026-07-07: 修复弱信号导入任务类型，使用数据库允许的 `manual` job_type，避免真实导入时触发约束错误。
2026-07-07: 新增运行手册和 UAT 验收结论：
  - `docs/data-governance/supply-chain-data-collection-runbook-2026-07-07.md`
  - `docs/qa/supply-chain-data-collection-uat-signoff-2026-07-07.md`
```
