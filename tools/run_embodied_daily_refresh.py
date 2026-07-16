#!/usr/bin/env python3
"""具身智能每日刷新、审计与送达补偿的统一入口。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PG_URL = "postgresql://kronos:kronos@localhost:6432/kronos"
PUBLISHABLE_PRIORITIES = {"P0", "P1", "P2"}


@dataclass(frozen=True)
class RefreshResult:
    mode: str
    run_id: str | None
    persisted: bool
    delivery_attempted: bool
    change_count: int = 0
    source_errors: dict[str, str] | None = None
    status: str = "success"
    delivery_summary: dict[str, Any] | None = None
    snapshot: dict[str, Any] | None = None


class EmbodiedRefreshOrchestrator:
    """Keep the durability boundary and side-effect order explicit and testable."""

    def __init__(
        self,
        *,
        repository: Any,
        refresh_sources: Callable[..., Any],
        normalize_evidence: Callable[..., Any],
        apply_mappings: Callable[..., Any],
        rollback_mappings: Callable[[], None],
        audit_and_rank: Callable[..., Any],
        diff_baseline: Callable[..., list[Any]],
        deliver_changes: Callable[..., Any],
        failure_repository_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.repository = repository
        self.refresh_sources = refresh_sources
        self.normalize_evidence = normalize_evidence
        self.apply_mappings = apply_mappings
        self.rollback_mappings = rollback_mappings
        self.audit_and_rank = audit_and_rank
        self.diff_baseline = diff_baseline
        self.deliver_changes = deliver_changes
        self.failure_repository_factory = failure_repository_factory

    def run(
        self,
        *,
        mode: str,
        as_of_date: str | date,
        send_feishu: bool = False,
        changes: list[Any] | None = None,
    ) -> RefreshResult:
        if mode not in {"dry-run", "apply", "audit"}:
            raise ValueError("mode must be dry-run, apply, or audit")
        run_date = date.fromisoformat(as_of_date) if isinstance(as_of_date, str) else as_of_date
        if mode == "audit":
            run = self.repository.begin_run(run_date, mode)
            run_id = run.run_id
            try:
                snapshot = self.audit_and_rank(run_id, None, mode)
                self.repository.save_snapshot(run_id, snapshot, commit=False)
                self.repository.commit()
                self.repository.finish_run(run_id, "success", {"snapshot": snapshot, "audit": snapshot.get("audit", {})})
                return RefreshResult(mode, run_id, True, False, status="success", snapshot=snapshot)
            except Exception:
                self.repository.rollback()
                try:
                    failure_repository = self.failure_repository_factory() if self.failure_repository_factory else self.repository
                    failure_repository.finish_run(run_id, "failed", {"failed_at": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass
                raise
        persisted = mode == "apply"
        run = self.repository.begin_run(run_date, mode) if persisted else None
        run_id = getattr(run, "run_id", None)
        if persisted and getattr(run, "status", "running") != "running":
            summary = getattr(run, "summary", {}) or {}
            return RefreshResult(
                mode, run_id, True, False, int(summary.get("changes", 0)),
                summary.get("source_errors", {}), getattr(run, "status", "success"),
                summary.get("delivery"), summary.get("snapshot"),
            )
        try:
            cursors = self.repository.load_cursors()
            refreshed = self.refresh_sources(cursors, run_date)
            normalized = self.normalize_evidence(refreshed.rows)
            mappings = self.apply_mappings(normalized, run_id if persisted else None, run_date, persist=persisted)
            snapshot = self.audit_and_rank(run_id, mappings, mode)
            baseline = self.repository.load_success_baseline(run_id) if persisted else None
            empty_baseline = {"status": "success", "mappings": []}
            detected = changes if changes is not None else self.diff_baseline(baseline or empty_baseline, snapshot)
            if persisted:
                self.repository.save_changes(detected, commit=False)
                self.repository.save_snapshot(run_id, snapshot, commit=False)

                successful = set(refreshed.rows) - set(refreshed.errors)
                for source in sorted(successful):
                    cursor = refreshed.next_cursors.get(source)
                    if cursor is not None:
                        self.repository.save_cursor(source, cursor, run_id, commit=False)
                self.repository.commit()

            publishable = [row for row in detected if _priority(row) in PUBLISHABLE_PRIORITIES]
            delivery_attempted = bool(persisted and send_feishu and publishable)
            delivery_summary = self.deliver_changes(run_id, publishable, snapshot) if delivery_attempted else None
            final_status = getattr(delivery_summary, "status", "success")

            if persisted:
                summary = {
                    "changes": len(detected), "source_errors": refreshed.errors, "snapshot": snapshot,
                }
                if delivery_summary is not None:
                    summary["delivery"] = asdict(delivery_summary) if hasattr(delivery_summary, "__dataclass_fields__") else {
                        key: getattr(delivery_summary, key) for key in ("status", "confirmed", "pending")
                        if hasattr(delivery_summary, key)
                    }
                self.repository.finish_run(run_id, final_status, summary)
            return RefreshResult(mode, run_id, persisted, delivery_attempted, len(detected), refreshed.errors,
                                 final_status, summary.get("delivery") if persisted else None, snapshot)
        except Exception:
            self.repository.rollback() if hasattr(self.repository, "rollback") else self.rollback_mappings()
            if persisted and run_id is not None:
                try:
                    failure_repository = self.failure_repository_factory() if self.failure_repository_factory else self.repository
                    failure_repository.finish_run(run_id, "failed", {"failed_at": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    pass
            raise


def _priority(value: Any) -> str:
    if isinstance(value, dict):
        payload = value.get("payload", value)
    else:
        payload = getattr(value, "payload", {})
    return str(payload.get("priority", "P3"))


def _coerce_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    text = str(value).strip()
    return date.fromisoformat(text[:10]) if text else None


def _source_text(row: dict[str, Any]) -> str:
    fields = (
        "title", "content", "question", "answer", "abstract", "summary",
        "main_business", "business_scope", "bz_item", "bz_sales",
    )
    return "。".join(str(row.get(key) or "").strip() for key in fields if str(row.get(key) or "").strip())


def _node_keywords(node: dict[str, Any]) -> set[str]:
    metadata = node.get("metadata") or {}
    values = [node.get("display_name")]
    for key in ("aliases", "keywords", "products"):
        raw = metadata.get(key, [])
        values.extend(raw if isinstance(raw, list) else [raw])
    generic = {"感知", "感知系统", "控制", "控制系统", "执行", "执行系统", "机器人"}
    return {str(value).strip().lower() for value in values if str(value or "").strip() and str(value).strip().lower() not in generic}


def identify_source_nodes(
    rows_by_source: dict[str, list[dict[str, Any]]], nodes: list[dict[str, Any]]
) -> tuple[list[tuple[str, dict[str, Any], str, str]], list[dict[str, Any]]]:
    """Conservative recognition: only a unique hierarchy-node match may become evidence."""
    identified = []
    conflicts = []
    keywords = [(str(node["node_id"]), _node_keywords(node)) for node in nodes]
    for source_name, rows in rows_by_source.items():
        for row in rows:
            code = str(row.get("code") or row.get("ts_code") or row.get("symbol") or "").strip()
            code = code.split(".")[0]
            text = _source_text(row)
            match_text = str(row.get("answer") or "").strip() if source_name == "interact_qa" else text
            if source_name == "interact_qa" and not any(term in match_text for term in ("生产", "销售", "供应", "交付", "量产", "业务", "产品", "订单", "收入")):
                continue
            lowered = match_text.lower()
            matches = sorted(node_id for node_id, terms in keywords if any(term in lowered for term in terms))
            if not re.fullmatch(r"\d{6}", code) or not text or not matches:
                continue
            if len(matches) == 1:
                identified.append((source_name, row, matches[0], text))
            else:
                # A cursor is a shared high-water mark (often one date), not a
                # source-record identity. Falling back to it collapses distinct
                # records under the same conflict primary key.
                identity = str(row.get("id") or row.get("source_id") or "").strip()
                fingerprint = hashlib.sha256(
                    json.dumps({"source": source_name, "code": code, "identity": identity, "text": text}, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest()
                conflicts.append({"source_name": source_name, "code": code, "node_ids": matches,
                                  "source_record_id": identity or fingerprint,
                                  "evidence_fingerprint": fingerprint})
    return identified, conflicts


def build_ranked_snapshot(run_id: str | None, audit_report: Any, candidates: list[dict[str, Any]], mappings: Any) -> dict[str, Any]:
    from embodied_refresh.audit import rank_node_leaders

    ranked = rank_node_leaders(candidates)
    mapping_rows = []
    for bucket in ("created", "updated", "unchanged"):
        for row in getattr(mappings, bucket, []):
            mapping_rows.append({
                "code": row.code, "node_id": row.node_id, "status": row.to_status,
                "mapping_id": row.mapping_id,
            })
    leaders = []
    for label, rows in (("formal", ranked.formal_top3), ("watch", ranked.watch_top3)):
        for rank, row in enumerate(rows, 1):
            leaders.append({
                "node_id": row.node_id or "unassigned", "rank": rank, "score": row.score,
                "code": row.code, "company_name": row.company_name, "candidate_label": label,
                "mapping_status": row.mapping_status, "dimension_scores": row.dimension_scores,
            })
    mapping_conflicts = [
        {"code": row.code, "node_ids": list(row.node_ids), "existing_node_id": row.existing_node_id,
         "proposed_node_id": row.proposed_node_id, "conflict_type": row.conflict_type,
         "review_status": row.review_status}
        for row in getattr(mappings, "conflicts", [])
    ]
    return {
        "run_id": run_id, "status": "success", "audit": asdict(audit_report),
        "leaders": leaders, "formal_top3": [row for row in leaders if row["candidate_label"] == "formal"],
        "watch_top3": [row for row in leaders if row["candidate_label"] == "watch"],
        "mappings": mapping_rows,
        "mapping_conflicts": mapping_conflicts,
    }


def retry_delivery(repository: Any, sender: Callable[..., Any], confirmer: Callable[..., bool]) -> list[Any]:
    from embodied_refresh.delivery import retry_due_batches

    return retry_due_batches(repository, sender, confirmer, now=datetime.now(timezone.utc))


def _lark_sender(chat_id: str, message: str, **kwargs: Any) -> Any:
    command = [
        "lark-cli", "im", "+messages-send", "--as", "bot", "--chat-id", chat_id,
        "--text", message, "--format", "json",
    ]
    if kwargs.get("idempotency_key"):
        command.extend(["--idempotency-key", str(kwargs["idempotency_key"])])
    process = subprocess.run(
        command,
        cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-500:] or "lark-cli send failed")
    return json.loads(process.stdout)


def _runtime_orchestrator(connection: Any, repository: Any, pg_url: str, targets: list[dict[str, str]]) -> EmbodiedRefreshOrchestrator:
    from embodied_refresh.audit import audit_chain
    from embodied_refresh.changes import ChangeBatch, diff_snapshots, render_change_digest
    from embodied_refresh.delivery import deliver_change_batch
    from embodied_refresh.evidence import normalize_evidence
    from embodied_refresh.mappings import MappingEvidence, apply_mapping_changes
    from embodied_refresh.models import RawEvidence
    from embodied_refresh.sources import fetch_incremental_sources
    from run_research_pipeline import confirm_message_delivery

    class FreshFailureRepository:
        def finish_run(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
            import psycopg2
            from embodied_refresh.repository import EmbodiedRefreshRepository
            fresh = psycopg2.connect(pg_url)
            try:
                EmbodiedRefreshRepository(fresh).finish_run(run_id, status, summary)
            finally:
                fresh.close()

    pending_conflicts: list[dict[str, Any]] = []

    def normalize(rows_by_source: dict[str, list[dict[str, Any]]]) -> list[MappingEvidence]:
        grouped: dict[tuple[str, str], list[Any]] = {}
        metadata: dict[tuple[str, str], dict[str, Any]] = {}
        identified, conflicts = identify_source_nodes(rows_by_source, repository.load_hierarchy_nodes())
        pending_conflicts[:] = conflicts
        for source_name, row, node_id, content in identified:
            code = str(row.get("code") or row.get("ts_code") or row.get("symbol") or "").strip()
            source_id = str(row.get("source_id") or row.get("id") or f"{source_name}:{code}:{row.get('source_cursor', '')}")
            raw = RawEvidence(
                source_id, source_name, content,
                _coerce_date(row.get("event_date") or row.get("ann_date") or row.get("pub_date")
                             or row.get("updated_at") or row.get("end_date") or row.get("source_cursor")),
                node_id, row.get("source_url"),
            )
            key = (code, node_id)
            grouped.setdefault(key, []).append(normalize_evidence(raw))
            metadata[key] = row
        return [
            MappingEvidence(code=code, chain_id="embodied_intelligence", node_id=node_id,
                            tag_name=str(metadata[(code, node_id)].get("tag_name") or node_id),
                            events=events, run_id=None,
                            source_names=tuple(sorted({event.source_type for event in events})))
            for (code, node_id), events in sorted(grouped.items())
        ]

    def apply(items: list[Any], run_id: str, as_of: date) -> Any:
        enriched = [type(item)(**{**item.__dict__, "run_id": run_id}) for item in items]
        if pending_conflicts:
            repository.save_identification_conflicts(run_id, pending_conflicts)
        return apply_mapping_changes(connection, enriched, as_of=as_of, persist=True, commit=False)

    def project(items: list[Any], _run_id: str | None, as_of: date, *, persist: bool = False) -> Any:
        return apply_mapping_changes(connection, items, as_of=as_of, persist=False)

    def audit(run_id: str | None, mappings: Any, mode: str) -> dict[str, Any]:
        report = audit_chain(connection, run_id or f"dry-run:{date.today().isoformat()}")
        return build_ranked_snapshot(run_id, report, repository.load_leader_candidates(), mappings)

    def diff(baseline: Any, current: dict[str, Any]) -> list[Any]:
        previous = getattr(baseline, "summary", {}).get("snapshot", baseline)
        return diff_snapshots(previous, current)

    def deliver(run_id: str, changes: list[Any], snapshot: dict[str, Any]) -> Any:
        message = render_change_digest(ChangeBatch(changes=changes, cutoff_time=datetime.now().isoformat(timespec="seconds")))
        if not message:
            return None
        return deliver_change_batch(repository, run_id, targets, message, _lark_sender, confirm_message_delivery)

    return EmbodiedRefreshOrchestrator(
        repository=repository,
        refresh_sources=lambda cursors, _date: fetch_incremental_sources(pg_url, cursors),
        normalize_evidence=normalize,
        apply_mappings=lambda items, run_id, as_of, persist=True: apply(items, run_id, as_of) if persist else project(items, run_id, as_of),
        rollback_mappings=connection.rollback,
        audit_and_rank=audit,
        diff_baseline=diff,
        deliver_changes=deliver,
        failure_repository_factory=FreshFailureRepository,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("dry-run", "apply", "audit", "retry-delivery"))
    parser.add_argument("--as-of-date", default=date.today().isoformat())
    parser.add_argument("--send-feishu", action="store_true")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", DEFAULT_PG_URL))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Runtime wiring is deliberately imported here so --help and unit tests stay side-effect free.
    import psycopg2
    from embodied_refresh.repository import EmbodiedRefreshRepository

    connection = psycopg2.connect(args.pg_url)
    try:
        repository = EmbodiedRefreshRepository(connection)
        if args.mode == "retry-delivery":
            from run_research_pipeline import confirm_message_delivery
            summaries = retry_delivery(repository, _lark_sender, confirm_message_delivery)
            print(json.dumps({"mode": args.mode, "batches": [asdict(row) for row in summaries]}, ensure_ascii=False, default=str))
            return 0
        config = json.loads((ROOT / "configs" / "scheduled_research.json").read_text(encoding="utf-8"))
        targets = config.get("chat_targets", [])
        orchestrator = _runtime_orchestrator(connection, repository, args.pg_url, targets)
        result = orchestrator.run(mode=args.mode, as_of_date=args.as_of_date, send_feishu=args.send_feishu)
        print(json.dumps(asdict(result), ensure_ascii=False, default=str))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
