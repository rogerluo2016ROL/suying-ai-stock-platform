"""Contracts for the supply-chain evidence orchestration repository."""

from __future__ import annotations

from datetime import date, datetime
import json

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
    ):
        self.mapping_row = mapping_row
        self.mapping_rows = list(mapping_rows or [])
        self.table_names = list(table_names or [])
        self.query_rows = dict(query_rows or {})
        self.calls: list[tuple[str, tuple]] = []
        self._one = None
        self._many = []
        self.rowcount = 1

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
    assert any("publish_time <= %s" in sql for sql, _ in cursor.calls)
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
