# AI Token 输出电力产业链 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有八层产业链、七个产业横向维度和独立市场交易层的框架下，落地 `ai_token_output_power`（富余电力驱动的 AI 推理 Token 输出产业链），支持证据分级、Token 产能/成本计算、A/B/C/D 四个股票池、候选排名和 staging 注册。

**Architecture:** 配置层定义 L1-L8、七个产业维度、电力来源分类和 E0-E5 证据规则；纯计算引擎负责 Token 产能、单位成本、证据等级、股票池和市场层闸门；PostgreSQL 迁移保存电力证据、产能快照、七维评分、独立市场快照、池状态和状态迁移；物化工具只在 staging/dry-run 运行，API 只读正式可用池并把 D 池作为非正式观察数据返回。被拒绝、禁用、过期或未审核证据不进入正式推荐排名，市场信号不反向提高产业证据等级。

**Tech Stack:** Python 3.11、pytest、FastAPI、PostgreSQL/Alembic、JSON 配置、现有 `kronos_factors` 引擎、`tools/codex-lowio.sh`。

## Global Constraints

- 固定链标识为 `chain_id = ai_token_output_power`，不得再创建同义链标识。
- 纵向必须完整保存 `L1` 至 `L8`；横向只保存七个产业维度：`function_value`、`technology_route`、`physical_bom`、`value_pool`、`competition_moat`、`supply_demand_cycle`、`evidence_validation`。
- 市场交易层单独存储和计算；估值、涨跌、换手、资金、拥挤度和策略信号不能提高证据等级、真实性分或股票池等级。
- 电力来源只能取 `curtailed_renewable`、`valley_power`、`park_self_generation_or_ppa`、`nominal_capacity`；没有并网、时段和电价证据时保存 `unknown`，不能默认低成本。
- Token 产能必须按模型、硬件、精度、上下文和批处理口径计算；禁止使用跨模型通用的 `tokens_per_mw_hour` 常数。
- 缺失数据保存 `NULL`/`unknown` 和 `coverage_ratio`，不把缺失当作零分，也不使用市场信号补齐产业证据。
- E0/E1 最高只能进入 D 池；E2 最高 C 池；E3/E4 最高 B 池；E5 且有连续收入/利润证据才允许 A 池。
- 被拒绝、禁用、过期或未审核的证据不得进入正式推荐排名；同一证据 ID在多映射中只能计分一次。
- 所有写库先用 `dry-run` 或 `staging`，正式注册必须由单独命令并显式环境变量授权。
- 保留当前工作树中与本功能无关的改动；每个任务只暂存本任务文件。

---

### Task 1: 注册 Token 输出链配置和七维元数据

**Files:**
- Modify: `packages/kronos-factors/configs/industry_chain_templates.json`，在 `templates` 中新增 `template_id = "ai_token_output_power"`。
- Modify: `packages/kronos-factors/configs/supply_chains.json`，在 `chains` 中新增 `AI Token输出电力` 配置。
- Modify: `packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py:CHAIN_IDS`，增加 `"AI Token输出电力": "ai_token_output_power"`。
- Create: `packages/kronos-factors/tests/test_token_output_power_config.py`。

**Interfaces:**
- Consumes: `load_supply_chain_config(path)` 和 `build_foundation_catalog(config, chains)`。
- Produces: `industry_chain_templates.json` 中可由 `template_id` 精确读取的八层模板；`build_foundation_catalog` 产出根节点 `chain_ai_token_output_power`；七维键名和电力来源枚举供后续迁移、引擎和 API 复用。

- [ ] **Step 1: 写配置契约测试（先让测试失败）**

```python
import json
from pathlib import Path

from kronos_factors.engine.supply_chain_foundation import (
    build_foundation_catalog,
    load_supply_chain_config,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "configs" / "industry_chain_templates.json"
SUPPLY_CHAIN_PATH = ROOT / "configs" / "supply_chains.json"


def test_token_output_template_has_eight_layers_seven_dimensions_and_separate_market_layer():
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    template = next(item for item in data["templates"] if item["template_id"] == "ai_token_output_power")
    assert [layer["layer_id"] for layer in template["layers"]] == [
        "demand", "task", "core_product", "foundation",
        "integration", "supporting", "infrastructure", "commercialization",
    ]
    assert template["industry_dimensions"] == [
        "function_value", "technology_route", "physical_bom",
        "value_pool", "competition_moat", "supply_demand_cycle",
        "evidence_validation",
    ]
    assert template["market_layer"]["separate_from_industry_evidence"] is True
    assert template["power_source_types"] == [
        "curtailed_renewable", "valley_power",
        "park_self_generation_or_ppa", "nominal_capacity",
    ]


def test_token_output_chain_slug_is_stable():
    config = load_supply_chain_config(SUPPLY_CHAIN_PATH)
    catalog = build_foundation_catalog(config, chains=["AI Token输出电力"])
    assert catalog.chain_lookup["AI Token输出电力"]["chain_id"] == "ai_token_output_power"
    assert any(node["node_id"] == "chain_ai_token_output_power" for node in catalog.nodes)
```

