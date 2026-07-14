# 产业链研究与选股模型 V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有 L1-L8 和 V1 模型的前提下，实现“八层 × 八维”产业研究、公司受益评分、A/B/C/D 四股票池、灵巧手案例、真实落库及 `staging` 模型注册。

**Architecture:** 把计算从现有大型 FastAPI `service.py` 中分离到 `kronos_factors.engine` 的纯函数模块；PostgreSQL 只保存带日期的事实、评分和状态；独立物化/评分/注册/回测工具负责批处理；API 只读取已落库结果并返回证据和限制。V1 与 V2 使用不同表和 `model_key` 并行运行。

**Tech Stack:** Python 3、FastAPI、PostgreSQL 16、Alembic、psycopg2、pytest、JSON 配置、现有 `screening_snapshots`/`model_registry`。

## Global Constraints

- 保留现有 L1-L8 名称、模板字段、API 旧字段和 `supply_chain_expectation_gap_v1`。
- V2 模型键固定为 `supply_chain_research_selection_v2`，首次只能注册为 `staging`。
- 缺失数据保存为 `NULL/unknown`，不得静默转换成 0 分。
- 所有分数范围为 0-100，所有权重组启动时必须校验合计为 1.0（允许误差 `1e-9`）。
- 公司先通过真实性硬门槛，再计算受益分和股票池；D 池不得写入正式策略快照。
- 三高 V2 只针对公司相关业务，不得直接使用公司整体指标冒充标签业务指标。
- 同一股票多个映射不得累加；主映射之外仅允许最多 5 分、且有独立收入证据的多业务加分。
- 所有历史计算只使用 `publish_time <= trade_date cutoff` 的当时可得信息，禁止后验泄漏。
- 多日收益必须使用 `daily_kline.close × adj_factor` 的可比价格；复权因子缺失必须显式报告覆盖率。
- 任何自动任务不得批准证据、升级证据等级或覆盖人工驳回结果。
- 写数据库的工具必须支持 `--dry-run`，真实写入使用单事务；失败不得留下半注册状态。
- 不新增运行时依赖，不接入 LLM，不自动生成买卖建议。
- 验证优先使用 `bash tools/codex-lowio.sh py` 子命令，不启动全栈或完整 E2E。

---

## 文件结构

**新增：**

- `backend/alembic/versions/032_supply_chain_research_selection_v2.py`：V2 研究、评分和股票池表。
- `packages/kronos-factors/configs/industry_chain_selection_v2.json`：全局权重、阈值和证据有效期。
- `packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py`：无数据库依赖的评分、分池和主映射选择纯函数。
- `packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py`：模板加载、V2校验和研究覆盖层。
- `packages/kronos-factors/tests/test_supply_chain_selection_v2.py`：纯函数契约测试。
- `tools/materialize_supply_chain_research_v2.py`：八维、路线和传导边物化工具。
- `tools/score_supply_chain_selection_v2.py`：公司映射批量评分和股票池状态迁移工具。
- `tools/register_supply_chain_research_selection_v2.py`：V2 注册和快照工具。
- `tools/backtest_supply_chain_research_selection_v2.py`：分池、分产业和消融回测工具。
- `tools/tests/test_materialize_supply_chain_research_v2.py`
- `tools/tests/test_score_supply_chain_selection_v2.py`
- `tools/tests/test_register_supply_chain_research_selection_v2.py`
- `tools/tests/test_backtest_supply_chain_research_selection_v2.py`
- `services/screener-service/app/domains/supply_chain/selection_repository.py`：V2 查询边界。
- `services/screener-service/app/domains/supply_chain/selection_service.py`：返回结构和限制逻辑。
- `services/screener-service/app/domains/supply_chain/selection_router.py`：V2 HTTP 路由。
- `services/screener-service/tests/test_supply_chain_selection_v2_api.py`
- `docs/qa/supply-chain-research-selection-v2-uat-2026-07-11.md`：真实落库、注册和验证证据。

**修改：**

- `services/screener-service/tests/test_supply_chain_v2_migration_contract.py`
- `packages/kronos-factors/configs/industry_chain_templates.json`
- `packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py`
- `packages/kronos-factors/tests/test_chain_deconstruct.py`
- `services/screener-service/app/domains/supply_chain/router.py`

---

### Task 1: 建立 V2 数据库契约

**Files:**

- Create: `backend/alembic/versions/032_supply_chain_research_selection_v2.py`
- Modify: `services/screener-service/tests/test_supply_chain_v2_migration_contract.py`

**Interfaces:**

- Consumes: Alembic revision `031`；现有 `supply_chain_hierarchy_nodes`、`business_tag_mapping` 和证据表。
- Produces: 9 张 V2 表，供任务 4-9 使用；所有表均为增量新增，不修改 V1 表语义。

- [ ] **Step 1: 写失败的迁移契约测试**

在 `test_supply_chain_v2_migration_contract.py` 增加：

```python
SELECTION_V2_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "backend/alembic/versions/032_supply_chain_research_selection_v2.py"
)


def test_selection_v2_migration_defines_research_and_selection_tables():
    sql = SELECTION_V2_MIGRATION_PATH.read_text(encoding="utf-8")
    required = [
        "supply_chain_node_dimensions",
        "supply_chain_transmission_edges",
        "supply_chain_technology_routes",
        "supply_chain_node_scores",
        "business_tag_authenticity_scores",
        "business_tag_operating_quality_scores",
        "business_tag_benefit_scores",
        "business_tag_selection_scores",
        "business_tag_pool_state",
        "business_tag_pool_transition_log",
    ]
    for table in required:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_selection_v2_migration_preserves_unknown_and_audit_contracts():
    sql = SELECTION_V2_MIGRATION_PATH.read_text(encoding="utf-8")
    required = [
        "score DOUBLE PRECISION",
        "coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0",
        "status IN ('known','estimated','proxy','unknown','contradicted')",
        "evidence_level IN ('E0','E1','E2','E3','E4','E5','E6')",
        "pool_code IN ('A','B','C','D')",
        "model_version TEXT NOT NULL",
        "veto_reasons JSONB NOT NULL DEFAULT '[]'",
        "trigger_evidence_ids JSONB NOT NULL DEFAULT '[]'",
        "review_status TEXT NOT NULL DEFAULT 'pending_review'",
        "uq_screening_snapshots_supply_chain_v2",
        "CREATE TABLE IF NOT EXISTS screening_models",
        "CREATE TABLE IF NOT EXISTS model_versions",
    ]
    for contract in required:
        assert contract in sql
```

