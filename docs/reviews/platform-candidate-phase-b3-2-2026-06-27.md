# Platform Candidate Phase B3-2 Review

> Date: 2026-06-27  
> Scope: screener Candidate snapshot contract, Candidate -> Plan field preservation, frontend type support  
> Verdict: Pass for B3-2.

## Changes Reviewed

- `screener-service` now adds Candidate snapshot fields in `_normalize_picks`:
  - `candidate_id`
  - `source_module`
  - `source_mode`
  - `visibility`
  - `data_scope`
- Candidate ID is deterministic: `CAND-{mode}-{code}`.
- Frontend `ScreenerPick` and `StrategyPick` types include Candidate fields.
- `Screener.generatePlan` preserves Candidate fields and adds a fallback for old cached picks.
- `strategy-service` plan-store tests now assert candidate snapshot fields are preserved inside Plan picks.

## Verification

Commands run:

```bash
cd services/screener-service && pytest tests/test_candidate_contract.py -q
python3 -m py_compile services/screener-service/app/routers/screener.py
cd services/strategy-service && pytest tests/test_plan_store_platform_scope.py tests/test_platform_scope.py -q
cd frontend && npx tsc -b --noEmit
cd frontend && npm run build
```

Results:

- Screener Candidate contract test: 1 passed.
- Strategy platform scope tests: 5 passed.
- Frontend TypeScript check passed.
- Frontend build passed.

Known warnings:

- Existing Vite chunk-size warning for `antd` and `echarts`.

## Residual Risk

- Candidate is still a snapshot field on screener output and Plan picks, not a persisted table.
- UI does not yet surface Candidate lineage or saved/private status.
- Order panel does not yet auto-fill `candidate_id/plan_id/decision_context_id` from selected Plan pick.

## Next Phase

B3-3 should wire the frontend P0 chain visibly: Candidate list -> Plan detail -> Order panel -> RiskVerdict display.
