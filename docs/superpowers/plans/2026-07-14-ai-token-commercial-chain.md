# AI Token Commercial Output Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有电力主轴 `ai_token_output_power` 重构为以 Token 需求、生产、交付、计费和商业输出为主轴的新链 `ai_token_output`，并形成可审计的八层、七维、E0-E5 和 A/B/C/D 股票池。

**Architecture:** 新链使用独立 chain_id、配置、证据表和物化结果，旧链只读保留。纯函数引擎负责代码标准化、层级分类、证据门槛和评分；工具层负责注册、候选迁移、物化和审计；供应链 repository/service/API 只读取新链结果，不以市场信号提升产业证据等级。

**Tech Stack:** Python 3、PostgreSQL 16、Alembic、psycopg2、FastAPI/Pydantic、pytest、JSON 配置。

## Global Constraints

- 新主链标识固定为 `ai_token_output`；旧 `ai_token_output_power` 不删除、不覆盖、不自动升级。
- 电力只属于 `inference_unit_economics` 成本因子，不作为主层级或股票池升级前提。
- 评分单元固定为“公司 × 业务标签 × 产业层级”；证券代码入库前统一为六位代码。
- E0/E1 只能进入 D，E2 进入 C，E3 进入 B，E4/E5 进入 A。
- 没有客户调用、上线或持续交付证据不得进入 A/B；硬件供货可以进入 C，但不得标记为 Token 收入。
- `rejected`/`disabled` 不进入正式池；市场交易信号不能改变证据等级或股票池。
- 未知数据保存为 `NULL` 或 `unknown`，禁止用行业均值或默认值伪造公司事实。
- production 注册、旧链删除和投资建议不在本计划范围内。

---

## File Structure

- `packages/kronos-factors/configs/industry_chain_templates.json`：新增 `ai_token_output` 八层与七维配置。
- `packages/kronos-factors/kronos_factors/engine/token_commercial_output.py`：代码标准化、层级分类、证据门槛、七维加权和股票池判定。
- `backend/alembic/versions/035_ai_token_commercial_output.py`：新链独立证据、评分、池状态和迁移日志表。
- `tools/register_ai_token_output.py`：注册新链节点与视图。
- `tools/rebuild_ai_token_output_candidates.py`：从旧链及公司业务证据重建、去重候选映射。
- `tools/materialize_ai_token_output.py`：物化七维评分和四池。
- `tools/audit_ai_token_output.py`：检查重复、宽泛标签、证据门槛、国内外输出和旧链隔离。
- `services/screener-service/app/domains/supply_chain/repository.py`：读取新链结构、池和证据下钻。
- `services/screener-service/app/domains/supply_chain/service.py`：组装 API 响应并隔离市场层。
- `docs/superpowers/uat/2026-07-14-ai-token-commercial-output-staging.md`：记录真实 staging 结果和限制。

### Task 1: 新链八层和七维配置

**Files:**
- Modify: `packages/kronos-factors/configs/industry_chain_templates.json`
- Create: `packages/kronos-factors/tests/test_token_commercial_output_config.py`

**Interfaces:**
- Consumes: JSON 根对象的 `templates` 数组。
- Produces: `template_id == "ai_token_output"`，包含 `layers`、`industry_dimensions` 和 `market_layer_separate`。

- [ ] **Step 1: 写失败配置测试**

```python
def test_token_output_template_has_confirmed_layers_and_dimensions():
    template = load_template("ai_token_output")
    assert [row["name"] for row in template["layers"]] == [
        "Token需求场景", "模型与AI产品", "推理优化软件", "核心算力硬件",
        "集群与网络支撑", "Token服务与交付平台", "计量计费与运营", "商业变现与输出",
    ]
    assert template["industry_dimensions"] == [
        "demand_authenticity", "model_product_strength", "inference_unit_economics",
        "bom_supply_position", "delivery_customer_stickiness", "commercial_output",
        "evidence_realization",
    ]
    assert template["market_layer_separate"] is True
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_commercial_output_config.py -q`

Expected: FAIL，提示找不到 `ai_token_output`。

- [ ] **Step 3: 添加新模板**

配置八层名称、segments 和证据字段；L1 至少包含 Agent、代码生成、客服、搜索、多模态和行业 AI，L8 至少包含 API 收入、Agent/SaaS、行业方案和海外服务输出。保留旧 `ai_token_output_power` 模板不变。

