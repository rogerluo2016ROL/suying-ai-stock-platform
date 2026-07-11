# Supply-chain Evidence Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 接通通用产业链证据编排，以灵巧手为首个验收案例，让候选发现、本地数据、官方补缺、人工审核、V2 评分和解释报告形成一条可追溯的数据链。

**Architecture:** 复用现有证据表、采集中心、审核接口和 V2 评分器。新增通用证据要求、纯规则缺口规划、带明确映射的适配器和运行编排器；自动产生的事实保持待审核，审核服务是唯一能写入 confirmed/approved 的应用路径。

**Tech Stack:** Python 3.11、FastAPI、Pydantic、PostgreSQL 15、Alembic、pytest、kronos-factors、现有本地数据采集中心。

## Global Constraints

- 设计基线：docs/superpowers/specs/2026-07-12-supply-chain-evidence-orchestration-design.md。
- 数据策略：本地数据优先，只对证据缺口访问官方资料。
- 运行必须显式传入 chain_id 和 as_of_date；截止时间为当日 23:59:59.999999 Asia/Shanghai。
- 公告、年报、调研和互动问答默认窗口为 as_of_date 向前 3 个完整日历年；产品和专利可以向前追溯。
- 旧产品只有在官方页面重新核验“仍在售”后才支持当前业务；旧专利只有在评分日法律状态仍为 active/granted 时才支持当前技术路线。
- 自动采集、事实提取和定时任务只能写 pending/pending_review。
- 公司整体财务只能标为 proxy，不能提高灵巧手真实性等级。
- 缺失值保存 NULL/unknown，不得用 0 或中性 50 分填空。
- 不设 A、B、C 池最低股票数量；证据不足时允许全部留在 D 或被排除。
- 轴向磁通同时执行 E0-E6 与 AF0-AF6 门槛，最终取更低的池上限。
- 禁止调用或导入 tools/backfill_ai_compute_all_mapped.py。该脚本有固定日期、AI 算力词表和公司级代理语义。
- 首轮不新增前端页面，只交付 JSON、Markdown 和现有解释 API。
- 模型保持 staging，直到样本外门槛和发布流程全部通过。
- 保留工作树中的其他改动；每个任务只提交列出的文件。
- 所有代码任务按 RED、GREEN、REFACTOR 顺序执行，使用 tools/codex-lowio.sh 跑聚焦测试。
- 当前相关测试基线为 67 passed，命令见“最终回归”。

---

## File map

### New files

- packages/kronos-factors/configs/industry_chain_evidence_requirements.json
- packages/kronos-factors/kronos_factors/engine/industry_chain_evidence_requirements.py
- packages/kronos-factors/kronos_factors/engine/supply_chain_evidence_orchestration.py
- packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py
- packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py
- backend/alembic/versions/033_supply_chain_evidence_review_gate.py
- services/screener-service/app/domains/supply_chain/evidence_review_repository.py
- services/screener-service/app/domains/supply_chain/evidence_review_service.py
- services/screener-service/app/domains/supply_chain/evidence_review_router.py
- services/screener-service/app/domains/supply_chain/evidence_orchestration_repository.py
- services/screener-service/tests/test_supply_chain_evidence_review.py
- services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py
- tools/supply_chain_evidence_adapters.py
- tools/supply_chain_evidence_orchestrator.py
- tools/supply_chain_evidence_report.py
- tools/run_supply_chain_evidence_orchestration.py
- tools/run_supply_chain_evidence_orchestration_uat.py
- tools/tests/test_supply_chain_evidence_adapters.py
- tools/tests/test_supply_chain_evidence_orchestrator.py
- tools/tests/test_supply_chain_evidence_report.py
- tools/tests/test_run_supply_chain_evidence_orchestration_uat.py

### Modified files

- packages/kronos-factors/configs/industry_chain_templates.json
- packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py
- packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py
- packages/kronos-factors/tests/test_industry_chain_templates.py
- packages/kronos-factors/tests/test_supply_chain_selection_v2.py
- tools/supply_chain_data_collection_center.py
- tools/supply_chain_evidence_pipeline.py
- tools/score_supply_chain_selection_v2.py
- tools/tests/test_supply_chain_data_collection_center.py
- tools/tests/test_supply_chain_evidence_pipeline.py
- tools/tests/test_score_supply_chain_selection_v2.py
- services/screener-service/app/domains/screening/service.py
- services/screener-service/app/domains/supply_chain/router.py
- services/screener-service/app/domains/supply_chain/models.py
- services/screener-service/app/domains/supply_chain/selection_repository.py
- services/screener-service/app/domains/supply_chain/selection_service.py
- services/screener-service/tests/test_supply_chain_selection_repository.py
- services/screener-service/tests/test_supply_chain_selection_v2_api.py
- services/screener-service/tests/test_supply_chain_v2_migration_contract.py
- services/screener-service/tests/fixtures/openapi_paths.json
- services/api-gateway/tests/test_gateway_routes.py

---

### Task 1: Add the global evidence requirement catalog

**Files:**

- Create: packages/kronos-factors/configs/industry_chain_evidence_requirements.json
- Create: packages/kronos-factors/kronos_factors/engine/industry_chain_evidence_requirements.py
- Create: packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py

**Interfaces:**

- Produces: EvidenceRequirementCatalog, load_evidence_requirements(), validate_evidence_requirements() and get_evidence_level_rule().
- Consumed by: Tasks 2, 5 and 8.

- [ ] **Step 1: Write the failing catalog tests**

~~~python
from copy import deepcopy

import pytest

from kronos_factors.engine.industry_chain_evidence_requirements import (
    get_evidence_level_rule,
    load_evidence_requirements,
    validate_evidence_requirements,
)


def test_catalog_defines_monotonic_e0_to_e6_and_pool_caps():
    catalog = load_evidence_requirements()
    validate_evidence_requirements(catalog)

    assert list(catalog.evidence_levels) == [f"E{i}" for i in range(7)]
    assert [catalog.evidence_levels[f"E{i}"]["rank"] for i in range(7)] == list(range(7))
    assert [catalog.evidence_levels[f"E{i}"]["max_pool"] for i in range(7)] == [
        None, "D", "C", "B", "A", "A", "A"
    ]


def test_e4_to_e6_require_strong_confirmed_facts():
    catalog = load_evidence_requirements()

    for level in ("E4", "E5", "E6"):
        rule = get_evidence_level_rule(level, requirements=catalog)
        assert rule["minimum_source_level"] == "strong"
        assert rule["allowed_fact_natures"] == ["confirmed_fact"]


def test_catalog_rejects_non_positive_expiry_days():
    catalog = load_evidence_requirements()
    broken = deepcopy(catalog.raw)
    broken["freshness_policies"]["customer_sample"] = 0

    with pytest.raises(ValueError, match="freshness_policies.customer_sample"):
        validate_evidence_requirements(broken)
~~~

- [ ] **Step 2: Run the tests and verify RED**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py
~~~

Expected: collection fails because industry_chain_evidence_requirements does not exist.

- [ ] **Step 3: Add the complete JSON catalog**

Create the file with these exact top-level keys and evidence type IDs:

~~~json
{
  "version": "v1.0",
  "source_level_rank": {"weak": 1, "mid": 2, "strong": 3},
  "evidence_levels": {
    "E0": {"rank": 0, "meaning": "untraceable_signal", "max_pool": null, "eligible": false},
    "E1": {"rank": 1, "meaning": "business_presence", "max_pool": "D", "eligible": true},
    "E2": {"rank": 2, "meaning": "product_or_prototype", "max_pool": "C", "eligible": true},
    "E3": {"rank": 3, "meaning": "customer_validation", "max_pool": "B", "eligible": true},
    "E4": {"rank": 4, "meaning": "order_or_delivery", "max_pool": "A", "eligible": true},
    "E5": {"rank": 5, "meaning": "recognized_revenue", "max_pool": "A", "eligible": true},
    "E6": {"rank": 6, "meaning": "recognized_profit", "max_pool": "A", "eligible": true}
  },
  "evidence_types": {
    "business_presence": {
      "level": "E1",
      "fact_types": ["business_presence"],
      "metadata_flags": [],
      "minimum_source_level": "mid",
      "allowed_fact_natures": ["confirmed_fact", "company_claim"],
      "score_fields": [],
      "expiry_policy": null,
      "search_terms": [],
      "default_next_action": "核验相关产品或样机"
    },
    "product_or_prototype": {
      "level": "E2",
      "fact_types": ["product_spec", "prototype_delivery"],
      "metadata_flags": [],
      "minimum_source_level": "mid",
      "allowed_fact_natures": ["confirmed_fact", "company_claim"],
      "score_fields": ["product_evidence_score"],
      "expiry_policy": null,
      "search_terms": ["产品", "样机", "样品", "规格"],
      "default_next_action": "核验客户送样或测试"
    },
    "customer_validation": {
      "level": "E3",
      "fact_types": ["customer_validation"],
      "metadata_flags": [],
      "minimum_source_level": "mid",
      "allowed_fact_natures": ["confirmed_fact", "company_claim"],
      "score_fields": ["customer_evidence_score"],
      "expiry_policy": "customer_test",
      "search_terms": ["送样", "验证", "测试", "定点"],
      "default_next_action": "核验订单或交付"
    },
    "order_or_delivery": {
      "level": "E4",
      "fact_types": ["order_award", "small_batch_delivery"],
      "metadata_flags": [],
      "minimum_source_level": "strong",
      "allowed_fact_natures": ["confirmed_fact"],
      "score_fields": ["order_revenue_evidence_score", "order_certainty_score"],
      "expiry_policy": null,
      "search_terms": ["订单", "中标", "合同", "交付"],
      "default_next_action": "核验收入确认"
    },
    "recognized_revenue": {
      "level": "E5",
      "fact_types": ["revenue_margin"],
      "metadata_flags": ["revenue_confirmed"],
      "minimum_source_level": "strong",
      "allowed_fact_natures": ["confirmed_fact"],
      "score_fields": ["revenue_exposure_score"],
      "expiry_policy": "financial_revenue",
      "search_terms": ["相关收入", "营业收入", "收入占比"],
      "default_next_action": "核验相关利润"
    },
    "recognized_profit": {
      "level": "E6",
      "fact_types": ["revenue_margin"],
      "metadata_flags": ["profit_confirmed"],
      "minimum_source_level": "strong",
      "allowed_fact_natures": ["confirmed_fact"],
      "score_fields": ["profit_elasticity_score"],
      "expiry_policy": "financial_revenue",
      "search_terms": ["毛利", "利润贡献", "分部利润"],
      "default_next_action": "复核利润持续性"
    }
  },
  "freshness_policies": {
    "interactive_answer": 90,
    "customer_sample": 180,
    "customer_test": 180,
    "nomination": 365,
    "financial_revenue": 180
  }
}
~~~

- [ ] **Step 4: Implement the loader and validators**

~~~python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

EVIDENCE_REQUIREMENTS_CONFIG_NAME = "industry_chain_evidence_requirements.json"
EXPECTED_LEVELS = tuple(f"E{i}" for i in range(7))
ALLOWED_POOLS = {None, "A", "B", "C", "D"}
ALLOWED_SOURCE_LEVELS = {"weak", "mid", "strong"}


@dataclass(frozen=True)
class EvidenceRequirementCatalog:
    version: str
    source_level_rank: dict[str, int]
    evidence_levels: dict[str, dict[str, Any]]
    evidence_types: dict[str, dict[str, Any]]
    freshness_policies: dict[str, int]
    raw: dict[str, Any]


def _config_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    return Path(__file__).resolve().parents[2] / "configs" / EVIDENCE_REQUIREMENTS_CONFIG_NAME


def _catalog(data: Mapping[str, Any]) -> EvidenceRequirementCatalog:
    raw = dict(data)
    return EvidenceRequirementCatalog(
        version=str(raw["version"]),
        source_level_rank=dict(raw["source_level_rank"]),
        evidence_levels=dict(raw["evidence_levels"]),
        evidence_types=dict(raw["evidence_types"]),
        freshness_policies=dict(raw["freshness_policies"]),
        raw=raw,
    )


def load_evidence_requirements(path: str | Path | None = None) -> EvidenceRequirementCatalog:
    result = _catalog(json.loads(_config_path(path).read_text(encoding="utf-8")))
    validate_evidence_requirements(result)
    return result


def validate_evidence_requirements(
    requirements: Mapping[str, Any] | EvidenceRequirementCatalog,
    *,
    selection_profile: Mapping[str, Any] | None = None,
) -> None:
    data = requirements.raw if isinstance(requirements, EvidenceRequirementCatalog) else dict(requirements)
    levels = data.get("evidence_levels") or {}
    if tuple(levels) != EXPECTED_LEVELS:
        raise ValueError("evidence_levels must define E0 through E6 in order")
    for rank, level in enumerate(EXPECTED_LEVELS):
        rule = levels[level]
        if int(rule.get("rank", -1)) != rank:
            raise ValueError(f"evidence_levels.{level}.rank must be {rank}")
        if rule.get("max_pool") not in ALLOWED_POOLS:
            raise ValueError(f"evidence_levels.{level}.max_pool is invalid")
    for name, days in (data.get("freshness_policies") or {}).items():
        if not isinstance(days, int) or days <= 0:
            raise ValueError(f"freshness_policies.{name} must be a positive integer")
    seen_fact_signatures: set[tuple[str, tuple[str, ...]]] = set()
    for type_id, rule in (data.get("evidence_types") or {}).items():
        if rule.get("level") not in levels:
            raise ValueError(f"evidence_types.{type_id}.level is invalid")
        if rule.get("minimum_source_level") not in ALLOWED_SOURCE_LEVELS:
            raise ValueError(f"evidence_types.{type_id}.minimum_source_level is invalid")
        policy = rule.get("expiry_policy")
        if policy is not None and policy not in data.get("freshness_policies", {}):
            raise ValueError(f"evidence_types.{type_id}.expiry_policy is invalid")
        fact_types = [str(item) for item in rule.get("fact_types") or []]
        flags = tuple(sorted(str(item) for item in rule.get("metadata_flags") or []))
        signatures = {(fact_type, flags) for fact_type in fact_types}
        duplicates = seen_fact_signatures.intersection(signatures)
        if duplicates:
            raise ValueError(f"fact signatures must map once: {sorted(duplicates)}")
        seen_fact_signatures.update(signatures)
        score_fields = rule.get("score_fields") or []
        if any(not isinstance(item, str) or not item for item in score_fields):
            raise ValueError(f"evidence_types.{type_id}.score_fields is invalid")
    for level in ("E4", "E5", "E6"):
        rules = [item for item in data["evidence_types"].values() if item["level"] == level]
        if not rules or any(
            item["minimum_source_level"] != "strong"
            or item["allowed_fact_natures"] != ["confirmed_fact"]
            for item in rules
        ):
            raise ValueError(f"{level} requires strong confirmed facts")
    if selection_profile:
        for pool, threshold in selection_profile["pool_thresholds"].items():
            if threshold["min_evidence_level"] not in levels:
                raise ValueError(f"pool_thresholds.{pool}.min_evidence_level is unknown")


