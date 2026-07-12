"""Contracts for the supply-chain evidence orchestration repository."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from app.domains.supply_chain.evidence_orchestration_repository import (
    EvidenceOrchestrationRepository,
)
from kronos_factors.engine.supply_chain_evidence_orchestration import (
    CandidateMappingProposal,
    DiscoveryHit,
    EvidenceGap,
    EvidenceRunRequest,
    NodeDimensionUpdate,
)
from supply_chain_evidence_adapters import AdapterResult
from supply_chain_data_collection_center import RawDocument


AS_OF = date(2026, 7, 9)


class FakeCursor:
    def __init__(
        self,
        *,
        mapping_row=None,
        mapping_rows=None,
        table_names=None,
        query_rows=None,
        fact_validation_status="pending",
        event_review_status="pending_review",
    ):
        self.mapping_row = mapping_row
        self.mapping_rows = list(mapping_rows or [])
        self.table_names = list(table_names or [])
        self.query_rows = dict(query_rows or {})
        self.calls: list[tuple[str, tuple]] = []
        self._one = None
        self._many = []
        self.rowcount = 1
        self.inserted_raw_doc_ids: set[str] = set()
        self.fact_validation_status = fact_validation_status
        self.event_review_status = event_review_status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, tuple(params or ())))
        self._one = None
        self._many = []
        if "information_schema.tables" in sql:
            self._many = [{"table_name": name} for name in self.table_names]
        elif (
            "INSERT INTO raw_evidence_documents" in sql
            and "RETURNING doc_id" in sql
        ):
            doc_id = str(params[0])
            if doc_id not in self.inserted_raw_doc_ids:
                self.inserted_raw_doc_ids.add(doc_id)
                self._one = {"doc_id": doc_id}
        elif (
            "INSERT INTO business_tag_evidence_events" in sql
            and "RETURNING review_status" in sql
        ):
            self._one = {"review_status": self.event_review_status}
        elif (
            "INSERT INTO evidence_extracted_facts" in sql
            and "RETURNING validation_status" in sql
        ):
            self._one = {"validation_status": self.fact_validation_status}
        elif "FOR UPDATE" in sql and "business_tag_mapping" in sql:
            self._one = self.mapping_row
        elif "FROM business_tag_mapping b" in sql:
            self._many = list(self.mapping_rows)
        else:
            for marker, rows in self.query_rows.items():
                if marker in sql:
                    self._many = list(rows)
                    self._one = self._many[0] if self._many else None
                    break

    def fetchone(self):
        return self._one

    def fetchall(self):
        return list(self._many)


class FakeConnection:
    def __init__(self, cursor=None):
        self.cursor_value = cursor or FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self, **_kwargs):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def document(doc_id="d1", *, metadata=None, doc_type="announcement"):
    return RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title=doc_id,
        content_text=f"{doc_id} 灵巧手驱动器用于机器人手部",
        url=f"https://example.test/{doc_id}",
        company_code="003021",
        company_name="兆威机电",
        publish_time="2026-07-01",
        doc_type=doc_type,
        metadata=metadata,
    )


def candidate_proposal(*, discovery_doc_ids=("d1",), discovery_fact_ids=()):
    return CandidateMappingProposal(
        mapping_id="candidate-stable",
        company_code="688001",
        chain_id="dexterous_hand",
        node_id="dexterous_hand_actuator",
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
        status="candidate",
        confidence=0.35,
        evidence_ids=(),
        provenance={
            "source": "independent_discovery",
            "requirement_id": "dexterous_axial_flux_motor",
            "technology_route_id": "dexterous_axial_flux_motor",
            "discovery_doc_ids": list(discovery_doc_ids),
            "discovery_fact_ids": list(discovery_fact_ids),
            "l1_l8_path": {
                "requirement_id": "dexterous_axial_flux_motor",
                "technology_route_id": "dexterous_axial_flux_motor",
                "discovery_doc_ids": list(discovery_doc_ids),
                "discovery_fact_ids": list(discovery_fact_ids),
            },
        },
    )


def discovery_hit(doc_id="d1"):
    return DiscoveryHit(
        doc_id=doc_id,
        company_code="688001",
        requirement_id="dexterous_axial_flux_motor",
        product_hits=("轴向磁通电机",),
        scene_hits=("机器人腕部",),
        excluded_hits=(),
        source_level="strong",
        publish_time=datetime(2026, 7, 1, 9, 0),
        eligible_for_mapping=True,
        validation_status="pending",
        proposal=candidate_proposal(discovery_doc_ids=(doc_id,)),
    )


def test_repository_uses_explicit_mapping_and_pending_status():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: connection)

    outcome = repository.persist_pending_document(
        document=document(),
        mapping_id="m-force",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=AS_OF,
    )

    assert outcome.mapping_id == "m-force"
    assert outcome.validation_status == "pending"
    assert outcome.review_status == "pending_review"
    assert outcome.event_id is not None
    assert outcome.inserted is True
    assert outcome.duplicate is False
    statements = [sql for sql, _ in cursor.calls]
    assert statements.index(next(sql for sql in statements if "raw_evidence_documents" in sql)) < statements.index(
        next(sql for sql in statements if "evidence_extracted_facts" in sql)
    )
    assert not any("SELECT" in sql and "business_tag_mapping" in sql for sql in statements)
    assert connection.commits == 1


def test_pending_persistence_strips_reserved_keys_and_round_trips_evidence_metadata():
    metadata = {
        "application_domain": ["机器人手部"],
        "installation_position": ["腕部"],
        "legal_status": "active",
        "legal_status_date": "2026-06-30",
        "review_normalization": {"risk_score": 100},
        "revenue_confirmed": True,
        "profit_confirmed": True,
    }
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(FakeCursor())
    )

    outcome = repository.persist_pending_document(
        document=document("patent", metadata=metadata, doc_type="patent"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=AS_OF,
    )

    assert outcome.fact_metadata == {
        "application_domain": ["机器人手部"],
        "installation_position": ["腕部"],
        "legal_status": "active",
        "legal_status_date": "2026-06-30",
    }


def test_pending_raw_document_conflict_returns_real_duplicate_outcome():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    first = repository.persist_pending_document(
        document=document("same"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=AS_OF,
    )
    second = repository.persist_pending_document(
        document=document("same"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j2",
        as_of_date=AS_OF,
    )

    assert (first.inserted, first.duplicate) == (True, False)
    assert (second.inserted, second.duplicate) == (False, True)
    raw_insert = next(
        sql for sql, _ in cursor.calls if "INSERT INTO raw_evidence_documents" in sql
    )
    assert "ON CONFLICT (doc_id) DO NOTHING" in raw_insert
    assert "RETURNING doc_id" in raw_insert
    conflict_update = next(
        sql for sql, _ in cursor.calls if "UPDATE raw_evidence_documents" in sql
    )
    assert "content_hash = %s" in conflict_update


def test_pending_rerun_returns_existing_reviewed_database_statuses():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    first = repository.persist_pending_document(
        document=document("reviewed-rerun"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=AS_OF,
    )
    cursor.fact_validation_status = "confirmed"
    cursor.event_review_status = "approved"

    second = repository.persist_pending_document(
        document=document("reviewed-rerun"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j2",
        as_of_date=AS_OF,
    )

    assert (first.validation_status, first.review_status) == (
        "pending",
        "pending_review",
    )
    assert (second.validation_status, second.review_status) == (
        "confirmed",
        "approved",
    )
    assert any(
        "RETURNING validation_status" in sql for sql, _ in cursor.calls
    )
    assert any("RETURNING review_status" in sql for sql, _ in cursor.calls)


def test_raw_document_identity_conflict_fails_closed():
    class IdentityConflictCursor(FakeCursor):
        def execute(self, statement, params=()):
            super().execute(statement, params)
            if "UPDATE raw_evidence_documents" in " ".join(
                str(statement).split()
            ):
                self.rowcount = 0

    cursor = IdentityConflictCursor()
    connection = FakeConnection(cursor)
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: connection
    )
    repository.persist_pending_document(
        document=document("same"),
        mapping_id="m1",
        requirement_id="product_or_prototype",
        job_id="j1",
        as_of_date=AS_OF,
    )

    with pytest.raises(RuntimeError, match="raw document identity conflict"):
        repository.persist_pending_document(
            document=document("same"),
            mapping_id="m1",
            requirement_id="product_or_prototype",
            job_id="j2",
            as_of_date=AS_OF,
        )

    assert connection.commits == 1
    assert connection.rollbacks == 1


def test_repository_persists_unmapped_discovery_before_candidate_mapping():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: connection)

    first = repository.persist_discovery_hit(discovery_hit("d-axis-1"), job_id="j1")
    second = repository.persist_discovery_hit(discovery_hit("d-axis-1"), job_id="j1")

    assert first.fact_mapping_id is None
    assert first.validation_status == "pending"
    assert first.fact_id == second.fact_id
    assert first.proposal.mapping_id == "candidate-stable"
    assert (first.inserted, first.duplicate) == (True, False)
    assert (second.inserted, second.duplicate) == (False, True)
    statements = [sql for sql, _ in cursor.calls]
    raw_indexes = [i for i, sql in enumerate(statements) if "raw_evidence_documents" in sql]
    fact_indexes = [i for i, sql in enumerate(statements) if "evidence_extracted_facts" in sql]
    assert raw_indexes[0] < fact_indexes[0]
    assert not any("business_tag_evidence_events" in sql for sql in statements)
    fact_params = next(params for sql, params in cursor.calls if "evidence_extracted_facts" in sql)
    assert None in fact_params  # explicit unmapped mapping_id


def test_discovery_rerun_never_downgrades_reviewed_mapping_or_clears_evidence():
    existing = {
        "mapping_id": "candidate-stable",
        "code": "688001",
        "business_segment_id": "reviewed-segment",
        "node_id": "reviewed-node",
        "theme_id": "reviewed-theme",
        "chain_id": "dexterous_hand",
        "tag_name": "已审核标签",
        "l1_l8_path": {
            "requirement_id": "dexterous_axial_flux_motor",
            "technology_route_id": "dexterous_axial_flux_motor",
            "discovery_doc_ids": ["d1"],
            "discovery_fact_ids": ["f1"],
        },
        "confidence": 0.9,
        "status": "verified",
        "evidence_ids": ["approved-e1"],
    }
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(FakeCursor(mapping_row=existing))
    )

    result = repository.upsert_candidate_mapping(
        candidate_proposal(discovery_doc_ids=("d2",), discovery_fact_ids=("f2",))
    )

    assert result.status == "verified"
    assert result.confidence == 0.9
    assert result.evidence_ids == ("approved-e1",)
    assert result.node_id == "reviewed-node"
    assert result.tag_name == "已审核标签"
    assert result.provenance["discovery_doc_ids"] == ["d1", "d2"]
    assert result.provenance["discovery_fact_ids"] == ["f1", "f2"]


def test_deep_frozen_provenance_is_thawed_for_json_and_route_round_trip():
    proposal = candidate_proposal()
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    written = repository.upsert_candidate_mapping(proposal)
    mapping_insert = next(
        params for sql, params in cursor.calls if "INSERT INTO business_tag_mapping" in sql
    )
    encoded_values = [value for value in mapping_insert if isinstance(value, str) and value.startswith("{")]
    assert encoded_values
    assert json.loads(encoded_values[0])["technology_route_id"] == "dexterous_axial_flux_motor"

    round_trip_cursor = FakeCursor(
        mapping_rows=[
            {
                "mapping_id": written.mapping_id,
                "code": written.company_code,
                "business_segment_id": written.business_segment_id,
                "node_id": written.node_id,
                "theme_id": written.theme_id,
                "chain_id": written.chain_id,
                "tag_name": written.tag_name,
                "l1_l8_path": written.provenance,
                "confidence": written.confidence,
                "status": written.status,
                "evidence_ids": list(written.evidence_ids),
            }
        ]
    )
    round_trip_repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(round_trip_cursor)
    )
    rows = round_trip_repository.fetch_mappings(
        "dexterous_hand", (written.mapping_id,), ()
    )

    assert rows[0]["requirement_id"] == "dexterous_axial_flux_motor"
    assert rows[0]["technology_route_id"] == "dexterous_axial_flux_motor"


def test_start_job_serializes_deep_frozen_limits_without_calling_upserts():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    request = EvidenceRunRequest(
        chain_id="dexterous_hand",
        as_of_date=AS_OF,
        mode="dry-run",
        source_policy="local-first",
        source_limits={"mapped_official_tasks": 2},
    )

    job_id = repository.start_job(request)

    assert job_id.startswith("JOB-")
    assert any("evidence_collection_jobs" in sql for sql, _ in cursor.calls)
    assert not any("upsert" in sql.casefold() for sql, _ in cursor.calls)
    assert not any("business_tag_mapping" in sql for sql, _ in cursor.calls)


def test_remaining_repository_queries_and_upserts_are_scoped_and_serializable():
    fact_metadata = {
        "candidate_proposal": {
            "mapping_id": "candidate-stable",
            "company_code": "688001",
            "chain_id": "dexterous_hand",
            "node_id": "dexterous_hand_actuator",
            "tag_name": "轴向磁通电机",
            "technology_route_id": "dexterous_axial_flux_motor",
            "status": "candidate",
            "confidence": 0.35,
            "evidence_ids": [],
            "provenance": candidate_proposal().provenance,
        }
    }
    cursor = FakeCursor(
        query_rows={
            "FROM raw_evidence_documents": [
                {
                    "doc_id": "raw-1",
                    "company_code": "688001",
                    "source_level": "strong",
                    "title": "轴向磁通电机",
                    "content_text": "机器人腕部轴向磁通电机",
                    "publish_time": datetime(2026, 7, 1),
                    "metadata": {},
                },
            ],
            "FROM stock_profiles": [{"code": "688001"}],
            "candidate_proposal": [{"metadata": fact_metadata}],
            "FROM evidence_extracted_facts f": [
                {
                    "fact_id": "f1",
                    "mapping_id": "m1",
                    "metadata": {"application_domain": ["机器人腕部"]},
                }
            ],
        }
    )
    connection = FakeConnection(cursor)
    repository = EvidenceOrchestrationRepository(connection_factory=lambda: connection)
    requirement = {
        "requirement_id": "dexterous_axial_flux_motor",
        "product_terms": ["轴向磁通电机"],
        "scene_terms": ["机器人腕部"],
        "negative_examples": ["轮毂"],
        "require_product_and_scene": True,
    }

    universe = repository.fetch_candidate_universe(AS_OF, requirement, (), 10)
    seeds = repository.fetch_discovery_seed_companies(AS_OF, requirement, 5)
    proposals = repository.list_candidate_proposals("j1")
    facts = repository.fetch_asof_facts(("m1",), datetime(2026, 7, 9, 15, 0))
    node_count = repository.upsert_node_dimension_updates(
        (
            NodeDimensionUpdate(
                node_id="dexterous_hand_actuator",
                dimension_id="technology_route",
                as_of_date=AS_OF,
                status="known",
                score=80.0,
                evidence_ids=("f1",),
            ),
        ),
        AS_OF,
    )

    assert universe[0]["doc_id"] == "raw-1"
    assert seeds == ["688001"]
    assert proposals[0].mapping_id == "candidate-stable"
    assert facts[0]["metadata"] == {"application_domain": ["机器人腕部"]}
    assert node_count == 1
    assert any("publish_time < %s" in sql for sql, _ in cursor.calls)
    assert any("INSERT INTO supply_chain_node_dimensions" in sql for sql, _ in cursor.calls)


def test_gap_round_trip_and_finish_job_sanitize_errors():
    cursor = FakeCursor(
        mapping_rows=[
            {
                "mapping_id": "m1",
                "l1_l8_path": {
                    "evidence_gaps": [
                        {
                            "mapping_id": "m1",
                            "requirement_id": "product_or_prototype",
                            "status": "missing",
                            "evidence_ids": [],
                            "next_action": "补证",
                            "reasons": ["缺失"],
                        }
                    ]
                },
            }
        ]
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    gap = EvidenceGap(
        mapping_id="m1",
        requirement_id="product_or_prototype",
        status="missing",
        evidence_ids=(),
        next_action="补证",
        reasons=("缺失",),
    )

    assert repository.upsert_gap_rows((gap,), AS_OF) == 1
    fetched = repository.fetch_gap_rows(("m1",))
    repository.finish_job(
        "j1",
        AdapterResult(
            (),
            ("m1:product",),
            ("postgresql://alice:dbpass@localhost/db password=hunter2",),
            "partial_success",
        ),
    )

    assert fetched == [gap]
    finish_params = next(
        params for sql, params in cursor.calls if "UPDATE evidence_collection_jobs" in sql
    )
    joined = " ".join(str(value) for value in finish_params)
    assert "dbpass" not in joined
    assert "hunter2" not in joined


def test_finish_job_keeps_fetched_inserted_and_duplicate_counts_separate():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    repository.finish_job(
        "j-counts",
        {
            "status": "success",
            "documents": (document("one"), document("two")),
            "failed_tasks": (),
            "errors": (),
            "fetched_count": 2,
            "inserted_count": 1,
            "duplicate_count": 1,
        },
    )
    params = next(
        params
        for sql, params in cursor.calls
        if "UPDATE evidence_collection_jobs" in sql
    )

    assert "duplicate_count = %s" in next(
        sql for sql, _ in cursor.calls if "UPDATE evidence_collection_jobs" in sql
    )
    assert params[:5] == ("success", 2, 1, 1, 0)


def test_finish_job_unknown_insert_and_duplicate_counts_default_to_zero():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    repository.finish_job(
        "j-unknown",
        AdapterResult((document("one"),), (), (), "success"),
    )
    params = next(
        params
        for sql, params in cursor.calls
        if "UPDATE evidence_collection_jobs" in sql
    )

    assert params[:5] == ("success", 1, 0, 0, 0)


def test_local_documents_report_missing_sources_and_apply_event_cutoff():
    cursor = FakeCursor(
        table_names=["raw_evidence_documents", "interact_qa"],
        query_rows={
            "FROM raw_evidence_documents": [
                {
                    "doc_id": "local-raw",
                    "source_id": "cninfo_announcement",
                    "source_level": "strong",
                    "title": "灵巧手产品",
                    "content_text": "灵巧手机器人手部",
                    "url": "https://example.test/raw",
                    "company_code": "003021",
                    "company_name": "兆威机电",
                    "publish_time": datetime(2026, 7, 1),
                    "doc_type": "announcement",
                    "metadata": {},
                },
                {
                    "doc_id": "local-undated",
                    "source_id": "cninfo_announcement",
                    "source_level": "strong",
                    "title": "灵巧手未知日期公告",
                    "content_text": "灵巧手机器人手部",
                    "url": "https://example.test/undated",
                    "company_code": "003021",
                    "company_name": "兆威机电",
                    "publish_time": None,
                    "doc_type": "announcement",
                    "metadata": {},
                },
            ],
            "FROM interact_qa": [
                {
                    "id": 1,
                    "code": "003021",
                    "pub_date": date(2019, 1, 1),
                    "pub_time": datetime(2019, 1, 1),
                    "question": "是否供应灵巧手",
                    "answer": "是",
                    "source": "szse",
                }
            ],
        },
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    rows, errors = repository.fetch_local_documents(
        type(
            "Task",
            (),
            {
                "mapping_id": "m1",
                "requirement_id": "product_or_prototype",
                "company_code": "003021",
                "queries": ("灵巧手",),
            },
        )(),
        AS_OF,
    )

    assert [row.title for row in rows] == ["灵巧手产品", "灵巧手未知日期公告"]
    assert "missing_local_source:stock_profiles" in errors
    assert "missing_local_source:patent_events" in errors


def test_independent_discovery_requirements_are_chain_scoped():
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: (_ for _ in ()).throw(AssertionError("no db"))
    )

    rows = repository.fetch_independent_discovery_requirements("dexterous_hand")

    assert [row["requirement_id"] for row in rows] == [
        "dexterous_axial_flux_motor"
    ]


def test_local_adapter_queries_every_available_supported_source():
    tables = [
        "raw_evidence_documents",
        "stock_profiles",
        "fina_mainbz",
        "announcements",
        "ts_raw_anns_d",
        "interact_qa",
        "research_reports_tushare",
        "patent_events",
    ]
    cursor = FakeCursor(table_names=tables)
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    task = type(
        "Task",
        (),
        {
            "company_code": "003021",
            "queries": ("灵巧手",),
        },
    )()

    rows, errors = repository.fetch_local_documents(task, AS_OF)

    sql = " ".join(statement for statement, _ in cursor.calls)
    assert rows == []
    assert errors == ()
    for table in tables:
        assert f"FROM {table}" in sql


def test_local_sources_have_explicit_catalog_mapping_and_fk_is_ensured_before_raw():
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(FakeCursor())
    )
    assert repository.LOCAL_SOURCE_BY_TABLE == {
        "announcements": "cninfo_announcement",
        "ts_raw_anns_d": "cninfo_announcement",
        "interact_qa": "exchange_interact_qa",
        "research_reports_tushare": "broker_expectation_local",
        "patent_events": "patent_public_platform",
        "stock_profiles": "local_stock_profile",
        "fina_mainbz": "local_business_segment",
        "raw_evidence_documents": None,
    }

    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    local_document = RawDocument(
        source_id="local_stock_profile",
        source_level="mid",
        title="本地公司档案",
        content_text="灵巧手业务",
        company_code="003021",
        doc_type="company_profile",
        metadata={"origin_table": "stock_profiles"},
    )
    first = repository.persist_raw_document(local_document, job_id="j1")
    second = repository.persist_raw_document(local_document, job_id="j2")

    assert (first.inserted, first.duplicate) == (True, False)
    assert (second.inserted, second.duplicate) == (False, True)

    statements = [sql for sql, _ in cursor.calls]
    catalog_index = next(
        index
        for index, sql in enumerate(statements)
        if "INSERT INTO evidence_source_catalog" in sql
    )
    raw_index = next(
        index
        for index, sql in enumerate(statements)
        if "INSERT INTO raw_evidence_documents" in sql
    )
    assert catalog_index < raw_index


def test_local_document_origin_table_and_historical_profile_cutoff_are_preserved():
    cursor = FakeCursor(
        table_names=["stock_profiles", "fina_mainbz"],
        query_rows={
            "FROM stock_profiles": [
                {
                    "code": "003021",
                    "full_name": "兆威机电",
                    "main_business": "灵巧手产品",
                    "business_scope": "机器人零部件",
                    "introduction": "",
                    "website": "https://example.test",
                    "updated_at": datetime(2026, 7, 10, 9, 0),
                }
            ],
            "FROM fina_mainbz": [
                {
                    "code": "003021",
                    "end_date": date(2026, 6, 30),
                    "biz_item": "灵巧手业务",
                    "biz_income": 1.0,
                    "biz_ratio": 0.1,
                    "biz_type": "P",
                }
            ],
        },
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    task = type(
        "Task", (), {"company_code": "003021", "queries": ("灵巧手",)}
    )()

    rows, _ = repository.fetch_local_documents(task, AS_OF)

    assert [row.source_id for row in rows] == ["local_business_segment"]
    assert rows[0].metadata["origin_table"] == "fina_mainbz"
    profile_sql = next(sql for sql, _ in cursor.calls if "FROM stock_profiles" in sql)
    assert "updated_at < %s" in profile_sql


def test_discovery_metadata_and_query_support_cross_job_recovery():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    repository.persist_discovery_hit(discovery_hit("d-cross-job"), job_id="job-1")
    repository.persist_discovery_hit(discovery_hit("d-cross-job"), job_id="job-2")

    fact_calls = [
        (sql, params)
        for sql, params in cursor.calls
        if "INSERT INTO evidence_extracted_facts" in sql
    ]
    assert len(fact_calls) == 2
    for expected_job, (_sql, params) in zip(("job-1", "job-2"), fact_calls):
        payload = json.loads(next(value for value in params if str(value).startswith("{")))
        assert payload["collection_job_ids"] == [expected_job]
        assert payload["candidate_proposal"]["provenance"]["discovery_doc_ids"]
    assert "collection_job_ids" in fact_calls[1][0]

    query_cursor = FakeCursor(query_rows={"candidate_proposal": []})
    query_repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(query_cursor)
    )
    query_repository.list_candidate_proposals("job-2")
    query_sql = query_cursor.calls[0][0]
    assert "metadata -> 'collection_job_ids' ? %s" in query_sql


def test_candidate_upsert_locks_before_select_and_merges_nested_discovery_ids():
    existing = {
        "mapping_id": "candidate-stable",
        "code": "688001",
        "business_segment_id": "reviewed-segment",
        "node_id": "reviewed-node",
        "theme_id": None,
        "chain_id": "dexterous_hand",
        "tag_name": "已审标签",
        "l1_l8_path": {
            "requirement_id": "dexterous_axial_flux_motor",
            "technology_route_id": "dexterous_axial_flux_motor",
            "l1_l8_path": {
                "discovery_doc_ids": ["old-doc"],
                "discovery_fact_ids": ["old-fact"],
            },
        },
        "confidence": 0.7,
        "status": "weak_evidence",
        "evidence_ids": ["review-e1"],
    }
    cursor = FakeCursor(mapping_row=existing)
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    result = repository.upsert_candidate_mapping(
        candidate_proposal(
            discovery_doc_ids=("new-doc",), discovery_fact_ids=("new-fact",)
        )
    )

    statements = [sql for sql, _ in cursor.calls]
    lock_index = next(
        index for index, sql in enumerate(statements) if "pg_advisory_xact_lock" in sql
    )
    select_index = next(
        index for index, sql in enumerate(statements) if "FOR UPDATE" in sql
    )
    assert lock_index < select_index
    assert result.status == "weak_evidence"
    assert result.confidence == 0.7
    assert result.evidence_ids == ("review-e1",)
    assert result.provenance["discovery_doc_ids"] == ["old-doc", "new-doc"]
    assert result.provenance["l1_l8_path"]["discovery_fact_ids"] == [
        "old-fact",
        "new-fact",
    ]


def test_point_in_time_queries_use_shanghai_exclusive_upper_bound():
    cursor = FakeCursor(
        query_rows={
            "FROM evidence_extracted_facts f": [],
            "FROM raw_evidence_documents": [],
            "FROM stock_profiles": [],
        }
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    requirement = {
        "product_terms": ["轴向磁通"],
        "scene_terms": ["机器人腕部"],
        "require_product_and_scene": True,
    }

    repository.fetch_asof_facts(("m1",), AS_OF)
    repository.fetch_candidate_universe(AS_OF, requirement, (), 5)
    repository.fetch_discovery_seed_companies(AS_OF, requirement, 5)

    source_wall_upper = datetime(2026, 7, 10, 0, 0)
    audit_utc_upper = datetime(2026, 7, 9, 16, 0)
    aware_upper = datetime(
        2026, 7, 10, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )
    fact_sql, fact_params = next(
        call for call in cursor.calls if "FROM evidence_extracted_facts f" in call[0]
    )
    assert "d.publish_time < %s" in fact_sql
    assert "f.created_at < %s" in fact_sql
    assert "f.reviewed_at IS NULL OR f.reviewed_at < %s" in fact_sql
    assert fact_params == (
        ["m1"], source_wall_upper, audit_utc_upper, aware_upper
    )
    candidate_sql, candidate_params = next(
        call for call in cursor.calls if "FROM raw_evidence_documents" in call[0]
    )
    assert "publish_time < %s" in candidate_sql
    assert "created_at < %s" in candidate_sql
    assert candidate_params == (source_wall_upper, audit_utc_upper, 25)
    seed_sql, seed_params = next(
        call for call in cursor.calls if "FROM stock_profiles" in call[0]
    )
    assert "updated_at < %s" in seed_sql
    assert seed_params == (
        ["%轴向磁通%"], audit_utc_upper, 5
    )


def test_node_dimension_auto_upsert_never_overwrites_reviewed_rows():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    repository.upsert_node_dimension_updates(
        (
            NodeDimensionUpdate(
                node_id="dexterous_hand_actuator",
                dimension_id="technology_route",
                as_of_date=AS_OF,
                status="known",
                score=80.0,
                evidence_ids=("f-new",),
            ),
        ),
        AS_OF,
    )

    sql = next(
        sql for sql, _ in cursor.calls if "INSERT INTO supply_chain_node_dimensions" in sql
    )
    assert "WHERE supply_chain_node_dimensions.review_status NOT IN ('approved','rejected')" in sql
    assert "review_status = 'pending_review'" not in sql.split("DO UPDATE SET", 1)[1]


def test_route_bearing_mapping_rejects_null_empty_and_wrong_route():
    def row(mapping_id, route):
        return {
            "mapping_id": mapping_id,
            "code": "688001",
            "business_segment_id": None,
            "node_id": "dexterous_hand_actuator",
            "theme_id": None,
            "chain_id": "dexterous_hand",
            "tag_name": "轴向磁通电机",
            "l1_l8_path": {
                "requirement_id": "dexterous_axial_flux_motor",
                "technology_route_id": route,
            },
            "confidence": 0.5,
            "status": "candidate",
            "evidence_ids": [],
        }

    cursor = FakeCursor(
        mapping_rows=[
            row("null-route", None),
            row("empty-route", ""),
            row("wrong-route", "automotive_axial_flux"),
            row("correct-route", "dexterous_axial_flux_motor"),
        ]
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    rows = repository.fetch_mappings("dexterous_hand", (), ())

    assert [item["mapping_id"] for item in rows] == ["correct-route"]
    assert repository.unresolved_technology_routes == [
        "null-route",
        "empty-route",
        "wrong-route",
    ]


def test_caller_owned_connection_is_never_committed_rolled_back_or_closed():
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: pytest.fail("caller connection must be reused")
    )

    outcome = repository.persist_discovery_hit(
        discovery_hit("d-transaction"), job_id="job-1", connection=connection
    )
    repository.upsert_candidate_mapping(outcome.proposal, connection=connection)

    assert connection.commits == 0
    assert connection.rollbacks == 0
    assert connection.closed == 0
    connection.rollback()
    assert connection.rollbacks == 1


def test_owned_connection_still_commits_and_closes():
    connection = FakeConnection(FakeCursor())
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: connection
    )

    repository.persist_discovery_hit(discovery_hit("d-owned"), job_id="job-1")

    assert connection.commits == 1
    assert connection.closed == 1


def test_older_gap_snapshot_cannot_overwrite_newer_snapshot():
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    gap = EvidenceGap(
        mapping_id="m1",
        requirement_id="product_or_prototype",
        status="missing",
        evidence_ids=(),
        next_action="补证",
        reasons=("缺失",),
    )
    repository.upsert_gap_rows((gap,), AS_OF)

    sql, params = next(
        call for call in cursor.calls if "UPDATE business_tag_mapping" in call[0]
    )
    assert "evidence_gaps_as_of_date" in sql
    assert "<= %s::date" in sql
    assert params.count(AS_OF.isoformat()) >= 2


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ('{"client_secret": "repo secret"}', "repo secret"),
        ("headers={'Authorization': 'Bearer repo-token'}", "repo-token"),
        ("https://example.test?api_key=query-secret&x=1", "query-secret"),
        ("password='spaced repo password'", "spaced repo password"),
        ("postgresql://alice:repo-pass@localhost/db", "repo-pass"),
    ],
)
def test_repository_error_sanitizer_handles_structured_secrets(raw, secret):
    cursor = FakeCursor()
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    repository.finish_job(
        "j1", AdapterResult((), (), (raw,), "partial_success")
    )
    params = next(
        params for sql, params in cursor.calls if "UPDATE evidence_collection_jobs" in sql
    )
    assert secret not in " ".join(str(value) for value in params)


def test_as_of_cutoffs_preserve_datetime_precision_and_sql_timestamp_types():
    from datetime import date, datetime, timezone
    from app.domains.supply_chain import evidence_orchestration_repository as module

    local_day = module._as_of_upper_bound(date(2026, 7, 9))
    local_intraday = module._as_of_upper_bound(datetime(2026, 7, 9, 9, 30))
    utc_intraday = module._as_of_upper_bound(
        datetime(2026, 7, 9, 15, 0, tzinfo=timezone.utc)
    )
    local_day_audit = module._as_of_audit_upper_bound(date(2026, 7, 9))
    local_intraday_audit = module._as_of_audit_upper_bound(
        datetime(2026, 7, 9, 9, 30)
    )
    utc_intraday_audit = module._as_of_audit_upper_bound(
        datetime(2026, 7, 9, 15, 0, tzinfo=timezone.utc)
    )

    assert local_day == datetime(2026, 7, 10, 0, 0)
    assert local_day.tzinfo is None
    assert local_intraday == datetime(2026, 7, 9, 9, 30)
    assert local_intraday.tzinfo is None
    assert utc_intraday == datetime(2026, 7, 9, 23, 0)
    assert utc_intraday.tzinfo is None
    assert local_day_audit == datetime(2026, 7, 9, 16, 0)
    assert local_intraday_audit == datetime(2026, 7, 9, 1, 30)
    assert utc_intraday_audit == datetime(2026, 7, 9, 15, 0)
    aware = module._as_of_aware_upper_bound(
        datetime(2026, 7, 9, 15, 0, tzinfo=timezone.utc)
    )
    assert aware == datetime(2026, 7, 9, 23, 0, tzinfo=module._SHANGHAI)


def test_candidate_proposals_merge_lineage_for_same_mapping_across_jobs():
    from dataclasses import replace
    from app.domains.supply_chain import evidence_orchestration_repository as module

    first = candidate_proposal(
        discovery_doc_ids=("d1",), discovery_fact_ids=("f1",)
    )
    second = replace(
        candidate_proposal(discovery_doc_ids=("d2",), discovery_fact_ids=("f2",)),
        confidence=first.confidence + 0.1,
    )

    merged = module._merge_candidate_proposals_by_mapping([first, second])

    assert len(merged) == 1
    assert merged[0].confidence == second.confidence
    assert tuple(merged[0].provenance["discovery_doc_ids"]) == ("d1", "d2")
    assert tuple(merged[0].provenance["discovery_fact_ids"]) == ("f1", "f2")


def test_asof_fact_sql_uses_naive_cutoffs_for_timestamp_and_aware_for_timestamptz():
    cursor = FakeCursor(query_rows={"FROM evidence_extracted_facts f": []})
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    cutoff = datetime(2026, 7, 9, 15, 0, tzinfo=timezone.utc)

    repository.fetch_asof_facts(("m1",), cutoff)

    sql, params = next(
        call for call in cursor.calls if "FROM evidence_extracted_facts f" in call[0]
    )
    assert "d.publish_time < %s" in sql
    assert "f.created_at < %s" in sql
    assert "f.reviewed_at < %s" in sql
    assert params[1] == datetime(2026, 7, 9, 23, 0)
    assert params[2] == datetime(2026, 7, 9, 15, 0)
    assert params[3] == datetime(
        2026, 7, 9, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )


def test_candidate_and_local_raw_queries_cut_off_publish_and_ingest_times():
    from types import SimpleNamespace

    cursor = FakeCursor(
        table_names=["raw_evidence_documents"],
        query_rows={"FROM raw_evidence_documents": []},
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    requirement = {
        "product_terms": ["轴向磁通"],
        "scene_terms": ["机器人腕部"],
        "require_product_and_scene": True,
    }
    task = SimpleNamespace(company_code="688001", queries=("轴向磁通",))

    repository.fetch_candidate_universe(AS_OF, requirement, (), 5)
    repository.fetch_local_documents(task, AS_OF)

    raw_calls = [
        (sql, params)
        for sql, params in cursor.calls
        if "FROM raw_evidence_documents" in sql
    ]
    assert len(raw_calls) == 2
    for sql, params in raw_calls:
        assert "publish_time < %s" in sql
        assert "created_at < %s" in sql
        cutoffs = [value for value in params if isinstance(value, datetime)]
        assert cutoffs[-2:] == [
            datetime(2026, 7, 10, 0, 0),
            datetime(2026, 7, 9, 16, 0),
        ]
        assert all(value.tzinfo is None for value in cutoffs[-2:])


def test_undated_patent_is_retained_pending_and_cut_off_by_created_at():
    from types import SimpleNamespace
    from supply_chain_evidence_adapters import current_support_status

    cursor = FakeCursor(
        table_names=["patent_events"],
        query_rows={
            "FROM patent_events": [
                {
                    "event_id": "pat-null-date",
                    "company_code": "688001",
                    "company_name": "测试公司",
                    "publication_number": "CN-X",
                    "patent_title": "机器人腕部轴向磁通电机",
                    "patent_abstract": "用于机器人腕部",
                    "applicant": "测试公司",
                    "application_date": None,
                    "publication_date": None,
                    "grant_date": None,
                    "patent_status": "active",
                    "created_at": datetime(2026, 7, 9, 8, 0),
                    "metadata": {},
                }
            ]
        },
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )
    task = SimpleNamespace(company_code="688001", queries=("轴向磁通",))

    rows, _ = repository.fetch_local_documents(task, AS_OF)

    sql, params = next(
        call for call in cursor.calls if "FROM patent_events" in call[0]
    )
    assert "COALESCE(publication_date, application_date) IS NULL" in sql
    assert "created_at < %s" in sql
    assert params[-1] == datetime(2026, 7, 9, 16, 0)
    assert len(rows) == 1
    assert rows[0].publish_time is None
    assert rows[0].metadata["legal_status_date"] is None
    assert current_support_status(rows[0], AS_OF) == "pending_review"
