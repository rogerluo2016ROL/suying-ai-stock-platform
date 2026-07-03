import importlib.util
import sys
from pathlib import Path


_PIPELINE_PATH = Path(__file__).resolve().parents[1] / "supply_chain_evidence_pipeline.py"
_SPEC = importlib.util.spec_from_file_location("supply_chain_evidence_pipeline", _PIPELINE_PATH)
pipeline = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = pipeline
_SPEC.loader.exec_module(pipeline)

default_source_catalog = pipeline.default_source_catalog
extract_fact_from_text = pipeline.extract_fact_from_text
build_document_hash = pipeline.build_document_hash
map_source_type_to_source_level = pipeline.map_source_type_to_source_level
decide_stage_transition = pipeline.decide_stage_transition
build_expectation_monitor_record = pipeline.build_expectation_monitor_record
build_mapping_search_terms = pipeline.build_mapping_search_terms
build_legacy_evidence_event_record = pipeline.build_legacy_evidence_event_record


def test_default_source_catalog_covers_three_batches():
    sources = default_source_catalog()
    levels = {item.source_level for item in sources}

    assert levels == {"strong", "mid", "weak"}
    assert any(item.source_id == "cninfo_announcement" for item in sources)
    assert any(item.source_id == "financial_news_authoritative" for item in sources)
    assert any(item.source_id == "market_community_signal" for item in sources)


def test_default_source_catalog_sets_confidence_caps_and_validation_rules():
    sources = {item.source_id: item for item in default_source_catalog()}

    assert sources["cninfo_announcement"].confidence_cap == 0.95
    assert sources["financial_news_authoritative"].requires_cross_validation is True
    assert sources["market_community_signal"].confidence_cap == 0.45
    assert sources["market_community_signal"].is_market_sentiment is True


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


def test_document_hash_is_stable_for_same_content():
    first = build_document_hash("source-a", "http://x", "标题", "正文")
    second = build_document_hash("source-a", "http://x", "标题", "正文")

    assert first == second


def test_map_source_type_to_source_level_handles_chinese_sources():
    assert map_source_type_to_source_level("公告目录") == "strong"
    assert map_source_type_to_source_level("互动易") == "mid"
    assert map_source_type_to_source_level("雪球社区") == "weak"


def test_mid_source_stage_change_requires_review():
    decision = decide_stage_transition(source_level="mid", commercial_stage_signal="C4")

    assert decision.review_status == "pending_review"
    assert decision.auto_apply is False


def test_weak_source_does_not_create_stage_upgrade():
    decision = decide_stage_transition(source_level="weak", commercial_stage_signal="C4")

    assert decision.auto_apply is False
    assert decision.new_commercial_stage is None


def test_analyst_estimate_creates_expectation_claim():
    fact = extract_fact_from_text(
        text="研报预计公司机器人业务2026年收入快速增长。",
        source_level="mid",
        company_code="300503.SZ",
        l5_tag="关节模组",
        l6_route="机器人",
    )
    record = build_expectation_monitor_record(
        fact_id="FACT-001",
        mapping_id="MAP-001",
        source_doc_id="DOC-001",
        fact=fact,
    )

    assert fact.fact_nature == "analyst_estimate"
    assert record["gap_status"] == "pending"
    assert "收入快速增长" in record["claim_text"]


def test_build_mapping_search_terms_uses_company_tag_and_l1_l8_path():
    terms = build_mapping_search_terms({
        "mapping_id": "MAP-001",
        "code": "300308.SZ",
        "company_name": "中际旭创",
        "tag_name": "高速光模块",
        "chain_id": "ai_compute",
        "node_id": "optical_module",
        "l1_l8_path": ["未来产业", "AI算力", "光模块", "800G"],
    })

    assert terms["mapping_id"] == "MAP-001"
    assert "中际旭创 高速光模块" in terms["queries"]
    assert "中际旭创 800G" in terms["queries"]
    assert "300308.SZ 高速光模块" in terms["queries"]
    assert terms["terms"][:2] == ["中际旭创", "高速光模块"]


def test_build_mapping_search_terms_extracts_names_from_l1_l8_dict_path():
    terms = build_mapping_search_terms({
        "mapping_id": "MAP-002",
        "code": "000100.SZ",
        "company_name": "TCL科技",
        "tag_name": "显示面板",
        "l1_l8_path": [
            {"name": "未来显示", "level": "L2"},
            {"name": "显示面板技术路线", "level": "L6"},
            {"name": "TCL科技 - 显示面板", "level": "L8"},
        ],
    })

    assert "显示面板技术路线" in terms["terms"]
    assert "TCL科技 {'name':" not in " ".join(terms["queries"])
    assert "TCL科技 TCL科技 - 显示面板" not in terms["queries"]


def test_build_legacy_evidence_event_record_preserves_fact_and_mapping_context():
    fact = extract_fact_from_text(
        text="公司高速光模块已实现批量供货，收入快速增长。",
        source_level="strong",
        company_code="300308.SZ",
        l5_tag="高速光模块",
        l6_route="800G",
    )
    record = build_legacy_evidence_event_record(
        fact_id="FACT-001",
        mapping_id="MAP-001",
        company_code="300308.SZ",
        node_id="optical_module",
        source_id="cninfo_announcement",
        source_type="announcement",
        title="公告标题",
        url="https://example.com/a",
        fact=fact,
    )

    assert record["mapping_id"] == "MAP-001"
    assert record["event_id"].startswith("EV-")
    assert record["evidence_type"] == "commercial_stage"
    assert record["review_status"] == "approved"
    assert record["impact_dimensions"]["growth"] is True