def get_evidence_level_rule(
    level: str,
    *,
    requirements: EvidenceRequirementCatalog | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    catalog = requirements or load_evidence_requirements(path)
    if level not in catalog.evidence_levels:
        raise ValueError(f"unknown evidence level: {level}")
    rule = dict(catalog.evidence_levels[level])
    matching = [item for item in catalog.evidence_types.values() if item["level"] == level]
    if matching:
        rule["minimum_source_level"] = matching[0]["minimum_source_level"]
        rule["allowed_fact_natures"] = list(matching[0]["allowed_fact_natures"])
    return rule
~~~

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py
git add packages/kronos-factors/configs/industry_chain_evidence_requirements.json packages/kronos-factors/kronos_factors/engine/industry_chain_evidence_requirements.py packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py
git commit -m "feat: add supply-chain evidence requirement catalog"
~~~

Expected: tests pass; commit contains only the three Task 1 files.

---

### Task 2: Add dexterous-hand evidence coverage and AF route contracts

**Files:**

- Modify: packages/kronos-factors/configs/industry_chain_templates.json:18531-18810
- Modify: packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py:1-104
- Modify: packages/kronos-factors/tests/test_industry_chain_templates.py:62-101

**Interfaces:**

- Consumes: EvidenceRequirementCatalog from Task 1.
- Produces: validate_industry_evidence_coverage() and get_business_evidence_requirement().
- Consumed by: candidate discovery in Task 5 and route gates in Task 8.

- [ ] **Step 1: Write failing template coverage tests**

~~~python
from kronos_factors.engine.industry_chain_evidence_requirements import load_evidence_requirements
from kronos_factors.engine.industry_chain_templates import (
    get_business_evidence_requirement,
    get_industry_template,
    validate_industry_evidence_coverage,
)


def test_dexterous_candidate_keywords_have_one_requirement_each():
    template = get_industry_template("dexterous_hand")
    validate_industry_evidence_coverage(template, load_evidence_requirements())

    keywords = template["candidate_mapping_rules"]["required_business_keywords"]
    matches = [get_business_evidence_requirement(template, keyword) for keyword in keywords]
    assert all(matches)
    assert len(matches) == len(keywords)


def test_axial_flux_ladder_is_monotonic_and_rejects_automotive_only():
    template = get_industry_template("dexterous_hand")
    axial = next(route for route in template["technology_routes"] if route["route_id"] == "dexterous_axial_flux_motor")
    ladder = axial["authenticity_ladder"]

    assert [ladder[f"AF{i}"]["rank"] for i in range(7)] == list(range(7))
    assert [ladder[f"AF{i}"]["max_pool"] for i in range(7)] == [None, "D", "C", "C", "B", "A", "A"]
    assert ladder["AF0"]["eligible"] is False
    assert "automotive" in axial["excluded_application_domains"]
    requirement = get_business_evidence_requirement(template, "轴向磁通电机")
    assert requirement["independent_discovery"] is True
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_industry_chain_templates.py
~~~

Expected: tests fail because the evidence coverage functions and template fields are missing.

- [ ] **Step 3: Add nine explicit industry coverage records**

Add requirement IDs and exact keyword coverage:

| requirement_id | business_keywords | node | route |
|---|---|---|---|
| dexterous_whole_hand | 灵巧手、机器人末端 | dexterous_hand_core_product | none |
| dexterous_micro_actuator | 微型执行器 | dexterous_hand_integration | none |
| dexterous_hollow_cup_motor | 空心杯电机 | dexterous_hand_foundation | dexterous_hollow_cup_screw |
| dexterous_frameless_motor | 无框电机 | dexterous_hand_foundation | dexterous_frameless_low_ratio |
| dexterous_axial_flux_motor | 轴向磁通电机 | dexterous_hand_foundation | dexterous_axial_flux_motor |
| dexterous_micro_screw | 微型丝杠 | dexterous_hand_foundation | dexterous_hollow_cup_screw |
| dexterous_tactile_sensor | 触觉传感器 | dexterous_hand_foundation | dexterous_tactile_sensing |
| dexterous_force_sensor | 力传感器 | dexterous_hand_foundation | dexterous_tactile_sensing |
| dexterous_tendon | 腱绳 | dexterous_hand_integration | dexterous_tendon_drive |

Write the search contract exactly as follows. Arrays below are JSON arrays in the template. `require_product_and_scene=false` is allowed only for the whole-hand row because the product term itself names the robot application; all component rows require both groups.

| requirement_id | aliases | product_terms | scene_terms | negative_examples | require product+scene | evidence types | next action |
|---|---|---|---|---|---|---|---|
| dexterous_whole_hand | 机器人手、仿生手、多指灵巧手、机器人末端 | 灵巧手、机器人手、多指手、末端执行器 | 机器人、具身智能、人形机器人 | 普通夹爪 | false | product_or_prototype、customer_validation、order_or_delivery、recognized_revenue、recognized_profit | 核验整手规格、客户和交付 |
| dexterous_micro_actuator | 微型驱动器、微型线性执行器 | 微型执行器、微型驱动器 | 灵巧手、机器人手指、机器人关节 | 汽车执行器 | true | product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验机器人安装位置和客户测试 |
| dexterous_hollow_cup_motor | 空杯电机、无铁芯电机 | 空心杯电机、空杯电机、无铁芯电机 | 灵巧手、机器人手指、末端执行器 | 消费电子震动马达 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue、recognized_profit | 核验灵巧手规格、送样和量产收入 |
| dexterous_frameless_motor | 力矩电机、无框力矩电机 | 无框电机、无框力矩电机 | 灵巧手、机器人关节、机器人腕部 | 通用工业伺服 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验机器人尺寸参数和装机位置 |
| dexterous_axial_flux_motor | 盘式电机、轴向磁场电机 | 轴向磁通电机、轴向磁场电机、盘式电机 | 灵巧手、机器人手指、机器人关节、机器人腕部 | 汽车驱动电机、轮毂电机、航空推进电机 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验机器人规格、装机、客户验证和收入 |
| dexterous_micro_screw | 微型滚珠丝杠、行星滚柱丝杠 | 微型丝杠、微型滚珠丝杠、微型行星滚柱丝杠 | 灵巧手、机器人手指、微型执行器 | 机床丝杠 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验尺寸、负载、送样和交付 |
| dexterous_tactile_sensor | 电子皮肤、阵列触觉 | 触觉传感器、电子皮肤、触觉阵列 | 灵巧手、机器人手指、机器人末端 | 气体传感器 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验阵列参数、装机和客户测试 |
| dexterous_force_sensor | 六维力传感器、指尖力传感器 | 力传感器、六维力传感器、指尖力传感器 | 灵巧手、机器人手指、机器人腕部 | 称重传感器 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验量程精度、安装位置和客户验证 |
| dexterous_tendon | 腱驱动、人工肌腱、柔性腱绳 | 腱绳、人工肌腱、柔性腱绳 | 灵巧手、机器人手指、腱驱动机器人 | 普通钢丝绳 | true | business_presence、product_or_prototype、customer_validation、order_or_delivery、recognized_revenue | 核验材料寿命、装机和交付 |

Do not treat aliases as facts. They only expand search. A match creates a candidate lead; E2 and above still require reviewed evidence of the corresponding type.

Set independent_discovery=true only on dexterous_axial_flux_motor in the first template. The orchestrator reads this flag generically; future industries can opt in other requirements without code changes.

Extend every AF entry with rank, eligible, required_fact_types, required_application_domains and required_metadata. AF2 through AF6 accept only dexterous_hand, robot_hand, robot_joint or robot_wrist. Add excluded_application_domains=["automotive"] to the route.

- [ ] **Step 4: Add coverage validation**

~~~python
def validate_industry_evidence_coverage(template, requirements) -> None:
    rows = list(template.get("evidence_requirements") or [])
    ids = [str(row.get("requirement_id") or "") for row in rows]
    if not rows or any(not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("industry evidence requirement ids must be non-empty and unique")
    known_types = set(requirements.evidence_types)
    route_ids = {str(route.get("route_id")) for route in template.get("technology_routes") or []}
    keyword_matches: dict[str, int] = {}
    for row in rows:
        if not set(row.get("required_evidence_type_ids") or []).issubset(known_types):
            raise ValueError(f"unknown evidence type in {row['requirement_id']}")
        if not row.get("product_terms"):
            raise ValueError(f"missing product terms in {row['requirement_id']}")
        if row.get("require_product_and_scene") and not row.get("scene_terms"):
            raise ValueError(f"missing scene terms in {row['requirement_id']}")
        if not row.get("next_validation_action"):
            raise ValueError(f"missing next action in {row['requirement_id']}")
        route_id = row.get("technology_route_id")
        if route_id and route_id not in route_ids:
            raise ValueError(f"unknown technology route: {route_id}")
        for keyword in row.get("business_keywords") or []:
            keyword_matches[str(keyword)] = keyword_matches.get(str(keyword), 0) + 1
    expected = template.get("candidate_mapping_rules", {}).get("required_business_keywords", [])
    invalid = [keyword for keyword in expected if keyword_matches.get(str(keyword), 0) != 1]
    if invalid:
        raise ValueError("candidate keywords require exactly one evidence coverage: " + ", ".join(invalid))


def get_business_evidence_requirement(template, keyword: str) -> dict:
    matches = [
        dict(row)
        for row in template.get("evidence_requirements") or []
        if keyword in (row.get("business_keywords") or [])
    ]
    if len(matches) != 1:
        raise ValueError(f"business keyword must resolve once: {keyword}")
    return matches[0]
~~~

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_industry_chain_templates.py packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py
git add packages/kronos-factors/configs/industry_chain_templates.json packages/kronos-factors/kronos_factors/engine/industry_chain_templates.py packages/kronos-factors/tests/test_industry_chain_templates.py
git commit -m "feat: define dexterous-hand evidence coverage"
~~~

Expected: every candidate keyword resolves once; AF0-AF6 is monotonic.

---

### Task 3: Remove automatic confirmation from existing collectors

**Files:**

- Modify: tools/supply_chain_data_collection_center.py:59-95,223-260,732-920,1197-1503
- Modify: tools/supply_chain_evidence_pipeline.py:46-73,136-242,767-922,997-1266
- Modify: tools/tests/test_supply_chain_data_collection_center.py:278-308
- Modify: tools/tests/test_supply_chain_evidence_pipeline.py:42-93

**Interfaces:**

- Produces: collectors that write pending facts, pending_review events, explicit publish_time and stage proposals with auto_apply=False.
- Consumed by: Tasks 4, 6 and 7.

- [ ] **Step 1: Reverse unsafe expectations and add publish-time tests**

~~~python
def test_extract_fact_from_strong_document_still_requires_review():
    document = center.RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="公告",
        content_text="公司灵巧手执行器已实现批量供货。",
        company_code="003021",
        publish_time="2026-07-09T09:00:00+08:00",
    )
    fact = center.extract_fact_from_document(document)
    assert fact.validation_status == "pending"


def test_strong_stage_signal_requires_review_and_is_not_auto_applied():
    decision = pipeline.decide_stage_transition(
        source_level="strong",
        commercial_stage_signal="C4",
    )
    assert decision.review_status == "pending_review"
    assert decision.auto_apply is False
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_data_collection_center.py tools/tests/test_supply_chain_evidence_pipeline.py
~~~

Expected: strong-source assertions fail because current code writes confirmed and auto-applies stages.

- [ ] **Step 3: Make all automatic paths review-only**

Apply these exact behavior changes in both modules:

~~~python
validation_status = "pending"
review_status = "pending_review"

return StageTransitionDecision(
    new_research_stage=new_research,
    new_commercial_stage=new_commercial,
    review_status="pending_review",
    auto_apply=False,
    reason=f"{source_level} evidence requires manual review",
)
~~~

Change ingest_text_document() to accept publish_time: datetime | None and mapping_id: str | None. Store the supplied publication time. Store NULL when callers do not know it; never use datetime.now() as the source publication time.

Extend RawDocument with metadata: dict[str, Any] | None = None. Preserve it in raw_evidence_documents.metadata so product-current and patent-legal-status checks can be reproduced. Existing callers remain compatible because the field defaults to None.

If mapping_id is missing, store the raw document, leave the fact unmapped and return mapping_required. Never select the highest-confidence company mapping.

Change refresh_stage_transitions() to create pending transition proposals only. Remove the automatic business_tag_stage_tracking upsert and return stage_applied=0.

- [ ] **Step 4: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_data_collection_center.py tools/tests/test_supply_chain_evidence_pipeline.py
git add tools/supply_chain_data_collection_center.py tools/supply_chain_evidence_pipeline.py tools/tests/test_supply_chain_data_collection_center.py tools/tests/test_supply_chain_evidence_pipeline.py
git commit -m "fix: require review for all collected evidence"
~~~

Expected: no automatic path writes confirmed, approved or an applied stage.

---

### Task 4: Add the transactional review gate

**Files:**

- Create: backend/alembic/versions/033_supply_chain_evidence_review_gate.py
- Create: services/screener-service/app/domains/supply_chain/evidence_review_repository.py
- Create: services/screener-service/app/domains/supply_chain/evidence_review_service.py
- Create: services/screener-service/app/domains/supply_chain/evidence_review_router.py
- Modify: services/screener-service/app/domains/supply_chain/router.py:1-13
- Modify: services/screener-service/app/domains/screening/service.py:1463-1591,3060-3074
- Create: services/screener-service/tests/test_supply_chain_evidence_review.py
- Modify: services/screener-service/tests/test_supply_chain_v2_migration_contract.py
- Modify: services/screener-service/tests/fixtures/openapi_paths.json
- Modify: services/api-gateway/tests/test_gateway_routes.py

**Interfaces:**

- Produces: EvidenceReviewRepository.review_fact(), review_event(), review_expectation_monitor(), list_queue() and one-transaction review service.
- Consumed by: Task 7 collection output and Task 9 explanation API.

- [ ] **Step 1: Write migration and service tests**

~~~python
def test_needs_more_evidence_keeps_fact_pending():
    assert normalize_review_decision("needs_more_evidence") == ("pending", "pending_review")


def test_fact_approval_sets_manual_marker_and_audit_fields():
    cursor = FakeCursor(review_fact_responses(existing_metadata={"keep": "value"}))
    repo = EvidenceReviewRepository(connection_factory=lambda: FakeConnection(cursor))
    result = repo.review_fact(
        fact_id="f1",
        decision="approved",
        reviewer="roger",
        note="原文与灵巧手业务一致",
        stage_after={"research_stage": "R4", "commercialization_stage": "C2"},
        normalization=ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
            evidence_delta_score=65,
            risk_score=20,
        ),
    )
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "set_config('app.supply_chain_review_action', 'manual', true)" in sql
    assert "review_normalization" in sql
    assert result["review_status"] == "approved"
    assert result["normalization_fields"] == ("evidence_delta_score", "risk_score")
    assert result["normalization"]["method_version"] == "manual-v1"
    assert result["normalization"]["as_of_date"] == "2026-07-09"
    assert result["metadata"]["keep"] == "value"
    assert result["reviewed_at"] == datetime(2026, 7, 12, 10, 0, tzinfo=timezone.utc)
    assert cursor.settings["app.supply_chain_review_action"] == ""


