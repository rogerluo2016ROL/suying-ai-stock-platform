from __future__ import annotations

import json
from datetime import date
from typing import Any
from uuid import uuid4

from .models import EvidenceChange, RefreshRun


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
        sql = """
            WITH existing AS (
                SELECT run_id, run_date, mode, status, summary, started_at, finished_at
                  FROM embodied_refresh_runs
                 WHERE run_date = %s AND mode = %s
            ), inserted AS (
                INSERT INTO embodied_refresh_runs
                    (run_id, run_date, mode, status, summary)
                SELECT %s, %s, %s, 'running', '{}'::jsonb
                 WHERE NOT EXISTS (SELECT 1 FROM existing)
                RETURNING run_id, run_date, mode, status, summary, started_at, finished_at
            )
            SELECT * FROM inserted
            UNION ALL
            SELECT * FROM existing
            LIMIT 1
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(sql, (run_date, mode, str(uuid4()), run_date, mode))
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
                for change in changes:
                    cursor.execute(
                        """
                        INSERT INTO embodied_evidence_changes
                            (change_fingerprint, run_id, node_id, change_type, payload)
                        SELECT %s, %s, %s, %s, %s::jsonb
                         WHERE NOT EXISTS (
                            SELECT 1 FROM embodied_evidence_changes
                             WHERE change_fingerprint = %s
                         )
                        RETURNING 1
                        """,
                        (
                            change.change_fingerprint,
                            change.run_id,
                            change.node_id,
                            change.change_type,
                            json.dumps(change.payload, ensure_ascii=False),
                            change.change_fingerprint,
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
                     WHERE run_id = %s
                    """,
                    (status, json.dumps(summary, ensure_ascii=False), run_id),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
