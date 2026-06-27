# Platform Persistence Phase B1 Review

> Date: 2026-06-27  
> Scope: tenant/membership/broker-account persistence contracts and auth platform profile fields  
> Verdict: ready for Phase B2 resource-scope wiring; live broker execution remains untouched.

## 1. Implemented

### Backend Persistence

- `backend/app/models/platform.py`
  - `Tenant`
  - `Membership`
  - `BrokerAccount`
- `backend/alembic/versions/014_platform_tenant_accounts.py`
  - creates `tenants`, `memberships`, `broker_accounts`
  - adds tenant/user/account indexes and uniqueness constraints
- `backend/app/models/user.py`
  - adds `User.memberships`
  - adds `User.broker_accounts`

### Backend Auth Profile

- `backend/app/schemas/auth.py`
  - `UserResponse` and `TokenUserResponse` now include optional platform fields.
- `backend/app/routers/auth.py`
  - `build_token_user_response(user)`
  - `build_user_response(user)`
  - deterministic fallback profile when tenant/account relationships are not loaded.

### Frontend Auth Normalization

- `frontend/src/contexts/AuthContext.tsx`
  - `normalizeAuthUserPayload(payload)`
  - supports both snake_case and camelCase platform fields.

## 2. Verification Evidence

```text
cd backend && .venv/bin/pytest \
  tests/test_platform_models.py \
  tests/test_auth_platform_profile.py \
  tests/test_platform_context.py \
  tests/test_auth.py -q

Result: 25 passed, with existing dev-secret warnings.
```

```text
cd frontend && npx vitest run \
  src/__tests__/AuthContext.test.tsx \
  src/__tests__/apiClientPlatformContext.test.ts \
  src/__tests__/PlatformContextBar.test.tsx \
  src/__tests__/ProtectedRoute.test.tsx

Result: 4 test files passed, 22 tests passed.
```

```text
cd frontend && npx tsc -b --noEmit
Result: exit 0.
```

```text
cd frontend && npm run build
Result: build passed. Existing antd/echarts chunk-size warning remains.
```

```text
cd backend && .venv/bin/python -m py_compile \
  alembic/versions/014_platform_tenant_accounts.py \
  app/models/platform.py \
  app/routers/auth.py \
  app/schemas/auth.py

Result: exit 0.
```

## 3. Guardrails Preserved

- No live order execution was changed.
- No `BrokerInterface` behavior was changed.
- No `XtquantBroker` behavior was changed.
- Migration file was added but not applied to a live database in this phase.
- Auth response defaults keep old environments usable while persistence adoption is staged.

## 4. Phase B2 Next Work

- Apply migration in a controlled backend environment.
- Seed default platform tenant and paper broker accounts.
- Explicitly load platform relationships in auth queries after migration is present.
- Wire `get_platform_context` into private resource APIs.
- Add tenant/account filters to Candidate, Plan, Backtest, RiskVerdict, and Order storage.
- Add audit records before enabling any live broker channel.