- [ ] **Step 4: 验证通过并提交**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_commercial_output_config.py -q`

Expected: PASS。

```bash
git add packages/kronos-factors/configs/industry_chain_templates.json packages/kronos-factors/tests/test_token_commercial_output_config.py
git commit -m "feat: add AI token commercial output chain config"
```

### Task 2: 纯函数分类、评分和股票池门槛

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/token_commercial_output.py`
- Create: `packages/kronos-factors/tests/test_token_commercial_output_engine.py`

**Interfaces:**
- Produces: `normalize_stock_code(code: str) -> str`。
- Produces: `classify_token_role(tag: str, evidence: dict) -> str | None`，返回 `L1` 至 `L8`。
- Produces: `score_token_dimensions(values: dict[str, float | None]) -> dict`。
- Produces: `derive_token_pool(evidence_grade: str, review_status: str, facts: dict) -> tuple[str | None, list[str]]`。

- [ ] **Step 1: 写代码标准化与宽泛标签测试**

```python
def test_normalize_stock_code_merges_exchange_suffixes():
    assert normalize_stock_code("300308.SZ") == "300308"
    assert normalize_stock_code("300308") == "300308"

def test_broad_cloud_tag_needs_specific_evidence():
    assert classify_token_role("云服务", {}) is None
    assert classify_token_role("推理API云服务", {"api_calls": 100}) == "L6"
```

- [ ] **Step 2: 写证据硬门槛测试**

```python
@pytest.mark.parametrize("grade,review,facts,expected", [
    ("E0", "candidate", {}, "D"),
    ("E1", "approved", {"product": True}, "D"),
    ("E2", "approved", {"verified_supply": True}, "C"),
    ("E3", "approved", {"customer_usage": True, "running": True}, "B"),
    ("E4", "approved", {"token_revenue": True}, "A"),
    ("E5", "approved", {"token_revenue": True, "continuous_cashflow": True}, "A"),
    ("E4", "rejected", {"token_revenue": True}, None),
])
def test_pool_gate(grade, review, facts, expected):
    assert derive_token_pool(grade, review, facts)[0] == expected
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_commercial_output_engine.py -q`

Expected: FAIL，模块尚不存在。

- [ ] **Step 4: 实现最小纯函数引擎**

权重固定为：业务真实性20、Token价值捕获20、技术与推理效率15、客户及商业化15、竞争壁垒10、成长兑现10、证据质量10。缺失维度不补默认分，返回 `coverage_ratio = 已有权重 / 100`；正式排序要求 `coverage_ratio >= 0.60`。

- [ ] **Step 5: 运行测试并提交**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_commercial_output_engine.py -q`

Expected: PASS。

```bash
git add packages/kronos-factors/kronos_factors/engine/token_commercial_output.py packages/kronos-factors/tests/test_token_commercial_output_engine.py
git commit -m "feat: add token commercial scoring and evidence gates"
```

### Task 3: 035 独立数据迁移

**Files:**
- Create: `backend/alembic/versions/035_ai_token_commercial_output.py`
- Create: `services/screener-service/tests/test_ai_token_commercial_migration_contract.py`

**Interfaces:**
- Consumes: Alembic revision `034`。
- Produces: `business_tag_token_commercial_evidence`、`business_tag_token_commercial_scores`、`business_tag_token_commercial_pool_states`、`business_tag_token_commercial_pool_transitions`。

- [ ] **Step 1: 写迁移合同测试**

```python
def test_migration_is_isolated_from_power_chain():
    sql = MIGRATION_PATH.read_text()
    assert 'revision: str = "035"' in sql
    assert 'down_revision: Union[str, None] = "034"' in sql
    assert "business_tag_token_commercial_evidence" in sql
    assert "domestic_output_status" in sql
    assert "overseas_output_status" in sql
    assert "token_role" in sql
    assert "evidence_grade IN ('E0','E1','E2','E3','E4','E5')" in sql
    assert "DROP TABLE business_tag_token_output_power_evidence" not in sql
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_ai_token_commercial_migration_contract.py -q`

Expected: FAIL，迁移文件不存在。

- [ ] **Step 3: 编写 035 迁移**

证据表保存 `mapping_id`、标准化 `code`、`layer_id`、`token_role`、国内/海外输出状态、Token指标、客户/交付/收入状态、E0-E5、审核状态、来源和原文。评分表保存七维原始分、综合分、覆盖率和证据ID。池表使用 `UNIQUE(mapping_id, as_of_date)`。

- [ ] **Step 4: 验证迁移链和合同测试**

Run: `cd backend && .venv/bin/alembic heads`

Expected: 仅 `035 (head)`。

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_ai_token_commercial_migration_contract.py -q`

Expected: PASS。

