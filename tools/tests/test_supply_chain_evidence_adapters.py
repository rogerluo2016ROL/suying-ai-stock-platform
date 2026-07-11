"""Contracts for scoped, local-first supply-chain evidence adapters."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psycopg2
import pytest

import supply_chain_data_collection_center as center
from supply_chain_data_collection_center import RawDocument
from supply_chain_evidence_adapters import (
    AdapterResult,
    CollectionTask,
    OfficialDiscoveryAdapter,
    OfficialGapAdapter,
    ScopedOfficialFetcher,
    UnmappedDiscoveryTask,
    collect_local_then_official,
    current_support_status,
    persist_adapter_result,
    resolve_collection_window,
    sanitize_error,
)


AS_OF = date(2026, 7, 9)


def document(
    doc_id: str,
    *,
    code: str = "003021",
    text: str = "灵巧手产品",
    doc_type: str = "announcement",
    publish_time: str | None = "2026-07-01",
    metadata: dict | None = None,
) -> RawDocument:
    # RawDocument ids are content-derived, so make the requested id part of the text.
    return RawDocument(
        source_id="test-source",
        source_level="strong",
        title=doc_id,
        content_text=f"{doc_id} {text}",
        url=f"https://example.test/{doc_id}",
        company_code=code,
        company_name="测试公司",
        publish_time=publish_time,
        doc_type=doc_type,
        metadata=metadata,
    )


class FakeAdapter:
    def __init__(self, rows_by_task: dict[str, list[RawDocument]], *, requests: int = 0):
        self.rows_by_task = rows_by_task
        self.requests = requests
        self.calls: list[list[str]] = []

    def collect(self, tasks, *, as_of_date, source_limits=None):
        keys = [f"{task.mapping_id}:{task.requirement_id}" for task in tasks]
        self.calls.append(keys)
        rows = [item for key in keys for item in self.rows_by_task.get(key, [])]
        return AdapterResult(tuple(rows), (), (), "success" if rows else "empty", self.requests)


def collection_task(mapping_id: str = "m1") -> CollectionTask:
    return CollectionTask(
        mapping_id,
        "product_or_prototype",
        "003021",
        "兆威机电",
        ("灵巧手",),
        product_terms=("灵巧手",),
        scene_terms=("机器人手部",),
        negative_examples=("否认",),
    )


def test_raw_document_is_the_single_shared_schema():
    import supply_chain_evidence_adapters as adapters

    assert adapters.RawDocument is center.RawDocument


def test_local_hit_prevents_official_request():
    local_doc = document("local-1")
    local = FakeAdapter({"m1:product_or_prototype": [local_doc]})
    official = FakeAdapter({"m1:product_or_prototype": [document("web-1")]})

    result = collect_local_then_official(
        [collection_task()], local=local, official=official, as_of_date=AS_OF
    )

    assert result.documents == (local_doc,)
    assert official.calls == []


def test_only_local_misses_are_sent_to_official_and_requests_are_counted():
    task_1 = collection_task("m1")
    task_2 = collection_task("m2")
    local = FakeAdapter({"m1:product_or_prototype": [document("local-1")]})
    official = FakeAdapter(
        {"m2:product_or_prototype": [document("web-2")]}, requests=3
    )

    result = collect_local_then_official(
        [task_1, task_2],
        local=local,
        official=official,
        as_of_date=AS_OF,
        source_limits={"mapped_official_tasks": 1},
    )

    assert [item.title for item in result.documents] == ["local-1", "web-2"]
    assert official.calls == [["m2:product_or_prototype"]]
    assert result.network_requests == 3


def test_mapped_official_adapter_honors_limits_and_counts_requests():
    class Fetcher:
        def __init__(self):
            self.calls = []

        def fetch(self, task, **kwargs):
            self.calls.append((task.mapping_id, kwargs))
            return [document(f"web-{task.mapping_id}")], 3

    fetcher = Fetcher()
    adapter = OfficialGapAdapter(fetcher)
    result = adapter.collect(
        [collection_task("m1"), collection_task("m2")],
        as_of_date=AS_OF,
        source_limits={
            "mapped_official_tasks": 1,
            "mapped_cninfo_documents_per_task": 2,
            "official_pages_per_company": 1,
        },
    )

    assert result.network_requests == 3
    assert result.status == "partial_success"
    assert "source_limit_skipped_tasks:1" in result.errors
    assert fetcher.calls[0][1]["document_limit"] == 2
    assert fetcher.calls[0][1]["pages_per_company"] == 1


def test_official_discovery_can_find_company_before_mapping_exists():
    class Fetcher:
        def fetch_unmapped(self, task, **kwargs):
            assert kwargs["document_limit"] == 50
            return [document("official-axis-1", code="688001")], 1

    task = UnmappedDiscoveryTask(
        chain_id="dexterous_hand",
        requirement_id="dexterous_axial_flux_motor",
        product_terms=("轴向磁通电机",),
        scene_terms=("机器人腕部",),
        negative_examples=("轮毂",),
        require_product_and_scene=True,
    )
    result = OfficialDiscoveryAdapter(Fetcher()).collect(
        [task],
        as_of_date=AS_OF,
        source_limits={"official_discovery_documents": 50},
    )

    assert result.documents[0].company_code == "688001"
    assert result.network_requests == 1


def test_source_windows_keep_active_patent_and_current_product_but_drop_old_event():
    assert resolve_collection_window("announcement", AS_OF) == (
        date(2023, 1, 1),
        AS_OF,
    )
    assert resolve_collection_window("official_product_page", AS_OF) == (None, AS_OF)
    assert resolve_collection_window("patent", AS_OF) == (None, AS_OF)
    patent = document(
        "patent-2018",
        doc_type="patent",
        publish_time="2018-01-01",
        metadata={"legal_status": "active", "legal_status_date": "2026-06-30"},
    )
    product = document(
        "product-2019",
        doc_type="official_product_page",
        publish_time="2019-01-01",
        metadata={"currently_offered": True, "verified_current_date": "2026-07-09"},
    )
    old = document("old", publish_time="2019-01-01")

    assert current_support_status(patent, AS_OF) == "current"
    assert current_support_status(product, AS_OF) == "current"
    assert current_support_status(old, AS_OF) == "historical_only"


def test_sanitize_error_redacts_database_dsn_and_secret_keys():
    value = sanitize_error(
        RuntimeError(
            "postgresql://alice:dbpass@localhost/db password=hunter2 "
            "client_secret=abc Authorization: Bearer topsecret"
        )
    )

    for secret in ("dbpass", "hunter2", "client_secret=abc", "topsecret"):
        assert secret not in value
    assert len(value) <= 540


def test_scoped_official_fetcher_only_marks_same_page_product_and_scene_without_negative():
    good = document(
        "good",
        text="灵巧手驱动器用于机器人手部",
        doc_type="official_product_page",
        publish_time=None,
        metadata={"revenue_confirmed": True, "profit_confirmed": True},
    )
    negative = document(
        "negative",
        text="灵巧手驱动器用于机器人手部，但公司否认供货",
        doc_type="official_product_page",
        publish_time=None,
    )

    fetcher = ScopedOfficialFetcher(
        cninfo_fetch=lambda **kwargs: ([], 1),
        ir_fetch=lambda **kwargs: ([good, negative], 2),
    )
    rows, request_count = fetcher.fetch(
        collection_task(), as_of_date=AS_OF, document_limit=10, pages_per_company=2
    )

    by_title = {row.title: row for row in rows}
    assert request_count == 3
    assert by_title["good"].metadata["currently_offered"] is True
    assert by_title["good"].metadata["verified_current_date"] == "2026-07-09"
    assert by_title["good"].metadata["application_domain"] == ["机器人手部"]
    assert by_title["good"].metadata["installation_position"] == ["机器人手部"]
    assert "revenue_confirmed" not in by_title["good"].metadata
    assert "profit_confirmed" not in by_title["good"].metadata
    assert "negative" not in by_title


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, rows):
        self.cursor_value = FakeCursor(rows)
        self.commit_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return self.cursor_value

    def commit(self):
        self.commit_calls += 1


class FakeResponse:
    def __init__(self, *, payload=None, content=b"", text="", url="https://example.test"):
        self._payload = payload or {}
        self.content = content
        self.text = text
        self.url = url
        self.status_code = 200
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def json(self):
        return self._payload


def test_document_only_ir_helper_has_no_persistence_side_effect(monkeypatch):
    connection = FakeConnection(
        [{"code": "003021", "company_name": "兆威机电", "website": "example.test"}]
    )
    monkeypatch.setattr(psycopg2, "connect", lambda *_args, **_kwargs: connection)

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def get(self, url, **_kwargs):
            self.calls.append(url)
            if len(self.calls) == 1:
                return FakeResponse(
                    text='<title>官网</title><a href="/product">产品中心</a>' + "首页" * 50,
                    url="http://example.test",
                )
            return FakeResponse(
                text="<title>灵巧手</title>" + "灵巧手机器人手部驱动器" * 20,
                url=url,
            )

    session = Session()
    rows, request_count = center.fetch_official_ir_documents(
        "postgresql://unused",
        company_codes=("003021",),
        start_date=None,
        as_of_date=AS_OF,
        limit=2,
        pages_per_company=2,
        session=session,
    )

    sql = " ".join(call[0] for call in connection.cursor_value.calls).upper()
    assert len(rows) == 2
    assert request_count == 2
    assert all(word not in sql for word in ("INSERT ", "UPDATE ", "DELETE "))
    assert connection.commit_calls == 0


def test_global_cninfo_uses_product_scene_queries_dedupes_and_applies_cutoff(monkeypatch):
    monkeypatch.setattr(
        center, "_extract_pdf_text", lambda _content: "机器人腕部轴向磁通电机 额定扭矩2Nm"
    )

    current = {
        "announcementId": "a1",
        "announcementTitle": "轴向磁通电机产品公告",
        "adjunctUrl": "finalpage/a1.pdf",
        "secCode": "688001",
        "secName": "测试公司",
        "announcementTime": "2026-07-01",
    }
    old = {**current, "announcementId": "old", "announcementTime": "2022-12-31"}

    class Session:
        def __init__(self):
            self.headers = {}
            self.posts = []
            self.gets = []

        def post(self, url, **kwargs):
            self.posts.append((url, kwargs))
            return FakeResponse(payload={"announcements": [current, old]})

        def get(self, url, **kwargs):
            self.gets.append((url, kwargs))
            return FakeResponse(content=b"%PDF-recorded")

    session = Session()
    rows, request_count = center.fetch_cninfo_keyword_documents(
        product_terms=("轴向磁通", "轴向磁通电机"),
        scene_terms=("机器人腕部",),
        require_product_and_scene=True,
        allowed_company_codes=("688001",),
        as_of_date=AS_OF,
        limit=10,
        session=session,
    )

    submitted = [str(kwargs) for _, kwargs in session.posts]
    assert len(rows) == 1
    assert rows[0].company_code == "688001"
    assert request_count == 3  # two searches plus one deduplicated PDF download
    assert len(session.gets) == 1
    assert all("机器人腕部" in value for value in submitted)
    assert any("轴向磁通" in value for value in submitted)
    assert any("轴向磁通电机" in value for value in submitted)


def test_persist_adapter_result_routes_current_pending_and_history_without_guessing_mapping():
    current = document("current")
    pending = document(
        "pending",
        doc_type="official_product_page",
        publish_time=None,
        metadata={},
    )
    historical = document("historical", publish_time="2019-01-01")

    class Repository:
        def __init__(self):
            self.pending = []
            self.raw = []

        def persist_pending_document(self, **kwargs):
            self.pending.append(kwargs)
            return kwargs

        def persist_raw_document(self, document, *, job_id):
            self.raw.append((document, job_id))
            return document.doc_id

    repository = Repository()
    outcomes = persist_adapter_result(
        AdapterResult((current, pending, historical), (), (), "success"),
        repository=repository,
        task=collection_task("m-explicit"),
        job_id="j1",
        as_of_date=AS_OF,
    )

    assert len(outcomes) == 3
    assert [row["mapping_id"] for row in repository.pending] == [
        "m-explicit",
        "m-explicit",
    ]
    assert [row["requirement_id"] for row in repository.pending] == [
        "product_or_prototype",
        "product_or_prototype",
    ]
    assert repository.pending[0]["document"].metadata["current_support_status"] == "current"
    assert repository.pending[1]["document"].metadata["current_support_status"] == "pending_review"
    assert repository.raw[0][0].metadata["current_support_status"] == "historical_only"


def test_legacy_official_commands_delegate_to_document_only_helpers(monkeypatch):
    connections = []

    def connection_factory(*_args, **_kwargs):
        connection = FakeConnection([{"code": "003021"}])
        connections.append(connection)
        return connection

    monkeypatch.setattr(psycopg2, "connect", connection_factory)
    persisted = []
    monkeypatch.setattr(
        center,
        "_insert_raw_document_and_fact",
        lambda cur, doc, source, job_id: persisted.append((doc, source, job_id))
        or {"inserted_doc": True, "inserted_fact": True, "duplicate": False},
    )
    cninfo_calls = []
    ir_calls = []
    cninfo_doc = document(
        "关于签订重大合同的公告",
        text="签订重大合同",
        doc_type="announcement_pdf",
    )
    ir_doc = document(
        "ir-wrapper",
        text="灵巧手机器人手部产品页",
        doc_type="official_product_page",
        publish_time=None,
    )

    def fake_cninfo(*args, **kwargs):
        cninfo_calls.append((args, kwargs))
        return [cninfo_doc], 2

    def fake_ir(*args, **kwargs):
        ir_calls.append((args, kwargs))
        return [ir_doc], 1

    monkeypatch.setattr(center, "fetch_cninfo_documents", fake_cninfo)
    monkeypatch.setattr(center, "fetch_official_ir_documents", fake_ir)

    cninfo_result = center.fetch_cninfo_pdf_announcements(
        "postgresql://unused", limit=1, title_mode="relevant"
    )
    ir_result = center.fetch_official_ir_pages(
        "postgresql://unused", limit=1, pages_per_company=1
    )

    assert cninfo_calls and cninfo_calls[0][1]["company_codes"] == ("003021",)
    assert ir_calls and ir_calls[0][1]["company_codes"] == ("003021",)
    assert cninfo_result["fetched"] == 1
    assert ir_result["fetched_pages"] == 1
    assert [row[0].title for row in persisted] == ["关于签订重大合同的公告", "ir-wrapper"]


class CountedFetchError(RuntimeError):
    def __init__(self, message, *, request_count, documents=()):
        super().__init__(message)
        self.request_count = request_count
        self.documents = tuple(documents)


def test_helper_http_failure_raises_safe_counted_error_instead_of_empty(monkeypatch):
    connection = FakeConnection(
        [
            {
                "code": "003021",
                "company_name": "兆威机电",
                "ann_date": "20260701",
                "publish_date": date(2026, 7, 1),
                "title": "重大合同公告",
                "url": "https://example.test?announcementId=1",
                "ts_code": "003021.SZ",
            }
        ]
    )
    monkeypatch.setattr(psycopg2, "connect", lambda *_args, **_kwargs: connection)

    class Session:
        headers = {}

        def post(self, *_args, **_kwargs):
            response = FakeResponse()
            response.status_code = 503
            return response

    with pytest.raises(Exception) as caught:
        center.fetch_cninfo_documents(
            "postgresql://unused",
            company_codes=("003021",),
            start_date=date(2023, 1, 1),
            as_of_date=AS_OF,
            limit=1,
            session=Session(),
        )

    assert getattr(caught.value, "request_count", None) == 1
    assert "503" in str(caught.value)


def test_global_cninfo_json_and_pdf_failures_preserve_request_count(monkeypatch):
    class JsonFailureSession:
        headers = {}

        def post(self, *_args, **_kwargs):
            class Response(FakeResponse):
                def json(self):
                    raise ValueError('bad json token="secret-json"')

            return Response()

    with pytest.raises(Exception) as json_error:
        center.fetch_cninfo_keyword_documents(
            product_terms=("轴向磁通",),
            scene_terms=("机器人腕部",),
            require_product_and_scene=True,
            allowed_company_codes=(),
            as_of_date=AS_OF,
            limit=1,
            session=JsonFailureSession(),
        )
    assert getattr(json_error.value, "request_count", None) == 1
    assert "secret-json" not in str(json_error.value)

    candidate = {
        "announcementId": "a1",
        "announcementTitle": "轴向磁通电机",
        "adjunctUrl": "a1.pdf",
        "secCode": "688001",
        "announcementTime": "2026-07-01",
    }

    class PdfFailureSession:
        headers = {}

        def post(self, *_args, **_kwargs):
            return FakeResponse(payload={"announcements": [candidate]})

        def get(self, *_args, **_kwargs):
            raise RuntimeError("download password='pdf secret'")

    with pytest.raises(Exception) as pdf_error:
        center.fetch_cninfo_keyword_documents(
            product_terms=("轴向磁通",),
            scene_terms=("机器人腕部",),
            require_product_and_scene=True,
            allowed_company_codes=(),
            as_of_date=AS_OF,
            limit=1,
            session=PdfFailureSession(),
        )
    assert getattr(pdf_error.value, "request_count", None) == 2
    assert "pdf secret" not in str(pdf_error.value)


def test_adapter_converts_counted_fetch_failure_to_partial_with_documents_and_count():
    partial = document("partial-official")

    class Fetcher:
        def fetch(self, *_args, **_kwargs):
            raise CountedFetchError(
                "headers={'Authorization': 'Bearer hidden-token'}",
                request_count=2,
                documents=(partial,),
            )

    result = OfficialGapAdapter(Fetcher()).collect(
        [collection_task()], as_of_date=AS_OF, source_limits={}
    )

    assert result.status == "partial_success"
    assert result.documents == (partial,)
    assert result.failed_tasks == ("m1:product_or_prototype",)
    assert result.network_requests == 2
    assert "hidden-token" not in " ".join(result.errors)


def test_event_dates_use_shanghai_day_and_enforce_both_window_bounds():
    utc_future_in_shanghai = document(
        "utc-future",
        publish_time=datetime(2026, 7, 9, 16, 30, tzinfo=timezone.utc),
    )
    naive_shanghai_same_day = document(
        "naive-same-day", publish_time=datetime(2026, 7, 9, 23, 59)
    )
    before_window = document("before-window", publish_time="2022-12-31")

    assert current_support_status(utc_future_in_shanghai, AS_OF) == "historical_only"
    assert current_support_status(naive_shanghai_same_day, AS_OF) == "current"
    assert current_support_status(before_window, AS_OF) == "historical_only"


def test_scoped_mapped_limit_only_caps_cninfo_not_ir_documents():
    cninfo = [
        document("cn-1", text="灵巧手用于机器人手部"),
        document("cn-2", text="灵巧手用于机器人手部"),
    ]
    ir = [
        document(
            f"ir-{index}",
            text="灵巧手用于机器人手部",
            doc_type="official_product_page",
            publish_time=None,
        )
        for index in range(3)
    ]
    fetcher = ScopedOfficialFetcher(
        cninfo_fetch=lambda **_kwargs: (cninfo, 1),
        ir_fetch=lambda **_kwargs: (ir, 3),
    )

    rows, request_count = fetcher.fetch(
        collection_task(), as_of_date=AS_OF, document_limit=1, pages_per_company=3
    )

    assert [row.title for row in rows] == ["cn-1", "ir-0", "ir-1", "ir-2"]
    assert request_count == 4


def test_discovery_limits_cninfo_documents_seed_companies_and_ir_pages_separately():
    from supply_chain_evidence_adapters import ScopedOfficialDiscoveryFetcher

    calls = {}

    def global_fetch(**kwargs):
        calls["global"] = kwargs
        return [
            document("cn-a", code="688001", text="轴向磁通用于机器人腕部"),
            document("cn-b", code="688002", text="轴向磁通用于机器人腕部"),
        ], 2

    def ir_fetch(**kwargs):
        calls["ir"] = kwargs
        return [
            document("ir-seed", code="688001", text="轴向磁通用于机器人腕部")
        ], 1

    task = UnmappedDiscoveryTask(
        chain_id="dexterous_hand",
        requirement_id="dexterous_axial_flux_motor",
        product_terms=("轴向磁通",),
        scene_terms=("机器人腕部",),
        negative_examples=(),
        require_product_and_scene=True,
        seed_company_codes=("688001", "688002"),
    )
    rows, _ = ScopedOfficialDiscoveryFetcher(
        global_cninfo_fetch=global_fetch, ir_fetch=ir_fetch
    ).fetch_unmapped(
        task,
        as_of_date=AS_OF,
        document_limit=1,
        company_limit=1,
        pages_per_company=2,
    )

    assert calls["global"]["limit"] == 1
    assert calls["ir"]["company_codes"] == ("688001",)
    assert calls["ir"]["pages_per_company"] == 2
    assert [row.title for row in rows] == ["cn-a", "ir-seed"]


def test_global_cninfo_limit_counts_deduplicated_download_attempts(monkeypatch):
    monkeypatch.setattr(
        center, "_extract_pdf_text", lambda _content: "轴向磁通机器人腕部"
    )
    candidates = [
        {
            "announcementId": value,
            "announcementTitle": value,
            "adjunctUrl": f"{value}.pdf",
            "secCode": "688001",
            "announcementTime": "2026-07-01",
        }
        for value in ("a1", "a2", "a3")
    ]

    class Session:
        def __init__(self):
            self.headers = {}
            self.gets = []

        def post(self, *_args, **_kwargs):
            return FakeResponse(payload={"announcements": candidates})

        def get(self, url, **_kwargs):
            self.gets.append(url)
            return FakeResponse(content=b"%PDF-ok")

    session = Session()
    rows, _ = center.fetch_cninfo_keyword_documents(
        product_terms=("轴向磁通",),
        scene_terms=("机器人腕部",),
        require_product_and_scene=True,
        allowed_company_codes=(),
        as_of_date=AS_OF,
        limit=1,
        session=session,
    )

    assert len(session.gets) == 1
    assert rows[0].metadata["source_limit_skipped_documents"] == 2


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ('{"client_secret": "abc def"}', "abc def"),
        ("{'Authorization': 'Bearer header-token'}", "header-token"),
        ("https://example.test/path?token=query-token&x=1", "query-token"),
        ("password='quoted secret value'", "quoted secret value"),
        ("postgresql://alice:dsn-pass@localhost/db", "dsn-pass"),
        ("Cookie: session cookie value", "session cookie value"),
    ],
)
def test_sanitize_error_handles_structured_and_quoted_secrets(raw, secret):
    assert secret not in sanitize_error(RuntimeError(raw))


def test_patent_current_status_requires_official_active_status_and_check_date():
    granted_claim = document(
        "claim",
        doc_type="patent",
        metadata={
            "legal_status": "granted_or_obtained",
            "legal_status_date": "2026-07-01",
        },
    )
    active_without_check = document(
        "no-check", doc_type="patent", metadata={"legal_status": "active"}
    )
    active_verified = document(
        "verified",
        doc_type="patent",
        metadata={"legal_status": "active", "legal_status_date": "2026-07-01"},
    )

    assert current_support_status(granted_claim, AS_OF) == "pending_review"
    assert current_support_status(active_without_check, AS_OF) == "pending_review"
    assert current_support_status(active_verified, AS_OF) == "current"


def test_legacy_cninfo_filters_title_before_final_limit_and_uses_shanghai_today(monkeypatch):
    monkeypatch.setattr(center, "shanghai_today", lambda: AS_OF)
    monkeypatch.setattr(
        psycopg2,
        "connect",
        lambda *_args, **_kwargs: FakeConnection([{"code": "003021"}]),
    )
    monkeypatch.setattr(
        center,
        "_insert_raw_document_and_fact",
        lambda *_args, **_kwargs: {
            "inserted_doc": True,
            "inserted_fact": True,
            "duplicate": False,
        },
    )
    calls = []

    def helper(*_args, **kwargs):
        calls.append(kwargs)
        stats = kwargs["stats"]
        stats.selected = 2
        stats.fetched = 1
        stats.skipped = 1
        stats.failed = 0
        return [
            document("关于签订重大合同的公告", doc_type="announcement_pdf"),
        ], 4

    monkeypatch.setattr(center, "fetch_cninfo_documents", helper)
    result = center.fetch_cninfo_pdf_announcements(
        "postgresql://unused", limit=1, title_mode="relevant"
    )

    assert calls[0]["as_of_date"] == AS_OF
    assert calls[0]["limit"] == 1
    assert calls[0]["title_predicate"]("关于签订重大合同的公告") is True
    assert calls[0]["title_predicate"]("股东大会法律意见书") is False
    assert result["selected"] == 2
    assert result["fetched"] == 1
    assert result["skipped"] == 1
    assert result["failed"] == 0


def test_legacy_ir_limit_is_company_count_and_pages_are_per_company(monkeypatch):
    monkeypatch.setattr(center, "shanghai_today", lambda: AS_OF)
    monkeypatch.setattr(
        psycopg2,
        "connect",
        lambda *_args, **_kwargs: FakeConnection(
            [{"code": "003021"}, {"code": "688001"}]
        ),
    )
    monkeypatch.setattr(
        center,
        "_insert_raw_document_and_fact",
        lambda *_args, **_kwargs: {
            "inserted_doc": True,
            "inserted_fact": True,
            "duplicate": False,
        },
    )
    calls = []

    def helper(*_args, **kwargs):
        calls.append(kwargs)
        return [
            document(
                f"ir-{index}", doc_type="official_product_page", publish_time=None
            )
            for index in range(4)
        ], 4

    monkeypatch.setattr(center, "fetch_official_ir_documents", helper)
    result = center.fetch_official_ir_pages(
        "postgresql://unused", limit=2, pages_per_company=2
    )

    assert calls[0]["company_codes"] == ("003021", "688001")
    assert calls[0]["limit"] == 4
    assert calls[0]["pages_per_company"] == 2
    assert result["selected_companies"] == 2
    assert result["fetched_pages"] == 4
    assert result["skipped"] == 0
    assert result["failed"] == 0


def test_mapped_official_sources_fail_independently_and_filter_partial_documents():
    calls = []
    partial_good = document(
        "cn-good", code="688001", text="轴向磁通电机用于机器人腕部",
        metadata={"revenue_confirmed": True},
    )
    partial_bad = document(
        "cn-bad", code="688001", text="轴向磁通电机用于机器人腕部，董事会换届",
        metadata={"revenue_confirmed": True},
    )
    ir_good = document(
        "ir-good", code="688001", text="轴向磁通电机用于机器人腕部",
        doc_type="official_product_page", publish_time=None,
    )

    def cninfo_fetch(**_kwargs):
        calls.append("cninfo")
        raise center.DocumentFetchError(
            "cninfo failed", request_count=2,
            documents=(partial_good, partial_bad),
        )

    def ir_fetch(**_kwargs):
        calls.append("ir")
        return [ir_good], 1

    task = CollectionTask(
        mapping_id="m-independent", requirement_id="r-independent",
        company_code="688001", company_name="测试公司",
        queries=("轴向磁通",), product_terms=("轴向磁通",),
        scene_terms=("机器人腕部",), negative_examples=("董事会换届",),
        require_product_and_scene=True,
    )
    result = OfficialGapAdapter(
        ScopedOfficialFetcher(cninfo_fetch=cninfo_fetch, ir_fetch=ir_fetch)
    ).collect([task], as_of_date=AS_OF, source_limits={})

    assert calls == ["cninfo", "ir"]
    assert result.status == "partial_success"
    assert result.network_requests == 3
    assert [item.title for item in result.documents] == ["cn-good", "ir-good"]
    assert "revenue_confirmed" not in result.documents[0].metadata
    assert result.documents[0].metadata["same_document_match"] is True


def test_discovery_sources_fail_independently_and_filter_partial_documents():
    from supply_chain_evidence_adapters import ScopedOfficialDiscoveryFetcher

    calls = []
    partial_good = document(
        "global-good", code="688001", text="轴向磁通电机用于机器人腕部",
        metadata={"profit_confirmed": True},
    )
    partial_bad = document(
        "global-bad", code="688001", text="轴向磁通电机用于机器人腕部，董事会换届",
    )
    ir_good = document(
        "global-ir", code="688001", text="轴向磁通电机用于机器人腕部",
        doc_type="official_product_page", publish_time=None,
    )

    def global_fetch(**_kwargs):
        calls.append("cninfo")
        raise center.DocumentFetchError(
            "global failed", request_count=2,
            documents=(partial_good, partial_bad),
        )

    def ir_fetch(**_kwargs):
        calls.append("ir")
        return [ir_good], 1

    task = UnmappedDiscoveryTask(
        chain_id="dexterous_hand", requirement_id="axial_flux",
        product_terms=("轴向磁通",), scene_terms=("机器人腕部",),
        negative_examples=("董事会换届",), require_product_and_scene=True,
        seed_company_codes=("688001",), allowed_company_codes=("688001",),
    )
    result = OfficialDiscoveryAdapter(
        ScopedOfficialDiscoveryFetcher(
            global_cninfo_fetch=global_fetch, ir_fetch=ir_fetch
        )
    ).collect([task], as_of_date=AS_OF, source_limits={})

    assert calls == ["cninfo", "ir"]
    assert result.status == "partial_success"
    assert result.network_requests == 3
    assert [item.title for item in result.documents] == ["global-good", "global-ir"]
    assert "profit_confirmed" not in result.documents[0].metadata


def test_legacy_ir_uses_actual_helper_stats_not_theoretical_page_capacity(monkeypatch):
    monkeypatch.setattr(center, "shanghai_today", lambda: AS_OF)
    monkeypatch.setattr(
        psycopg2,
        "connect",
        lambda *_args, **_kwargs: FakeConnection(
            [{"code": "003021"}, {"code": "688001"}]
        ),
    )
    monkeypatch.setattr(
        center,
        "_insert_raw_document_and_fact",
        lambda *_args, **_kwargs: {
            "inserted_doc": True,
            "inserted_fact": True,
            "duplicate": False,
        },
    )

    def helper(*_args, **kwargs):
        stats = kwargs["stats"]
        stats.selected = 2
        stats.fetched = 2
        stats.skipped = 0
        stats.failed = 0
        return [
            document("ir-a", doc_type="official_product_page", publish_time=None),
            document("ir-b", doc_type="official_product_page", publish_time=None),
        ], 2

    monkeypatch.setattr(center, "fetch_official_ir_documents", helper)
    result = center.fetch_official_ir_pages(
        "postgresql://unused", limit=2, pages_per_company=2
    )

    assert result["selected_companies"] == 2
    assert result["fetched_pages"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
