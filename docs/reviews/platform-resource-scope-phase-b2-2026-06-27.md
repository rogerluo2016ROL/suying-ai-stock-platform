# Platform Resource Scope Phase B2 Review

> Date: 2026-06-27  
> Scope: auth platform defaults, strategy Plan isolation, trade paper account view, frontend proxy smoke test  
> Verdict: Pass for Phase B2. Do not use this as approval for live trading changes.

## Changes Reviewed

- Auth now returns platform fields on login, register and `/api/v1/auth/me`.
- New users receive deterministic defaults during registration:
  - `tenant_id=tenant-default`
  - `default_trade_account_id=paper-u{userId}`
  - `trade_mode=paper`
  - `broker_adapter=paper`
- Strategy plans carry:
  - `tenant_id`
  - `owner_user_id`
  - `account_id`
  - `visibility`
  - `data_scope`
- Strategy plan reads and writes now filter by tenant/user/account scope.
- Trade paper account view returns platform boundary fields without changing live broker or order execution paths.

## HTTP Evidence

Clean local ports used:

- auth: `http://127.0.0.1:9021`
- strategy: `http://127.0.0.1:8023`
- trade: `http://127.0.0.1:8026`
- frontend: `http://127.0.0.1:3010`

Observed responses:

- Admin login returned `tenant_id=platform`, `tenant_name=平台运营`, `default_trade_account_id=null`.
- User registration returned `tenant_id=tenant-default`, `default_trade_account_id=paper-u105`.
- Strategy create returned plan scope `tenant-default / owner_user_id=105 / account_id=paper-u105 / data_scope=account`.
- Trade paper account returned `tenant-default / owner_user_id=105 / account_id=paper-u105`.
- A second user `paper-u106` listed strategy plans and received `total=0`, confirming private plan isolation.
- Frontend proxy on `3010` returned the same login and trade account scope.

## Verification

Commands run:

```bash
backend/.venv/bin/pytest backend/tests/test_platform_seed_service.py backend/tests/test_platform_models.py backend/tests/test_auth_platform_profile.py backend/tests/test_auth.py -q
cd backend && DATABASE_TEST_NULLPOOL=1 .venv/bin/pytest tests/sit/test_auth_integration.py::TestRegister::test_register_returns_tokens_and_user tests/sit/test_auth_integration.py::TestLogin::test_login_returns_access_token_and_user tests/sit/test_auth_integration.py::TestMe::test_me_returns_user_info -q
cd services/trade-service && pytest tests/test_platform_account_view.py tests/test_broker_account_contract.py -q
backend/.venv/bin/python -m py_compile backend/app/services/auth_service.py backend/app/routers/auth.py backend/app/services/platform_service.py
python3 -m py_compile services/trade-service/app/platform_scope.py services/trade-service/app/routes.py
cd frontend && npx tsc -b --noEmit
cd frontend && npx vitest run src/__tests__/AuthContext.test.tsx src/__tests__/apiClientPlatformContext.test.ts src/__tests__/PlatformContextBar.test.tsx src/__tests__/ProtectedRoute.test.tsx
cd frontend && npm run build
```

Results:

- Backend unit/platform auth tests: 23 passed.
- Backend auth SIT subset: 3 passed.
- Trade service tests: 4 passed.
- Frontend platform/auth tests: 22 passed.
- Frontend build passed.

Known warnings:

- Dev-only secret fallback warnings for `JWT_SECRET_KEY`, `ADMIN_PASSWORD`, and `KRONOS_SERVICE_SECRET`.
- Existing Vite chunk-size warning for `antd` and `echarts`.

## Residual Risk

- Existing already-running services on ports `9001`, `8003`, `8006`, and `3000` may be old processes. The verified usable stack is on `9021`, `8023`, `8026`, and `3010`.
- Candidate, Order, RiskVerdict, Audit and RiskGate forced linkage are not yet complete.
- No live trading path was changed or approved.

## Next Phase

Phase B3 should wire Candidate -> Plan -> Order -> RiskVerdict with append-only audit records before any broker adapter expansion or QMT live trading work.
