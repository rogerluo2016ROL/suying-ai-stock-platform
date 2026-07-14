#!/usr/bin/env python3
"""Safety-first PostgreSQL UAT harness for dexterous-hand evidence orchestration.

The fixed identity and pure contract helpers are intentionally separated from
the database execution boundary.  Invalid input is rejected before a socket is
opened, and synthetic writes are always owned by one outer transaction.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import uuid
from zoneinfo import ZoneInfo


CHAIN_ID = "dexterous_hand"
REPO_ROOT = Path(__file__).resolve().parents[1]
AS_OF_DATE = date(2026, 7, 9)
TIMEZONE = "Asia/Shanghai"
MODEL_VERSION = "v2.0"
DATABASE_REVISION = "033"
REAL_COMPANY_CODES = ("003021", "300007", "300660", "603662", "603728")
MODEL_REGISTRY_ID = "supply_chain_research_selection_v2"
REQUIRED_REVIEW_TRIGGERS = (
    "trg_supply_chain_manual_review_fact",
    "trg_supply_chain_manual_review_event",
    "trg_supply_chain_manual_review_expectation",
    "trg_supply_chain_manual_review_stage",
)
FIXED_OUTPUT_DIR = Path("outputs/supply_chain_evidence/dexterous_hand/2026-07-09")
FIXED_QA_PATH = REPO_ROOT / "docs/qa/supply-chain-evidence-orchestration-uat-2026-07-12.md"
PLAN_STEPS = (
    "preflight",
    "dry_run",
    "collect",
    "collect_idempotency",
    "score_before_review",
    "synthetic_review_rollback",
    "report",
)
SNAPSHOT_FIELDS = (
    "raw_evidence_documents",
    "evidence_extracted_facts",
    "business_tag_evidence_events",
    "evidence_gaps",
    "business_tag_authenticity_scores",
    "business_tag_operating_quality_scores",
    "business_tag_benefit_scores",
    "business_tag_selection_scores",
    "business_tag_pool_state",
    "business_tag_pool_transition_log",
    "evidence_collection_jobs",
)
SNAPSHOT_NAMES = (
    "before",
    "after_dry_run",
    "after_collect_1",
    "after_collect_2",
    "after_real_score",
    "inside_synthetic_before_rollback",
    "after_synthetic_rollback",
)
RESULT_SECTIONS = (
    "status",
    "identity",
    "preflight",
    "count_snapshots",
    "dry_run",
    "collect_1",
    "collect_2",
    "real_company_review_status",
    "score_before_review",
    "axial_flux_discovery",
    "synthetic_review",
    "direct_approval_guard",
    "no_lookahead",
    "transaction_boundary",
    "rollback_cleanup",
    "limitations",
    "assertions",
)
REQUIRED_ASSERTION_IDS = tuple(
    f"{group}{number:02d}"
    for group, maximum in (
        ("A", 4), ("B", 7), ("C", 7), ("D", 5), ("E", 8), ("F", 9), ("G", 7)
    )
    for number in range(1, maximum + 1)
)
REQUIRED_EVIDENCE_SECTIONS = (
    "preflight",
    "dry_run",
    "collect_1",
    "collect_2",
    "real_company_review_status",
    "score_before_review",
    "axial_flux_discovery",
    "synthetic_review",
    "direct_approval_guard",
    "no_lookahead",
    "transaction_boundary",
    "rollback_cleanup",
)
SYNTHETIC_CLEANUP_TABLES = (
    "evidence_source_catalog",
    "business_tag_mapping",
    "raw_evidence_documents",
    "evidence_extracted_facts",
    "business_tag_evidence_events",
    "business_tag_expectation_monitor",
    "business_tag_stage_tracking",
    "business_tag_authenticity_scores",
    "business_tag_operating_quality_scores",
    "business_tag_benefit_scores",
    "business_tag_selection_scores",
    "business_tag_pool_state",
    "business_tag_pool_transition_log",
)


class UATContractError(ValueError):
    """The fixed UAT identity or an execution prerequisite was violated."""


class UATAssertionError(AssertionError):
    """A safety or evidence assertion failed."""


class TransactionOwnershipError(UATAssertionError):
    """A business entry attempted to own the caller's transaction."""


@dataclass(frozen=True)
class UATPlan:
    chain_id: str
    as_of_date: date
    company_codes: tuple[str, ...] = REAL_COMPANY_CODES
    steps: tuple[str, ...] = PLAN_STEPS
    real_fact_review_mode: str = "read_only"
    synthetic_review_rollback: bool = True
    synthetic_score_date_policy: str = "reviewed_at_date"


@dataclass(frozen=True)
class ValidatedUATInputs:
    pg_url: str = field(repr=False)
    chain_id: str = CHAIN_ID
    as_of_date: date = AS_OF_DATE
    output_dir: Path = FIXED_OUTPUT_DIR


@dataclass(frozen=True)
class CountSnapshot:
    name: str
    counts: dict[str, int]


@dataclass(frozen=True)
class PreflightEvidence:
    database_revision: str
    required_objects_missing: tuple[str, ...]
    company_mapping_codes: tuple[str, ...]
    invalid_confirmed_facts: int
    invalid_approved_events: int
    invalid_approved_monitors: int
    invalid_approved_stages: int
    model_stage: str | None
    offline_head: str | None


def build_uat_plan(chain_id: str, as_of_date: date) -> UATPlan:
    if chain_id != CHAIN_ID or as_of_date != AS_OF_DATE:
        raise UATContractError("Task 10 UAT identity must be dexterous_hand/2026-07-09")
    return UATPlan(chain_id=chain_id, as_of_date=as_of_date)


def validate_uat_inputs(
    *, pg_url: str, chain_id: str, as_of_date: str, output_dir: str | Path
) -> ValidatedUATInputs:
    if not str(pg_url or "").strip():
        raise UATContractError("--pg-url is required")
    try:
        dsn = urlsplit(str(pg_url))
        port = dsn.port
    except ValueError as exc:
        raise UATContractError("--pg-url is not a valid PostgreSQL URL") from exc
    if dsn.scheme not in {"postgres", "postgresql"}:
        raise UATContractError("--pg-url must use postgres/postgresql scheme")
    if dsn.hostname not in {"localhost", "127.0.0.1"}:
        raise UATContractError("--pg-url host must be localhost or 127.0.0.1")
    if port != 6432:
        raise UATContractError("--pg-url port must be 6432")
    if dsn.path != "/kronos":
        raise UATContractError("--pg-url database must be kronos")
    if Path.cwd().resolve() != REPO_ROOT:
        raise UATContractError(f"working directory must be repository root {REPO_ROOT}")
    try:
        parsed_date = date.fromisoformat(as_of_date)
    except (TypeError, ValueError) as exc:
        raise UATContractError("--as-of-date must use YYYY-MM-DD") from exc
    build_uat_plan(chain_id, parsed_date)
    actual = Path(output_dir).expanduser().resolve()
    expected = (REPO_ROOT / FIXED_OUTPUT_DIR).resolve()
    if actual != expected:
        raise UATContractError(f"--output-dir must resolve to {expected}")
    return ValidatedUATInputs(
        pg_url=str(pg_url), chain_id=chain_id, as_of_date=parsed_date, output_dir=actual
    )


def _redacted_dsn(pg_url: str) -> str:
    try:
        parsed = urlsplit(pg_url)
    except ValueError:
        return "<redacted-pg-url>"
    if not parsed.scheme or not parsed.hostname:
        return "<redacted-pg-url>"
    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def sanitize_diagnostic(error: BaseException | str, *, pg_url: str) -> str:
    text = str(error).replace(pg_url, _redacted_dsn(pg_url))
    try:
        parsed = urlsplit(pg_url)
        if parsed.password:
            text = text.replace(parsed.password, "<redacted>")
    except ValueError:
        pass
    patterns = (
        r"(?i)(token|api[_-]?key|cookie|authorization)\s*[=:]\s*[^\s;&]+",
        r"(?i)(password|passwd|pwd)\s*[=:]\s*[^\s;&]+",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: f"{m.group(1)}=<redacted>", text)
    return " ".join(text.splitlines())


_SNAPSHOT_SQL = """
SELECT
  (SELECT count(*) FROM raw_evidence_documents) AS raw_evidence_documents,
  (SELECT count(*) FROM evidence_extracted_facts) AS evidence_extracted_facts,
  (SELECT count(*) FROM business_tag_evidence_events) AS business_tag_evidence_events,
  (SELECT COALESCE(sum(CASE WHEN jsonb_typeof(l1_l8_path->'evidence_gaps') = 'array'
      THEN jsonb_array_length(l1_l8_path->'evidence_gaps') ELSE 0 END), 0)
     FROM business_tag_mapping) AS evidence_gaps,
  (SELECT count(*) FROM business_tag_authenticity_scores) AS business_tag_authenticity_scores,
  (SELECT count(*) FROM business_tag_operating_quality_scores) AS business_tag_operating_quality_scores,
  (SELECT count(*) FROM business_tag_benefit_scores) AS business_tag_benefit_scores,
  (SELECT count(*) FROM business_tag_selection_scores) AS business_tag_selection_scores,
  (SELECT count(*) FROM business_tag_pool_state) AS business_tag_pool_state,
  (SELECT count(*) FROM business_tag_pool_transition_log) AS business_tag_pool_transition_log,
  (SELECT count(*) FROM evidence_collection_jobs) AS evidence_collection_jobs
"""


def capture_count_snapshot(connection: Any, name: str) -> CountSnapshot:
    if name not in SNAPSHOT_NAMES:
        raise UATContractError(f"unsupported snapshot name: {name}")
    with connection.cursor() as cur:
        cur.execute(_SNAPSHOT_SQL)
        row = cur.fetchone()
    if row is None:
        raise UATAssertionError("count snapshot query returned no row")
    if not isinstance(row, Mapping):
        row = dict(zip(SNAPSHOT_FIELDS, row, strict=True))
    counts = {field: int(row[field]) for field in SNAPSHOT_FIELDS}
    return CountSnapshot(name=name, counts=counts)


class CallerOwnedConnectionGuard:
    """Proxy that lets business code use cursors but forbids transaction ownership."""

    def __init__(self, raw: Any):
        object.__setattr__(self, "raw", raw)
        object.__setattr__(self, "transaction_calls", {"commit": 0, "rollback": 0, "close": 0})

    def cursor(self, *args: Any, **kwargs: Any) -> Any:
        return self.raw.cursor(*args, **kwargs)

    def _forbidden(self, method: str) -> None:
        self.transaction_calls[method] += 1
        raise TransactionOwnershipError(
            f"caller-owned connection forbids business {method}()"
        )

    def commit(self) -> None:
        self._forbidden("commit")

    def rollback(self) -> None:
        self._forbidden("rollback")

    def close(self) -> None:
        self._forbidden("close")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"raw", "transaction_calls"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self.raw, name, value)


def exercise_caller_owned_entries(
    raw_connection: Any,
    *,
    review_fact: Callable[..., Any],
    review_event: Callable[..., Any],
    review_expectation_monitor: Callable[..., Any],
    run_batch_score: Callable[..., Any],
) -> dict[str, int]:
    """Contract probe used before real synthetic records are created."""
    guard = CallerOwnedConnectionGuard(raw_connection)
    review_fact(connection=guard)
    review_event(connection=guard)
    review_expectation_monitor(connection=guard)
    run_batch_score(connection=guard)
    return dict(guard.transaction_calls)


def run_synthetic_transaction(raw_connection: Any, operation: Callable[[Any], Any]) -> Any:
    """Run one synthetic operation with exactly one caller-owned rollback."""
    if bool(getattr(raw_connection, "autocommit", False)):
        raise UATContractError("synthetic connection must have autocommit disabled")
    guard = CallerOwnedConnectionGuard(raw_connection)
    original: BaseException | None = None
    try:
        return operation(guard)
    except BaseException as exc:
        original = exc
        raise
    finally:
        try:
            raw_connection.rollback()
        except BaseException:
            if original is None:
                raise
        finally:
            raw_connection.close()