- [ ] **Step 2: 运行失败测试，确认缺少模板和链标识**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_output_power_config.py -q`

Expected: FAIL，提示找不到 `ai_token_output_power` 模板或 `AI Token输出电力` 链配置。

- [ ] **Step 3: 写入最小完整配置**

在 `industry_chain_templates.json` 中新增以下结构，并为八层分别填写设计文档中的节点、证据和指标：

```json
{
  "template_id": "ai_token_output_power",
  "name": "富余电力驱动的 AI 推理 Token 输出产业链",
  "base_template_id": "complex_tech",
  "chain_id": "ai_token_output_power",
  "industry_dimensions": [
    "function_value", "technology_route", "physical_bom",
    "value_pool", "competition_moat", "supply_demand_cycle",
    "evidence_validation"
  ],
  "power_source_types": [
    "curtailed_renewable", "valley_power",
    "park_self_generation_or_ppa", "nominal_capacity"
  ],
  "market_layer": {
    "separate_from_industry_evidence": true,
    "fields": ["valuation", "price_change", "turnover", "fund_flow", "crowding", "strategy_signal"]
  },
  "evidence_grades": {
    "E0": "concept_or_public_claim",
    "E1": "power_park_or_compute_plan",
    "E2": "facility_or_compute_built",
    "E3": "inference_runtime_qps_or_token_data",
    "E4": "api_revenue_customer_order_or_customer_validation",
    "E5": "recurring_token_revenue_and_profit"
  }
}
```

八层的 `layers` 数组使用下面的完整节点契约，不能继续复用只包含 AI 服务器的旧模板：

```json
[
  {"layer_id":"demand","order":1,"name":"需求层","segments":["企业Agent","智能客服","代码生成","搜索","内容生成","多模态应用"],"evidence":["API调用量","DAU","Token消耗量","付费客户数"]},
  {"layer_id":"task","order":2,"name":"任务层","segments":["实时推理","批量推理","长上下文","视频生成","端侧推理"],"evidence":["QPS","并发数","上下文长度","输入输出Token比"]},
  {"layer_id":"core_product","order":3,"name":"核心产品层","segments":["大模型","推理API","模型服务平台","Agent平台"],"evidence":["模型调用量","Token价格","SLA","客户留存"]},
  {"layer_id":"foundation","order":4,"name":"底层支撑层","segments":["GPU/ASIC","HBM","先进封装","推理软件","光互联"],"evidence":["Tokens/s","Tokens/W","显存","芯片供货和适配"]},
  {"layer_id":"integration","order":5,"name":"集成层","segments":["AI服务器","推理集群","模型压缩","量化","调度","推理引擎"],"evidence":["集群上线","利用率","延迟","KV Cache命中率"]},
  {"layer_id":"supporting","order":6,"name":"配套层","segments":["液冷","电源","变压器","PCB","连接器","光模块","存储"],"evidence":["机柜功率","PUE","冷却能力","交付订单"]},
  {"layer_id":"infrastructure","order":7,"name":"基础设施层","segments":["低谷电","弃风弃光","绿电交易","储能","IDC","智算中心"],"evidence":["可用MW","电价","供电小时","并网容量","机房利用率"]},
  {"layer_id":"commercialization","order":8,"name":"商业变现层","segments":["按Token计费","API","SaaS","Agent服务","算力租赁"],"evidence":["Token收入","单Token价格","毛利率","续费率","现金流"]}
]
```

在 `supply_chains.json` 中新增 `AI Token输出电力`，其 `industries` 至少包含 `软件服务`、`通信设备`、`电力`、`计算机设备`，并按 `需求、任务、核心产品、底层支撑、集成、配套、基础设施、商业变现` 提供可匹配关键词。同步把 `CHAIN_IDS` 增加为：

```python
"AI Token输出电力": "ai_token_output_power",
```

- [ ] **Step 4: 运行通过测试并检查 JSON**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_output_power_config.py -q`

Expected: `2 passed`，且 `python -m json.tool packages/kronos-factors/configs/industry_chain_templates.json` 返回成功。

- [ ] **Step 5: 提交本任务**

```bash
git add packages/kronos-factors/configs/industry_chain_templates.json packages/kronos-factors/configs/supply_chains.json packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py packages/kronos-factors/tests/test_token_output_power_config.py
git commit -m "feat: register token output power chain config"
```

### Task 2: 增加电力证据、产能、七维评分、市场快照和池状态表

**Files:**
- Create: `backend/alembic/versions/032_ai_token_output_power.py`。
- Create: `services/screener-service/tests/test_ai_token_output_power_migration_contract.py`。

**Interfaces:**
- Consumes: `business_tag_mapping(mapping_id, code, chain_id, status)`、现有 Alembic head `031`。
- Produces: 六张新增表及索引：`business_tag_token_output_power_evidence`、`business_tag_token_output_capacity_snapshots`、`business_tag_token_dimension_scores`、`business_tag_token_market_snapshots`、`business_tag_token_pool_states`、`business_tag_token_pool_transitions`。

- [ ] **Step 1: 写迁移契约测试（先让测试失败）**

