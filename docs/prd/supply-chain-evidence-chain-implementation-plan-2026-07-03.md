# 产业链证据链补全实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 PRD 建立产业链证据链补全、结构化事实、阶段跟踪、证据新鲜度和预期差监控的底座。

**Architecture:** 先新增数据库底座，再实现离线采集和抽取脚本，然后接入现有供应链证据表，最后补前端跟踪台。外部付费数据源只做目录和接入点，不写假数据。

**Tech Stack:** PostgreSQL, Alembic, Python, FastAPI, React, Ant Design, existing `business_tag_*` tables.

## Global Constraints

- 永远不能用模型编造证据。
- 强证据决定阶段，半强证据辅助评分，弱信号只做预警。
- 所有阶段变化必须能追溯到原文摘录和来源。
- 所有新增表必须幂等写入。
- 未授权数据源必须显示为未配置或待授权。
- 不重做现有 L1-L8 拆解，只补证据链体系。

---

## 文件结构

计划新增或修改：

| 文件 | 动作 | 责任 |
|---|---|---|
| `backend/alembic/versions/023_supply_chain_evidence_pipeline.py` | 新增 | 新增 6 张证据链表和索引 |
| `services/screener-service/tests/test_supply_chain_v2_migration_contract.py` | 修改 | 增加迁移合同测试 |
| `tools/supply_chain_evidence_pipeline.py` | 新增 | 数据源种子、文本抽取、从现有事件回填原始文档和事实 |
| `tools/tests/test_supply_chain_evidence_pipeline.py` | 新增 | 测试来源分级、阶段识别、弱信号不升级 |
| `docs/prd/supply-chain-evidence-chain-tracking-prd-2026-07-03.md` | 已新增 | PRD |
| `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md` | 已新增 | 详细方案 |
| `docs/prd/supply-chain-evidence-chain-implementation-plan-2026-07-03.md` | 已新增 | 本计划 |
| `services/screener-service/app/routers/screener.py` | 后续修改 | 增加证据链查询接口 |
| `frontend/src/pages/supply-chain-bom/*` | 后续修改 | 增加证据链、时间线、待复核展示 |

---

## Task 1: 数据库迁移底座

**Files:**

- Create: `backend/alembic/versions/023_supply_chain_evidence_pipeline.py`
- Modify: `services/screener-service/tests/test_supply_chain_v2_migration_contract.py`

**Interfaces:**

- Consumes: existing `business_tag_mapping`, `business_tag_evidence_events`, `business_tag_stage_tracking`
- Produces: `evidence_source_catalog`, `raw_evidence_documents`, `evidence_extracted_facts`, `business_tag_stage_transition_log`, `business_tag_evidence_freshness`, `business_tag_expectation_monitor`

- [x] **Step 1: 写失败测试**

在 `services/screener-service/tests/test_supply_chain_v2_migration_contract.py` 增加测试，要求 `023_supply_chain_evidence_pipeline.py` 包含 6 张表和关键字段：

```python
def test_supply_chain_evidence_pipeline_migration_defines_source_document_fact_tables():
    sql = EVIDENCE_PIPELINE_MIGRATION_PATH.read_text(encoding="utf-8")

    required_tables = [
        "evidence_source_catalog",
        "raw_evidence_documents",
        "evidence_extracted_facts",
        "business_tag_stage_transition_log",
        "business_tag_evidence_freshness",
        "business_tag_expectation_monitor",
    ]

    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql
```

- [x] **Step 2: 跑测试确认失败**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q
```

Expected: 失败原因是 `023_supply_chain_evidence_pipeline.py` 不存在。

- [x] **Step 3: 新增迁移文件**

迁移必须包含：

```text
revision = "023"
down_revision = "022"
```

新增表：

```text
evidence_source_catalog
raw_evidence_documents
evidence_extracted_facts
business_tag_stage_transition_log
business_tag_evidence_freshness
business_tag_expectation_monitor
```

必要约束：

```text
source_level IN ('strong','mid','weak')
fact_nature IN ('confirmed_fact','company_claim','analyst_estimate','media_report','market_signal','rumor_signal')
validation_status IN ('confirmed','pending','contradicted','expired','rejected')
freshness_status IN ('fresh','stale','expired','unknown')
gap_status IN ('pending','fulfilled','partially_fulfilled','missed','contradicted')
```

- [x] **Step 4: 跑迁移合同测试**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q
```

Expected: PASS.

- [x] **Step 5: 跑真实数据库迁移**

Run:

```bash
cd backend
PYTHONPATH=. DATABASE_SYNC_URL=postgresql+psycopg2://kronos:kronos@localhost:6432/kronos alembic upgrade head
```

Expected: 新表存在，`alembic_version` 为 `023`。

---

## Task 2: 证据源目录和种子数据

**Files:**

