import importlib.util
import inspect
import sys
import types
from datetime import datetime, timezone
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


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


def _install_fake_psycopg2(monkeypatch, cursor):
    connection = _FakeConnection(cursor)
    monkeypatch.setitem(
        sys.modules,
        "psycopg2",
        types.SimpleNamespace(connect=lambda _pg_url: connection),
    )
    return connection


class _IngestCursor:
    rowcount = 1

    def __init__(self):
        self.calls = []
        self._one = None
        self._many = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        self.rowcount = 1
        self._one = None
        self._many = []
        if "FROM evidence_source_catalog" in sql:
            self._one = ("cninfo_announcement", "announcement", "strong", 0.95, "available")
        elif "FROM business_tag_mapping" in sql:
            mapping_id = "MAP-EXPLICIT" if "mapping_id = %s" in sql else "MAP-HIGHEST-CONFIDENCE"
            row = (mapping_id, "embodied_intelligence", "灵巧手执行器", "robot_hand")
            self._one = row
            self._many = [row]
        elif "RETURNING doc_id" in sql:
            self._one = ("DOC-STORED",)

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._many


def _call_ingest(cursor, monkeypatch, *, publish_time_marker, mapping_id_marker):
    _install_fake_psycopg2(monkeypatch, cursor)
    kwargs = {
        "pg_url": "postgresql://fake",
        "source_id": "cninfo_announcement",
        "company_code": "003021",
        "company_name": "兆威机电",
        "title": "公告",
        "text": "公司灵巧手执行器已实现批量供货。",
    }
    parameters = inspect.signature(pipeline.ingest_text_document).parameters
    if "publish_time" in parameters:
        kwargs["publish_time"] = publish_time_marker
    if "mapping_id" in parameters:
        kwargs["mapping_id"] = mapping_id_marker
    return pipeline.ingest_text_document(**kwargs)


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


def test_extract_fact_from_strong_source_still_requires_review():
    fact = extract_fact_from_text(
        text="公司800G高速光模块已实现批量供货，收入占比持续提升。",
        source_level="strong",
        company_code="300308.SZ",
        l5_tag="高速光模块",
        l6_route="800G",
    )

    assert fact.commercial_stage_signal == "C4"
    assert fact.growth_signal is True
    assert fact.validation_status == "pending"


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


def test_strong_stage_signal_requires_review_and_is_not_auto_applied():
    decision = decide_stage_transition(
        source_level="strong",
        commercial_stage_signal="C4",
    )

    assert decision.review_status == "pending_review"
    assert decision.auto_apply is False


def test_ingest_text_document_requires_explicit_time_and_mapping_contract():
    parameters = inspect.signature(pipeline.ingest_text_document).parameters

    assert "publish_time" in parameters
    assert "mapping_id" in parameters
    assert "metadata" in inspect.signature(pipeline.ExtractedFact).parameters


def test_pipeline_pending_fact_preserves_sanitized_metadata():
    metadata = {
        "application_domain": "dexterous_hand",
        "installation_position": "robot_wrist",
        "legal_status": "granted",
        "legal_status_date": "2026-07-09",
        "review_normalization": {"risk_score": 99},
    }
    parameters = inspect.signature(extract_fact_from_text).parameters
    assert "metadata" in parameters

    fact = extract_fact_from_text(
        text="公司机器人产品已获得专利。",
        source_level="strong",
        company_code="003021",
        l5_tag="灵巧手执行器",
        metadata=metadata,
    )

    assert fact.metadata == {
        "application_domain": "dexterous_hand",
        "installation_position": "robot_wrist",
        "legal_status": "granted",
        "legal_status_date": "2026-07-09",
    }


