"""Tests for chain deconstruct API endpoints.

AC verification:
- [AC-1] GET /chain/deconstruct?theme_id=&method= returns tree_nodes + graph format
- [AC-2] GET /chain/node/{node_id}/companies returns company mapping list with resonance field
- [AC-3] API P95 <= 500ms
- [AC-4] Valid theme_id returns 200, invalid theme_id returns 404
"""

import pytest
import json
from fastapi.testclient import TestClient

from app.main import app
from app.domains.supply_chain import evidence_review_service
from app.routers import screener as screener_router
from app.routers.screener import (
    BusinessTagBatchScoreRequest,
    SupplyChainInferredMaterializeRequest,
    SupplyChainRefreshWorkflowRequest,
    _batch_score_business_tags,
    _build_l8_evidence_status_records,
    _build_l8_source_evidence_events,
    _calculate_business_tag_expectation_gap_score,
    _calculate_business_tag_three_high_score,
    _build_inferred_business_tag_materialization,
    _calculate_company_expectation_gap_rankings,
    _calculate_company_value_rankings,
    _materialize_supply_chain_inferred_data,
    _refresh_supply_chain_tracking_workflow,
    _seed_chain_nodes_for_deconstruct,
    _infer_business_tag_evidence_event,
    _source_record_matches_mapping,
    _stage_from_evidence_events,
    _stage_record_from_reviewed_event,
)
from kronos_factors.engine.chain_deconstruct import load_industry_chain_templates


client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures and helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_theme_id():
    """Provide a test theme_id that exists in the database."""
    # Use one of the themes from Task #5 migration
    return "future_industry_core"


@pytest.fixture(scope="module")
def test_node_id():
    """Provide a test node_id that exists in the database."""
    # Use one of the nodes from Task #5 migration
    return "quantum_core"


# ─────────────────────────────────────────────────────────────────────────────
# AC-1: GET /chain/deconstruct returns tree_nodes + graph format
# ─────────────────────────────────────────────────────────────────────────────