- Create: `tools/supply_chain_evidence_pipeline.py`
- Create: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: `evidence_source_catalog`
- Produces: `seed-source-catalog` CLI

- [x] **Step 1: 写失败测试**

测试 `default_source_catalog()` 返回第一批、第二批、第三批来源，并包含 `confidence_cap` 和 `requires_cross_validation`。

```python
def test_default_source_catalog_covers_three_batches():
    sources = default_source_catalog()
    levels = {item.source_level for item in sources}
    assert levels == {"strong", "mid", "weak"}
    assert any(item.source_id == "cninfo_announcement" for item in sources)
    assert any(item.source_id == "financial_news_authoritative" for item in sources)
    assert any(item.source_id == "market_community_signal" for item in sources)
```

- [x] **Step 2: 跑测试确认失败**

Run:

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_pipeline.py -q
```

Expected: 失败原因是模块或函数不存在。

- [x] **Step 3: 实现 `EvidenceSource` 和 `default_source_catalog()`**

字段：

```python
source_id: str
source_name: str
source_type: str
source_level: Literal["strong", "mid", "weak"]
source_reliability_score: float
confidence_cap: float
is_official: bool
is_third_party_estimate: bool
is_market_sentiment: bool
requires_cross_validation: bool
license_status: str
update_frequency: str
crawl_method: str
enabled: bool
```

- [x] **Step 4: 实现 `seed-source-catalog` CLI**

命令：

```bash
python3 tools/supply_chain_evidence_pipeline.py seed-source-catalog --pg-url postgresql://kronos:kronos@localhost:6432/kronos
```

Expected: 输出 inserted/updated 数量。

- [x] **Step 5: 跑测试和真实库验证**

Run:

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_pipeline.py -q
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "select source_level,count(*) from evidence_source_catalog group by source_level;"
```

Expected: strong、mid、weak 都有记录。

Implementation note: `tools` 目录不是 Python package，脚本单测应沿用现有 `tools/tests` 惯例，通过 `importlib.util.spec_from_file_location()` 从文件路径加载被测脚本。

---

## Task 3: 文本结构化抽取

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`
- Modify: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: raw text, source metadata, business tag mapping keywords
- Produces: `ExtractedFact`

- [x] **Step 1: 写失败测试：strong 证据识别阶段**

```python
def test_extract_fact_detects_mass_production_from_strong_source():
    fact = extract_fact_from_text(
        text="公司800G高速光模块已实现批量供货，收入占比持续提升。",
        source_level="strong",
        company_code="300308.SZ",
        l5_tag="高速光模块",
        l6_route="800G",
    )
    assert fact.commercial_stage_signal == "C4"
    assert fact.growth_signal is True
    assert fact.validation_status == "confirmed"
```

- [x] **Step 2: 写失败测试：weak 不升级**

```python
def test_extract_fact_keeps_weak_signal_pending():
    fact = extract_fact_from_text(
        text="社区讨论称公司可能有机器人订单。",
        source_level="weak",
        company_code="002979.SZ",
        l5_tag="运动控制",
        l6_route="机器人",
    )
    assert fact.validation_status == "pending"
    assert fact.commercial_stage_signal is None
```

- [x] **Step 3: 实现关键词规则**

实现研发阶段、商用阶段、增长、盈利、围墙、风险关键词匹配。第一版用规则，后续再接 LLM 抽取。

- [x] **Step 4: 跑测试**

Run:

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_pipeline.py -q
```

Expected: PASS.

---

## Task 4: 原始文档和结构化事实入库

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`
- Modify: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: `raw_evidence_documents`, `evidence_extracted_facts`
- Produces: `ingest-text` CLI

- [x] **Step 1: 写失败测试：content_hash 稳定**

```python
def test_document_hash_is_stable_for_same_content():
    first = build_document_hash("source-a", "http://x", "标题", "正文")
    second = build_document_hash("source-a", "http://x", "标题", "正文")
    assert first == second
```

- [x] **Step 2: 实现文档 hash、文档 upsert、事实 upsert**

`ingest-text` 支持：

```bash
python3 tools/supply_chain_evidence_pipeline.py ingest-text \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --source-id manual_announcement \
  --company-code 300308.SZ \
  --company-name 中际旭创 \
  --title "样例公告" \
  --text "公司800G高速光模块已批量供货"
```

- [x] **Step 3: 跑真实库验证**

Run:

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "select count(*) from raw_evidence_documents; select count(*) from evidence_extracted_facts;"
```

Expected: 两张表数量增加。

---

## Task 5: 回填现有证据事件

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: existing `business_tag_evidence_events`
- Produces: `raw_evidence_documents`, `evidence_extracted_facts`, `business_tag_evidence_freshness`

- [x] **Step 1: 新增 `backfill-existing-events` CLI**

命令：

```bash
python3 tools/supply_chain_evidence_pipeline.py backfill-existing-events \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --run-prefix 18C \
  --limit 500
```