def test_historical_auto_confirmed_rows_are_not_score_eligible():
    migration_sql = migration_upgrade_sql()
    assert "validation_status = 'pending'" in migration_sql
    assert "review_status = 'pending_review'" in migration_sql


def test_expectation_monitor_has_review_path():
    repo = EvidenceReviewRepository(connection_factory=lambda: FakeConnection())
    result = repo.review_expectation_monitor(
        monitor_id="x1",
        decision="approved",
        reviewer="roger",
        note="已核对原始声明、发布日期和预期日期",
        normalization=ReviewNormalization(
            method_version="manual-v1",
            as_of_date=date(2026, 7, 9),
            market_expectation_score=55,
            catalyst_score=70,
        ),
    )
    assert result["review_status"] == "approved"
    assert result["normalization_fields"] == ("catalyst_score", "market_expectation_score")


def test_review_normalization_rejects_out_of_range_scores():
    with pytest.raises(ValidationError):
        ReviewNormalization(method_version="manual-v1", as_of_date=date(2026, 7, 9), risk_score=101)


def test_reviewed_at_crossing_utc_day_uses_shanghai_review_date():
    reviewed_at = datetime(2026, 7, 11, 17, 30, tzinfo=timezone.utc)
    assert reviewed_at.astimezone(ZoneInfo("Asia/Shanghai")).date() == date(2026, 7, 12)


def test_approval_without_normalization_preserves_metadata():
    result = review_fact_fixture(
        decision="approved",
        normalization=None,
        existing_metadata={
            "keep": "value",
            "review_normalization": {"risk_score": 99, "method_version": "collector"},
        },
    )
    assert result["metadata"] == {"keep": "value"}
    assert result["normalization_fields"] == ()
~~~

Migration contract assertions:

~~~python
assert 'revision: str = "033"' in migration_text
assert "032" in migration_text
assert "ADD COLUMN IF NOT EXISTS reviewer TEXT" in migration_text
assert "guard_supply_chain_manual_review" in migration_text
assert "business_tag_expectation_monitor" in migration_text
assert "business_tag_stage_tracking" in migration_text
assert "NULLIF(BTRIM(NEW.review_note), '') IS NOT NULL" in migration_text
assert "TIMESTAMP WITH TIME ZONE" in migration_text
assert "AT TIME ZONE 'Asia/Shanghai'" in migration_text
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_evidence_review.py services/screener-service/tests/test_supply_chain_v2_migration_contract.py
~~~

Expected: revision 033 and review modules are missing.

- [ ] **Step 3: Add revision 033**

Add reviewer, review_note and reviewed_at TIMESTAMP WITH TIME ZONE to evidence_extracted_facts and business_tag_expectation_monitor. business_tag_evidence_events already has the three fields, but its reviewed_at is naive. Convert it with `ALTER COLUMN reviewed_at TYPE TIMESTAMP WITH TIME ZONE USING reviewed_at AT TIME ZONE 'Asia/Shanghai'`; the project convention treats legacy naive audit timestamps as Shanghai local time. The downgrade converts the event value back with `reviewed_at AT TIME ZONE 'Asia/Shanghai'` before dropping the new fact/monitor columns. Before installing guards, demote historical rows that cannot prove manual review:

~~~sql
UPDATE evidence_extracted_facts
SET metadata = coalesce(metadata, '{}'::jsonb) - 'review_normalization'
WHERE coalesce(metadata, '{}'::jsonb) ? 'review_normalization';

UPDATE business_tag_expectation_monitor
SET metadata = coalesce(metadata, '{}'::jsonb) - 'review_normalization'
WHERE coalesce(metadata, '{}'::jsonb) ? 'review_normalization';

UPDATE evidence_extracted_facts AS fact
SET reviewer = event.reviewer,
    review_note = event.review_note,
    reviewed_at = event.reviewed_at
FROM business_tag_evidence_events AS event
WHERE fact.evidence_event_id = event.event_id
  AND fact.validation_status = 'confirmed'
  AND event.review_status = 'approved'
  AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
  AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
  AND event.reviewed_at IS NOT NULL;

UPDATE evidence_extracted_facts
SET validation_status = 'pending'
WHERE validation_status = 'confirmed'
  AND (
      NULLIF(BTRIM(reviewer), '') IS NULL
      OR NULLIF(BTRIM(review_note), '') IS NULL
      OR reviewed_at IS NULL
  );

UPDATE business_tag_evidence_events
SET review_status = 'pending_review'
WHERE review_status = 'approved'
  AND (
      NULLIF(BTRIM(reviewer), '') IS NULL
      OR NULLIF(BTRIM(review_note), '') IS NULL
      OR reviewed_at IS NULL
  );

UPDATE business_tag_expectation_monitor
SET review_status = 'pending_review'
WHERE review_status = 'approved'
  AND (
      NULLIF(BTRIM(reviewer), '') IS NULL
      OR NULLIF(BTRIM(review_note), '') IS NULL
      OR reviewed_at IS NULL
  );

UPDATE business_tag_stage_tracking AS stage
SET review_status = 'pending_review'
WHERE stage.review_status = 'approved'
  AND NOT EXISTS (
      SELECT 1
      FROM business_tag_evidence_events AS event
      WHERE event.event_id = stage.source_event_id
        AND event.review_status = 'approved'
        AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
        AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
        AND event.reviewed_at IS NOT NULL
  );
~~~

Create BEFORE INSERT OR UPDATE triggers on evidence_extracted_facts, business_tag_evidence_events and business_tag_expectation_monitor. They must reject any inserted or updated confirmed/approved row unless:

~~~sql
current_setting('app.supply_chain_review_action', true) = 'manual'
AND NULLIF(BTRIM(NEW.reviewer), '') IS NOT NULL
AND NULLIF(BTRIM(NEW.review_note), '') IS NOT NULL
AND NEW.reviewed_at IS NOT NULL
~~~

Create a fourth trigger on business_tag_stage_tracking. An approved stage requires the same manual transaction marker and source_event_id pointing to an approved event with non-empty reviewer, review_note and reviewed_at. The downgrade drops all four triggers, the function and the six newly added audit columns. It does not re-approve demoted historical rows. Task 8 and Task 9 also require audited facts/events/stages in every scoring query, so a disabled trigger cannot make legacy rows score-eligible.

- [ ] **Step 4: Implement the review transaction**

~~~python
ReviewDecision = Literal["approved", "rejected", "needs_more_evidence"]


class ReviewNormalization(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    method_version: str = Field(min_length=1)
    as_of_date: date
    market_expectation_score: float | None = Field(default=None, ge=0, le=100)
    catalyst_score: float | None = Field(default=None, ge=0, le=100)
    evidence_delta_score: float | None = Field(default=None, ge=0, le=100)
    claim_risk_penalty_score: float | None = Field(default=None, ge=0, le=100)
    risk_score: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def require_score(self):
        values = self.model_dump(exclude={"method_version", "as_of_date"}, exclude_none=True)
        if not values:
            raise ValueError("normalization requires at least one score")
        return self


def normalize_review_decision(decision: ReviewDecision) -> tuple[str, str]:
    return {
        "approved": ("confirmed", "approved"),
        "rejected": ("rejected", "rejected"),
        "needs_more_evidence": ("pending", "pending_review"),
    }[decision]


class EvidenceReviewRepository:
    def review_fact(
        self,
        *,
        fact_id: str,
        decision: ReviewDecision,
        reviewer: str,
        note: str,
        stage_after: dict[str, str] | None,
        normalization: ReviewNormalization | None = None,
        connection=None,
    ) -> dict:
        fact_status, event_status = normalize_review_decision(decision)
        normalization_payload = (
            normalization.model_dump(mode="json", exclude_none=True)
            if normalization else None
        )
        owns_connection = connection is None
        active = connection or self.connection_factory()
        try:
            with active.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SAVEPOINT supply_chain_manual_review")
                cur.execute("SELECT current_setting('app.supply_chain_review_action', true) AS value")
                previous_marker = str((cur.fetchone() or {}).get("value") or "")
                try:
                    cur.execute("SELECT set_config('app.supply_chain_review_action', 'manual', true)")
                    fact = self._update_fact(
                        cur, fact_id, fact_status, reviewer, note, normalization_payload,
                    )
                    if fact.get("evidence_event_id"):
                        self._update_event(cur, fact["evidence_event_id"], event_status, reviewer, note)
                    if decision == "approved" and stage_after:
                        self._upsert_stage_from_review(cur, fact, stage_after, reviewer, note)
                    cur.execute(
                        "SELECT set_config('app.supply_chain_review_action', %s, true)",
                        (previous_marker,),
                    )
                    cur.execute("RELEASE SAVEPOINT supply_chain_manual_review")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT supply_chain_manual_review")
                    cur.execute(
                        "SELECT set_config('app.supply_chain_review_action', %s, true)",
                        (previous_marker,),
                    )
                    cur.execute("RELEASE SAVEPOINT supply_chain_manual_review")
                    raise
            if owns_connection:
                active.commit()
        except Exception:
            if owns_connection:
                active.rollback()
            raise
        finally:
            if owns_connection:
                active.close()
        metadata = dict(fact.get("metadata") or {})
        stored = dict(metadata.get("review_normalization") or {})
        allowed_fields = {"evidence_delta_score", "risk_score"}
        fields = tuple(sorted(
            key for key, value in stored.items()
            if key in allowed_fields and value is not None
        ))
        return {
            "fact_id": fact_id,
            "review_status": event_status,
            "reviewer": reviewer,
            "reviewed_at": fact["reviewed_at"],
            "normalization_fields": fields,
            "normalization": stored,
            "metadata": metadata,
        }
~~~

review_event() and review_expectation_monitor() use the same savepoint, marker restoration and connection ownership rule. API calls omit connection and commit once. PostgreSQL UAT passes its own connection, so approval and score checks can be rolled back. The manual marker is restored before any method returns, including caller-owned success. There is no nested hidden commit.

review_normalization is an audit-owned reserved key. Collectors and pending-fact persistence remove it from incoming metadata. Migration 033 removes all legacy occurrences before any row can score. _update_fact() and _update_expectation_monitor() first calculate `clean_metadata = coalesce(metadata,'{}'::jsonb) - 'review_normalization'`, then use `CASE WHEN %s::jsonb IS NULL THEN clean_metadata ELSE jsonb_set(clean_metadata, '{review_normalization}', %s::jsonb, true) END` in the approval transaction and RETURNING metadata, reviewed_at. A missing payload clears an untrusted old normalization while preserving every unrelated key. The public result is built from returned columns, not the request, and includes database reviewed_at plus the stored normalization object. normalization_fields is the sorted intersection of non-NULL stored keys with the target's allowed score set: fact uses evidence_delta_score/risk_score; monitor uses market_expectation_score/catalyst_score/claim_risk_penalty_score. For decision=approved, review_fact() may persist evidence_delta_score and risk_score. review_expectation_monitor() may persist market_expectation_score, catalyst_score and claim_risk_penalty_score. The service rejects normalization on rejected/needs_more_evidence decisions, rejects target-incompatible fields, attaches reviewer, reviewed_at, method_version and as_of_date, and recomputes the 20-trading-day adjusted price return server-side. Review events do not accept normalization because business_tag_evidence_events has no metadata column. Approval without normalization remains valid evidence but leaves the corresponding score NULL.

Document in the response that the shared database user makes this an application-level gate, not verified human identity. Do not claim RBAC coverage.

- [ ] **Step 5: Register routes and preserve legacy compatibility**

New public routes, all under the gateway's existing screener prefix:

~~~text
GET  /api/v1/screener/supply-chain/evidence-review/queue
POST /api/v1/screener/supply-chain/evidence/facts/{fact_id}/review
POST /api/v1/screener/supply-chain/evidence/events/{event_id}/review
POST /api/v1/screener/supply-chain/evidence/expectations/{monitor_id}/review
~~~

The existing screening event-review endpoint delegates to the new service. The queue includes pending facts, pending events and pending expectation monitors. Add all new paths to openapi_paths.json and add one gateway routing assertion proving the prefix forwards to screener-service.

The new request model requires reviewer with min_length=1 and note with min_length=1 and accepts optional normalization: ReviewNormalization; remove the old default reviewer="system" from the review path. This records an asserted operator name, not authenticated identity.

- [ ] **Step 6: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_evidence_review.py services/screener-service/tests/test_supply_chain_v2_migration_contract.py services/screener-service/tests/test_domain_composition.py services/screener-service/tests/test_api.py services/api-gateway/tests/test_gateway_routes.py
git add backend/alembic/versions/033_supply_chain_evidence_review_gate.py services/screener-service/app/domains/supply_chain/evidence_review_repository.py services/screener-service/app/domains/supply_chain/evidence_review_service.py services/screener-service/app/domains/supply_chain/evidence_review_router.py services/screener-service/app/domains/supply_chain/router.py services/screener-service/app/domains/screening/service.py services/screener-service/tests/test_supply_chain_evidence_review.py services/screener-service/tests/test_supply_chain_v2_migration_contract.py services/screener-service/tests/fixtures/openapi_paths.json services/api-gateway/tests/test_gateway_routes.py
git commit -m "feat: gate supply-chain evidence approval"
~~~

Expected: tests pass and Alembic has one head at revision 033.

---

### Task 5: Implement pure candidate discovery and gap planning

**Files:**

- Create: packages/kronos-factors/kronos_factors/engine/supply_chain_evidence_orchestration.py
- Create: packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py

**Interfaces:**

- Consumes: Task 1 catalog and Task 2 coverage.
- Produces: EvidenceRunRequest, RequirementMatch, DiscoveryHit, CandidateMappingProposal, EvidenceGap, discover_candidate_documents(), propose_independent_candidates(), plan_evidence_gaps(), build_node_dimension_updates() and derive_axial_flux_stage().
- Consumed by: Tasks 6, 7 and 8.

- [ ] **Step 1: Write failing pure-function tests**

~~~python
def test_product_without_robot_scene_cannot_create_mapping():
    matches = discover_candidate_documents(
        documents=[{"doc_id": "d1", "text": "公司生产空心杯电机，用于消费电子"}],
        requirement={
            "requirement_id": "dexterous_hollow_cup_motor",
            "product_terms": ["空心杯电机"],
            "scene_terms": ["灵巧手", "机器人手指"],
            "negative_examples": ["消费电子"],
        },
    )
    assert matches[0].eligible_for_mapping is False


def test_gap_planner_separates_two_mappings_for_same_company():
    facts = [
        {"mapping_id": "force", "fact_type": "product_spec", "validation_status": "confirmed", "publish_time": datetime(2026, 7, 1)},
    ]
    gaps = plan_evidence_gaps(
        mapping_ids=("force", "tactile"),
        requirement_ids=("product_or_prototype",),
        facts=facts,
        as_of_date=date(2026, 7, 9),
        freshness_policies={},
    )
    assert {(gap.mapping_id, gap.status) for gap in gaps} == {
        ("force", "satisfied"), ("tactile", "missing")
    }


def test_automotive_axial_flux_stays_af0():
    stage = derive_axial_flux_stage([
        {"fact_type": "product_spec", "metadata": {"application_domain": "automotive"}}
    ])
    assert stage == "AF0"


def test_independent_axial_flux_hit_becomes_auditable_candidate_not_approved_evidence():
    hits = propose_independent_candidates(
        documents=[{
            "doc_id": "d-axis-1",
            "company_code": "688001",
            "source_level": "strong",
            "publish_time": "2026-06-30T10:00:00+08:00",
            "text": "机器人腕部轴向磁通电机，额定扭矩2Nm",
        }],
        requirement=axial_flux_requirement(),
        as_of_date=date(2026, 7, 9),
    )
    assert hits[0].eligible_for_mapping is True
    assert hits[0].validation_status == "pending"
    assert hits[0].proposal.status == "candidate"
    assert hits[0].proposal.evidence_ids == ()
    assert hits[0].proposal.technology_route_id == "dexterous_axial_flux_motor"


def test_multiple_documents_for_same_company_requirement_share_one_mapping():
    hits = propose_independent_candidates(
        documents=[axis_document("d1", "688001"), axis_document("d2", "688001")],
        requirement=axial_flux_requirement(),
        as_of_date=date(2026, 7, 9),
    )
    assert len({hit.proposal.mapping_id for hit in hits}) == 1
    assert {hit.doc_id for hit in hits} == {"d1", "d2"}


def test_only_approved_facts_update_node_dimensions():
    updates = build_node_dimension_updates(
        facts=[
            {"validation_status": "pending", "metadata": {"dimension_ids": ["physical_bom"]}},
            {"validation_status": "confirmed", "metadata": {"dimension_ids": ["evidence_validation"]}},
        ],
        node_id="dexterous_hand_foundation",
        as_of_date=date(2026, 7, 9),
    )
    assert [item.dimension_id for item in updates] == ["evidence_validation"]
    assert updates[0].status == "known"


def test_source_limits_reject_unknown_non_positive_or_boolean_values():
    with pytest.raises(ValueError):
        evidence_request(source_limits={"official_discovery_documents": -1})
    with pytest.raises(ValueError):
        evidence_request(source_limits={"unknown_source": 10})
    with pytest.raises(ValueError):
        evidence_request(source_limits={"mapped_official_tasks": True})


def test_mapping_and_company_scopes_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mapping_ids and company_codes"):
        evidence_request(mapping_ids=("m1",), company_codes=("688001",))
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py
~~~

Expected: the orchestration engine is missing.

- [ ] **Step 3: Implement public value objects**

~~~python
RunMode = Literal["dry-run", "collect", "score", "full"]
SourcePolicy = Literal["local-first", "official-gap"]
GapStatus = Literal["satisfied", "pending_review", "missing", "proxy", "contradicted", "stale"]


@dataclass(frozen=True)
class EvidenceRunRequest:
    chain_id: str
    as_of_date: date
    mode: RunMode
    source_policy: SourcePolicy
    mapping_ids: tuple[str, ...] = ()
    company_codes: tuple[str, ...] = ()
    source_limits: Mapping[str, int] = field(default_factory=dict)
    allow_score: bool = False

    def __post_init__(self) -> None:
        if self.mapping_ids and self.company_codes:
            raise ValueError("mapping_ids and company_codes are mutually exclusive")
        allowed = {
            "discovery", "official_discovery_documents",
            "official_discovery_companies", "official_pages_per_company",
            "mapped_official_tasks", "mapped_cninfo_documents_per_task",
        }
        for key, value in self.source_limits.items():
            if key not in allowed or isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"invalid source limit: {key}")


