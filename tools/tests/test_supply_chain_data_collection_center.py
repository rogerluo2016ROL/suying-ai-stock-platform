import importlib.util
import inspect
import json
import sys
import types
from pathlib import Path


_CENTER_PATH = Path(__file__).resolve().parents[1] / "supply_chain_data_collection_center.py"
_SPEC = importlib.util.spec_from_file_location("supply_chain_data_collection_center", _CENTER_PATH)
center = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = center
_SPEC.loader.exec_module(center)


def _normalized_sql(sql):
    return " ".join(sql.split())


def _conflict_update_clause(sql):
    normalized = _normalized_sql(sql)
    assert "ON CONFLICT" in normalized
    return normalized.split("ON CONFLICT", 1)[1]


def _assert_manual_review_columns_are_untouched(sql):
    update_clause = _conflict_update_clause(sql)
    assert "review_status = EXCLUDED.review_status" not in update_clause
    assert "review_note = EXCLUDED.review_note" not in update_clause
    assert "reviewer = EXCLUDED.reviewer" not in update_clause
    assert "reviewed_at = EXCLUDED.reviewed_at" not in update_clause


def test_default_collection_sources_cover_three_layers():
    sources = center.default_collection_sources()
    levels = {source.source_level for source in sources}

    assert levels == {"strong", "mid", "weak"}
    assert any(source.source_id == "cninfo_announcement" for source in sources)
    assert any(source.source_id == "broker_expectation" for source in sources)
    assert any(source.source_id == "market_community_signal" for source in sources)


def test_collection_sources_keep_weak_signal_below_strong_confidence():
    sources = {source.source_id: source for source in center.default_collection_sources()}

    assert sources["cninfo_announcement"].confidence_cap == 0.95
    assert sources["market_community_signal"].confidence_cap == 0.45
    assert sources["market_community_signal"].is_market_sentiment is True
    assert sources["broker_expectation"].license_status == "license_required"
    assert sources["broker_expectation_local"].license_status == "available"
    assert sources["broker_expectation_local"].crawl_method == "existing_table"
    assert sources["financial_news_authoritative"].license_status == "available"
    assert sources["financial_news_authoritative"].source_type == "financial_news"


def test_document_hash_is_idempotent():
    first = center.build_document_hash("source", "https://example.com/a", "标题", "正文")
    second = center.build_document_hash("source", "https://example.com/a", "标题", "正文")

    assert first == second


def test_extract_cninfo_announcement_id_from_detail_url():
    url = "http://www.cninfo.com.cn/new/disclosure/detail?stockCode=600735&announcementId=1225402146&orgId=x"

    assert center.extract_cninfo_announcement_id(url) == "1225402146"


def test_cninfo_pdf_url_uses_static_host():
    assert center.cninfo_pdf_url("finalpage/2026-07-01/1225402146.PDF") == (
        "http://static.cninfo.com.cn/finalpage/2026-07-01/1225402146.PDF"
    )


def test_cninfo_title_relevance_filters_noise_and_keeps_projects():
    assert center.is_relevant_cninfo_title("关于实施清洁能源设备和技术改造升级项目的对外投资公告") is True
    assert center.is_relevant_cninfo_title("关于控股股东股份解除质押的公告") is False
    assert center.is_relevant_cninfo_title("2025年度股东会的法律意见书") is False


def test_tender_cninfo_title_only_keeps_order_related_titles():
    assert center.is_tender_cninfo_title("关于收到项目中标通知书的公告") is True
    assert center.is_tender_cninfo_title("关于签订重大合同的公告") is True
    assert center.is_tender_cninfo_title("关于实施清洁能源设备和技术改造升级项目的对外投资公告") is False
    assert center.is_tender_cninfo_title("关于募集资金投资项目可行性报告") is False
    assert center.is_tender_cninfo_title("关于控股股东股份解除质押的公告") is False


def test_industry_index_keywords_cover_core_chains():
    assert "算力" in center.CHAIN_INDEX_KEYWORDS["ai_compute"]
    assert "人形机器人" in center.CHAIN_INDEX_KEYWORDS["embodied_intelligence"]
    assert "半导体设备" in center.CHAIN_INDEX_KEYWORDS["semiconductor_equipment_materials"]


def test_government_project_keywords_filter_common_noise():
    assert "政府补助" in center.GOVERNMENT_PROJECT_KEYWORDS
    assert "示范项目" in center.GOVERNMENT_PROJECT_KEYWORDS
    assert "募集资金" in center.GOVERNMENT_PROJECT_NOISE_KEYWORDS
    assert "核查意见" in center.GOVERNMENT_PROJECT_NOISE_KEYWORDS