- [x] **Step 2: 映射 source_type 到 source_level**

规则：

```text
公告、财报、招投标、专利 → strong
互动易、调研纪要、官网、新闻、研报 → mid
社区、招聘、公众号、自媒体 → weak
未知来源 → mid 且 requires_cross_validation = true
```

- [x] **Step 3: 更新证据新鲜度**

按 `mapping_id` 统计最近 strong、mid、weak、any 日期，写入 `business_tag_evidence_freshness`。

- [x] **Step 4: 跑真实库验证**

Run:

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "select freshness_status,count(*) from business_tag_evidence_freshness group by freshness_status;"
```

Expected: 至少有 fresh 或 stale 记录。

Implementation note: 新鲜度刷新应覆盖全部 `business_tag_mapping`，没有事实证据的映射写入 `unknown`，用于暴露证据缺口。

---

## Task 6: 阶段变更和待复核规则

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`
- Modify: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: `evidence_extracted_facts`, `business_tag_stage_tracking`
- Produces: `business_tag_stage_transition_log`

- [x] **Step 1: 写测试：mid 来源只进待复核**

```python
def test_mid_source_stage_change_requires_review():
    decision = decide_stage_transition(source_level="mid", commercial_stage_signal="C4")
    assert decision.review_status == "pending_review"
    assert decision.auto_apply is False
```

- [x] **Step 2: 写测试：weak 来源不生成阶段升级**

```python
def test_weak_source_does_not_create_stage_upgrade():
    decision = decide_stage_transition(source_level="weak", commercial_stage_signal="C4")
    assert decision.auto_apply is False
    assert decision.new_commercial_stage is None
```

- [x] **Step 3: 实现 `refresh-stage-transitions` CLI**

只为 strong 和 mid 生成变更日志。weak 只写 freshness 和预警标记。

- [x] **Step 4: 验证**

Run:

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_pipeline.py -q
```

Expected: PASS.

---

## Task 7: 预期差监控

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`
- Modify: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: `evidence_extracted_facts`
- Produces: `business_tag_expectation_monitor`

- [x] **Step 1: 写测试：研报预期进入 monitor**

```python
def test_analyst_estimate_creates_expectation_claim():
    fact = extract_fact_from_text(
        text="研报预计公司机器人业务2026年收入快速增长。",
        source_level="mid",
        company_code="300503.SZ",
        l5_tag="关节模组",
        l6_route="机器人",
    )
    assert fact.fact_nature == "analyst_estimate"
```

- [x] **Step 2: 实现预期声明抽取**

关键词：

```text
预计
有望
放量
收入快速增长
贡献利润
订单兑现
```

- [x] **Step 3: 实现 monitor upsert**

默认 `gap_status = pending`，后续由强证据事实更新为 fulfilled、partially_fulfilled、missed 或 contradicted。

- [x] **Step 4: 验证**

Run:

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "select gap_status,count(*) from business_tag_expectation_monitor group by gap_status;"
```

Expected: 有 pending 记录。

---

## Task 8: 后端查询接口

**Files:**

- Modify: `services/screener-service/app/routers/screener.py`
- Modify: `services/screener-service/tests/test_chain_api.py`

**Interfaces:**

- Consumes: 新增 6 张表
- Produces:
  - `GET /api/v1/screener/supply-chain/business-tag/{mapping_id}/evidence-chain`
  - `GET /api/v1/screener/supply-chain/evidence-review/queue`

- [x] **Step 1: 写接口测试**

测试返回：

```json
{
  "version": "supply-chain-evidence-chain-v1",
  "mapping_id": "MAP-001",
  "documents": [],
  "facts": [],
  "freshness": {},
  "expectations": [],
  "limitations": []
}
```

- [x] **Step 2: 实现查询函数**

查询原始文档、结构化事实、新鲜度、预期差和阶段变更日志。

- [x] **Step 3: 验证**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py -q
```

Expected: 新增测试通过，既有测试不回归。

---

## Task 9: 前端跟踪台

**Files:**

- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/supply-chain-bom/CompanyResearchDrawer.tsx`
- Create: `frontend/src/pages/supply-chain-bom/EvidenceChainPanel.tsx`
- Create: `frontend/src/pages/supply-chain-bom/StageTimelinePanel.tsx`

**Interfaces:**

- Consumes: Task 8 API
- Produces: 公司业务标签证据链展示

- [x] **Step 1: 增加 API client 类型和方法**

新增 `EvidenceChainResponse` 类型，字段对齐后端响应。

- [x] **Step 2: 增加证据链面板**

展示：

```text
原始文档
结构化事实
阶段信号
三高信号
证据新鲜度
预期差
```

- [x] **Step 3: 增加阶段时间线**

展示 R 阶段、C 阶段、触发证据、复核状态。

- [x] **Step 4: 验证**

Run:

```bash
bash tools/codex-lowio.sh fe-typecheck
```

Expected: TypeScript 通过。

Implementation note: `frontend/src/api/client.ts` 已新增 `EvidenceChainResponse`、`EvidenceReviewQueueResponse` 和对应 API 方法；`CompanyResearchDrawer` 已从静态抽屉改为通过 `mapping_id` 拉取真实证据链、阶段变化和预期差数据。`packages/kronos-factors/kronos_factors/engine/supply_chain.py` 同步透传 `business_tag_mapping.mapping_id`，前端缺少 `mapping_id` 时只显示空态，不伪造证据链。`supply-chain/workbench` 已增加真实映射兜底：模型候选为空时返回 `business_tag_mapping` 候选，状态标记为 `mapping_fallback`。

---

## Task 10: 真实数据试跑和验收

**Files:**

- Modify: `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`

**Interfaces:**

- Consumes: 18 条产业链已落库公司映射
- Produces: UAT 证据文档

- [x] **Step 1: 迁移数据库**

Run:

```bash
cd backend
PYTHONPATH=. DATABASE_SYNC_URL=postgresql+psycopg2://kronos:kronos@localhost:6432/kronos alembic upgrade head
```

- [x] **Step 2: 写入数据源目录**

Run:

```bash
python3 tools/supply_chain_evidence_pipeline.py seed-source-catalog --pg-url postgresql://kronos:kronos@localhost:6432/kronos
```

- [x] **Step 3: 回填现有 18 条产业链证据**

Run:

```bash
python3 tools/supply_chain_evidence_pipeline.py backfill-existing-events --pg-url postgresql://kronos:kronos@localhost:6432/kronos --run-prefix 18C --limit 5000
```

- [x] **Step 4: 验证覆盖率**

Run:

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "
select count(*) from raw_evidence_documents;
select count(*) from evidence_extracted_facts;
select freshness_status,count(*) from business_tag_evidence_freshness group by freshness_status;
"
```

- [x] **Step 5: 写 UAT 证据**

在 `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md` 记录：

```text
迁移结果
来源目录数量
原始文档数量
结构化事实数量
新鲜度分布
阶段变更候选数量
预期差记录数量
已知限制
```

Implementation note: UAT 已记录在 `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`。当前真实库状态：`alembic_version=023`，数据源目录 13，原始文档 2056，结构化事实 2056，新鲜度 2199，阶段变化候选 30，预期差记录 159；抽样 `18C-MAP-ai_compute-300308SZ` 证据链接口返回 200。

---

## Task 11: P1 检索词生成和旧证据事件同步

**PRD AC:** AC-9、AC-10

**Files:**

- Modify: `tools/supply_chain_evidence_pipeline.py`
- Modify: `tools/tests/test_supply_chain_evidence_pipeline.py`

**Interfaces:**

- Consumes: `business_tag_mapping`
- Produces: 检索词 dry-run、`business_tag_evidence_events` 同步事件

- [x] **Step 1: 生成业务标签检索词**

新增：

```bash
python3 tools/supply_chain_evidence_pipeline.py generate-search-terms --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 3
```

输出公司名、证券代码、标签、L1-L8 路径组合出的检索词。`l1_l8_path` 为对象数组时只取 `name`，避免出现 Python dict 字符串。

- [x] **Step 2: 新增证据同步旧事件表**

`ingest-text` 写入 `raw_evidence_documents` 和 `evidence_extracted_facts` 后，同步 upsert `business_tag_evidence_events`，使现有证据时间线不失效。

- [x] **Step 3: 新证据入库后刷新新鲜度**

`ingest-text` 完成后调用 `refresh_evidence_freshness`，避免新增证据后前端仍显示旧的新鲜度状态。

- [x] **Step 4: 验证**

真实库验证：

```text
generate-search-terms --limit 1 => mapping_count=1，queries 已清理为公司/代码 + 标签/路径名称。
ingest-text P1证据同步样例 => legacy_events=1，freshness_rows=2199。
business_tag_evidence_events 可查到 EV-ffe7631856d35d9481aff91f / commercial_stage / approved。
```

当前真实库补充后状态：

```text
raw_evidence_documents=2057
evidence_extracted_facts=2057
business_tag_evidence_events=31888
business_tag_evidence_freshness=2199
```

---

## 自检清单

- [x] PRD 的所有 P0 AC 都有对应任务。
- [x] 第二批和第三批数据源被纳入来源目录和规则。
- [x] 弱信号不能改变阶段。
- [x] 所有阶段变化都有原文或结构化事实关联。
- [x] 未授权数据源不会生成假数据。
- [x] 前端不是第一步，先完成证据底座。

---

## Task 12: 18 条产业链增量刷新、全量拆解落库和项目验收

**PRD AC:** AC-1 至 AC-10

**Files:**