@dataclass(frozen=True)
class RequirementMatch:
    requirement_id: str
    product_hits: tuple[str, ...]
    scene_hits: tuple[str, ...]
    excluded_hits: tuple[str, ...]
    eligible_for_mapping: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class CandidateMappingProposal:
    mapping_id: str
    company_code: str
    chain_id: str
    node_id: str
    tag_name: str
    technology_route_id: str | None
    status: Literal["candidate"]
    confidence: float
    evidence_ids: tuple[str, ...]
    provenance: Mapping[str, Any]


@dataclass(frozen=True)
class DiscoveryHit:
    doc_id: str
    company_code: str
    requirement_id: str
    product_hits: tuple[str, ...]
    scene_hits: tuple[str, ...]
    excluded_hits: tuple[str, ...]
    source_level: str
    publish_time: datetime | None
    eligible_for_mapping: bool
    validation_status: Literal["pending"]
    proposal: CandidateMappingProposal | None


@dataclass(frozen=True)
class EvidenceGap:
    mapping_id: str
    requirement_id: str
    status: GapStatus
    evidence_ids: tuple[str, ...]
    next_action: str
    reasons: tuple[str, ...]
    product_terms: tuple[str, ...] = ()
    scene_terms: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    require_product_and_scene: bool = True


@dataclass(frozen=True)
class NodeDimensionUpdate:
    node_id: str
    dimension_id: str
    as_of_date: date
    status: Literal["known", "proxy", "contradicted"]
    score: float | None
    evidence_ids: tuple[str, ...]
~~~

- [ ] **Step 4: Implement matching, cutoff and AF rules**

discover_candidate_documents() requires a product hit and a scene hit; any negative example blocks eligible_for_mapping.

propose_independent_candidates() is the first phase for any template requirement marked independent_discovery. Axial flux is the first configured use. It scans local company documents before normal mapping collection, emits one DiscoveryHit per source document, and never emits confirmed evidence. For axial flux, an eligible hit requires:

1. source level mid or strong;
2. publication time on or before as_of_date;
3. an axial-flux product hit and a robot-hand/joint/wrist scene hit in the same document;
4. no excluded automotive-only, wheel-hub or aviation-only context.

The deterministic proposal mapping ID is hash(chain_id, company_code, requirement_id). technology_route_id is copied from the matched industry requirement. Its l1_l8_path provenance contains requirement_id, technology_route_id and deduplicated discovery_doc_ids/discovery_fact_ids arrays; upsert merges those arrays instead of creating another mapping. evidence_ids remains empty and status is candidate. This creates one traceable E1 research lead per company and requirement, not one mapping per document and not an E2 product fact. For axial flux, the missing approved route fact means AF0 and exclusion from all four pools; an approved patent/laboratory prototype must first reach AF1 before D is possible. The pending discovery facts and all later facts still need manual review before E2 or higher.

Existing five derived mappings follow the same E1 evidence rule: a candidate row whose provenance contains derived_from_mapping_id is a traceable business lead with an evidence cap of D. It does not copy or consume any evidence_ids from the source mapping. A stricter configured route gate still wins, so an axial mapping at AF0 is excluded rather than placed in D.

plan_evidence_gaps() must:

1. ignore facts published after as_of_date;
2. isolate facts by mapping_id;
3. treat pending as pending_review;
4. treat company-level facts as proxy;
5. detect contradicted and freshness expiry;
6. return one gap for every mapping and requirement pair.

derive_axial_flux_stage() evaluates AF6 down to AF0 and requires application_domain in dexterous_hand, robot_hand, robot_joint or robot_wrist for AF2 and above.

build_node_dimension_updates() reads confirmed facts only. It updates the dimension IDs carried in fact metadata and leaves every unmentioned dimension unchanged. Proxy facts write status=proxy and no numeric score unless the fact contains a documented scoring method.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py
git add packages/kronos-factors/kronos_factors/engine/supply_chain_evidence_orchestration.py packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py
git commit -m "feat: plan supply-chain evidence gaps"
~~~

Expected: pure tests pass without PostgreSQL or network.

---

### Task 6: Add scoped adapters and the PostgreSQL repository

**Files:**

- Create: tools/supply_chain_evidence_adapters.py
- Create: services/screener-service/app/domains/supply_chain/evidence_orchestration_repository.py
- Create: tools/tests/test_supply_chain_evidence_adapters.py
- Create: services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py
- Modify: tools/supply_chain_data_collection_center.py:1197-1503

**Interfaces:**

- Consumes: EvidenceGap and explicit mapping_id/requirement_id from Task 5.
- Produces: CollectionTask, UnmappedDiscoveryTask, AdapterResult, LocalEvidenceAdapter, OfficialDiscoveryAdapter, OfficialGapAdapter and EvidenceOrchestrationRepository.
- Consumed by: Task 7.

- [ ] **Step 1: Write adapter and repository tests**

~~~python
def test_local_hit_prevents_official_request():
    local = FakeAdapter({"m1:product": [document("local-1")]})
    official = FakeAdapter({"m1:product": [document("web-1")]})
    tasks = [CollectionTask("m1", "product", "003021", "兆威机电", ("灵巧手",))]

    result = collect_local_then_official(tasks, local=local, official=official)

    assert [item.doc_id for item in result.documents] == ["local-1"]
    assert official.calls == []


def test_repository_uses_explicit_mapping_and_pending_status():
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: FakeConnection())
    outcome = repository.persist_pending_document(
        document=document("d1"),
        mapping_id="m-force",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=date(2026, 7, 9),
    )
    assert outcome.mapping_id == "m-force"
    assert outcome.validation_status == "pending"
    assert outcome.review_status == "pending_review"


def test_pending_persistence_strips_reserved_review_normalization():
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: FakeConnection())
    outcome = repository.persist_pending_document(
        document=document("d-malicious", metadata={
            "keep": "value",
            "review_normalization": {"risk_score": 100, "method_version": "collector"},
        }),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=date(2026, 7, 9),
    )
    assert outcome.fact_metadata == {"keep": "value"}


def test_repository_persists_unmapped_discovery_before_candidate_mapping():
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: FakeConnection())
    outcome = repository.persist_discovery_hit(discovery_hit("d-axis-1"), job_id="j1")
    assert outcome.fact_mapping_id is None
    assert outcome.validation_status == "pending"
    mapping = repository.upsert_candidate_mapping(outcome.proposal)
    assert mapping.status == "candidate"
    assert mapping.evidence_ids == ()
    round_trip = repository.fetch_mappings("dexterous_hand", (mapping.mapping_id,), ())
    assert round_trip[0]["technology_route_id"] == "dexterous_axial_flux_motor"


def test_discovery_rerun_never_downgrades_reviewed_mapping_or_clears_evidence():
    repository = repository_with_mapping(
        status="verified",
        confidence=0.9,
        evidence_ids=["approved-e1"],
        discovery_doc_ids=["d1"],
    )
    result = repository.upsert_candidate_mapping(candidate_proposal(
        status="candidate",
        confidence=0.35,
        evidence_ids=(),
        discovery_doc_ids=["d2"],
    ))
    assert result.status == "verified"
    assert result.confidence == 0.9
    assert result.evidence_ids == ("approved-e1",)
    assert result.provenance["discovery_doc_ids"] == ["d1", "d2"]


def test_official_discovery_can_find_company_before_mapping_exists():
    adapter = OfficialDiscoveryAdapter(
        fetcher=FakeGlobalOfficialFetcher([
            document(
                "official-axis-1",
                code="688001",
                text="机器人腕部轴向磁通电机，额定扭矩2Nm",
            )
        ])
    )
    result = adapter.collect(
        [unmapped_axial_flux_task()],
        as_of_date=date(2026, 7, 9),
        source_limits={"official_discovery_documents": 50},
    )
    assert result.documents[0].company_code == "688001"
    assert result.network_requests == 1


def test_mapped_official_adapter_honors_limits_and_counts_requests():
    adapter = OfficialGapAdapter(FakeScopedFetcher(requests_per_task=3))
    result = adapter.collect(
        [collection_task("m1"), collection_task("m2")],
        as_of_date=date(2026, 7, 9),
        source_limits={
            "mapped_official_tasks": 1,
            "mapped_cninfo_documents_per_task": 2,
            "official_pages_per_company": 1,
        },
    )
    assert result.network_requests == 3
    assert result.status == "partial_success"
    assert "source_limit_skipped_tasks:1" in result.errors


def test_source_windows_keep_active_patent_and_current_product_but_drop_old_event():
    as_of = date(2026, 7, 9)
    assert resolve_collection_window("announcement", as_of) == (date(2023, 1, 1), as_of)
    assert resolve_collection_window("official_product_page", as_of) == (None, as_of)
    assert resolve_collection_window("patent", as_of) == (None, as_of)
    assert current_support_status(active_patent_2018(), as_of) == "current"
    assert current_support_status(current_product_page_2019(), as_of) == "current"
    assert current_support_status(old_announcement_2019(), as_of) == "historical_only"


def test_sanitize_error_redacts_database_dsn_and_secret_keys():
    value = sanitize_error(RuntimeError(
        "postgresql://alice:dbpass@localhost/db password=hunter2 client_secret=abc"
    ))
    assert "dbpass" not in value
    assert "hunter2" not in value
    assert "client_secret=abc" not in value
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_adapters.py services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py
~~~

Expected: adapter and repository imports fail.

- [ ] **Step 3: Implement narrow adapter contracts**

~~~python
import re

from supply_chain_data_collection_center import RawDocument


def normalize_stock_code(value: object) -> str:
    return str(value or "").strip().split(".", 1)[0]