def test_ensure_weak_signal_source_rejects_strong_source():
    try:
        center.ensure_weak_signal_source("cninfo_announcement")
    except ValueError as exc:
        assert "not a weak-signal source" in str(exc)
    else:
        raise AssertionError("strong sources must not be accepted for weak-signal import")


def test_load_weak_signal_documents_from_jsonl(tmp_path):
    file_path = tmp_path / "weak.jsonl"
    file_path.write_text(
        '{"title":"社区线索","content_text":"传闻公司机器人业务有新增订单，待验证。","company_code":"002708.SZ","company_name":"光洋股份"}\n',
        encoding="utf-8",
    )

    docs = center.load_weak_signal_documents(str(file_path), "market_community_signal")

    assert len(docs) == 1
    assert docs[0].source_level == "weak"
    assert docs[0].source_id == "market_community_signal"
    assert docs[0].company_code == "002708.SZ"


def test_scheduled_collection_plan_contains_daily_and_manual_batches():
    plan = center.scheduled_collection_plan()
    batches = {item["batch"]: item for item in plan}

    assert "daily_core" in batches
    assert "manual_weak_signal" in batches
    assert "refresh_expectation_scores" in batches["daily_core"]["tasks"]
    assert "import_weak_signals" in batches["manual_weak_signal"]["tasks"]


def test_industry_index_helpers_are_stable():
    assert center._date_from_yyyymmdd("20260630") == "2026-06-30"
    assert center._date_from_yyyymmdd("bad") is None
    first = center._industry_series_id("source", "chain", "metric", "2026-06-30", "region")
    second = center._industry_series_id("source", "chain", "metric", "2026-06-30", "region")
    assert first == second
    assert first.startswith("IPS-")


def test_stage_progress_score_uses_higher_of_research_and_commercial():
    assert center.calculate_stage_progress_score("R5", "C1") == 75.0
    assert center.calculate_stage_progress_score("R1", "C4") == 80.0
    assert center.calculate_stage_progress_score(None, None) == 0.0


def test_market_expectation_score_responds_to_claims_and_price_reaction():
    quiet = center.calculate_market_expectation_score(
        analyst_claims=0,
        news_claims=0,
        total_claims=0,
        price_change_20d=0,
    )
    hot = center.calculate_market_expectation_score(
        analyst_claims=4,
        news_claims=3,
        total_claims=9,
        price_change_20d=18,
    )

    assert quiet == 35.0
    assert hot > quiet
    assert hot <= 100.0


def test_prosperity_score_uses_index_proxy_but_stays_bounded():
    assert center.calculate_prosperity_score(3.0, 1.0) == 61.0
    assert center.calculate_prosperity_score(-30.0, -10.0) == 0.0
    assert center.calculate_prosperity_score(50.0, 50.0) == 100.0


def test_normalize_website_url_adds_scheme():
    assert center.normalize_website_url("www.example.com/") == "http://www.example.com"
    assert center.normalize_website_url("https://www.example.com/news") == "https://www.example.com/news"


def test_html_to_text_removes_tags_and_scripts():
    html = "<html><head><script>bad()</script></head><body><h1>产品发布</h1><p>客户合作</p></body></html>"

    text = center.html_to_text(html)

    assert "产品发布" in text
    assert "客户合作" in text
    assert "bad()" not in text


def test_extract_relevant_official_links_filters_noise_and_external_links():
    html = """
    <a href="/news/product.html">产品新闻</a>
    <a href="/jobs">招聘</a>
    <a href="https://other.example.com/news">外部新闻</a>
    <a href="/ir">投资者关系</a>
    """

    links = center.extract_relevant_official_links("https://www.example.com", html, max_links=5)

    assert "https://www.example.com/news/product.html" in links
    assert "https://www.example.com/ir" in links
    assert all("jobs" not in item for item in links)
    assert all("other.example.com" not in item for item in links)


def test_response_text_uses_apparent_encoding():
    class Response:
        apparent_encoding = "utf-8"
        encoding = None
        text = "中文标题"

    response = Response()

    assert center.response_text(response) == "中文标题"
    assert response.encoding == "utf-8"