- Add: `tools/run_18chains_incremental_refresh.py`
- Add: `tools/tests/test_18chains_incremental_refresh.py`
- Modify: `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`
- Modify: `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md`

**Interfaces:**

- Consumes: Tushare 行情/资金/研报/券商推荐、公告、互动问答、主营构成、财报表、现有 `business_tag_mapping`
- Produces: `business_tag_evidence_events`、`raw_evidence_documents`、`evidence_extracted_facts`、`business_tag_l8_evidence_status`、`business_tag_stage_tracking`、`business_tag_three_high_scores`、`business_tag_expectation_gap_scores`

- [x] **Step 1: 新增统一增量刷新编排**

新增 `tools/run_18chains_incremental_refresh.py`，按以下顺序执行：

```text
外部/本地源增量刷新
数据源目录初始化
18 链业务标签映射批量证据生成
旧证据事件回填为原始文档和结构化事实
研发/商用阶段刷新
预期差监控刷新
数据库统计
验收报告输出
```

- [x] **Step 2: 财报披露滞后保护**

财务表不按自然日强行追最新，而按披露滞后窗口判断。2026-07-03 对应可验收财务期为 2026-03-31；本地 `financial_income` 和 `financial_indicator` 已到 2026-03-31，因此跳过慢速全市场重拉，避免重复拉取未披露或不可用数据。

- [x] **Step 3: 日志和兜底治理**

脚本关闭无效 SQLite fallback，并对直接调用的数据同步函数做输出截断，只保留尾部摘要。真实写入仍以 PostgreSQL 为准，避免采集过程被 SQLite 结构不一致日志淹没。

- [x] **Step 4: 真实增量源刷新**

本次已完成的真实增量源状态：

| 数据表 | 最新日期/期间 | 行数 |
|---|---:|---:|
| daily_kline | 2026-07-02 | 8604835 |
| daily_basic | 2026-07-01 | 10744455 |
| moneyflow | 2026-07-02 | 14294615 |
| financial_income | 2026-03-31 | 17595 |
| financial_indicator | 2026-03-31 | 33524 |
| forecast_data | 2027-12-31 | 27251 |
| fina_mainbz | 2026-03-31 | 379 |
| announcements | 2026-07-02 | 33924 |
| interact_qa | 2026-07-02 | 137322 |
| research_reports_tushare | 2026-06-24 | 116300 |
| broker_recommend | 202606 | 17347 |

- [x] **Step 5: 18 链全量拆解落库**

验收报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/eighteen_chains_incremental_refresh_20260703/18chains-incremental-20260703-130007_acceptance_report.json
```

核心结果：

| 指标 | 数量 |
|---|---:|
| 产业链数量 | 18 |
| 标签映射 | 2199 |
| 覆盖公司 | 1162 |
| 批量生成证据事件 | 23920 |
| 原始证据文档 | 32114 |
| 结构化事实 | 32114 |
| L8 证据状态 | 16366 |
| 阶段跟踪记录 | 2339 |
| 三高评分 | 2199 |
| 预期差评分 | 2199 |

- [x] **Step 6: 项目验收**

自动化验收通过：

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py services/screener-service/tests/test_chain_api.py tools/tests/test_supply_chain_evidence_pipeline.py tools/tests/test_18chains_incremental_refresh.py -q
```

结果：`71 passed`。

```bash
bash tools/codex-lowio.sh fe-typecheck
```

结果：通过。

---

## Task 15: 18 条产业链候选公司总榜

**PRD AC:** AC-2、AC-3、AC-4、AC-5、AC-7、AC-8

**目标：**

把 18 条产业链已落库的公司-标签证据，汇总成可排序、可导出的候选公司总榜。总榜不是交易买入信号，而是产业链证据强弱和后续研究优先级。

**Files:**

- Add: `tools/build_supply_chain_candidate_ranking.py`
- Add: `tools/tests/test_supply_chain_candidate_ranking.py`
- Modify: `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`
- Modify: `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md`

- [x] **Step 1: 新增排名公式**

评分权重：

| 维度 | 权重 | 说明 |
|---|---:|---|
| 三高总分 | 35% | 标签级增长、盈利、围墙、阶段、证据综合 |
| 围墙分 | 15% | 卡脖子、壁垒、国产替代等证据 |
| 阶段分 | 12% | 研发和商用阶段 |
| 证据分 | 12% | 标签级证据数量和维度 |
| L8 覆盖 | 10% | L8 细分证据是否完整 |
| 新鲜度 | 8% | 证据是否近期有效 |
| 预期差 | 6% | 实际进展相对市场预期 |
| 20 日涨幅 | 2% | 行情辅助项，不主导产业链排序 |

- [x] **Step 2: 新增总榜脚本**

执行：

```bash
python3 tools/build_supply_chain_candidate_ranking.py \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --top-n 120
```

