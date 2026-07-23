"""Contract tests for the dexterous-hand PostgreSQL UAT harness."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import run_supply_chain_evidence_orchestration_uat as uat
from supply_chain_data_collection_center import RawDocument
from supply_chain_evidence_adapters import AdapterResult


AS_OF = date(2026, 7, 9)
EXPECTED_OUTPUT = Path("outputs/supply_chain_evidence/dexterous_hand/2026-07-09")


def test_build_uat_plan_is_fixed_and_read_only_for_real_companies():
    plan = uat.build_uat_plan("dexterous_hand", AS_OF)

    assert plan.steps == (
        "preflight",
        "dry_run",
        "collect",
        "collect_idempotency",
        "score_before_review",
        "synthetic_review_rollback",
        "report",
    )
    assert plan.real_fact_review_mode == "read_only"
    assert plan.synthetic_review_rollback is True
    assert plan.synthetic_score_date_policy == "reviewed_at_date"
    assert plan.company_codes == ("003021", "300007", "300660", "603662", "603728")
    with pytest.raises(Exception):
        plan.company_codes += ("000001",)


@pytest.mark.parametrize(
    ("chain_id", "as_of", "output"),
    [
        ("other", "2026-07-09", EXPECTED_OUTPUT),
        ("dexterous_hand", "2026-07-08", EXPECTED_OUTPUT),
        ("dexterous_hand", "2026-07-09", Path("outputs/elsewhere")),
    ],
)
def test_invalid_cli_contract_fails_before_connect(chain_id, as_of, output):
    calls = []

    code = uat.run_cli(
        [
            "--pg-url",
            "postgresql://user:secret@localhost:6432/kronos",
            "--chain-id",
            chain_id,
            "--as-of-date",
            as_of,
            "--output-dir",
            str(output),
        ],
        connector=lambda *_args, **_kwargs: calls.append("connect"),
    )
    assert code != 0
    assert calls == []


def test_output_path_may_be_absolute_but_is_locked_to_repo_root():
    expected = uat.REPO_ROOT / EXPECTED_OUTPUT
    parsed = uat.validate_uat_inputs(
        pg_url="postgresql://localhost:6432/kronos",
        chain_id="dexterous_hand",
        as_of_date="2026-07-09",
        output_dir=expected,
    )
    assert parsed.output_dir == expected.resolve()
    assert parsed.as_of_date == AS_OF


@pytest.mark.parametrize(
    "dsn",
    (
        "mysql://localhost:6432/kronos",
        "postgresql://db.example.com:6432/kronos",
        "postgresql://localhost:5432/kronos",
        "postgresql://localhost:6432/other",
    ),
)
def test_pg_url_is_locked_to_existing_local_kronos_database(dsn):
    with pytest.raises(uat.UATContractError):
        uat.validate_uat_inputs(
            pg_url=dsn,
            chain_id="dexterous_hand",
            as_of_date="2026-07-09",
            output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
        )


def test_working_directory_must_be_the_worktree_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(uat.UATContractError, match="working directory"):
        uat.validate_uat_inputs(
            pg_url="postgresql://localhost:6432/kronos",
            chain_id="dexterous_hand",
            as_of_date="2026-07-09",
            output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
        )


def test_redaction_removes_password_and_common_credentials():
    dsn = "postgresql://alice:s3cret@localhost:6432/kronos?token=abc"
    text = uat.sanitize_diagnostic(
        RuntimeError(f"failed {dsn} Cookie=session API_KEY=key-1"), pg_url=dsn
    )
    assert "s3cret" not in text
    assert "token=abc" not in text
    assert "session" not in text
    assert "key-1" not in text
    assert "localhost:6432" in text


class SnapshotCursor:
    def __init__(self, row):
        self.row = row
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        self.sql = sql

    def fetchone(self):
        return self.row


class SnapshotConnection:
    def __init__(self, row):
        self.cursor_value = SnapshotCursor(row)

    def cursor(self, **_kwargs):
        return self.cursor_value


def test_count_snapshot_has_every_required_counter_and_stable_name():
    expected = {key: index for index, key in enumerate(uat.SNAPSHOT_FIELDS, start=1)}
    snapshot = uat.capture_count_snapshot(SnapshotConnection(expected), "before")
    assert snapshot.name == "before"
    assert snapshot.counts == expected
    sql = SnapshotConnection(expected)
    uat.capture_count_snapshot(sql, "after_dry_run")
    assert all(field in sql.cursor_value.sql for field in uat.SNAPSHOT_FIELDS)


class RawConnection:
    def __init__(self):
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0
        self.autocommit = False

    def cursor(self, *args, **kwargs):
        return (args, kwargs)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1

    def close(self):
        self.close_calls += 1


def test_caller_owned_guard_forbids_business_transaction_ownership():
    raw = RawConnection()
    guard = uat.CallerOwnedConnectionGuard(raw)
    assert guard.cursor("x", cursor_factory="y") == (("x",), {"cursor_factory": "y"})
    for method in (guard.commit, guard.rollback, guard.close):
        with pytest.raises(uat.TransactionOwnershipError):
            method()
    assert guard.transaction_calls == {"commit": 1, "rollback": 1, "close": 1}
    assert raw.commit_calls == raw.rollback_calls == raw.close_calls == 0


def test_all_four_business_entries_receive_guard_and_do_not_own_transaction():
    raw = RawConnection()
    observed = []

    def entry(**kwargs):
        observed.append(kwargs["connection"])
        return {}

    counts = uat.exercise_caller_owned_entries(
        raw,
        review_fact=entry,
        review_event=entry,
        review_expectation_monitor=entry,
        run_batch_score=entry,
    )
    assert len(observed) == 4
    assert len({id(value) for value in observed}) == 1
    assert all(isinstance(value, uat.CallerOwnedConnectionGuard) for value in observed)
    assert counts == {"commit": 0, "rollback": 0, "close": 0}


def test_synthetic_scope_has_exactly_one_outer_rollback_on_success():
    raw = RawConnection()
    value = uat.run_synthetic_transaction(raw, lambda guard: ("ok", guard.raw is raw))
    assert value == ("ok", True)
    assert raw.commit_calls == 0
    assert raw.rollback_calls == 1
    assert raw.close_calls == 1


def test_synthetic_scope_rolls_back_but_preserves_original_error():
    raw = RawConnection()

    def fail(_guard):
        raise RuntimeError("original synthetic failure")

    with pytest.raises(RuntimeError, match="original synthetic failure"):
        uat.run_synthetic_transaction(raw, fail)
    assert raw.rollback_calls == 1
    assert raw.close_calls == 1


def test_approved_only_score_rejects_pending_ids_and_changed_gates():
    baseline = {"m1": {"evidence_level": "E2", "af_level": "AF0", "pool_code": None, "blocking_gate": "axis_flux_af0"}}
    same = json.loads(json.dumps(baseline))
    uat.assert_approved_only_score_isolation(
        baseline=baseline,
        after_collect=same,
        score_result={"results": [{"evidence_ids": ["old-approved"]}]},
        pending_ids={"new-pending"},
        transitions=[{"trigger_evidence_ids": ["old-approved"]}],
    )
    with pytest.raises(uat.UATAssertionError, match="pending"):
        uat.assert_approved_only_score_isolation(
            baseline=baseline,
            after_collect=same,
            score_result={"results": [{"evidence_ids": ["new-pending"]}]},
            pending_ids={"new-pending"},
            transitions=[],
        )


def test_no_lookahead_requires_publish_and_review_cutoff_independently():
    uat.assert_no_lookahead(
        historical_visible_ids=set(),
        review_date_visible_ids={"reviewed-later"},
        reviewed_later_id="reviewed-later",
        published_later_id="published-later",
    )
    with pytest.raises(uat.UATAssertionError, match="publish"):
        uat.assert_no_lookahead(
            historical_visible_ids={"published-later"},
            review_date_visible_ids={"reviewed-later"},
            reviewed_later_id="reviewed-later",
            published_later_id="published-later",
        )


def test_review_date_comes_only_from_timezone_aware_postgres_value():
    reviewed_at = datetime(2026, 7, 12, 17, 30, tzinfo=timezone.utc)
    assert uat.synthetic_score_date(reviewed_at) == date(2026, 7, 13)
    with pytest.raises(uat.UATAssertionError, match="timezone-aware"):
        uat.synthetic_score_date(datetime(2026, 7, 12, 17, 30))


def test_metadata_roundtrip_checks_three_business_fields_and_collection_job_id():
    expected = {
        "application_domain": "robot_wrist",
        "installation_position": "wrist_joint",
        "uat_run_id": "uat-task10-run",
    }
    stored = {**expected, "collection_job_id": "uat-task10-run", "db_extra": "allowed"}
    uat.assert_synthetic_metadata(stored, expected, job_id="uat-task10-run")
    with pytest.raises(uat.UATAssertionError):
        uat.assert_synthetic_metadata(
            {**stored, "collection_job_id": "wrong"}, expected, job_id="uat-task10-run"
        )


def test_result_document_has_all_required_sections_and_four_pool_keys():
    result = uat.build_result_document(
        status="PASS_WITH_LIMITATIONS",
        assertions={"A01": {"passed": True, "evidence": "fixed plan"}},
        pool_counts={"D": 2},
        limitations=["official source unavailable"],
    )
    assert tuple(result) == uat.RESULT_SECTIONS
    assert result["score_before_review"]["pool_counts"] == {"A": 0, "B": 0, "C": 0, "D": 2}
    assert result["identity"]["as_of_date"] == "2026-07-09"
    assert result["preflight"]["model_stage"] == "staging"
    assert "不构成自动买入" in result["limitations"][-1]


def _complete_assertions():
    return {
        assertion_id: {"passed": True, "evidence": f"evidence-{assertion_id}"}
        for assertion_id in uat.REQUIRED_ASSERTION_IDS
    }


def _complete_result():
    result = uat.build_result_document(
        status="PASS", assertions=_complete_assertions(), pool_counts={}, limitations=[]
    )
    result["count_snapshots"] = {
        name: {field: 0 for field in uat.SNAPSHOT_FIELDS}
        for name in uat.SNAPSHOT_NAMES
    }
    for section in uat.REQUIRED_EVIDENCE_SECTIONS:
        result[section] = {"evidence": "verified"}
    result["preflight"] = {
        "database_revision": "033",
        "model_stage": "staging",
        "evidence": "verified",
    }
    return result


def test_final_result_validator_rejects_empty_or_incomplete_pass_payload():
    empty = uat.build_result_document(
        status="PASS", assertions={}, pool_counts={}, limitations=[]
    )
    with pytest.raises(uat.UATAssertionError, match="assertions"):
        uat.validate_final_result(empty)

    complete = uat.build_result_document(
        status="PASS_WITH_LIMITATIONS",
        assertions=_complete_assertions(),
        pool_counts={},
        limitations=["source unavailable"],
    )
    complete["count_snapshots"] = {
        name: {field: 0 for field in uat.SNAPSHOT_FIELDS}
        for name in uat.SNAPSHOT_NAMES
    }
    for section in uat.REQUIRED_EVIDENCE_SECTIONS:
        complete[section] = {"evidence": "checked"}
    complete["preflight"].update(database_revision="033", model_stage="staging")
    uat.validate_final_result(complete)


def test_final_validator_requires_exact_revision_and_staging_not_none():
    for field, value in (("database_revision", None), ("model_stage", None)):
        result = _complete_result()
        result["preflight"][field] = value
        with pytest.raises(uat.UATAssertionError):
            uat.validate_final_result(result)


def test_recursive_sensitive_scan_catches_nested_credentials():
    with pytest.raises(uat.UATAssertionError, match="sensitive"):
        uat.assert_no_sensitive_output(
            {"safe": [{"nested": "postgresql://u:secret@localhost:6432/kronos"}]}
        )
    with pytest.raises(uat.UATAssertionError):
        uat.assert_no_sensitive_output({"token": "not configured"})
    with pytest.raises(uat.UATAssertionError):
        uat.assert_no_sensitive_output({"url": "https://x.test/a?X-Amz-Signature=abc"})
    with pytest.raises(uat.UATAssertionError):
        uat.assert_no_sensitive_output({"header": "Authorization: Bearer abc"})
    uat.assert_no_sensitive_output({"host": "localhost:6432", "token": "<redacted>"})


@pytest.mark.parametrize(
    "key",
    ("db_password", "api_token_value", "authorization_header", "cookie_value"),
)
def test_sensitive_scan_rejects_composite_sensitive_key_components(key):
    with pytest.raises(uat.UATAssertionError, match="sensitive key"):
        uat.assert_no_sensitive_output({key: "plaintext-secret"})


def test_unrestricted_axial_normalization_accepts_real_raw_document_and_proposes():
    document = RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="机器人腕部轴向磁通电机产品规格",
        content_text="公司发布机器人腕部轴向磁通电机产品规格。",
        company_code="688001",
        company_name="测试公司",
        publish_time="2026-07-08T10:00:00+08:00",
        doc_type="announcement",
        metadata={"application_domain": "robot_wrist"},
    )
    records = uat.normalize_unrestricted_discovery_documents([document])
    requirement = {
        "chain_id": "dexterous_hand",
        "requirement_id": "dexterous_axial_flux_motor",
        "node_id": "dexterous_hand_foundation",
        "business_keywords": ["轴向磁通电机"],
        "product_terms": ["轴向磁通电机"],
        "scene_terms": ["机器人腕部"],
        "negative_examples": ["轮毂", "航空"],
        "require_product_and_scene": True,
        "independent_discovery": True,
        "technology_route_id": "dexterous_axial_flux_motor",
    }
    hits = uat.propose_axial_candidates(records, requirement=requirement)
    assert records[0]["doc_id"] == document.doc_id
    assert records[0]["company_code"] == "688001"
    assert len(hits) == 1
    assert hits[0].eligible_for_mapping is True


def test_default_axial_discovery_core_normalizes_real_adapter_raw_document(monkeypatch):
    import run_supply_chain_evidence_orchestration as run_cli_module

    requirement = {
        "chain_id": "dexterous_hand",
        "requirement_id": "dexterous_axial_flux_motor",
        "node_id": "dexterous_hand_foundation",
        "business_keywords": ["轴向磁通电机"],
        "product_terms": ["轴向磁通电机"],
        "scene_terms": ["机器人腕部"],
        "negative_examples": ["轮毂", "航空"],
        "require_product_and_scene": True,
        "independent_discovery": True,
        "technology_route_id": "dexterous_axial_flux_motor",
    }
    document = RawDocument(
        source_id="cninfo_announcement",
        source_level="strong",
        title="机器人腕部轴向磁通电机产品规格",
        content_text="公司发布机器人腕部轴向磁通电机产品规格。",
        company_code="688001",
        publish_time="2026-07-08T10:00:00+08:00",
        metadata={"application_domain": "robot_wrist"},
    )

    class Repository:
        def __init__(self):
            self.persisted = []

        def fetch_independent_discovery_requirements(self, _chain_id):
            return [requirement]

        def fetch_candidate_universe(self, *_args):
            return []

        def fetch_discovery_seed_companies(self, *_args):
            return ["688001"]

        def start_job(self, _request):
            return "job-1"

        def persist_discovery_hit(self, hit, *, job_id):
            self.persisted.append((hit, job_id))
            return SimpleNamespace(
                inserted=True,
                duplicate=False,
                validation_status="pending",
                proposal=hit.proposal,
            )

        def upsert_candidate_mapping(self, _proposal):
            return None

        def finish_job(self, *_args):
            return None

    repository = Repository()
    adapter = SimpleNamespace(
        collect=lambda *_args, **_kwargs: AdapterResult(
            (document,), (), (), "success", 1
        )
    )
    monkeypatch.setattr(
        run_cli_module,
        "build_runtime_dependencies",
        lambda _args: {
            "repository": repository,
            "official_discovery_adapter": adapter,
        },
    )
    runtime = uat.DefaultUATRuntime.__new__(uat.DefaultUATRuntime)
    runtime.inputs = uat.ValidatedUATInputs(
        pg_url="postgresql://localhost:6432/kronos",
        output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
    )
    result = runtime.axial_discovery()
    assert result["hits"] == 1
    assert result["pending"] == 1
    assert repository.persisted[0][0].company_code == "688001"


def test_markdown_is_pending_safe_and_declares_staging_limitations():
    result = uat.build_result_document(
        status="PASS",
        assertions={},
        pool_counts={},
        limitations=[],
    )
    report = uat.render_uat_markdown(result)
    for heading in ("已审核事实", "待审核事实", "已拒绝事实", "证据缺口", "下一步行动", "8 层 × 8 维矩阵", "A/B/C/D 四池", "AF 独立搜索"):
        assert heading in report
    assert "模型仍为 staging" in report
    assert "不具有投资有效性" in report


def test_failure_exit_semantics_never_return_zero_or_leak_dsn(capsys):
    dsn = "postgresql://u:secret@localhost:6432/kronos"
    code = uat.run_cli(
        [
            "--pg-url", dsn,
            "--chain-id", "dexterous_hand",
            "--as-of-date", "2026-07-09",
            "--output-dir", str(EXPECTED_OUTPUT),
        ],
        connector=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(f"cannot connect {dsn}")),
    )
    assert code != 0
    assert "secret" not in capsys.readouterr().err


def test_preflight_rejects_wrong_revision_missing_company_and_non_staging_model():
    base = uat.PreflightEvidence(
        database_revision="033",
        required_objects_missing=(),
        company_mapping_codes=uat.REAL_COMPANY_CODES,
        invalid_confirmed_facts=0,
        invalid_approved_events=0,
        invalid_approved_monitors=0,
        invalid_approved_stages=0,
        model_stage="staging",
        offline_head="033",
    )
    uat.assert_preflight(base)
    for changed in (
        {"database_revision": "032"},
        {"offline_head": "032"},
        {"company_mapping_codes": uat.REAL_COMPANY_CODES[:-1]},
        {"model_stage": "production"},
        {"invalid_confirmed_facts": 1},
    ):
        with pytest.raises(uat.UATAssertionError):
            uat.assert_preflight(SimpleNamespace(**{**vars(base), **changed}))


def test_offline_alembic_head_must_parse_exact_033():
    completed = SimpleNamespace(returncode=0, stdout="033 (head)\n", stderr="")
    assert uat.verify_offline_alembic_head(runner=lambda *args, **kwargs: completed) == "033"
    with pytest.raises(uat.UATAssertionError):
        uat.verify_offline_alembic_head(
            runner=lambda *args, **kwargs: SimpleNamespace(
                returncode=0, stdout="032 (head)\n", stderr=""
            )
        )


class PreflightCursor:
    def __init__(self):
        self.executed = []
        self.current = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.current = " ".join(sql.split())
        self.executed.append((self.current, params))

    def fetchone(self):
        if "FROM alembic_version" in self.current:
            return ("033",)
        if "AS missing_objects" in self.current:
            return {"missing_objects": []}
        if "invalid_confirmed_facts" in self.current:
            return {
                "invalid_confirmed_facts": 0,
                "invalid_approved_events": 0,
                "invalid_approved_monitors": 0,
                "invalid_approved_stages": 0,
            }
        if "FROM model_registry" in self.current:
            return ("staging",)
        raise AssertionError(self.current)

    def fetchall(self):
        if "split_part(code" in self.current:
            return [(code,) for code in uat.REAL_COMPANY_CODES]
        raise AssertionError(self.current)


class PreflightConnection:
    def __init__(self):
        self.value = PreflightCursor()

    def cursor(self, **_kwargs):
        return self.value


def test_real_preflight_query_uses_revision_033_objects_audit_and_correct_model_id():
    connection = PreflightConnection()
    evidence = uat.collect_preflight_evidence(connection, offline_head="033")
    uat.assert_preflight(evidence)
    combined = "\n".join(sql for sql, _params in connection.value.executed)
    assert "guard_supply_chain_manual_review" in combined
    for trigger in uat.REQUIRED_REVIEW_TRIGGERS:
        assert trigger in combined
    assert "public.guard_supply_chain_manual_review" in combined
    assert "tgenabled" in combined
    assert "public" in combined
    assert "id = %s" in combined
    assert "model_name" not in combined
    model_query = next(item for item in connection.value.executed if "FROM model_registry" in item[0])
    assert model_query[1] == ("supply_chain_research_selection_v2",)


class StateCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.sql, self.params = sql, params

    def fetchall(self):
        return [
            {
                "code": code,
                "confirmed_fact_ids": [f"fact-{code}"],
                "approved_event_ids": [],
                "approved_monitor_ids": [],
                "approved_stage_ids": [],
            }
            for code in uat.REAL_COMPANY_CODES
        ]


def test_real_company_review_scope_snapshot_is_complete_and_read_only():
    connection = SimpleNamespace(cursor=lambda **_kwargs: StateCursor())
    state = uat.capture_real_company_review_state(connection)
    assert tuple(state) == uat.REAL_COMPANY_CODES
    assert state["003021"]["confirmed_fact_ids"] == ("fact-003021",)


class FakeUATRuntime:
    def __init__(self):
        self.calls = []
        self.collect_count = 0
        self.scope_call_count = 0
        self.review_state = {
            code: {
                "confirmed_fact_ids": (f"approved-{code}",),
                "approved_event_ids": (),
                "approved_monitor_ids": (),
                "approved_stage_ids": (),
            }
            for code in uat.REAL_COMPANY_CODES
        }
        self.scope_ids = {
            "mapping_ids": ("real-mapping",),
            "document_ids": ("DOC-new",),
            "fact_ids": ("FACT-new",),
            "event_ids": ("EV-new",),
            "pending_ids": ("FACT-new", "EV-new"),
        }

    def preflight(self):
        self.calls.append("preflight")
        return uat.PreflightEvidence(
            "033", (), uat.REAL_COMPANY_CODES, 0, 0, 0, 0, "staging", "033"
        )

    def snapshot(self, name):
        self.calls.append(f"snapshot:{name}")
        counts = {field: 0 for field in uat.SNAPSHOT_FIELDS}
        if name not in {"before", "after_dry_run"}:
            counts.update(
                raw_evidence_documents=1,
                evidence_extracted_facts=1,
                business_tag_evidence_events=1,
            )
        return uat.CountSnapshot(name, counts)

    def real_review_state(self):
        self.calls.append("real_review_state")
        return self.review_state

    def orchestrate(self, *, mode, source_policy, allow_score):
        self.calls.append(f"orchestrate:{mode}:{source_policy}:{allow_score}")
        if mode == "dry-run":
            return {
                "writes": 0,
                "network_requests": 0,
                "inserted_documents": 0,
                "duplicate_documents": 0,
                "pending_facts": 0,
                "failed_tasks": (),
                "data_limitations": (),
                "companies": (),
            }
        self.collect_count += 1
        return {
            "writes": 4 if self.collect_count == 1 else 2,
            "network_requests": 1,
            "inserted_documents": 1 if self.collect_count == 1 else 0,
            "duplicate_documents": 0 if self.collect_count == 1 else 1,
            "pending_facts": 1,
            "approved_facts": 0,
            "failed_tasks": ("official-ir",),
            "data_limitations": ("adapter_error:official source unavailable",),
            "official_discovery_hits": 0,
            "companies": (),
        }

    def axial_discovery(self):
        self.calls.append("axial_discovery")
        return {
            "scope": "unrestricted_candidate_universe",
            "requirement_id": "dexterous_axial_flux_motor",
            "seed_company_codes": ("688001",),
            "hits": 0,
            "excluded": 0,
            "pending": 0,
            "inserted_documents": 0,
            "duplicate_documents": 0,
            "failed_tasks": (),
            "data_limitations": (),
        }

    def render_report(self, result):
        self.calls.append("render_report")
        return "# Task7 evidence report\n\n## 待审核事实\n"

    def score(self, *, dry_run):
        self.calls.append(f"score:{dry_run}")
        return {
            "mapping_count": 1,
            "pool_counts": {"D": 1},
            "transitions": 0,
            "results": [
                {
                    "mapping_id": "real-mapping",
                    "evidence_ids": ["approved-003021"],
                    "evidence_gate": {"level": "E2"},
                    "route_gate": {"level": "AF0"},
                    "selection": {
                        "pool_code": "D",
                        "blocking_gate": None,
                        "detail": {
                            "selection_context": {
                                "market_expectation_score": None,
                                "expectation_gap_score": None,
                                "catalyst_score": None,
                                "risk_score": None,
                            }
                        },
                    },
                    "benefit": {"detail": {"node_attractiveness": None}},
                    "data_limitations": [
                        "missing_market_expectation_score",
                        "missing_expectation_gap_score",
                        "missing_catalyst_score",
                        "missing_risk_score",
                        "missing_node_score",
                        "unaudited_commercial_stage",
                    ],
                }
            ],
        }

    def scoped_ids(self):
        self.calls.append("scoped_ids")
        self.scope_call_count += 1
        if self.scope_call_count == 1:
            return {
                "mapping_ids": ("real-mapping",),
                "document_ids": (),
                "fact_ids": (),
                "event_ids": (),
                "pending_ids": (),
            }
        return self.scope_ids

    def transitions(self):
        return []

    def run_regressions(self):
        self.calls.append("run_regressions")
        return {"passed": True, "command": "focused pytest", "summary": "202 passed"}

    def git_staged_check(self):
        self.calls.append("git_staged_check")
        return {"passed": True, "staged_files": []}

    def synthetic(self):
        self.calls.append("synthetic")
        inside = {field: 0 for field in uat.SNAPSHOT_FIELDS}
        inside.update(
            raw_evidence_documents=2,
            evidence_extracted_facts=3,
            business_tag_evidence_events=3,
        )
        return {
            "synthetic_ids": {
                "run_id": "uat-task10-run",
                "mapping_id": "uat-task10-mapping",
                "doc_id": "uat-task10-doc",
                "fact_id": "FACT-derived",
                "event_id": "EV-derived",
                "monitor_id": "uat-task10-monitor",
            },
            "derived_id_design_deviation": "repository forces FACT-/EV- IDs; exact IDs tracked",
            "pending_metadata_round_trip": True,
            "pending_route_level": "AF0",
            "reviewed_at": "2026-07-12T10:00:00+00:00",
            "review_date": "2026-07-12",
            "future_publish_date": "2026-07-13",
            "approved_route_level": "AF2",
            "route_max_pool": "C",
            "matched_fact_ids": ["FACT-derived"],
            "historical_visible_ids": [],
            "review_date_visible_ids": ["FACT-derived"],
            "future_fact_id": "FACT-future",
            "direct_guard_error": "confirmed supply-chain fact requires audited manual review",
            "savepoint_recovered": True,
            "markers_restored": True,
            "original_marker": "preexisting",
            "restored_marker": "preexisting",
            "transaction_calls": {"commit": 0, "rollback": 0, "close": 0},
            "outer_rollback_calls": 1,
            "cleanup_counts": {table: 0 for table in uat.SYNTHETIC_CLEANUP_TABLES},
            "inside_snapshot": inside,
        }


def test_default_executor_contract_runs_every_phase_and_builds_evidenced_result():
    runtime = FakeUATRuntime()
    inputs = uat.ValidatedUATInputs(
        pg_url="postgresql://localhost:6432/kronos",
        output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
    )
    result = uat.execute_uat(inputs, runtime=runtime)
    uat.validate_execution_result(result)
    assert result["assertions"]["G01"]["passed"] is False
    assert result["status"] == "PASS_WITH_LIMITATIONS"
    assert result["collect_2"]["inserted_documents"] == 0
    assert result["score_before_review"]["pool_counts"] == {"A": 0, "B": 0, "C": 0, "D": 1}
    assert result["synthetic_review"]["derived_id_design_deviation"]
    assert result["preflight"]["model_stage_after"] == "staging"
    assert runtime.calls.count("preflight") == 2
    assert "render_report" in runtime.calls
    assert runtime.calls.index("orchestrate:dry-run:local-first:False") < runtime.calls.index("orchestrate:collect:official-gap:False")
    assert runtime.calls.count("orchestrate:collect:official-gap:False") == 2
    assert runtime.calls.count("axial_discovery") == 2
    assert result["assertions"]["G06"]["evidence"]["summary"] == "202 passed"
    assert result["assertions"]["G07"]["evidence"]["staged_files"] == []
    assert result["assertions"]["A01"]["evidence"] != result["assertions"]["A02"]["evidence"]


def test_executor_fails_if_second_collect_is_not_idempotent():
    runtime = FakeUATRuntime()
    original = runtime.scoped_ids
    calls = 0

    def unstable_ids():
        nonlocal calls
        calls += 1
        value = dict(original())
        if calls == 3:
            value["fact_ids"] = ("FACT-new", "FACT-unstable")
        return value

    runtime.scoped_ids = unstable_ids
    inputs = uat.ValidatedUATInputs(
        pg_url="postgresql://localhost:6432/kronos",
        output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
    )
    with pytest.raises(uat.UATAssertionError, match="idempot"):
        uat.execute_uat(inputs, runtime=runtime)


def test_default_runtime_request_matches_real_event_contract_and_fixed_scope():
    request = uat.build_runtime_request(
        mode="collect", source_policy="official-gap", allow_score=False
    )
    assert request.company_codes == uat.REAL_COMPANY_CODES
    assert request.mapping_ids == ()
    assert request.source_limits == {
        "discovery": 500,
        "official_discovery_documents": 20,
        "official_discovery_companies": 20,
        "official_pages_per_company": 3,
        "mapped_official_tasks": 50,
        "mapped_cninfo_documents_per_task": 20,
    }


def test_default_executor_constructs_real_runtime_adapter(monkeypatch):
    inputs = uat.ValidatedUATInputs(
        pg_url="postgresql://localhost:6432/kronos",
        output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
    )
    connection = object()
    runtime = object()
    monkeypatch.setattr(uat, "DefaultUATRuntime", lambda actual_inputs, actual_connection: runtime)
    monkeypatch.setattr(
        uat,
        "execute_uat",
        lambda actual_inputs, *, runtime: {"inputs": actual_inputs, "runtime": runtime},
    )
    result = uat._default_executor(inputs, connection)
    assert result == {"inputs": inputs, "runtime": runtime}


def test_default_regressions_run_three_isolated_pytest_groups(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="10 passed in 1.0s\n", stderr="")

    monkeypatch.setattr(uat.subprocess, "run", fake_run)
    runtime = uat.DefaultUATRuntime.__new__(uat.DefaultUATRuntime)
    evidence = runtime.run_regressions()
    assert evidence["passed"] is True
    assert len(calls) == 3
    assert all(command[:3] == ["bash", "tools/codex-lowio.sh", "py"] for command in calls)
    assert evidence["passed_count"] == 30


def test_git_stage_check_requires_completely_empty_index(monkeypatch):
    monkeypatch.setattr(
        uat.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="docs/unrelated.md\n", stderr=""
        ),
    )
    runtime = uat.DefaultUATRuntime.__new__(uat.DefaultUATRuntime)
    evidence = runtime.git_staged_check()
    assert evidence["passed"] is False
    assert evidence["staged_files"] == ["docs/unrelated.md"]


def test_cli_executor_none_uses_default_and_writes_three_artifact_contract(monkeypatch):
    calls = []
    connection = SimpleNamespace(close=lambda: calls.append("close"))
    result = _complete_result()
    monkeypatch.setattr(
        uat,
        "_default_executor",
        lambda inputs, active: calls.append(("execute", inputs, active)) or result,
    )
    monkeypatch.setattr(
        uat,
        "write_uat_outputs",
        lambda output, payload: calls.append(("write", output, payload)),
    )
    code = uat.run_cli(
        [
            "--pg-url", "postgresql://localhost:6432/kronos",
            "--chain-id", "dexterous_hand",
            "--as-of-date", "2026-07-09",
            "--output-dir", str(EXPECTED_OUTPUT),
        ],
        connector=lambda *_args, **_kwargs: connection,
    )
    assert code == 0
    assert calls[0][0] == "execute"
    assert calls[1][0] == "write"
    assert calls[2] == "close"


def test_write_outputs_validates_and_creates_json_report_and_qa(tmp_path):
    output = tmp_path / "out"
    qa = tmp_path / "qa.md"
    result = _complete_result()
    result["assertions"]["G01"] = {
        "passed": False,
        "evidence": {"state": "pending_artifact_write_and_readback"},
    }
    uat.write_uat_outputs(output, result, qa_path=qa)
    payload = json.loads((output / "result.json").read_text())
    assert payload["status"] == "PASS"
    assert payload["assertions"]["G01"]["passed"] is True
    assert "模型仍为 staging" in (output / "report.md").read_text()
    assert "UAT QA" in qa.read_text()


def test_synthetic_cleanup_contract_includes_source_catalog_and_task7_report():
    assert "evidence_source_catalog" in uat.SYNTHETIC_CLEANUP_TABLES
    runtime = FakeUATRuntime()
    inputs = uat.ValidatedUATInputs(
        pg_url="postgresql://localhost:6432/kronos",
        output_dir=uat.REPO_ROOT / EXPECTED_OUTPUT,
    )
    result = uat.execute_uat(inputs, runtime=runtime)
    report = uat.render_uat_markdown(result)
    assert "# Task7 evidence report" in report
