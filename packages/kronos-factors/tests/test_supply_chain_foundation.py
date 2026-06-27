from pathlib import Path

from kronos_factors.engine.supply_chain_foundation import (
    build_foundation_catalog,
    build_foundation_report,
    load_supply_chain_config,
    mapping_to_pg_rows,
    score_company_mappings,
)
from kronos_factors.engine.supply_chain import _merge_mapping_context


def _sample_config():
    return {
        "chains": {
            "半导体": {
                "industries": ["半导体", "元器件"],
                "layers": ["材料", "设备", "制造", "封测", "设计"],
                "layer_keywords": {
                    "材料": ["光刻胶", "电子级玻璃布"],
                    "设备": ["刻蚀", "薄膜沉积"],
                    "制造": ["晶圆制造"],
                    "封测": ["封装测试"],
                    "设计": ["集成电路设计"],
                },
            },
            "AI算力": {
                "industries": ["通信设备", "软件服务"],
                "layers": ["硬件", "软件", "应用"],
                "layer_keywords": {
                    "硬件": ["光模块", "服务器"],
                    "软件": ["软件", "数据库"],
                    "应用": ["解决方案"],
                },
            },
        }
    }


def test_build_foundation_catalog_creates_chain_and_layer_nodes():
    catalog = build_foundation_catalog(_sample_config())
    node_ids = {node["node_id"] for node in catalog.nodes}

    assert "chain_semiconductor" in node_ids
    assert "semiconductor_materials" in node_ids
    assert "chain_ai_compute" in node_ids
    assert "ai_compute_hardware" in node_ids
    assert len(catalog.nodes) == 10


def test_build_foundation_catalog_creates_non_orphan_edges():
    catalog = build_foundation_catalog(_sample_config())
    node_ids = {node["node_id"] for node in catalog.nodes}

    assert len(catalog.edges) >= 8
    for edge in catalog.edges:
        assert edge["from_node_id"] in node_ids
        assert edge["to_node_id"] in node_ids


def test_score_company_mappings_labels_verified_when_business_and_industry_match():
    catalog = build_foundation_catalog(_sample_config())
    companies = [
        {
            "code": "301526",
            "name": "国际复材",
            "industry": "元器件",
            "main_business": "电子级玻璃纤维和电子级玻璃布研发生产销售",
            "introduction": "",
            "report_titles": [],
        }
    ]

    mappings = score_company_mappings(catalog, companies, min_confidence=0.30)

    assert mappings
    best = mappings[0]
    assert best.code == "301526"
    assert best.node_id == "semiconductor_materials"
    assert best.confidence >= 0.85
    assert best.status == "verified"
    assert best.mapping_source == "main_business"


def test_score_company_mappings_keeps_weak_industry_match_separate():
    catalog = build_foundation_catalog(_sample_config())
    companies = [
        {
            "code": "000001",
            "name": "测试半导体",
            "industry": "半导体",
            "main_business": "",
            "introduction": "",
            "report_titles": [],
        }
    ]

    mappings = score_company_mappings(catalog, companies, min_confidence=0.30)

    assert mappings
    assert mappings[0].node_id == "chain_semiconductor"
    assert mappings[0].confidence == 0.30
    assert mappings[0].status == "weak_evidence"
    assert mappings[0].mapping_source == "industry"


def test_real_config_catalog_meets_first_phase_node_and_edge_thresholds():
    config = load_supply_chain_config(Path(__file__).resolve().parents[1] / "configs" / "supply_chains.json")
    catalog = build_foundation_catalog(config)
    report = build_foundation_report(catalog, [])

    assert report["node_count"] >= 35
    assert report["edge_count"] >= 30
    assert "audit" in report


def test_generic_keyword_without_industry_match_is_not_promoted():
    catalog = build_foundation_catalog(_sample_config())
    companies = [
        {
            "code": "000002",
            "name": "泛服务公司",
            "industry": "房地产",
            "main_business": "软件服务和解决方案",
            "introduction": "",
            "report_titles": [],
        }
    ]

    mappings = score_company_mappings(catalog, companies, min_confidence=0.30)

    assert mappings == []


