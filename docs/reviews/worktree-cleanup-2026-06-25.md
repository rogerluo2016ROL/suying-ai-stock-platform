# Worktree Cleanup Notes - 2026-06-25

## Current Branch

- Branch: `feat/data-service-compose-pgonly`
- Remote: `origin/feat/data-service-compose-pgonly`
- PR: `#5` is open as draft.

## Safe Commit Group: Data-Service Readiness

These files belong to the current follow-up and can be committed together after verification:

- `services/data-service/app/config.py`
- `services/data-service/app/routers/data.py`
- `services/data-service/app/scheduler.py`
- `services/data-service/app/sync/rt_min.py`
- `services/data-service/tests/test_runtime_readiness.py`
- `services/data-service/tests/test_auction_verification_script.py`
- `tools/verify_auction_collection.py`
- `docs/reviews/worktree-cleanup-2026-06-25.md`

## Already-Staged Unrelated Work

These files were already staged before this follow-up. Do not include them in the data-service readiness commit unless explicitly requested:

- `backend/alembic/versions/013_industry_chain_deconstruct.py`
- `backend/tests/sit/test_industry_chain_tables.py`
- `packages/kronos-factors/kronos_factors/engine/chain_deconstruct.py`
- `packages/kronos-factors/kronos_factors/engine/supply_chain_bom_v5.py`
- `packages/kronos-factors/tests/test_chain_deconstruct.py`
- `packages/kronos-factors/tests/test_resonance_v6.py`
- `services/screener-service/app/llm_multi_provider.py`
- `services/screener-service/app/llm_policy_interpret.py`
- `services/screener-service/app/main.py`
- `services/screener-service/app/routers/screener.py`
- `services/screener-service/pyproject.toml`
- `services/screener-service/tests/test_chain_api.py`
- `services/screener-service/tests/test_chain_candidates_api.py`
- `services/screener-service/tests/test_llm_multi_provider.py`
- `services/screener-service/tests/test_llm_policy_interpret.py`
- `services/screener-service/tests/test_policy_interpret_api.py`
- `tools/migrate_v4_to_chain_nodes.py`
- `tools/resonance_ic_validation.py`
- progress/output files under `.claude/`, `progress/`, and `outputs/`

## Unstaged Unrelated Work

These modified files should be reviewed as separate model/data tasks:

- `packages/kronos-data/kronos_data/backfill_financial.py`
- `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
- `packages/kronos-factors/kronos_factors/engine/supply_chain.py`
- `services/screener-service/app/llm_supply_chain.py`
- `tools/backtest_bi_trend.py`
- `tools/walk_forward.py`
- report and output changes under `docs/superpowers/specs/` and `outputs/`

## Untracked Work

Likely source files that deserve separate review:

- `packages/kronos-factors/kronos_factors/engine/bi_alpha_v15.py`
- `packages/kronos-factors/kronos_factors/engine/supply_chain_foundation.py`
- `packages/kronos-factors/tests/test_bi_alpha_v15.py`
- `packages/kronos-factors/tests/test_supply_chain_foundation.py`
- `services/screener-service/tests/test_supply_chain_foundation_api.py`
- `tools/build_supply_chain_foundation.py`
- `tools/factor_ic_probe.py`

Likely generated or local-only files:

- `.superpowers/`
- `outputs/afternoon_trend_full/`
- `outputs/bi_trend_launch/`
- `outputs/bt_v14_2026-*.json`
- `outputs/factor_ic_probe*.json`
- `outputs/walk_forward_2024-2025_v14.json`
- `outputs/wf_v14_run.log`

## Recommendation

1. Commit the data-service readiness group by explicit pathspec only.
2. Keep the staged unrelated files staged for now, but do not mix them into PR #5.
3. Split remaining source work into separate commits: industry-chain schema/API, multi-LLM policy interpretation, BI alpha v15, and supply-chain foundation.
4. Treat generated `outputs/` files as evidence artifacts; commit only the ones required by a review or report.