输出：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.json
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.csv
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_candidate_ranking_20260703/supply_chain_candidate_ranking_20260703-135416.md
```

- [x] **Step 3: 真实库运行结果**

| 指标 | 数量 |
|---|---:|
| 标签映射评分行 | 2255 |
| 公司-产业链组合 | 1219 |
| 产业链数量 | 18 |
| 重点候选 | 1 |
| 观察 | 92 |
| 暂缓 | 1126 |

全局 Top 10：

| 排名 | chain_id | 代码 | 名称 | 分数 | 信号 | 最强标签 |
|---:|---|---|---|---:|---|---|
| 1 | ai_compute | 688498 | 源杰科技 | 80.97 | 重点候选 | 公司业务标签：AI芯片/芯片业务 |
| 2 | ai_compute | 688008 | 澜起科技 | 74.39 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 3 | ai_compute | 300502 | 新易盛 | 73.11 | 观察 | 公司业务标签：光模块业务 |
| 4 | ai_compute | 301308 | 江波龙 | 72.75 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 5 | ai_compute | 688110 | 东芯股份 | 72.39 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 6 | ai_compute | 603893 | 瑞芯微 | 71.79 | 观察 | 公司业务标签：AI算法业务 |
| 7 | ai_compute | 300308 | 中际旭创 | 71.04 | 观察 | 公司业务标签：光模块业务 |
| 8 | ai_compute | 688620 | 安凯微 | 70.43 | 观察 | 公司业务标签：AI芯片/芯片业务 |
| 9 | ai_compute | 603459 | 红板科技 | 70.17 | 观察 | 公司业务标签：PCB与连接材料业务 |
| 10 | ai_compute | 603160 | 汇顶科技 | 70.12 | 观察 | 公司业务标签：AI芯片/芯片业务 |

Implementation note: 全局榜被 `ai_compute` 占据较多，是因为该链映射和证据覆盖最充分；脚本已同时输出“分产业链 Top 5”，避免只看全局榜造成链间规模偏差。

- [x] **Step 4: 验证**

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_candidate_ranking.py -q
```

结果：`3 passed`。

## Task 16: 候选总榜 API 和前端真实数据页签

**PRD AC:** AC-2、AC-3、AC-4、AC-5、AC-7、AC-8、AC-10

**目标：**

把 Task 15 的候选公司总榜从离线报告接到产品页面，避免前端继续停留在静态或空工作台状态。页面必须直接读取后端真实库聚合结果，并能从公司行打开标签级证据链。

**Files:**

- Modify: `services/screener-service/app/routers/screener.py`
- Modify: `services/screener-service/tests/test_chain_api.py`
- Modify: `frontend/src/api/client.ts`
- Add: `frontend/src/pages/supply-chain-bom/SupplyChainCandidateRankingPanel.tsx`
- Add: `frontend/src/__tests__/SupplyChainCandidateRankingPanel.test.tsx`
- Modify: `frontend/src/pages/SupplyChainBom.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/__tests__/PrototypeRoutes.test.tsx`

- [x] **Step 1: 后端候选总榜接口**

新增接口：

```text
GET /api/v1/screener/supply-chain/candidate-ranking?top_n=100&chain_id=&signal=
```

接口返回：

| 字段 | 说明 |
|---|---|
| `summary` | 映射行、公司-产业链组合、产业链数量、信号分布 |
| `items` | 全局公司-产业链排序 |
| `by_chain` | 分产业链 Top 列表 |
| `best_mapping_id` | 前端打开证据链的业务标签入口 |
| `three_high_total`、`growth_score`、`profit_score`、`moat_score` | 标签级三高 |
| `research_stage`、`commercialization_stage` | 标签级研发和商用阶段 |
| `l8_match_rate`、`fresh_rate`、`fact_count` | L8 和证据质量 |
| `latest_price`、`change_1d_pct`、`change_20d_pct` | 行情辅助字段 |

- [x] **Step 2: 前端真实数据页签**

新增页签：

```text
/supply-chain-bom/ranking
```

展示内容：

| 区块 | 数据来源 |
|---|---|
| KPI | `/supply-chain/candidate-ranking.summary` |
| 排名表 | `/supply-chain/candidate-ranking.items` |
| 产业链/信号筛选 | 接口返回的真实 chain_id 和 signal |
| 查看证据 | 使用 `best_mapping_id` 打开既有公司研究抽屉 |

实现要求：

```text
不生成静态候选。
不使用公司整体证据冒充标签证据。
没有 mapping_id 时不能进入证据链。
```

- [x] **Step 3: 真实库验收**

真实接口烟测：

```text
HTTP 200
version = supply-chain-candidate-ranking-v1
source_status = ready
mapping_rows = 2255
company_chain_rows = 1219
chain_count = 18
signal_distribution = {'重点候选': 1, '观察': 92, '暂缓': 1126}
```

接口 Top 3：