- [ ] **Step 5: 提交迁移**

```bash
git add backend/alembic/versions/035_ai_token_commercial_output.py services/screener-service/tests/test_ai_token_commercial_migration_contract.py
git commit -m "feat: add token commercial evidence schema"
```

### Task 4: 新链注册工具

**Files:**
- Create: `tools/register_ai_token_output.py`
- Create: `tools/tests/test_register_ai_token_output.py`

**Interfaces:**
- Consumes: `industry_chain_templates.json` 中 `ai_token_output`。
- Produces: `register(mode: str, pg_url: str, as_of_date: str, connection=None) -> dict`。

- [ ] **Step 1: 写失败测试**

```python
def test_registration_creates_eight_isolated_nodes(fake_connection):
    result = register("staging", "unused", "2026-07-14", fake_connection)
    assert result["chain_id"] == "ai_token_output"
    assert result["node_count"] == 8
    assert all(row["chain_id"] == "ai_token_output" for row in fake_connection.node_rows)
```

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py tools/tests/test_register_ai_token_output.py -q`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现注册**

复用现有节点/视图表的 upsert 方式，但节点 ID 固定为 `ai_token_output:L1` 至 `ai_token_output:L8`。production 仍要求 `ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1`。

- [ ] **Step 4: 验证并提交**

Run: `bash tools/codex-lowio.sh py tools/tests/test_register_ai_token_output.py -q`

Expected: PASS。

```bash
git add tools/register_ai_token_output.py tools/tests/test_register_ai_token_output.py
git commit -m "feat: register AI token commercial output chain"
```

### Task 5: 候选映射重建与代码去重

**Files:**
- Create: `tools/rebuild_ai_token_output_candidates.py`
- Create: `services/screener-service/tests/test_rebuild_ai_token_output_candidates.py`

**Interfaces:**
- Consumes: 旧链映射、公司业务标签及其原始证据。
- Uses: `normalize_stock_code`、`classify_token_role`。
- Produces: `rebuild(pg_url: str, as_of_date: str, dry_run: bool) -> dict`。

- [ ] **Step 1: 写去重和不继承 verified 的测试**

```python
def test_rebuild_deduplicates_and_downgrades_cross_chain_rows():
    rows = [
        source("300308", "高速光模块", "verified"),
        source("300308.SZ", "高速光模块", "verified"),
    ]
    result = build_candidates(rows)
    assert len(result) == 1
    assert result[0]["code"] == "300308"
    assert result[0]["status"] == "candidate"
    assert result[0]["evidence_grade"] == "E0"
```

- [ ] **Step 2: 写宽泛标签阻断测试**

```python
def test_generic_tags_require_manual_review():
    result = build_candidates([source("603881", "云服务", "verified")])
    assert result[0]["layer_id"] is None
    assert "broad_tag_requires_review" in result[0]["reason_codes"]
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_rebuild_ai_token_output_candidates.py -q`

Expected: FAIL，工具不存在。

- [ ] **Step 4: 实现可追溯重建**

以 `(normalize_stock_code(code), layer_id, normalized_business_tag)` 去重。每条记录保存 `source_chain_id`、`source_mapping_id`、分类规则、未验证字段和下一验证节点。宽泛“软件/云服务/数据中心/AI业务”不自动分层；跨链 verified 统一降为 `candidate/E0/D`。

- [ ] **Step 5: dry-run 验证和提交**

Run: `python3 tools/rebuild_ai_token_output_candidates.py --as-of-date 2026-07-14 --dry-run`

Expected: 输出旧映射数、标准化后公司数、可分类数、宽泛标签待复核数和 L1-L8 分布，不写库。

```bash
git add tools/rebuild_ai_token_output_candidates.py services/screener-service/tests/test_rebuild_ai_token_output_candidates.py
git commit -m "feat: rebuild token output candidates with evidence isolation"
```

### Task 6: 七维评分与四池物化

**Files:**
- Create: `tools/materialize_ai_token_output.py`
- Create: `tools/tests/test_materialize_ai_token_output.py`

**Interfaces:**
- Consumes: 新链 mapping 和 commercial evidence。
- Uses: `score_token_dimensions`、`derive_token_pool`。
- Produces: `materialize(pg_url: str, as_of_date: str, mode: str) -> dict`。

- [ ] **Step 1: 写硬件与Token收入隔离测试**

```python
def test_hardware_supply_can_reach_c_but_not_token_revenue_a():
    row = evidence(grade="E2", verified_supply=True, token_revenue=None)
    state = build_pool_state(row)
    assert state["pool_code"] == "C"
    assert "token_revenue_unverified" in state["reason_codes"]