def test_parse_tender_award_fact_detects_award_and_amount():
    fact = center.parse_tender_award_fact(
        "关于公司收到中标通知书的公告",
        "公司收到某项目中标通知书，中标金额为1.23亿元。",
        "测试公司",
    )

    assert fact["event_type"] == "award"
    assert fact["award_amount"] == 123000000
    assert fact["currency"] == "CNY"
    assert fact["commercial_signal"] == "C4"


def test_parse_tender_amount_prefers_contextual_rmb_amount():
    amount, currency = center.parse_tender_amount(
        "合同金额为98,992,200.00美元，按汇率1美元对人民币7.0348元计算，折合人民币约6.96亿元。"
    )

    assert amount == 696000000
    assert currency == "CNY"


def test_parse_tender_amount_supports_comma_yuan_amount():
    amount, currency = center.parse_tender_amount("中标金额：199,799,325.00 元。")

    assert amount == 199799325
    assert currency == "CNY"


def test_parse_tender_amount_ignores_unrelated_numbers_without_context():
    assert center.parse_tender_amount("公告编号2025-044，公司召开会议。") == (None, None)


def test_parse_patent_event_fact_detects_granted_ip_signal():
    fact = center.parse_patent_event_fact(
        "关于取得发明专利证书的公告",
        "公司近日获得一项发明专利授权，该专利用于高速连接器结构设计。",
        "测试公司",
    )

    assert fact["patent_status"] == "granted_or_obtained"
    assert fact["moat_signal"] is True
    assert "发明专利" in fact["patent_abstract"]


def test_parse_patent_event_fact_ignores_non_ip_text():
    assert center.parse_patent_event_fact("普通经营公告", "公司召开经营会议。") is None


def test_parse_tender_award_fact_detects_framework_agreement():
    fact = center.parse_tender_award_fact(
        "关于签订框架协议的公告",
        "公司与客户签订框架协议，预计采购金额5000万元。",
        "测试公司",
    )

    assert fact["event_type"] == "framework_agreement"
    assert fact["award_amount"] == 50000000


def test_parse_tender_award_fact_returns_none_without_signal():
    assert center.parse_tender_award_fact("普通新闻", "公司召开会议。") is None


def test_parse_tender_award_fact_rejects_noise_titles_even_with_amounts():
    assert center.parse_tender_award_fact(
        "关于募集资金使用的可行性报告",
        "报告提到采购设备和合同金额1亿元。",
        "测试公司",
    ) is None
    assert center.parse_tender_award_fact(
        "关于使用部分闲置自有资金进行现金管理合同到期的公告",
        "公司现金管理合同到期，赎回本金6亿元。",
        "测试公司",
    ) is None


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

    assert fact.fact_type == "commercial_progress"
    assert fact.commercial_stage_signal == "C4"
    assert fact.validation_status == "pending"


def test_pending_fact_preserves_only_sanitized_explicit_document_metadata():
    metadata = {
        "application_domain": "dexterous_hand",
        "installation_position": "robot_wrist",
        "revenue_confirmed": False,
        "legal_status": "granted",
        "legal_status_date": "2026-07-09",
        "review_normalization": {"risk_score": 99},
    }
    assert "metadata" in inspect.signature(center.RawDocument).parameters
    assert "metadata" in inspect.signature(center.ExtractedFact).parameters

    document = center.RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="产品与专利公告",
        content_text="公司机器人产品已获得专利。",
        company_code="003021",
        metadata=metadata,
    )

    fact = center.extract_fact_from_document(document)

    assert fact.metadata == {
        "application_domain": "dexterous_hand",
        "installation_position": "robot_wrist",
        "revenue_confirmed": False,
        "legal_status": "granted",
        "legal_status_date": "2026-07-09",
    }


def test_center_pending_fact_metadata_is_deep_copied():
    metadata = {"route_context": {"positions": ["robot_wrist"]}}
    fact = center.extract_fact_from_document(center.RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="产品公告",
        content_text="公司机器人产品已获得专利。",
        company_code="003021",
        metadata=metadata,
    ))

    metadata["route_context"]["positions"].append("robot_joint")

    assert fact.metadata == {"route_context": {"positions": ["robot_wrist"]}}


