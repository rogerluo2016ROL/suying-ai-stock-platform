"""Contracts for scoped, local-first supply-chain evidence adapters."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import psycopg2

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
    assert "currently_offered" not in (by_title["negative"].metadata or {})
    assert "application_domain" not in (by_title["negative"].metadata or {})


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
