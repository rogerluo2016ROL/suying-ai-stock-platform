# Task 6 Report: Idempotent Three-Group Delivery

## Result

- Added persistent delivery state for each `(change_batch_id, chat_id)` target.
- Each target stores its own confirmed `message_id`, `attempt_count`, and `next_retry_at`.
- Confirmed targets are never sent again.
- Unconfirmed messages with a `message_id` are confirmed again without resending.
- Failed/unconfirmed targets become due after 5, 15, and 30 minutes; compensation is invocation-driven and contains no sleep.
- A data-complete batch remains `data_success_delivery_incomplete` until every target is confirmed.
- Existing research-pipeline confirmation remains the default and is now dependency-injectable for tests.
- Targets are rejected unless they contain exactly three unique, non-empty chat IDs.
- A stable `embodied:{batch_id}:{chat_id}` idempotency key is passed to capable senders; legacy two-argument senders remain compatible.
- `scan_due_deliveries` and `retry_due_batches(repository, sender, confirmer, now)` provide production compensation entrypoints without sleeping or in-memory batch arguments. Message text and all target key/name/chat IDs are persisted in delivery detail for restart recovery.
- Due-time, terminal-state, and maximum-attempt checks execute atomically inside the claim lock. A not-yet-due row remains failed/unconfirmed with its original retry timestamp.
- Delivery errors reuse the pipeline redactor; configured Lark credentials and token-like values are not persisted.

## Concurrency and crash boundary

- A transaction advisory lock serializes the read/claim transition, while a session advisory lock remains held across sender, confirmer, and final save. This prevents two workers from sending the same target concurrently.
- The claim is committed as `sending` before the external call. If the process dies after Feishu accepts the request but before the final database save, exactly-once delivery cannot be proven locally. A later claim changes stale `sending` to `reconcile_required`; automatic compensation deliberately does not resend it. An operator must reconcile it against Feishu using the stable idempotency key or message history.
- Task 6 exposes the compensation function. Wiring its five-minute scheduler invocation belongs to Task 7.

## TDD Evidence

1. RED: focused command failed during collection with `ModuleNotFoundError: embodied_refresh.delivery`.
2. GREEN: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_embodied_refresh_repository.py tools/tests/test_run_research_manifest.py -q` passed: 50 tests.
3. Syntax: `python3 -m py_compile` passed for the changed Python modules.
4. Whitespace: `git diff --check` passed.
