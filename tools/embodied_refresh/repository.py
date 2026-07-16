from __future__ import annotations

import json
import hashlib
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import uuid4

from .models import DeliveryRecord, EvidenceChange, RefreshRun


TERMINAL_RUN_STATUSES = {"success", "data_success_delivery_incomplete", "failed"}


class EmbodiedRefreshRepository:
    def __init__(self, connection: Any, chain_id: str = "embodied_intelligence") -> None:
        self.connection = connection
        self.chain_id = chain_id

    @staticmethod
    def _run(row: Any) -> RefreshRun | None:
        return RefreshRun(*row) if row else None

    def begin_run(self, run_date: date, mode: str) -> RefreshRun:
        """Insert a running batch or return the existing idempotent batch."""
        # Match the database uniqueness boundary exactly: (run_date, mode).
        # Including chain_id here would give two contenders different locks
        # even though they still compete for the same unique database row.
        lock_key = f"embodied-refresh-run:{run_date.isoformat()}:{mode}"
        select_sql = """
                SELECT run_id, run_date, mode, status, summary, started_at, finished_at
                  FROM embodied_refresh_runs
                 WHERE run_date = %s AND mode = %s
        """
        insert_sql = """
                INSERT INTO embodied_refresh_runs
                    (run_id, run_date, mode, status, summary)
                VALUES (%s, %s, %s, 'running', '{}'::jsonb)
                RETURNING run_id, run_date, mode, status, summary, started_at, finished_at
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (lock_key,),
                )
                cursor.execute(select_sql, (run_date, mode))
                run = self._run(cursor.fetchone())
                if run is None:
                    cursor.execute(insert_sql, (str(uuid4()), run_date, mode))
                    run = self._run(cursor.fetchone())
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        if run is None:
            raise RuntimeError("begin_run did not return a refresh batch")
        return run

    def load_success_baseline(self, before_run_id: str) -> RefreshRun | None:
        """Return the newest earlier run whose status is success."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, run_date, mode, status, summary, started_at, finished_at
                  FROM embodied_refresh_runs
                 WHERE status = 'success'
                   AND run_date < (SELECT run_date FROM embodied_refresh_runs WHERE run_id = %s)
                 ORDER BY run_date DESC, started_at DESC
                 LIMIT 1
                """,
                (before_run_id,),
            )
            return self._run(cursor.fetchone())

    def load_cursors(self) -> dict[str, str]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT source_name, cursor_value FROM embodied_source_cursors WHERE chain_id = %s",
                (self.chain_id,),
            )
            return {str(row[0]): str(row[1]) for row in cursor.fetchall()}

    def save_snapshot(self, run_id: str, snapshot: Any) -> None:
        rows = snapshot if isinstance(snapshot, (list, tuple)) else snapshot.get("leaders", [])
        try:
            with self.connection.cursor() as cursor:
                for row in rows:
                    payload = row if isinstance(row, dict) else row.__dict__
                    cursor.execute(
                        """INSERT INTO embodied_leader_snapshots
                               (snapshot_id, run_id, node_id, rank, score, payload)
                           VALUES (%s,%s,%s,%s,%s,%s::jsonb)
                           ON CONFLICT (run_id, node_id, rank) DO NOTHING""",
                        (str(uuid4()), run_id, payload["node_id"], payload["rank"], payload["score"], json.dumps(payload, default=str)),
                    )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def load_hierarchy_nodes(self) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT node_id, display_name, COALESCE(metadata, '{}'::jsonb), layer_level
                     FROM supply_chain_hierarchy_nodes
                    WHERE chain_id IN ('embodied_intelligence','embodied')"""
            )
            return [
                {"node_id": row[0], "display_name": row[1], "metadata": row[2] or {}, "layer_level": row[3]}
                for row in cursor.fetchall()
            ]

    def load_leader_candidates(self) -> list[dict[str, Any]]:
        """Load persisted mapping/evidence state; ranking itself remains pure."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT m.code, COALESCE(s.name, m.code), m.node_id, m.status,
                          COALESCE(m.confidence, 0),
                          count(DISTINCT e.event_id)::integer,
                          count(DISTINCT e.event_id) FILTER (WHERE e.review_status='approved')::integer
                     FROM business_tag_mapping m
                     LEFT JOIN stocks s ON s.code=m.code
                     LEFT JOIN business_tag_evidence_events e
                       ON e.event_id IN (SELECT jsonb_array_elements_text(COALESCE(m.evidence_ids,'[]'::jsonb)))
                    WHERE m.chain_id IN ('embodied_intelligence','embodied')
                      AND m.status IN ('verified','candidate','weak_evidence','pending_review')
                    GROUP BY m.code, s.name, m.node_id, m.status, m.confidence"""
            )
            result = []
            for code, name, node_id, status, confidence, evidence_count, approved_count in cursor.fetchall():
                authenticity = 100.0 if status == "verified" else max(25.0, float(confidence or 0) * 100)
                quality = (100.0 * approved_count / evidence_count) if evidence_count else 0.0
                result.append({
                    "code": code, "company_name": name, "node_id": node_id, "mapping_status": status,
                    "business_authenticity": authenticity, "evidence_quality": quality,
                })
            return result

    def save_identification_conflicts(self, run_id: str, conflicts: list[dict[str, Any]]) -> None:
        """Stage ambiguous recognitions in the caller's mapping transaction."""
        with self.connection.cursor() as cursor:
            for conflict in conflicts:
                nodes = sorted(set(conflict["node_ids"]))
                source_record_id = str(conflict.get("source_record_id") or conflict.get("evidence_fingerprint") or "").strip()
                if not source_record_id:
                    source_record_id = hashlib.sha256(json.dumps(conflict, sort_keys=True).encode()).hexdigest()
                conflict_id = "EMB-IDENTIFY-" + hashlib.sha256(
                    (f"{self.chain_id}|{conflict['code']}|"
                     f"{conflict.get('evidence_fingerprint') or source_record_id}|{','.join(nodes)}").encode()
                ).hexdigest()[:24]
                cursor.execute(
                    """INSERT INTO embodied_mapping_conflicts
                           (conflict_id, run_id, chain_id, code, proposed_node_id,
                            conflict_type, status, source_record_ids, evidence_fingerprints,
                            source_names, proposed_node_ids)
                       VALUES (%s,%s,%s,%s,%s,'ambiguous_node_recognition','pending_review',%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb)
                       ON CONFLICT (conflict_id) DO NOTHING""",
                    (conflict_id, run_id, self.chain_id, conflict["code"], nodes[0],
                     json.dumps([source_record_id]), json.dumps([conflict.get("evidence_fingerprint") or source_record_id]),
                     json.dumps([conflict["source_name"]]), json.dumps(nodes)),
                )

    def save_cursor(self, source_name: str, cursor_value: str, run_id: str) -> None:
        """Advance one successful source cursor after the mapping transaction commits."""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO embodied_source_cursors
                        (chain_id, source_name, cursor_value, run_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (chain_id, source_name) DO UPDATE
                    SET cursor_value = EXCLUDED.cursor_value,
                        run_id = EXCLUDED.run_id,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (self.chain_id, source_name, cursor_value, run_id),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def save_changes(self, changes: list[EvidenceChange]) -> int:
        """Insert unseen change fingerprints and return the inserted count."""
        inserted = 0
        try:
            with self.connection.cursor() as cursor:
                # A stable order prevents two multi-change batches from taking
                # the same advisory locks in opposite order and deadlocking.
                for change in sorted(changes, key=lambda item: item.change_fingerprint):
                    cursor.execute(
                        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                        (f"embodied-refresh-change:{change.change_fingerprint}",),
                    )
                    cursor.execute(
                        """
                        SELECT 1 FROM embodied_evidence_changes
                         WHERE change_fingerprint = %s
                        """,
                        (change.change_fingerprint,),
                    )
                    if cursor.fetchone() is not None:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO embodied_evidence_changes
                            (change_fingerprint, run_id, node_id, change_type, payload)
                        VALUES (%s, %s, %s, %s, %s::jsonb)
                        RETURNING 1
                        """,
                        (
                            change.change_fingerprint,
                            change.run_id,
                            change.node_id,
                            change.change_type,
                            json.dumps(change.payload, ensure_ascii=False),
                        ),
                    )
                    inserted += int(cursor.fetchone() is not None)
            self.connection.commit()
            return inserted
        except Exception:
            self.connection.rollback()
            raise

    def finish_run(self, run_id: str, status: str, summary: dict[str, Any]) -> None:
        """Persist terminal run status and structured summary."""
        if status not in TERMINAL_RUN_STATUSES:
            raise ValueError(f"status must be terminal: {status}")
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE embodied_refresh_runs
                       SET status = %s, summary = %s::jsonb, finished_at = CURRENT_TIMESTAMP
                     WHERE run_id = %s AND status = 'running'
                    """,
                    (status, json.dumps(summary, ensure_ascii=False), run_id),
                )
                if cursor.rowcount != 1:
                    cursor.execute("SELECT status FROM embodied_refresh_runs WHERE run_id=%s", (run_id,))
                    existing = cursor.fetchone()
                    if existing is None:
                        raise LookupError(f"refresh run not found: {run_id}")
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    @staticmethod
    def _delivery(row: Any) -> DeliveryRecord | None:
        return DeliveryRecord(*row) if row else None

    def delivery(self, change_batch_id: str, chat_id: str) -> DeliveryRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT delivery_id, change_batch_id, chat_id, status, message_id,
                       detail, attempt_count, next_retry_at
                  FROM embodied_delivery_records
                 WHERE change_batch_id = %s AND chat_id = %s
                """,
                (change_batch_id, chat_id),
            )
            return self._delivery(cursor.fetchone())

    def initialize_deliveries(self, change_batch_id: str, targets: list[dict[str, str]], message: str, now: Any) -> None:
        """Atomically persist the complete recovery manifest before any external send."""
        try:
            with self.connection.cursor() as cursor:
                for target in targets:
                    detail = {
                        "target_key": target.get("key", ""), "target_name": target.get("name", ""),
                        "target_chat_id": target["chat_id"], "message": message,
                    }
                    cursor.execute(
                        """INSERT INTO embodied_delivery_records
                               (delivery_id, change_batch_id, chat_id, status, detail, attempt_count, next_retry_at)
                           VALUES (%s,%s,%s,'pending',%s::jsonb,0,%s)
                           ON CONFLICT (change_batch_id, chat_id) DO NOTHING""",
                        (str(uuid4()), change_batch_id, target["chat_id"], json.dumps(detail, ensure_ascii=False), now),
                    )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def deliveries(self, change_batch_id: str) -> list[DeliveryRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT delivery_id, change_batch_id, chat_id, status, message_id,
                       detail, attempt_count, next_retry_at
                  FROM embodied_delivery_records
                 WHERE change_batch_id = %s ORDER BY chat_id
                """,
                (change_batch_id,),
            )
            return [DeliveryRecord(*row) for row in cursor.fetchall()]

    def due_deliveries(self, now: Any) -> list[DeliveryRecord]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT delivery_id, change_batch_id, chat_id, status, message_id,
                          detail, attempt_count, next_retry_at
                     FROM embodied_delivery_records
                    WHERE next_retry_at <= %s
                      AND status IN ('pending','failed','unconfirmed')
                    ORDER BY next_retry_at, change_batch_id, chat_id""",
                (now,),
            )
            return [DeliveryRecord(*row) for row in cursor.fetchall()]

    @contextmanager
    def claim_delivery(self, change_batch_id: str, target: dict[str, str], now: Any):
        """Serialize one target and durably mark the crash window before sending."""
        chat_id = target["chat_id"]
        lock_key = f"embodied-delivery:{change_batch_id}:{chat_id}"
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
                cursor.execute(
                    """SELECT delivery_id, change_batch_id, chat_id, status, message_id,
                              detail, attempt_count, next_retry_at
                         FROM embodied_delivery_records
                        WHERE change_batch_id = %s AND chat_id = %s FOR UPDATE""",
                    (change_batch_id, chat_id),
                )
                existing = self._delivery(cursor.fetchone())
                if existing and existing.status == "sending":
                    cursor.execute(
                        "UPDATE embodied_delivery_records SET status='reconcile_required', next_retry_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE delivery_id=%s",
                        (existing.delivery_id,),
                    )
                    self.connection.commit()
                    yield None
                    return
                if existing and existing.status in {"confirmed", "reconcile_required"}:
                    self.connection.commit()
                    yield None
                    return
                if existing and (
                    existing.attempt_count >= 4
                    or (existing.next_retry_at is not None and existing.next_retry_at > now)
                ):
                    self.connection.commit()
                    yield None
                    return
                if existing is None:
                    existing = DeliveryRecord(str(uuid4()), change_batch_id, chat_id, "pending")
                cursor.execute(
                    """INSERT INTO embodied_delivery_records
                           (delivery_id, change_batch_id, chat_id, status, message_id, detail, attempt_count, next_retry_at)
                       VALUES (%s,%s,%s,'sending',%s,%s::jsonb,%s,NULL)
                       ON CONFLICT (change_batch_id, chat_id) DO UPDATE SET status='sending', next_retry_at=NULL, updated_at=CURRENT_TIMESTAMP
                       WHERE embodied_delivery_records.status NOT IN ('confirmed','sending','reconcile_required')""",
                    (existing.delivery_id, change_batch_id, chat_id, existing.message_id, json.dumps(existing.detail), existing.attempt_count),
                )
            self.connection.commit()
            yield existing
        except Exception:
            self.connection.rollback()
            raise
        finally:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_key,))

    def save_delivery(self, record: DeliveryRecord) -> None:
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"embodied-delivery:{record.change_batch_id}:{record.chat_id}",),
                )
                cursor.execute(
                    """
                    INSERT INTO embodied_delivery_records
                        (delivery_id, change_batch_id, chat_id, status, message_id,
                         detail, attempt_count, next_retry_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (change_batch_id, chat_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        message_id = EXCLUDED.message_id,
                        detail = EXCLUDED.detail,
                        attempt_count = EXCLUDED.attempt_count,
                        next_retry_at = EXCLUDED.next_retry_at,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE embodied_delivery_records.status <> 'confirmed'
                    """,
                    (
                        record.delivery_id,
                        record.change_batch_id,
                        record.chat_id,
                        record.status,
                        record.message_id,
                        json.dumps(record.detail, ensure_ascii=False),
                        record.attempt_count,
                        record.next_retry_at,
                    ),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