def sanitize_error(exc: Exception) -> str:
    message = str(exc)[:500]
    for pattern in (
        r"(?i)(authorization|cookie|x-api-key|api[_-]?key|token|password|passwd|secret|client_secret)\s*[:=]\s*[^\s,;]+",
        r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@",
        r"(?i)(bearer)\s+[^\s,;]+",
    ):
        message = re.sub(pattern, r"\1=<redacted>", message)
    return f"{type(exc).__name__}: {message}"


EVENT_SOURCE_TYPES = {
    "announcement", "announcement_pdf", "interactive_qa",
    "research_report", "investor_relations_event",
}


def resolve_collection_window(source_type: str, as_of_date: date) -> tuple[date | None, date]:
    if source_type in EVENT_SOURCE_TYPES:
        return date(as_of_date.year - 3, 1, 1), as_of_date
    if source_type in {"official_product_page", "company_profile", "patent"}:
        return None, as_of_date
    raise ValueError(f"unknown source window: {source_type}")


def current_support_status(document: RawDocument, as_of_date: date) -> str:
    metadata = document.metadata or {}
    if document.doc_type == "patent":
        status = str(metadata.get("legal_status") or "").casefold()
        checked = parse_date(metadata.get("legal_status_date"))
        return "current" if status in {"active", "granted"} and checked and checked <= as_of_date else "historical_only"
    if document.doc_type == "official_product_page":
        checked = parse_date(metadata.get("verified_current_date"))
        if metadata.get("currently_offered") is True and checked and checked <= as_of_date:
            return "current"
        return "pending_review"
    start_date, _ = resolve_collection_window(document.doc_type or "announcement", as_of_date)
    published = parse_date(document.publish_time)
    return "current" if published and (start_date is None or published >= start_date) else "historical_only"


@dataclass(frozen=True)
class CollectionTask:
    mapping_id: str
    requirement_id: str
    company_code: str
    company_name: str
    queries: tuple[str, ...]
    product_terms: tuple[str, ...] = ()
    scene_terms: tuple[str, ...] = ()
    negative_examples: tuple[str, ...] = ()
    require_product_and_scene: bool = True


@dataclass(frozen=True)
class UnmappedDiscoveryTask:
    chain_id: str
    requirement_id: str
    product_terms: tuple[str, ...]
    scene_terms: tuple[str, ...]
    negative_examples: tuple[str, ...]
    require_product_and_scene: bool
    seed_company_codes: tuple[str, ...] = ()
    allowed_company_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterResult:
    documents: tuple[RawDocument, ...]
    failed_tasks: tuple[str, ...]
    errors: tuple[str, ...]
    status: Literal["success", "partial_success", "empty"]
    network_requests: int = 0


class LocalEvidenceAdapter:
    def __init__(self, repository):
        self.repository = repository

    def collect(self, tasks: list[CollectionTask], *, as_of_date: date) -> AdapterResult:
        documents: list[RawDocument] = []
        failed: list[str] = []
        errors: list[str] = []
        for task in tasks:
            try:
                documents.extend(self.repository.fetch_local_documents(task, as_of_date))
            except Exception as exc:
                failed.append(f"{task.mapping_id}:{task.requirement_id}")
                errors.append(sanitize_error(exc))
        status = "partial_success" if failed or errors else ("success" if documents else "empty")
        return AdapterResult(tuple(documents), tuple(failed), tuple(errors), status)


class OfficialGapAdapter:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def collect(
        self,
        tasks: list[CollectionTask],
        *,
        as_of_date: date,
        source_limits: Mapping[str, int],
    ) -> AdapterResult:
        documents: list[RawDocument] = []
        failed: list[str] = []
        errors: list[str] = []
        requests = 0
        task_limit = source_limits.get("mapped_official_tasks", 100)
        if len(tasks) > task_limit:
            errors.append(f"source_limit_skipped_tasks:{len(tasks) - task_limit}")
        for task in tasks[:task_limit]:
            try:
                fetched, request_count = self.fetcher.fetch(
                    task,
                    as_of_date=as_of_date,
                    document_limit=source_limits.get("mapped_cninfo_documents_per_task", 20),
                    pages_per_company=source_limits.get("official_pages_per_company", 2),
                )
                documents.extend(fetched)
                requests += request_count
            except Exception as exc:
                failed.append(f"{task.mapping_id}:{task.requirement_id}")
                errors.append(sanitize_error(exc))
        status = "partial_success" if failed or errors else ("success" if documents else "empty")
        return AdapterResult(tuple(documents), tuple(failed), tuple(errors), status, requests)


class OfficialDiscoveryAdapter:
    def __init__(self, fetcher):
        self.fetcher = fetcher

    def collect(self, tasks, *, as_of_date: date, source_limits: Mapping[str, int]) -> AdapterResult:
        documents: list[RawDocument] = []
        errors: list[str] = []
        requests = 0
        for task in tasks:
            try:
                fetched, request_count = self.fetcher.fetch_unmapped(
                    task,
                    as_of_date=as_of_date,
                    document_limit=source_limits.get("official_discovery_documents", 50),
                    company_limit=source_limits.get("official_discovery_companies", 20),
                    pages_per_company=source_limits.get("official_pages_per_company", 2),
                )
                documents.extend(fetched)
                requests += request_count
            except Exception as exc:
                errors.append(sanitize_error(exc))
        status = "partial_success" if errors else ("success" if documents else "empty")
        return AdapterResult(tuple(documents), (), tuple(errors), status, requests)


class ScopedOfficialFetcher:
    def __init__(self, *, cninfo_fetch, ir_fetch):
        self.cninfo_fetch = cninfo_fetch
        self.ir_fetch = ir_fetch

    def fetch(
        self,
        task: CollectionTask,
        *,
        as_of_date: date,
        document_limit: int,
        pages_per_company: int,
    ) -> tuple[list[RawDocument], int]:
        event_start, _ = resolve_collection_window("announcement", as_of_date)
        product_start, _ = resolve_collection_window("official_product_page", as_of_date)
        cninfo_documents, cninfo_requests = self.cninfo_fetch(
            company_codes=(task.company_code,),
            as_of_date=as_of_date,
            start_date=event_start,
            limit=document_limit,
        )
        ir_documents, ir_requests = self.ir_fetch(
            company_codes=(task.company_code,),
            as_of_date=as_of_date,
            start_date=product_start,
            pages_per_company=pages_per_company,
        )
        documents = [*cninfo_documents, *ir_documents]
        queries = tuple(item.casefold() for item in task.queries)
        filtered = [
            item for item in documents
            if normalize_stock_code(item.company_code) == normalize_stock_code(task.company_code)
            and any(query in f"{item.title} {item.content_text}".casefold() for query in queries)
        ]
        return filtered, cninfo_requests + ir_requests


class ScopedOfficialDiscoveryFetcher:
    def __init__(self, *, global_cninfo_fetch, ir_fetch):
        self.global_cninfo_fetch = global_cninfo_fetch
        self.ir_fetch = ir_fetch

    def fetch_unmapped(
        self,
        task: UnmappedDiscoveryTask,
        *,
        as_of_date: date,
        document_limit: int,
        company_limit: int,
        pages_per_company: int,
    ) -> tuple[list[RawDocument], int]:
        documents, requests = self.global_cninfo_fetch(
            product_terms=task.product_terms,
            scene_terms=task.scene_terms,
            require_product_and_scene=task.require_product_and_scene,
            allowed_company_codes=task.allowed_company_codes,
            as_of_date=as_of_date,
            limit=document_limit,
        )
        allowed = {normalize_stock_code(code) for code in task.allowed_company_codes}
        if allowed:
            documents = [
                item for item in documents
                if normalize_stock_code(item.company_code) in allowed
            ]
        seeds = [
            code for code in task.seed_company_codes
            if not allowed or normalize_stock_code(code) in allowed
        ][:company_limit]
        if seeds:
            ir_documents, ir_requests = self.ir_fetch(
                company_codes=seeds,
                start_date=None,
                as_of_date=as_of_date,
                pages_per_company=pages_per_company,
            )
            documents.extend(ir_documents)
            requests += ir_requests
        return documents, requests
~~~

The local adapter reads stock_profiles, fina_mainbz, available announcement tables, interact_qa, available IR Q&A tables, research_reports_tushare, patent tables and raw_evidence_documents. It checks table existence, applies resolve_collection_window separately per source and reports missing sources. RawDocument is imported from supply_chain_data_collection_center; the adapter does not define a competing document schema.

For every returned document, persist_adapter_result() records current_support_status. current documents may create pending mapped facts. pending_review documents may create pending facts but cannot score until review supplies the missing current-status evidence. historical_only documents are retained as raw history and gap explanation but do not create a current scoring fact.

Before writing any automatic fact or expectation monitor, sanitize_pending_metadata() removes the reserved review_normalization key while preserving other metadata. Only Task 4 review methods may create that key.

The official product fetcher sets currently_offered=true and verified_current_date=as_of_date only when the product page returns successfully and the same page contains the configured product and scene terms. The patent adapter records legal_status and legal_status_date from the official patent-status source. Neither flag confirms the business fact; both still enter manual review as pending.

The official adapter reuses CNINFO PDF parsing, normalize_website_url(), extract_relevant_official_links(), html_to_text() and content hashing through the new pure fetch helpers in Step 4. It accepts explicit CollectionTask rows; it never calls the legacy full-pool commands.

ScopedOfficialFetcher uses task.product_terms, task.scene_terms and task.negative_examples separately. For an official product page it sets currently_offered only when the same page has at least one product term, the required scene condition and no negative example; requirements with require_product_and_scene=false waive only the scene condition. A generic query hit alone stays pending_review.

- [ ] **Step 4: Scope official fetch helpers**

Extract two document-only helpers from the existing commands:

~~~python
def fetch_cninfo_documents(
    pg_url: str,
    *,
    company_codes: tuple[str, ...],
    start_date: date | None,
    as_of_date: date,
    limit: int = 20,
    session=None,
) -> tuple[list[RawDocument], int]:
    """Return (documents, HTTP request count); no job rows, fact rows or commits."""


def fetch_official_ir_documents(
    pg_url: str,
    *,
    company_codes: tuple[str, ...],
    start_date: date | None,
    as_of_date: date,
    limit: int = 10,
    pages_per_company: int = 2,
    session=None,
) -> tuple[list[RawDocument], int]:
    """Return (documents, HTTP request count); no job rows, fact rows or commits."""


def fetch_cninfo_keyword_documents(
    *,
    product_terms: tuple[str, ...],
    scene_terms: tuple[str, ...],
    require_product_and_scene: bool,
    allowed_company_codes: tuple[str, ...],
    as_of_date: date,
    limit: int,
    session=None,
) -> tuple[list[RawDocument], int]:
    """Search CNINFO globally by product+scene and return documents plus request count."""
~~~

Filter candidate rows inside these helpers:

~~~python
normalized_codes = {normalize_stock_code(code) for code in company_codes}
if normalized_codes:
    rows = [row for row in rows if normalize_stock_code(row["code"]) in normalized_codes]
if as_of_date is not None:
    rows = [
        row for row in rows
        if row.get("publish_date") is None
        or (
            row["publish_date"] <= as_of_date
            and (start_date is None or row["publish_date"] >= start_date)
        )
    ]
~~~

fetch_cninfo_keyword_documents() submits separate quoted product+scene queries to the official CNINFO announcement search, deduplicates by announcement ID before downloading PDFs, stops at limit, keeps only announcements from January 1 of as_of_date.year-3 through as_of_date and returns company_code from the announcement payload. The session is injectable; tests use recorded search JSON and PDF bytes. The existing fetch_cninfo_pdf_announcements() and fetch_official_ir_pages() remain backward-compatible commands: they call the helpers and then use the legacy persistence path. ScopedOfficialFetcher and ScopedOfficialDiscoveryFetcher call only the document helpers. Documents with unknown publication date may be stored as pending, but the scorer excludes them.

- [ ] **Step 5: Implement repository methods and stable IDs**

~~~text
fetch_mappings(chain_id, mapping_ids, company_codes)
fetch_independent_discovery_requirements(chain_id)
fetch_candidate_universe(as_of_date, requirement, company_codes, limit)
fetch_discovery_seed_companies(as_of_date, requirement, limit)
persist_discovery_hit(hit, job_id)
list_candidate_proposals(job_id)
fetch_asof_facts(mapping_ids, cutoff)
fetch_gap_rows(mapping_ids)
upsert_node_dimension_updates(updates, as_of_date)
upsert_candidate_mapping(candidate)
upsert_gap_rows(gaps, as_of_date)
start_job(request)
finish_job(job_id, result)
persist_pending_document(document, mapping_id, requirement_id, job_id, as_of_date)
~~~

The independent discovery transaction is ordered and idempotent:

~~~text
fetch_candidate_universe scoped by the requirement's product/scene terms and cutoff
→ propose_independent_candidates
→ persist raw document and pending discovery fact with mapping_id NULL and no event
→ upsert candidate mapping from deterministic proposal
→ attach subsequent collection tasks to the new mapping_id
~~~

No repository method is allowed to guess a mapping from company_code. A company with force-sensor and tactile-sensor mappings receives separate facts for separate CollectionTask rows.

business_tag_mapping has no dedicated technology_route_id column. upsert_candidate_mapping() stores requirement_id and technology_route_id inside the provenance object in l1_l8_path. fetch_mappings() deterministically enriches every row by first reading that provenance and otherwise resolving tag_name through get_business_evidence_requirement(). If a route-bearing requirement cannot be resolved exactly once, the mapping is excluded with unresolved_technology_route; it must never fall through to an unrestricted route gate.

On conflict, upsert_candidate_mapping() may only append deduplicated discovery_doc_ids/discovery_fact_ids and fill previously NULL structural fields. It must preserve the higher existing status, never reduce confidence, never replace non-empty evidence_ids and never overwrite reviewer-approved mapping fields with a candidate proposal.

Stable keys:

~~~text
mapping_id = hash(chain_id, company_code, requirement_id)
doc_id   = hash(source_id, url, title, normalized_content)
fact_id  = hash(doc_id, mapping_id or "unmapped", requirement_id, publish_date, normalized_quote)
event_id = hash(fact_id, mapping_id)  # mapped facts only
~~~

dry-run callers never invoke an upsert method.

- [ ] **Step 6: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_adapters.py services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py tools/tests/test_supply_chain_data_collection_center.py
git add tools/supply_chain_evidence_adapters.py services/screener-service/app/domains/supply_chain/evidence_orchestration_repository.py tools/tests/test_supply_chain_evidence_adapters.py services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py tools/supply_chain_data_collection_center.py
git commit -m "feat: add scoped supply-chain evidence adapters"
~~~

Expected: a failed network task produces partial_success; errors do not expose credentials.

---

### Task 7: Build orchestration modes and reports