def test_mapping_to_pg_rows_contains_bom_and_chain_rows():
    catalog = build_foundation_catalog(_sample_config())
    mapping = score_company_mappings(catalog, [{
        "code": "301526",
        "name": "国际复材",
        "industry": "元器件",
        "main_business": "电子级玻璃布",
        "introduction": "",
        "report_titles": [],
    }])[0]

    rows = mapping_to_pg_rows(mapping)

    assert rows["company_bom_mapping"]["code"] == "301526"
    assert rows["company_bom_mapping"]["status"] == "verified"
    assert rows["company_chain_mapping"]["policy_match_score"] >= 0.80
    assert rows["company_chain_mapping"]["evidence"]["mapping_source"] == "main_business"


def test_merge_mapping_context_adds_mapping_fields_without_overwriting_score():
    pick = {"code": "301526", "name": "国际复材", "chain": "半导体", "total_score": 71.0}
    context = {
        "301526": [
            {
                "node_id": "ai_compute_hardware",
                "node_name": "硬件",
                "chain_id": "ai_compute",
                "mapping_confidence": 0.9,
                "mapping_status": "verified",
                "mapping_source": "main_business",
                "evidence_gaps": [],
            },
            {
                "node_id": "semiconductor_materials",
                "node_name": "材料",
                "chain_id": "semiconductor",
                "mapping_confidence": 0.85,
                "mapping_status": "verified",
                "mapping_source": "main_business",
                "evidence_gaps": [],
            },
        ]
    }

    merged = _merge_mapping_context(pick, context)

    assert merged["total_score"] == 71.0
    assert merged["node_id"] == "semiconductor_materials"
    assert merged["mapping_confidence"] == 0.85
    assert merged["mapping_status"] == "verified"


def test_merge_mapping_context_adds_quality_weight_for_ranking():
    pick = {"code": "688001", "name": "弱证据公司", "chain": "半导体", "total_score": 80.0}
    context = {
        "688001": [
            {
                "node_id": "chain_semiconductor",
                "node_name": "半导体",
                "chain_id": "semiconductor",
                "mapping_confidence": 0.3,
                "mapping_status": "weak_evidence",
                "mapping_source": "industry",
                "evidence_gaps": ["缺少公司到产业链节点的正式映射"],
            }
        ]
    }

    merged = _merge_mapping_context(pick, context)

    assert merged["total_score"] == 80.0
    assert merged["mapping_quality_weight"] == 0.85
    assert merged["mapping_adjusted_score"] == 68.0


def test_merge_mapping_context_keeps_verified_mapping_at_full_weight():
    pick = {"code": "301526", "name": "国际复材", "chain": "半导体", "total_score": 80.0}
    context = {
        "301526": [
            {
                "node_id": "semiconductor_materials",
                "node_name": "材料",
                "chain_id": "semiconductor",
                "mapping_confidence": 0.85,
                "mapping_status": "verified",
                "mapping_source": "main_business",
                "evidence_gaps": [],
            }
        ]
    }

    merged = _merge_mapping_context(pick, context)

    assert merged["mapping_quality_weight"] == 1.0
    assert merged["mapping_adjusted_score"] == 80.0


def test_merge_mapping_context_ignores_rejected_mapping():
    pick = {"code": "000001", "name": "被驳回公司", "chain": "半导体", "total_score": 80.0}
    context = {
        "000001": [
            {
                "node_id": "semiconductor_materials",
                "node_name": "材料",
                "chain_id": "semiconductor",
                "mapping_confidence": 0.9,
                "mapping_status": "rejected",
                "mapping_source": "manual_review",
                "evidence_gaps": [],
            }
        ]
    }

    merged = _merge_mapping_context(pick, context)

    assert merged["mapping_status"] == "weak_evidence"
    assert merged["mapping_source"] == "fallback_keyword"
    assert merged["mapping_quality_weight"] == 0.75
    assert merged["mapping_adjusted_score"] == 60.0
