# Platform Foundation Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first engineering layer for the platformized cloud/multi-tenant design: visible platform context in the frontend, stable platform scope types, backend tenant context dependencies, and safe API propagation without changing real-money order execution behavior.

**Architecture:** Phase A is an additive foundation. Frontend gets `PlatformSession`/`PlatformScope` types and a reusable `PlatformContextBar`; backend gets tenant/account context parsing dependencies and schemas that can be consumed by services later. Trade execution paths are not changed in Phase A; they only display platform/account mode until the BrokerAdapter implementation is reviewed separately.

**Tech Stack:** React 18 + TypeScript 5.6 + Ant Design 5.22 + Vitest; FastAPI + Pydantic v2 + SQLAlchemy; PostgreSQL remains the target persistence layer, but Phase A avoids schema migrations unless a task explicitly says otherwise.

## Global Constraints

- Do not modify live order execution, QMT/Xtquant execution, `BrokerInterface`, `auto_trading_executor`, or account money movement in Phase A.
- All platform-private objects must be modeled with `tenantId`, optional `ownerUserId`, optional `accountId`, `visibility`, and `dataScope`.
- Existing roles remain `admin | internal_analyst | external_analyst | user`; map them to role views instead of renaming auth roles.
- Frontend must continue working when backend `/api/v1/auth/me` does not yet return tenant/account fields; use deterministic defaults.
- Tests must cover the fallback path and role-view mapping.
- Use existing design language: Ant Design, current CSS variables, compact operational UI.
- No new npm or Python dependencies.

---

### Task 1: Frontend Platform Session Types And Context Bar

**Files:**
- Create: `frontend/src/types/platform.ts`
- Create: `frontend/src/components/layout/PlatformContextBar.tsx`
- Modify: `frontend/src/components/layout/index.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/__tests__/PlatformContextBar.test.tsx`
- Test: `frontend/src/__tests__/PlatformContextBar.test.tsx`

**Interfaces:**
- Produces: `PlatformSession`, `PlatformScope`, `buildPlatformSessionFromUser(user)`, `roleToRoleView(role)`.
- Produces: `<PlatformContextBar session={platformSession} />`.
- Consumes: `Role` and `User` from `frontend/src/contexts/AuthContext.tsx`.

- [x] **Step 1: Write the failing component tests**

Create `frontend/src/__tests__/PlatformContextBar.test.tsx` with tests that render admin and user sessions and assert visible role view, tenant, account, data scope, and broker mode text.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/__tests__/PlatformContextBar.test.tsx`

Expected: FAIL because `PlatformContextBar` and platform types do not exist.

- [x] **Step 3: Add platform scope types**

Create `frontend/src/types/platform.ts` exporting:

```ts
import type { Role, User } from '../contexts/AuthContext'

export type RoleView = 'trader' | 'investor' | 'admin'
export type Visibility = 'private' | 'tenant_shared' | 'public'
export type DataScope = 'public' | 'tenant' | 'user' | 'account'
export type TradeMode = 'paper' | 'live'

export interface PlatformScope {
  tenantId: string
  ownerUserId?: string
  accountId?: string
  visibility: Visibility
  dataScope: DataScope
}

export interface PlatformSession extends PlatformScope {
  roleView: RoleView
  tenantName: string
  userName: string
  tradeMode: TradeMode
  brokerAdapter: 'paper' | 'xtquant_qmt' | 'broker_rest'
  cloudReady: boolean
}

export function roleToRoleView(role: Role): RoleView {
  if (role === 'admin') return 'admin'
  if (role === 'user') return 'investor'
  return 'trader'
}