```

- [ ] **Step 2: 写市场信号不得升级产业池测试**

```python
def test_market_signal_does_not_change_industry_pool():
    row = evidence(grade="E1", product=True, market_signal_score=99)
    assert build_pool_state(row)["pool_code"] == "D"
```

- [ ] **Step 3: 运行失败测试**

Run: `bash tools/codex-lowio.sh py tools/tests/test_materialize_ai_token_output.py -q`

Expected: FAIL，物化器不存在。

- [ ] **Step 4: 实现 dry-run、staging、apply 三种模式**

`dry-run` 只计算；`staging` 写新链独立评分/池表；`apply` 仍不得修改旧链。输出 L1-L8、七维覆盖率、A/B/C/D、国内/海外输出数、宽泛标签数和排除数。

- [ ] **Step 5: 验证并提交**

Run: `bash tools/codex-lowio.sh py tools/tests/test_materialize_ai_token_output.py -q`

Expected: PASS。

```bash
git add tools/materialize_ai_token_output.py tools/tests/test_materialize_ai_token_output.py
git commit -m "feat: materialize AI token commercial stock pools"
```

### Task 7: Repository、Service 与 API 下钻

**Files:**
- Modify: `services/screener-service/app/domains/supply_chain/repository.py`
- Modify: `services/screener-service/app/domains/supply_chain/service.py`
- Modify: `services/screener-service/app/domains/screening/service.py`
- Create: `services/screener-service/tests/test_token_commercial_output_api.py`

**Interfaces:**
- Produces repository methods: `list_token_output_pools(as_of_date, pool_code, limit)`、`get_token_output_evidence(mapping_id)`。
- Produces service methods: `token_output_overview(...)`、`token_output_mapping_detail(mapping_id)`。
- Produces HTTP routes: `GET /api/v1/screener/supply-chain/token-output` and `GET /api/v1/screener/supply-chain/token-output/{mapping_id}`。
- API response separates `industry_score` and `market_signal_score`。

- [ ] **Step 1: 写 API 合同测试**

```python
def test_overview_separates_counts_and_market_layer(client):
    payload = client.get("/api/v1/screener/supply-chain/token-output").json()
    assert {"mapping_count", "unique_company_count", "formal_company_count"} <= payload.keys()
    assert payload["market_layer_separate"] is True
    assert "domestic_output_count" in payload
    assert "overseas_output_count" in payload
```

- [ ] **Step 2: 写证据下钻测试**

```python
def test_mapping_detail_exposes_provenance_and_gaps(client):
    detail = client.get("/api/v1/screener/supply-chain/token-output/TOKENMAP-1").json()
    assert "source_mapping_ids" in detail
    assert "evidence_grade" in detail
    assert "missing_fields" in detail
    assert "next_validation_node" in detail
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_token_commercial_output_api.py -q`

Expected: FAIL，新接口未定义。

- [ ] **Step 4: 实现查询与响应组装**

SQL 必须按标准化代码统计去重公司；正式池只包含 A/B/C；D 单列 `provisional_items`。市场信号只作为独立字段返回，不参与 repository 的 evidence grade 和 pool code 查询。

- [ ] **Step 5: 验证并提交**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_token_commercial_output_api.py -q`

Expected: PASS。

```bash
git add services/screener-service/app/domains/supply_chain/repository.py services/screener-service/app/domains/supply_chain/service.py services/screener-service/app/domains/screening/service.py services/screener-service/tests/test_token_commercial_output_api.py
git commit -m "feat: expose token commercial chain evidence API"
```

### Task 8: 审计工具和回归门

**Files:**
- Create: `tools/audit_ai_token_output.py`
- Create: `tools/tests/test_audit_ai_token_output.py`

**Interfaces:**
- Produces: `audit(pg_url: str, as_of_date: str, connection=None) -> dict`。
- Blocking keys: `duplicate_company_layer_count`、`broad_tag_formal_count`、`pool_gate_violation_count`、`legacy_chain_mutation_count`。

- [ ] **Step 1: 写阻断测试**

```python
def test_audit_blocks_duplicate_and_broad_formal_rows(fake_connection):
    result = audit("unused", "2026-07-14", fake_connection)
    assert result["duplicate_company_layer_count"] > 0
    assert result["broad_tag_formal_count"] > 0
    assert len(result["blocking_issues"]) == 2
```

- [ ] **Step 2: 写旧链隔离测试**