def test_pending_document_metadata_round_trips_without_guessing_mapping():
    metadata = {
        "application_domain": "dexterous_hand",
        "installation_position": "robot_wrist",
        "revenue_confirmed": False,
        "legal_status": "granted",
        "legal_status_date": "2026-07-09",
        "review_normalization": {"risk_score": 99},
    }
    document_kwargs = {
        "source_id": "cninfo_announcement",
        "source_level": "strong",
        "title": "产品与专利公告",
        "content_text": "公司机器人产品已获得专利。",
        "company_code": "003021",
        "publish_time": "2026-07-09T09:00:00+08:00",
    }
    if "metadata" in inspect.signature(center.RawDocument).parameters:
        document_kwargs["metadata"] = metadata
    document = center.RawDocument(**document_kwargs)

    class RecordingCursor:
        rowcount = 1

        def __init__(self):
            self.calls = []
            self._one = None

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            self.rowcount = 1
            self._one = None
            if "RETURNING (xmax = 0) AS inserted" in sql:
                self._one = (True,)
            elif "SELECT mapping_id, chain_id, node_id, tag_name" in _normalized_sql(sql):
                self._one = {
                    "mapping_id": "MAP-EXPLICIT",
                    "chain_id": "embodied_intelligence",
                    "node_id": "robot_component",
                    "tag_name": "机器人零部件",
                }

        def fetchone(self):
            return self._one

    cursor = RecordingCursor()
    result = center._insert_raw_document_and_fact(
        cursor,
        document,
        center._source_by_id("cninfo_announcement"),
        "JOB-1",
    )
    raw_sql, raw_params = next(call for call in cursor.calls if "INSERT INTO raw_evidence_documents" in call[0])
    fact_sql, fact_params = next(call for call in cursor.calls if "INSERT INTO evidence_extracted_facts" in call[0])
    raw_metadata = json.loads(raw_params[-1])
    fact_metadata = json.loads(fact_params[-1])

    assert raw_metadata["review_normalization"] == {"risk_score": 99}
    assert raw_metadata["application_domain"] == "dexterous_hand"
    assert fact_metadata["application_domain"] == "dexterous_hand"
    assert fact_metadata["installation_position"] == "robot_wrist"
    assert fact_metadata["revenue_confirmed"] is False
    assert fact_metadata["legal_status"] == "granted"
    assert fact_metadata["legal_status_date"] == "2026-07-09"
    assert "review_normalization" not in fact_metadata
    assert fact_params[2] is None
    assert not any("FROM business_tag_mapping" in sql for sql, _ in cursor.calls)
    assert result.get("status") == "mapping_required"
    raw_update = _conflict_update_clause(raw_sql)
    fact_update = _conflict_update_clause(fact_sql)
    conflict_contract = {
        "raw_keeps_existing_publish_time": (
            "publish_time = COALESCE(raw_evidence_documents.publish_time, EXCLUDED.publish_time)" in raw_update
        ),
        "raw_existing_metadata_wins": "metadata = EXCLUDED.metadata || raw_evidence_documents.metadata" in raw_update,
        "fact_keeps_existing_validation": "validation_status = EXCLUDED.validation_status" not in fact_update,
        "fact_existing_metadata_wins": (
            "metadata = (EXCLUDED.metadata - 'review_normalization') || evidence_extracted_facts.metadata"
            in fact_update
        ),
    }
    assert conflict_contract == {
        "raw_keeps_existing_publish_time": True,
        "raw_existing_metadata_wins": True,
        "fact_keeps_existing_validation": True,
        "fact_existing_metadata_wins": True,
    }


def test_generic_keyword_hit_does_not_invent_route_metadata():
    fact = center.extract_fact_from_document(center.RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="普通业务公告",
        content_text="公司机器人产品已获得专利并形成收入。",
        company_code="003021",
    ))

    assert getattr(fact, "metadata", {"missing": True}) is None


def test_extract_fact_from_weak_document_does_not_upgrade_stage():
    document = center.RawDocument(
        source_id="market_community_signal",
        source_level="weak",
        title="社区讨论",
        content_text="社区讨论称公司可能有机器人订单。",
        company_code="002979.SZ",
    )

    fact = center.extract_fact_from_document(document)

    assert fact.fact_type == "weak_signal"
    assert fact.research_stage_signal is None
    assert fact.commercial_stage_signal is None
    assert fact.validation_status == "pending"


def test_build_mapping_keywords_uses_company_and_l1_l8_terms():
    result = center.build_mapping_keywords({
        "mapping_id": "MAP-1",
        "code": "688629",
        "company_name": "华丰科技",
        "tag_name": "高速连接器",
        "chain_id": "ai_compute",
        "node_id": "ai_compute_hardware",
        "l1_l8_path": [
            {"name": "未来产业主攻方向", "layer": "L1"},
            {"name": "AI算力", "layer": "L2"},
            {"name": "高速背板连接器", "layer": "L6"},
        ],
    })

    assert result["mapping_id"] == "MAP-1"
    assert "华丰科技 高速连接器" in result["queries"]
    assert "华丰科技 高速背板连接器" in result["queries"]
    assert "688629 高速连接器" in result["queries"]


