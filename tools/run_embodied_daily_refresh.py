#!/usr/bin/env python3
"""具身智能每日刷新、审计与送达补偿的统一入口。"""

from __future__ import annotations

import argparse
import json
import os
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
    ) -> None:
        self.repository = repository
        self.refresh_sources = refresh_sources
        self.normalize_evidence = normalize_evidence
        self.apply_mappings = apply_mappings
        self.rollback_mappings = rollback_mappings
        self.audit_and_rank = audit_and_rank
        self.diff_baseline = diff_baseline
        self.deliver_changes = deliver_changes

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
        persisted = mode != "dry-run"
        run = self.repository.begin_run(run_date, mode) if persisted else None
        run_id = getattr(run, "run_id", None)
        try:
            cursors = self.repository.load_cursors()
            refreshed = self.refresh_sources(cursors, run_date)
            normalized = self.normalize_evidence(refreshed.rows)
            if persisted:
                try:
                    mappings = self.apply_mappings(normalized, run_id, run_date)
                except Exception:
                    self.rollback_mappings()
                    raise
            else:
                mappings = normalized
            snapshot = self.audit_and_rank(run_id, mappings, mode)
            baseline = self.repository.load_success_baseline(run_id) if persisted else None
            detected = changes if changes is not None else (
                self.diff_baseline(baseline, snapshot) if baseline is not None else []
            )
            if persisted:
                self.repository.save_changes(detected)
                self.repository.save_snapshot(run_id, snapshot)

            publishable = [row for row in detected if _priority(row) in PUBLISHABLE_PRIORITIES]
            delivery_attempted = bool(persisted and send_feishu and publishable)
            if delivery_attempted:
                self.deliver_changes(run_id, publishable, snapshot)

            if persisted:
                successful = set(refreshed.rows) - set(refreshed.errors)
                for source in sorted(successful):
                    cursor = refreshed.next_cursors.get(source)
                    if cursor is not None:
                        self.repository.save_cursor(source, cursor, run_id)
                self.repository.finish_run(run_id, "success", {
                    "changes": len(detected), "source_errors": refreshed.errors, "snapshot": snapshot,
                })
            return RefreshResult(mode, run_id, persisted, delivery_attempted, len(detected), refreshed.errors)
        except Exception:
            if persisted and run_id is not None:
                self.repository.finish_run(run_id, "failed", {"failed_at": datetime.now(timezone.utc).isoformat()})
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

    def normalize(rows_by_source: dict[str, list[dict[str, Any]]]) -> list[MappingEvidence]:
        grouped: dict[tuple[str, str], list[Any]] = {}
        metadata: dict[tuple[str, str], dict[str, Any]] = {}
        for source_name, rows in rows_by_source.items():
            for row in rows:
                code = str(row.get("code") or row.get("ts_code") or "").strip()
                node_id = str(row.get("node_id") or "").strip()
                content = str(row.get("content") or row.get("title") or row.get("main_business") or "").strip()
                if not code or not node_id or not content:
                    continue
                source_id = str(row.get("source_id") or row.get("id") or f"{source_name}:{code}:{row.get('source_cursor', '')}")
                raw = RawEvidence(
                    source_id, source_name, content,
                    _coerce_date(row.get("event_date") or row.get("ann_date") or row.get("pub_date")),
                    node_id, row.get("source_url"),
                )
                key = (code, node_id)
                grouped.setdefault(key, []).append(normalize_evidence(raw))
                metadata[key] = row
        return [
            MappingEvidence(code=code, chain_id="embodied_intelligence", node_id=node_id,
                            tag_name=str(metadata[(code, node_id)].get("tag_name") or node_id),
                            events=events, run_id=None)
            for (code, node_id), events in sorted(grouped.items())
        ]

    def apply(items: list[Any], run_id: str, as_of: date) -> Any:
        enriched = [type(item)(**{**item.__dict__, "run_id": run_id}) for item in items]
        return apply_mapping_changes(connection, enriched, as_of=as_of)

    def audit(run_id: str | None, mappings: Any, mode: str) -> dict[str, Any]:
        report = audit_chain(connection, run_id or f"dry-run:{date.today().isoformat()}")
        mapping_rows = []
        for bucket in ("created", "updated", "unchanged"):
            for row in getattr(mappings, bucket, []):
                mapping_rows.append({
                    "code": row.code, "node_id": row.node_id, "status": row.to_status,
                    "mapping_id": row.mapping_id,
                })
        return {
            "run_id": run_id, "status": "success", "audit": asdict(report),
            "leaders": [], "mappings": mapping_rows,
        }

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
        apply_mappings=apply,
        rollback_mappings=connection.rollback,
        audit_and_rank=audit,
        diff_baseline=diff,
        deliver_changes=deliver,
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


if __name__ == "__main__":
    raise SystemExit(main())