def synthetic_score_date(reviewed_at: datetime) -> date:
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise UATAssertionError("PostgreSQL reviewed_at must be timezone-aware")
    return reviewed_at.astimezone(ZoneInfo(TIMEZONE)).date()


def assert_synthetic_metadata(
    stored: Mapping[str, Any],
    expected_business_fields: Mapping[str, Any],
    *,
    job_id: str,
) -> None:
    required = ("application_domain", "installation_position", "uat_run_id")
    if set(expected_business_fields) != set(required):
        raise UATContractError("synthetic metadata contract must contain exactly three business fields")
    for key in required:
        if stored.get(key) != expected_business_fields[key]:
            raise UATAssertionError(f"synthetic metadata field {key} did not round-trip")
    if stored.get("collection_job_id") != job_id:
        raise UATAssertionError("synthetic metadata collection_job_id did not round-trip")


def _all_evidence_ids(score_result: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for bundle in score_result.get("results") or ():
        result.update(str(value) for value in bundle.get("evidence_ids") or ())
    return result


def assert_approved_only_score_isolation(
    *,
    baseline: Mapping[str, Any],
    after_collect: Mapping[str, Any],
    score_result: Mapping[str, Any],
    pending_ids: set[str],
    transitions: Sequence[Mapping[str, Any]],
) -> None:
    if dict(baseline) != dict(after_collect):
        raise UATAssertionError("approved-only gates changed after pending collect")
    if _all_evidence_ids(score_result) & pending_ids:
        raise UATAssertionError("pending evidence entered approved-only score")
    for transition in transitions:
        trigger_ids = {str(value) for value in transition.get("trigger_evidence_ids") or ()}
        if trigger_ids & pending_ids:
            raise UATAssertionError("pending evidence triggered a pool transition")


def assert_no_lookahead(
    *,
    historical_visible_ids: set[str],
    review_date_visible_ids: set[str],
    reviewed_later_id: str,
    published_later_id: str,
) -> None:
    if reviewed_later_id in historical_visible_ids:
        raise UATAssertionError("review cutoff admitted a later-reviewed fact")
    if published_later_id in historical_visible_ids:
        raise UATAssertionError("publish cutoff admitted a later-published fact")
    if published_later_id in review_date_visible_ids:
        raise UATAssertionError("review-date cutoff admitted a fact published one day later")
    if reviewed_later_id not in review_date_visible_ids:
        raise UATAssertionError("reviewed fact is not visible on its Shanghai review date")


def _payload(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dataclass_fields__"):
        return {name: getattr(value, name) for name in value.__dataclass_fields__}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    raise UATContractError(f"runtime returned unsupported {type(value).__name__}")


def _score_gate_snapshot(score_result: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(score_result.get("results") or ()):
        row = dict(raw)
        mapping_id = str(row.get("mapping_id") or f"mapping-{index}")
        selection = row.get("selection") or {}
        evidence_gate = row.get("evidence_gate") or (selection.get("detail") or {}).get("pool_gates", {}).get("evidence", {})
        route_gate = row.get("route_gate") or (selection.get("detail") or {}).get("pool_gates", {}).get("route", {})
        result[mapping_id] = {
            "evidence_level": evidence_gate.get("level"),
            "af_level": route_gate.get("level"),
            "pool_code": selection.get("pool_code"),
            "blocking_gate": selection.get("blocking_gate"),
        }
    return result


def validate_missing_score_inputs(score_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    fields = {
        "market_expectation_score": "missing_market_expectation_score",
        "expectation_gap_score": "missing_expectation_gap_score",
        "catalyst_score": "missing_catalyst_score",
        "risk_score": "missing_risk_score",
    }
    for bundle in score_result.get("results") or ():
        mapping_id = str(bundle.get("mapping_id") or "")
        limitations = list(bundle.get("data_limitations") or ())
        context = (((bundle.get("selection") or {}).get("detail") or {}).get("selection_context") or {})
        for field_name, limitation in fields.items():
            value = context.get(field_name)
            if value is None and limitation not in limitations:
                raise UATAssertionError(
                    f"mapping {mapping_id} missing {field_name} without {limitation}"
                )
            evidence.append(
                {"mapping_id": mapping_id, "field": field_name, "value": value, "limitation": limitation if value is None else None}
            )
        node_value = (((bundle.get("benefit") or {}).get("detail") or {}).get("node_attractiveness"))
        if node_value is None and "missing_node_score" not in limitations:
            limitations.append("missing_node_score")
        evidence.append(
            {"mapping_id": mapping_id, "field": "node_attractiveness", "value": node_value, "limitation": "missing_node_score" if node_value is None else None}
        )
        stage_missing = "unaudited_commercial_stage" in limitations or "missing_audited_stage" in limitations
        evidence.append(
            {"mapping_id": mapping_id, "field": "commercial_stage", "value": None if stage_missing else "audited", "limitation": "unaudited_commercial_stage" if stage_missing else None}
        )
        bundle["data_limitations"] = sorted(set(limitations))
    return evidence


def _assert_same_snapshot(left: CountSnapshot, right: CountSnapshot, reason: str) -> None:
    if left.counts != right.counts:
        raise UATAssertionError(reason)


def execute_uat(inputs: ValidatedUATInputs, *, runtime: Any) -> dict[str, Any]:
    """Execute the fixed stage machine against an injected real or mock runtime."""
    plan = build_uat_plan(inputs.chain_id, inputs.as_of_date)
    preflight = runtime.preflight()
    assert_preflight(preflight)
    snapshots: dict[str, dict[str, int]] = {}

    before = runtime.snapshot("before")
    snapshots[before.name] = dict(before.counts)
    review_before = runtime.real_review_state()
    ids_before = dict(runtime.scoped_ids())

    dry = _payload(
        runtime.orchestrate(mode="dry-run", source_policy="local-first", allow_score=False)
    )
    after_dry = runtime.snapshot("after_dry_run")
    snapshots[after_dry.name] = dict(after_dry.counts)
    if int(dry.get("writes", -1)) != 0 or int(dry.get("network_requests", -1)) != 0:
        raise UATAssertionError("dry-run performed writes or network requests")
    _assert_same_snapshot(before, after_dry, "dry-run changed database counts")
    if runtime.real_review_state() != review_before:
        raise UATAssertionError("dry-run changed real-company review IDs")
    baseline_score = dict(runtime.score(dry_run=True))
    baseline_gates = _score_gate_snapshot(baseline_score)

    collect_1 = _payload(
        runtime.orchestrate(mode="collect", source_policy="official-gap", allow_score=False)
    )
    axial_1 = dict(runtime.axial_discovery())
    if axial_1.get("scope") != "unrestricted_candidate_universe":
        raise UATAssertionError("axial-flux independent discovery was limited to five companies")
    ids_1 = dict(runtime.scoped_ids())
    after_collect_1 = runtime.snapshot("after_collect_1")
    snapshots[after_collect_1.name] = dict(after_collect_1.counts)
    new_fact_ids = set(ids_1.get("fact_ids") or ()) - set(ids_before.get("fact_ids") or ())
    new_event_ids = set(ids_1.get("event_ids") or ()) - set(ids_before.get("event_ids") or ())
    pending_after_collect = set(ids_1.get("pending_ids") or ())
    if not (new_fact_ids | new_event_ids).issubset(pending_after_collect):
        raise UATAssertionError("automatic collection produced non-pending evidence IDs")
    if runtime.real_review_state() != review_before:
        raise UATAssertionError("collect changed real-company approved IDs")

    collect_2_raw = runtime.orchestrate(
        mode="collect", source_policy="official-gap", allow_score=False
    )
    axial_2 = dict(runtime.axial_discovery())
    task7_report = runtime.render_report(collect_2_raw)
    collect_2 = _payload(collect_2_raw)
    ids_2 = dict(runtime.scoped_ids())
    after_collect_2 = runtime.snapshot("after_collect_2")
    snapshots[after_collect_2.name] = dict(after_collect_2.counts)
    for field_name in (
        "raw_evidence_documents",
        "evidence_extracted_facts",
        "business_tag_evidence_events",
        "evidence_gaps",
    ):
        if after_collect_1.counts[field_name] != after_collect_2.counts[field_name]:
            raise UATAssertionError(f"collect idempotency failed for {field_name}")
    if ids_1 != ids_2 or int(collect_2.get("inserted_documents", -1)) != 0:
        raise UATAssertionError("collect idempotency failed for exact IDs/insert count")
    axial_stable_fields = (
        "scope", "requirement_id", "seed_company_codes", "hits", "excluded", "pending"
    )
    if any(axial_1.get(key) != axial_2.get(key) for key in axial_stable_fields):
        raise UATAssertionError("axial-flux independent discovery was not idempotent")
    if int(axial_2.get("inserted_documents", -1)) != 0:
        raise UATAssertionError("second axial-flux discovery inserted duplicate documents")
    if runtime.real_review_state() != review_before:
        raise UATAssertionError("second collect changed real-company approved IDs")

    real_score = dict(runtime.score(dry_run=False))
    missing_input_evidence = validate_missing_score_inputs(real_score)
    after_real_score = runtime.snapshot("after_real_score")
    snapshots[after_real_score.name] = dict(after_real_score.counts)
    pending_ids = {str(value) for value in ids_2.get("pending_ids") or ()}
    assert_approved_only_score_isolation(
        baseline=baseline_gates,
        after_collect=_score_gate_snapshot(real_score),
        score_result=real_score,
        pending_ids=pending_ids,
        transitions=runtime.transitions(),
    )
    if runtime.real_review_state() != review_before:
        raise UATAssertionError("approved-only score changed real-company review IDs")

    synthetic = dict(runtime.synthetic())
    if synthetic.get("transaction_calls") != {"commit": 0, "rollback": 0, "close": 0}:
        raise UATAssertionError("business entry owned caller transaction")
    if int(synthetic.get("outer_rollback_calls", 0)) != 1:
        raise UATAssertionError("synthetic transaction did not have exactly one outer rollback")
    if not synthetic.get("savepoint_recovered") or not synthetic.get("markers_restored"):
        raise UATAssertionError("trigger SAVEPOINT/transaction marker contract failed")
    if synthetic.get("original_marker") != synthetic.get("restored_marker"):
        raise UATAssertionError("manual review marker was not restored to its original value")
    if not synthetic.get("pending_metadata_round_trip"):
        raise UATAssertionError("pending metadata did not round-trip through PostgreSQL")
    if "confirmed supply-chain fact requires audited manual review" not in str(
        synthetic.get("direct_guard_error") or ""
    ):
        raise UATAssertionError("033 direct-approval trigger evidence is missing")
    if synthetic.get("approved_route_level") != "AF2" or synthetic.get("route_max_pool") != "C":
        raise UATAssertionError("approved synthetic metadata did not reach AF2/C route gate")
    derived_fact = str((synthetic.get("synthetic_ids") or {}).get("fact_id") or "")
    if derived_fact not in set(synthetic.get("matched_fact_ids") or ()):
        raise UATAssertionError("route gate did not report the exact repository-derived fact ID")
    future_fact_id = str(synthetic.get("future_fact_id") or "")
    review_date_value = date.fromisoformat(str(synthetic.get("review_date") or ""))
    future_publish_value = date.fromisoformat(
        str(synthetic.get("future_publish_date") or "")
    )
    if review_date_value <= AS_OF_DATE:
        raise UATAssertionError("synthetic review date must be later than historical cutoff")
    if future_publish_value != review_date_value + timedelta(days=1):
        raise UATAssertionError("future fact publish date must be exactly review_date + 1 day")
    assert_no_lookahead(
        historical_visible_ids=set(synthetic.get("historical_visible_ids") or ()),
        review_date_visible_ids=set(synthetic.get("review_date_visible_ids") or ()),
        reviewed_later_id=derived_fact,
        published_later_id=future_fact_id,
    )
    cleanup_counts = dict(synthetic.get("cleanup_counts") or {})
    if set(cleanup_counts) != set(SYNTHETIC_CLEANUP_TABLES) or any(int(value) for value in cleanup_counts.values()):
        raise UATAssertionError("synthetic rollback left database rows")
    inside = synthetic.get("inside_snapshot")
    if not isinstance(inside, Mapping) or set(inside) != set(SNAPSHOT_FIELDS):
        raise UATAssertionError("synthetic inside-transaction snapshot is missing")
    snapshots["inside_synthetic_before_rollback"] = {key: int(value) for key, value in inside.items()}
    after_rollback = runtime.snapshot("after_synthetic_rollback")
    snapshots[after_rollback.name] = dict(after_rollback.counts)
    _assert_same_snapshot(
        after_real_score,
        after_rollback,
        "full database counts did not return to after_real_score baseline",
    )
    postflight = runtime.preflight()
    assert_preflight(postflight)
    if postflight.model_stage != preflight.model_stage:
        raise UATAssertionError("model registry stage changed during UAT")
    regression_evidence = dict(runtime.run_regressions())
    if regression_evidence.get("passed") is not True:
        raise UATAssertionError("focused UAT regression suite did not pass")
    git_evidence = dict(runtime.git_staged_check())
    if git_evidence.get("passed") is not True:
        raise UATAssertionError("git staged-file safety check did not pass")

    limitations = sorted(
        {
            *(str(value) for value in collect_1.get("data_limitations") or ()),
            *(str(value) for value in collect_2.get("data_limitations") or ()),
            *(str(value) for value in axial_1.get("data_limitations") or ()),
            *(str(value) for value in axial_2.get("data_limitations") or ()),
            *(str(value) for row in real_score.get("results") or () for value in row.get("data_limitations") or ()),
            str(synthetic.get("derived_id_design_deviation") or "").strip(),
        }
        - {""}
    )
    source_failures = sorted(
        {
            *(str(value) for value in collect_1.get("failed_tasks") or ()),
            *(str(value) for value in collect_2.get("failed_tasks") or ()),
            *(str(value) for value in axial_1.get("failed_tasks") or ()),
            *(str(value) for value in axial_2.get("failed_tasks") or ()),
        }
    )
    status = "PASS_WITH_LIMITATIONS" if limitations or source_failures else "PASS"
    pool_counts = _pool_counts(real_score.get("pool_counts") or {})
    transaction_calls = dict(synthetic.get("transaction_calls") or {})
    assertions = {
        "A01": {"passed": True, "evidence": {"steps": list(plan.steps)}},
        "A02": {"passed": True, "evidence": {"real_fact_review_mode": plan.real_fact_review_mode}},
        "A03": {"passed": True, "evidence": {"synthetic_score_date_policy": plan.synthetic_score_date_policy}},
        "A04": {"passed": True, "evidence": {"chain_id": inputs.chain_id, "as_of_date": inputs.as_of_date.isoformat(), "companies": list(plan.company_codes), "output_dir": str(inputs.output_dir)}},
        "B01": {"passed": True, "evidence": {"host": "localhost/127.0.0.1", "port": 6432, "database": "kronos"}},
        "B02": {"passed": True, "evidence": {"offline_head": preflight.offline_head, "database_revision": preflight.database_revision}},
        "B03": {"passed": True, "evidence": {"required_objects_missing": list(preflight.required_objects_missing)}},
        "B04": {"passed": True, "evidence": {"mapping_codes": list(preflight.company_mapping_codes)}},
        "B05": {"passed": True, "evidence": {"invalid_confirmed_facts": preflight.invalid_confirmed_facts}},
        "B06": {"passed": True, "evidence": {"invalid_approved_events": preflight.invalid_approved_events, "invalid_approved_monitors": preflight.invalid_approved_monitors}},
        "B07": {"passed": True, "evidence": {"invalid_approved_stages": preflight.invalid_approved_stages, "model_stage_before": preflight.model_stage, "model_stage_after": postflight.model_stage}},
        "C01": {"passed": True, "evidence": {"writes": dry.get("writes"), "network_requests": dry.get("network_requests")}},
        "C02": {"passed": True, "evidence": {"before": before.counts, "after_dry_run": after_dry.counts}},
        "C03": {"passed": True, "evidence": {"mapped_company_codes": list(REAL_COMPANY_CODES), "axial_scope": axial_2.get("scope"), "axial_seed_codes": list(axial_2.get("seed_company_codes") or ())}},
        "C04": {"passed": True, "evidence": {"new_pending_ids": sorted(new_fact_ids | new_event_ids)}},
        "C05": {"passed": True, "evidence": {"real_review_sets_unchanged": runtime.real_review_state() == review_before}},
        "C06": {"passed": True, "evidence": {"mapped_ids_stable": ids_1 == ids_2, "axial_ids_stable": all(axial_1.get(key) == axial_2.get(key) for key in axial_stable_fields)}},
        "C07": {"passed": True, "evidence": {"source_failures": source_failures, "axial_hits": axial_2.get("hits", 0)}},
        "D01": {"passed": True, "evidence": {"pending_ids": sorted(pending_ids), "score_evidence_ids": sorted(_all_evidence_ids(real_score))}},
        "D02": {"passed": True, "evidence": {"baseline_gates": baseline_gates, "after_collect_gates": _score_gate_snapshot(real_score)}},
        "D03": {"passed": True, "evidence": {"transitions": runtime.transitions()}},
        "D04": {"passed": True, "evidence": {"pool_counts": pool_counts}},
        "D05": {"passed": True, "evidence": {"missing_score_inputs": missing_input_evidence}},
        "E01": {"passed": True, "evidence": {"pending_metadata_round_trip": synthetic.get("pending_metadata_round_trip"), "pending_route_level": synthetic.get("pending_route_level")}},
        "E02": {"passed": True, "evidence": {"approved_route_level": synthetic.get("approved_route_level"), "matched_fact_ids": synthetic.get("matched_fact_ids")}},
        "E03": {"passed": True, "evidence": {"reviewed_at": synthetic.get("reviewed_at"), "timezone_aware": True}},
        "E04": {"passed": True, "evidence": {"review_date": synthetic.get("review_date"), "timezone": TIMEZONE}},
        "E05": {"passed": True, "evidence": {"route_level": synthetic.get("approved_route_level"), "max_pool": synthetic.get("route_max_pool")}},
        "E06": {"passed": True, "evidence": {"historical_visible_ids": synthetic.get("historical_visible_ids"), "review_date_visible_ids": synthetic.get("review_date_visible_ids")}},
        "E07": {"passed": True, "evidence": {"future_fact_id": future_fact_id, "future_publish_date": synthetic.get("future_publish_date"), "review_date": synthetic.get("review_date")}},
        "E08": {"passed": True, "evidence": {"historical_as_of_date": AS_OF_DATE.isoformat(), "synthetic_review_date": synthetic.get("review_date")}},
        "F01": {"passed": True, "evidence": {"entry": "review_fact", "transaction_calls": transaction_calls}},
        "F02": {"passed": True, "evidence": {"entry": "review_event", "transaction_calls": transaction_calls}},
        "F03": {"passed": True, "evidence": {"entry": "review_expectation_monitor", "transaction_calls": transaction_calls}},
        "F04": {"passed": True, "evidence": {"entry": "run_batch_score", "transaction_calls": transaction_calls}},
        "F05": {"passed": True, "evidence": {"original_marker": synthetic.get("original_marker"), "restored_marker": synthetic.get("restored_marker")}},
        "F06": {"passed": True, "evidence": {"trigger_error": synthetic.get("direct_guard_error")}},
        "F07": {"passed": True, "evidence": {"savepoint_recovered": synthetic.get("savepoint_recovered")}},
        "F08": {"passed": True, "evidence": {"outer_rollback_calls": synthetic.get("outer_rollback_calls")}},
        "F09": {"passed": True, "evidence": {"cleanup_counts": cleanup_counts, "count_baseline_restored": after_real_score.counts == after_rollback.counts}},
        "G01": {"passed": False, "evidence": {"state": "pending_artifact_write_and_readback"}},
        "G02": {"passed": True, "evidence": {"report_sections": ["count_snapshots", "source_failures", "pool_counts", "axial_flux", "limitations"]}},
        "G03": {"passed": True, "evidence": {"model_stage": postflight.model_stage, "investment_limitation": True}},
        "G04": {"passed": True, "evidence": {"pending_ids_are_clues_only": sorted(pending_ids)}},
        "G05": {"passed": True, "evidence": {"recursive_sensitive_scan": "passed_before_write"}},
        "G06": {"passed": True, "evidence": regression_evidence},
        "G07": {"passed": True, "evidence": git_evidence},
    }
    if set(assertions) != set(REQUIRED_ASSERTION_IDS):
        raise UATAssertionError("explicit assertion map is incomplete")
    result = build_result_document(
        status=status,
        assertions=assertions,
        pool_counts=real_score.get("pool_counts") or {},
        limitations=limitations,
    )
    result["preflight"] = {
        **_payload(preflight),
        "database_revision_after": postflight.database_revision,
        "model_stage_after": postflight.model_stage,
        "evidence": "revision, schema-bound trigger/function, audit and staging checks passed",
    }
    result["count_snapshots"] = snapshots
    result["dry_run"] = {**dry, "score_baseline": baseline_score, "evidence": "zero writes/network and identical counts"}
    result["collect_1"] = {
        **collect_1,
        "scope_ids_before": ids_before,
        "scope_ids": ids_1,
        "new_pending_ids": sorted(new_fact_ids | new_event_ids),
        "source_failures": source_failures,
        "evidence": "pending-only fixed scope",
    }
    result["collect_2"] = {
        **collect_2,
        "scope_ids": ids_2,
        "task7_report_markdown": task7_report,
        "evidence": "zero inserts and exact stable IDs",
    }
    result["real_company_review_status"] = {"before": review_before, "after": runtime.real_review_state(), "evidence": "read-only set equality"}
    result["score_before_review"] = {
        **real_score,
        "pool_counts": _pool_counts(real_score.get("pool_counts") or {}),
        "pending_ids_excluded": sorted(pending_ids),
        "missing_score_inputs": missing_input_evidence,
        "evidence": "approved-only gates unchanged; each NULL input has an explicit limitation",
    }
    result["axial_flux_discovery"] = {
        **axial_2,
        "mapped_collect_scope": list(REAL_COMPANY_CODES),
        "independent_discovery_scope": axial_2.get("scope"),
        "first_run": axial_1,
        "failures": source_failures,
        "evidence": "mapped collect fixed to five companies; AF discovery used unrestricted candidates",
    }
    result["synthetic_review"] = {**synthetic, "evidence": "pending metadata -> audited AF2/C round trip"}
    result["direct_approval_guard"] = {"error": synthetic.get("direct_guard_error"), "savepoint_recovered": synthetic.get("savepoint_recovered"), "evidence": "033 trigger rejected direct SQL"}
    result["no_lookahead"] = {"historical_as_of_date": AS_OF_DATE.isoformat(), "synthetic_review_date": synthetic.get("review_date"), "historical_visible_ids": synthetic.get("historical_visible_ids"), "review_date_visible_ids": synthetic.get("review_date_visible_ids"), "future_fact_id": future_fact_id, "evidence": "publish and review cutoffs independently checked"}
    result["transaction_boundary"] = {"business_calls": synthetic.get("transaction_calls"), "outer_rollback_calls": 1, "evidence": "caller-owned transaction guard"}
    result["rollback_cleanup"] = {"counts": cleanup_counts, "evidence": "fresh-connection exact-ID zero residual"}
    validate_execution_result(result)
    return result


def assert_preflight(evidence: PreflightEvidence | Any) -> None:
    failures: list[str] = []
    if evidence.database_revision != DATABASE_REVISION:
        failures.append(f"database revision is {evidence.database_revision!r}, expected 033")
    if evidence.offline_head != DATABASE_REVISION:
        failures.append(f"offline alembic head is {evidence.offline_head!r}, expected 033")
    failures.extend(str(item) for item in evidence.required_objects_missing)
    if tuple(sorted(evidence.company_mapping_codes)) != tuple(sorted(REAL_COMPANY_CODES)):
        failures.append("not all five fixed real-company mappings exist")
    for field_name in (
        "invalid_confirmed_facts",
        "invalid_approved_events",
        "invalid_approved_monitors",
        "invalid_approved_stages",
    ):
        if int(getattr(evidence, field_name)):
            failures.append(f"{field_name} is non-zero")
    if evidence.model_stage != "staging":
        failures.append("selection model must already be staging")
    if failures:
        raise UATAssertionError("preflight failed: " + "; ".join(failures))


_REQUIRED_OBJECTS_SQL = """
-- required function: public.guard_supply_chain_manual_review
WITH required_relations(name) AS (
  VALUES
    ('raw_evidence_documents'), ('evidence_extracted_facts'),
    ('business_tag_evidence_events'), ('business_tag_expectation_monitor'),
    ('business_tag_stage_tracking'), ('business_tag_mapping'),
    ('business_tag_authenticity_scores'), ('business_tag_operating_quality_scores'),
    ('business_tag_benefit_scores'), ('business_tag_selection_scores'),
    ('business_tag_pool_state'), ('business_tag_pool_transition_log'),
    ('evidence_collection_jobs'), ('model_registry')
), required_columns(table_name, column_name) AS (
  VALUES
    ('evidence_extracted_facts', 'reviewer'),
    ('evidence_extracted_facts', 'review_note'),
    ('evidence_extracted_facts', 'reviewed_at'),
    ('business_tag_evidence_events', 'reviewer'),
    ('business_tag_evidence_events', 'review_note'),
    ('business_tag_evidence_events', 'reviewed_at'),
    ('business_tag_expectation_monitor', 'reviewer'),
    ('business_tag_expectation_monitor', 'review_note'),
    ('business_tag_expectation_monitor', 'reviewed_at'),
    ('business_tag_stage_tracking', 'source_event_id'),
    ('business_tag_stage_tracking', 'review_status')
), required_triggers(name, table_name) AS (
  VALUES
    ('trg_supply_chain_manual_review_fact', 'evidence_extracted_facts'),
    ('trg_supply_chain_manual_review_event', 'business_tag_evidence_events'),
    ('trg_supply_chain_manual_review_expectation', 'business_tag_expectation_monitor'),
    ('trg_supply_chain_manual_review_stage', 'business_tag_stage_tracking')
), missing AS (
  SELECT 'table:' || expected.name AS item
  FROM required_relations expected
  WHERE to_regclass('public.' || expected.name) IS NULL
  UNION ALL
  SELECT 'column:' || expected.table_name || '.' || expected.column_name
  FROM required_columns expected
  WHERE NOT EXISTS (
    SELECT 1 FROM information_schema.columns actual
    WHERE actual.table_schema = 'public'
      AND actual.table_name = expected.table_name
      AND actual.column_name = expected.column_name
  )
  UNION ALL
  SELECT 'trigger:' || expected.name
  FROM required_triggers expected
  WHERE NOT EXISTS (
    SELECT 1 FROM pg_trigger actual
    JOIN pg_class relation ON relation.oid = actual.tgrelid
    JOIN pg_namespace relation_schema ON relation_schema.oid = relation.relnamespace
    JOIN pg_proc review_function ON review_function.oid = actual.tgfoid
    JOIN pg_namespace function_schema ON function_schema.oid = review_function.pronamespace
    WHERE actual.tgname = expected.name
      AND relation.relname = expected.table_name
      AND relation_schema.nspname = 'public'
      AND function_schema.nspname = 'public'
      AND review_function.proname = 'guard_supply_chain_manual_review'
      AND actual.tgenabled <> 'D'
      AND NOT actual.tgisinternal
  )
  UNION ALL
  SELECT 'function:guard_supply_chain_manual_review'
  WHERE NOT EXISTS (
    SELECT 1 FROM pg_proc fn
    JOIN pg_namespace sch ON sch.oid = fn.pronamespace
    WHERE sch.nspname = 'public'
      AND fn.proname = 'guard_supply_chain_manual_review'
  )
)
SELECT COALESCE(array_agg(item ORDER BY item), ARRAY[]::text[]) AS missing_objects
FROM missing
"""


_INVALID_AUDIT_SQL = """
SELECT
  (SELECT count(*) FROM evidence_extracted_facts fact
   WHERE fact.validation_status = 'confirmed'
     AND (NULLIF(BTRIM(fact.reviewer), '') IS NULL
       OR NULLIF(BTRIM(fact.review_note), '') IS NULL
       OR fact.reviewed_at IS NULL
       OR (fact.evidence_event_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM business_tag_evidence_events event
         WHERE event.event_id = fact.evidence_event_id
           AND event.mapping_id IS NOT DISTINCT FROM fact.mapping_id
           AND event.review_status = 'approved'
           AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
           AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
           AND event.reviewed_at IS NOT NULL)))) AS invalid_confirmed_facts,
  (SELECT count(*) FROM business_tag_evidence_events
   WHERE review_status = 'approved'
     AND (NULLIF(BTRIM(reviewer), '') IS NULL
       OR NULLIF(BTRIM(review_note), '') IS NULL OR reviewed_at IS NULL))
    AS invalid_approved_events,
  (SELECT count(*) FROM business_tag_expectation_monitor
   WHERE review_status = 'approved'
     AND (NULLIF(BTRIM(reviewer), '') IS NULL
       OR NULLIF(BTRIM(review_note), '') IS NULL OR reviewed_at IS NULL))
    AS invalid_approved_monitors,
  (SELECT count(*) FROM business_tag_stage_tracking stage
   WHERE stage.review_status = 'approved' AND NOT EXISTS (
     SELECT 1 FROM business_tag_evidence_events event
     WHERE event.event_id = stage.source_event_id
       AND event.mapping_id = stage.mapping_id
       AND event.review_status = 'approved'
       AND NULLIF(BTRIM(event.reviewer), '') IS NOT NULL
       AND NULLIF(BTRIM(event.review_note), '') IS NOT NULL
       AND event.reviewed_at IS NOT NULL)) AS invalid_approved_stages
"""


def _first_value(row: Any) -> Any:
    if isinstance(row, Mapping):
        return next(iter(row.values()))
    return row[0]


def verify_offline_alembic_head(*, runner: Callable[..., Any] = subprocess.run) -> str:
    completed = runner(
        ["alembic", "-c", "alembic.ini", "heads"],
        cwd=REPO_ROOT / "backend",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = " ".join(str(completed.stdout or "").split())
    if completed.returncode != 0 or output != "033 (head)":
        diagnostic = " ".join(str(completed.stderr or output).split())
        raise UATAssertionError(
            f"offline alembic head must be exactly 033 (head): {diagnostic}"
        )
    return "033"


def collect_preflight_evidence(
    connection: Any, *, offline_head: str | None
) -> PreflightEvidence:
    """Read every hard preflight from the connected existing development DB."""
    with connection.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        revision_row = cur.fetchone()
        cur.execute(_REQUIRED_OBJECTS_SQL)
        objects_row = cur.fetchone()
        cur.execute(
            """
            SELECT DISTINCT split_part(code, '.', 1) AS code
            FROM business_tag_mapping
            WHERE chain_id = %s AND status <> 'rejected'
              AND split_part(code, '.', 1) = ANY(%s)
            ORDER BY code
            """,
            (CHAIN_ID, list(REAL_COMPANY_CODES)),
        )
        company_rows = cur.fetchall()
        cur.execute(_INVALID_AUDIT_SQL)
        invalid_row = cur.fetchone()
        cur.execute(
            "SELECT stage FROM model_registry WHERE id = %s",
            (MODEL_REGISTRY_ID,),
        )
        model_row = cur.fetchone()
    if revision_row is None:
        raise UATAssertionError("alembic_version has no current revision")
    if objects_row is None or invalid_row is None:
        raise UATAssertionError("preflight catalog/audit query returned no row")
    missing = (
        objects_row.get("missing_objects", ())
        if isinstance(objects_row, Mapping)
        else objects_row[0]
    ) or ()
    company_codes = tuple(
        str(row.get("code") if isinstance(row, Mapping) else row[0])
        for row in company_rows
    )
    invalid = (
        invalid_row
        if isinstance(invalid_row, Mapping)
        else dict(
            zip(
                (
                    "invalid_confirmed_facts",
                    "invalid_approved_events",
                    "invalid_approved_monitors",
                    "invalid_approved_stages",
                ),
                invalid_row,
                strict=True,
            )
        )
    )
    return PreflightEvidence(
        database_revision=str(_first_value(revision_row)),
        required_objects_missing=tuple(str(value) for value in missing),
        company_mapping_codes=company_codes,
        invalid_confirmed_facts=int(invalid["invalid_confirmed_facts"]),
        invalid_approved_events=int(invalid["invalid_approved_events"]),
        invalid_approved_monitors=int(invalid["invalid_approved_monitors"]),
        invalid_approved_stages=int(invalid["invalid_approved_stages"]),
        model_stage=(str(_first_value(model_row)) if model_row is not None else None),
        offline_head=offline_head,
    )


def capture_real_company_review_state(connection: Any) -> dict[str, dict[str, tuple[str, ...]]]:
    """Capture immutable review-ID sets; this function performs no review writes."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT scoped.code,
              ARRAY(SELECT DISTINCT fact.fact_id::text
                    FROM business_tag_mapping mapping
                    JOIN evidence_extracted_facts fact ON fact.mapping_id = mapping.mapping_id
                    WHERE split_part(mapping.code, '.', 1) = scoped.code
                      AND mapping.chain_id = %s AND fact.validation_status = 'confirmed'
                    ORDER BY 1) AS confirmed_fact_ids,
              ARRAY(SELECT DISTINCT event.event_id::text
                    FROM business_tag_mapping mapping
                    JOIN business_tag_evidence_events event ON event.mapping_id = mapping.mapping_id
                    WHERE split_part(mapping.code, '.', 1) = scoped.code
                      AND mapping.chain_id = %s AND event.review_status = 'approved'
                    ORDER BY 1) AS approved_event_ids,
              ARRAY(SELECT DISTINCT monitor.monitor_id::text
                    FROM business_tag_mapping mapping
                    JOIN business_tag_expectation_monitor monitor ON monitor.mapping_id = mapping.mapping_id
                    WHERE split_part(mapping.code, '.', 1) = scoped.code
                      AND mapping.chain_id = %s AND monitor.review_status = 'approved'
                    ORDER BY 1) AS approved_monitor_ids,
              ARRAY(SELECT DISTINCT stage.stage_id::text
                    FROM business_tag_mapping mapping
                    JOIN business_tag_stage_tracking stage ON stage.mapping_id = mapping.mapping_id
                    WHERE split_part(mapping.code, '.', 1) = scoped.code
                      AND mapping.chain_id = %s AND stage.review_status = 'approved'
                    ORDER BY 1) AS approved_stage_ids
            FROM unnest(%s::text[]) AS scoped(code)
            ORDER BY scoped.code
            """,
            (CHAIN_ID, CHAIN_ID, CHAIN_ID, CHAIN_ID, list(REAL_COMPANY_CODES)),
        )
        rows = cur.fetchall()
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    columns = (
        "code",
        "confirmed_fact_ids",
        "approved_event_ids",
        "approved_monitor_ids",
        "approved_stage_ids",
    )
    for raw in rows:
        row = raw if isinstance(raw, Mapping) else dict(zip(columns, raw, strict=True))
        code = str(row["code"])
        result[code] = {
            key: tuple(str(value) for value in row.get(key) or ())
            for key in columns[1:]
        }
    if tuple(result) != REAL_COMPANY_CODES:
        raise UATAssertionError("real-company review state did not return all five codes")
    return result


def _pool_counts(values: Mapping[str, int]) -> dict[str, int]:
    return {code: int(values.get(code, 0)) for code in ("A", "B", "C", "D")}


def build_result_document(
    *,
    status: str,
    assertions: Mapping[str, Any],
    pool_counts: Mapping[str, int],
    limitations: Sequence[str],
) -> dict[str, Any]:
    if status not in {"PASS", "PASS_WITH_LIMITATIONS", "FAIL", "BLOCKED"}:
        raise UATContractError(f"unsupported UAT status: {status}")
    investment_limit = "模型仍为 staging；本 UAT 不具有投资有效性，不构成自动买入结论。"
    data: dict[str, Any] = {
        "status": status,
        "identity": {
            "chain_id": CHAIN_ID,
            "as_of_date": AS_OF_DATE.isoformat(),
            "timezone": TIMEZONE,
            "model_version": MODEL_VERSION,
        },
        "preflight": {"database_revision": DATABASE_REVISION, "model_stage": "staging"},
        "count_snapshots": {},
        "dry_run": {},
        "collect_1": {},
        "collect_2": {},
        "real_company_review_status": {code: {} for code in REAL_COMPANY_CODES},
        "score_before_review": {"pool_counts": _pool_counts(pool_counts), "mapping_results": []},
        "axial_flux_discovery": {"hits": 0, "excluded": 0, "pending": 0, "failures": []},
        "synthetic_review": {},
        "direct_approval_guard": {},
        "no_lookahead": {
            "historical_as_of_date": AS_OF_DATE.isoformat(),
            "synthetic_review_date": None,
        },
        "transaction_boundary": {},
        "rollback_cleanup": {},
        "limitations": [*map(str, limitations), investment_limit],
        "assertions": dict(assertions),
    }
    return data


def _walk_output(value: object) -> list[str]:
    if isinstance(value, Mapping):
        return [item for key, child in value.items() for item in (str(key), *_walk_output(child))]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [item for child in value for item in _walk_output(child)]
    return [str(value)]


def assert_no_sensitive_output(value: object) -> None:
    sensitive_keys = {
        "password", "passwd", "pwd", "api_key", "apikey", "x_api_key",
        "cookie", "authorization", "token", "access_token", "refresh_token",
        "secret", "client_secret",
    }

    def inspect(item: object, key: str | None = None) -> None:
        if key is not None:
            normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
            components = {part for part in normalized.split("_") if part}
            sensitive_component = bool(
                normalized in sensitive_keys
                or components & {
                    "password", "passwd", "pwd", "token", "cookie",
                    "authorization", "secret",
                }
                or ({"api", "key"} <= components)
            )
            is_redacted = item is None or (
                isinstance(item, str) and item in {"", "<redacted>"}
            )
            if sensitive_component and not is_redacted:
                raise UATAssertionError(f"sensitive key {key} has a non-redacted value")
        if isinstance(item, Mapping):
            for child_key, child in item.items():
                inspect(child, str(child_key))
        elif isinstance(item, (list, tuple, set, frozenset)):
            for child in item:
                inspect(child)

    inspect(value)
    text = "\n".join(_walk_output(value))
    sensitive_patterns = (
        r"(?i)postgres(?:ql)?://[^\s/@:]+:[^\s/@]+@",
        r"(?i)(?:password|passwd|pwd|api[_-]?key|cookie|authorization|token)\s*[=:]\s*(?!<redacted>)[^\s,;]+",
        r"(?i)authorization\s*:\s*(?:bearer|basic)\s+\S+",
        r"(?i)[?&](?:x-amz-signature|signature|sig|x-goog-signature)=[^&\s]+",
    )
    if any(re.search(pattern, text) for pattern in sensitive_patterns):
        raise UATAssertionError("sensitive credential found in UAT output")


def normalize_unrestricted_discovery_documents(
    documents: Sequence[object],
) -> tuple[dict[str, Any], ...]:
    """Use Task 7's canonical RawDocument -> discovery Mapping conversion."""
    _install_product_import_paths()
    from supply_chain_evidence_orchestrator import _scope_discovery_documents

    records, _filtered = _scope_discovery_documents(
        documents,
        scope_active=False,
        allowed_codes=(),
    )
    return records


def propose_axial_candidates(
    records: Sequence[Mapping[str, Any]],
    *,
    requirement: Mapping[str, Any],
):
    _install_product_import_paths()
    from kronos_factors.engine.supply_chain_evidence_orchestration import (
        propose_independent_candidates,
    )

    return propose_independent_candidates(
        records,
        requirement=requirement,
        as_of_date=AS_OF_DATE,
    )


def validate_final_result(
    result: Mapping[str, Any], *, allow_pending_artifact: bool = False
) -> None:
    if tuple(result) != RESULT_SECTIONS:
        raise UATAssertionError("final result sections are incomplete or out of contract order")
    status = result.get("status")
    if status not in {"PASS", "PASS_WITH_LIMITATIONS"}:
        raise UATAssertionError("only evidenced PASS statuses may be written")
    assertions = result.get("assertions")
    if not isinstance(assertions, Mapping) or set(assertions) != set(REQUIRED_ASSERTION_IDS):
        raise UATAssertionError("A01-G07 assertions are incomplete")
    for assertion_id in REQUIRED_ASSERTION_IDS:
        item = assertions[assertion_id]
        if (
            assertion_id == "G01"
            and allow_pending_artifact
            and isinstance(item, Mapping)
            and item.get("passed") is False
            and item.get("evidence")
        ):
            continue
        if not isinstance(item, Mapping) or item.get("passed") is not True or not item.get("evidence"):
            raise UATAssertionError(f"assertion {assertion_id} lacks passing evidence")
    snapshots = result.get("count_snapshots")
    if not isinstance(snapshots, Mapping) or set(snapshots) != set(SNAPSHOT_NAMES):
        raise UATAssertionError("required count snapshots are incomplete")
    for name in SNAPSHOT_NAMES:
        counts = snapshots[name]
        if not isinstance(counts, Mapping) or set(counts) != set(SNAPSHOT_FIELDS):
            raise UATAssertionError(f"snapshot {name} fields are incomplete")
    for section in REQUIRED_EVIDENCE_SECTIONS:
        value = result.get(section)
        if not isinstance(value, Mapping) or not value:
            raise UATAssertionError(f"required evidence section {section} is empty")
    preflight = result["preflight"]
    if preflight.get("database_revision") != DATABASE_REVISION:
        raise UATAssertionError("preflight database revision is not 033")
    if preflight.get("model_stage") != "staging":
        raise UATAssertionError("preflight model is not staging")
    assert_no_sensitive_output(result)


def validate_execution_result(result: Mapping[str, Any]) -> None:
    assertions = result.get("assertions")
    if not isinstance(assertions, Mapping) or set(assertions) != set(REQUIRED_ASSERTION_IDS):
        raise UATAssertionError("A01-G07 assertions are incomplete")
    artifact = assertions.get("G01")
    if not isinstance(artifact, Mapping) or artifact.get("passed") is not False:
        raise UATAssertionError("execution result G01 must remain pending until artifact readback")
    validate_final_result(result, allow_pending_artifact=True)


def render_uat_markdown(result: Mapping[str, Any]) -> str:
    pools = result.get("score_before_review", {}).get("pool_counts", {})
    limitations = result.get("limitations") or []
    report = "\n".join(
        (
            f"# 灵巧手产业链证据编排 UAT：{result.get('status')}",
            "",
            f"- 历史截止日：{AS_OF_DATE.isoformat()} ({TIMEZONE})",
            "- 模型仍为 staging",
            "- 本 UAT 不具有投资有效性，不构成自动买入结论。",
            "",
            "## 已审核事实",
            "",
            "仅列示完整审计链并在截止日可见的事实。",
            "",
            "## 待审核事实",
            "",
            "采集结果仅作为待审核线索，不转换为公司结论。",
            "",
            "## 已拒绝事实",
            "",
            "保留拒绝理由供追溯。",
            "",
            "## 证据缺口",
            "",
            "缺失输入保持 NULL，不用中性分填充。",
            "",
            "## 下一步行动",
            "",
            "按 blocking gate 和证据缺口安排人工核验。",
            "",
            "## 8 层 × 8 维矩阵",
            "",
            "矩阵仅展示当前可用证据和缺口。",
            "",
            "## A/B/C/D 四池",
            "",
            " | ".join(f"{code}: {int(pools.get(code, 0))}" for code in ("A", "B", "C", "D")),
            "",
            "## AF 独立搜索和 route gate",
            "",
            "轴向磁通命中、排除、待审和失败数均如实记录。",
            "",
            "## 数据限制",
            "",
            *(f"- {item}" for item in limitations),
            "",
        )
    )
    task7_report = str(
        (result.get("collect_2") or {}).get("task7_report_markdown") or ""
    ).strip()
    if task7_report:
        report += "\n## Task 7 证据报告原文\n\n" + task7_report + "\n"
    return report


def render_qa_markdown(result: Mapping[str, Any]) -> str:
    synthetic = result.get("synthetic_review") or {}
    return "\n".join(
        (
            "# 灵巧手产业链证据编排 UAT QA",
            "",
            f"- 状态：{result.get('status')}",
            f"- 数据库 revision：{(result.get('preflight') or {}).get('database_revision')}",
            f"- 历史截止日：{AS_OF_DATE.isoformat()} ({TIMEZONE})",
            f"- synthetic reviewed_at：{synthetic.get('reviewed_at')}",
            f"- synthetic 上海 review date：{synthetic.get('review_date')}",
            "- UAT 没有批准五家真实公司事实。",
            "- 模型仍为 staging；本 UAT 不能证明投资有效性，不构成自动买入信号。",
            "",
            "## 来源、计数与四池",
            "",
            "```json",
            json.dumps(
                {
                    "source_failures": (result.get("collect_1") or {}).get("source_failures"),
                    "count_snapshots": result.get("count_snapshots"),
                    "real_company_review_status": result.get("real_company_review_status"),
                    "pool_counts": (result.get("score_before_review") or {}).get("pool_counts"),
                    "axial_flux": result.get("axial_flux_discovery"),
                    "missing_inputs": result.get("limitations"),
                    "rollback_cleanup": result.get("rollback_cleanup"),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            "```",
            "",
            "## 设计偏差",
            "",
            str(synthetic.get("derived_id_design_deviation") or "无"),
            "",
        )
    )


def write_uat_outputs(
    output_dir: Path,
    result: Mapping[str, Any],
    *,
    qa_path: Path = FIXED_QA_PATH,
) -> None:
    validate_execution_result(result)
    mutable = result if isinstance(result, dict) else dict(result)
    report = render_uat_markdown(mutable)
    qa_report = render_qa_markdown(mutable)
    assert_no_sensitive_output({"result": mutable, "report": report, "qa": qa_report})
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "result.json"
    report_path = output_dir / "report.md"
    temp_result = result_path.with_suffix(".json.tmp")
    temp_report = report_path.with_suffix(".md.tmp")
    temp_qa = qa_path.with_suffix(qa_path.suffix + ".tmp")
    temp_paths = (temp_result, temp_report, temp_qa)
    try:
        temp_report.write_text(report, encoding="utf-8")
        temp_qa.write_text(qa_report, encoding="utf-8")
        if any(not path.is_file() or not path.read_text(encoding="utf-8").strip() for path in (temp_report, temp_qa)):
            raise UATAssertionError("report/QA temporary artifact readback failed")
        mutable["assertions"]["G01"] = {
            "passed": True,
            "evidence": {
                "result_json": str(result_path),
                "report_markdown": str(report_path),
                "qa_markdown": str(qa_path),
                "report_qa_readable": True,
            },
        }
        validate_final_result(mutable)
        assert_no_sensitive_output({"result": mutable, "report": report, "qa": qa_report})
        temp_result.write_text(
            json.dumps(mutable, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        parsed = json.loads(temp_result.read_text(encoding="utf-8"))
        if parsed.get("assertions", {}).get("G01", {}).get("passed") is not True:
            raise UATAssertionError("final result artifact did not retain G01 evidence")
        temp_report.replace(report_path)
        temp_qa.replace(qa_path)
        temp_result.replace(result_path)
        artifacts = (result_path, report_path, qa_path)
        if any(not path.is_file() or not path.read_text(encoding="utf-8").strip() for path in artifacts):
            raise UATAssertionError("PASS requires readable result/report/QA artifacts")
    finally:
        for path in temp_paths:
            if path.exists():
                path.unlink()


def _install_product_import_paths() -> None:
    for path in (
        REPO_ROOT / "tools",
        REPO_ROOT / "packages" / "kronos-factors",
        REPO_ROOT / "services" / "screener-service",
    ):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


class _SyntheticDocument:
    def __init__(
        self,
        *,
        doc_id: str,
        source_id: str,
        company_code: str,
        publish_time: str,
        title: str,
        content_text: str,
        metadata: Mapping[str, Any],
    ):
        self.doc_id = doc_id
        self.source_id = source_id
        self.source_level = "strong"
        self.company_code = company_code
        self.company_name = "Task10 synthetic company"
        self.publish_time = publish_time
        self.title = title
        self.content_text = content_text
        self.url = f"https://uat.invalid/{doc_id}"
        self.doc_type = "product_spec"
        self.metadata = dict(metadata)
        self.content_hash = uuid.uuid5(uuid.NAMESPACE_URL, doc_id).hex


def build_runtime_request(*, mode: str, source_policy: str, allow_score: bool):
    _install_product_import_paths()
    from kronos_factors.engine.supply_chain_evidence_orchestration import EvidenceRunRequest

    return EvidenceRunRequest(
        chain_id=CHAIN_ID,
        as_of_date=AS_OF_DATE,
        mode=mode,
        source_policy=source_policy,
        source_limits={
            "discovery": 500,
            "official_discovery_documents": 20,
            "official_discovery_companies": 20,
            "official_pages_per_company": 3,
            "mapped_official_tasks": 50,
            "mapped_cninfo_documents_per_task": 20,
        },
        mapping_ids=(),
        company_codes=REAL_COMPANY_CODES,
        allow_score=allow_score,
    )


class DefaultUATRuntime:
    """Adapter over the real Task 7-9 interfaces; construction itself is read-only."""

    def __init__(self, inputs: ValidatedUATInputs, connection: Any):
        _install_product_import_paths()
        self.inputs = inputs
        self.connection = connection
        self._last_score: dict[str, Any] = {}

    @staticmethod
    def _dict_cursor(connection: Any):
        from psycopg2.extras import RealDictCursor

        return connection.cursor(cursor_factory=RealDictCursor)

    def preflight(self) -> PreflightEvidence:
        return collect_preflight_evidence(
            self.connection,
            offline_head=verify_offline_alembic_head(),
        )

    def snapshot(self, name: str) -> CountSnapshot:
        return capture_count_snapshot(self.connection, name)

    def real_review_state(self) -> dict[str, dict[str, tuple[str, ...]]]:
        return capture_real_company_review_state(self.connection)

    def _mapping_ids(self) -> list[str]:
        with self._dict_cursor(self.connection) as cur:
            cur.execute(
                """
                SELECT mapping_id
                FROM business_tag_mapping
                WHERE chain_id = %s AND status <> 'rejected'
                  AND split_part(code, '.', 1) = ANY(%s)
                ORDER BY mapping_id
                """,
                (CHAIN_ID, list(REAL_COMPANY_CODES)),
            )
            return [str(row["mapping_id"]) for row in cur.fetchall()]

    def orchestrate(self, *, mode: str, source_policy: str, allow_score: bool) -> Any:
        from run_supply_chain_evidence_orchestration import build_runtime_dependencies
        from supply_chain_evidence_orchestrator import run_evidence_orchestration

        args = argparse.Namespace(
            pg_url=self.inputs.pg_url,
            source_limit=[],
        )
        dependencies = build_runtime_dependencies(args)
        # Mapped collection is intentionally limited to the fixed five companies.
        # Independent AF discovery runs through axial_discovery() with no company scope.
        dependencies["repository"].fetch_independent_discovery_requirements = (
            lambda _chain_id: ()
        )
        request = build_runtime_request(
            mode=mode, source_policy=source_policy, allow_score=allow_score
        )
        return run_evidence_orchestration(request, **dependencies)

    def axial_discovery(self) -> dict[str, Any]:
        from run_supply_chain_evidence_orchestration import build_runtime_dependencies
        from supply_chain_evidence_orchestrator import build_unmapped_discovery_tasks
        from kronos_factors.engine.supply_chain_evidence_orchestration import EvidenceRunRequest

        args = argparse.Namespace(pg_url=self.inputs.pg_url, source_limit=[])
        dependencies = build_runtime_dependencies(args)
        repository = dependencies["repository"]
        adapter = dependencies["official_discovery_adapter"]
        requirements = tuple(
            item
            for item in repository.fetch_independent_discovery_requirements(CHAIN_ID)
            if item.get("technology_route_id") == "dexterous_axial_flux_motor"
            or item.get("requirement_id") == "dexterous_axial_flux_motor"
        )
        if len(requirements) != 1:
            raise UATAssertionError("axial-flux independent requirement must resolve exactly once")
        request = EvidenceRunRequest(
            chain_id=CHAIN_ID,
            as_of_date=AS_OF_DATE,
            mode="collect",
            source_policy="official-gap",
            source_limits=dict(build_runtime_request(mode="collect", source_policy="official-gap", allow_score=False).source_limits),
            mapping_ids=(),
            company_codes=(),
            allow_score=False,
        )
        requirement = requirements[0]
        local_documents = repository.fetch_candidate_universe(
            AS_OF_DATE, requirement, (), request.source_limits["discovery"]
        )
        local_records = normalize_unrestricted_discovery_documents(local_documents)
        filtered_local_documents = len(local_documents) - len(local_records)
        hits = list(
            propose_axial_candidates(local_records, requirement=requirement)
        )
        tasks = build_unmapped_discovery_tasks(
            requirements, tuple(hits), repository, request, ()
        )
        official = adapter.collect(
            tasks,
            as_of_date=AS_OF_DATE,
            source_limits=request.source_limits,
        ) if tasks else None
        filtered_official_documents = 0
        if official is not None:
            official_records = normalize_unrestricted_discovery_documents(
                official.documents
            )
            filtered_official_documents = len(official.documents) - len(official_records)
            hits.extend(
                propose_axial_candidates(official_records, requirement=requirement)
            )
        job_id = repository.start_job(request)
        inserted = 0
        duplicate = 0
        pending = 0
        seen: set[tuple[str, str, str]] = set()
        try:
            for hit in hits:
                identity = (str(hit.doc_id), str(hit.requirement_id), str(hit.company_code))
                if identity in seen:
                    continue
                seen.add(identity)
                outcome = repository.persist_discovery_hit(hit, job_id=job_id)
                if outcome.validation_status != "pending":
                    raise UATAssertionError("automatic axial discovery produced a non-pending fact")
                inserted += int(bool(outcome.inserted))
                duplicate += int(bool(outcome.duplicate))
                pending += int(outcome.validation_status == "pending")
                if outcome.proposal is not None and hit.eligible_for_mapping:
                    repository.upsert_candidate_mapping(outcome.proposal)
            failures = tuple(official.failed_tasks) if official is not None else ()
            errors = tuple(official.errors) if official is not None else ()
            repository.finish_job(
                job_id,
                {
                    "status": "partial_success" if failures or errors else "success",
                    "fetched_count": len(seen),
                    "inserted_count": inserted,
                    "duplicate_count": duplicate,
                    "failed_tasks": failures,
                    "errors": errors,
                },
            )
        except Exception as exc:
            repository.finish_job(
                job_id,
                {
                    "status": "failed",
                    "fetched_count": len(seen),
                    "inserted_count": inserted,
                    "duplicate_count": duplicate,
                    "failed_tasks": ("axial_flux_independent_discovery",),
                    "errors": (sanitize_diagnostic(exc, pg_url=self.inputs.pg_url),),
                },
            )
            raise
        seed_codes = sorted(
            {str(code) for task in tasks for code in task.seed_company_codes}
        )
        return {
            "scope": "unrestricted_candidate_universe",
            "requirement_id": "dexterous_axial_flux_motor",
            "seed_company_codes": tuple(seed_codes),
            "hits": sum(1 for hit in hits if hit.eligible_for_mapping),
            "excluded": sum(1 for hit in hits if not hit.eligible_for_mapping),
            "pending": pending,
            "inserted_documents": inserted,
            "duplicate_documents": duplicate,
            "failed_tasks": tuple(official.failed_tasks) if official is not None else (),
            "data_limitations": tuple(
                [
                    *(f"adapter_error:{value}" for value in (official.errors if official is not None else ())),
                    *(
                        [f"scope_filtered_official_discovery_documents:{filtered_official_documents}"]
                        if filtered_official_documents
                        else []
                    ),
                    *(
                        [f"scope_filtered_local_discovery_documents:{filtered_local_documents}"]
                        if filtered_local_documents
                        else []
                    ),
                ]
            ),
            "network_requests": int(official.network_requests) if official is not None else 0,
        }

    def render_report(self, result: Any) -> str:
        from supply_chain_evidence_report import render_evidence_report

        return render_evidence_report(result)

    def score(self, *, dry_run: bool) -> dict[str, Any]:
        from score_supply_chain_selection_v2 import run_batch_score

        value = run_batch_score(
            pg_url=self.inputs.pg_url,
            chain_id=CHAIN_ID,
            trade_date=AS_OF_DATE,
            model_version=MODEL_VERSION,
            dry_run=dry_run,
            mapping_ids=self._mapping_ids(),
        )
        self._last_score = dict(value)
        return self._last_score

    def scoped_ids(self) -> dict[str, tuple[str, ...]]:
        with self._dict_cursor(self.connection) as cur:
            cur.execute(
                """
                WITH scoped_mapping AS (
                  SELECT mapping_id FROM business_tag_mapping
                  WHERE chain_id = %s AND status <> 'rejected'
                    AND split_part(code, '.', 1) = ANY(%s)
                )
                SELECT
                  ARRAY(SELECT mapping_id::text FROM scoped_mapping ORDER BY 1) AS mapping_ids,
                  ARRAY(SELECT DISTINCT fact.doc_id::text
                        FROM evidence_extracted_facts fact
                        WHERE fact.mapping_id IN (SELECT mapping_id FROM scoped_mapping)
                          AND fact.doc_id IS NOT NULL ORDER BY 1) AS document_ids,
                  ARRAY(SELECT DISTINCT fact.fact_id::text
                        FROM evidence_extracted_facts fact
                        WHERE fact.mapping_id IN (SELECT mapping_id FROM scoped_mapping)
                        ORDER BY 1) AS fact_ids,
                  ARRAY(SELECT DISTINCT event.event_id::text
                        FROM business_tag_evidence_events event
                        WHERE event.mapping_id IN (SELECT mapping_id FROM scoped_mapping)
                        ORDER BY 1) AS event_ids,
                  ARRAY(
                    SELECT fact.fact_id::text FROM evidence_extracted_facts fact
                    WHERE fact.mapping_id IN (SELECT mapping_id FROM scoped_mapping)
                      AND fact.validation_status <> 'confirmed'
                    UNION
                    SELECT event.event_id::text FROM business_tag_evidence_events event
                    WHERE event.mapping_id IN (SELECT mapping_id FROM scoped_mapping)
                      AND event.review_status <> 'approved'
                    ORDER BY 1
                  ) AS pending_ids
                """,
                (CHAIN_ID, list(REAL_COMPANY_CODES)),
            )
            row = dict(cur.fetchone() or {})
        return {
            key: tuple(str(value) for value in row.get(key) or ())
            for key in ("mapping_ids", "document_ids", "fact_ids", "event_ids", "pending_ids")
        }

    def transitions(self) -> list[dict[str, Any]]:
        with self._dict_cursor(self.connection) as cur:
            cur.execute(
                """
                SELECT transition_id, mapping_id, trigger_evidence_ids
                FROM business_tag_pool_transition_log
                WHERE transition_date = %s
                  AND mapping_id = ANY(%s)
                ORDER BY transition_id
                """,
                (AS_OF_DATE, self._mapping_ids()),
            )
            return [dict(row) for row in cur.fetchall()]

    def run_regressions(self) -> dict[str, Any]:
        groups = (
            (
                "packages+kronos-tools",
                (
                    "packages/kronos-factors/tests/test_industry_chain_evidence_requirements.py",
                    "packages/kronos-factors/tests/test_industry_chain_templates.py",
                    "packages/kronos-factors/tests/test_supply_chain_evidence_orchestration.py",
                    "packages/kronos-factors/tests/test_supply_chain_selection_v2.py",
                    "tools/tests/test_supply_chain_data_collection_center.py",
                    "tools/tests/test_supply_chain_evidence_pipeline.py",
                    "tools/tests/test_supply_chain_evidence_adapters.py",
                    "tools/tests/test_supply_chain_evidence_orchestrator.py",
                    "tools/tests/test_supply_chain_evidence_report.py",
                    "tools/tests/test_score_supply_chain_selection_v2.py",
                    "tools/tests/test_run_supply_chain_evidence_orchestration_uat.py",
                ),
            ),
            (
                "screener-service",
                (
                    "services/screener-service/tests/test_supply_chain_evidence_review.py",
                    "services/screener-service/tests/test_supply_chain_evidence_orchestration_repository.py",
                    "services/screener-service/tests/test_supply_chain_selection_repository.py",
                    "services/screener-service/tests/test_supply_chain_selection_v2_api.py",
                    "services/screener-service/tests/test_supply_chain_v2_migration_contract.py",
                    "services/screener-service/tests/test_api.py",
                ),
            ),
            ("api-gateway", ("services/api-gateway/tests/test_gateway_routes.py",)),
        )
        results: list[dict[str, Any]] = []
        passed_count = 0
        for name, test_files in groups:
            completed = subprocess.run(
                ["bash", "tools/codex-lowio.sh", "py", *test_files],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            summary = " ".join((completed.stdout or completed.stderr).splitlines()[-3:])
            skipped = bool(re.search(r"\b\d+ skipped\b", summary))
            match = re.search(r"\b(\d+) passed\b", summary)
            count = int(match.group(1)) if match else 0
            passed_count += count
            results.append(
                {
                    "group": name,
                    "returncode": completed.returncode,
                    "postgresql_tests_skipped": skipped,
                    "passed_count": count,
                    "summary": summary,
                }
            )
        return {
            "passed": all(
                item["returncode"] == 0
                and item["postgresql_tests_skipped"] is False
                and item["passed_count"] > 0
                for item in results
            ),
            "groups": results,
            "passed_count": passed_count,
            "test_file_count": sum(len(files) for _name, files in groups),
        }

    def git_staged_check(self) -> dict[str, Any]:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        staged = tuple(line.strip() for line in completed.stdout.splitlines() if line.strip())
        return {
            "passed": completed.returncode == 0 and not staged,
            "returncode": completed.returncode,
            "staged_files": list(staged),
        }

    def synthetic(self) -> dict[str, Any]:
        return _run_real_synthetic_uat(self.inputs)


def _fetch_fact(connection: Any, fact_id: str) -> dict[str, Any]:
    from psycopg2.extras import RealDictCursor

    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT fact.*, document.publish_time
            FROM evidence_extracted_facts fact
            JOIN raw_evidence_documents document ON document.doc_id = fact.doc_id
            WHERE fact.fact_id = %s
            """,
            (fact_id,),
        )
        row = cur.fetchone()
    if not row:
        raise UATAssertionError(f"synthetic fact {fact_id} was not persisted")
    return dict(row)


def _visible_fact_ids(connection: Any, mapping_id: str, trade_date: date) -> set[str]:
    from psycopg2.extras import RealDictCursor
    from app.domains.supply_chain.selection_repository import SelectionRepository
    from score_supply_chain_selection_v2 import _cutoff_utc

    repository = SelectionRepository(lambda: connection)
    with connection.cursor(cursor_factory=RealDictCursor) as cur:
        rows = repository.fetch_asof_evidence(cur, mapping_id, _cutoff_utc(trade_date))
    return {
        str(row.get("fact_id") or row.get("evidence_id"))
        for row in rows
        if row.get("fact_id") or row.get("evidence_id")
    }


def _marker(connection: Any) -> str:
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.supply_chain_review_action', true)")
        row = cur.fetchone()
    return str(row[0] or "") if row else ""


def _cleanup_counts(pg_url: str, ids: Mapping[str, Any]) -> dict[str, int]:
    import psycopg2

    connection = psycopg2.connect(pg_url, connect_timeout=5)
    try:
        mapping_id = str(ids["mapping_id"])
        exact = {
            "evidence_source_catalog": tuple(ids["source_ids"]),
            "raw_evidence_documents": tuple(ids["doc_ids"]),
            "evidence_extracted_facts": tuple(ids["fact_ids"]),
            "business_tag_evidence_events": tuple(ids["event_ids"]),
            "business_tag_expectation_monitor": tuple(ids["monitor_ids"]),
        }
        id_columns = {
            "evidence_source_catalog": "source_id",
            "raw_evidence_documents": "doc_id",
            "evidence_extracted_facts": "fact_id",
            "business_tag_evidence_events": "event_id",
            "business_tag_expectation_monitor": "monitor_id",
        }
        result: dict[str, int] = {}
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM business_tag_mapping WHERE mapping_id = %s", (mapping_id,))
            result["business_tag_mapping"] = int(cur.fetchone()[0])
            for table, values in exact.items():
                cur.execute(
                    f"SELECT count(*) FROM {table} WHERE {id_columns[table]} = ANY(%s)",
                    (list(values),),
                )
                result[table] = int(cur.fetchone()[0])
            for table in SYNTHETIC_CLEANUP_TABLES:
                if table in result:
                    continue
                cur.execute(f"SELECT count(*) FROM {table} WHERE mapping_id = %s", (mapping_id,))
                result[table] = int(cur.fetchone()[0])
        return result
    finally:
        connection.close()


def _run_real_synthetic_uat(inputs: ValidatedUATInputs) -> dict[str, Any]:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    from app.domains.supply_chain.evidence_orchestration_repository import EvidenceOrchestrationRepository
    from app.domains.supply_chain.evidence_review_repository import (
        EvidenceFactMetadataPatch,
        EvidenceReviewRepository,
    )
    from app.domains.supply_chain.evidence_review_service import EvidenceReviewService
    from kronos_factors.engine.industry_chain_templates import get_industry_template
    from kronos_factors.scorer.supply_chain_selection_v2 import derive_route_gate
    from score_supply_chain_selection_v2 import run_batch_score

    token = uuid.uuid4().hex
    prefix = f"uat-task10-{token}"
    ids: dict[str, Any] = {
        "run_id": f"{prefix}-run",
        "mapping_id": f"{prefix}-mapping",
        "doc_ids": [f"{prefix}-doc", f"{prefix}-future-doc"],
        "fact_ids": [],
        "event_ids": [],
        "monitor_ids": [f"{prefix}-monitor"],
        "source_ids": [f"{prefix}-source"],
    }
    raw = psycopg2.connect(inputs.pg_url, connect_timeout=5)
    raw.autocommit = False
    original_marker = _marker(raw)
    guard = CallerOwnedConnectionGuard(raw)
    repository = EvidenceOrchestrationRepository(lambda: guard)
    review_service = EvidenceReviewService(EvidenceReviewRepository(lambda: guard))
    outer_rollback_calls = 0
    result: dict[str, Any] | None = None
    original: BaseException | None = None
    try:
        mapping_id = ids["mapping_id"]
        company_code = f"UAT{token[:8]}"
        route_path = {
            "requirement_id": "dexterous_axial_flux_motor",
            "technology_route_id": "dexterous_axial_flux_motor",
            "uat_run_id": ids["run_id"],
        }
        with raw.cursor() as cur:
            cur.execute(
                """
                INSERT INTO business_tag_mapping (
                  mapping_id, code, node_id, chain_id, tag_name, l1_l8_path,
                  confidence, status, evidence_ids
                ) VALUES (%s, %s, NULL, %s, %s, %s::jsonb, 0.35, 'candidate', '[]'::jsonb)
                """,
                (
                    mapping_id,
                    company_code,
                    CHAIN_ID,
                    "轴向磁通电机",
                    json.dumps(route_path, ensure_ascii=False),
                ),
            )

        metadata = {
            "application_domain": "robot_wrist",
            "installation_position": "wrist_joint",
            "uat_run_id": ids["run_id"],
        }
        document = _SyntheticDocument(
            doc_id=ids["doc_ids"][0],
            source_id=ids["source_ids"][0],
            company_code=company_code,
            publish_time="2026-07-08T10:00:00+08:00",
            title="Task10 synthetic axial-flux product specification",
            content_text="Synthetic robot wrist axial-flux motor product specification.",
            metadata=metadata,
        )
        pending = repository.persist_pending_document(
            document=document,
            mapping_id=mapping_id,
            requirement_id="product_or_prototype",
            job_id=ids["run_id"],
            as_of_date=AS_OF_DATE,
            connection=guard,
        )
        ids["fact_ids"].append(str(pending.fact_id))
        if pending.event_id:
            ids["event_ids"].append(str(pending.event_id))
        pending_fact = _fetch_fact(raw, pending.fact_id)
        assert_synthetic_metadata(
            dict(pending_fact.get("metadata") or {}),
            metadata,
            job_id=ids["run_id"],
        )
        mapping = {
            "mapping_id": mapping_id,
            "code": company_code,
            "chain_id": CHAIN_ID,
            "tag_name": "轴向磁通电机",
            "technology_route_id": "dexterous_axial_flux_motor",
            "l1_l8_path": route_path,
            "status": "candidate",
        }
        template = get_industry_template(CHAIN_ID)
        pending_gate = derive_route_gate(mapping, [pending_fact], template, as_of_date=AS_OF_DATE)
        if pending_gate.level != "AF0":
            raise UATAssertionError("pending synthetic fact satisfied route gate")

        patch = EvidenceFactMetadataPatch(
            application_domain="robot_wrist",
            installation_position="wrist_joint",
        )
        reviewed = review_service.review_fact(
            fact_id=pending.fact_id,
            decision="approved",
            reviewer=f"{prefix}-reviewer",
            note="Task10 synthetic review only; rolled back after UAT",
            stage_after=None,
            metadata_patch=patch,
            connection=guard,
        )
        reviewed_at = reviewed.get("reviewed_at")
        if not isinstance(reviewed_at, datetime):
            raise UATAssertionError("review_fact did not return PostgreSQL reviewed_at")
        review_date = synthetic_score_date(reviewed_at)
        if _marker(raw) != original_marker:
            raise UATAssertionError("manual marker was not restored after fact review")
        approved_fact = _fetch_fact(raw, pending.fact_id)
        approved_metadata = dict(approved_fact.get("metadata") or {})
        assert_synthetic_metadata(
            approved_metadata,
            metadata,
            job_id=ids["run_id"],
        )
        approved_gate = derive_route_gate(
            mapping, [approved_fact], template, as_of_date=review_date
        )
        if (
            approved_gate.level != "AF2"
            or approved_gate.max_pool_code != "C"
            or pending.fact_id not in approved_gate.matched_fact_ids
        ):
            raise UATAssertionError("audited route metadata did not produce AF2/C")

        extra_event_id = f"{prefix}-event"
        ids["event_ids"].append(extra_event_id)
        with raw.cursor() as cur:
            cur.execute(
                """
                INSERT INTO business_tag_evidence_events (
                  event_id, mapping_id, code, event_date, source_type, source_id,
                  title, excerpt, evidence_type, confidence, review_status
                ) VALUES (%s, %s, %s, CURRENT_DATE, 'uat', %s, %s, %s,
                          'product_spec', 0.8, 'pending_review')
                """,
                (extra_event_id, mapping_id, company_code, ids["source_ids"][0], "Synthetic event", "Synthetic event"),
            )
        review_service.review_event(
            event_id=extra_event_id,
            decision="approved",
            reviewer=f"{prefix}-reviewer",
            note="Task10 synthetic event review",
            stage_after=None,
            connection=guard,
        )
        if _marker(raw) != original_marker:
            raise UATAssertionError("manual marker was not restored after event review")

        monitor_id = ids["monitor_ids"][0]
        with raw.cursor() as cur:
            cur.execute(
                """
                INSERT INTO business_tag_expectation_monitor (
                  monitor_id, mapping_id, claim_text, claim_date, expected_result,
                  expected_date, gap_status, evidence_ids, review_status, metadata
                ) VALUES (%s, %s, %s, CURRENT_DATE, %s, CURRENT_DATE,
                          'pending', '[]'::jsonb, 'pending_review', %s::jsonb)
                """,
                (monitor_id, mapping_id, "Synthetic expectation", "Synthetic expected result", json.dumps({"uat_run_id": ids["run_id"]})),
            )
        review_service.review_expectation_monitor(
            monitor_id=monitor_id,
            decision="approved",
            reviewer=f"{prefix}-reviewer",
            note="Task10 synthetic expectation review",
            connection=guard,
        )
        if _marker(raw) != original_marker:
            raise UATAssertionError("manual marker was not restored after expectation review")

        direct_fact_id = f"{prefix}-direct-fact"
        ids["fact_ids"].append(direct_fact_id)
        with raw.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evidence_extracted_facts (
                  fact_id, doc_id, mapping_id, company_code, fact_type, fact_nature,
                  original_quote, source_level, confidence, validation_status, metadata
                ) VALUES (%s, %s, %s, %s, 'product_spec', 'company_claim',
                          'Synthetic direct guard fact', 'strong', 0.8, 'pending', '{}'::jsonb)
                """,
                (direct_fact_id, document.doc_id, mapping_id, company_code),
            )
            cur.execute("SAVEPOINT direct_approval_guard")
            try:
                cur.execute(
                    """
                    UPDATE evidence_extracted_facts
                    SET validation_status='confirmed', reviewer=%s, review_note=%s,
                        reviewed_at=CURRENT_TIMESTAMP
                    WHERE fact_id=%s
                    """,
                    (f"{prefix}-reviewer", "direct SQL must fail", direct_fact_id),
                )
                raise UATAssertionError("direct SQL approval unexpectedly succeeded")
            except UATAssertionError:
                raise
            except Exception as exc:
                direct_guard_error = sanitize_diagnostic(exc, pg_url=inputs.pg_url)
                if "confirmed supply-chain fact requires audited manual review" not in direct_guard_error:
                    raise UATAssertionError("direct approval failed for an unexpected reason") from exc
                cur.execute("ROLLBACK TO SAVEPOINT direct_approval_guard")
                cur.execute("RELEASE SAVEPOINT direct_approval_guard")
                cur.execute("SELECT 1")
                if cur.fetchone()[0] != 1:
                    raise UATAssertionError("outer transaction unusable after savepoint rollback")

        future_publish_date = review_date + timedelta(days=1)
        future_document = _SyntheticDocument(
            doc_id=ids["doc_ids"][1],
            source_id=ids["source_ids"][0],
            company_code=company_code,
            publish_time=f"{future_publish_date.isoformat()}T10:00:00+08:00",
            title="Task10 future-published specification",
            content_text="Synthetic future-published robot wrist specification.",
            metadata=metadata,
        )
        future = repository.persist_pending_document(
            document=future_document,
            mapping_id=mapping_id,
            requirement_id="product_or_prototype",
            job_id=ids["run_id"],
            as_of_date=review_date,
            connection=guard,
        )
        ids["fact_ids"].append(str(future.fact_id))
        if future.event_id:
            ids["event_ids"].append(str(future.event_id))
        review_service.review_fact(
            fact_id=future.fact_id,
            decision="approved",
            reviewer=f"{prefix}-reviewer",
            note="Task10 future fact review",
            stage_after=None,
            metadata_patch=patch,
            connection=guard,
        )
        historical_visible = _visible_fact_ids(raw, mapping_id, AS_OF_DATE)
        review_visible = _visible_fact_ids(raw, mapping_id, review_date)
        if pending.fact_id not in review_visible:
            raise UATAssertionError("ordinary reviewed fact was not visible on review date")
        if future.fact_id in review_visible:
            raise UATAssertionError("future-published fact was visible on review date")

        historical_score = run_batch_score(
            pg_url=inputs.pg_url,
            chain_id=CHAIN_ID,
            trade_date=AS_OF_DATE,
            model_version=MODEL_VERSION,
            dry_run=False,
            mapping_ids=[mapping_id],
            connection=guard,
        )
        review_date_score = run_batch_score(
            pg_url=inputs.pg_url,
            chain_id=CHAIN_ID,
            trade_date=review_date,
            model_version=MODEL_VERSION,
            dry_run=False,
            mapping_ids=[mapping_id],
            connection=guard,
        )
        historical_score_ids = {
            str(evidence_id)
            for bundle in historical_score.get("results") or ()
            for evidence_id in bundle.get("evidence_ids") or ()
        }
        review_date_score_ids = {
            str(evidence_id)
            for bundle in review_date_score.get("results") or ()
            for evidence_id in bundle.get("evidence_ids") or ()
        }
        if pending.fact_id in historical_score_ids or future.fact_id in historical_score_ids:
            raise UATAssertionError("historical score admitted post-cutoff synthetic evidence")
        if pending.fact_id not in review_date_score_ids:
            raise UATAssertionError("review-date score did not admit audited synthetic evidence")
        if guard.transaction_calls != {"commit": 0, "rollback": 0, "close": 0}:
            raise UATAssertionError("caller-owned business entry attempted transaction ownership")
        inside = capture_count_snapshot(raw, "inside_synthetic_before_rollback")
        result = {
            "synthetic_ids": {
                "run_id": ids["run_id"],
                "mapping_id": mapping_id,
                "doc_ids": tuple(ids["doc_ids"]),
                "fact_ids": tuple(ids["fact_ids"]),
                "event_ids": tuple(ids["event_ids"]),
                "monitor_ids": tuple(ids["monitor_ids"]),
                "source_ids": tuple(ids["source_ids"]),
                "fact_id": str(pending.fact_id),
                "event_id": str(pending.event_id),
            },
            "derived_id_design_deviation": (
                "Repository/scorer contracts force derived FACT-/EV-/score/transition IDs; "
                "exact fact/event IDs were read from PendingDocumentOutcome and all derived "
                "rows were verified by exact ID or mapping_id after rollback."
            ),
            "pending_metadata_round_trip": all(
                pending_fact.get("metadata", {}).get(key) == value
                for key, value in metadata.items()
            ) and pending_fact.get("metadata", {}).get("collection_job_id") == ids["run_id"],
            "pending_route_level": pending_gate.level,
            "reviewed_at": reviewed_at.isoformat(),
            "review_date": review_date.isoformat(),
            "approved_route_level": approved_gate.level,
            "route_max_pool": approved_gate.max_pool_code,
            "matched_fact_ids": list(approved_gate.matched_fact_ids),
            "historical_visible_ids": sorted(historical_visible),
            "review_date_visible_ids": sorted(review_visible),
            "future_fact_id": str(future.fact_id),
            "future_publish_date": future_publish_date.isoformat(),
            "historical_score": historical_score,
            "review_date_score": review_date_score,
            "historical_score_evidence_ids": sorted(historical_score_ids),
            "review_date_score_evidence_ids": sorted(review_date_score_ids),
            "direct_guard_error": direct_guard_error,
            "savepoint_recovered": True,
            "markers_restored": _marker(raw) == original_marker,
            "original_marker": original_marker,
            "restored_marker": _marker(raw),
            "transaction_calls": dict(guard.transaction_calls),
            "outer_rollback_calls": 1,
            "inside_snapshot": dict(inside.counts),
        }
    except BaseException as exc:
        original = exc
        raise
    finally:
        try:
            raw.rollback()
            outer_rollback_calls += 1
        except BaseException:
            if original is None:
                raise
        finally:
            raw.close()
    if result is None:
        raise UATAssertionError("synthetic UAT produced no result")
    if outer_rollback_calls != 1:
        raise UATAssertionError("synthetic UAT outer rollback count was not one")
    result["cleanup_counts"] = _cleanup_counts(inputs.pg_url, ids)
    result["outer_rollback_calls"] = outer_rollback_calls
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed dexterous-hand PostgreSQL UAT")
    parser.add_argument("--pg-url", required=True)
    parser.add_argument("--chain-id", required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def _default_connector(pg_url: str, *, connect_timeout: int = 5) -> Any:
    import psycopg2

    return psycopg2.connect(pg_url, connect_timeout=connect_timeout)


def _default_executor(inputs: ValidatedUATInputs, connection: Any) -> Mapping[str, Any]:
    return execute_uat(inputs, runtime=DefaultUATRuntime(inputs, connection))


def run_cli(
    argv: list[str] | None = None,
    *,
    connector: Callable[..., Any] = _default_connector,
    executor: Callable[[ValidatedUATInputs, Any], Mapping[str, Any]] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    # This entire block precedes connector() by contract.
    try:
        inputs = validate_uat_inputs(
            pg_url=args.pg_url,
            chain_id=args.chain_id,
            as_of_date=args.as_of_date,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(sanitize_diagnostic(exc, pg_url=str(args.pg_url or "")), file=sys.stderr)
        return 2
    connection = None
    try:
        connection = connector(inputs.pg_url, connect_timeout=5)
        active_executor = executor or _default_executor
        result = dict(active_executor(inputs, connection))
        if result.get("status") not in {"PASS", "PASS_WITH_LIMITATIONS"}:
            raise UATAssertionError(f"UAT status is {result.get('status', 'FAIL')}")
        write_uat_outputs(inputs.output_dir, result)
        return 0
    except Exception as exc:
        print(sanitize_diagnostic(exc, pg_url=inputs.pg_url), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
