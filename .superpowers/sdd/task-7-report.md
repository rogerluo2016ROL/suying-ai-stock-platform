# Task 7 Report: Unified CLI and Scheduled Jobs

## Result

- Added one CLI for `dry-run`, `apply`, `audit`, and `retry-delivery`.
- The orchestrator enforces the required side-effect order. Mapping failures roll back, mark the run failed, and never persist changes, advance cursors, or deliver.
- `dry-run` performs no run, mapping, change, snapshot, cursor, or delivery writes.
- Delivery is attempted only for P0-P2 changes when `--send-feishu` is explicit; P3-only batches stay internal.
- Task 6's persisted `retry_due_batches` is wired to the `retry-delivery` CLI mode.
- Added daily 19:30 (including weekends), Sunday 20:30 audit, and five-minute delivery compensation schedules.
- All three embodied tasks use `calendar_scope=all_days`; the original four strategies retain their unchanged cron expressions and default trading-day gate.
- The five-minute task is repeatable and therefore is not suppressed after its first successful same-day invocation.

## TDD Evidence

1. RED: CLI tests initially failed because the unified module did not exist; scheduler tests failed because the three tasks and runner routing did not exist.
2. RED: the dry-run no-write assertion caught mapping execution and was fixed by using normalized preview rows without calling the mapping transaction.
3. RED: the repeatable retry test caught same-day duplicate suppression and was fixed with an explicit repeatable task flag.
4. GREEN: embodied focused suites passed: 66 passed, 1 skipped.
5. GREEN: scheduled research suite passed: 10 passed.
6. `py_compile`, CLI `--help`, and `git diff --check` passed.

## Review Remediation

- Replaced the placeholder empty leader list with persisted candidate loading and `rank_node_leaders`; formal/watch Top3 are saved with explicit labels and ranks.
- Delivery now atomically pre-creates all three pending target rows before the first external call, so compensation can reconstruct the full batch after an early failure.
- The orchestrator preserves `data_success_delivery_incomplete` and the structured delivery summary instead of overwriting it with success.
- Added conservative node recognition for the real five-source row shapes. Only one unique hierarchy keyword match becomes mapping evidence; ambiguous matches are persisted as `pending_review` conflicts.
- `audit` is now a strict read-only branch: no run row, source refresh, mapping transaction, snapshot/cursor write, or delivery.
- Failure handling rolls back first, records failure through a fresh connection with errors safely contained, re-raises the original exception, and closes the main connection in `finally`.

## Final Branch Review Remediation

- Mapping evidence now accumulates across batches: every event is linked to its mapping, stable event IDs are appended even without a status transition, and historical plus current valid evidence is evaluated together. A new mapping can become verified from one S source or two independent A sources in the same transaction.
- Evidence, mappings, transitions/conflicts, changes, leader snapshots and successful-source cursors now share one caller-owned data transaction. Delivery starts only after that transaction commits.
- Delivery no longer finalizes runs. The orchestrator owns the first terminal status; five-minute compensation uses a guarded three-confirmed-row transition from incomplete to success.
- Stale `sending` and `reconcile_required` rows are retried with the same deterministic Feishu UUID, allowing safe message-ID recovery instead of permanent suspension.
- Audit creates a traceable audit run and persists its audit/snapshot/terminal state while leaving mappings, cursors and delivery untouched.
- The scheduler records the embodied CLI's top-level `status`, `run_id` and `delivery_summary` verbatim.
- Migration 038 persists nullable trusted publisher identities. Historical reconstruction preserves missing identities as `None`; record IDs are never promoted to publisher identities.
- New mappings always record `NULL -> candidate`; same-batch S evidence records a second `candidate -> verified` transition. Same-day successful audit/apply runs are returned idempotently, while existing failed runs return `failed_existing` rather than fabricated success.