def test_ingest_stores_supplied_publish_time_and_exact_mapping(monkeypatch):
    cursor = _IngestCursor()
    publish_time = datetime(2026, 7, 9, 9, 0, tzinfo=timezone.utc)

    result = _call_ingest(
        cursor,
        monkeypatch,
        publish_time_marker=publish_time,
        mapping_id_marker="MAP-EXPLICIT",
    )
    raw_sql, raw_params = next(call for call in cursor.calls if "INSERT INTO raw_evidence_documents" in call[0])
    _, fact_params = next(call for call in cursor.calls if "INSERT INTO evidence_extracted_facts" in call[0])

    assert raw_params[7] == publish_time
    assert "publish_time = EXCLUDED.publish_time" in raw_sql
    assert fact_params[2] == "MAP-EXPLICIT"
    assert result.get("mapping_id") == "MAP-EXPLICIT"


def test_ingest_with_unknown_mapping_stores_nulls_and_returns_mapping_required(monkeypatch):
    cursor = _IngestCursor()

    result = _call_ingest(
        cursor,
        monkeypatch,
        publish_time_marker=None,
        mapping_id_marker=None,
    )
    _, raw_params = next(call for call in cursor.calls if "INSERT INTO raw_evidence_documents" in call[0])
    _, fact_params = next(call for call in cursor.calls if "INSERT INTO evidence_extracted_facts" in call[0])

    assert not any(
        "SELECT mapping_id, chain_id, tag_name, node_id" in " ".join(sql.split())
        for sql, _ in cursor.calls
    )
    assert raw_params[7] is None
    assert fact_params[2] is None
    assert result.get("status") == "mapping_required"


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
    assert record["review_status"] == "pending_review"
    assert record["impact_dimensions"]["growth"] is True


def test_backfill_approved_strong_event_still_writes_pending_fact_and_null_unknown_time(monkeypatch):
    class BackfillCursor:
        rowcount = 1

        def __init__(self):
            self.calls = []
            self._one = None
            self._many = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            self.rowcount = 1
            self._one = None
            self._many = []
            if "FROM business_tag_evidence_events e" in sql:
                self._many = [(
                    "EV-OLD",
                    "MAP-001",
                    "003021",
                    None,
                    "公告",
                    "公告标题",
                    "公司灵巧手执行器已实现批量供货。",
                    "https://example.com/a",
                    "commercial_stage",
                    0.9,
                    "approved",
                    "灵巧手执行器",
                    "embodied_intelligence",
                )]
            elif "RETURNING doc_id" in sql:
                self._one = ("DOC-STORED",)

        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._many

    cursor = BackfillCursor()
    _install_fake_psycopg2(monkeypatch, cursor)

    pipeline.backfill_existing_events(pg_url="postgresql://fake")
    _, raw_params = next(call for call in cursor.calls if "INSERT INTO raw_evidence_documents" in call[0])
    _, fact_params = next(call for call in cursor.calls if "INSERT INTO evidence_extracted_facts" in call[0])

    assert raw_params[6] is None
    assert fact_params[20] == "pending"


def test_refresh_stage_transitions_only_creates_pending_proposals(monkeypatch):
    class StageCursor:
        rowcount = 1

        def __init__(self):
            self.calls = []
            self._one = None
            self._many = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            self.rowcount = 1
            self._one = None
            self._many = []
            if "FROM evidence_extracted_facts f" in sql:
                self._many = [(
                    "FACT-001",
                    "MAP-001",
                    "EV-001",
                    "strong",
                    None,
                    "C4",
                    "公司已实现批量供货。",
                    datetime(2026, 7, 9, 9, 0),
                )]
            elif "FROM business_tag_stage_tracking" in sql:
                self._one = None

        def fetchone(self):
            return self._one

        def fetchall(self):
            return self._many

    cursor = StageCursor()
    _install_fake_psycopg2(monkeypatch, cursor)

    result = pipeline.refresh_stage_transitions(pg_url="postgresql://fake")
    _, transition_params = next(
        call for call in cursor.calls if "INSERT INTO business_tag_stage_transition_log" in call[0]
    )

    assert transition_params[-1] == "pending_review"
    assert not any("INSERT INTO business_tag_stage_tracking" in sql for sql, _ in cursor.calls)
    assert result["stage_applied"] == 0
