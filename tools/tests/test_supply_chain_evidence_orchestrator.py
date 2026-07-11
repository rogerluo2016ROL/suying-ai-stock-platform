"""Contracts for end-to-end supply-chain evidence orchestration."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
import inspect
from pathlib import Path
from types import SimpleNamespace
import warnings

import pytest

warnings.filterwarnings(
    "ignore",
    message=r"Unknown pytest\.mark\.postgresql.*",
    category=pytest.PytestUnknownMarkWarning,
)

from kronos_factors.engine.supply_chain_evidence_orchestration import (
    CandidateMappingProposal,
    DiscoveryHit,
    EvidenceGap,
    EvidenceRunRequest,
)
from supply_chain_data_collection_center import RawDocument
from supply_chain_evidence_adapters import AdapterResult
from supply_chain_evidence_orchestrator import (
    build_collection_tasks,
    build_unmapped_discovery_tasks,
    run_evidence_orchestration,
)


AS_OF = date(2026, 7, 9)


def axis_requirement(requirement_id: str = "dexterous_axial_flux_motor") -> dict:
    return {
        "chain_id": "dexterous_hand",
        "requirement_id": requirement_id,
        "node_id": "dexterous_hand_foundation",
        "business_keywords": ["轴向磁通电机"],
        "product_terms": ["轴向磁通电机"],
        "scene_terms": ["机器人腕部"],
        "negative_examples": ["轮毂", "航空"],
        "require_product_and_scene": True,
        "required_evidence_type_ids": [
            "product_or_prototype",
            "customer_validation",
        ],
        "independent_discovery": True,
        "technology_route_id": "dexterous_axial_flux_motor",
    }


def mapping(
    mapping_id: str = "m1",
    code: str = "688001",
    *,
    requirement_id: str = "dexterous_axial_flux_motor",
    node_id: str = "dexterous_hand_foundation",
) -> dict:
    return {
        "mapping_id": mapping_id,
        "code": code,
        "company_name": f"公司{code}",
        "chain_id": "dexterous_hand",
        "node_id": node_id,
        "tag_name": "轴向磁通电机",
        "status": "candidate",
        "confidence": 0.35,
        "evidence_ids": [],
        "requirement_id": requirement_id,
        "technology_route_id": "dexterous_axial_flux_motor",
        "l1_l8_path": {"requirement_id": requirement_id},
    }


def document(
    name: str,
    *,
    code: str = "688001",
    text: str = "机器人腕部采用轴向磁通电机",
) -> RawDocument:
    return RawDocument(
        source_id="test-source",
        source_level="strong",
        title=name,
        content_text=f"{name} {text}",
        url=f"https://example.test/{name}",
        company_code=code,
        company_name=f"公司{code}",
        publish_time="2026-07-01T10:00:00+08:00",
        doc_type="announcement",
        metadata={},
    )


def discovery_hit(code: str = "688001", requirement_id: str = "req-1") -> DiscoveryHit:
    proposal = CandidateMappingProposal(
        mapping_id=f"candidate-{code}-{requirement_id}",
        company_code=code,
        chain_id="dexterous_hand",
        node_id="dexterous_hand_foundation",
        tag_name="轴向磁通电机",
        technology_route_id="dexterous_axial_flux_motor",
        status="candidate",
        confidence=0.35,
        evidence_ids=(),
        provenance={"requirement_id": requirement_id},
    )
    return DiscoveryHit(
        doc_id=f"doc-{code}-{requirement_id}",
        company_code=code,
        requirement_id=requirement_id,
        product_hits=("轴向磁通电机",),
        scene_hits=("机器人腕部",),
        excluded_hits=(),
        source_level="strong",
        publish_time=datetime(2026, 7, 1, 10, 0),
        eligible_for_mapping=True,
        validation_status="pending",
        proposal=proposal,
    )


def audited_dimension_fact(
    mapping_id: str,
    dimension_id: str,
    *,
    fact_id: str | None = None,
    status: str = "confirmed",
) -> dict:
    return {
        "fact_id": fact_id or f"fact-{mapping_id}-{dimension_id}",
        "mapping_id": mapping_id,
        "fact_type": "product_spec",
        "fact_nature": "confirmed_fact",
        "source_level": "strong",
        "validation_status": status,
        "reviewer": "reviewer-1" if status == "confirmed" else None,
        "review_note": "已核对原始证据" if status == "confirmed" else None,
        "reviewed_at": datetime(2026, 7, 2, 10, 0) if status == "confirmed" else None,
        "publish_time": datetime(2026, 7, 1, 9, 0),
        "metadata": {"dimension_ids": [dimension_id]},
    }


class FakeRepository:
    def __init__(
        self,
        *,
        mappings=None,
        requirements=None,
        local_discovery_documents=None,
        seed_codes=None,
        facts=None,
        pending_outcomes=None,
        fail_persist: bool = False,
    ):
        self.mappings = list(mappings if mappings is not None else [mapping()])
        self.requirements = list(requirements if requirements is not None else [axis_requirement()])
        self.local_discovery_documents = list(local_discovery_documents or [])
        self.seed_codes = list(seed_codes or ["688001", "688002"])
        self.facts = list(facts or [])
        self.pending_outcomes = list(pending_outcomes or [])
        self.fail_persist = fail_persist
        self.fetch_mapping_calls = []
        self.discovery_scope_calls = []
        self.started_jobs = []
        self.finished_jobs = []
        self.persisted_discovery_codes = []
        self.mapping_upserts = []
        self.persisted_pending = []
        self.persisted_raw = []
        self.dimension_updates = []
        self.events = []

    def fetch_mappings(self, chain_id, mapping_ids, company_codes):
        self.fetch_mapping_calls.append((chain_id, tuple(mapping_ids), tuple(company_codes)))
        # Deliberately return everything. The orchestration boundary must enforce scope too.
        return [dict(item) for item in self.mappings]

    def fetch_independent_discovery_requirements(self, chain_id):
        assert chain_id == "dexterous_hand"
        return [dict(item) for item in self.requirements]

    def fetch_candidate_universe(self, as_of_date, requirement, company_codes, limit):
        self.discovery_scope_calls.append(tuple(company_codes))
        assert as_of_date == AS_OF
        assert limit > 0
        return [dict(item) for item in self.local_discovery_documents]

    def fetch_discovery_seed_companies(self, as_of_date, requirement, limit):
        assert as_of_date == AS_OF
        return self.seed_codes[:limit]

    def fetch_asof_facts(self, mapping_ids, cutoff):
        assert cutoff.date() == AS_OF
        return [dict(item) for item in self.facts]

    def start_job(self, request):
        self.events.append("start_job")
        self.started_jobs.append(request)
        return "job-1"

    def finish_job(self, job_id, payload):
        self.events.append(f"finish:{payload['status']}")
        self.finished_jobs.append((job_id, payload))

    def persist_discovery_hit(self, hit, *, job_id):
        self.events.append(f"persist_discovery:{hit.company_code}")
        self.persisted_discovery_codes.append(hit.company_code)
        return SimpleNamespace(
            proposal=hit.proposal,
            validation_status="pending",
            inserted=True,
            doc_id=hit.doc_id,
            fact_id=f"fact-{hit.doc_id}",
        )

    def upsert_candidate_mapping(self, proposal):
        self.events.append(f"upsert_mapping:{proposal.company_code}")
        self.mapping_upserts.append(proposal)
        if not any(item["mapping_id"] == proposal.mapping_id for item in self.mappings):
            self.mappings.append(
                mapping(
                    proposal.mapping_id,
                    proposal.company_code,
                    requirement_id=str(proposal.provenance["requirement_id"]),
                    node_id=proposal.node_id,
                )
            )
        return proposal

    def persist_pending_document(self, **kwargs):
        if self.fail_persist:
            raise RuntimeError("persist failed")
        self.events.append(
            f"persist_pending:{kwargs['mapping_id']}:{kwargs['requirement_id']}"
        )
        self.persisted_pending.append(kwargs)
        if self.pending_outcomes:
            return self.pending_outcomes.pop(0)
        return SimpleNamespace(
            doc_id=kwargs["document"].doc_id,
            fact_id=f"fact-{kwargs['document'].doc_id}",
            validation_status="pending",
            inserted=True,
        )

    def persist_raw_document(self, document, *, job_id):
        self.persisted_raw.append((document, job_id))
        return SimpleNamespace(doc_id=document.doc_id, inserted=True)

    def upsert_node_dimension_updates(self, updates, as_of_date):
        self.events.append("dimension_updates")
        self.dimension_updates.extend(updates)
        return len(updates)


class FakeAdapter:
    def __init__(self, documents=(), *, requests=0, failed=(), errors=()):
        self.documents = tuple(documents)
        self.requests = requests
        self.failed = tuple(failed)
        self.errors = tuple(errors)
        self.calls = []

    def collect(self, tasks, *, as_of_date, source_limits=None):
        self.calls.append((tuple(tasks), as_of_date, dict(source_limits or {})))
        status = "partial_success" if self.failed or self.errors else (
            "success" if self.documents else "empty"
        )
        return AdapterResult(
            self.documents,
            self.failed,
            self.errors,
            status,
            self.requests,
        )


class FailIfCalledAdapter:
    def collect(self, *_args, **_kwargs):
        raise AssertionError("adapter must not be called")


class SpyScoreRunner:
    def __init__(self, events=None):
        self.calls = []
        self.events = events

    def __call__(self, **kwargs):
        if self.events is not None:
            self.events.append("score")
        self.calls.append(kwargs)
        return {
            "mapping_count": len(kwargs["mapping_ids"]),
            "pool_counts": {"B": len(kwargs["mapping_ids"])},
            "transitions": len(kwargs["mapping_ids"]),
            "written": len(kwargs["mapping_ids"]),
            "results": [],
        }


class FailIfCalled:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError("score runner must not be called")


def request(mode: str, source_policy: str = "local-first", **kwargs):
    return EvidenceRunRequest(
        "dexterous_hand",
        AS_OF,
        mode,
        source_policy,
        **kwargs,
    )


def test_dry_run_has_no_network_writes_or_jobs():
    repository = FakeRepository()
    result = run_evidence_orchestration(
        request("dry-run"),
        repository=repository,
        local_adapter=FailIfCalledAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=FailIfCalled(),
    )

    assert result.writes == 0
    assert result.network_requests == 0
    assert repository.started_jobs == []
    assert repository.finished_jobs == []
    assert repository.dimension_updates == []


def test_collect_does_not_score_change_pool_or_node_dimensions():
    score_runner = SpyScoreRunner()
    repository = FakeRepository()
    result = run_evidence_orchestration(
        request("collect", "official-gap"),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter(),
        official_adapter=FakeAdapter(),
        score_runner=score_runner,
    )

    assert score_runner.calls == []
    assert result.pool_transitions == 0
    assert repository.dimension_updates == []
    assert repository.finished_jobs[0][1]["status"] == "success"


def test_score_updates_only_fully_audited_dimensions_before_scoring():
    facts = [
        audited_dimension_fact("m1", "physical_bom"),
        audited_dimension_fact("m1", "technology_route", status="pending"),
    ]
    repository = FakeRepository(facts=facts)
    score_runner = SpyScoreRunner(repository.events)
    result = run_evidence_orchestration(
        request("score"),
        repository=repository,
        local_adapter=FailIfCalledAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=score_runner,
    )

    assert [item.dimension_id for item in repository.dimension_updates] == [
        "physical_bom"
    ]
    assert repository.events.index("dimension_updates") < repository.events.index("score")
    assert score_runner.calls[0]["mapping_ids"] == ["m1"]
    assert result.approved_facts == 1
    assert result.pending_facts == 0
    assert "score_repository_audit_gate_pending_task_8" in result.data_limitations


def test_score_never_assigns_one_mappings_fact_to_another_node():
    repository = FakeRepository(
        mappings=[
            mapping("m1", "688001", node_id="node-one"),
            mapping("m2", "688002", node_id="node-two"),
        ],
        facts=[audited_dimension_fact("m1", "physical_bom")],
    )
    run_evidence_orchestration(
        request("score"),
        repository=repository,
        local_adapter=FailIfCalledAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=SpyScoreRunner(),
    )

    assert [(item.node_id, item.dimension_id) for item in repository.dimension_updates] == [
        ("node-one", "physical_bom")
    ]


def test_score_aggregates_same_node_mapping_evidence_before_one_upsert():
    repository = FakeRepository(
        mappings=[
            mapping("m1", "688001", node_id="shared-node"),
            mapping("m2", "688002", node_id="shared-node"),
        ],
        facts=[
            audited_dimension_fact(
                "m1", "physical_bom", fact_id="bom-from-m1"
            ),
            audited_dimension_fact(
                "m2", "physical_bom", fact_id="bom-from-m2"
            ),
        ],
    )
    run_evidence_orchestration(
        request("score"),
        repository=repository,
        local_adapter=FailIfCalledAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=SpyScoreRunner(),
    )

    assert len(repository.dimension_updates) == 1
    assert repository.dimension_updates[0].node_id == "shared-node"
    assert repository.dimension_updates[0].evidence_ids == (
        "bom-from-m1",
        "bom-from-m2",
    )


@pytest.mark.parametrize("allow_score", [False, True])
def test_full_scores_only_with_explicit_allow_score(allow_score):
    repository = FakeRepository(facts=[audited_dimension_fact("m1", "physical_bom")])
    score_runner = SpyScoreRunner()
    result = run_evidence_orchestration(
        request("full", allow_score=allow_score),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=score_runner,
    )

    assert bool(score_runner.calls) is allow_score
    assert result.pool_transitions == (1 if allow_score else 0)
    assert bool(repository.dimension_updates) is allow_score


def test_company_scope_filters_local_global_and_persistence_results():
    repository = FakeRepository(
        mappings=[],
        local_discovery_documents=[
            {
                "doc_id": "local-in",
                "company_code": "688001",
                "source_level": "strong",
                "publish_time": "2026-07-01T10:00:00+08:00",
                "text": "机器人腕部轴向磁通电机",
            },
            {
                "doc_id": "local-out",
                "company_code": "688002",
                "source_level": "strong",
                "publish_time": "2026-07-01T10:00:00+08:00",
                "text": "机器人腕部轴向磁通电机",
            },
        ],
    )
    run_evidence_orchestration(
        request("collect", "official-gap", company_codes=("688001.SH",)),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter(
            [document("official-in", code="688001"), document("official-out", code="688002")]
        ),
        official_adapter=FakeAdapter(),
        score_runner=FailIfCalled(),
    )

    assert repository.discovery_scope_calls == [("688001",)]
    assert set(repository.persisted_discovery_codes) == {"688001"}
    assert {item.company_code for item in repository.mapping_upserts} == {"688001"}


def test_company_scope_filters_same_doc_id_from_a_different_company():
    repository = FakeRepository(mappings=[])
    in_scope = document("same-content", code="688001")
    out_of_scope = replace(in_scope, company_code="688002")
    assert in_scope.doc_id == out_of_scope.doc_id

    result = run_evidence_orchestration(
        request("collect", "official-gap", company_codes=("688001",)),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter([in_scope, out_of_scope]),
        official_adapter=FakeAdapter(),
        score_runner=FailIfCalled(),
    )

    assert result.official_discovery_hits == 1
    finished_documents = repository.finished_jobs[0][1]["documents"]
    assert [item.company_code for item in finished_documents] == ["688001"]


def test_discovery_pending_fact_is_reported_under_its_candidate_company():
    repository = FakeRepository(mappings=[])
    result = run_evidence_orchestration(
        request("collect", "official-gap", company_codes=("688001",)),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter([document("official-candidate")]),
        official_adapter=FakeAdapter(),
        score_runner=FailIfCalled(),
    )

    candidate = next(
        item for item in result.companies if item["company_code"] == "688001"
    )
    assert [item["validation_status"] for item in candidate["pending"]] == [
        "pending"
    ]


def test_mapping_scope_resolves_company_allow_list_for_official_discovery():
    repository = FakeRepository(
        mappings=[mapping("m1", "688001"), mapping("m2", "688002")],
    )
    official_discovery = FakeAdapter(
        [document("official-in", code="688001"), document("official-out", code="688002")]
    )
    local = FakeAdapter(
        [document("mapped-in", code="688001"), document("mapped-out", code="688002")]
    )
    run_evidence_orchestration(
        request("collect", "official-gap", mapping_ids=("m1",)),
        repository=repository,
        local_adapter=local,
        official_discovery_adapter=official_discovery,
        official_adapter=FakeAdapter(),
        score_runner=FailIfCalled(),
    )

    task = official_discovery.calls[0][0][0]
    assert task.allowed_company_codes == ("688001",)
    assert set(repository.persisted_discovery_codes) <= {"688001"}
    assert repository.persisted_pending
    assert {row["mapping_id"] for row in repository.persisted_pending} == {"m1"}
    assert {
        row["document"].company_code for row in repository.persisted_pending
    } == {"688001"}


def test_official_gap_emits_one_bounded_task_per_independent_requirement():
    requirements = [
        axis_requirement("req-1"),
        {**axis_requirement("req-2"), "product_terms": ["盘式电机"]},
    ]
    repository = FakeRepository(requirements=requirements, seed_codes=["688001", "688002"])
    tasks = build_unmapped_discovery_tasks(
        requirements,
        [discovery_hit("688001", "req-1")],
        repository,
        request("collect", "official-gap", company_codes=("688001", "688002")),
        [mapping("m1", "688001")],
    )

    assert [task.requirement_id for task in tasks] == ["req-1", "req-2"]
    assert tasks[0].seed_company_codes == ("688002",)
    assert tasks[1].seed_company_codes == ("688001", "688002")
    assert all(task.allowed_company_codes == ("688001", "688002") for task in tasks)


def test_scoped_discovery_seeds_use_allow_list_when_global_rank_omits_company():
    repository = FakeRepository(seed_codes=["999999"])
    tasks = build_unmapped_discovery_tasks(
        [axis_requirement()],
        [],
        repository,
        request(
            "collect",
            "official-gap",
            company_codes=("688001", "688002"),
            source_limits={"official_discovery_companies": 1},
        ),
        [],
    )

    assert tasks[0].allowed_company_codes == ("688001", "688002")
    assert tasks[0].seed_company_codes == ("688001",)


def test_collection_tasks_keep_mapping_requirement_and_grouped_terms_isolated():
    gaps = [
        EvidenceGap(
            mapping_id="m1",
            requirement_id="product_or_prototype",
            status="missing",
            evidence_ids=(),
            next_action="collect_product_evidence",
            reasons=("missing",),
            product_terms=("轴向磁通电机",),
            scene_terms=("机器人腕部",),
            negative_examples=("轮毂",),
        ),
        EvidenceGap(
            mapping_id="m2",
            requirement_id="customer_validation",
            status="proxy",
            evidence_ids=("proxy-1",),
            next_action="collect_customer_validation",
            reasons=("proxy",),
            product_terms=("空心杯电机",),
            scene_terms=("机器人手指",),
            negative_examples=("消费电子",),
        ),
    ]

    tasks = build_collection_tasks(
        gaps,
        candidates=(mapping("m1", "688001"), mapping("m2", "688002")),
    )

    assert [(task.mapping_id, task.requirement_id) for task in tasks] == [
        ("m1", "product_or_prototype"),
        ("m2", "customer_validation"),
    ]
    assert tasks[0].queries == ("轴向磁通电机", "机器人腕部")
    assert tasks[1].negative_examples == ("消费电子",)


def test_mapped_documents_persist_only_to_the_task_they_match():
    repository = FakeRepository(
        mappings=[mapping("m1", "688001"), mapping("m2", "688002")]
    )
    local = FakeAdapter([document("only-m1", code="688001")])
    run_evidence_orchestration(
        request("collect"),
        repository=repository,
        local_adapter=local,
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=FailIfCalled(),
    )

    assert repository.persisted_pending
    assert {row["mapping_id"] for row in repository.persisted_pending} == {"m1"}
    assert all(row["document"].company_code == "688001" for row in repository.persisted_pending)


def test_counts_come_from_returned_outcomes_and_pending_is_not_approved():
    outcomes = [
        SimpleNamespace(validation_status="pending", inserted=True, fact_id="p1"),
        SimpleNamespace(validation_status="pending", duplicate=True, fact_id="p2"),
    ]
    single_requirement_mapping = mapping()
    single_requirement_mapping["required_evidence_type_ids"] = [
        "product_or_prototype"
    ]
    repository = FakeRepository(
        mappings=[single_requirement_mapping],
        requirements=[
            {
                **axis_requirement(),
                "required_evidence_type_ids": ["product_or_prototype"],
            }
        ],
        pending_outcomes=outcomes,
    )
    result = run_evidence_orchestration(
        request("collect"),
        repository=repository,
        local_adapter=FakeAdapter(
            [document("inserted"), replace(document("duplicate"), url="https://other.test/duplicate")]
        ),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=FailIfCalled(),
    )

    assert result.inserted_documents == 1
    assert result.duplicate_documents == 1
    assert result.pending_facts == 2
    assert result.approved_facts == 0


def test_unknown_repository_insert_conflict_counts_stay_zero_with_limitation():
    single_requirement_mapping = mapping()
    single_requirement_mapping["required_evidence_type_ids"] = [
        "product_or_prototype"
    ]
    repository = FakeRepository(
        mappings=[single_requirement_mapping],
        requirements=[
            {
                **axis_requirement(),
                "required_evidence_type_ids": ["product_or_prototype"],
            }
        ],
        pending_outcomes=[
            SimpleNamespace(validation_status="pending", fact_id="ambiguous")
        ],
    )
    result = run_evidence_orchestration(
        request("collect"),
        repository=repository,
        local_adapter=FakeAdapter([document("ambiguous")]),
        official_discovery_adapter=FailIfCalledAdapter(),
        official_adapter=FailIfCalledAdapter(),
        score_runner=FailIfCalled(),
    )

    assert result.inserted_documents == 0
    assert result.duplicate_documents == 0
    assert "persistence_outcome_does_not_expose_insert_duplicate_counts" in (
        result.data_limitations
    )


def test_network_and_partial_job_counts_are_aggregated_from_both_official_adapters():
    single_requirement_mapping = mapping()
    single_requirement_mapping["required_evidence_type_ids"] = [
        "product_or_prototype"
    ]
    repository = FakeRepository(
        mappings=[single_requirement_mapping],
        requirements=[
            {
                **axis_requirement(),
                "required_evidence_type_ids": ["product_or_prototype"],
            }
        ]
    )
    result = run_evidence_orchestration(
        request("collect", "official-gap"),
        repository=repository,
        local_adapter=FakeAdapter(),
        official_discovery_adapter=FakeAdapter(
            [document("discovery", text="不相关的公告")],
            requests=2,
            failed=("discover:req",),
            errors=("d",),
        ),
        official_adapter=FakeAdapter(
            [document("mapped")], requests=3, failed=("m1:req",), errors=("m",)
        ),
        score_runner=FailIfCalled(),
    )

    assert result.network_requests == 5
    assert result.failed_tasks == ("discover:req", "m1:req")
    assert repository.finished_jobs[0][1]["status"] == "partial_success"


def test_collection_exception_finishes_job_as_failed_before_reraising():
    repository = FakeRepository(fail_persist=True)
    with pytest.raises(RuntimeError, match="persist failed"):
        run_evidence_orchestration(
            request("collect"),
            repository=repository,
            local_adapter=FakeAdapter([document("boom")]),
            official_discovery_adapter=FailIfCalledAdapter(),
            official_adapter=FailIfCalledAdapter(),
            score_runner=FailIfCalled(),
        )

    assert repository.finished_jobs[0][1]["status"] == "failed"
    assert "persist failed" in repository.finished_jobs[0][1]["errors"][0]


def test_cli_parser_accepts_exact_arguments_and_validates_source_limits():
    import run_supply_chain_evidence_orchestration as cli

    args = cli.build_parser().parse_args(
        [
            "--chain-id",
            "dexterous_hand",
            "--as-of-date",
            "2026-07-09",
            "--mode",
            "full",
            "--source-policy",
            "official-gap",
            "--source-limit",
            "discovery=100",
            "--source-limit",
            "official_pages_per_company=2",
            "--mapping-id",
            "m1",
            "--allow-score",
            "--pg-url",
            "postgresql://example.invalid/db",
            "--output-dir",
            "out",
        ]
    )
    parsed = cli.request_from_args(args)

    assert parsed.mapping_ids == ("m1",)
    assert parsed.company_codes == ()
    assert dict(parsed.source_limits) == {
        "discovery": 100,
        "official_pages_per_company": 2,
    }
    assert parsed.allow_score is True
    with pytest.raises(ValueError, match="source limit"):
        cli.parse_source_limits(["discovery=0"])
    with pytest.raises(ValueError, match="key=value"):
        cli.parse_source_limits(["discovery"])


def test_cli_uses_real_dependencies_from_the_current_worktree():
    import run_supply_chain_evidence_orchestration as cli
    from app.domains.supply_chain.evidence_orchestration_repository import (
        EvidenceOrchestrationRepository,
    )
    from supply_chain_evidence_adapters import (
        LocalEvidenceAdapter,
        OfficialDiscoveryAdapter,
        OfficialGapAdapter,
    )

    dependencies = cli.build_runtime_dependencies(
        SimpleNamespace(pg_url="postgresql://example.invalid/db")
    )
    root = Path(__file__).resolve().parents[2]

    assert isinstance(dependencies["repository"], EvidenceOrchestrationRepository)
    assert isinstance(dependencies["local_adapter"], LocalEvidenceAdapter)
    assert isinstance(dependencies["official_adapter"], OfficialGapAdapter)
    assert isinstance(
        dependencies["official_discovery_adapter"], OfficialDiscoveryAdapter
    )
    assert dependencies["score_runner"].func is cli.run_batch_score
    assert Path(inspect.getfile(cli.EvidenceOrchestrationRepository)).resolve().is_relative_to(
        root
    )
    assert cli.WORKTREE_IMPORT_PATHS == (
        str(root / "tools"),
        str(root / "packages" / "kronos-factors"),
        str(root / "services" / "screener-service"),
    )


def test_cli_writes_json_and_markdown_only_when_output_dir_is_supplied(
    monkeypatch, tmp_path
):
    import run_supply_chain_evidence_orchestration as cli
    from supply_chain_evidence_orchestrator import build_empty_score_result

    result = build_empty_score_result(request("dry-run"), reason="test")
    monkeypatch.setattr(cli, "build_runtime_dependencies", lambda _args: {})
    monkeypatch.setattr(cli, "run_evidence_orchestration", lambda *_args, **_kwargs: result)
    monkeypatch.chdir(tmp_path)
    common = [
        "--chain-id",
        "dexterous_hand",
        "--as-of-date",
        "2026-07-09",
        "--mode",
        "dry-run",
        "--source-policy",
        "local-first",
    ]

    assert cli.main(common) == 0
    assert not (tmp_path / "result.json").exists()
    assert not (tmp_path / "report.md").exists()

    output_dir = tmp_path / "explicit-output"
    assert cli.main([*common, "--output-dir", str(output_dir)]) == 0
    assert (output_dir / "result.json").is_file()
    assert (output_dir / "report.md").is_file()


@pytest.mark.postgresql
def test_real_local_adapter_reads_inserted_raw_document_for_exact_task(monkeypatch):
    """Optional PostgreSQL integration; no network calls are made."""

    import os
    import uuid

    import psycopg2

    root = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(root / "services" / "screener-service"))

    from app.domains.supply_chain.evidence_orchestration_repository import (
        EvidenceOrchestrationRepository,
    )
    from supply_chain_evidence_adapters import CollectionTask, LocalEvidenceAdapter

    pg_url = os.getenv(
        "KRONOS_PG_URL",
        "postgresql://kronos:kronos@localhost:6432/kronos",
    )
    try:
        connection = psycopg2.connect(pg_url, connect_timeout=1)
    except psycopg2.Error as exc:
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    connection.close()

    token = uuid.uuid4().hex
    code = f"T{token[:5]}"
    as_of_date = date.today()
    raw = RawDocument(
        source_id="integration-local",
        source_level="strong",
        title=f"local-{token}",
        content_text=f"{token} 轴向磁通电机用于机器人腕部",
        company_code=code,
        company_name="集成测试公司",
        publish_time=(as_of_date - timedelta(days=1)).isoformat(),
        doc_type="announcement",
        metadata={},
    )
    repository = EvidenceOrchestrationRepository(
        connection_factory=lambda: psycopg2.connect(pg_url, connect_timeout=1)
    )
    repository.persist_raw_document(raw, job_id=f"integration-{token}")
    try:
        task = CollectionTask(
            mapping_id=f"mapping-{token}",
            requirement_id="product_or_prototype",
            company_code=code,
            company_name="集成测试公司",
            queries=("轴向磁通电机", "机器人腕部"),
            product_terms=("轴向磁通电机",),
            scene_terms=("机器人腕部",),
            negative_examples=("轮毂",),
        )
        result = LocalEvidenceAdapter(repository).collect([task], as_of_date=as_of_date)
        assert [item.doc_id for item in result.documents] == [raw.doc_id]
        assert result.network_requests == 0
    finally:
        with psycopg2.connect(pg_url, connect_timeout=1) as cleanup:
            with cleanup.cursor() as cur:
                cur.execute("DELETE FROM raw_evidence_documents WHERE doc_id = %s", (raw.doc_id,))