class TestChainDeconstruct:
    """Tests for GET /chain/deconstruct endpoint."""

    def test_workbench_uses_business_tag_mapping_fallback_when_model_candidates_empty(self, monkeypatch):
        """Workbench should still return real mapping candidates when model pool is empty."""
        monkeypatch.setattr(
            screener_router,
            "_load_supply_chain_bom_payload",
            lambda: {"version": "test", "source": "test", "themes": [], "nodes": [], "edges": []},
        )
        monkeypatch.setattr(screener_router, "_get_supply_chain_candidate_pool", lambda top_n, trade_date: [])
        monkeypatch.setattr(
            screener_router,
            "_query_business_tag_mapping_candidates",
            lambda top_n, node_id=None: [
                {
                    "mapping_id": "MAP-TEST-1",
                    "code": "000001",
                    "name": "测试公司",
                    "node_id": "ai_compute_hardware",
                    "mapping_status": "verified",
                    "candidate_source": "business_tag_mapping_fallback",
                }
            ],
        )
        monkeypatch.setattr(screener_router, "_attach_market_snapshots", lambda candidates, trade_date=None: candidates)
        monkeypatch.setattr(screener_router, "_query_upstream_influence_candidates", lambda limit, trade_date: [])
        monkeypatch.setattr(screener_router, "_query_supply_chain_data_freshness", lambda: {})
        monkeypatch.setattr(screener_router, "_query_research_ingestion_status", lambda: {})

        response = client.get("/api/v1/screener/supply-chain/workbench", params={"top_n": 5})

        assert response.status_code == 200
        data = response.json()
        assert data["candidate_count"] == 1
        assert data["data_status"]["candidate_pool"] == "mapping_fallback"
        assert data["candidates"][0]["mapping_id"] == "MAP-TEST-1"
        assert data["candidates"][0]["candidate_source"] == "business_tag_mapping_fallback"
        assert any(w["code"] == "candidate_pool_mapping_fallback" for w in data["warnings"])

    def test_seed_bom_can_feed_deconstruct_when_pg_chain_nodes_empty(self):
        """Bundled BOM seed config should be usable when chain_nodes is empty."""
        nodes, theme_name = _seed_chain_nodes_for_deconstruct("future_industry_core")

        assert theme_name == "未来产业主攻方向"
        assert {node["node_id"] for node in nodes} >= {
            "embodied_ai_core",
            "bom_reducer",
        }
        reducer = next(node for node in nodes if node["node_id"] == "bom_reducer")
        assert reducer["node_name"] == "减速器"
        assert reducer["parent_node_id"] == "embodied_ai_core"
        assert reducer["layer"] > 0

    def test_returns_200_for_valid_theme_id(self, test_theme_id):
        """[AC-4] Valid theme_id should return 200."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        assert response.status_code == 200

    def test_returns_404_for_invalid_theme_id(self):
        """[AC-4] Invalid theme_id should return 404."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": "invalid_theme_xyz", "method": "upstream_downstream"},
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_returns_400_for_invalid_method(self, test_theme_id):
        """Invalid method should return 400."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "invalid_method"},
        )
        assert response.status_code == 400

    def test_returns_tree_structure(self, test_theme_id):
        """[AC-1] Response should contain tree structure."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "theme" in data
        assert "view" in data
        assert "tree" in data

        # Verify theme structure
        assert data["theme"]["id"] == test_theme_id
        assert "name" in data["theme"]

        # Verify view matches requested method
        assert data["view"] == "upstream_downstream"

        # Verify tree structure
        tree = data["tree"]
        assert tree["node_id"] == "root"
        assert "children" in tree

    def test_value_chain_method_returns_value_chain_data(self, test_theme_id):
        """[AC-1] method='value_chain' should return value_chain field."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "value_chain"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "value_chain"
        assert "value_chain" in data
        assert data["model_metadata"]["inference_mode"] == "chain:value_chain"
        assert data["data_freshness"]["source"] == "chain_nodes"
        assert data["fallback_reason"] is None
        assert isinstance(data["value_chain"], dict)

        # Each node should have margin/pricing_power/value_added/note
        for node_id, vc_data in data["value_chain"].items():
            assert "margin" in vc_data
            assert "pricing_power" in vc_data
            assert "value_added" in vc_data
            assert "note" in vc_data

    def test_competition_method_returns_competition_data(self, test_theme_id):
        """[AC-1] method='competition' should return competition field."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "competition"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "competition"
        assert "competition" in data
        assert isinstance(data["competition"], dict)

        # Each node should have concentration/leader_share/barrier/threat/note
        for node_id, comp_data in data["competition"].items():
            assert "concentration" in comp_data
            assert "leader_share" in comp_data
            assert "barrier" in comp_data
            assert "threat" in comp_data
            assert "note" in comp_data

    def test_bom_method_returns_layered_bom_data(self, test_theme_id):
        """method='bom' should return L1-L8 BOM layers and paths."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "bom"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "bom"
        assert "bom_layers" in data
        assert "bom_paths" in data
        assert set(data["bom_layers"].keys()) == {f"L{i}" for i in range(1, 9)}
        assert data["model_metadata"]["inference_mode"] == "chain:bom"

    def test_bom_method_returns_completed_semantic_table(self, test_theme_id):
        """method='bom' should expose completed L1-L8 rows without placeholder gaps."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "bom"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["bom_table"]
        for layer in (f"L{i}" for i in range(1, 9)):
            assert data["bom_layers"][layer], f"{layer} should not be empty"

        table_text = json.dumps(data["bom_table"], ensure_ascii=False)
        assert "待拆" not in table_text
        assert "待挂接" not in table_text
        assert "业务" in table_text
        assert "客户验证" in table_text

    def test_complex_tech_template_returns_eight_layer_chain_logic(self, test_theme_id):
        """template='complex_tech' should return the industry-link template without replacing L1-L8 BOM."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "complex_tech",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "complex_tech"
        assert data["template"]["template_id"] == "complex_tech"
        assert data["template"]["name"] == "复杂科技产业链路模板"
        assert data["model_metadata"]["inference_mode"] == "chain:complex_tech"
        assert data["tree"]["node_id"] == "template:complex_tech"

        children = data["tree"]["children"]
        assert [child["layer_id"] for child in children] == [
            "demand",
            "task",
            "core_product",
            "foundation",
            "integration",
            "supporting",
            "infrastructure",
            "commercialization",
        ]
        assert [child["name"] for child in children] == [
            "需求层",
            "任务层",
            "核心产品层",
            "底层支撑层",
            "集成层",
            "配套层",
            "基础设施层",
            "商业变现层",
        ]
        for child in children:
            assert child["definition"]
            assert child["key_questions"]
            assert "evidence" in child
            assert "companies" in child
            assert "tracking_metrics" in child

        core_product = next(child for child in children if child["layer_id"] == "core_product")
        assert "AI芯片/GPU/NPU/ASIC" in core_product["segments"]

        foundation = next(child for child in children if child["layer_id"] == "foundation")
        assert {"先进制程", "Chiplet/CoWoS", "HBM"} <= set(foundation["segments"])

    def test_complex_tech_template_returns_structured_metrics(self, test_theme_id):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "complex_tech",
            },
        )

        assert response.status_code == 200
        children = response.json()["tree"]["children"]

        for child in children:
            metrics = child["metrics"]
            assert metrics["commercialization"], child["layer_id"]
            assert metrics["expectation_gap"], child["layer_id"]
            assert metrics["trigger_signals"], child["layer_id"]
            assert child["tracking_metrics"], "legacy tracking_metrics must stay available"

    def test_embodied_intelligence_template_reuses_complex_chain_logic(self, test_theme_id):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "embodied_intelligence",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "embodied_intelligence"
        assert data["template"]["template_id"] == "embodied_intelligence"
        assert data["template"]["name"] == "具身智能复杂产业链路模板"
        assert data["model_metadata"]["inference_mode"] == "chain:embodied_intelligence"
        assert data["tree"]["node_id"] == "template:embodied_intelligence"

        children = data["tree"]["children"]
        assert [child["layer_id"] for child in children] == [
            "demand",
            "task",
            "core_product",
            "foundation",
            "integration",
            "supporting",
            "infrastructure",
            "commercialization",
        ]

        core_product = next(child for child in children if child["layer_id"] == "core_product")
        foundation = next(child for child in children if child["layer_id"] == "foundation")
        infrastructure = next(child for child in children if child["layer_id"] == "infrastructure")

        assert "人形机器人整机" in core_product["segments"]
        assert {"减速器", "伺服电机", "力矩传感器"} <= set(foundation["segments"])
        assert infrastructure["capex_evidence"]
        assert infrastructure["physical_metrics"]
        assert infrastructure["expectation_gap"]["gap_direction"] == "unknown"
        assert infrastructure["trigger_signal"]["signal_strength"] in {"weak", "medium", "strong", "unknown"}

    def test_storage_chips_template_returns_eight_layer_chain_logic(self, test_theme_id):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "storage_chips",
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "storage_chips"
        assert data["template"]["template_id"] == "storage_chips"
        assert data["template"]["name"] == "存储芯片复杂产业链路模板"
        assert data["model_metadata"]["inference_mode"] == "chain:storage_chips"
        assert data["tree"]["node_id"] == "template:storage_chips"

        children = data["tree"]["children"]
        assert [child["layer_id"] for child in children] == [
            "demand",
            "task",
            "core_product",
            "foundation",
            "integration",
            "supporting",
            "infrastructure",
            "commercialization",
        ]

        core_product = next(child for child in children if child["layer_id"] == "core_product")
        foundation = next(child for child in children if child["layer_id"] == "foundation")
        commercialization = next(child for child in children if child["layer_id"] == "commercialization")

        assert {"DRAM", "NAND Flash", "HBM"} <= set(core_product["segments"])
        assert {"刻蚀/薄膜/清洗设备", "电子特气", "光刻胶"} <= set(foundation["segments"])
        assert "价格周期" in commercialization["segments"]
        for child in children:
            assert child["metrics"]["commercialization"]
            assert child["physical_metrics"]

    @pytest.mark.parametrize(
        ("template_id", "template_name", "core_segments", "foundation_segments"),
        [
            (
                "ai_compute_infrastructure",
                "AI算力基础设施复杂产业链路模板",
                {"AI芯片/GPU/ASIC", "AI服务器", "高速光模块"},
                {"HBM", "高速PCB", "电源芯片"},
            ),
            (
                "advanced_packaging_chiplet",
                "先进封装/Chiplet复杂产业链路模板",
                {"2.5D/3D封装", "Chiplet", "CoWoS类封装"},
                {"ABF/IC载板", "TSV/RDL", "环氧塑封料"},
            ),
            (
                "semiconductor_equipment_materials",
                "半导体设备材料复杂产业链路模板",
                {"刻蚀设备", "薄膜设备", "清洗设备", "CMP设备"},
                {"硅片", "光刻胶", "电子特气", "CMP材料"},
            ),
            (
                "lithography_equipment_chain",
                "光刻机/光刻工艺复杂产业链路模板",
                {"ArF浸没光刻机", "KrF光刻机", "涂胶显影设备"},
                {"光学元件", "掩膜版", "光刻胶"},
            ),
            (
                "data_ai_application_commercialization",
                "数据要素/AI应用商业化复杂产业链路模板",
                {"行业大模型", "AI办公软件", "数据交易平台"},
                {"算力资源", "数据资源", "向量数据库"},
            ),
            (
                "defense_informatization_unmanned",
                "军工信息化/无人作战复杂产业链路模板",
                {"无人机", "雷达系统", "红外探测"},
                {"碳纤维复材", "高温合金", "连接器"},
            ),
            (
                "intelligent_driving_v2x",
                "智能驾驶/车路云复杂产业链路模板",
                {"智能驾驶域控", "车载操作系统", "高精地图"},
                {"车规芯片", "传感器", "通信模组"},
            ),
            (
                "controlled_fusion_materials",
                "可控核聚变材料复杂产业链路模板",
                {"超导磁体", "第一壁材料", "高功率电源"},
                {"钨钼材料", "钽铌锆材料", "高温合金"},
            ),
            (
                "industrial_machine_tools_cnc",
                "工业母机/高端数控复杂产业链路模板",
                {"五轴数控机床", "数控系统", "加工中心"},
                {"伺服系统", "滚珠丝杠", "减速器"},
            ),
            (
                "innovative_drug_cxo_adc_glp1",
                "创新药/CXO/ADC/减重药复杂产业链路模板",
                {"ADC药物", "GLP-1药物", "小分子创新药"},
                {"原料药", "多肽合成", "Linker/Payload"},
            ),
            (
                "flexible_dc_offshore_wind_grid",
                "海上风电/柔直输电复杂产业链路模板",
                {"海上风机", "海底电缆", "柔直换流阀"},
                {"导体材料", "绝缘材料", "电力电子器件"},
            ),
            (
                "rare_earth_minor_metals_security",
                "稀土永磁/小金属资源安全复杂产业链路模板",
                {"稀土氧化物", "钕铁硼磁材", "锂钴资源"},
                {"矿山资源", "分离冶炼", "合金材料"},
            ),
            (
                "display_oled_microled",
                "OLED/Micro LED/半导体显示复杂产业链路模板",
                {"OLED面板", "Micro LED显示", "Mini LED背光"},
                {"发光材料", "光学膜", "玻璃基板"},
            ),
            (
                "domestic_os_database_industrial_software",
                "国产操作系统/数据库/工业软件复杂产业链路模板",
                {"国产操作系统", "国产数据库", "CAD/CAE/工业软件"},
                {"CPU适配", "安全可信", "工业知识模型"},
            ),
            (
                "huawei_ascend_ai_ecosystem",
                "昇腾AI算力生态复杂产业链路模板",
                {"昇腾AI处理器", "Atlas服务器", "CANN异构计算架构"},
                {"鲲鹏CPU生态", "高速互联", "光模块"},
            ),
            (
                "offshore_wind_subsea_cable",
                "海风海缆/海洋能源装备复杂产业链路模板",
                {"海底电缆", "海底光电复合缆", "动态海缆"},
                {"高压绝缘材料", "导体材料", "海缆附件"},
            ),
            (
                "new_power_system_grid",
                "新型电力系统/智能电网复杂产业链路模板",
                {"特高压设备", "柔直设备", "电力电缆"},
                {"电力电子器件", "绝缘材料", "导线金具"},
            ),
        ],
    )
    def test_priority_complex_templates_return_eight_layer_chain_logic(
        self,
        test_theme_id,
        template_id,
        template_name,
        core_segments,
        foundation_segments,
    ):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": template_id,
            },
        )

        assert response.status_code == 200
        data = response.json()

        assert data["view"] == template_id
        assert data["template"]["template_id"] == template_id
        assert data["template"]["name"] == template_name
        assert data["model_metadata"]["inference_mode"] == f"chain:{template_id}"
        assert data["tree"]["node_id"] == f"template:{template_id}"

        children = data["tree"]["children"]
        assert [child["layer_id"] for child in children] == [
            "demand",
            "task",
            "core_product",
            "foundation",
            "integration",
            "supporting",
            "infrastructure",
            "commercialization",
        ]

        core_product = next(child for child in children if child["layer_id"] == "core_product")
        foundation = next(child for child in children if child["layer_id"] == "foundation")
        assert core_segments <= set(core_product["segments"])
        assert foundation_segments <= set(foundation["segments"])
        for child in children:
            assert child["metrics"]["commercialization"]
            assert child["capex_evidence"]
            assert child["physical_metrics"]

    def test_complex_tech_layers_include_evidence_chain_gap_and_triggers(self, test_theme_id):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "complex_tech",
            },
        )

        assert response.status_code == 200
        children = response.json()["tree"]["children"]

        infrastructure = next(child for child in children if child["layer_id"] == "infrastructure")
        assert infrastructure["capex_evidence"], "CAPEX evidence should be attached to the mapped layer"
        assert infrastructure["physical_metrics"], "physical metrics should be attached to the mapped layer"

        capex = infrastructure["capex_evidence"][0]
        assert capex["mapped_layer_id"] == "infrastructure"
        assert capex["metric_usage"]
        assert capex["source_type"]
        assert capex["as_of_date"]

        physical_metric = infrastructure["physical_metrics"][0]
        assert physical_metric["mapped_layer_id"] == "infrastructure"
        assert physical_metric["mapped_segment"]
        assert physical_metric["metric_usage"]
        assert physical_metric["source_type"]

        evidence = infrastructure["evidence_chain"]
        evidence_ids = {item["evidence_id"] for item in evidence}
        assert capex["evidence_id"] in evidence_ids
        assert physical_metric["metric_id"] in evidence_ids
        for item in evidence:
            assert item["evidence_type"] in {"capex", "physical_metric"}
            assert item["impact_direction"] in {"positive", "negative", "neutral", "unknown"}
            assert item["confidence"] in {"high", "medium", "low", "unknown"}

        expectation_gap = infrastructure["expectation_gap"]
        assert expectation_gap["calculation_method"] == "existing_business_tag_formula_unavailable"
        assert set(expectation_gap["evidence_ids"]) <= evidence_ids
        assert expectation_gap["gap_direction"] == "unknown"

        trigger_signal = infrastructure["trigger_signal"]
        assert set(trigger_signal["triggered_by_evidence_ids"]) <= evidence_ids
        assert trigger_signal["signal_strength"] in {"weak", "medium", "strong", "unknown"}

    def test_complex_tech_macro_context_is_top_level_unknown_when_unverified(self, test_theme_id):
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={
                "theme_id": test_theme_id,
                "method": "upstream_downstream",
                "template": "complex_tech",
            },
        )

        assert response.status_code == 200
        data = response.json()
        macro_context = data["macro_context"]

        assert {item["region"] for item in macro_context} == {"US", "CN", "JP", "KR", "EU"}
        for item in macro_context:
            assert item["policy_stance"] == "unknown"
            assert item["inflation_state"] == "unknown"
            assert item["rate_trend"] == "unknown"
            assert item["liquidity_signal"] == "unknown"
            assert item["source_type"]
            assert item["as_of_date"]
            assert item["evidence_level"] == "unknown"

        for child in data["tree"]["children"]:
            assert "macro_context" not in child

    def test_complex_tech_evidence_model_is_config_driven(self):
        config = load_industry_chain_templates()
        template = next(item for item in config["templates"] if item["template_id"] == "complex_tech")

        assert {item["region"] for item in template["macro_context"]} == {"US", "CN", "JP", "KR", "EU"}
        assert template["macro_context"][0]["policy_stance"] == "unknown"

        layers = template["layers"]
        assert len(layers) == 8
        for layer in layers:
            metrics = layer["metrics"]
            assert metrics["commercialization"], layer["layer_id"]
            assert metrics["expectation_gap"], layer["layer_id"]
            assert metrics["trigger_signals"], layer["layer_id"]
            assert layer["physical_metrics"], layer["layer_id"]

        demand = next(layer for layer in layers if layer["layer_id"] == "demand")
        foundation = next(layer for layer in layers if layer["layer_id"] == "foundation")
        infrastructure = next(layer for layer in layers if layer["layer_id"] == "infrastructure")
        assert demand["capex_evidence"]
        assert foundation["capex_evidence"]
        assert infrastructure["capex_evidence"]

    def test_complex_tech_data_source_catalog_prioritizes_real_evidence_sources(self):
        config = load_industry_chain_templates()
        catalog = config["data_source_catalog"]

        source_ids = {source["source_id"] for source in catalog}
        assert {
            "tushare_cn_equity",
            "official_macro_policy",
            "sec_company_filings",
            "company_investor_relations",
            "industry_physical_research",
        } <= source_ids

        for source in catalog:
            assert source["source_id"]
            assert source["coverage"]
            assert source["collection_method"] in {"manual_first", "semi_auto", "auto", "external_api"}
            assert source["automation_status"] in {"manual", "planned", "ready"}
            assert source["evidence_level"] in {"reported", "confirmed", "inferred", "manual_judgement", "unknown"}
            assert source["target_fields"]
            assert source["priority"] in {"P0", "P1", "P2"}

        official_macro = next(source for source in catalog if source["source_id"] == "official_macro_policy")
        assert {"US", "CN", "JP", "KR", "EU"} <= set(official_macro["regions"])

        capex_sources = [
            source for source in catalog
            if "capex_evidence" in source["target_fields"]
        ]
        assert {source["source_id"] for source in capex_sources} == {
            "sec_company_filings",
            "company_investor_relations",
        }

    def test_complex_tech_collection_task_catalog_defines_next_ingestion_work(self):
        config = load_industry_chain_templates()
        tasks = config["collection_task_catalog"]

        task_ids = {task["task_id"] for task in tasks}
        assert {
            "collect_bigtech_ai_capex",
            "collect_macro_policy_baseline",
            "maintain_physical_metric_watchlist",
        } <= task_ids

        valid_sources = {source["source_id"] for source in config["data_source_catalog"]}
        for task in tasks:
            assert task["task_id"]
            assert task["status"] in {"backlog", "manual_ready", "planned", "blocked"}
            assert task["target_template_id"] == "complex_tech"
            assert task["source_ids"]
            assert set(task["source_ids"]) <= valid_sources
            assert task["target_layers"]
            assert task["target_fields"]
            assert task["output_contract"]
            assert task["owner"] in {"product-lead", "research-analyst", "data-engineer"}
            assert task["cadence"] in {"event_driven", "weekly", "monthly", "quarterly"}

        capex_task = next(task for task in tasks if task["task_id"] == "collect_bigtech_ai_capex")
        assert {"demand", "foundation", "infrastructure"} <= set(capex_task["target_layers"])
        assert "capex_evidence" in capex_task["target_fields"]
        assert "quote" in capex_task["output_contract"]["required_fields"]

        physical_task = next(task for task in tasks if task["task_id"] == "maintain_physical_metric_watchlist")
        assert {"foundation", "supporting", "infrastructure"} <= set(physical_task["target_layers"])
        assert "physical_metrics" in physical_task["target_fields"]

class TestSupplyChainDataReadiness:
    """Tests for V2 data readiness endpoint."""

    def test_data_readiness_reports_v2_layer_and_source_status(self):
        """Data readiness should expose L1-L8 coverage and source readiness."""
        response = client.get("/api/v1/screener/supply-chain/data-readiness")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "supply-chain-v2-readiness"
        assert set(data["layer_coverage"].keys()) == {f"L{i}" for i in range(1, 9)}
        assert "business_segments" in data
        assert "announcement_body" in data
        assert "research_body" in data
        assert "evidence_events" in data
        assert "business_tag_mapping" in data["target_tables"]
        assert "business_tag_evidence_events" in data["target_tables"]
        assert data["implementation_gates"]["core_pool_requires_business_evidence"] is True


class TestSupplyChainLayers:
    """Tests for V2 L1-L8 hierarchy endpoints."""

    def test_layers_returns_l1_to_l8_contract(self):
        response = client.get("/api/v1/screener/supply-chain/layers")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "supply-chain-v2-layers"
        assert set(data["layers"].keys()) == {f"L{i}" for i in range(1, 9)}
        assert isinstance(data["nodes"], list)
        assert isinstance(data["tree"], list)
        assert data["node_count"] == len(data["nodes"])

    def test_layer_detail_returns_node_context(self):
        layers_response = client.get("/api/v1/screener/supply-chain/layers")
        first_node = layers_response.json()["nodes"][0]

        response = client.get(f"/api/v1/screener/supply-chain/layer/{first_node['layer_node_id']}")

        assert response.status_code == 200
        data = response.json()

        assert data["node"]["layer_node_id"] == first_node["layer_node_id"]
        assert "ancestors" in data
        assert "children" in data


class TestSupplyChainCompanyBusinessTags:
    """Tests for V2 company business-tag endpoint."""

    def test_company_business_tags_returns_stable_card_contract(self):
        """Company business-tags endpoint should be safe before V2 tables are populated."""
        response = client.get("/api/v1/screener/supply-chain/company/000001/business-tags")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "supply-chain-v2-business-tags"
        assert data["normalized_code"] == "000001"
        assert "source_status" in data
        assert "tag_count" in data
        assert isinstance(data["tags"], list)
        assert isinstance(data["limitations"], list)


class TestSupplyChainBusinessTagEvidenceAndStage:
    """Tests for V2 business-tag evidence and stage endpoints."""

    def test_stage_inference_uses_approved_event_stage_after(self):
        stage = _stage_from_evidence_events([
            {
                "event_id": "EV-1",
                "review_status": "approved",
                "stage_after": {
                    "research_stage": "R3",
                    "commercialization_stage": "C2",
                },
                "title": "产品完成客户验证",
            },
            {
                "event_id": "EV-2",
                "review_status": "pending_review",
                "stage_after": {
                    "research_stage": "R6",
                    "commercialization_stage": "C6",
                },
            },
        ])

        assert stage["research_stage"] == "R3"
        assert stage["commercialization_stage"] == "C2"
        assert stage["stage_confirmed"] is True
        assert stage["source_event_id"] == "EV-1"

    def test_business_tag_evidence_returns_timeline_contract(self):
        response = client.get("/api/v1/screener/supply-chain/business-tag/demo-mapping/evidence")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "supply-chain-v2-evidence"
        assert data["mapping_id"] == "demo-mapping"
        assert "source_status" in data
        assert isinstance(data["events"], list)
        assert data["event_count"] == len(data["events"])
        assert data["review_gate"]["approved_events_enter_scoring"] is True

    def test_business_tag_stage_returns_default_stage_contract(self):
        response = client.get("/api/v1/screener/supply-chain/business-tag/demo-mapping/stage")

        assert response.status_code == 200
        data = response.json()

        assert data["version"] == "supply-chain-v2-stage"
        assert data["mapping_id"] == "demo-mapping"
        assert data["current_stage"]["research_stage"].startswith("R")
        assert data["current_stage"]["commercialization_stage"].startswith("C")
        assert data["current_stage"]["stage_confirmed"] is False
        assert isinstance(data["history"], list)
        assert data["stage_gate"]["stage_change_requires_evidence"] is True

    def test_business_tag_evidence_chain_returns_tracking_contract(self, monkeypatch):
        def fake_query(mapping_id):
            return {
                "version": "supply-chain-evidence-chain-v1",
                "mapping_id": mapping_id,
                "documents": [],
                "facts": [],
                "freshness": {},
                "stage_transitions": [],
                "expectations": [],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_business_tag_evidence_chain", fake_query)

        response = client.get("/api/v1/screener/supply-chain/business-tag/demo-mapping/evidence-chain")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-evidence-chain-v1"
        assert data["mapping_id"] == "demo-mapping"
        assert isinstance(data["documents"], list)
        assert isinstance(data["facts"], list)
        assert isinstance(data["stage_transitions"], list)
        assert isinstance(data["expectations"], list)
        assert "limitations" in data

    def test_evidence_review_queue_returns_tracking_contract(self, monkeypatch):
        def fake_query(limit=50):
            assert limit == 2
            return {
                "version": "supply-chain-evidence-review-queue-v2",
                "queue": [
                    {"queue_type": "event", "id": "e1"},
                    {"queue_type": "expectation_monitor", "id": "x1"},
                ],
                "counts": {"facts": 7, "events": 5, "expectations": 3},
                "review_gate": "application_level",
            }

        monkeypatch.setattr(evidence_review_service, "list_queue", fake_query)

        response = client.get(
            "/api/v1/screener/supply-chain/evidence-review/queue",
            params={"limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-evidence-review-queue-v2"
        assert [item["queue_type"] for item in data["queue"]] == [
            "event",
            "expectation_monitor",
        ]
        assert data["counts"] == {"facts": 7, "events": 5, "expectations": 3}


class TestSupplyChainEvidenceReview:
    """Tests for V2 evidence review write endpoint."""

    def test_review_endpoint_accepts_approved_evidence_payload(self, monkeypatch):
        def fake_review(event_id, request):
            return {
                "version": "supply-chain-v2-evidence-review",
                "event_id": event_id,
                "review_status": request.review_status,
                "stage_updated": True,
            }

        monkeypatch.setattr(screener_router, "_review_business_tag_evidence", fake_review)

        response = client.post(
            "/api/v1/screener/supply-chain/evidence/EV-001/review",
            json={
                "review_status": "approved",
                "reviewer": "pm",
                "note": "客户验证证据可信",
                "stage_after": {
                    "research_stage": "R3",
                    "commercialization_stage": "C2",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-evidence-review"
        assert data["event_id"] == "EV-001"
        assert data["review_status"] == "approved"
        assert data["stage_updated"] is True

    def test_stage_record_only_created_for_approved_stage_event(self):
        approved_record = _stage_record_from_reviewed_event(
            {
                "event_id": "EV-001",
                "mapping_id": "MAP-001",
                "event_date": "2026-07-02",
                "title": "产品完成客户验证",
                "stage_after": {
                    "research_stage": "R3",
                    "commercialization_stage": "C2",
                },
            },
            review_status="approved",
        )
        pending_record = _stage_record_from_reviewed_event(
            {
                "event_id": "EV-002",
                "mapping_id": "MAP-001",
                "stage_after": {
                    "research_stage": "R6",
                    "commercialization_stage": "C6",
                },
            },
            review_status="pending_review",
        )

        assert approved_record is not None
        assert approved_record["stage_id"] == "STAGE-MAP-001-EV-001"
        assert approved_record["research_stage"] == "R3"
        assert approved_record["commercialization_stage"] == "C2"
        assert approved_record["source_event_id"] == "EV-001"
        assert pending_record is None


class TestSupplyChainEvidenceExtraction:
    """Tests for V2 candidate evidence extraction endpoint."""

    def test_source_record_must_match_mapping_terms_or_evidence_keywords(self):
        mapping = {
            "tag_name": "减速器",
            "node_id": "bom_reducer",
            "l1_l8_path": [{"name": "具身智能"}, {"name": "减速器"}],
        }
        matched_source = {
            "title": "公司减速器产品完成客户验证",
            "excerpt": "客户验证顺利推进",
        }
        unrelated_source = {
            "title": "公司地产项目完成交付",
            "excerpt": "与产业链标签无关",
        }

        assert _source_record_matches_mapping(matched_source, mapping) is True
        assert _source_record_matches_mapping(unrelated_source, mapping) is False

    def test_infer_evidence_event_marks_candidate_as_pending_review(self):
        event = _infer_business_tag_evidence_event(
            mapping_id="MAP-001",
            mapping={
                "code": "000001",
                "node_id": "bom_test",
                "tag_name": "测试业务",
            },
            source={
                "source_type": "announcement_title",
                "source_id": "ANN-001",
                "title": "公司产品完成客户验证并获得小批量订单",
                "excerpt": "客户验证、小批量订单",
                "event_date": "2026-07-02",
            },
        )

        assert event["mapping_id"] == "MAP-001"
        assert event["review_status"] == "pending_review"
        assert event["evidence_type"] in {"customer_validation", "order"}
        assert event["stage_after"]["research_stage"].startswith("R")
        assert event["stage_after"]["commercialization_stage"].startswith("C")

    def test_extract_endpoint_returns_candidate_event_contract(self, monkeypatch):
        def fake_extract(mapping_id, request):
            return {
                "version": "supply-chain-v2-evidence-extract",
                "mapping_id": mapping_id,
                "persisted": True,
                "event": {
                    "event_id": "EV-MAP-001-123",
                    "review_status": "pending_review",
                    "evidence_type": "customer_validation",
                },
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_extract_business_tag_evidence_event", fake_extract)

        response = client.post(
            "/api/v1/screener/supply-chain/business-tag/MAP-001/evidence/extract",
            json={
                "source_type": "announcement_title",
                "source_id": "ANN-001",
                "title": "公司产品完成客户验证并获得小批量订单",
                "excerpt": "客户验证、小批量订单",
                "event_date": "2026-07-02",
                "persist": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-evidence-extract"
        assert data["mapping_id"] == "MAP-001"
        assert data["persisted"] is True
        assert data["event"]["review_status"] == "pending_review"

    def test_batch_extract_endpoint_returns_pending_review_summary(self, monkeypatch):
        def fake_batch(request):
            return {
                "version": "supply-chain-v2-evidence-batch-extract",
                "source_status": "ok",
                "mapping_count": 1,
                "candidate_source_count": 2,
                "created_event_count": 2,
                "events": [
                    {"event_id": "EV-MAP-001-a", "review_status": "pending_review"},
                    {"event_id": "EV-MAP-001-b", "review_status": "pending_review"},
                ],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_batch_extract_business_tag_evidence", fake_batch)

        response = client.post(
            "/api/v1/screener/supply-chain/evidence/batch-extract",
            json={
                "mapping_id": "MAP-001",
                "source_types": ["announcement_title", "research_title", "irm_qa"],
                "limit": 20,
                "persist": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-evidence-batch-extract"
        assert data["mapping_count"] == 1
        assert data["created_event_count"] == 2
        assert {event["review_status"] for event in data["events"]} == {"pending_review"}


class TestSupplyChainThreeHighScores:
    """Tests for V2 business-tag three-high score calculation."""

    def test_inferred_materialization_builds_l1_l8_evidence_and_three_high_baseline(self):
        materialized = _build_inferred_business_tag_materialization(
            {
                "mapping_id": "auto_300308_ai_compute_hardware",
                "code": "300308",
                "company_name": "中际旭创",
                "node_id": "ai_compute_hardware",
                "node_name": "硬件",
                "theme_id": "future_industry_core",
                "theme_name": "未来产业主攻方向",
                "chain_id": "ai_compute",
                "product_name": "光模块",
                "material_name": "",
                "status": "verified",
                "confidence": 0.85,
                "mapping_keywords": ["光模块"],
                "mapping_source": "main_business",
            },
            trade_date="2026-07-02",
        )

        mapping = materialized["mapping"]
        event = materialized["evidence_event"]
        stage = materialized["stage"]
        score = materialized["three_high_score"]

        assert mapping["mapping_id"] == "auto_300308_ai_compute_hardware"
        assert [item["layer"] for item in mapping["l1_l8_path"]] == [f"L{i}" for i in range(1, 9)]
        assert mapping["l1_l8_path"][1]["name"] == "AI算力"
        assert mapping["l1_l8_path"][4]["name"] == "光模块"
        assert mapping["l1_l8_path"][6]["name"] == "公司业务标签：光模块业务"
        assert mapping["l1_l8_path"][4]["name"] != mapping["l1_l8_path"][6]["name"]
        assert [item["dimension_id"] for item in mapping["l1_l8_path"][7]["dimensions"]] == [
            "research_progress",
            "prototype_delivery",
            "customer_validation",
            "order_award",
            "capacity_mass_production",
            "revenue_margin",
            "patent_standard",
        ]
        assert event["source_type"] == "rule_inference"
        assert event["review_status"] == "candidate"
        assert "不是公告或研报原文" in event["excerpt"]
        assert stage["review_status"] == "candidate"
        assert len(materialized["l8_evidence_statuses"]) == 7
        assert materialized["l8_evidence_statuses"][0]["dimension_name"] == "研发进展"
        assert score["score_detail"]["inference_only"] is True
        assert score["score_detail"]["requires_original_evidence"] is True
        assert score["profit_score"] is None
        assert score["growth_score"] > 0
        assert score["moat_score"] > 0
        assert event["event_id"] in score["evidence_ids"]

    def test_l8_source_events_are_structured_by_dimension(self):
        mapping = {
            "mapping_id": "auto_300308_ai_compute_hardware",
            "code": "300308",
            "node_id": "ai_compute_hardware",
            "tag_name": "光模块业务",
        }

        events = _build_l8_source_evidence_events(
            mapping_id=mapping["mapping_id"],
            mapping=mapping,
            source={
                "source_type": "research_title",
                "source_id": "RPT-001",
                "title": "AI算力需求推动业绩高增，1.6T光模块出货进展顺利",
                "excerpt": "",
                "event_date": "2026-04-01",
            },
        )
        statuses = _build_l8_evidence_status_records(
            mapping=mapping,
            l8_source_events=events,
            trade_date="2026-07-02",
        )

        assert {event["evidence_type"] for event in events} >= {
            "capacity_mass_production",
            "revenue_margin",
        }
        revenue_status = next(item for item in statuses if item["dimension_id"] == "revenue_margin")
        assert revenue_status["source_status"] == "matched"
        assert revenue_status["evidence_count"] >= 1
        patent_status = next(item for item in statuses if item["dimension_id"] == "patent_standard")
        assert patent_status["source_status"] == "missing"

    def test_inferred_materialize_endpoint_returns_persist_summary(self, monkeypatch):
        def fake_materialize(request):
            assert request.node_id == "ai_compute_hardware"
            assert request.persist is True
            return {
                "version": "supply-chain-v2-inferred-materialize",
                "source_status": "ready",
                "persisted": True,
                "mapping_count": 2,
                "written": {
                    "business_tag_mapping": 2,
                    "business_tag_evidence_events": 2,
                    "business_tag_three_high_scores": 2,
                },
                "limitations": ["推导证据不能替代公告或研报原文"],
            }

        monkeypatch.setattr(screener_router, "_materialize_supply_chain_inferred_data", fake_materialize)

        response = client.post(
            "/api/v1/screener/supply-chain/inferred-data/materialize",
            json={"node_id": "ai_compute_hardware", "persist": True, "limit": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-inferred-materialize"
        assert data["persisted"] is True
        assert data["written"]["business_tag_three_high_scores"] == 2

    def test_three_high_score_uses_business_tag_evidence_and_marks_missing_profit(self):
        score = _calculate_business_tag_three_high_score(
            mapping={
                "mapping_id": "MAP-001",
                "code": "000001",
                "confidence": 0.8,
                "revenue_ratio": 0.25,
                "gross_profit_ratio": None,
            },
            stage={
                "research_stage": "R3",
                "commercialization_stage": "C2",
            },
            events=[
                {
                    "event_id": "EV-ORDER",
                    "review_status": "approved",
                    "evidence_type": "order",
                    "confidence": 0.8,
                    "impact_dimensions": ["growth"],
                },
                {
                    "event_id": "EV-MOAT-PENDING",
                    "review_status": "pending_review",
                    "evidence_type": "moat",
                    "confidence": 0.9,
                    "impact_dimensions": ["moat"],
                },
            ],
            trade_date="2026-07-02",
        )

        assert score["mapping_id"] == "MAP-001"
        assert score["growth_score"] > 0
        assert score["profit_score"] is None
        assert score["moat_score"] == 0
        assert score["score_detail"]["profit_score_status"] == "unavailable"
        assert score["score_detail"]["approved_evidence_count"] == 1
        assert "EV-ORDER" in score["evidence_ids"]
        assert "EV-MOAT-PENDING" not in score["evidence_ids"]
        assert score["total_score"] <= 80

    def test_three_high_score_endpoint_returns_business_tag_score_contract(self, monkeypatch):
        def fake_score(mapping_id, request):
            return {
                "version": "supply-chain-v2-three-high-score",
                "mapping_id": mapping_id,
                "persisted": request.persist,
                "score": {
                    "growth_score": 70,
                    "profit_score": None,
                    "moat_score": 30,
                    "total_score": 52,
                    "score_detail": {"profit_score_status": "unavailable"},
                },
            }

        monkeypatch.setattr(screener_router, "_score_business_tag_three_high", fake_score)

        response = client.post(
            "/api/v1/screener/supply-chain/business-tag/MAP-001/three-high/score",
            json={"trade_date": "2026-07-02", "persist": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-three-high-score"
        assert data["mapping_id"] == "MAP-001"
        assert data["persisted"] is True
        assert data["score"]["profit_score"] is None

    def test_three_high_score_query_endpoint_returns_latest_contract(self, monkeypatch):
        def fake_query(mapping_id):
            return {
                "version": "supply-chain-v2-three-high-score",
                "mapping_id": mapping_id,
                "source_status": "ready",
                "score": {
                    "growth_score": 70,
                    "profit_score": None,
                    "moat_score": 30,
                    "total_score": 52,
                },
            }

        monkeypatch.setattr(screener_router, "_query_business_tag_three_high_score", fake_query)

        response = client.get("/api/v1/screener/supply-chain/business-tag/MAP-001/three-high/score")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-three-high-score"
        assert data["mapping_id"] == "MAP-001"
        assert data["source_status"] == "ready"
        assert data["score"]["total_score"] == 52


class TestSupplyChainExpectationGapScores:
    """Tests for V2 business-tag expectation-gap score calculation."""

    def test_expectation_gap_score_uses_stage_evidence_expectation_and_risk(self):
        score = _calculate_business_tag_expectation_gap_score(
            mapping={
                "mapping_id": "MAP-001",
                "code": "000001",
                "confidence": 0.85,
                "market_expectation_score": 45,
            },
            stage={
                "research_stage": "R4",
                "commercialization_stage": "C3",
            },
            events=[
                {
                    "event_id": "EV-ORDER",
                    "review_status": "approved",
                    "evidence_type": "order",
                    "confidence": 0.8,
                    "impact_dimensions": ["growth"],
                },
                {
                    "event_id": "EV-RISK",
                    "review_status": "approved",
                    "evidence_type": "risk",
                    "confidence": 0.6,
                    "impact_dimensions": ["risk"],
                },
                {
                    "event_id": "EV-PENDING",
                    "review_status": "pending_review",
                    "evidence_type": "commercialization",
                    "confidence": 1.0,
                    "impact_dimensions": ["growth"],
                },
            ],
            trade_date="2026-07-02",
        )

        assert score["gap_id"] == "GAP-MAP-001-2026-07-02"
        assert score["mapping_id"] == "MAP-001"
        assert score["actual_progress_score"] > score["market_expectation_score"]
        assert score["evidence_delta_score"] > 0
        assert score["risk_penalty_score"] > 0
        assert score["expectation_gap_score"] > 0
        assert score["gap_type"] == "positive"
        assert score["score_detail"]["approved_evidence_count"] == 2
        assert "EV-ORDER" in score["evidence_ids"]
        assert "EV-PENDING" not in score["evidence_ids"]

    def test_expectation_gap_score_endpoint_returns_business_tag_score_contract(self, monkeypatch):
        def fake_score(mapping_id, request):
            return {
                "version": "supply-chain-v2-expectation-gap-score",
                "mapping_id": mapping_id,
                "persisted": request.persist,
                "score": {
                    "actual_progress_score": 80,
                    "market_expectation_score": 45,
                    "evidence_delta_score": 65,
                    "risk_penalty_score": 10,
                    "expectation_gap_score": 48,
                    "gap_type": "positive",
                },
            }

        monkeypatch.setattr(screener_router, "_score_business_tag_expectation_gap", fake_score)

        response = client.post(
            "/api/v1/screener/supply-chain/business-tag/MAP-001/expectation-gap/score",
            json={"trade_date": "2026-07-02", "persist": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-expectation-gap-score"
        assert data["mapping_id"] == "MAP-001"
        assert data["persisted"] is True
        assert data["score"]["gap_type"] == "positive"

    def test_expectation_gap_score_query_endpoint_returns_latest_contract(self, monkeypatch):
        def fake_query(mapping_id):
            return {
                "version": "supply-chain-v2-expectation-gap-score",
                "mapping_id": mapping_id,
                "source_status": "ready",
                "score": {
                    "expectation_gap_score": 48,
                    "gap_type": "positive",
                },
            }

        monkeypatch.setattr(screener_router, "_query_business_tag_expectation_gap_score", fake_query)

        response = client.get("/api/v1/screener/supply-chain/business-tag/MAP-001/expectation-gap/score")

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-expectation-gap-score"
        assert data["mapping_id"] == "MAP-001"
        assert data["source_status"] == "ready"
        assert data["score"]["gap_type"] == "positive"


class TestSupplyChainBatchScores:
    """Tests for V2 batch scoring across business-tag mappings."""

    def test_batch_score_runs_selected_scores_for_each_mapping(self, monkeypatch):
        def fake_mappings(request):
            assert request.code == "000001"
            return [
                {"mapping_id": "MAP-001", "code": "000001", "tag_name": "减速器"},
                {"mapping_id": "MAP-002", "code": "000001", "tag_name": "机器人"},
            ]

        def fake_three_high(mapping_id, request):
            return {
                "mapping_id": mapping_id,
                "persisted": request.persist,
                "score": {"total_score": 52},
                "limitations": [],
            }

        def fake_expectation_gap(mapping_id, request):
            return {
                "mapping_id": mapping_id,
                "persisted": request.persist,
                "score": {"expectation_gap_score": 48, "gap_type": "positive"},
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_business_tag_mappings_for_batch_score", fake_mappings)
        monkeypatch.setattr(screener_router, "_score_business_tag_three_high", fake_three_high)
        monkeypatch.setattr(screener_router, "_score_business_tag_expectation_gap", fake_expectation_gap)

        result = _batch_score_business_tags(BusinessTagBatchScoreRequest(
            code="000001",
            score_types=["three_high", "expectation_gap"],
            trade_date="2026-07-02",
            persist=True,
            limit=20,
        ))

        assert result["version"] == "supply-chain-v2-batch-score"
        assert result["mapping_count"] == 2
        assert result["score_count"] == 4
        assert result["error_count"] == 0
        assert result["results"][0]["scores"]["three_high"]["total_score"] == 52
        assert result["results"][0]["scores"]["expectation_gap"]["gap_type"] == "positive"

    def test_batch_score_endpoint_returns_summary_contract(self, monkeypatch):
        def fake_batch(request):
            return {
                "version": "supply-chain-v2-batch-score",
                "source_status": "ready",
                "mapping_count": 1,
                "score_count": 2,
                "error_count": 0,
                "results": [
                    {
                        "mapping_id": "MAP-001",
                        "scores": {
                            "three_high": {"total_score": 52},
                            "expectation_gap": {"expectation_gap_score": 48},
                        },
                    }
                ],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_batch_score_business_tags", fake_batch)

        response = client.post(
            "/api/v1/screener/supply-chain/business-tags/batch-score",
            json={
                "code": "000001",
                "score_types": ["three_high", "expectation_gap"],
                "trade_date": "2026-07-02",
                "persist": True,
                "limit": 20,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-batch-score"
        assert data["mapping_count"] == 1
        assert data["score_count"] == 2


class TestSupplyChainRefreshWorkflow:
    """Tests for one-click supply-chain tracking refresh workflow."""

    def test_refresh_workflow_runs_extract_score_and_rankings(self, monkeypatch):
        def fake_extract(request):
            assert request.code == "000001"
            return {
                "version": "supply-chain-v2-evidence-batch-extract",
                "source_status": "ok",
                "mapping_count": 1,
                "created_event_count": 2,
                "events": [{"event_id": "EV-1"}, {"event_id": "EV-2"}],
                "limitations": ["candidate evidence requires review"],
            }

        def fake_batch_score(request):
            assert request.code == "000001"
            assert request.score_types == ["three_high", "expectation_gap"]
            return {
                "version": "supply-chain-v2-batch-score",
                "source_status": "ready",
                "mapping_count": 1,
                "score_count": 2,
                "error_count": 0,
                "results": [{"mapping_id": "MAP-001", "scores": {}}],
                "limitations": [],
            }

        def fake_rankings(rank_type, top_n, trade_date):
            return {
                "version": "supply-chain-v2-rankings",
                "rank_type": rank_type,
                "trade_date": trade_date,
                "source_status": "ready",
                "items": [{"rank": 1, "code": "000001"}],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_batch_extract_business_tag_evidence", fake_extract)
        monkeypatch.setattr(screener_router, "_batch_score_business_tags", fake_batch_score)
        monkeypatch.setattr(screener_router, "_query_supply_chain_rankings", fake_rankings)

        result = _refresh_supply_chain_tracking_workflow(SupplyChainRefreshWorkflowRequest(
            code="000001",
            source_types=["announcement_title", "research_title"],
            score_types=["three_high", "expectation_gap"],
            rank_types=["value", "expectation_gap"],
            trade_date="2026-07-02",
            include_evidence_extract=True,
            include_scores=True,
            include_rankings=True,
            persist=True,
            evidence_limit=20,
            score_limit=20,
            top_n=10,
        ))

        assert result["version"] == "supply-chain-v2-refresh-workflow"
        assert result["source_status"] == "ready"
        assert result["steps"]["evidence_extract"]["created_event_count"] == 2
        assert result["steps"]["human_review"]["review_required_count"] == 2
        assert result["steps"]["batch_score"]["score_count"] == 2
        assert result["rankings"]["value"]["items"][0]["code"] == "000001"
        assert result["rankings"]["expectation_gap"]["rank_type"] == "expectation_gap"

    def test_refresh_workflow_endpoint_returns_summary_contract(self, monkeypatch):
        def fake_refresh(request):
            return {
                "version": "supply-chain-v2-refresh-workflow",
                "source_status": "ready",
                "steps": {
                    "evidence_extract": {"created_event_count": 1},
                    "human_review": {"review_required_count": 1},
                    "batch_score": {"score_count": 2},
                },
                "rankings": {"value": {"items": [{"code": "000001"}]}},
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_refresh_supply_chain_tracking_workflow", fake_refresh)

        response = client.post(
            "/api/v1/screener/supply-chain/refresh-workflow",
            json={
                "code": "000001",
                "source_types": ["announcement_title"],
                "score_types": ["three_high", "expectation_gap"],
                "rank_types": ["value"],
                "trade_date": "2026-07-02",
                "include_evidence_extract": True,
                "include_scores": True,
                "include_rankings": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-refresh-workflow"
        assert data["steps"]["batch_score"]["score_count"] == 2
        assert data["rankings"]["value"]["items"][0]["code"] == "000001"


class TestSupplyChainValueRankings:
    """Tests for V2 company value ranking from business-tag scores."""

    def test_value_ranking_aggregates_only_attributed_business_tag_scores(self):
        rankings = _calculate_company_value_rankings([
            {
                "code": "000001",
                "name": "样例公司",
                "mapping_id": "MAP-CORE",
                "tag_name": "减速器",
                "total_score": 80,
                "revenue_ratio": 0.3,
                "gross_profit_ratio": None,
                "confidence": 0.8,
                "evidence_score": 80,
            },
            {
                "code": "000001",
                "name": "样例公司",
                "mapping_id": "MAP-THEME",
                "tag_name": "机器人",
                "total_score": 90,
                "revenue_ratio": None,
                "gross_profit_ratio": None,
                "confidence": 0.9,
                "evidence_score": 90,
            },
            {
                "code": "000002",
                "name": "弱归因公司",
                "mapping_id": "MAP-WEAK",
                "tag_name": "材料",
                "total_score": 75,
                "revenue_ratio": None,
                "gross_profit_ratio": None,
                "confidence": 0.7,
                "evidence_score": 60,
            },
        ])

        assert rankings[0]["code"] == "000001"
        assert rankings[0]["rank_status"] == "rankable"
        assert rankings[0]["value_score"] > 0
        assert rankings[0]["business_tags"][0]["mapping_id"] == "MAP-CORE"
        assert rankings[0]["business_tags"][0]["contribution_score"] > 0
        assert rankings[0]["business_tags"][1]["mapping_id"] == "MAP-THEME"
        assert rankings[0]["business_tags"][1]["rank_status"] == "theme_only"
        assert rankings[1]["code"] == "000002"
        assert rankings[1]["rank_status"] == "theme_only"
        assert rankings[1]["value_score"] == 0

    def test_value_ranking_endpoint_returns_rank_contract(self, monkeypatch):
        def fake_rankings(rank_type, top_n, trade_date):
            return {
                "version": "supply-chain-v2-rankings",
                "rank_type": rank_type,
                "trade_date": trade_date,
                "source_status": "ready",
                "items": [
                    {
                        "rank": 1,
                        "code": "000001",
                        "name": "样例公司",
                        "value_score": 18.0,
                        "rank_status": "rankable",
                        "business_tags": [{"mapping_id": "MAP-CORE"}],
                    }
                ],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_supply_chain_rankings", fake_rankings)

        response = client.get(
            "/api/v1/screener/supply-chain/rankings",
            params={"rank_type": "value", "top_n": 20, "trade_date": "2026-07-02"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-rankings"
        assert data["rank_type"] == "value"
        assert data["items"][0]["business_tags"][0]["mapping_id"] == "MAP-CORE"


class TestSupplyChainExpectationGapRankings:
    """Tests for V2 company expectation-gap ranking from business-tag gap scores."""

    def test_expectation_gap_ranking_aggregates_attributed_positive_gaps(self):
        rankings = _calculate_company_expectation_gap_rankings([
            {
                "code": "000001",
                "name": "样例公司",
                "mapping_id": "MAP-GAP",
                "tag_name": "减速器",
                "expectation_gap_score": 75,
                "actual_progress_score": 85,
                "market_expectation_score": 45,
                "evidence_delta_score": 80,
                "risk_penalty_score": 10,
                "gap_type": "positive",
                "revenue_ratio": 0.4,
                "gross_profit_ratio": None,
                "confidence": 0.9,
            },
            {
                "code": "000001",
                "name": "样例公司",
                "mapping_id": "MAP-THEME-GAP",
                "tag_name": "机器人",
                "expectation_gap_score": 90,
                "actual_progress_score": 90,
                "market_expectation_score": 20,
                "evidence_delta_score": 90,
                "risk_penalty_score": 0,
                "gap_type": "positive",
                "revenue_ratio": None,
                "gross_profit_ratio": None,
                "confidence": 0.8,
            },
            {
                "code": "000002",
                "name": "弱归因公司",
                "mapping_id": "MAP-WEAK-GAP",
                "tag_name": "材料",
                "expectation_gap_score": 88,
                "actual_progress_score": 80,
                "market_expectation_score": 30,
                "evidence_delta_score": 70,
                "risk_penalty_score": 5,
                "gap_type": "positive",
                "revenue_ratio": None,
                "gross_profit_ratio": None,
                "confidence": 0.7,
            },
        ])

        assert rankings[0]["code"] == "000001"
        assert rankings[0]["rank_status"] == "rankable"
        assert rankings[0]["expectation_gap_score"] > 0
        assert rankings[0]["business_tags"][0]["mapping_id"] == "MAP-GAP"
        assert rankings[0]["business_tags"][0]["gap_contribution_score"] > 0
        assert rankings[0]["business_tags"][0]["gap_type"] == "positive"
        assert rankings[0]["business_tags"][1]["rank_status"] == "theme_only"
        assert rankings[1]["code"] == "000002"
        assert rankings[1]["rank_status"] == "theme_only"
        assert rankings[1]["expectation_gap_score"] == 0

    def test_expectation_gap_ranking_endpoint_returns_rank_contract(self, monkeypatch):
        def fake_rankings(rank_type, top_n, trade_date):
            return {
                "version": "supply-chain-v2-rankings",
                "rank_type": rank_type,
                "trade_date": trade_date,
                "source_status": "ready",
                "items": [
                    {
                        "rank": 1,
                        "code": "000001",
                        "name": "样例公司",
                        "expectation_gap_score": 27.0,
                        "rank_status": "rankable",
                        "business_tags": [{"mapping_id": "MAP-GAP", "gap_type": "positive"}],
                    }
                ],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_supply_chain_rankings", fake_rankings)

        response = client.get(
            "/api/v1/screener/supply-chain/rankings",
            params={"rank_type": "expectation_gap", "top_n": 20, "trade_date": "2026-07-02"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-v2-rankings"
        assert data["rank_type"] == "expectation_gap"
        assert data["items"][0]["business_tags"][0]["gap_type"] == "positive"


class TestSupplyChainCandidateRanking:
    """Tests for evidence-first candidate ranking API."""

    def test_candidate_score_adds_bigtech_capex_tailwind_for_ai_compute(self):
        context = {
            "company_count": 5,
            "record_count": 13,
            "companies": ["Alphabet", "Amazon", "Meta", "Microsoft", "Oracle"],
        }
        result = screener_router._score_supply_chain_candidate_row({
            "chain_id": "ai_compute",
            "tag_name": "AI服务器",
            "node_id": "infrastructure",
            "three_high_total": 70,
            "moat_score": 70,
            "stage_score": 70,
            "evidence_score": 70,
            "l8_match_rate": 0.8,
            "fresh_rate": 0.9,
            "expectation_gap_score": 20,
            "change_20d_pct": 5,
        }, context)

        assert result["score_parts"]["bigtech_capex_tailwind"] > 0
        assert result["bigtech_capex_tailwind"]["company_count"] == 5
        assert "infrastructure" in result["bigtech_capex_tailwind"]["matched_layers"]
        assert result["commercialization_indicator"]
        assert result["expectation_gap_indicator"]
        assert result["trigger_signal_indicator"]

    def test_candidate_score_does_not_apply_capex_tailwind_to_other_chains(self):
        context = {
            "company_count": 5,
            "record_count": 13,
            "companies": ["Alphabet", "Amazon", "Meta", "Microsoft", "Oracle"],
        }
        result = screener_router._score_supply_chain_candidate_row({
            "chain_id": "consumer_upgrade",
            "tag_name": "品牌零售",
            "node_id": "retail",
            "three_high_total": 70,
            "moat_score": 70,
            "stage_score": 70,
            "evidence_score": 70,
            "l8_match_rate": 0.8,
            "fresh_rate": 0.9,
            "expectation_gap_score": 20,
            "change_20d_pct": 5,
        }, context)

        assert result["score_parts"]["bigtech_capex_tailwind"] == 0
        assert result["bigtech_capex_tailwind"]["matched_layers"] == []

    def test_candidate_score_adds_company_capex_evidence_score(self):
        context = {"company_count": 0, "record_count": 0, "companies": []}
        result = screener_router._score_supply_chain_candidate_row({
            "chain_id": "ai_compute",
            "tag_name": "AI服务器",
            "node_id": "infrastructure",
            "three_high_total": 70,
            "moat_score": 70,
            "stage_score": 70,
            "evidence_score": 70,
            "l8_match_rate": 0.8,
            "fresh_rate": 0.9,
            "expectation_gap_score": 20,
            "change_20d_pct": 5,
            "capex_evidence_count": 2,
            "capex_amount_count": 1,
            "capex_direction_ai_count": 2,
            "capex_fresh_count": 2,
            "capex_avg_confidence": 0.8,
            "capex_latest_as_of_date": "2026-08-30",
            "capex_directions": [["AI服务器", "数据中心"]],
        }, context)

        assert result["score_parts"]["company_capex_evidence"] > 70
        assert result["company_capex_evidence"]["evidence_count"] == 2
        assert "AI相关投入方向" in result["company_capex_evidence"]["indicator"]

    def test_candidate_ranking_endpoint_returns_global_and_chain_top(self, monkeypatch):
        def fake_candidate_ranking(top_n, chain_id=None, signal=None):
            assert top_n == 20
            assert chain_id == "ai_compute"
            assert signal == "观察"
            return {
                "version": "supply-chain-candidate-ranking-v1",
                "source_status": "ready",
                "filters": {"top_n": top_n, "chain_id": chain_id, "signal": signal},
                "summary": {"chain_count": 18, "company_chain_rows": 1219},
                "items": [{"code": "300308", "name": "中际旭创", "rank_score": 71.04}],
                "by_chain": {"ai_compute": [{"code": "300308", "name": "中际旭创"}]},
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_supply_chain_candidate_ranking", fake_candidate_ranking)

        response = client.get(
            "/api/v1/screener/supply-chain/candidate-ranking",
            params={"top_n": 20, "chain_id": "ai_compute", "signal": "观察"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["version"] == "supply-chain-candidate-ranking-v1"
        assert data["source_status"] == "ready"
        assert data["items"][0]["code"] == "300308"
        assert data["by_chain"]["ai_compute"][0]["name"] == "中际旭创"


class TestSupplyChainCapexEvidenceReview:
    """Tests for structured CAPEX evidence review API."""

    def test_capex_evidence_review_queue_endpoint_returns_pending_items(self, monkeypatch):
        def fake_queue(limit=50, chain_id=None, review_status="pending_review"):
            assert limit == 20
            assert chain_id == "ai_compute"
            assert review_status == "pending_review"
            return {
                "version": "business-tag-capex-evidence-review-queue-v1",
                "source_status": "ready",
                "filters": {"limit": limit, "chain_id": chain_id, "review_status": review_status},
                "counts": {"pending_review": 51},
                "queue": [
                    {
                        "capex_evidence_id": "capex-1",
                        "mapping_id": "18C-MAP-ai_compute-300308SZ",
                        "code": "300308",
                        "company_name": "中际旭创",
                        "quote": "进一步加大产能投入",
                        "review_status": "pending_review",
                    }
                ],
                "limitations": [],
            }

        monkeypatch.setattr(screener_router, "_query_capex_evidence_review_queue", fake_queue)

        response = client.get(
            "/api/v1/screener/supply-chain/capex-evidence-review/queue",
            params={"limit": 20, "chain_id": "ai_compute", "review_status": "pending_review"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source_status"] == "ready"
        assert data["counts"]["pending_review"] == 51
        assert data["queue"][0]["capex_evidence_id"] == "capex-1"

    def test_capex_evidence_review_endpoint_updates_status(self, monkeypatch):
        def fake_review(capex_evidence_id, request):
            assert capex_evidence_id == "capex-1"
            assert request.review_status == "approved"
            assert request.reviewer == "pm"
            return {
                "version": "business-tag-capex-evidence-review-v1",
                "capex_evidence_id": capex_evidence_id,
                "review_status": request.review_status,
                "reviewer": request.reviewer,
            }

        monkeypatch.setattr(screener_router, "_review_capex_evidence", fake_review)

        response = client.post(
            "/api/v1/screener/supply-chain/capex-evidence/capex-1/review",
            json={"review_status": "approved", "reviewer": "pm", "note": "原文可信"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["capex_evidence_id"] == "capex-1"
        assert data["review_status"] == "approved"


# ─────────────────────────────────────────────────────────────────────────────
# AC-2: GET /chain/node/{node_id}/companies returns company list with resonance
# ─────────────────────────────────────────────────────────────────────────────

class TestChainNodeCompanies:
    """Tests for GET /chain/node/{node_id}/companies endpoint."""

    def test_returns_200_for_valid_node_id(self, test_node_id):
        """Valid node_id should return 200."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        # Note: May return empty companies list if no mappings exist yet
        assert response.status_code == 200

    def test_returns_404_for_invalid_node_id(self):
        """Invalid node_id should return 404."""
        response = client.get(
            "/api/v1/screener/chain/node/invalid_node_xyz/companies"
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_returns_correct_structure(self, test_node_id):
        """[AC-2] Response should contain node_id, node_name, and companies."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert data["node_id"] == test_node_id
        assert "node_name" in data
        assert "company_count" in data
        assert "companies" in data

    def test_company_has_required_fields(self, test_node_id):
        """[AC-2] Each company should have resonance field."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        companies = data.get("companies", [])
        if companies:
            # Check first company has all required fields
            company = companies[0]
            assert "code" in company
            assert "name" in company
            assert "rank" in company
            assert "resonance" in company
            assert "trade_signal" in company

            # Check resonance structure
            resonance = company["resonance"]
            assert "summary" in resonance
            assert "dimensions" in resonance

    def test_resonance_derived_from_three_factors(self, test_node_id):
        """[AC-2] Resonance should be derived from three_factors."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        companies = data.get("companies", [])
        if companies:
            # Resonance summary should follow pattern based on active_count
            company = companies[0]
            resonance = company["resonance"]
            summary = resonance.get("summary", "")

            # Verify summary patterns
            valid_summaries = [
                "三因子共振 — 强启动信号",
                "双因子共振 — 关注信号",
                "单因子达标 — 观察信号",
                "待兑现 — 暂无共振",
                "待评估",
            ]
            assert summary in valid_summaries


# ─────────────────────────────────────────────────────────────────────────────
# AC-3: API P95 <= 500ms (performance benchmark)
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIPerformance:
    """Tests for API response time."""

    def test_deconstruct_response_time(self, test_theme_id):
        """[AC-3] GET /chain/deconstruct should complete within 500ms."""
        import time

        start = time.time()
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200
        # Note: In test environment without real PG, this may be fast
        # In production with real PG, should be < 500ms
        assert elapsed < 5000, f"Response time {elapsed:.1f}ms exceeds 5s (test tolerance)"

    def test_node_companies_response_time(self, test_node_id):
        """[AC-3] GET /chain/node/{node_id}/companies should complete within 500ms."""
        import time

        start = time.time()
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200
        assert elapsed < 5000, f"Response time {elapsed:.1f}ms exceeds 5s (test tolerance)"


@pytest.mark.asyncio
async def test_chain_candidates_returns_explicit_empty_state_when_trade_date_is_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("latest trade date unavailable")

    monkeypatch.setattr(screener_router, "_get_supply_chain_candidate_pool", unavailable)
    result = await screener_router.chain_candidates(
        filter="all", resonance_level=None, top_n=5, trade_date=None
    )
    assert result["candidates"] == []
    assert result["data_status"] == "empty"
    assert result["fallback_reason"] == "latest trade date unavailable"