- [ ] **Step 2: 运行测试并确认因迁移文件缺失而失败**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q
```

Expected: FAIL，错误包含 `032_supply_chain_research_selection_v2.py` 不存在。

- [ ] **Step 3: 创建迁移并定义完整表约束**

迁移文件使用：

```python
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_node_dimensions (
            dimension_record_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            chain_id TEXT,
            template_id TEXT,
            dimension_id TEXT NOT NULL CHECK (dimension_id IN (
                'function_value','technology_route','physical_bom','value_pool',
                'competition_moat','supply_demand_cycle','evidence_validation','market_expectation'
            )),
            as_of_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'unknown' CHECK (
                status IN ('known','estimated','proxy','unknown','contradicted')
            ),
            score DOUBLE PRECISION CHECK (score IS NULL OR score BETWEEN 0 AND 100),
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (coverage_ratio BETWEEN 0 AND 1),
            confidence_score DOUBLE PRECISION CHECK (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100),
            payload JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (node_id, dimension_id, as_of_date)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_transmission_edges (
            edge_id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL,
            from_node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            to_node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            flow_type TEXT NOT NULL CHECK (flow_type IN ('product_flow','value_flow','technology_flow','data_flow')),
            transmission_logic TEXT NOT NULL,
            transmission_strength DOUBLE PRECISION CHECK (transmission_strength IS NULL OR transmission_strength BETWEEN 0 AND 100),
            transmission_lag_days INTEGER CHECK (transmission_lag_days IS NULL OR transmission_lag_days >= 0),
            failure_conditions JSONB NOT NULL DEFAULT '[]',
            leading_metric_ids JSONB NOT NULL DEFAULT '[]',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (coverage_ratio BETWEEN 0 AND 1),
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chain_id, from_node_id, to_node_id, flow_type)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_technology_routes (
            route_id TEXT PRIMARY KEY,
            chain_id TEXT NOT NULL,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            route_name TEXT NOT NULL,
            maturity_stage TEXT NOT NULL CHECK (maturity_stage IN (
                'concept','prototype','engineering_sample','customer_validation',
                'small_batch','mass_production','mature','declining'
            )),
            performance_metrics JSONB NOT NULL DEFAULT '{}',
            manufacturing_difficulty JSONB NOT NULL DEFAULT '{}',
            cost_trend JSONB NOT NULL DEFAULT '{}',
            substitute_route_ids JSONB NOT NULL DEFAULT '[]',
            failure_conditions JSONB NOT NULL DEFAULT '[]',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            last_strong_evidence_date DATE,
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supply_chain_node_scores (
            score_id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL REFERENCES supply_chain_hierarchy_nodes(node_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            demand_certainty DOUBLE PRECISION,
            value_pool_score DOUBLE PRECISION,
            bottleneck_score DOUBLE PRECISION,
            supply_demand_score DOUBLE PRECISION,
            technology_maturity_score DOUBLE PRECISION,
            commercialization_score DOUBLE PRECISION,
            transmission_score DOUBLE PRECISION,
            evidence_quality_score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (coverage_ratio BETWEEN 0 AND 1),
            score_status TEXT NOT NULL DEFAULT 'insufficient_evidence',
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (node_id, trade_date, model_version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_authenticity_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            evidence_level TEXT NOT NULL CHECK (evidence_level IN ('E0','E1','E2','E3','E4','E5','E6')),
            product_evidence_score DOUBLE PRECISION,
            customer_evidence_score DOUBLE PRECISION,
            order_revenue_evidence_score DOUBLE PRECISION,
            source_reliability_score DOUBLE PRECISION,
            freshness_score DOUBLE PRECISION,
            authenticity_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (coverage_ratio BETWEEN 0 AND 1),
            max_pool_code TEXT CHECK (max_pool_code IN ('A','B','C','D')),
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            score_detail JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_operating_quality_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            growth_score DOUBLE PRECISION,
            profit_score DOUBLE PRECISION,
            moat_score DOUBLE PRECISION,
            total_score DOUBLE PRECISION,
            growth_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            profit_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            moat_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            total_coverage DOUBLE PRECISION NOT NULL DEFAULT 0,
            data_status JSONB NOT NULL DEFAULT '{}',
            cap_hits JSONB NOT NULL DEFAULT '[]',
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_benefit_scores (
            score_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            node_attractiveness DOUBLE PRECISION,
            operating_quality_score DOUBLE PRECISION,
            revenue_exposure_score DOUBLE PRECISION,
            order_certainty_score DOUBLE PRECISION,
            profit_elasticity_score DOUBLE PRECISION,
            delivery_capability_score DOUBLE PRECISION,
            benefit_raw DOUBLE PRECISION,
            authenticity_score DOUBLE PRECISION,
            benefit_score DOUBLE PRECISION,
            coverage_ratio DOUBLE PRECISION NOT NULL DEFAULT 0,
            score_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_selection_scores (
            selection_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            trade_date DATE NOT NULL,
            model_version TEXT NOT NULL,
            benefit_score DOUBLE PRECISION,
            expectation_gap_score DOUBLE PRECISION,
            catalyst_score DOUBLE PRECISION,
            risk_score DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            opportunity_score DOUBLE PRECISION,
            pool_code TEXT CHECK (pool_code IN ('A','B','C','D')),
            eligibility_status TEXT NOT NULL,
            veto_reasons JSONB NOT NULL DEFAULT '[]',
            factor_detail JSONB NOT NULL DEFAULT '{}',
            evidence_ids JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (mapping_id, trade_date, model_version)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_pool_state (
            mapping_id TEXT PRIMARY KEY REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            pool_code TEXT NOT NULL CHECK (pool_code IN ('A','B','C','D')),
            state_status TEXT NOT NULL DEFAULT 'active',
            effective_from DATE NOT NULL,
            next_validation_event TEXT,
            next_validation_date DATE,
            source_selection_id TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS business_tag_pool_transition_log (
            transition_id TEXT PRIMARY KEY,
            mapping_id TEXT NOT NULL REFERENCES business_tag_mapping(mapping_id),
            code TEXT NOT NULL,
            from_pool_code TEXT CHECK (from_pool_code IS NULL OR from_pool_code IN ('A','B','C','D')),
            to_pool_code TEXT CHECK (to_pool_code IS NULL OR to_pool_code IN ('A','B','C','D')),
            transition_date DATE NOT NULL,
            transition_reason TEXT NOT NULL,
            trigger_evidence_ids JSONB NOT NULL DEFAULT '[]',
            review_status TEXT NOT NULL DEFAULT 'pending_review',
            reviewer TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS screening_models (
            id SERIAL PRIMARY KEY,
            model_key VARCHAR NOT NULL UNIQUE,
            display_name VARCHAR NOT NULL,
            category VARCHAR NOT NULL,
            factor_keys VARCHAR[] NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS model_versions (
            id SERIAL PRIMARY KEY,
            model_name VARCHAR NOT NULL,
            version_tag VARCHAR NOT NULL,
            snapshot_count INTEGER NOT NULL DEFAULT 0,
            win_rate DOUBLE PRECISION,
            mean_return DOUBLE PRECISION,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (model_name, version_tag)
        )
    """)
    score_columns = {
        "supply_chain_node_scores": [
            "demand_certainty", "value_pool_score", "bottleneck_score",
            "supply_demand_score", "technology_maturity_score",
            "commercialization_score", "transmission_score",
            "evidence_quality_score", "total_score",
        ],
        "business_tag_authenticity_scores": [
            "product_evidence_score", "customer_evidence_score",
            "order_revenue_evidence_score", "source_reliability_score",
            "freshness_score", "authenticity_score",
        ],
        "business_tag_operating_quality_scores": [
            "growth_score", "profit_score", "moat_score", "total_score",
        ],
        "business_tag_benefit_scores": [
            "node_attractiveness", "operating_quality_score",
            "revenue_exposure_score", "order_certainty_score",
            "profit_elasticity_score", "delivery_capability_score",
            "benefit_raw", "authenticity_score", "benefit_score",
        ],
        "business_tag_selection_scores": [
            "benefit_score", "expectation_gap_score", "catalyst_score",
            "risk_score", "confidence_score", "opportunity_score",
        ],
    }
    for table_name, columns in score_columns.items():
        for index, column_name in enumerate(columns):
            op.execute(
                f"ALTER TABLE {table_name} ADD CONSTRAINT ck_{table_name[:18]}_{index}_0_100 "
                f"CHECK ({column_name} IS NULL OR {column_name} BETWEEN 0 AND 100)"
            )
    coverage_columns = {
        "business_tag_operating_quality_scores": [
            "growth_coverage", "profit_coverage", "moat_coverage", "total_coverage",
        ],
        "business_tag_benefit_scores": ["coverage_ratio"],
    }
    for table_name, columns in coverage_columns.items():
        for index, column_name in enumerate(columns):
            op.execute(
                f"ALTER TABLE {table_name} ADD CONSTRAINT ck_{table_name[:18]}_cov_{index} "
                f"CHECK ({column_name} BETWEEN 0 AND 1)"
            )
    for statement in [
        "CREATE INDEX IF NOT EXISTS idx_node_dimensions_lookup ON supply_chain_node_dimensions(node_id, as_of_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_transmission_edges_chain ON supply_chain_transmission_edges(chain_id, flow_type)",
        "CREATE INDEX IF NOT EXISTS idx_node_scores_date ON supply_chain_node_scores(trade_date, total_score DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS idx_selection_scores_pool ON business_tag_selection_scores(trade_date, model_version, pool_code, opportunity_score DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS idx_pool_transition_mapping ON business_tag_pool_transition_log(mapping_id, transition_date DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_screening_snapshots_supply_chain_v2 ON screening_snapshots(model_key, trade_date, stock_code, COALESCE(time_slot, '')) WHERE model_key = 'supply_chain_research_selection_v2'",
    ]:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_screening_snapshots_supply_chain_v2")
    for table in [
        "business_tag_pool_transition_log", "business_tag_pool_state",
        "business_tag_selection_scores", "business_tag_benefit_scores",
        "business_tag_operating_quality_scores", "business_tag_authenticity_scores",
        "supply_chain_node_scores", "supply_chain_technology_routes",
        "supply_chain_transmission_edges", "supply_chain_node_dimensions",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table}")
```

`screening_models` 和 `model_versions` 是既有跨模型兼容表，即使本迁移在空数据库中补建，downgrade 也不删除；只撤销V2部分唯一索引和10张V2业务表，避免破坏其他已注册模型。

- [ ] **Step 4: 运行迁移契约测试**

Run:

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q
```

Expected: PASS。

- [ ] **Step 5: 提交数据库契约**

```bash
git add backend/alembic/versions/032_supply_chain_research_selection_v2.py services/screener-service/tests/test_supply_chain_v2_migration_contract.py
git commit -m "feat: add supply-chain selection v2 schema"
```

---

### Task 2: 实现无数据库依赖的评分与分池内核

**Files:**

- Create: `packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py`
- Create: `packages/kronos-factors/tests/test_supply_chain_selection_v2.py`

**Interfaces:**

- Consumes: 0-100 子分、`None` 缺失值、设计文档固定权重和 E0-E6 证据等级。
- Produces: `ScoreResult`、`score_node_attractiveness`、`score_operating_quality`、`score_authenticity`、`score_company_benefit`、`score_selection_opportunity`、`assign_selection_pool`、`aggregate_stock_mappings`。

- [ ] **Step 1: 写评分和缺失语义的失败测试**

```python
from kronos_factors.scorer.supply_chain_selection_v2 import (
    ScoreResult,
    aggregate_stock_mappings,
    assign_selection_pool,
    score_authenticity,
    score_company_benefit,
    score_node_attractiveness,
    score_operating_quality,
    score_selection_opportunity,
)


def test_weighted_scores_keep_unknown_as_none():
    result = score_node_attractiveness({
        "demand_certainty": None,
        "value_pool_score": None,
        "bottleneck_score": None,
        "supply_demand_score": None,
        "technology_maturity_score": None,
        "commercialization_score": None,
        "transmission_score": None,
        "evidence_quality_score": None,
    })
    assert result == ScoreResult(score=None, coverage_ratio=0.0, detail={"status": "unknown"})


def test_authenticity_is_a_multiplier_not_an_additive_bonus():
    benefit = score_company_benefit(
        {
            "node_attractiveness": 80,
            "operating_quality_score": 80,
            "revenue_exposure_score": 80,
            "order_certainty_score": 80,
            "profit_elasticity_score": 80,
            "delivery_capability_score": 80,
        },
        authenticity_score=50,
    )
    assert benefit.score == 40.0


def test_growth_caps_only_expansion_without_orders_at_55():
    result = score_operating_quality(
        growth={
            "realized_revenue_growth": None,
            "backlog_growth": None,
            "customer_share_growth": None,
            "delivery_growth": 90,
            "growth_sustainability": None,
        },
        profit={},
        moat={},
        growth_cap=55,
    )
    assert result.detail["growth_score"] == 55.0
    assert "growth_cap:55" in result.detail["cap_hits"]


def test_pool_assignment_uses_hard_evidence_gates():
    base = {
        "commercial_stage": "C4",
        "authenticity_score": 80,
        "confidence_score": 75,
        "benefit_score": 70,
        "operating_quality_coverage": 0.8,
        "has_veto": False,
        "has_order_or_delivery_evidence": True,
        "has_product_evidence": True,
        "has_customer_validation": True,
    }
    assert assign_selection_pool({**base, "evidence_level": "E4"})["pool_code"] == "A"
    assert assign_selection_pool({**base, "evidence_level": "E3"})["pool_code"] == "B"
    assert assign_selection_pool({**base, "evidence_level": "E2", "has_customer_validation": False})["pool_code"] == "C"
    assert assign_selection_pool({**base, "evidence_level": "E1", "has_product_evidence": False})["pool_code"] == "D"


def test_multiple_mappings_do_not_stack_scores():
    selected = aggregate_stock_mappings([
        {"code": "000001", "mapping_id": "m1", "benefit_score": 72, "evidence_level": "E4", "independent_revenue": True},
        {"code": "000001", "mapping_id": "m2", "benefit_score": 65, "evidence_level": "E3", "independent_revenue": True},
        {"code": "000001", "mapping_id": "m3", "benefit_score": 60, "evidence_level": "E2", "independent_revenue": False},
    ])[0]
    assert selected["primary_mapping_id"] == "m1"
    assert selected["diversification_bonus"] == 5.0
    assert selected["stock_score"] == 77.0
```

- [ ] **Step 2: 运行测试并确认导入失败**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py -q
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现统一的缺失值聚合器和固定公式**

核心实现必须包含以下签名和行为：

```python
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ScoreResult:
    score: float | None
    coverage_ratio: float
    detail: dict


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 4)


def weighted_available_score(values: Mapping[str, float | None], weights: Mapping[str, float]) -> ScoreResult:
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1.0")
    known = {key: float(values[key]) for key in weights if values.get(key) is not None}
    if not known:
        return ScoreResult(None, 0.0, {"status": "unknown"})
    for key, value in known.items():
        if value < 0 or value > 100:
            raise ValueError(f"{key} must be between 0 and 100")
    known_weight = sum(weights[key] for key in known)
    score = sum(known[key] * weights[key] for key in known) / known_weight
    return ScoreResult(_clamp(score), round(known_weight, 4), {"known_fields": sorted(known)})


NODE_WEIGHTS = {
    "demand_certainty": 0.20,
    "value_pool_score": 0.15,
    "bottleneck_score": 0.15,
    "supply_demand_score": 0.15,
    "technology_maturity_score": 0.10,
    "commercialization_score": 0.10,
    "transmission_score": 0.10,
    "evidence_quality_score": 0.05,
}

BENEFIT_WEIGHTS = {
    "node_attractiveness": 0.20,
    "operating_quality_score": 0.20,
    "revenue_exposure_score": 0.20,
    "order_certainty_score": 0.15,
    "profit_elasticity_score": 0.15,
    "delivery_capability_score": 0.10,
}


def score_node_attractiveness(values: Mapping[str, float | None]) -> ScoreResult:
    return weighted_available_score(values, NODE_WEIGHTS)


def score_authenticity(values: Mapping[str, float | None]) -> ScoreResult:
    return weighted_available_score(values, {
        "product_evidence_score": 0.30,
        "customer_evidence_score": 0.25,
        "order_revenue_evidence_score": 0.25,
        "source_reliability_score": 0.10,
        "freshness_score": 0.10,
    })


def score_company_benefit(values: Mapping[str, float | None], *, authenticity_score: float | None,
                          profile: Mapping | None = None) -> ScoreResult:
    raw = weighted_available_score(values, BENEFIT_WEIGHTS)
    if raw.score is None or authenticity_score is None:
        if authenticity_score is None:
            return ScoreResult(None, raw.coverage_ratio, {**raw.detail, "status": "unknown_authenticity"})
        return raw
    return ScoreResult(
        score=_clamp(raw.score * authenticity_score / 100.0),
        coverage_ratio=raw.coverage_ratio,
        detail={**raw.detail, "benefit_raw": raw.score, "authenticity_score": authenticity_score},
    )


def score_selection_opportunity(inputs: Mapping[str, float | None],
                                profile: Mapping | None = None) -> ScoreResult:
    required = ("benefit_score", "expectation_gap_score", "catalyst_score", "risk_score")
    known = [key for key in required if inputs.get(key) is not None]
    if len(known) != len(required):
        return ScoreResult(None, len(known) / len(required), {"status": "insufficient_evidence", "known_fields": known})
    score = _clamp(
        inputs["benefit_score"] * 0.55
        + inputs["expectation_gap_score"] * 0.30
        + inputs["catalyst_score"] * 0.15
        - inputs["risk_score"] * 0.30
    )
    return ScoreResult(score, 1.0, {"status": "ready"})
```

`score_operating_quality` 必须分别调用 `weighted_available_score` 计算增长、盈利、围墙，并应用设计中的数据上限；`assign_selection_pool` 必须按 A→B→C→D 顺序检查全部硬条件并返回包含 `pool_code`、`eligibility_status`、`veto_reasons` 的字典；`aggregate_stock_mappings` 按股票分组，使用证据等级顺序 `E6>E5>E4>E3>E2>E1>E0` 和 `benefit_score` 选择主映射，独立收入映射每条加 2.5 分、总上限 5 分。

- [ ] **Step 4: 补充边界测试**

增加并通过：权重不为1抛错、分数越界抛错、否决项不得进入A/B/C、E0返回排除状态、利润子项全部未知时不把盈利分写成0。

- [ ] **Step 5: 运行纯函数测试**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交评分内核**

```bash
git add packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py packages/kronos-factors/tests/test_supply_chain_selection_v2.py
git commit -m "feat: add supply-chain selection v2 scoring core"
```

---

### Task 3: 增加 V2 配置、模板校验与灵巧手八层案例

**Files:**

- Create: `packages/kronos-factors/configs/industry_chain_selection_v2.json`
- Create: `packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py`
- Modify: `packages/kronos-factors/configs/industry_chain_templates.json`
- Modify: `packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py`
- Modify: `packages/kronos-factors/tests/test_chain_deconstruct.py`

**Interfaces:**

- Consumes: 现有 `industry_chain_templates.json` 和任务2的固定评分字段。
- Produces: `load_template_catalog()`、`get_industry_template()`、`load_selection_v2_profile()`、`validate_selection_v2_profile()`、模板 `dexterous_hand`、API树中的 V2 可选字段。

- [ ] **Step 1: 写配置与灵巧手模板失败测试**

```python
from kronos_factors.engine.industry_chain_templates import (
    load_template_catalog,
    load_selection_v2_profile,
    validate_selection_v2_profile,
)


def test_selection_v2_profile_weights_and_pool_thresholds():
    profile = load_selection_v2_profile()
    validate_selection_v2_profile(profile)
    assert sum(profile["weights"]["node"].values()) == 1.0
    assert sum(profile["weights"]["benefit"].values()) == 1.0
    assert profile["pool_thresholds"]["A"]["min_evidence_level"] == "E4"
    assert profile["evidence_expiry_days"]["customer_sample"] == 180


def test_dexterous_hand_template_has_eight_layers_and_axial_flux_route():
    config = load_template_catalog()
    template = next(t for t in config["templates"] if t["template_id"] == "dexterous_hand")
    assert [layer["layer_id"] for layer in template["layers"]] == [
        "demand", "task", "core_product", "foundation",
        "integration", "supporting", "infrastructure", "commercialization",
    ]
    axial = next(route for route in template["technology_routes"] if route["route_id"] == "dexterous_axial_flux_motor")
    assert axial["node_id"] == "dexterous_hand_foundation"
    assert axial["authenticity_ladder"]["AF4"]["max_pool"] == "B"
    assert axial["authenticity_ladder"]["AF5"]["max_pool"] == "A"
```

- [ ] **Step 2: 运行测试并确认缺少加载器和模板**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_chain_deconstruct.py -q
```

Expected: FAIL，缺少 `load_selection_v2_profile` 或 `dexterous_hand`。

- [ ] **Step 3: 创建全局选择配置**

`industry_chain_selection_v2.json` 必须包含：

```json
{
  "version": "v2.0",
  "model_key": "supply_chain_research_selection_v2",
  "dimensions": [
    "function_value", "technology_route", "physical_bom", "value_pool",
    "competition_moat", "supply_demand_cycle", "evidence_validation", "market_expectation"
  ],
  "flow_types": ["product_flow", "value_flow", "technology_flow", "data_flow"],
  "weights": {
    "node": {
      "demand_certainty": 0.20, "value_pool_score": 0.15,
      "bottleneck_score": 0.15, "supply_demand_score": 0.15,
      "technology_maturity_score": 0.10, "commercialization_score": 0.10,
      "transmission_score": 0.10, "evidence_quality_score": 0.05
    },
    "benefit": {
      "node_attractiveness": 0.20, "operating_quality_score": 0.20,
      "revenue_exposure_score": 0.20, "order_certainty_score": 0.15,
      "profit_elasticity_score": 0.15, "delivery_capability_score": 0.10
    },
    "opportunity": {
      "benefit_score": 0.55, "expectation_gap_score": 0.30, "catalyst_score": 0.15
    },
    "risk_penalty": 0.30
  },
  "pool_thresholds": {
    "A": {"min_evidence_level": "E4", "min_commercial_stage": "C4", "min_authenticity": 75, "min_confidence": 70, "min_benefit": 60, "min_operating_coverage": 0.60},
    "B": {"min_evidence_level": "E3", "min_authenticity": 60, "requires_next_validation": true},
    "C": {"min_evidence_level": "E2", "requires_product": true},
    "D": {"min_evidence_level": "E1"}
  },
  "evidence_expiry_days": {
    "customer_sample": 180, "customer_test": 180, "nomination": 365,
    "interactive_answer": 90, "financial_revenue": 180
  },
  "diversification_bonus_per_mapping": 2.5,
  "diversification_bonus_cap": 5.0
}
```

- [ ] **Step 4: 增加灵巧手模板的精确八层和路线**

在 `templates` 中增加 `template_id=dexterous_hand`，八层 `segments` 固定为：

```python
{
    "demand": ["制造业柔性自动化", "具身智能", "危险作业", "仓储物流", "商业服务", "家庭服务"],
    "task": ["抓取", "捏取", "旋拧", "插接", "工具操作", "手内操作", "遥操作"],
    "core_product": ["五指灵巧手", "工业灵巧末端", "仿生手", "遥操作手", "灵巧手开发平台"],
    "foundation": ["空心杯电机", "无框力矩电机", "轴向磁通电机", "微型丝杠", "微型减速器", "腱绳", "触觉传感器", "编码器", "驱动芯片"],
    "integration": ["旋转执行器", "直线执行器", "掌内腱绳执行器", "手指模组", "整手机电集成", "手眼力控系统"],
    "supporting": ["钕铁硼磁材", "铜线", "软磁材料", "微型轴承", "工程塑料", "柔性电路", "连接器", "加工检测设备"],
    "infrastructure": ["遥操作平台", "数据采集", "仿真训练", "测试评价", "可靠性实验室", "自动化产线", "维修网络"],
    "commercialization": ["整手销售", "机器人配套", "执行器外售", "RaaS", "操作数据服务", "指尖耗材", "维护升级"]
}
```

技术路线至少包含空心杯+丝杠、无框低减速比、轴向磁通+掌内/腕部、腱绳、连杆、差动欠驱动、压阻/电容/磁式/光学触觉。轴向磁通路线必须明确 AF0-AF6、安装位置、持续转矩、峰值转矩、温升、直径、厚度和装机证据为验证字段，未有数据时保存 `unknown/null`。

轴向磁通路线的 `authenticity_ladder` 精确定义为：

```json
{
  "AF0": {"meaning": "只有轴向磁通技术概念", "max_pool": null},
  "AF1": {"meaning": "专利或实验室样机", "max_pool": "D"},
  "AF2": {"meaning": "机器人规格产品和参数", "max_pool": "C"},
  "AF3": {"meaning": "装入关节、腕部或灵巧手样机", "max_pool": "C"},
  "AF4": {"meaning": "机器人客户送样、定点或联合验证", "max_pool": "B"},
  "AF5": {"meaning": "小批量交付", "max_pool": "A"},
  "AF6": {"meaning": "形成可识别收入和订单", "max_pool": "A"}
}
```

模板同时增加候选映射规则，但不硬编码“已进入灵巧手供应链”的结论：

```json
{
  "candidate_mapping_rules": {
    "source_chain_ids": ["embodied_intelligence"],
    "required_business_keywords": [
      "灵巧手", "微型执行器", "空心杯电机", "无框电机", "轴向磁通电机",
      "微型丝杠", "触觉传感器", "力传感器", "腱绳", "机器人末端"
    ],
    "derived_status": "candidate",
    "derived_confidence_cap": 0.35,
    "requires_original_evidence": true
  }
}
```

该规则只生成待复核候选，不能复制源产业链分数、阶段或股票池等级；没有明确灵巧手原文证据时最高为E1/D池。

- [ ] **Step 5: 实现配置加载和权重校验**

在新建的 `industry_chain_templates.py` 增加，并让 `chain_deconstruct.py` 导入兼容：

```python
SELECTION_V2_CONFIG_NAME = "industry_chain_selection_v2.json"


def _config_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "configs"


def load_template_catalog(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else _config_dir() / "industry_chain_templates.json"
    return json.loads(target.read_text(encoding="utf-8"))


def get_industry_template(template_id: str, *, path: str | Path | None = None) -> dict[str, Any]:
    for template in load_template_catalog(path).get("templates", []):
        if template.get("template_id") == template_id:
            return template
    raise ValueError(f"unknown industry template: {template_id}")


def load_selection_v2_profile(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else _config_dir() / SELECTION_V2_CONFIG_NAME
    return json.loads(target.read_text(encoding="utf-8"))


def validate_selection_v2_profile(profile: dict[str, Any]) -> None:
    for group in ("node", "benefit", "opportunity"):
        total = sum(float(v) for v in profile["weights"][group].values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights.{group} must sum to 1.0, got {total}")
    if profile["dimensions"] != [
        "function_value", "technology_route", "physical_bom", "value_pool",
        "competition_moat", "supply_demand_cycle", "evidence_validation", "market_expectation",
    ]:
        raise ValueError("selection v2 dimensions are invalid")
```

`build_industry_template_tree()` 只在模板存在 V2 字段时附加 `research_dimensions`、`technology_routes`、`transmission_edges`；旧模板响应不改变。

- [ ] **Step 6: 运行模板与原有回归测试**

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_chain_deconstruct.py -q
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py -q
```

Expected: PASS，现有18条模板测试不退化。

- [ ] **Step 7: 提交配置与模板**

```bash
git add packages/kronos-factors/configs/industry_chain_selection_v2.json packages/kronos-factors/configs/industry_chain_templates.json packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py packages/kronos-factors/tests/test_chain_deconstruct.py
git commit -m "feat: add dexterous-hand research template"
```

---

### Task 4: 物化八维、技术路线、传导边和节点吸引力

**Files:**

- Create: `tools/materialize_supply_chain_research_v2.py`
- Create: `tools/tests/test_materialize_supply_chain_research_v2.py`

**Interfaces:**

- Consumes: `get_industry_template(template_id)`、`industry_chain_selection_v2.json`、任务1的四张节点研究表。
- Produces: `build_research_rows(template, as_of_date)`、`derive_candidate_mappings(cur, template)` 和 `materialize(pg_url, template_id, as_of_date, dry_run)`；先补齐 `supply_chain_hierarchy_nodes`，再写路线、传导边、维度、节点分和待复核候选映射。

- [ ] **Step 1: 写失败的物化载荷测试**

```python
from datetime import date

from materialize_supply_chain_research_v2 import build_research_rows


def test_build_research_rows_keeps_unknown_dimensions_nullable():
    template = {
        "template_id": "demo",
        "layers": [{
            "layer_id": "demand", "order": 1, "name": "需求层",
            "definition": "真实需求", "segments": ["工业"],
            "research_dimensions": {
                "function_value": {"status": "known", "score": 80, "evidence_ids": ["ev1"]}
            },
        }],
        "technology_routes": [],
        "transmission_edges": [],
    }
    rows = build_research_rows(template, date(2026, 7, 11))
    assert len(rows["dimensions"]) == 8
    missing = next(r for r in rows["dimensions"] if r["dimension_id"] == "value_pool")
    assert missing["status"] == "unknown"
    assert missing["score"] is None
    assert missing["coverage_ratio"] == 0.0


def test_axial_flux_route_is_not_promoted_without_evidence():
    template = {
        "template_id": "dexterous_hand",
        "layers": [{"layer_id": "foundation", "order": 4, "name": "底层支撑层", "segments": []}],
        "technology_routes": [{
            "route_id": "dexterous_axial_flux_motor",
            "node_id": "dexterous_hand_foundation",
            "route_name": "轴向磁通电机",
            "maturity_stage": "concept",
            "evidence_ids": [],
        }],
        "transmission_edges": [],
    }
    rows = build_research_rows(template, date(2026, 7, 11))
    route = rows["routes"][0]
    assert route["maturity_stage"] == "concept"
    assert route["review_status"] == "pending_review"
    assert route["last_strong_evidence_date"] is None


def test_derived_mapping_is_capped_as_candidate_without_original_evidence():
    row = build_derived_mapping(
        template_id="dexterous_hand",
        source={
            "mapping_id": "source-m1", "code": "000001",
            "business_segment_id": "seg1", "tag_name": "空心杯电机",
            "evidence_ids": [],
        },
        matched_keyword="空心杯电机",
    )
    assert row["status"] == "candidate"
    assert row["confidence"] == 0.35
    assert row["evidence_ids"] == []
    assert row["l1_l8_path"][-1]["requires_original_evidence"] is True
```

- [ ] **Step 2: 运行测试并确认工具文件缺失**

```bash
bash tools/codex-lowio.sh py tools/tests/test_materialize_supply_chain_research_v2.py -q
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现确定性载荷生成**

工具公开接口和标识生成规则：

```python
import hashlib


DIMENSIONS = (
    "function_value", "technology_route", "physical_bom", "value_pool",
    "competition_moat", "supply_demand_cycle", "evidence_validation", "market_expectation",
)


def layer_node_id(template_id: str, layer_id: str) -> str:
    return f"{template_id}_{layer_id}"


def build_research_rows(template: dict, as_of_date: date) -> dict[str, list[dict]]:
    dimensions, routes, edges, nodes = [], [], [], []
    for layer in sorted(template["layers"], key=lambda item: int(item["order"])):
        node_id = layer_node_id(template["template_id"], layer["layer_id"])
        nodes.append({
            "node_id": node_id,
            "parent_node_id": None,
            "layer_level": f"L{int(layer['order'])}",
            "layer_name": layer["name"],
            "display_name": layer["name"],
            "chain_id": template["template_id"],
            "source_table": "industry_chain_templates",
            "source_id": f"{template['template_id']}:{layer['layer_id']}",
            "keywords": layer.get("segments", []),
        })
        configured = layer.get("research_dimensions", {})
        for dimension_id in DIMENSIONS:
            item = configured.get(dimension_id, {})
            dimensions.append({
                "dimension_record_id": f"{node_id}:{dimension_id}:{as_of_date.isoformat()}",
                "node_id": node_id,
                "chain_id": template["template_id"],
                "template_id": template["template_id"],
                "dimension_id": dimension_id,
                "as_of_date": as_of_date,
                "status": item.get("status", "unknown"),
                "score": item.get("score"),
                "coverage_ratio": float(item.get("coverage_ratio", 0.0)),
                "confidence_score": item.get("confidence_score"),
                "payload": item.get("payload", {}),
                "evidence_ids": item.get("evidence_ids", []),
                "review_status": item.get("review_status", "pending_review"),
            })
    for index, node in enumerate(nodes):
        node["parent_node_id"] = nodes[index - 1]["node_id"] if index else None
    for route in template.get("technology_routes", []):
        routes.append({
            **route,
            "performance_metrics": route.get("performance_metrics", {}),
            "manufacturing_difficulty": route.get("manufacturing_difficulty", {}),
            "cost_trend": route.get("cost_trend", {}),
            "substitute_route_ids": route.get("substitute_route_ids", []),
            "failure_conditions": route.get("failure_conditions", []),
            "evidence_ids": route.get("evidence_ids", []),
            "last_strong_evidence_date": route.get("last_strong_evidence_date"),
            "review_status": route.get("review_status", "pending_review"),
        })
    for edge in template.get("transmission_edges", []):
        edges.append({
            **edge,
            "transmission_strength": edge.get("transmission_strength"),
            "transmission_lag_days": edge.get("transmission_lag_days"),
            "coverage_ratio": float(edge.get("coverage_ratio", 0.0)),
            "review_status": edge.get("review_status", "pending_review"),
        })
    return {"nodes": nodes, "dimensions": dimensions, "routes": routes, "edges": edges}


def build_derived_mapping(*, template_id: str, source: dict, matched_keyword: str) -> dict:
    mapping_id = f"DEXH-{source['code']}-{hashlib.sha1(matched_keyword.encode()).hexdigest()[:10]}"
    return {
        "mapping_id": mapping_id,
        "code": source["code"],
        "business_segment_id": source.get("business_segment_id"),
        "node_id": f"{template_id}_foundation",
        "theme_id": "future_industry_dexterous_hand",
        "chain_id": template_id,
        "tag_name": matched_keyword,
        "l1_l8_path": [{
            "level": "provenance",
            "derived_from_mapping_id": source["mapping_id"],
            "requires_original_evidence": True,
        }],
        "revenue_ratio": None,
        "gross_profit_ratio": None,
        "confidence": 0.35,
        "status": "candidate",
        "evidence_ids": [],
    }
```

- [ ] **Step 4: 实现单事务物化与 dry-run**

`materialize()` 必须：

1. 校验模板、八层、八维和权重；
2. `dry_run=True` 时只返回 `planned` 计数和载荷摘要，不连接数据库；
3. 写入时依次 upsert `supply_chain_hierarchy_nodes`、`supply_chain_technology_routes`、`supply_chain_transmission_edges`、`supply_chain_node_dimensions`；
4. 仅当节点分所需证据覆盖满足规则时写正式 `total_score`，否则写 `NULL` 和 `insufficient_evidence`；
5. 根据 `candidate_mapping_rules` 从现有映射中筛候选，生成 `status=candidate`、`confidence<=0.35` 的 `business_tag_mapping`；不复制源评分和阶段；
6. 所有 JSON 使用 `psycopg2.extras.Json`，全部操作在一个连接事务内。

CLI：

```python
parser.add_argument("--template-id", required=True)
parser.add_argument("--as-of-date", required=True)
parser.add_argument("--pg-url", default=DEFAULT_DSN)
parser.add_argument("--dry-run", action="store_true")
```

- [ ] **Step 5: 运行物化工具测试和模板回归**

```bash
bash tools/codex-lowio.sh py tools/tests/test_materialize_supply_chain_research_v2.py -q
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_chain_deconstruct.py -q
```

Expected: PASS。

- [ ] **Step 6: 提交研究层物化工具**

```bash
git add tools/materialize_supply_chain_research_v2.py tools/tests/test_materialize_supply_chain_research_v2.py
git commit -m "feat: materialize supply-chain research dimensions"
```

---

### Task 5: 实现公司真实性、三高V2、受益度和股票池落库

**Files:**

- Create: `services/screener-service/app/domains/supply_chain/selection_repository.py`
- Create: `tools/score_supply_chain_selection_v2.py`
- Create: `tools/tests/test_score_supply_chain_selection_v2.py`

**Interfaces:**

- Consumes: 任务2纯函数、任务1评分表、现有 `business_tag_mapping`、阶段、证据、分部收入、新鲜度和预期监控。
- Produces: `SelectionRepository`、`build_mapping_inputs()`、`score_mapping()`、`run_batch_score()`；保存 mapping 级分数和股票池迁移。

- [ ] **Step 1: 写 as-of 数据和分池迁移失败测试**

```python
from datetime import date, datetime, timezone

from score_supply_chain_selection_v2 import score_mapping


def test_score_mapping_ignores_evidence_after_trade_date():
    mapping = {"mapping_id": "m1", "code": "000001", "commercialization_stage": "C4"}
    evidence = [
        {"event_id": "old", "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc), "fact_type": "order", "validation_status": "confirmed", "source_level": "strong"},
        {"event_id": "future", "publish_time": datetime(2026, 7, 12, tzinfo=timezone.utc), "fact_type": "revenue", "validation_status": "confirmed", "source_level": "strong"},
    ]
    result = score_mapping(mapping, evidence, trade_date=date(2026, 7, 11), node_score=70)
    assert "old" in result["evidence_ids"]
    assert "future" not in result["evidence_ids"]
    assert result["authenticity"]["evidence_level"] == "E4"


def test_score_mapping_never_promotes_pending_review_evidence():
    mapping = {"mapping_id": "m1", "code": "000001", "commercialization_stage": "C2"}
    evidence = [{
        "event_id": "pending", "publish_time": datetime(2026, 7, 10, tzinfo=timezone.utc),
        "fact_type": "order", "validation_status": "pending", "source_level": "strong",
    }]
    result = score_mapping(mapping, evidence, trade_date=date(2026, 7, 11), node_score=70)
    assert result["authenticity"]["evidence_level"] in {"E0", "E1"}
    assert result["selection"]["pool_code"] in {None, "D"}
```

- [ ] **Step 2: 运行测试并确认工具缺失**

```bash
bash tools/codex-lowio.sh py tools/tests/test_score_supply_chain_selection_v2.py -q
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现只读仓储边界**

`selection_repository.py` 定义 `SelectionRepository`，其中 `REQUIRED_TABLES` 固定包含 `business_tag_mapping`、两张证据表、阶段表、新鲜度表、节点分表、四张公司评分表和股票池状态表。本步骤完整实现以下公开方法：`preflight(cur) -> list[str]`、`fetch_mappings(cur, chain_id, mapping_ids) -> list[dict]`、`fetch_asof_evidence(cur, mapping_id, cutoff) -> list[dict]`、`fetch_asof_stage(cur, mapping_id, trade_date) -> dict | None`、`fetch_node_score(cur, node_id, trade_date, model_version) -> dict | None`、`upsert_score_bundle(cur, bundle) -> None`、`transition_pool(cur, bundle) -> bool`。

实现中不能保留省略号；SQL必须使用参数绑定。`fetch_asof_evidence` 过滤：

```sql
WHERE mapping_id = %s
  AND publish_time <= %s
  AND validation_status IN ('confirmed','pending','contradicted','expired','rejected')
ORDER BY publish_time DESC, fact_id
```

如果事实表没有 `publish_time`，通过 `raw_evidence_documents.doc_id` 联表读取；不得使用 `crawl_time` 替代发布日期。

- [ ] **Step 4: 实现 mapping 级评分编排**

`score_mapping()`：

```python
from dataclasses import asdict


def score_mapping(mapping: dict, evidence: list[dict], *, trade_date: date,
                  node_score: float | None, profile: dict | None = None) -> dict:
    cutoff = datetime.combine(trade_date, time.max, tzinfo=timezone.utc)
    usable = [e for e in evidence if e.get("publish_time") and e["publish_time"] <= cutoff]
    confirmed = [e for e in usable if e.get("validation_status") == "confirmed"]
    evidence_level = derive_evidence_level(mapping, confirmed)
    authenticity = score_authenticity(build_authenticity_inputs(confirmed))
    operating = score_operating_quality(
        build_growth_inputs(mapping, confirmed),
        build_profit_inputs(mapping, confirmed),
        build_moat_inputs(mapping, confirmed),
        profile or load_selection_profile(),
    )
    benefit = score_company_benefit(
        build_benefit_inputs(mapping, confirmed, node_score, operating.score),
        authenticity_score=authenticity.score,
        profile=profile or load_selection_profile(),
    )
    selection = score_selection_opportunity(
        build_selection_inputs(mapping, confirmed, benefit.score),
        profile=profile or load_selection_profile(),
    )
    pool = assign_selection_pool(
        build_pool_inputs(
            mapping, confirmed, evidence_level,
            authenticity.score, operating.coverage_ratio, benefit.score, selection.score,
        ),
        profile or load_selection_profile(),
    )
    return {
        "mapping_id": mapping["mapping_id"], "code": mapping["code"],
        "trade_date": trade_date, "model_version": "v2.0",
        "authenticity": {**asdict(authenticity), "evidence_level": evidence_level},
        "operating_quality": asdict(operating), "benefit": asdict(benefit),
        "selection": {**asdict(selection), "opportunity_score": selection.score, **pool},
        "evidence_ids": sorted({e["event_id"] for e in confirmed if e.get("event_id")}),
    }
```

其中 `derive_evidence_level(mapping, confirmed)` 只认已确认事实：产品 E2、客户验证 E3、定点/订单/小批量 E4、财报收入 E5、利润贡献 E6；具有明确业务关键词但尚无原始证据的派生候选为 E1；纯传闻为 E0。

- [ ] **Step 5: 实现批量事务、状态迁移和 dry-run**

`run_batch_score()` 必须：

- 明确要求 `trade_date`；
- preflight 缺表时抛出列出全部缺表的错误；
- `dry_run` 返回分池数量和每个映射的限制，不写数据库；
- 真实写入时依次 upsert 四张评分表；
- 只有池变化时写 `business_tag_pool_transition_log`；
- 自动计算只能写 `review_status=pending_review`，不能冒充人工批准；
- 同事务失败全部回滚。

- [ ] **Step 6: 运行评分工具测试**

```bash
bash tools/codex-lowio.sh py tools/tests/test_score_supply_chain_selection_v2.py -q
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交评分落库工具**

```bash
git add services/screener-service/app/domains/supply_chain/selection_repository.py tools/score_supply_chain_selection_v2.py tools/tests/test_score_supply_chain_selection_v2.py
git commit -m "feat: score supply-chain mappings into evidence pools"
```

---

### Task 6: 提供V2候选、公司解释和批量评分API

**Files:**

- Create: `services/screener-service/app/domains/supply_chain/models.py`
- Create: `services/screener-service/app/domains/supply_chain/selection_service.py`
- Create: `services/screener-service/app/domains/supply_chain/selection_router.py`
- Modify: `services/screener-service/app/domains/supply_chain/router.py`
- Create: `services/screener-service/tests/test_supply_chain_selection_v2_api.py`

**Interfaces:**

- Consumes: 任务5 `SelectionRepository` 和已落库分数；现有 supply-chain domain router。
- Produces: 三个新API；旧 `/api/v1/screener/chain/deconstruct` 保持不变。

- [ ] **Step 1: 写API失败测试**

```python
def test_candidates_return_primary_mapping_and_five_scores(client, monkeypatch):
    monkeypatch.setattr(
        "app.domains.supply_chain.selection_service.list_selection_candidates",
        lambda **kwargs: {
            "trade_date": "2026-07-11", "chain_id": "dexterous_hand",
            "model_version": "v2.0", "items": [{
                "code": "000001", "pool_code": "A", "primary_mapping_id": "m1",
                "secondary_mappings": [], "benefit_score": 70,
                "expectation_gap_score": 60, "risk_score": 20,
                "confidence_score": 80, "opportunity_score": 60.5,
                "evidence_level": "E4", "data_limitations": [],
            }], "data_limitations": [],
        },
    )
    response = client.get(
        "/api/v1/supply-chain/selection/candidates",
        params={"chain_id": "dexterous_hand", "trade_date": "2026-07-11", "pool": "A"},
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["primary_mapping_id"] == "m1"


def test_candidates_missing_tables_returns_503_with_table_names(client, monkeypatch):
    def fail(**kwargs):
        raise MissingSelectionTables(["business_tag_selection_scores"])
    monkeypatch.setattr("app.domains.supply_chain.selection_service.list_selection_candidates", fail)
    response = client.get(
        "/api/v1/supply-chain/selection/candidates",
        params={"chain_id": "dexterous_hand", "trade_date": "2026-07-11"},
    )
    assert response.status_code == 503
    assert "business_tag_selection_scores" in response.json()["detail"]["missing_tables"]
```

- [ ] **Step 2: 运行测试并确认路由不存在**

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_selection_v2_api.py -q
```

Expected: FAIL，状态码404或导入缺失。

- [ ] **Step 3: 定义请求和响应模型**

`models.py` 至少包含：

```python
class SelectionBatchCalculateRequest(BaseModel):
    chain_id: str
    trade_date: date
    mapping_ids: list[str] = Field(default_factory=list)
    model_version: str = "v2.0"
    dry_run: bool = True


class SelectionCandidate(BaseModel):
    code: str
    pool_code: Literal["A", "B", "C", "D"]
    primary_mapping_id: str
    secondary_mappings: list[dict] = Field(default_factory=list)
    benefit_score: float | None
    expectation_gap_score: float | None
    risk_score: float | None
    confidence_score: float | None
    opportunity_score: float | None
    evidence_level: Literal["E0", "E1", "E2", "E3", "E4", "E5", "E6"]
    data_limitations: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 实现服务层查询和主映射聚合**

```python
def list_selection_candidates(*, chain_id: str, trade_date: date,
                              pool: str | None, model_version: str,
                              limit: int, offset: int) -> dict:
    rows = repository.fetch_candidate_rows(
        chain_id=chain_id, trade_date=trade_date, pool=pool,
        model_version=model_version, limit=limit, offset=offset,
    )
    items = aggregate_stock_mappings(rows)
    return {
        "chain_id": chain_id, "trade_date": trade_date.isoformat(),
        "model_version": model_version, "items": items,
        "data_limitations": collect_limitations(rows),
    }
```

`get_stock_selection_detail()` 返回全部 mapping 的评分路径、证据ID、阶段、当前池和迁移日志。服务层不得重新计算历史分数。

- [ ] **Step 5: 注册三个新路由**

`selection_router.py` 定义：

```python
router = APIRouter(prefix="/supply-chain/selection", tags=["supply-chain-selection"])

@router.get("/candidates")
def candidates(chain_id: str, trade_date: date, pool: str | None = None,
               model_version: str = "v2.0", limit: int = 50, offset: int = 0):
    try:
        return selection_service.list_selection_candidates(
            chain_id=chain_id, trade_date=trade_date, pool=pool,
            model_version=model_version, limit=limit, offset=offset,
        )
    except MissingSelectionTables as exc:
        raise HTTPException(status_code=503, detail={"missing_tables": exc.tables}) from exc

@router.get("/stocks/{code}")
def stock_detail(code: str, chain_id: str, trade_date: date,
                 model_version: str = "v2.0"):
    try:
        return selection_service.get_stock_selection_detail(
            code=code, chain_id=chain_id, trade_date=trade_date,
            model_version=model_version,
        )
    except MissingSelectionTables as exc:
        raise HTTPException(status_code=503, detail={"missing_tables": exc.tables}) from exc

@router.post("/batch-score")
def batch_score(request: SelectionBatchCalculateRequest):
    try:
        return selection_service.batch_calculate_selection(request)
    except MissingSelectionTables as exc:
        raise HTTPException(status_code=503, detail={"missing_tables": exc.tables}) from exc
```

捕获 `MissingSelectionTables` 转为503，其余验证错误转为422。`router.py` 使用 `router.include_router(selection_router)`；不要把V2路由写回3835行的旧 `service.py`。

- [ ] **Step 6: 运行新API和旧产业链回归测试**

服务测试单独运行，避免多个顶层 `tests` 包的收集冲突：

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_selection_v2_api.py -q
bash tools/codex-lowio.sh py services/screener-service/tests/test_chain_api.py services/screener-service/tests/test_chain_candidates_api.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交V2 API**

```bash
git add services/screener-service/app/domains/supply_chain/models.py services/screener-service/app/domains/supply_chain/selection_service.py services/screener-service/app/domains/supply_chain/selection_router.py services/screener-service/app/domains/supply_chain/router.py services/screener-service/tests/test_supply_chain_selection_v2_api.py
git commit -m "feat: expose supply-chain selection v2 APIs"
```

---

### Task 7: 注册 `staging` 模型并写入幂等分池快照

**Files:**

- Create: `tools/register_supply_chain_research_selection_v2.py`
- Create: `tools/tests/test_register_supply_chain_research_selection_v2.py`
- Modify: `services/training-service/app/schemas.py`
- Modify: `services/training-service/app/routes.py`
- Create: `services/training-service/tests/test_screener_model_registry.py`

**Interfaces:**

- Consumes: `business_tag_selection_scores`、`business_tag_mapping`、任务2主映射聚合、现有三张模型注册表和 `screening_snapshots`。
- Produces: `fetch_pool_candidates()`、`snapshot_factor_payload()`、`register_and_snapshot()`；训练服务能解析 `model_type=screener`。

- [ ] **Step 1: 写注册身份、D池排除和快照载荷失败测试**

```python
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "register_supply_chain_research_selection_v2.py"
SPEC = importlib.util.spec_from_file_location("register_supply_chain_research_selection_v2", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(module)


def test_model_identity_and_stage_are_explicit():
    assert module.MODEL_ID == "supply_chain_research_selection_v2"
    assert module.MODEL_NAME == "产业链研究与选股模型"
    assert module.VERSION_TAG == "v2.0"
    assert module.MODEL_STAGE == "staging"


def test_snapshot_payload_keeps_audit_fields():
    payload = module.snapshot_factor_payload({
        "pool_code": "A", "primary_mapping_id": "m1", "model_version": "v2.0",
        "benefit_score": 70, "expectation_gap_score": 60, "risk_score": 20,
        "confidence_score": 80, "opportunity_score": 60.5,
        "evidence_level": "E4", "coverage_ratio": 0.8, "veto_reasons": [],
    })
    assert payload["pool_code"] == "A"
    assert payload["primary_mapping_id"] == "m1"
    assert payload["confidence_score"] == 80.0


def test_filter_snapshot_candidates_excludes_d_and_vetoed_rows():
    rows = [
        {"code": "1", "pool_code": "A", "veto_reasons": [], "benefit_score": 70, "evidence_level": "E4"},
        {"code": "2", "pool_code": "D", "veto_reasons": [], "benefit_score": 80, "evidence_level": "E1"},
        {"code": "3", "pool_code": "B", "veto_reasons": ["mapping_contradicted"], "benefit_score": 90, "evidence_level": "E3"},
    ]
    assert [r["code"] for r in module.filter_snapshot_candidates(rows)] == ["1"]
```

- [ ] **Step 2: 写训练服务模型类型失败测试**

```python
import pytest
from pydantic import ValidationError

from app.routes import _build_truthful_comparison
from app.schemas import ModelType, TrainingParams


def test_training_registry_accepts_screener_model_type():
    assert ModelType("screener") is ModelType.SCREENER


def test_training_params_reject_screener_registry_type():
    with pytest.raises(ValidationError):
        TrainingParams(model_type=ModelType.SCREENER)


def test_model_comparison_never_fills_missing_performance_metrics():
    comparisons, verdict, recommendation = _build_truthful_comparison({}, None)
    assert comparisons == []
    assert verdict == "insufficient_evidence"
    assert "缺少真实回测指标" in recommendation
```

- [ ] **Step 3: 运行测试并确认失败**

```bash
bash tools/codex-lowio.sh py tools/tests/test_register_supply_chain_research_selection_v2.py -q
bash tools/codex-lowio.sh py services/training-service/tests/test_screener_model_registry.py -q
```

Expected: 注册工具缺失；`ModelType` 不接受 `screener`。

- [ ] **Step 4: 实现候选获取、主映射选择和因子载荷**

工具固定常量：

```python
MODEL_ID = "supply_chain_research_selection_v2"
MODEL_NAME = "产业链研究与选股模型"
DISPLAY_NAME = "产业链研究与选股模型 V2.0"
VERSION_TAG = "v2.0"
MODEL_STAGE = "staging"
ELIGIBLE_POOLS = ("A", "B", "C")
FACTOR_KEYS = [
    "pool_code", "primary_mapping_id", "model_version", "benefit_score",
    "expectation_gap_score", "risk_score", "confidence_score",
    "opportunity_score", "evidence_level", "coverage_ratio", "veto_reasons",
]
```

`fetch_pool_candidates()` 从指定 `trade_date/model_version` 读取完整合格候选，不使用今天最新复核替代历史截面。先按股票代码分组，再调用任务2 `aggregate_stock_mappings()`；D池、`eligibility_status != eligible`、有否决项的行全部排除。

```python
def snapshot_factor_payload(row: dict) -> dict:
    payload = {key: row.get(key) for key in FACTOR_KEYS}
    for key in (
        "benefit_score", "expectation_gap_score", "risk_score",
        "confidence_score", "opportunity_score", "coverage_ratio",
    ):
        if payload.get(key) is not None:
            payload[key] = float(payload[key])
    return payload


def filter_snapshot_candidates(rows: list[dict]) -> list[dict]:
    return [
        row for row in rows
        if row.get("pool_code") in ELIGIBLE_POOLS
        and not row.get("veto_reasons")
        and row.get("eligibility_status", "eligible") == "eligible"
    ]
```

- [ ] **Step 5: 实现注册前结构预检和原子事务**

注册前验证下列列存在：

```python
REQUIRED_SCHEMA = {
    "screening_models": {"model_key", "display_name", "category", "factor_keys", "is_active"},
    "model_registry": {"id", "name", "version", "model_type", "stage", "params", "metrics", "artifact_uri"},
    "model_versions": {"model_name", "version_tag", "snapshot_count", "win_rate", "mean_return", "is_current"},
    "screening_snapshots": {"model_key", "trade_date", "stock_code", "time_slot", "factors", "total_score", "grade", "rank_in_day"},
}
```

`register_and_snapshot()` 在同一事务内：

1. preflight 表和列；
2. 获取 A/B/C 合格候选并按股票去重；
3. upsert `screening_models`；
4. upsert `model_registry`，强制 `model_type=screener`、`stage=staging`；
5. 更新 `model_versions`，初始胜率和收益为 `NULL`；
6. 删除相同模型、日期、时段的旧快照；
7. 写入新快照；
8. 任一失败则回滚全部注册和快照写入。

CLI 必须支持：

```text
--pg-url
--trade-date（必填）
--time-slot（默认 close）
--top-a（默认 20）
--top-b（默认 20）
--top-c（默认 20）
--dry-run
```

- [ ] **Step 6: 让训练服务接受 screener 类型**

在 `ModelType` 中增加：

```python
SCREENER = "screener"
```

在 `TrainingParams.model_type` 上增加 `field_validator`，当值为 `ModelType.SCREENER` 时抛出 `ValueError("screener is a registry-only model type")`。因此 `SCREENER` 只用于注册表列表和详情解析，不进入训练任务创建。

同时把模型比较中的固定默认收益、Sharpe、胜率等全部删除，抽出：

```python
REQUIRED_COMPARE_METRICS = (
    "ic", "icir", "sharpe", "max_drawdown",
    "annual_return", "win_rate", "profit_loss_ratio",
)


def _build_truthful_comparison(new_metrics: dict, old_metrics: dict | None):
    missing_new = [key for key in REQUIRED_COMPARE_METRICS if new_metrics.get(key) is None]
    missing_old = (
        list(REQUIRED_COMPARE_METRICS)
        if old_metrics is None
        else [key for key in REQUIRED_COMPARE_METRICS if old_metrics.get(key) is None]
    )
    if missing_new or missing_old:
        missing = sorted(set(missing_new + missing_old))
        return (
            [],
            "insufficient_evidence",
            "缺少真实回测指标：" + ", ".join(missing) + "；不能生成上线建议。",
        )
    return _compare_complete_metric_sets(new_metrics, old_metrics)
```

原比较路由调用该函数；不再以0.052、1.8、0.62等固定数值填空。

- [ ] **Step 7: 运行注册、训练契约和V1回归测试**

```bash
bash tools/codex-lowio.sh py tools/tests/test_register_supply_chain_research_selection_v2.py tools/tests/test_register_supply_chain_expectation_gap_model.py -q
bash tools/codex-lowio.sh py services/training-service/tests/test_screener_model_registry.py services/training-service/tests/test_training_contracts.py -q
```

Expected: PASS；V1常量和公式测试不变。

- [ ] **Step 8: 提交注册能力**

```bash
git add tools/register_supply_chain_research_selection_v2.py tools/tests/test_register_supply_chain_research_selection_v2.py services/training-service/app/schemas.py services/training-service/app/routes.py services/training-service/tests/test_screener_model_registry.py
git commit -m "feat: register supply-chain selection v2 snapshots"
```

---

### Task 8: 实现复权、T+1可执行、分池与消融回测

**Files:**

- Create: `services/backtest-service/app/adapters/supply_chain_selection_v2.py`
- Modify: `services/backtest-service/app/adapters/registry.py`
- Create: `services/backtest-service/tests/test_supply_chain_selection_v2_adapter.py`
- Create: `tools/backtest_supply_chain_research_selection_v2.py`
- Create: `tools/tests/test_backtest_supply_chain_research_selection_v2.py`

**Interfaces:**

- Consumes: 历史冻结的 `business_tag_selection_scores` 完整候选、任务7快照、`daily_kline`、`adj_factor`、现有 `BacktestRequest` 和 `factor_evaluations`。
- Produces: `SupplyChainSelectionV2Adapter.run()`、七种消融结果、A/B/C分池T+3/5/10/20真实结果和不足原因。

- [ ] **Step 1: 写复权、T+1和分池失败测试**

```python
from app.adapters.base import BacktestRequest
from app.adapters.supply_chain_selection_v2 import (
    SupplyChainSelectionV2Adapter,
    normalize_stock_code,
)


def test_normalize_stock_code_removes_exchange_suffix():
    assert normalize_stock_code("300001.SZ") == "300001"
    assert normalize_stock_code("688001") == "688001"


def test_adapter_registers_expected_model_key():
    assert SupplyChainSelectionV2Adapter.model_key == "supply_chain_research_selection_v2"


def test_pool_metrics_never_include_d_pool(fake_connection):
    report = SupplyChainSelectionV2Adapter().run(
        BacktestRequest(
            model_key="supply_chain_research_selection_v2",
            forward_days=5,
            cost_bps=14,
            min_periods=1,
            min_per_day=1,
            min_observations=1,
            connection_factory=lambda: fake_connection,
        ),
        readiness={"status": "ready"},
    )
    assert "D" not in report["by_pool"]
    assert report["execution_assumption"] == "T+1 open to future adjusted close, 14.0 bps cost"
```

- [ ] **Step 2: 运行测试并确认适配器不存在**

```bash
bash tools/codex-lowio.sh py services/backtest-service/tests/test_supply_chain_selection_v2_adapter.py -q
```

Expected: FAIL with `ModuleNotFoundError`。

- [ ] **Step 3: 实现严格收益口径**

适配器查询必须遵守：

```sql
SELECT
    s.trade_date,
    s.stock_code,
    s.factors,
    entry.trade_date AS entry_date,
    entry.open AS entry_open,
    entry.adj_factor AS entry_adj,
    exit.close AS exit_close,
    exit.adj_factor AS exit_adj
FROM screening_snapshots s
JOIN LATERAL (
    SELECT k.trade_date, k.open, a.adj_factor
    FROM daily_kline k
    LEFT JOIN adj_factor a ON a.code = k.code AND a.trade_date = k.trade_date
    WHERE k.code = split_part(s.stock_code, '.', 1)
      AND k.trade_date > s.trade_date
      AND k.open > 0
    ORDER BY k.trade_date
    LIMIT 1
) entry ON TRUE
JOIN LATERAL (
    SELECT k.close, a.adj_factor
    FROM daily_kline k
    LEFT JOIN adj_factor a ON a.code = k.code AND a.trade_date = k.trade_date
    WHERE k.code = split_part(s.stock_code, '.', 1)
      AND k.trade_date >= entry.trade_date
      AND k.close > 0
    ORDER BY k.trade_date
    OFFSET %s LIMIT 1
) exit ON TRUE
WHERE s.model_key = %s
  AND s.factors->>'pool_code' IN ('A','B','C')
ORDER BY s.trade_date, s.stock_code
```

收益使用现有 `compute_adjusted_return(entry_open, entry_adj, exit_close, exit_adj, cost_bps)`。任一端 `adj_factor` 缺失时，该条不进入正式复权结果，并计入 `missing_adj_factor_count`；不能静默按1作为正式验收口径。

- [ ] **Step 4: 输出分池、分链、基准和数据覆盖**

报告固定包含：

```python
{
    "model_key": "supply_chain_research_selection_v2",
    "execution_assumption": "T+1 open to future adjusted close, 14.0 bps cost",
    "by_pool": {"A": {}, "B": {}, "C": {}},
    "by_chain": {},
    "by_market_regime": {},
    "benchmark": {},
    "excess_return": {},
    "coverage": {
        "snapshot_rows": 0,
        "return_rows": 0,
        "missing_adj_factor_count": 0,
        "available_score_dates": 0,
    },
    "insufficient_reason": None,
}
```

没有足够历史截面时 `status=INSUFFICIENT_EVIDENCE`，不得填充默认胜率、Sharpe或收益。

- [ ] **Step 5: 实现完整候选集消融**

CLI固定七个变体：

```python
ABLATIONS = (
    "v1",
    "v2_full",
    "v2_without_dimensions",
    "v2_without_market_expectation",
    "v2_without_risk_penalty",
    "v2_three_high_only",
    "v2_evidence_stage_only",
)
```

每个历史日期必须从当日完整 `business_tag_selection_scores` 合格候选集重排，再选Top-N；不能只在最终快照入选样本中重排。结果写 `factor_evaluations`，每个变体使用独立 `evaluation_id`，并保存请求、样本覆盖、结果和不足原因。

- [ ] **Step 6: 注册回测适配器并增加CLI测试**

在 `registry.py` 增加：

```python
from .supply_chain_selection_v2 import SupplyChainSelectionV2Adapter

BACKTEST_ADAPTERS = {
    "bi_trend_launch": BiTrendAdapter(),
    "cb_auction_t0": CbAuctionT0Adapter(),
    "supply_chain_research_selection_v2": SupplyChainSelectionV2Adapter(),
}
```

工具测试必须覆盖：七种变体、D池排除、缺复权因子、样本不足、不同后缀代码归一化和禁止后验重算。

- [ ] **Step 7: 运行回测和现有真实口径回归测试**

```bash
bash tools/codex-lowio.sh py services/backtest-service/tests/test_supply_chain_selection_v2_adapter.py services/backtest-service/tests/test_truthful_factor_contract.py services/backtest-service/tests/test_factor_evidence_api.py -q
bash tools/codex-lowio.sh py tools/tests/test_backtest_supply_chain_research_selection_v2.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交回测能力**

```bash
git add services/backtest-service/app/adapters/supply_chain_selection_v2.py services/backtest-service/app/adapters/registry.py services/backtest-service/tests/test_supply_chain_selection_v2_adapter.py tools/backtest_supply_chain_research_selection_v2.py tools/tests/test_backtest_supply_chain_research_selection_v2.py
git commit -m "feat: backtest supply-chain v2 by evidence pool"
```

---

### Task 9: 真实落库、灵巧手试跑、注册与UAT签字

**Files:**

- Create: `docs/qa/supply-chain-research-selection-v2-uat-2026-07-11.md`
- Verify only: all files from Tasks 1-8

**Interfaces:**

- Consumes: 本地 PostgreSQL `localhost:6432/kronos`、最新已确认交易日、Tasks 1-8全部能力。
- Produces: 真实V2表数据、灵巧手八层研究记录、mapping分池、`staging`模型、快照、回测/不足证据结果和UAT报告。

- [ ] **Step 1: 检查工作区、Alembic head和V2快照重复**

```bash
git status --short
cd backend && DATABASE_SYNC_URL=postgresql+psycopg2://kronos:kronos@localhost:6432/kronos ../.venv/bin/alembic heads
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "SELECT count(*) AS existing_global_duplicate_groups FROM (SELECT 1 FROM screening_snapshots GROUP BY model_key,trade_date,stock_code,coalesce(time_slot,'') HAVING count(*)>1) d"
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "SELECT model_key,trade_date,stock_code,coalesce(time_slot,''),count(*) FROM screening_snapshots WHERE model_key='supply_chain_research_selection_v2' GROUP BY 1,2,3,4 HAVING count(*)>1"
```

Expected: Alembic 只有一个 head `032`；V2重复查询返回0行。全局重复组只作为现状记录，不在本任务中删除或改写其他模型历史数据；迁移仅对V2模型建立部分唯一索引。

- [ ] **Step 2: 运行全部聚焦测试**

```bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_v2_migration_contract.py -q
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py packages/kronos-factors/tests/test_chain_deconstruct.py -q
bash tools/codex-lowio.sh py tools/tests/test_materialize_supply_chain_research_v2.py tools/tests/test_score_supply_chain_selection_v2.py tools/tests/test_register_supply_chain_research_selection_v2.py tools/tests/test_backtest_supply_chain_research_selection_v2.py -q
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_selection_v2_api.py services/screener-service/tests/test_chain_api.py -q
bash tools/codex-lowio.sh py services/backtest-service/tests/test_supply_chain_selection_v2_adapter.py -q
bash tools/codex-lowio.sh py services/training-service/tests/test_screener_model_registry.py -q
```

Expected: 全部PASS。

- [ ] **Step 3: 将数据库迁移到新head并验证表结构**

```bash
cd backend && DATABASE_SYNC_URL=postgresql+psycopg2://kronos:kronos@localhost:6432/kronos ../.venv/bin/alembic upgrade head
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -c "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('supply_chain_node_dimensions','supply_chain_transmission_edges','supply_chain_technology_routes','supply_chain_node_scores','business_tag_authenticity_scores','business_tag_operating_quality_scores','business_tag_benefit_scores','business_tag_selection_scores','business_tag_pool_state','business_tag_pool_transition_log') ORDER BY table_name"
```

Expected: 10张表全部返回；`alembic_version=032`。

- [ ] **Step 4: 固定最新共同交易日**

```bash
export TRADE_DATE="$(PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -Atc "SELECT max(k.trade_date) FROM daily_kline k WHERE EXISTS (SELECT 1 FROM adj_factor a WHERE a.trade_date=k.trade_date)")"
test -n "$TRADE_DATE"
echo "$TRADE_DATE"
```

Expected: 输出一个明确的 `YYYY-MM-DD`。UAT报告必须记录该日期，不得写模糊的“今天”。

- [ ] **Step 5: dry-run灵巧手物化和评分**

```bash
python tools/materialize_supply_chain_research_v2.py --template-id dexterous_hand --as-of-date "$TRADE_DATE" --dry-run
python tools/score_supply_chain_selection_v2.py --chain-id dexterous_hand --trade-date "$TRADE_DATE" --model-version v2.0 --dry-run
```

Expected: 物化计划显示8个节点、64条节点维度、配置中的路线、传导边和待复核候选映射；评分计划列出候选数量、A/B/C/D/排除数量和数据限制，不写数据库。

- [ ] **Step 6: 真实物化和评分**

```bash
python tools/materialize_supply_chain_research_v2.py --template-id dexterous_hand --as-of-date "$TRADE_DATE"
python tools/score_supply_chain_selection_v2.py --chain-id dexterous_hand --trade-date "$TRADE_DATE" --model-version v2.0
```

Expected: 单事务成功；未知字段为NULL；所有自动结果保持 `pending_review`；没有原始证据的轴向磁通公司不得进入A/B池。

- [ ] **Step 7: 验证灵巧手八个反例和股票池状态**

执行SQL验证：

```bash
PGPASSWORD=kronos psql -h localhost -p 6432 -U kronos -d kronos -v trade_date="$TRADE_DATE" <<'SQL'
SELECT pool_code, count(*)
FROM business_tag_selection_scores
WHERE trade_date = :'trade_date' AND model_version = 'v2.0'
GROUP BY pool_code ORDER BY pool_code;

SELECT m.code, m.tag_name, a.evidence_level, s.pool_code,
       s.benefit_score, s.confidence_score, s.opportunity_score, s.veto_reasons
FROM business_tag_selection_scores s
JOIN business_tag_mapping m ON m.mapping_id = s.mapping_id
JOIN business_tag_authenticity_scores a
  ON a.mapping_id = s.mapping_id
 AND a.trade_date = s.trade_date
 AND a.model_version = s.model_version
WHERE s.trade_date = :'trade_date'
  AND m.chain_id = 'dexterous_hand'
ORDER BY s.pool_code NULLS LAST, s.opportunity_score DESC NULLS LAST;
SQL
```

Expected: D池和排除映射不会获得正式推荐资格；多映射股票只有主映射可以进入快照；AF0-AF4不越级。

- [ ] **Step 8: dry-run并真实注册staging模型**

```bash
python tools/register_supply_chain_research_selection_v2.py --trade-date "$TRADE_DATE" --time-slot close --dry-run
python tools/register_supply_chain_research_selection_v2.py --trade-date "$TRADE_DATE" --time-slot close
```

Expected: `model_registry.stage=staging`；只写A/B/C；D池0条；同股票同日期时段只有一条V2快照；V1记录和快照数不变。

- [ ] **Step 9: 运行四个周期回测和消融**

```bash
for H in 3 5 10 20; do
  python tools/backtest_supply_chain_research_selection_v2.py --forward-days "$H" --cost-bps 14 --run-ablation
done
```

Expected: 有足够历史截面则输出真实指标；不足时明确输出 `INSUFFICIENT_EVIDENCE` 和缺少的日期/样本数，不生成虚构胜率，也不升级production。

- [ ] **Step 10: 写UAT报告**

报告必须包含：

- 代码提交和实际迁移版本；
- 精确交易日和证据截止时间；
- 10张表行数；
- 8节点/64维度/路线/传导边数量；
- A/B/C/D及排除数量；
- 轴向磁通AF0-AF6反例结果；
- V1/V2注册状态和快照数量；
- T+3/5/10/20覆盖、真实结果或不足原因；
- 七项消融状态；
- 已知限制；
- 最终结论只能是 `PASS`、`CONDITIONAL PASS` 或 `FAIL`，不得因功能运行成功就宣称选股有效。

- [ ] **Step 11: 运行最终验证并提交UAT报告**

```bash
git diff --check
git status --short
git add docs/qa/supply-chain-research-selection-v2-uat-2026-07-11.md
git commit -m "docs: record supply-chain selection v2 UAT"
```

Expected: 只提交UAT报告和本任务相关文件；不混入现有 `.wolf/worktrees/*` 或 `chatbi-workspace/raw/backend/cockpit-screen` 改动。

---

## 实施完成门禁

只有同时满足以下条件才算本计划完成：

1. Tasks 1-8 聚焦测试全部通过；
2. 本地PG真实迁移、物化、评分和注册成功；
3. V1可继续查询，V2只处于`staging`；
4. 灵巧手八个反例全部通过；
5. D池不进入正式快照；
6. 同股票多映射不叠加；
7. 回测使用复权T+1口径且不后验泄漏；
8. 样本不足时明确返回不足，不伪造指标；
9. UAT报告包含可复核SQL、计数、日期和限制；
10. 未经样本外验证，不升级`production`、不输出自动买卖建议。