| 排名 | chain_id | 代码 | 名称 | 分数 | 信号 | mapping_id |
|---:|---|---|---|---:|---|---|
| 1 | ai_compute | 688498 | 源杰科技 | 80.97 | 重点候选 | auto_688498_ai_compute_hardware |
| 2 | ai_compute | 688008 | 澜起科技 | 74.39 | 观察 | auto_688008_ai_compute_hardware |
| 3 | ai_compute | 300502 | 新易盛 | 73.11 | 观察 | auto_300502_ai_compute_hardware |

- [x] **Step 4: 验证**

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py::TestSupplyChainCandidateRanking -q
bash tools/codex-lowio.sh fe-test src/__tests__/SupplyChainCandidateRankingPanel.test.tsx
bash tools/codex-lowio.sh fe-test src/__tests__/PrototypeRoutes.test.tsx
bash tools/codex-lowio.sh fe-typecheck
```

结果：

```text
后端接口测试通过。
候选总榜组件测试通过。
路由覆盖测试通过，73 passed。
前端类型检查通过。
```

Implementation note: 本次验收将样本级结构化证据从 2057 条扩展到全量 32114 条；验收通过条件为 18 条产业链全部覆盖、映射/原始文档/结构化事实/L8 状态/三高评分均有真实落库数据。

---

## Task 13: 18 条产业链数据质量体检和补数优先级

**PRD AC:** AC-3、AC-4、AC-5、AC-7、AC-8、AC-10

**Files:**

- Add: `tools/audit_supply_chain_data_quality.py`
- Add: `tools/tests/test_supply_chain_quality_audit.py`
- Modify: `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`
- Modify: `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md`

**Interfaces:**

- Consumes: `business_tag_mapping`、`business_tag_evidence_events`、`evidence_extracted_facts`、`business_tag_l8_evidence_status`、`business_tag_evidence_freshness`、`business_tag_stage_tracking`、`business_tag_three_high_scores`、`business_tag_expectation_gap_scores`
- Produces: 18 链质量分、风险等级、补数优先级、JSON/Markdown 体检报告

- [x] **Step 1: 新增体检评分口径**

质量分由 7 个部分组成：

| 维度 | 权重 | 目的 |
|---|---:|---|
| 映射深度 | 20 | 判断产业链公司/标签是否太薄 |
| 公司广度 | 10 | 判断候选公司覆盖是否太窄 |
| 结构化证据 | 25 | 判断标签级证据是否足够 |
| L8 覆盖 | 20 | 判断细粒度证据是否完整 |
| 阶段覆盖 | 10 | 判断研发/商用阶段是否有记录 |
| 三高评分覆盖 | 5 | 判断三高是否已按标签计算 |
| 新鲜度 | 10 | 判断证据是否需要刷新 |

- [x] **Step 2: 新增补数优先级**

脚本按风险等级、质量分、映射数量排序，生成 `repair_priority`。风险解释：

```text
high：不是说产业链不好，而是当前数据底座不足或证据新鲜度不足，不能直接拿来做强推荐。
medium：已有基础数据，但排序前建议补映射或刷新证据。
low：可以进入日更跟踪，但仍可能需要扩公司池。
```

- [x] **Step 3: 真实库运行**

执行：

```bash
python3 tools/audit_supply_chain_data_quality.py --pg-url postgresql://kronos:kronos@localhost:6432/kronos
```

输出：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703/chain_quality_audit_20260703-131200.json
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703/chain_quality_audit_20260703-131200.md
```

总体结果：

| 指标 | 数值 |
|---|---:|
| 产业链数量 | 18 |
| 高风险链 | 3 |
| 中风险链 | 4 |
| 低风险链 | 11 |
| 平均质量分 | 78.88 |

Top 5 补数优先级：

| 优先级 | chain_id | 风险 | 质量分 | 主要动作 |
|---:|---|---|---:|---|
| 1 | future_materials | high | 74.41 | 补公司/标签映射；刷新过期/未知证据 |
| 2 | industrial_software | high | 74.41 | 补公司/标签映射；刷新过期/未知证据 |
| 3 | embodied_intelligence | high | 97.72 | 刷新过期/未知证据 |
| 4 | quantum_technology | medium | 74.72 | 补公司/标签映射；刷新过期/未知证据 |
| 5 | brain_computer_interface | medium | 76.26 | 补公司/标签映射；刷新过期/未知证据 |

Implementation note: `embodied_intelligence` 质量分高但风险高，是因为映射、事实、L8 证据较充分，但新鲜度只有 69.4%，属于“近期证据刷新不足”，不是“产业链拆解缺失”。

- [x] **Step 4: 验证**

```bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_quality_audit.py -q
```

结果：`3 passed`。

---

## Task 14: 优先链候选池补全和证据刷新

**PRD AC:** AC-3、AC-4、AC-5、AC-7、AC-8、AC-10

**背景：**

Task 13 体检后，优先修复三类问题：