**Files:**

- Create: tools/supply_chain_evidence_orchestrator.py
- Create: tools/supply_chain_evidence_report.py
- Create: tools/run_supply_chain_evidence_orchestration.py
- Create: tools/tests/test_supply_chain_evidence_orchestrator.py
- Create: tools/tests/test_supply_chain_evidence_report.py

**Interfaces:**

- Consumes: Tasks 1, 2, 5 and 6.
- Produces: run_evidence_orchestration() and render_evidence_report().
- Consumed by: Task 10.

- [ ] **Step 1: Write mode and report tests**

~~~python
def test_dry_run_has_no_network_or_writes():
    result = run_evidence_orchestration(
        EvidenceRunRequest("dexterous_hand", date(2026, 7, 9), "dry-run", "local-first"),
        repository=FakeRepository(),
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=FailIfCalled(),
    )
    assert result.writes == 0
    assert result.network_requests == 0


def test_collect_does_not_score_or_change_pool():
    score_runner = SpyScoreRunner()
    result = run_evidence_orchestration(
        EvidenceRunRequest("dexterous_hand", date(2026, 7, 9), "collect", "official-gap"),
        repository=FakeRepository(),
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter(),
        official_adapter=FakeAdapter(),
        score_runner=score_runner,
    )
    assert score_runner.calls == []
    assert result.pool_transitions == 0


def test_report_labels_pending_evidence_as_pending():
    markdown = render_evidence_report(result_with_pending_fact())
    assert "待审核" in markdown
    assert "已确认订单" not in markdown


def test_score_mode_updates_only_audited_node_dimensions_before_scoring():
    repository = FakeRepository(audited_facts=[audited_dimension_fact("physical_bom")])
    score_runner = SpyScoreRunner()
    run_evidence_orchestration(
        EvidenceRunRequest("dexterous_hand", date(2026, 7, 9), "score", "local-first"),
        repository=repository,
        local_adapter=FailIfCalledAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=score_runner,
    )
    assert [item.dimension_id for item in repository.dimension_updates] == ["physical_bom"]
    assert score_runner.calls[0]["mapping_ids"] == repository.mapping_ids


def test_company_scoped_run_never_persists_global_discovery_outside_scope():
    repository = FakeRepository(mappings=[], official_documents=[
        axis_document("in-scope", "688001"),
        axis_document("out-of-scope", "688002"),
    ])
    run_evidence_orchestration(
        EvidenceRunRequest(
            "dexterous_hand", date(2026, 7, 9), "collect", "official-gap",
            company_codes=("688001",),
        ),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeOfficialDiscoveryAdapter(repository.official_documents),
        official_adapter=FakeAdapter(),
        score_runner=FailIfCalled(),
    )
    assert repository.persisted_discovery_codes == ["688001"]
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_orchestrator.py tools/tests/test_supply_chain_evidence_report.py
~~~

Expected: orchestration and report modules are missing.

- [ ] **Step 3: Implement exact mode semantics**

- dry-run: read-only, no network, no job rows and transaction rollback.
- collect: local-first, official-gap if requested, write pending documents/facts/events, no scoring.
- score: call run_batch_score() only; it reads approved evidence.
- full: collect sequence; score only when allow_score=True.

Before approved scoring, score and full modes call build_node_dimension_updates() with confirmed facts and persist those updates. Pending collection never changes supply_chain_node_dimensions.

The result and public function are:

~~~python
@dataclass(frozen=True)
class EvidenceRunResult:
    chain_id: str
    as_of_date: date
    mode: RunMode
    candidate_count: int
    requirement_count: int
    local_hits: int
    official_discovery_hits: int
    official_gap_hits: int
    inserted_documents: int
    duplicate_documents: int
    pending_facts: int
    approved_facts: int
    failed_tasks: tuple[str, ...]
    pool_counts: Mapping[str, int]
    pool_transitions: int
    writes: int
    network_requests: int
    data_limitations: tuple[str, ...]
    companies: tuple[Mapping[str, Any], ...]


def run_evidence_orchestration(
    request: EvidenceRunRequest,
    *,
    repository,
    local_adapter,
    official_discovery_adapter,
    official_adapter,
    score_runner,
) -> EvidenceRunResult:
    mappings = repository.fetch_mappings(
        request.chain_id,
        request.mapping_ids,
        request.company_codes,
    )
    scope_active, discovery_codes = resolve_discovery_scope(request, mappings)
    discovery_hits = []
    if request.mode != "score" and not (scope_active and not discovery_codes):
        for requirement in repository.fetch_independent_discovery_requirements(request.chain_id):
            universe = repository.fetch_candidate_universe(
                request.as_of_date,
                requirement,
                discovery_codes,
                request.source_limits.get("discovery", 5000),
            )
            discovery_hits.extend(propose_independent_candidates(
                universe,
                requirement=requirement,
                as_of_date=request.as_of_date,
            ))
    candidates = build_candidates(mappings, tuple(discovery_hits), request)
    gaps = plan_run_gaps(candidates, repository, request)
    if request.mode == "dry-run":
        return build_result(request, candidates, gaps, writes=0, network_requests=0)
    if request.mode == "score":
        return run_approved_score(request, repository, score_runner)

    job_id = repository.start_job(request)
    official_discovery_result = empty_adapter_result()
    if request.source_policy == "official-gap":
        discovery_tasks = build_unmapped_discovery_tasks(
            repository.fetch_independent_discovery_requirements(request.chain_id),
            tuple(discovery_hits),
            repository,
            request,
            mappings,
        )
        if discovery_tasks:
            official_discovery_result = official_discovery_adapter.collect(
                discovery_tasks,
                as_of_date=request.as_of_date,
                source_limits=request.source_limits,
            )
            for requirement in repository.fetch_independent_discovery_requirements(request.chain_id):
                discovery_hits.extend(propose_independent_candidates(
                    official_discovery_result.documents,
                    requirement=requirement,
                    as_of_date=request.as_of_date,
                ))
    for hit in discovery_hits:
        outcome = repository.persist_discovery_hit(hit, job_id)
        if outcome.proposal is not None:
            repository.upsert_candidate_mapping(outcome.proposal)
    mappings = repository.fetch_mappings(
        request.chain_id,
        request.mapping_ids,
        request.company_codes,
    )
    candidates = build_candidates(mappings, (), request)
    gaps = plan_run_gaps(candidates, repository, request)
    tasks = build_collection_tasks(gaps)
    local_result = local_adapter.collect(
        tasks,
        as_of_date=request.as_of_date,
    )
    persisted = repository.persist_adapter_result(job_id, local_result, request)
    remaining = replan_after_persist(candidates, repository, request)
    official_result = empty_adapter_result()
    if request.source_policy == "official-gap" and remaining:
        official_result = official_adapter.collect(
            build_collection_tasks(remaining),
            as_of_date=request.as_of_date,
            source_limits=request.source_limits,
        )
        persisted += repository.persist_adapter_result(job_id, official_result, request)
    score_result = None
    if request.mode == "full" and request.allow_score:
        score_result = run_approved_score(request, repository, score_runner)
    result = build_result_from_runs(
        request,
        candidates,
        gaps,
        local_result,
        official_discovery_result,
        official_result,
        persisted,
        score_result,
    )
    repository.finish_job(job_id, result)
    return result
~~~

Define the helpers with these contracts:

~~~python
def build_candidates(mappings, discovery_hits, request) -> tuple[Mapping[str, Any], ...]:
    """Merge by deterministic mapping_id; never merge evidence across mappings."""


def plan_run_gaps(candidates, repository, request) -> tuple[EvidenceGap, ...]:
    facts = repository.fetch_asof_facts(
        tuple(item["mapping_id"] for item in candidates),
        cutoff=end_of_day_shanghai(request.as_of_date),
    )
    return tuple(plan_evidence_gaps(candidates, facts, request.as_of_date))


def build_collection_tasks(gaps) -> list[CollectionTask]:
    """Create tasks for missing/stale/proxy gaps and copy grouped terms from the requirement."""


def resolve_discovery_scope(request, mappings) -> tuple[bool, tuple[str, ...]]:
    if request.company_codes:
        return True, tuple(sorted({normalize_stock_code(code) for code in request.company_codes}))
    if request.mapping_ids:
        return True, tuple(sorted({normalize_stock_code(row["code"]) for row in mappings}))
    return False, ()


def build_unmapped_discovery_tasks(requirements, hits, repository, request, mappings):
    scope_active, allowed_codes = resolve_discovery_scope(request, mappings)
    if scope_active and not allowed_codes:
        return []
    tasks = []
    for requirement in requirements:
        existing_codes = {
            hit.company_code
            for hit in hits
            if hit.eligible_for_mapping
            and hit.requirement_id == requirement["requirement_id"]
        }
        seeds = [
            code
            for code in repository.fetch_discovery_seed_companies(
                request.as_of_date,
                requirement,
                request.source_limits.get("official_discovery_companies", 20),
            )
            if code not in existing_codes
        ]
        tasks.append(UnmappedDiscoveryTask(
            chain_id=request.chain_id,
            requirement_id=requirement["requirement_id"],
            product_terms=tuple(requirement["product_terms"]),
            scene_terms=tuple(requirement["scene_terms"]),
            negative_examples=tuple(requirement["negative_examples"]),
            require_product_and_scene=bool(requirement.get("require_product_and_scene", True)),
            seed_company_codes=tuple(seeds),
            allowed_company_codes=allowed_codes,
        ))
    return tasks


def run_approved_score(request, repository, score_runner):
    scoped_mappings = repository.fetch_mappings(
        request.chain_id,
        request.mapping_ids,
        request.company_codes,
    )
    scoped_mapping_ids = [item["mapping_id"] for item in scoped_mappings]
    if not scoped_mapping_ids:
        return build_empty_score_result(request, reason="no_scoped_mappings")
    audited = repository.fetch_audited_scoring_facts(
        tuple(scoped_mapping_ids),
        end_of_day_shanghai(request.as_of_date),
    )
    updates = build_node_dimension_updates_by_node(audited, request.as_of_date)
    repository.upsert_node_dimension_updates(updates, request.as_of_date)
    return score_runner(
        chain_id=request.chain_id,
        trade_date=request.as_of_date,
        mapping_ids=scoped_mapping_ids,
        dry_run=False,
    )
~~~

When source_policy is official-gap, build_unmapped_discovery_tasks() always emits one bounded official-search task for every independent requirement. An unscoped request searches globally. A company_codes request filters every local/global result to those codes; a mapping_ids request first resolves those mappings to company codes and uses that allow-list. Local hits only remove duplicate seed company codes; they never disable official discovery for other in-scope companies. Stable document and mapping IDs make the combined local/official result idempotent.

replan_after_persist() repeats plan_run_gaps(); empty_adapter_result() returns AdapterResult((), (), (), "empty"); build_empty_score_result() returns zero candidates and the supplied limitation. build_result() and build_result_from_runs() include mapped official gaps and unmapped official discovery counts, sum network_requests from both adapters, fill every EvidenceRunResult field from returned counts and never infer approved_facts from pending_facts. Only repository and adapter calls perform I/O.

The result includes candidate_count, requirement_count, local_hits, official_discovery_hits, official_gap_hits, inserted_documents, duplicate_documents, pending_facts, approved_facts, failed_tasks, pool_counts, pool_transitions, data_limitations and per-company detail.

- [ ] **Step 4: Implement CLI and report output**

Exact CLI arguments:

~~~text
--chain-id
--as-of-date
--mode dry-run|collect|score|full
--source-policy local-first|official-gap
--source-limit key=value (repeatable; validated by EvidenceRunRequest)
--mapping-id (repeatable)
--company-code (repeatable)
--allow-score
--pg-url
--output-dir
~~~

Write result.json and report.md only when output-dir is supplied. The Markdown report contains approved, pending, rejected, gaps, next actions, the 8-layer by 8-dimension matrix, four pools, AF search and limitations. The dimension columns are exactly function_value, technology_route, physical_bom, value_pool, competition_moat, supply_demand_cycle, evidence_validation and market_expectation. Every cell displays known, proxy, unknown or contradicted, plus evidence_ids when present. No cell is changed merely because another cell on the same layer has evidence.

The CLI assembles real dependencies, not fake test doubles:

~~~python
repository = EvidenceOrchestrationRepository(connection_factory=pg_connection_factory(args.pg_url))
local_adapter = LocalEvidenceAdapter(repository)
official_fetcher = ScopedOfficialFetcher(
    cninfo_fetch=partial(fetch_cninfo_documents, args.pg_url),
    ir_fetch=partial(fetch_official_ir_documents, args.pg_url),
)
official_adapter = OfficialGapAdapter(official_fetcher)
official_discovery_adapter = OfficialDiscoveryAdapter(
    ScopedOfficialDiscoveryFetcher(
        global_cninfo_fetch=fetch_cninfo_keyword_documents,
        ir_fetch=partial(fetch_official_ir_documents, args.pg_url),
    )
)
result = run_evidence_orchestration(
    request,
    repository=repository,
    local_adapter=local_adapter,
    official_discovery_adapter=official_discovery_adapter,
    official_adapter=official_adapter,
    score_runner=partial(run_batch_score, pg_url=args.pg_url, model_version="v2.0"),
)
~~~

Add one PostgreSQL-marked adapter integration test that inserts a temporary local raw document and proves the real LocalEvidenceAdapter returns it for the exact mapping/requirement. Keep network disabled in this test. Official fetcher unit tests inject recorded HTML/PDF bytes and assert company/as_of filters; they do not make live HTTP calls.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_supply_chain_evidence_orchestrator.py tools/tests/test_supply_chain_evidence_report.py
git add tools/supply_chain_evidence_orchestrator.py tools/supply_chain_evidence_report.py tools/run_supply_chain_evidence_orchestration.py tools/tests/test_supply_chain_evidence_orchestrator.py tools/tests/test_supply_chain_evidence_report.py
git commit -m "feat: orchestrate supply-chain evidence collection"
~~~

Expected: all modes pass isolated tests and pending facts remain labeled.

---

### Task 8: Replace hard-coded evidence levels with E/AF double gates

**Files:**

- Modify: packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py:1-430
- Modify: tools/score_supply_chain_selection_v2.py:52-60,110-386
- Modify: packages/kronos-factors/tests/test_supply_chain_selection_v2.py
- Modify: tools/tests/test_score_supply_chain_selection_v2.py

**Interfaces:**

- Consumes: Task 1 catalog, Task 2 template and Task 5 AF classifier.
- Produces: PoolGateResult, derive_evidence_gate(), derive_route_gate() and combine_pool_gates().
- Consumed by: Task 9 and Task 10.

- [ ] **Step 1: Write E/AF gate tests**