def test_build_mapping_keywords_falls_back_to_l8_company_name():
    result = center.build_mapping_keywords({
        "mapping_id": "MAP-2",
        "code": "002708.SZ",
        "company_name": "",
        "tag_name": "机器人轴承",
        "l1_l8_path": [
            {"name": "具身智能", "layer": "L2"},
            {"name": "光洋股份 - 机器人轴承/关节零部件", "layer": "L8"},
        ],
    })

    assert result["company_name"] == "光洋股份"
    assert "光洋股份 机器人轴承" in result["queries"]


def test_run_source_supports_only_existing_backfill_sources():
    try:
        center.run_existing_source_backfill("postgresql://invalid", "broker_expectation", limit=1)
    except ValueError as exc:
        assert "currently supports" in str(exc)
    else:
        raise AssertionError("broker_expectation should not run without a licensed adapter")


def test_build_legacy_event_record_from_strong_fact_requires_review():
    record = center.build_legacy_event_record_from_fact({
        "fact_id": "FACT-1",
        "mapping_id": "MAP-1",
        "company_code": "300308.SZ",
        "node_id": "optical_module",
        "fact_type": "commercial_progress",
        "source_level": "strong",
        "validation_status": "confirmed",
        "source_id": "cninfo_announcement",
        "source_type": "announcement",
        "title": "公告",
        "original_quote": "公司已批量供货。",
        "growth_signal": True,
        "profit_signal": False,
        "moat_signal": False,
        "risk_signal": False,
        "commercial_stage_signal": "C4",
    })

    assert record["event_id"].startswith("EV-")
    assert record["evidence_type"] == "commercial_stage"
    assert record["review_status"] == "pending_review"
    assert record["impact_dimensions"]["growth"] is True


def test_build_legacy_event_record_from_weak_fact_requires_review():
    record = center.build_legacy_event_record_from_fact({
        "fact_id": "FACT-2",
        "mapping_id": "MAP-2",
        "company_code": "002979.SZ",
        "fact_type": "weak_signal",
        "source_level": "weak",
        "validation_status": "pending",
    })

    assert record["evidence_type"] == "weak_signal"
    assert record["review_status"] == "pending_review"


def test_center_event_sync_conflict_preserves_existing_approved_review_fields(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []
            self._many = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql, params=None):
            self.calls.append((sql, params))
            self._many = []
            if "FROM evidence_extracted_facts f" in sql:
                self._many = [{
                    "fact_id": "FACT-APPROVED",
                    "mapping_id": "MAP-001",
                    "company_code": "300308.SZ",
                    "fact_type": "commercial_progress",
                    "original_quote": "公司已批量供货。",
                    "source_level": "strong",
                    "confidence": 0.8,
                    "validation_status": "confirmed",
                    "research_stage_signal": None,
                    "commercial_stage_signal": "C4",
                    "growth_signal": True,
                    "profit_signal": False,
                    "moat_signal": False,
                    "risk_signal": False,
                    "source_id": "cninfo_announcement",
                    "source_type": "announcement",
                    "title": "公告",
                    "publish_time": "2026-07-09",
                    "url": "https://example.com/a",
                    "node_id": "optical_module",
                }]

        def fetchall(self):
            return self._many

    class Connection:
        def __init__(self, cursor):
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def cursor(self, cursor_factory=None):
            return self._cursor

        def commit(self):
            return None

    cursor = Cursor()
    connection = Connection(cursor)
    psycopg2 = types.ModuleType("psycopg2")
    extras = types.ModuleType("psycopg2.extras")
    psycopg2.__path__ = []
    psycopg2.connect = lambda _pg_url: connection
    psycopg2.extras = extras
    extras.RealDictCursor = object
    monkeypatch.setitem(sys.modules, "psycopg2", psycopg2)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)

    result = center.sync_facts_to_legacy_events("postgresql://fake")
    event_sql, _ = next(
        call for call in cursor.calls if "INSERT INTO business_tag_evidence_events" in call[0]
    )

    assert result == {"selected": 1, "synced": 1}
    _assert_manual_review_columns_are_untouched(event_sql)
