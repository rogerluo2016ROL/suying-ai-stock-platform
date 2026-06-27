# Platform Persistence Phase B1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first persistent platform identity layer: tenant, membership, broker account contracts, and auth profile fields that frontend platform context can consume.

**Architecture:** Keep this phase additive and non-executing. Backend gets SQLAlchemy models, an Alembic migration, Pydantic auth profile fields, and pure helpers that resolve platform defaults without touching live trading. Frontend keeps the Phase A context bar but accepts both snake_case and camelCase auth payloads.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy + Alembic; React 18 + TypeScript + Vitest.

## Global Constraints

- Do not modify live order execution, QMT/Xtquant execution, `BrokerInterface`, `auto_trading_executor`, or account money movement.
- Do not apply migrations against a live database in this step; only add migration files and model/tests.
- Existing roles remain `admin | internal_analyst | external_analyst | user`.
- Auth responses must remain backward-compatible for existing clients.
- Frontend must tolerate both `tenantId` and `tenant_id` style fields.
- No new npm or Python dependencies.

---

### Task 1: Backend Platform Persistence Models

**Files:**
- Create: `backend/app/models/platform.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/014_platform_tenant_accounts.py`
- Create: `backend/tests/test_platform_models.py`

**Interfaces:**
- Produces: `Tenant`, `Membership`, `BrokerAccount`.
- Consumes: existing `User` model.

- [x] Write failing tests for metadata tables and relationships.
- [x] Add SQLAlchemy models.
- [x] Export models and import them in Alembic env.
- [x] Add migration `014`.
- [x] Run backend model tests.

### Task 2: Backend Auth Platform Profile Fields

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/routers/auth.py`
- Create: `backend/tests/test_auth_platform_profile.py`

**Interfaces:**
- Produces: `build_token_user_response(user)` and `build_user_response(user)`.
- Consumes: `BrokerAccount` / `Membership` relationships when present, deterministic defaults when absent.

- [x] Write failing tests for `/me` response helper defaults and relationship-backed account.
- [x] Extend `UserResponse` and `TokenUserResponse` with optional platform fields.
- [x] Refactor auth routes to use response helpers.
- [x] Run auth platform profile tests.

### Task 3: Frontend Auth Payload Normalization

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx`
- Modify: `frontend/src/__tests__/AuthContext.test.tsx`

**Interfaces:**
- Produces: `normalizeAuthUserPayload(payload)` helper.
- Consumes: backend snake_case and existing camelCase auth payloads.

- [x] Write failing tests for snake_case `/me` payload.
- [x] Implement normalization helper.
- [x] Use helper for refresh, login, and register.
- [x] Run focused frontend auth/context tests.

### Task 4: Documentation And Verification

**Files:**
- Modify: `docs/design/New design/01 PRD 文档/0.5 平台化详细方案设计.md`
- Create: `docs/reviews/platform-persistence-phase-b1-2026-06-27.md`

**Interfaces:**
- Consumes outputs from Tasks 1-3.

- [x] Document implemented persistence contracts.
- [x] Record verification evidence.
- [x] Record risks and Phase B2 next work.