~~~python
def test_af0_excludes_even_when_revenue_evidence_is_e6():
    result = score_mapping(
        axial_mapping(),
        e6_automotive_facts(),
        trade_date=date(2026, 7, 9),
        node_score=80,
    )
    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "excluded"
    assert "axis_flux_af0" in result["selection"]["blocking_gate"]


def test_e4_plus_af1_is_capped_at_d():
    result = score_mapping(
        axial_mapping(),
        e4_plus_af1_facts(),
        trade_date=date(2026, 7, 9),
        node_score=80,
    )
    assert result["selection"]["pool_code"] == "D"


def test_axial_tag_without_explicit_route_is_resolved_not_unrestricted():
    mapping = axial_mapping()
    mapping.pop("technology_route_id", None)
    result = score_mapping(
        mapping,
        e6_automotive_facts(),
        trade_date=date(2026, 7, 9),
        node_score=80,
    )
    assert result["selection"]["eligibility_status"] == "excluded"
    assert "axis_flux_af0" in result["selection"]["blocking_gate"]


def test_independent_axial_discovery_is_e1_but_af0_excluded_until_route_approval():
    result = score_mapping(
        independent_axial_candidate_mapping(discovery_fact_ids=["pending-axis-1"]),
        [],
        trade_date=date(2026, 7, 9),
        node_score=None,
    )
    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] is None
    assert result["selection"]["eligibility_status"] == "excluded"
    assert result["selection"]["blocking_gate"] == "axis_flux_af0"


def test_traceable_candidate_mapping_is_e1_without_inheriting_source_evidence():
    result = score_mapping(
        derived_candidate_mapping(provenance_mapping_id="source-m1", evidence_ids=[]),
        [],
        trade_date=date(2026, 7, 9),
        node_score=None,
    )
    assert result["authenticity"]["evidence_level"] == "E1"
    assert result["selection"]["pool_code"] == "D"
    assert result["evidence_ids"] == []


def test_stale_customer_validation_downgrades_evidence_gate():
    gate = derive_evidence_gate(
        traceable_mapping(),
        [approved_customer_validation(publish_date=date(2025, 1, 1))],
        load_evidence_requirements(),
        as_of_date=date(2026, 7, 9),
    )
    assert gate.level == "E1"
    assert "stale_customer_validation" in gate.reasons


def test_legacy_confirmed_without_audit_fields_is_ignored():
    result = score_mapping(
        traceable_mapping(),
        [confirmed_fact(reviewer=None, reviewed_at=None)],
        trade_date=date(2026, 7, 9),
        node_score=None,
    )
    assert result["authenticity"]["evidence_level"] == "E1"


def test_legacy_approved_stage_without_audited_source_event_is_ignored():
    mapping = repository_mapping_with_stage(
        commercial_stage="C5",
        stage_review_status="approved",
        source_event_reviewer=None,
    )
    prepared = prepare_mapping_for_score(mapping, trade_date=date(2026, 7, 9))
    assert prepared["commercial_stage"] is None
~~~

Add a parameterized E1-E6 test with expected caps D/C/B/A/A/A. Keep existing no-lookahead and pending-evidence tests.

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py tools/tests/test_score_supply_chain_selection_v2.py
~~~

Expected: AF exclusion and config-driven gates fail.

- [ ] **Step 3: Implement gate value objects**

~~~python
@dataclass(frozen=True)
class PoolGateResult:
    eligible: bool
    max_pool_code: str | None
    level: str
    matched_fact_ids: tuple[str, ...]
    reasons: tuple[str, ...]


def combine_pool_gates(*gates: PoolGateResult) -> PoolGateResult:
    excluded = [gate for gate in gates if not gate.eligible]
    if excluded:
        reasons = tuple(reason for gate in excluded for reason in gate.reasons)
        return PoolGateResult(False, None, excluded[0].level, (), reasons)
    rank = {"D": 1, "C": 2, "B": 3, "A": 4}
    capped_gates = [gate for gate in gates if gate.max_pool_code]
    facts = tuple(sorted({fact for gate in gates for fact in gate.matched_fact_ids}))
    reasons = tuple(reason for gate in gates for reason in gate.reasons)
    if not capped_gates:
        return PoolGateResult(True, None, "unrestricted", facts, reasons)
    capped = min(capped_gates, key=lambda gate: rank[gate.max_pool_code])
    return PoolGateResult(True, capped.max_pool_code, capped.level, facts, reasons)
~~~

derive_evidence_gate(mapping, confirmed_facts, requirements, *, as_of_date) reads Task 1 configuration. It applies each evidence type's expiry_policy on the scoring date before selecting the highest level. Expired evidence remains in explanation output with stale_reason but cannot preserve its old pool cap. derive_route_gate() returns an unrestricted eligible gate when the mapping has no technology_route_id or the resolved route has no configured authenticity_ladder. For the axial route it requires the matching industry template and reads AF0-AF6. Remove EVIDENCE_MAX_POOL and hard-coded evidence/order maps from the scoring tool.

E1 has one explicit provenance rule. A candidate mapping is E1 when its l1_l8_path contains either a non-empty derived_from_mapping_id or non-empty discovery_fact_ids array and its status is candidate/pending_review/verified. This proves a traceable lead only. It does not read source-mapping evidence_ids and cannot become E2 without an audited fact.

resolve_mapping_technology_route() checks, in order, explicit mapping value, provenance technology_route_id, then the template requirement resolved from tag_name. A route-bearing requirement that cannot resolve exactly once returns an ineligible unresolved_route gate, not an unrestricted gate. This rule is covered by both pure scorer tests and the Task 6 PostgreSQL round-trip test.

Change _confirmed_evidence() so it filters by publication cutoff, validation_status=confirmed, non-empty reviewer, non-empty review_note and reviewed_at on or before the cutoff, but does not globally require fact_nature=confirmed_fact. Legacy confirmed rows without complete audit fields are returned only as limitations and are never score inputs. derive_evidence_gate() then applies each evidence type's allowed_fact_natures and expiry policy. E4-E6 still require confirmed_fact because Task 1 config states that rule; approved company claims can support only the lower levels permitted by config.

run_batch_score() may populate commercial_stage only from a business_tag_stage_tracking row with review_status=approved whose source event is also approved, has a non-empty reviewer, non-empty review_note, reviewed_at no later than cutoff and event_date no later than the scoring date. Otherwise commercial_stage is NULL and the explanation includes unaudited_commercial_stage. The pure score_mapping() still accepts explicit test inputs, but the PostgreSQL path never trusts an unaudited stage.

- [ ] **Step 4: Extend score mapping and pool assignment**

Extend score_mapping() with evidence_requirements: EvidenceRequirementCatalog | None = None and industry_template: Mapping[str, Any] | None = None. Insert this block after confirmed evidence is filtered and before assign_selection_pool():

~~~python
catalog = evidence_requirements or load_evidence_requirements()
template = industry_template
chain_id = str(mapping.get("chain_id") or "")
if template is None and chain_id:
    template = get_industry_template(chain_id)
route_id = resolve_mapping_technology_route(mapping, template)
mapping_for_gate = {**mapping, "technology_route_id": route_id}
evidence_gate = derive_evidence_gate(
    mapping_for_gate,
    confirmed,
    catalog,
    as_of_date=trade_date,
)
route_gate = derive_route_gate(mapping_for_gate, confirmed, template)
combined_gate = combine_pool_gates(evidence_gate, route_gate)
pool_inputs["max_pool_code"] = combined_gate.max_pool_code
pool_inputs["hard_exclusion_reasons"] = list(combined_gate.reasons) if not combined_gate.eligible else []
pool = assign_selection_pool(pool_inputs, configured_profile)
~~~

Pass hard_exclusion_reasons to assign_selection_pool(). A non-empty list returns pool_code=None and eligibility_status=excluded. A route cap can lower a pool; it cannot raise the evidence pool.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py tools/tests/test_score_supply_chain_selection_v2.py packages/kronos-factors/tests/test_industry_chain_templates.py
git add packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py tools/score_supply_chain_selection_v2.py packages/kronos-factors/tests/test_supply_chain_selection_v2.py tools/tests/test_score_supply_chain_selection_v2.py
git commit -m "feat: enforce evidence and route pool gates"
~~~

Expected: E0-E6 and AF0-AF6 tests pass; no-lookahead and NULL semantics remain green.

---

### Task 9: Supply approved expectation, catalyst and risk context to scoring and APIs

**Files:**

- Modify: packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py
- Modify: packages/kronos-factors/tests/test_supply_chain_selection_v2.py
- Modify: services/screener-service/app/domains/supply_chain/selection_repository.py:18-430
- Modify: tools/score_supply_chain_selection_v2.py:272-495
- Modify: services/screener-service/app/domains/supply_chain/models.py:11-54
- Modify: services/screener-service/app/domains/supply_chain/selection_router.py
- Modify: services/screener-service/app/domains/supply_chain/selection_service.py:18-135
- Modify: services/screener-service/tests/test_supply_chain_selection_repository.py
- Modify: services/screener-service/tests/test_supply_chain_selection_v2_api.py
- Modify: services/screener-service/tests/fixtures/openapi_paths.json
- Modify: services/api-gateway/tests/test_gateway_routes.py
- Modify: tools/tests/test_score_supply_chain_selection_v2.py

**Interfaces:**

- Consumes: approved facts from Task 4 and gates from Task 8.
- Produces: SelectionRepository.fetch_selection_context() and complete explanation fields.
- Consumed by: Task 10.

- [ ] **Step 1: Write failing context and API tests**

~~~python
def test_candidate_contract_reports_missing_catalyst():
    result = selection_service.list_selection_candidates(
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        pool=None,
        model_version="v2.0",
        limit=50,
        offset=0,
        repository=RepositoryWithMissingCatalyst(),
    )
    assert result["items"][0]["catalyst_score"] is None
    assert any("missing_catalyst_score" in item for item in result["items"][0]["data_limitations"])


def test_selection_context_requires_approved_claims_and_adjusted_prices():
    cursor = FakeCursor(selection_context_responses())
    repository = SelectionRepository(connection_factory=lambda: None)
    result = repository.fetch_selection_context(
        cursor,
        mapping_id="m1",
        code="003021",
        trade_date=date(2026, 7, 9),
        cutoff=datetime(2026, 7, 9, 15, 59, 59, tzinfo=timezone.utc),
    )
    sql = "\n".join(statement for statement, _ in cursor.executed)
    assert "review_status = 'approved'" in sql
    assert "reviewer IS NOT NULL" in sql
    assert "review_note" in sql
    assert "reviewed_at" in sql
    assert "adj_factor" in sql
    assert result["market_expectation_score"] is None


def test_approved_expectation_gap_uses_existing_formula_without_neutral_fill():
    inputs = ExpectationGapInputs(
        actual_progress_score=80,
        market_expectation_score=50,
        evidence_delta_score=40,
        claim_risk_penalty_score=20,
        evidence_ids=("progress-1", "expectation-1"),
    )
    assert calculate_approved_expectation_gap(inputs) == 35.0
    assert calculate_approved_expectation_gap(replace(inputs, market_expectation_score=None)) is None


def test_catalyst_aggregates_only_explicit_reviewed_scores():
    score = aggregate_catalyst_score([
        ApprovedScoreInput("c1", 80, "strong", 1.0, 0.9),
        ApprovedScoreInput("c2", 60, "mid", 0.5, 0.7),
    ])
    assert score.score == 74.4
    assert score.evidence_ids == ("c1", "c2")


def test_risk_uses_worst_explicit_reviewed_risk():
    score = aggregate_risk_score([
        ApprovedScoreInput("r1", 40, "strong", 0.9, 0.9),
        ApprovedScoreInput("r2", 70, "mid", 0.8, 0.7),
    ])
    assert score.score == 70
    assert score.evidence_ids == ("r2",)


def test_batch_score_does_not_commit_or_close_caller_owned_connection():
    connection = SpyConnection(batch_score_fixture_rows())
    run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        model_version="v2.0",
        dry_run=False,
        connection=connection,
    )
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
    assert connection.close_calls == 0


def test_batch_score_keeps_zero_argument_connection_factory_contract():
    factory = SpyZeroArgFactory(batch_score_fixture_rows())
    run_batch_score(
        pg_url="unused",
        chain_id="dexterous_hand",
        trade_date=date(2026, 7, 9),
        model_version="v2.0",
        dry_run=True,
        connection_factory=factory,
    )
    assert factory.calls == 1
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py services/screener-service/tests/test_supply_chain_selection_repository.py services/screener-service/tests/test_supply_chain_selection_v2_api.py tools/tests/test_score_supply_chain_selection_v2.py
~~~

Expected: the repository lacks selection context and the API omits catalyst_score.

- [ ] **Step 3: Implement approved-only context**

~~~python
@dataclass(frozen=True)
class ApprovedScoreInput:
    evidence_id: str
    score: float
    source_level: Literal["mid", "strong"]
    confidence: float
    source_reliability: float


@dataclass(frozen=True)
class AggregatedEvidenceScore:
    score: float | None
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExpectationGapInputs:
    actual_progress_score: float | None
    market_expectation_score: float | None
    evidence_delta_score: float | None
    claim_risk_penalty_score: float | None
    evidence_ids: tuple[str, ...]


def calculate_actual_progress_score(
    research_rank: int,
    commercialization_rank: int,
    evidence_delta_score: float,
) -> float:
    research = min(100.0, max(0, research_rank) / 6 * 100)
    commercial = min(100.0, max(0, commercialization_rank) / 7 * 100)
    stage_progress = research * 0.4 + commercial * 0.6
    return round(stage_progress * 0.65 + evidence_delta_score * 0.35, 4)


def calculate_approved_expectation_gap(inputs: ExpectationGapInputs) -> float | None:
    values = (
        inputs.actual_progress_score,
        inputs.market_expectation_score,
        inputs.evidence_delta_score,
        inputs.claim_risk_penalty_score,
    )
    if any(value is None for value in values):
        return None
    actual, market, delta, claim_risk = (float(value) for value in values)
    if any(value < 0 or value > 100 for value in (actual, market, delta, claim_risk)):
        return None
    raw = actual - market + delta * 0.35 - claim_risk * 0.45
    return round(min(100.0, max(0.0, raw)), 4)


def aggregate_catalyst_score(inputs: Sequence[ApprovedScoreInput]) -> AggregatedEvidenceScore:
    valid = [
        item for item in inputs
        if 0 <= item.score <= 100
        and item.source_level in {"mid", "strong"}
        and 0 <= item.confidence <= 1
        and 0 <= item.source_reliability <= 1
    ]
    if not valid:
        return AggregatedEvidenceScore(None, ())
    weights = [item.source_reliability * item.confidence for item in valid]
    total = sum(weights)
    if total <= 0:
        return AggregatedEvidenceScore(None, ())
    score = sum(item.score * weight for item, weight in zip(valid, weights)) / total
    return AggregatedEvidenceScore(
        round(score, 4),
        tuple(sorted(item.evidence_id for item in valid)),
    )


