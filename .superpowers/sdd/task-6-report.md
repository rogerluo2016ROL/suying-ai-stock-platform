# Task 6 Report: Idempotent Three-Group Delivery

## Result

- Added persistent delivery state for each `(change_batch_id, chat_id)` target.
- Each target stores its own confirmed `message_id`, `attempt_count`, and `next_retry_at`.
- Confirmed targets are never sent again.
- Unconfirmed messages with a `message_id` are confirmed again without resending.
- Failed/unconfirmed targets become due after 5, 15, and 30 minutes; compensation is invocation-driven and contains no sleep.
- A data-complete batch remains `data_success_delivery_incomplete` until every target is confirmed.
- Existing research-pipeline confirmation remains the default and is now dependency-injectable for tests.

## TDD Evidence

1. RED: focused command failed during collection with `ModuleNotFoundError: embodied_refresh.delivery`.
2. GREEN: `bash tools/codex-lowio.sh py tools/tests/test_embodied_refresh_delivery.py tools/tests/test_embodied_refresh_repository.py tools/tests/test_run_research_manifest.py -q` passed: 39 tests.
3. Syntax: `python3 -m py_compile` passed for the changed Python modules.
4. Whitespace: `git diff --check` passed.