export function buildPlatformSessionFromUser(user: User | null): PlatformSession {
  const role = user?.role ?? 'user'
  const roleView = roleToRoleView(role)
  const fallbackTenantId = roleView === 'admin' ? 'platform' : 'tenant-default'
  return {
    tenantId: user?.tenantId || fallbackTenantId,
    tenantName: user?.tenantName || (roleView === 'admin' ? '平台运营' : '默认租户'),
    ownerUserId: user ? String(user.id) : undefined,
    accountId: user?.defaultTradeAccountId || (roleView === 'admin' ? undefined : 'paper-default'),
    visibility: roleView === 'admin' ? 'tenant_shared' : 'private',
    dataScope: roleView === 'admin' ? 'tenant' : 'account',
    roleView,
    userName: user?.name || '未登录用户',
    tradeMode: user?.tradeMode || 'paper',
    brokerAdapter: user?.brokerAdapter || 'paper',
    cloudReady: true,
  }
}
```

- [x] **Step 4: Extend AuthContext user type**

Modify `frontend/src/contexts/AuthContext.tsx` `User` to include optional platform fields:

```ts
tenantId?: string
tenantName?: string
defaultTradeAccountId?: string
tradeMode?: 'paper' | 'live'
brokerAdapter?: 'paper' | 'xtquant_qmt' | 'broker_rest'
```

When setting user from `/me`, login, and register, pass through these optional fields if present.

- [x] **Step 5: Add PlatformContextBar**

Create `frontend/src/components/layout/PlatformContextBar.tsx` using Ant Design `Space`, `Tag`, `Typography`, `Tooltip`, and `CloudOutlined`/`SafetyCertificateOutlined`. It must display:

- role view label: `操盘手`, `个人投资者`, or `系统管理员`
- tenant name and id
- account id or `未绑定交易账户`
- `公共+私有隔离`
- trade mode: `模拟盘` or `实盘`
- broker adapter: `paper`, `xtquant_qmt`, or `broker_rest`

- [x] **Step 6: Export and wire into App layout**

Modify `frontend/src/components/layout/index.ts` to export the component and types.

Modify `frontend/src/App.tsx`:

```ts
import { PlatformContextBar } from './components/layout'
import { buildPlatformSessionFromUser } from './types/platform'
```

Then compute:

```ts
const platformSession = useMemo(() => buildPlatformSessionFromUser(user), [user])
```

Render `<PlatformContextBar session={platformSession} />` directly below the existing `Header` and above `Content`.

- [x] **Step 7: Run focused tests**

Run: `cd frontend && npx vitest run src/__tests__/PlatformContextBar.test.tsx src/__tests__/AuthContext.test.tsx src/__tests__/ProtectedRoute.test.tsx`

Expected: PASS.

- [x] **Step 8: Run TypeScript check**

Run: `cd frontend && npx tsc -b --noEmit`

Expected: PASS.

---

### Task 2: Backend Tenant Context Dependency

**Files:**
- Create: `backend/app/schemas/platform.py`
- Create: `backend/app/api/platform_deps.py`
- Test: `backend/tests/test_platform_context.py`

**Interfaces:**
- Produces: `PlatformContext`, `get_platform_context`, and `require_account_scope`.
- Consumes: existing `get_current_user`.

Steps:

- [x] Write tests for default tenant context from current user.
- [x] Implement Pydantic schema with `tenant_id`, `user_id`, `role`, `account_id`, `role_view`.
- [x] Implement dependency that reads `X-Tenant-Id` and `X-Trade-Account-Id` but does not trust them for cross-tenant access.
- [x] Run `cd backend && .venv/bin/pytest tests/test_platform_context.py -v`.

---

### Task 3: API Client Platform Headers

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/__tests__/apiPlatformHeaders.test.ts`

**Interfaces:**
- Produces: `injectPlatformContext(getContext)`.
- Consumes: `PlatformSession`.

Steps:

- [x] Add tests proving `X-Tenant-Id` and `X-Trade-Account-Id` are attached only when present.
- [x] Implement `injectPlatformContext`.
- [x] Wire it from `AuthContext` or `App` without breaking existing `injectAuth`.
- [x] Run focused API tests.

---

### Task 4: Read-Only Broker Account Contract

**Files:**
- Create: `services/trade-service/app/platform_schemas.py`
- Create: `services/trade-service/tests/test_broker_account_contract.py`
- Do not modify real broker execution methods.

**Interfaces:**
- Produces: `BrokerAccountView` and `BrokerAdapterCapability`.

Steps:

- [x] Test schema validation for paper and xtquant views.
- [x] Implement read-only schemas.
- [x] Run `cd services/trade-service && pytest tests/test_broker_account_contract.py -v`.

---

### Task 5: Phase A Integration Audit

**Files:**
- Modify: `docs/design/New design/01 PRD 文档/0.5 平台化详细方案设计.md`
- Create: `docs/reviews/platform-foundation-phase-a-2026-06-27.md`

**Interfaces:**
- Consumes outputs from Tasks 1-4.

Steps:

- [x] Document implemented interfaces and remaining Phase B work.
- [x] Run frontend focused tests, backend context tests, trade schema tests.
- [x] Run `git diff --stat`.
- [x] Record risks: real trading execution still unchanged, QMT gateway still design-only.