```python
from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend" / "alembic" / "versions" / "032_ai_token_output_power.py"
)


def test_token_output_power_migration_defines_all_tables_and_guards():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    for table in [
        "business_tag_token_output_power_evidence",
        "business_tag_token_output_capacity_snapshots",
        "business_tag_token_dimension_scores",
        "business_tag_token_market_snapshots",
        "business_tag_token_pool_states",
        "business_tag_token_pool_transitions",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    for contract in [
        "power_source_type IN ('curtailed_renewable','valley_power','park_self_generation_or_ppa','nominal_capacity')",
        "evidence_grade IN ('E0','E1','E2','E3','E4','E5')",
        "pool_code IN ('A','B','C','D')",
        "dimension_id IN ('function_value','technology_route','physical_bom','value_pool','competition_moat','supply_demand_cycle','evidence_validation')",
        "separate_from_industry_evidence BOOLEAN NOT NULL DEFAULT TRUE",
        "coverage_ratio DOUBLE PRECISION",
        "billable_tokens DOUBLE PRECISION",
        "cost_per_million_tokens DOUBLE PRECISION",
    ]:
        assert contract in sql


def test_token_output_power_migration_has_mapping_and_date_indexes():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    for index_name in [
        "idx_token_power_evidence_mapping_date",
        "idx_token_power_capacity_mapping_date",
        "idx_token_power_dimension_mapping_date",
        "idx_token_power_market_mapping_date",
        "idx_token_power_pool_mapping_date",
        "idx_token_power_transition_mapping_date",
    ]:
        assert index_name in sql
```

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_ai_token_output_power_migration_contract.py -q`

Expected: FAIL，提示迁移文件不存在。

- [ ] **Step 3: 写 `032` 迁移的完整 DDL**

设置 `revision = "032"`、`down_revision = "031"`。六张表必须包含以下字段：

```python
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_output_power_evidence (
    evidence_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    code TEXT NOT NULL,
    chain_id TEXT NOT NULL,
    layer_id TEXT NOT NULL,
    power_source_type TEXT NOT NULL CHECK (power_source_type IN ('curtailed_renewable','valley_power','park_self_generation_or_ppa','nominal_capacity')),
    available_mw DOUBLE PRECISION,
    available_hours DOUBLE PRECISION,
    tariff_or_cost DOUBLE PRECISION,
    grid_connection_status TEXT NOT NULL DEFAULT 'unknown',
    storage_support TEXT NOT NULL DEFAULT 'unknown',
    curtailment_or_valley_evidence TEXT,
    hardware_type TEXT,
    model_profile TEXT,
    precision TEXT,
    batch_mode TEXT,
    tokens_per_mw_hour DOUBLE PRECISION,
    cluster_availability DOUBLE PRECISION,
    evidence_grade TEXT NOT NULL DEFAULT 'E0' CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
    review_status TEXT NOT NULL DEFAULT 'pending_review' CHECK (review_status IN ('candidate','pending_review','approved','rejected')),
    source_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    quote TEXT,
    as_of_date DATE NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
```

`business_tag_token_output_capacity_snapshots` 保存 `model_profile`、`hardware_type`、`precision`、`available_mw`、`operating_hours`、`utilization`、`tokens_per_mw_hour`、`cluster_availability`、`billable_tokens`、六项成本、`cost_per_million_tokens`、`calculation_status`、`evidence_ids`、`as_of_date`；`business_tag_token_dimension_scores` 保存七个 `dimension_id` 的分数、解释、覆盖率和证据 ID；`business_tag_token_market_snapshots` 保存估值、价格、换手、资金、拥挤度、策略信号 JSON，以及 `separate_from_industry_evidence = TRUE`；`business_tag_token_pool_states` 保存 `evidence_grade`、`pool_code`、真实性、商业化、产业吸引力、覆盖率、原因和下一验证日期；`business_tag_token_pool_transitions` 保存原池、新池、触发证据、日期、审核状态和下一验证节点。所有表都建立 `mapping_id, as_of_date` 复合索引。

上述五张表的字段契约固定如下，实施时按此字段逐一建表，不用自由命名：

```python
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_output_capacity_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    code TEXT NOT NULL,
    model_profile TEXT NOT NULL,
    hardware_type TEXT NOT NULL,
    precision TEXT NOT NULL,
    batch_mode TEXT NOT NULL,
    available_mw DOUBLE PRECISION,
    operating_hours DOUBLE PRECISION,
    utilization DOUBLE PRECISION,
    tokens_per_mw_hour DOUBLE PRECISION,
    cluster_availability DOUBLE PRECISION,
    billable_tokens DOUBLE PRECISION,
    electricity_cost DOUBLE PRECISION,
    compute_depreciation DOUBLE PRECISION,
    facility_and_cooling_cost DOUBLE PRECISION,
    network_cost DOUBLE PRECISION,
    operation_cost DOUBLE PRECISION,
    financing_cost DOUBLE PRECISION,
    cost_per_million_tokens DOUBLE PRECISION,
    calculation_status TEXT NOT NULL DEFAULT 'unknown',
    evidence_ids JSONB NOT NULL DEFAULT '[]',
    as_of_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_dimension_scores (
    dimension_score_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    dimension_id TEXT NOT NULL CHECK (dimension_id IN ('function_value','technology_route','physical_bom','value_pool','competition_moat','supply_demand_cycle','evidence_validation')),
    score DOUBLE PRECISION,
    explanation TEXT,
    coverage_ratio DOUBLE PRECISION,
    evidence_ids JSONB NOT NULL DEFAULT '[]',
    as_of_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (mapping_id, dimension_id, as_of_date)
)
""")
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_market_snapshots (
    market_snapshot_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    trade_date DATE NOT NULL,
    valuation JSONB NOT NULL DEFAULT '{}',
    price_change JSONB NOT NULL DEFAULT '{}',
    turnover JSONB NOT NULL DEFAULT '{}',
    fund_flow JSONB NOT NULL DEFAULT '{}',
    crowding JSONB NOT NULL DEFAULT '{}',
    strategy_signal JSONB NOT NULL DEFAULT '{}',
    market_signal_score DOUBLE PRECISION,
    separate_from_industry_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    source_status TEXT NOT NULL DEFAULT 'unknown',
    coverage_ratio DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (mapping_id, trade_date)
)
""")
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_pool_states (
    pool_state_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    evidence_grade TEXT NOT NULL CHECK (evidence_grade IN ('E0','E1','E2','E3','E4','E5')),
    pool_code TEXT NOT NULL CHECK (pool_code IN ('A','B','C','D')),
    authenticity_score DOUBLE PRECISION,
    commercialization_score DOUBLE PRECISION,
    industrial_attractiveness_score DOUBLE PRECISION,
    coverage_ratio DOUBLE PRECISION,
    reason_codes JSONB NOT NULL DEFAULT '[]',
    next_validation_node TEXT,
    next_validation_date DATE,
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    as_of_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (mapping_id, as_of_date)
)
""")
op.execute("""
CREATE TABLE IF NOT EXISTS business_tag_token_pool_transitions (
    transition_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
    old_pool_code TEXT CHECK (old_pool_code IN ('A','B','C','D')),
    new_pool_code TEXT NOT NULL CHECK (new_pool_code IN ('A','B','C','D')),
    trigger_evidence_ids JSONB NOT NULL DEFAULT '[]',
    transition_date DATE NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    next_validation_node TEXT,
    next_validation_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
```

- [ ] **Step 4: 运行迁移契约测试**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_ai_token_output_power_migration_contract.py -q`

Expected: `2 passed`。

- [ ] **Step 5: 提交本任务**

```bash
git add backend/alembic/versions/032_ai_token_output_power.py services/screener-service/tests/test_ai_token_output_power_migration_contract.py
git commit -m "feat: add token output power evidence schema"
```

### Task 3: 实现 Token 产能、单位成本、证据等级和股票池纯计算引擎

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/token_output_power.py`。
- Create: `packages/kronos-factors/tests/test_token_output_power_engine.py`。

**Interfaces:**
- Consumes: Task 1 的四类电力来源和 E0-E5 配置枚举。
- Produces: `calculate_billable_tokens(...) -> float | None`、`calculate_cost_per_million_tokens(...) -> float | None`、`derive_evidence_grade(flags: EvidenceFlags) -> str`、`derive_pool_code(...) -> str`、`calculate_opportunity_score(...) -> float | None`、`dedupe_evidence_ids(ids) -> list[str]`、`select_primary_mapping(rows) -> dict`。

- [ ] **Step 1: 写纯函数测试**

```python
import pytest

from kronos_factors.engine.token_output_power import (
    EvidenceFlags,
    calculate_billable_tokens,
    calculate_cost_per_million_tokens,
    calculate_opportunity_score,
    dedupe_evidence_ids,
    derive_evidence_grade,
    derive_pool_code,
    select_primary_mapping,
)


def test_billable_tokens_uses_all_five_factors():
    assert calculate_billable_tokens(10, 100, 0.5, 2000, 0.8) == 800000.0


def test_missing_capacity_returns_none_instead_of_zero():
    assert calculate_billable_tokens(10, None, 0.5, 2000, 0.8) is None


def test_invalid_utilization_is_rejected():
    with pytest.raises(ValueError, match="utilization"):
        calculate_billable_tokens(10, 100, 1.2, 2000, 0.8)


def test_cost_per_million_tokens_is_cost_sum_divided_by_billable_tokens():
    assert calculate_cost_per_million_tokens(100, 200, 50, 25, 10, 15, 1000000) == 400.0


def test_evidence_grade_and_pool_do_not_use_market_signal():
    flags = EvidenceFlags(power_or_plan=True, facility_built=True, runtime=True, commercial=True, recurring_profit=False)
    assert derive_evidence_grade(flags) == "E4"
    assert derive_pool_code("E4", has_customer_validation=True, has_token_revenue=True, has_profit=False, veto=False) == "B"
    assert derive_pool_code("E4", has_customer_validation=True, has_token_revenue=True, has_profit=True, veto=False) == "A"


def test_market_signal_cannot_admit_e0_to_formal_pool():
    assert calculate_opportunity_score("D", 90, 90, 90, 100) is None
    assert calculate_opportunity_score("B", 80, 70, 60, 50) == 16.8


def test_evidence_ids_are_deduplicated_and_primary_mapping_uses_evidence_then_benefit():
    assert dedupe_evidence_ids(["e1", "e1", "e2", "", None]) == ["e1", "e2"]
    rows = [
        {"mapping_id": "m1", "evidence_grade": "E3", "benefit_score": 90},
        {"mapping_id": "m2", "evidence_grade": "E4", "benefit_score": 60},
    ]
    assert select_primary_mapping(rows)["mapping_id"] == "m2"
```

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_output_power_engine.py -q`

Expected: FAIL，提示 `token_output_power` 模块不存在。

- [ ] **Step 3: 写最小纯计算实现**

实现以下固定接口，并把所有输入转为 `float` 后校验：容量/时长/Token 速率必须非负；`utilization`、`cluster_availability` 必须在 `[0, 1]`；任一产能因子缺失返回 `None`；单位成本在 `billable_tokens` 缺失或小于等于 0 时返回 `None`，计算为 `(六项成本之和 / billable_tokens) * 1_000_000`；`derive_evidence_grade` 按 E5→E0 逐级判断；`derive_pool_code` 按 A→D 判断且 `veto=True` 直接返回 `D`；`calculate_opportunity_score` 只接受 A/B/C，先通过池准入，再计算 `industrial_score * authenticity_score / 100 * commercialization_score / 100 * market_signal_score / 100`，D 返回 `None`。

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceFlags:
    power_or_plan: bool = False
    facility_built: bool = False
    runtime: bool = False
    commercial: bool = False
    recurring_profit: bool = False
```

- [ ] **Step 4: 运行引擎测试**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_token_output_power_engine.py -q`

Expected: `7 passed`。

- [ ] **Step 5: 提交本任务**

```bash
git add packages/kronos-factors/kronos_factors/engine/token_output_power.py packages/kronos-factors/tests/test_token_output_power_engine.py
git commit -m "feat: add token capacity and evidence scoring engine"
```

### Task 4: 物化 staging 数据并修复候选排名的证据闸门

**Files:**
- Create: `tools/materialize_ai_token_output_power.py`。
- Create: `tools/tests/test_materialize_ai_token_output_power.py`。
- Modify: `tools/build_supply_chain_candidate_ranking.py:fetch_mapping_rows` 及其 SQL CTE。
- Modify: `tools/tests/test_supply_chain_candidate_ranking.py`。

**Interfaces:**
- Consumes: Task 2 的六张表、Task 3 的纯函数、`business_tag_mapping`、`business_tag_evidence_events`、`business_tag_l8_evidence_status`、`business_tag_evidence_freshness`。
- Produces: `materialize(pg_url, as_of_date, mode, top_n) -> dict`；命令参数 `--pg-url`、`--as-of-date`、`--mode {dry-run,staging,apply}`、`--top-n`；正式排名查询只接收 `A/B/C`，D 仅作为 `provisional_items` 返回；所有 mapping SQL 排除 `rejected` 和 `disabled`。

- [ ] **Step 1: 写物化工具的纯函数测试**

```python
import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[1] / "materialize_ai_token_output_power.py"
SPEC = importlib.util.spec_from_file_location("materialize_ai_token_output_power", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_build_capacity_snapshot_preserves_model_and_hardware_profile():
    result = MODULE.build_capacity_snapshot({
        "available_mw": 10,
        "operating_hours": 100,
        "utilization": 0.5,
        "tokens_per_mw_hour": 2000,
        "cluster_availability": 0.8,
        "model_profile": "long_context_32k",
        "hardware_type": "inference_gpu",
        "precision": "int8",
    })
    assert result["billable_tokens"] == 800000.0
    assert result["model_profile"] == "long_context_32k"
    assert result["hardware_type"] == "inference_gpu"


def test_pool_materialization_keeps_d_out_of_formal_items():
    result = MODULE.split_formal_and_provisional([
        {"mapping_id": "m1", "pool_code": "A"},
        {"mapping_id": "m2", "pool_code": "D"},
    ])
    assert [item["mapping_id"] for item in result["formal_items"]] == ["m1"]
    assert [item["mapping_id"] for item in result["provisional_items"]] == ["m2"]


def test_mapping_sql_excludes_rejected_and_disabled_statuses():
    sql = MODULE.build_mapping_sql("ai_token_output_power", formal_only=True)
    assert "COALESCE(m.status, '') NOT IN ('rejected', 'disabled')" in sql
    assert "pool_code IN ('A', 'B', 'C')" in sql
```

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py tools/tests/test_materialize_ai_token_output_power.py -q`

Expected: FAIL，提示物化工具不存在。

- [ ] **Step 3: 实现 staging 物化工具**

`build_capacity_snapshot(row)` 必须把 Task 3 的五因子公式结果和成本字段写入容量快照；`split_formal_and_provisional(rows)` 把 A/B/C 放入 `formal_items`，D 放入 `provisional_items`；`materialize(..., mode="dry-run")` 只返回待插入、待更新、被排除和覆盖率计数，不执行 `INSERT`/`UPDATE`；`mode="staging"` 只写 `business_tag_token_*` 六张表和 `supply_chain_deconstruct_views`，不改 `business_tag_mapping.status`；`mode="apply"` 仅允许在显式命令行调用时执行同样的幂等 upsert。

CLI 固定输出 JSON 字段：`mode`、`as_of_date`、`chain_id`、`mapping_count`、`evidence_count`、`capacity_snapshot_count`、`pool_counts`、`formal_count`、`provisional_count`、`excluded_count`、`coverage_ratio`、`limitations`。

- [ ] **Step 4: 修复候选排名 SQL**

在 `build_supply_chain_candidate_ranking.py` 抽出 `build_mapping_sql(chain_id: str | None = None, formal_only: bool = False) -> str`，`mapping_base` 增加：

```sql
WHERE COALESCE(m.status, '') NOT IN ('rejected', 'disabled')
```

当 `chain_id == 'ai_token_output_power'` 且 `formal_only=True` 时，增加最新池状态连接并限制：

```sql
AND ps.pool_code IN ('A', 'B', 'C')
AND ps.evidence_grade IN ('E2', 'E3', 'E4', 'E5')
AND COALESCE(ps.coverage_ratio, 0) >= 0.60
```

保留现有其他产业链的排序字段，但把 `mapping_status` 作为真正的准入条件，不再只读取而不使用。`fetch_mapping_rows` 增加 `chain_id` 和 `formal_only` 参数，默认值保持现有调用兼容。

- [ ] **Step 5: 运行物化和排名测试**

Run: `bash tools/codex-lowio.sh py tools/tests/test_materialize_ai_token_output_power.py tools/tests/test_supply_chain_candidate_ranking.py -q`

Expected: `所有测试通过`；排名测试必须证明 rejected mapping 不会进入 SQL 结果，D 池只出现在 `provisional_items`。

- [ ] **Step 6: 提交本任务**

```bash
git add tools/materialize_ai_token_output_power.py tools/tests/test_materialize_ai_token_output_power.py tools/build_supply_chain_candidate_ranking.py tools/tests/test_supply_chain_candidate_ranking.py
git commit -m "feat: materialize token output pools with evidence gates"
```

### Task 5: 增加后端查询边界和 Token 输出产业链 API

**Files:**
- Modify: `services/screener-service/app/domains/supply_chain/repository.py`。
- Modify: `services/screener-service/app/domains/supply_chain/service.py`。
- Modify: `services/screener-service/app/domains/screening/service.py`，增加两个路由和内部转发函数。
- Create: `services/screener-service/tests/test_token_output_power_api.py`。
- Modify: `services/screener-service/tests/test_domain_composition.py`。

**Interfaces:**
- Consumes: Task 2 的表、Task 3 的评分语义、Task 4 的 staging 物化结果。
- Produces: `repository.fetch_token_output_power_snapshot(cur, top_n, pool_code=None, trade_date=None) -> list[dict[str, Any]]`；`repository.fetch_token_output_power_provisional_snapshot(cur, top_n, pool_code=None, trade_date=None) -> list[dict[str, Any]]`；`repository.fetch_token_output_power_mapping(cur, mapping_id) -> dict[str, Any]`；`service.token_output_power_payload(top_n=50, pool_code=None, include_provisional=False, trade_date=None) -> dict[str, Any]`；`service.token_output_power_mapping_detail(mapping_id) -> dict[str, Any]`；HTTP `GET /supply-chain/token-output-power` 和 `GET /supply-chain/token-output-power/{mapping_id}`。

- [ ] **Step 1: 写 API 契约测试**

```python
from app.domains.supply_chain import service


def fake_snapshot(*_args, **_kwargs):
    return [
        {"mapping_id": "mapping-1", "pool_code": "A", "evidence_grade": "E5", "coverage_ratio": 0.9},
    ]


def fake_provisional_snapshot(*_args, **_kwargs):
    return [
        {"mapping_id": "mapping-d", "pool_code": "D", "evidence_grade": "E1", "coverage_ratio": 0.2},
    ]


def fake_mapping_detail(*_args, **_kwargs):
    return {
        "mapping_id": "mapping-1",
        "evidence_chain": [{"source_url": "https://example.test/evidence"}],
        "capacity_snapshots": [{"model_profile": "long_context_32k"}],
        "market_layer": {"separate_from_industry_evidence": True},
    }


def test_token_output_power_payload_keeps_market_layer_separate(monkeypatch):
    monkeypatch.setattr(service.repository, "fetch_token_output_power_snapshot", fake_snapshot)
    monkeypatch.setattr(service.repository, "fetch_token_output_power_provisional_snapshot", fake_provisional_snapshot)
    payload = service.token_output_power_payload(top_n=10, include_provisional=True)
    assert payload["chain_id"] == "ai_token_output_power"
    assert set(payload["layers"]) == {f"L{i}" for i in range(1, 9)}
    assert payload["industry_dimensions"] == [
        "function_value", "technology_route", "physical_bom",
        "value_pool", "competition_moat", "supply_demand_cycle",
        "evidence_validation",
    ]
    assert payload["market_layer"]["separate_from_industry_evidence"] is True
    assert payload["items"][0]["pool_code"] in {"A", "B", "C"}
    assert payload["provisional_items"][0]["pool_code"] == "D"


def test_token_output_power_mapping_detail_returns_traceable_evidence(monkeypatch):
    monkeypatch.setattr(service.repository, "fetch_token_output_power_mapping", fake_mapping_detail)
    payload = service.token_output_power_mapping_detail("mapping-1")
    assert payload["mapping_id"] == "mapping-1"
    assert payload["evidence_chain"][0]["source_url"]
    assert payload["capacity_snapshots"][0]["model_profile"] == "long_context_32k"
    assert payload["market_layer"]["separate_from_industry_evidence"] is True
```

测试替身必须返回一条 A 池、一条 D 池、一个电力证据、一条产能快照、七条维度记录和一条独立市场快照；不得用真实数据库连接。`service.token_output_power_payload` 只调用 `fetch_token_output_power_snapshot` 获取正式项，`include_provisional=True` 时再调用 `fetch_token_output_power_provisional_snapshot`。

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_token_output_power_api.py -q`

Expected: FAIL，提示查询函数或 API payload 不存在。

- [ ] **Step 3: 实现 repository 查询**

所有 SQL 先选择最新 `as_of_date`/`created_at` 记录；`fetch_token_output_power_snapshot` 默认 `include_provisional=False`，只查 A/B/C，只有显式为真才额外查询 D；查询必须带 `m.status NOT IN ('rejected','disabled')`；`fetch_token_output_power_mapping` 返回映射、七维评分、证据链、容量成本、池迁移、市场快照六个分组，任何缺表返回 `source_status = "missing_table"` 而不是伪造空分数。

- [ ] **Step 4: 实现 service payload 和 HTTP 路由**

`token_output_power_payload` 固定返回：`version`、`chain_id`、`as_of`、`source_status`、`layers`、`industry_dimensions`、`power_model`、`pools`、`items`、`provisional_items`、`market_layer`、`coverage_ratio`、`limitations`。`market_layer` 只携带市场快照字段，不能合并到 `industry_dimensions` 或 `evidence_validation`。

在 `services/screener-service/app/domains/screening/service.py` 增加：

```python
@router.get("/supply-chain/token-output-power")
async def supply_chain_token_output_power(
    top_n: int = Query(50, ge=1, le=200),
    pool_code: Optional[str] = Query(None, pattern="^[ABCD]$"),
    include_provisional: bool = Query(False),
    trade_date: Optional[str] = Query(None),
):
    return supply_chain_service.token_output_power_payload(top_n, pool_code, include_provisional, trade_date)


@router.get("/supply-chain/token-output-power/{mapping_id}")
async def supply_chain_token_output_power_mapping(mapping_id: str):
    return supply_chain_service.token_output_power_mapping_detail(mapping_id)
```

- [ ] **Step 5: 运行 API 和域组合测试**

Run: `bash tools/codex-lowio.sh py services/screener-service/tests/test_token_output_power_api.py services/screener-service/tests/test_domain_composition.py -q`

Expected: `所有测试通过`，并能在路由集合中找到两个新路径。

- [ ] **Step 6: 提交本任务**

```bash
git add services/screener-service/app/domains/supply_chain/repository.py services/screener-service/app/domains/supply_chain/service.py services/screener-service/app/domains/screening/service.py services/screener-service/tests/test_token_output_power_api.py services/screener-service/tests/test_domain_composition.py
git commit -m "feat: expose token output power chain API"
```

### Task 6: 完成 staging 注册、V1/V2 对照和数据质量报告

**Files:**
- Create: `tools/register_ai_token_output_power.py`。
- Create: `tools/audit_ai_token_output_power.py`。
- Create: `tools/tests/test_register_ai_token_output_power.py`。
- Create: `tools/tests/test_audit_ai_token_output_power.py`。
- Create: `docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md`。

**Interfaces:**
- Consumes: Task 1-5 的配置、迁移、纯计算引擎、物化结果和 API。
- Produces: `register(mode="staging"|"production", pg_url, as_of_date, connection=None) -> dict`；`audit(pg_url, as_of_date, previous_ranking_path, connection=None) -> dict`；staging 注册只写 `supply_chain_hierarchy_nodes`、`supply_chain_deconstruct_views` 和 `business_tag_token_*`，不把 D 池写入正式候选快照；审计报告包含 V1/V2 名单差异、四池数量、L1-L8 覆盖率、七维覆盖率、电力字段覆盖率、重复证据数、被排除映射数和阻断项。

- [ ] **Step 1: 写注册和审计测试**

```python
import pytest

from tools.register_ai_token_output_power import register
from tools.audit_ai_token_output_power import audit


class FakeConnection:
    def __init__(self):
        self.rows = {}

    def upsert(self, table, key, row):
        existed = (table, key) in self.rows
        self.rows[(table, key)] = row
        return "updated" if existed else "inserted"


@pytest.fixture
def fake_pg():
    return FakeConnection()


def test_production_registration_requires_explicit_environment_guard(monkeypatch):
    monkeypatch.delenv("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION", raising=False)
    with pytest.raises(PermissionError, match="ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION"):
        register(mode="production", pg_url="postgresql://test", as_of_date="2026-07-14")


def test_staging_registration_is_idempotent(fake_pg):
    first = register(mode="staging", pg_url="postgresql://test", as_of_date="2026-07-14", connection=fake_pg)
    second = register(mode="staging", pg_url="postgresql://test", as_of_date="2026-07-14", connection=fake_pg)
    assert first["inserted"] >= 1
    assert second["updated"] >= 1
    assert second["formal_pool_count"] == first["formal_pool_count"]


def test_audit_marks_unknown_power_fields_and_excludes_d_pool(fake_pg, tmp_path):
    report = audit("postgresql://test", "2026-07-14", tmp_path / "v1.json", connection=fake_pg)
    assert report["power_field_coverage"] < 1.0
    assert report["formal_pool_count"] == report["pool_counts"]["A"] + report["pool_counts"]["B"] + report["pool_counts"]["C"]
    assert report["provisional_pool_count"] == report["pool_counts"]["D"]
    assert "rejected_mapping_count" in report
```

- [ ] **Step 2: 运行失败测试**

Run: `bash tools/codex-lowio.sh py tools/tests/test_register_ai_token_output_power.py tools/tests/test_audit_ai_token_output_power.py -q`

Expected: FAIL，提示注册/审计模块不存在。

- [ ] **Step 3: 实现 staging 注册器**

注册器必须：读取固定 `chain_id`；对 L1-L8 节点使用稳定主键 `ai_token_output_power:L1` 至 `ai_token_output_power:L8`；以 `ON CONFLICT DO UPDATE` 写入层级节点和 `supply_chain_deconstruct_views`；只写 A/B/C 正式池快照，D 写入 `provisional_items` 对应的池状态；同一 `mapping_id + as_of_date` 重跑不产生重复行；`mode="production"` 没有环境变量 `ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1` 时抛出 `PermissionError`。

CLI 固定为：

```bash
python tools/register_ai_token_output_power.py --mode staging --as-of-date 2026-07-14
python tools/register_ai_token_output_power.py --mode production --as-of-date 2026-07-14
```

第二条命令在没有显式授权时必须失败，不得静默注册。

- [ ] **Step 4: 实现 V1/V2 审计器**

审计器读取旧版 `build_supply_chain_candidate_ranking.py` 输出和新链 API/表，按照 `code + chain_id` 对齐；分别输出 `pool_counts`、`formal_pool_count`、`provisional_pool_count`、`l1_l8_coverage`、`industry_dimension_coverage`、`power_field_coverage`、`capacity_model_coverage`、`duplicate_evidence_count`、`rejected_mapping_count`、`stale_evidence_count`、`v1_only_codes`、`v2_only_codes`、`blocking_issues`。任何 `formal_pool_count > 0` 但证据等级不足、池 D 进入正式项、市场信号进入真实性分、拒绝映射进入排名，都写入 `blocking_issues`。

- [ ] **Step 5: 运行 staging dry-run 和专项测试**

Run:

```bash
python tools/materialize_ai_token_output_power.py --mode dry-run --as-of-date 2026-07-14 --top-n 200
bash tools/codex-lowio.sh py tools/tests/test_register_ai_token_output_power.py tools/tests/test_audit_ai_token_output_power.py -q
```

Expected: dry-run 只输出 JSON 统计，不改变数据库；专项测试全部通过；若当前数据库没有 E3/E4/E5 证据，报告明确显示正式 A/B 池为 0 或受覆盖率限制，不能用概念数据填充。

- [ ] **Step 6: 生成 staging UAT 文档**

在 `docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md` 记录实际命令、`as_of_date`、数据库迁移版本、四池数量、覆盖率、排除原因、V1/V2 差异和阻断项。文档中必须明确：当前结果是 staging，不代表已经完成正式注册或可直接交易。

- [ ] **Step 7: 提交本任务**

```bash
git add tools/register_ai_token_output_power.py tools/audit_ai_token_output_power.py tools/tests/test_register_ai_token_output_power.py tools/tests/test_audit_ai_token_output_power.py docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md
git commit -m "feat: add token output power staging registration audit"
```

### Task 7: 全量专项验证和交付门槛

**Files:**
- Modify: `docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md`，补充最终测试结果。
- Test: `packages/kronos-factors/tests/test_token_output_power_config.py`。
- Test: `packages/kronos-factors/tests/test_token_output_power_engine.py`。
- Test: `services/screener-service/tests/test_ai_token_output_power_migration_contract.py`。
- Test: `services/screener-service/tests/test_token_output_power_api.py`。
- Test: `tools/tests/test_materialize_ai_token_output_power.py`。
- Test: `tools/tests/test_register_ai_token_output_power.py`。
- Test: `tools/tests/test_audit_ai_token_output_power.py`。

**Interfaces:**
- Consumes: Task 1-6 的全部实现和 staging 数据。
- Produces: 可复现的测试命令、无未解决阻断项的 staging 验收结论；如果阻断项仍存在，明确停在 staging，不执行 production 注册。

- [ ] **Step 1: 运行低 I/O 专项测试集合**

Run:

```bash
bash tools/codex-lowio.sh py \
  packages/kronos-factors/tests/test_token_output_power_config.py \
  packages/kronos-factors/tests/test_token_output_power_engine.py \
  services/screener-service/tests/test_ai_token_output_power_migration_contract.py \
  services/screener-service/tests/test_token_output_power_api.py \
  tools/tests/test_materialize_ai_token_output_power.py \
  tools/tests/test_register_ai_token_output_power.py \
  tools/tests/test_audit_ai_token_output_power.py -q
```

Expected: 所有专项测试通过；失败时保留完整失败项，不以“配置已写入”替代运行验证。

- [ ] **Step 2: 检查计划和代码质量门槛**

Run:

```bash
git diff --check HEAD~7..HEAD
rg -n "ai_token_output_power|curtailed_renewable|valley_power|park_self_generation_or_ppa|nominal_capacity|function_value|evidence_grade|pool_code|separate_from_industry_evidence" packages backend services tools docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md
```

Expected: 没有空白错误；关键契约在配置、迁移、引擎、工具、API 和 UAT 文档中均可追踪。

- [ ] **Step 3: 更新 UAT 结论**

只有同时满足以下条件才把文档结论写为“可申请正式注册”：L1-L8 齐全、七维覆盖率达到设计阈值、市场层独立、拒绝/过期证据为零进入正式项、同证据重复计分为零、产能/成本公式可复现、正式池没有 D 项、API 能返回证据链。否则写为“继续 staging”，列出下一验证节点。

- [ ] **Step 4: 最终提交本任务**

```bash
git add docs/superpowers/uat/2026-07-14-ai-token-output-power-staging.md
git commit -m "test: verify token output power staging chain"
```

## 完成定义

- 配置、数据库、纯计算、物化、排名、API、注册和审计均有独立测试。
- `ai_token_output_power` 是唯一链标识，八层、七维和市场交易层结构可下钻。
- 低价电力只有在并网、算力上线、推理运行和商业证据成立后才允许升级股票池。
- A/B/C/D 四个股票池可复现；D 池不进入正式推荐和回测。
- 现有排名中的 rejected/disabled 映射被排除，市场信号不污染产业证据分。
- staging 结果和阻断项全部记录后，才讨论是否执行 production 注册；本计划本身不自动执行 production 注册或交易。
