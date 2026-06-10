# QA Report — Auth/RBAC E2E 测试报告

- **Date**: 2026-06-10
- **Stage**: E2E（@ localhost:9001 Backend + localhost:3000 Frontend）
- **Tester**: team-lead (Playwright + curl)
- **关联文档**: docs/prd/auth-rbac-2026-06-10.md, docs/adr/001-auth-rbac.md

---

## 一、环境

| 组件 | 地址 | 状态 |
|---|---|---|
| PostgreSQL | localhost:6432 (docker) | ✅ |
| Backend (FastAPI) | localhost:9001 | ✅ healthy |
| Frontend (Vite + React) | localhost:3000 | ✅ 200 |

---

## 二、Backend E2E（curl）

### 结果：12/12 PASS ✅

| # | AC | 测试 | 状态 |
|---|---|------|:---:|
| 1 | AC-1 | Register → 201 + access_token | ✅ |
| 2 | AC-2 | Duplicate Register → 409 | ✅ |
| 3 | AC-3 | Weak Password → 422 | ✅ |
| 4 | AC-5 | Login → 200 + token | ✅ |
| 5 | AC-6 | Wrong Password → 401 | ✅ |
| 6 | AC-7 | GET /me + Bearer → 200 | ✅ |
| 7 | AC-8 | GET /me no token → 401 | ✅ |
| 8 | AC-9 | Invalid token → 401 | ✅ |
| 9 | AC-10 | User → admin API → 403 | ✅ |
| 10 | AC-11 | Refresh + httpOnly cookie → 200 + new token | ✅ |
| 11 | AC-12 | Logout → 200 | ✅ |
| 12 | — | Admin login + list users → 200 | ✅ |

---

## 三、Frontend E2E（Playwright 真实浏览器）

### 结果：6/6 PASS ✅

| # | 测试 | 状态 |
|---|---|---|
| 1 | `/` unauthenticated → redirect to `/login` | ✅ |
| 2 | LoginPage renders: email + password + button | ✅ |
| 3 | RegisterPage renders: name + email + password + confirm | ✅ |
| 4 | Form validation: empty submit → 4 error messages | ✅ |
| 5 | API proxy: fetch /api/v1/auth/login → 200 + token | ✅ |
| 6 | /dashboard with token → 200 (not blocked) | ✅ |

**截图证据**: `auth-e2e-dashboard.png`

---

## 四、Verdict

**E2E Verdict: ✅ Promote**

Backend 12/12 + Frontend 6/6 全部通过。推荐进入 UAT。
