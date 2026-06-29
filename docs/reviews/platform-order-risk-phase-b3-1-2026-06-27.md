# Platform Order Risk Phase B3-1 Review

> Date: 2026-06-27  
> Scope: trade-service order scope, paper/live risk verdict contract, audit payload enrichment  
> Verdict: Pass for B3-1. Live broker execution was not changed.

## Changes Reviewed

- `PlaceOrderRequest` now accepts optional:
  - `decision_context_id`
  - `candidate_id`
  - `plan_id`
- `POST /api/v1/trade/order` reads platform headers:
  - `X-Tenant-Id`
  - `X-Trade-Account-Id`
- Order responses include:
  - `tenant_id`
  - `owner_user_id`
  - `account_id`
  - `visibility`
  - `data_scope`
  - `order_scope`
  - `risk_verdict`
- Paper and live orders both run `pre_check` before execution.
- Rejected orders now write best-effort `RISK_REJECT` audit records.
- Successful orders write `PLACE_ORDER` audit details with `order_scope`, decision ids and `risk_verdict`.

## HTTP Evidence

Via frontend proxy `http://127.0.0.1:3010`:

- Valid paper order:
  - request: `300750 BUY 100 @ 10`
  - response: `200`
  - `order_id=ORD0001`
  - `tenant_id=tenant-default`
  - `account_id=paper-u105`
  - `decision_context_id=CTX-B3-1`
  - `risk_verdict.result=pass`
  - `risk_verdict.risk_check.checks.length=6`
- Rejected paper order:
  - request: `300750 BUY 100000 @ 1000`
  - response: `400`
  - `error_code=RISK_REJECT`
  - `detail.extra.result=reject`
  - `detail.extra.account_id=paper-u105`
  - `detail.extra.decision_context_id=CTX-B3-REJECT`

## Verification

Commands run:

```bash
cd services/trade-service && pytest tests/test_platform_account_view.py tests/test_broker_account_contract.py -q
python3 -m py_compile services/trade-service/app/platform_scope.py services/trade-service/app/routes.py services/trade-service/app/schemas.py
cd services/trade-service && pytest tests/ -q
```

Results:

- Focused trade tests: 6 passed.
- Full trade-service tests: 21 passed.
- Python compile checks passed.

## Residual Risk

- Candidate objects are not yet persisted as first-class resources.
- Audit log remains best-effort and queryable, but not yet wired to a cross-service immutable audit event model.
- Frontend order panel still needs UI-level display for `RiskVerdict` and candidate/plan lineage.
- QMT/live broker execution path was intentionally left untouched.

## Next Phase

B3-2 should promote screener picks into `Candidate` snapshots and carry `candidate_id` through `Candidate -> Plan -> Order -> RiskVerdict`.