```text
future_materials：映射太薄，且部分证据过期/未知。
industrial_software：映射太薄，且部分证据过期/未知。
embodied_intelligence：映射和证据较多，但新鲜度不足。
```

**Files:**

- Add: `tools/repair_priority_supply_chains.py`
- Add: `tools/tests/test_repair_priority_supply_chains.py`
- Add: `tools/tests/test_backfill_ai_compute_all_mapped.py`
- Modify: `tools/backfill_ai_compute_all_mapped.py`
- Modify: `docs/qa/supply-chain-evidence-chain-uat-2026-07-03.md`
- Modify: `docs/prd/supply-chain-evidence-chain-detailed-design-2026-07-03.md`

- [x] **Step 1: 新增候选池修复工具**

新增：

```bash
python3 tools/repair_priority_supply_chains.py \
  --pg-url postgresql://kronos:kronos@localhost:6432/kronos \
  --since 2026-01-01 \
  --limit-per-chain 20 \
  --execute
```

规则：

```text
只使用本地 PostgreSQL 已落库来源：公司资料、公告、互动问答、研报标题。
新增映射状态统一为 candidate。
证券代码统一去掉 .SZ/.SH 后缀，避免和行情/财务/资料表无法关联。
无效代码、单条宽泛主题研报命中不入库。
新增映射不伪造 company_business_segments 外键，business_segment_id 置空，node_id 和 L1-L8 路径保留。
```

- [x] **Step 2: 修复批量回填脚本的外键删除问题**

`tools/backfill_ai_compute_all_mapped.py` 原逻辑会删除旧 `batch_10y_%` 事件；当事件已被 `evidence_extracted_facts.evidence_event_id` 引用时会触发外键错误。

已改为：

```text
只删除未被 evidence_extracted_facts 引用的旧 batch 事件。
已结构化的事件不删除，后续通过 ON CONFLICT 更新。
```

- [x] **Step 3: 真实库修复执行**

修复报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/priority_chain_repair_20260703/priority_chain_repair_20260703-133930.json
/Users/rogerluo/程序目录/K线大模型/outputs/priority_chain_repair_20260703/priority_chain_repair_20260703-133930.md
```

修复结果：

| chain_id | 来源命中公司 | 选中候选 | 新增映射 | 刷新已有映射 | 新增证据事件 |
|---|---:|---:|---:|---:|---:|
| future_materials | 484 | 20 | 18 | 2 | 120 |
| industrial_software | 342 | 20 | 20 | 0 | 120 |
| embodied_intelligence | 354 | 20 | 18 | 2 | 120 |

合计新增：

| 项目 | 数量 |
|---|---:|
| 候选映射 | 56 |
| 修复证据事件 | 359 |

- [x] **Step 4: 三条链重算和结构化**

已执行：

```bash
python3 tools/backfill_ai_compute_all_mapped.py --chain-id future_materials
python3 tools/backfill_ai_compute_all_mapped.py --chain-id industrial_software
python3 tools/backfill_ai_compute_all_mapped.py --chain-id embodied_intelligence
python3 tools/supply_chain_evidence_pipeline.py backfill-existing-events --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
python3 tools/supply_chain_evidence_pipeline.py refresh-stage-transitions --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
python3 tools/supply_chain_evidence_pipeline.py refresh-expectation-monitor --pg-url postgresql://kronos:kronos@localhost:6432/kronos --limit 80000
```

结构化结果：

| 指标 | 数量 |
|---|---:|
| 证据事件 | 32917 |
| 原始证据文档 | 32919 |
| 结构化事实 | 32919 |
| L8 证据状态 | 16758 |
| 三高评分 | 32919 |
| 预期差评分 | 32919 |

- [x] **Step 5: 修复后质量复测**

复测报告：

```text
/Users/rogerluo/程序目录/K线大模型/outputs/supply_chain_quality_audit_20260703_after_repair/chain_quality_audit_20260703-134337.md
```

复测总览：

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| 高风险链 | 3 | 0 |
| 中风险链 | 4 | 5 |
| 低风险链 | 11 | 13 |
| 平均质量分 | 78.88 | 81.42 |

重点链变化：

| chain_id | 修复前 | 修复后 | 说明 |
|---|---|---|---|
| future_materials | high / 6 映射 | low / 24 映射 | 候选池补齐，进入日更跟踪 |
| industrial_software | high / 6 映射 | low / 26 映射 | 候选池补齐，进入日更跟踪 |
| embodied_intelligence | high / 36 映射 | medium / 54 映射 | 映射增加，但新鲜度仍只有 79.6%，需继续刷近期硬证据 |

- [x] **Step 6: 验证**

```bash
bash tools/codex-lowio.sh py tools/tests/test_repair_priority_supply_chains.py tools/tests/test_backfill_ai_compute_all_mapped.py -q
```

结果：通过。