```python
def test_audit_reports_legacy_chain_without_mutating_it(fake_connection):
    result = audit("unused", "2026-07-14", fake_connection)
    assert result["legacy_chain_id"] == "ai_token_output_power"
    assert result["legacy_chain_mutation_count"] == 0
```

- [ ] **Step 3: 实现审计并验证**

审计还需输出八层覆盖、七维覆盖、A/B/C/D、国内/海外输出、NULL/unknown 比例、rejected 排除、证据时效和原始来源覆盖。

Run: `bash tools/codex-lowio.sh py tools/tests/test_audit_ai_token_output.py -q`

Expected: PASS。

- [ ] **Step 4: 提交**

```bash
git add tools/audit_ai_token_output.py tools/tests/test_audit_ai_token_output.py
git commit -m "feat: audit AI token commercial chain integrity"
```

### Task 9: Staging 迁移、重建、验收和文档

**Files:**
- Create: `docs/superpowers/uat/2026-07-14-ai-token-commercial-output-staging.md`

**Interfaces:**
- Consumes: Tasks 1-8 的全部命令行工具和数据库结构。
- Produces: 可复现的 staging 数量、证据覆盖和阻断项记录。

- [ ] **Step 1: 记录迁移前状态**

Run: `cd backend && .venv/bin/alembic current`

Expected: `034`。

Run: `psql "$KRONOS_PG_URL" -X -c "SELECT chain_id,count(*) FROM business_tag_mapping WHERE chain_id IN ('ai_token_output_power','ai_token_output') GROUP BY chain_id"`

Expected: 旧链数量被记录；新链为0或不存在。

- [ ] **Step 2: 执行 035 和新链注册**

Run: `cd backend && .venv/bin/alembic upgrade 035`

Expected: `034 -> 035` 成功。

Run: `python3 tools/register_ai_token_output.py --mode staging --as-of-date 2026-07-14`

Expected: 8 个节点、8 个视图；production 未注册。

- [ ] **Step 3: dry-run 后重建候选**

Run: `python3 tools/rebuild_ai_token_output_candidates.py --as-of-date 2026-07-14 --dry-run`

Expected: 输出去重和宽泛标签统计，不写库。

Run: `python3 tools/rebuild_ai_token_output_candidates.py --as-of-date 2026-07-14 --mode staging`

Expected: 新链只生成 candidate/E0 起始记录，旧链数量不变。

- [ ] **Step 4: 物化与审计**

Run: `python3 tools/materialize_ai_token_output.py --as-of-date 2026-07-14 --mode staging`

Run: `python3 tools/audit_ai_token_output.py --as-of-date 2026-07-14`

Expected: 重复公司同层为0、宽泛标签正式池为0、股票池门槛违规为0、旧链改动为0。A/B/C 可以为0，不允许为了填满股票池伪造证据。

- [ ] **Step 5: 运行全部专项回归**

Run each group separately to avoid repository `tests` package name collisions:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_commercial_output_config.py packages/kronos-factors/tests/test_token_commercial_output_engine.py -q
bash tools/codex-lowio.sh py services/screener-service/tests/test_ai_token_commercial_migration_contract.py services/screener-service/tests/test_rebuild_ai_token_output_candidates.py services/screener-service/tests/test_token_commercial_output_api.py -q
bash tools/codex-lowio.sh py tools/tests/test_register_ai_token_output.py tools/tests/test_materialize_ai_token_output.py tools/tests/test_audit_ai_token_output.py -q
```

Expected: 三组全部 PASS。

- [ ] **Step 6: 编写 UAT 文档**

文档必须记录：迁移版本、八层/七维覆盖、映射数、去重公司数、A/B/C/D、国内/海外输出、宽泛标签待复核数、证据覆盖、阻断项，以及“本结果不是投资建议”。不得把 D 池写成正式推荐池。

- [ ] **Step 7: 提交验收记录**

```bash
git add docs/superpowers/uat/2026-07-14-ai-token-commercial-output-staging.md
git commit -m "docs: record AI token commercial chain staging UAT"
```

## Final Verification

- [ ] `git diff --check` 无格式错误。
- [ ] `cd backend && .venv/bin/alembic current && .venv/bin/alembic heads` 均为 `035`。
- [ ] 新链八层节点为8，旧链节点和映射数量与迁移前一致。
- [ ] 标准化后不存在同公司、同层、同业务标签重复映射。
- [ ] 所有 A/B/C 记录均满足对应 E2/E3/E4 门槛；rejected/disabled 正式池数量为0。
- [ ] 市场交易字段与产业证据、产业评分分栏返回。
- [ ] production 注册未执行。