def aggregate_risk_score(inputs: Sequence[ApprovedScoreInput]) -> AggregatedEvidenceScore:
    valid = [
        item for item in inputs
        if 0 <= item.score <= 100
        and item.source_level in {"mid", "strong"}
        and 0 <= item.confidence <= 1
        and 0 <= item.source_reliability <= 1
    ]
    if not valid:
        return AggregatedEvidenceScore(None, ())
    worst = max(item.score for item in valid)
    ids = tuple(sorted(item.evidence_id for item in valid if item.score == worst))
    return AggregatedEvidenceScore(round(worst, 4), ids)


def fetch_selection_context(
    self,
    cur,
    *,
    mapping_id: str,
    code: str,
    trade_date: date,
    cutoff: datetime,
) -> dict[str, Any]:
    expectation = self._fetch_approved_expectation_inputs(cur, mapping_id, cutoff)
    catalyst_inputs = self._fetch_approved_catalyst_inputs(cur, mapping_id, trade_date, cutoff)
    risk_inputs = self._fetch_confirmed_risk_inputs(cur, mapping_id, cutoff)
    price_reaction = self._fetch_adjusted_price_reaction(cur, code, trade_date)
    expectation_gap = calculate_approved_expectation_gap(expectation)
    catalyst = aggregate_catalyst_score(catalyst_inputs)
    risk = aggregate_risk_score(risk_inputs)
    return {
        "expectation_gap_score": expectation_gap,
        "market_expectation_score": expectation.market_expectation_score,
        "catalyst_score": catalyst.score,
        "risk_score": risk.score,
        "adjusted_price_reaction": price_reaction,
        "selection_context_evidence_ids": sorted(
            set(expectation.evidence_ids)
            | set(catalyst.evidence_ids)
            | set(risk.evidence_ids)
        ),
    }
~~~

Implement _fetch_approved_expectation_inputs(), _fetch_approved_catalyst_inputs(), _fetch_confirmed_risk_inputs() and _fetch_adjusted_price_reaction() in the same repository. Each query applies the cutoff and review-status rules listed below.

Rules:

- every approved/confirmed query also requires non-empty reviewer, non-empty review_note and reviewed_at no later than cutoff;
- expectation gap uses the existing formula shown above and never uses the old neutral 50 fallback. research rank R0-R6 and commercialization rank C0-C7 come only from an audited stage. stage_progress is `research_rank/6*100*0.4 + commercialization_rank/7*100*0.6`; actual_progress is `stage_progress*0.65 + evidence_delta_score*0.35`. evidence_delta_score comes from an audited fact's metadata.review_normalization. market_expectation_score comes from an approved expectation monitor's metadata.review_normalization whose as_of_date equals the scoring date; the service also stores the recomputed adjusted 20-day return and it must match a fresh recomputation within 0.01 percentage point. claim_risk_penalty_score comes from approved missed/contradicted expectation claims, so it does not duplicate the separate route/market risk score. Every normalized value requires method_version and as_of_date no later than the score date. Any missing component returns NULL;
- catalyst reads approved expectation monitors with expected_date greater than trade_date, source date no later than cutoff, and explicit metadata.review_normalization.catalyst_score in 0..100. Source level and confidence come from the linked source document/fact. No explicit score or no future event returns NULL;
- risk reads audited negative facts, route failures and reproducible market-risk records, excluding missed/contradicted expectation claims already used in claim_risk_penalty_score. Each input must carry metadata.review_normalization.risk_score in 0..100 and method_version. The aggregate is the highest scored risk; a confirmed veto remains a separate pool rejection. Missing risk inputs return NULL;
- adjusted price reaction uses the scoring date and the 20th prior available trade row, joins daily_kline and adj_factor at both endpoints and calculates `(end_close * end_adj_factor) / (start_close * start_adj_factor) - 1`; missing close or factor returns NULL;
- old business_tag_expectation_gap_scores may be read only when score_detail.source_policy equals approved_only_v2, all evidence_ids resolve to audited rows and the stored price input passes the adjusted-return check.

Scores in metadata are not accepted merely because a collector wrote them. The containing fact/event/monitor must first pass the manual review gate. The first release does not invent a score from prose; prose without an explicit reviewed normalization remains pending or NULL.

run_batch_score() fetches this context for each mapping and merges it into a copy before score_mapping(). Extend its signature with connection=None and apply the same ownership rule as the review repository:

~~~python
def run_batch_score(
    *,
    pg_url: str,
    chain_id: str,
    trade_date: date,
    model_version: str,
    dry_run: bool,
    mapping_ids: list[str] | None = None,
    repository: SelectionRepository | None = None,
    connection_factory=None,
    connection=None,
):
    owns_connection = connection is None
    factory = connection_factory or (lambda: psycopg2.connect(pg_url))
    active = connection or factory()
    repo = repository or SelectionRepository(connection_factory=lambda: active)
    try:
        result = run_batch_score_in_connection(
            active,
            chain_id=chain_id,
            trade_date=trade_date,
            model_version=model_version,
            dry_run=dry_run,
            mapping_ids=mapping_ids,
            repository=repo,
        )
        if owns_connection:
            active.rollback() if dry_run else active.commit()
        return result
    except Exception:
        if owns_connection:
            active.rollback()
        raise
    finally:
        if owns_connection:
            active.close()
~~~

Thread active through every SelectionRepository fetch and persist call. A caller-owned connection is never committed, rolled back or closed. This lets the UAT insert, approve, score and inspect synthetic rows in one transaction before rolling everything back.

- [ ] **Step 4: Complete explanation fields**

Add catalyst_score to SelectionCandidate and FIVE_SELECTION_SCORES. Extend stock detail with:

~~~text
approved_evidence
pending_facts
rejected_facts
evidence_gaps
score_components
missing_score_inputs
pool_gate
blocking_gate
next_validation
~~~

The API labels pending facts as pending and never exposes credentials.

Expose selection endpoints through the gateway at `/api/v1/screener/supply-chain/selection/...`. Keep the old `/api/v1/supply-chain/selection/...` paths as deprecated aliases with include_in_schema=False so current direct-service callers do not break. Add the public paths to openapi_paths.json and a gateway assertion for the candidates endpoint.

- [ ] **Step 5: Run GREEN and commit**

~~~bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_supply_chain_selection_v2.py services/screener-service/tests/test_supply_chain_selection_repository.py services/screener-service/tests/test_supply_chain_selection_v2_api.py services/screener-service/tests/test_api.py services/api-gateway/tests/test_gateway_routes.py tools/tests/test_score_supply_chain_selection_v2.py
git add packages/kronos-factors/kronos_factors/scorer/supply_chain_selection_v2.py packages/kronos-factors/tests/test_supply_chain_selection_v2.py services/screener-service/app/domains/supply_chain/selection_repository.py tools/score_supply_chain_selection_v2.py services/screener-service/app/domains/supply_chain/models.py services/screener-service/app/domains/supply_chain/selection_router.py services/screener-service/app/domains/supply_chain/selection_service.py services/screener-service/tests/test_supply_chain_selection_repository.py services/screener-service/tests/test_supply_chain_selection_v2_api.py services/screener-service/tests/fixtures/openapi_paths.json services/api-gateway/tests/test_gateway_routes.py tools/tests/test_score_supply_chain_selection_v2.py
git commit -m "feat: explain approved supply-chain selection inputs"
~~~

Expected: missing expectation, catalyst or risk remains NULL and appears in limitations.

---

### Task 10: Run dexterous-hand PostgreSQL UAT and publish the report

**Files:**

- Create: tools/run_supply_chain_evidence_orchestration_uat.py
- Create: tools/tests/test_run_supply_chain_evidence_orchestration_uat.py
- Create during UAT: docs/qa/supply-chain-evidence-orchestration-uat-2026-07-12.md
- Generate, do not commit unless requested: outputs/supply_chain_evidence/dexterous_hand/2026-07-09/result.json
- Generate, do not commit unless requested: outputs/supply_chain_evidence/dexterous_hand/2026-07-09/report.md

**Interfaces:**

- Consumes: all prior tasks.
- Produces: repeatable UAT and user-facing evidence report.

- [ ] **Step 1: Write the UAT contract test**

~~~python
def test_uat_never_approves_real_company_facts():
    plan = build_uat_plan(chain_id="dexterous_hand", as_of_date=date(2026, 7, 9))
    assert plan.steps == (
        "preflight",
        "dry_run",
        "collect",
        "collect_idempotency",
        "score_before_review",
        "synthetic_review_rollback",
        "report",
    )
    assert plan.real_fact_review_mode == "read_only"
    assert plan.synthetic_review_rollback is True
    assert plan.synthetic_score_date_policy == "reviewed_at_date"
~~~

- [ ] **Step 2: Verify RED**

~~~bash
bash tools/codex-lowio.sh py tools/tests/test_run_supply_chain_evidence_orchestration_uat.py
~~~

Expected: the UAT tool is missing.

- [ ] **Step 3: Implement the UAT sequence**

The tool performs:

1. verify PostgreSQL and Alembic revision 033;
2. record document, fact, event, gap, score and transition counts;
3. run dry-run and verify all counts stay unchanged;
4. run collect for five existing candidates plus independent axial-flux discovery;
5. rerun collect and verify no duplicate documents, facts or events;
6. run score before review and verify pending facts cannot change pools;
7. open one caller-owned transaction for steps 7-9, create a synthetic mapping and fact, pass that connection into review_fact(), read the timezone-aware reviewed_at returned by PostgreSQL, convert it with reviewed_at.astimezone(ZoneInfo('Asia/Shanghai')).date(), and use that as run_batch_score(connection=connection) trade_date; keep the transaction open and assert the reviewed fact is visible only to that current-or-later synthetic score;
8. after review_fact() returns, assert current_setting('app.supply_chain_review_action', true) is not manual; create SAVEPOINT direct_approval_guard, attempt direct SQL pending to confirmed while supplying non-empty reviewer, review_note and reviewed_at, verify the trigger rejects solely because the marker is absent, then ROLLBACK TO SAVEPOINT so the surrounding UAT transaction remains usable;
9. in the same caller-owned transaction, create a future-dated synthetic fact and verify 2026-07-09 scoring cannot read it; then perform the single rollback for steps 7-9 and assert all synthetic mappings, facts, events, stages and scores are gone;
10. write JSON, Markdown and QA results.

The UAT fails if review_fact(), review_event(), review_expectation_monitor() or run_batch_score() commits, rolls back or closes a caller-owned connection. It also checks that historical confirmed/approved rows without reviewer, review_note or reviewed_at are absent from scoring inputs after migration 033.

The fixed 2026-07-09 run remains the historical no-lookahead baseline. The synthetic approval check uses the real database reviewed_at date; it never backdates reviewer or reviewed_at to make historical scoring pass. The QA report prints both dates separately.

The five real companies are 003021、300007、300660、603662、603728. The tool never approves facts attached to them.

- [ ] **Step 4: Run focused regression**

~~~bash
bash tools/codex-lowio.sh py \
  packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py \
  packages/kronos-factors/tests/test_industry_chain_templates.py \
  packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py \
  packages/kronos-factors/tests/test_supply_chain_selection_v2.py \
  tools/tests/test_supply_chain_data_collection_center.py \
  tools/tests/test_supply_chain_evidence_pipeline.py \
  tools/tests/test_supply_chain_evidence_adapters.py \
  tools/tests/test_supply_chain_evidence_orchestrator.py \
  tools/tests/test_supply_chain_evidence_report.py \
  tools/tests/test_score_supply_chain_selection_v2.py \
  tools/tests/test_run_supply_chain_evidence_orchestration_uat.py \
  services/screener-service/tests/test_supply_chain_evidence_review.py \
  services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py \
  services/screener-service/tests/test_supply_chain_selection_repository.py \
  services/screener-service/tests/test_supply_chain_selection_v2_api.py \
  services/screener-service/tests/test_supply_chain_v2_migration_contract.py \
  services/screener-service/tests/test_api.py \
  services/api-gateway/tests/test_gateway_routes.py
~~~

Expected: all listed tests pass.

- [ ] **Step 5: Apply migration and run UAT**

Precondition:

~~~bash
psql 'postgresql://kronos:kronos@localhost:6432/kronos' -X -c 'SELECT 1'
~~~

Expected: one row containing 1. If PostgreSQL is unavailable, restore the existing local dev database; do not substitute SQLite or an empty database.

Run:

~~~bash
cd backend && alembic -c alembic.ini upgrade head
cd ..
python3 tools/run_supply_chain_evidence_orchestration_uat.py \
  --pg-url 'postgresql://kronos:kronos@localhost:6432/kronos' \
  --chain-id dexterous_hand \
  --as-of-date 2026-07-09 \
  --output-dir outputs/supply_chain_evidence/dexterous_hand/2026-07-09
~~~

Expected:

- revision is 033;
- dry-run writes 0 rows;
- automatic facts remain pending;
- second collect adds no duplicate documents, facts or events;
- direct SQL confirmation is rejected;
- the five real companies are not auto-approved;
- A/B/C may remain empty;
- report lists each missing score input and axial-flux result;
- model registry remains staging.

- [ ] **Step 6: Write and commit the QA report**

The QA report states the exact cutoff, source failures, before/after counts, real-company review status, four-pool counts and investment-validity limitation. It never converts pending facts into company conclusions.

~~~bash
git add tools/run_supply_chain_evidence_orchestration_uat.py tools/tests/test_run_supply_chain_evidence_orchestration_uat.py docs/qa/supply-chain-evidence-orchestration-uat-2026-07-12.md
git commit -m "test: validate dexterous-hand evidence orchestration"
~~~

Expected: the commit excludes outputs/ and contains the UAT tool, test and QA report.

---

## Final regression

Run the original baseline set:

~~~bash
bash tools/codex-lowio.sh py \
  packages/kronos-factors/tests/test_industry_chain_templates.py \
  packages/kronos-factors/tests/test_supply_chain_selection_v2.py \
  tools/tests/test_supply_chain_data_collection_center.py \
  tools/tests/test_supply_chain_evidence_pipeline.py
~~~

Expected: at least the original 67 tests pass, plus new tests.

Run repository checks:

~~~bash
git status --short
git log --oneline --decorate -12
~~~

Expected: no unrelated files are staged; commits correspond to the ten tasks above.
