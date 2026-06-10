# QA Report — Auth/RBAC 权限系统 — E2E + UAT 测试策略

- **Date**: 2026-06-10
- **Stage**: Strategy（E2E + UAT 策略框架，非执行报告）
- **Tester**: qa-engineer (deepseek-v4-pro)
- **Branch**: feature/auth-rbac（预计）
- **Environment**: local docker-compose（PostgreSQL + FastAPI backend + React frontend）
- **PRD**: docs/prd/auth-rbac-2026-06-10.md / Kronos/docs/投资管理平台_PRD_产品需求文档.md §2
- **Code review (含 SIT Audit)**: TBD（code-review 通过后方可执行本策略中的测试）

---

## Summary

> 本文件为测试策略框架，**未执行**。E2E 测试在 code-review + SIT Audit 通过后启动；UAT 在 E2E 通过后启动。

- **Total E2E Scenarios**: 12
- **Total UAT Scenarios**: 8
- **AC Coverage**: 覆盖 PRD §2.2 全部 16 功能点 x 4 角色的权限矩阵
- **Status**: ⏳ 等待 code-review 通过

---

## 权限矩阵（PRD §2.2 原文引用）

| 功能模块 | 管理员 | 内部分析师 | 外部分析师 | 普通用户 |
|---------|:---:|:---:|:---:|:---:|
| 选股 | ✅ | ✅ | ✅ | ✅ |
| 排序 | ✅ | ✅ | ✅ | ✅ |
| 方案生成 | ✅ | ✅ | ✅ | ✅ |
| 预测 | ✅ | ✅ | ✅ | ✅ |
| 回测 | ✅ | ✅ | ✅ | ❌ |
| 训练优化 | ✅ | ❌ | ❌ | ❌ |
| 确定方案/报告 | ✅ | ✅ | ✅ | ✅ |
| 交易信号 | ✅ | ✅ | ✅ | ✅ |
| 预警提醒 | ✅ | ✅ | ✅ | ✅ |
| 模拟交易 | ✅ | ✅ | ❌ | ✅ |
| 实盘交易 | ✅ | ❌ | ❌ | ✅ |
| 个股诊断 | ✅ | ✅ | ✅ | ✅ |
| 系统配置 | ✅ | ❌ | ❌ | ❌ |
| 模型管理 | ✅ | ❌ | ❌ | ❌ |
| 用户管理 | ✅ | ❌ | ❌ | ❌ |
| 数据源管理 | ✅ | ❌ | ❌ | ❌ |
| 客户管理 | ✅ | ✅ | ✅ | ❌ |

---

## Pre-conditions Checked

> 执行测试前必须全部勾选。

- [ ] 单元测试 + lint + typecheck 全绿
- [ ] code-reviewer 报告已存在且 verdict ≠ Block（含 SIT Audit = ✅ / ⚠️）
- [ ] PRD auth-rbac spec 文件可访问
- [ ] 测试数据库已启动（`docker compose up -d`）
- [ ] 数据库迁移已 apply（users/roles 表存在）
- [ ] 测试 seed 数据已注入（4 个角色各 1 个测试用户）
- [ ] 后端服务已启动（FastAPI on localhost:8000）
- [ ] 前端服务已启动（React on localhost:5173）
- [ ] chrome-devtools-mcp 可用于浏览器截图

---

## 测试环境准备

### 3.1 测试用户预设（Seed Data）

```sql
-- roles 枚举表
CREATE TYPE user_role AS ENUM ('admin', 'internal_analyst', 'external_analyst', 'user');

-- 测试用户（密码均为 Test@123456，bcrypt hash）
INSERT INTO users (username, email, password_hash, role, is_active, created_at) VALUES
  ('test_admin',              'admin@test.local',             '$2b$12$...', 'admin',              true, NOW()),
  ('test_internal_analyst',   'internal@test.local',          '$2b$12$...', 'internal_analyst',   true, NOW()),
  ('test_external_analyst',   'external@test.local',          '$2b$12$...', 'external_analyst',   true, NOW()),
  ('test_user',               'user@test.local',              '$2b$12$...', 'user',               true, NOW());
```

### 3.2 数据库 Seed 脚本期望

| 要求 | 说明 |
|------|------|
| Seed 脚本位置 | `backend/scripts/seed_test_users.sql` 或 `backend/app/scripts/seed.py` |
| 幂等性 | 重复执行不报错（`ON CONFLICT DO NOTHING` 或 `INSERT ... WHERE NOT EXISTS`） |
| 密码 | 所有测试用户统一密码 `Test@123456`，bcrypt hash |
| 角色一致性 | 4 个角色的 username/email/role 必须与上表一致（E2E 脚本硬编码这些凭据） |
| 执行方式 | `docker compose exec backend python scripts/seed.py` 或自动在 pytest fixture 中 |

### 3.3 环境变量

```bash
# E2E 测试需要的环境变量
export TEST_BASE_URL=http://localhost:8000/api/v1
export TEST_FRONTEND_URL=http://localhost:5173
export TEST_ADMIN_EMAIL=admin@test.local
export TEST_USER_EMAIL=user@test.local
export TEST_PASSWORD=Test@123456
export JWT_SECRET=test-secret-do-not-use-in-production
export JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
export JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
```

---

## E2E 测试场景

### E2E-1: 注册新用户 + 登录 + 获取用户信息（Happy Path）

- **Priority**: P0
- **Setup**: 清空测试数据库，确保 `test_newuser@test.local` 不存在
- **Action**:
  1. `POST /api/v1/auth/register` — 提交 `{username: "newuser", email: "test_newuser@test.local", password: "Test@123456"}`
  2. 从响应提取 `access_token`
  3. `GET /api/v1/auth/me` — Header `Authorization: Bearer <access_token>`
- **Expected**:
  - Register 返回 `201 Created`，含 `{id, username, email, role: "user", is_active: true}`（不含 password_hash）
  - Login 返回 `200 OK`，含 `{access_token, refresh_token, token_type: "bearer"}`
  - `/auth/me` 返回 `200 OK`，含当前用户信息，`role = "user"`
- **Evidence**: `curl -i` 完整请求/响应 3 次调用
- **Verdict**: ⏳ 待执行

---

### E2E-2: 错误密码登录 → 401

- **Priority**: P0
- **Setup**: 确保 seed 用户 `test_user` 存在
- **Action**:
  1. `POST /api/v1/auth/login` — 提交 `{email: "user@test.local", password: "WrongPassword999"}`
- **Expected**:
  - 返回 `401 Unauthorized`
  - Body 含 `{detail: "Invalid email or password"}`（不区分"用户不存在"和"密码错误"，防止用户枚举）
- **Evidence**: `curl -i` 完整响应（状态行 + body）
- **Verdict**: ⏳ 待执行

---

### E2E-3: 过期 Token → 401 → 自动刷新或重定向登录

- **Priority**: P0
- **Setup**: 使用 `test_user` 登录，获取一个**已过期的** access_token（可通过设置极短过期时间如 1 秒后 sleep 2 秒模拟）
- **Action**:
  1. `GET /api/v1/auth/me` — 使用过期 access_token
  2. 观察前端行为：是否自动调用 `POST /api/v1/auth/refresh` 并重试原请求
  3. 若 refresh_token 也过期，观察是否重定向到 `/login`
- **Expected**:
  - 过期 access_token 请求返回 `401 Unauthorized`，含 `{detail: "Token has expired"}`
  - 前端拦截器检测到 401 + token expired → 自动调用 `/auth/refresh`
  - Refresh 成功 → 用新 token 重试原请求 → 返回 `200 OK`
  - Refresh 也失败（refresh_token 过期）→ 清除本地 token → 重定向到 `/login`
- **Evidence**: 浏览器 Network 面板截图（含 401 → refresh → 200 链路），或前端 console log
- **Verdict**: ⏳ 待执行

---

### E2E-4: 普通用户尝试访问管理端 API → 403

- **Priority**: P0
- **Setup**: 使用 `test_user`（role=user）登录，获取 access_token
- **Action**:
  1. `GET /api/v1/admin/users` — Header `Authorization: Bearer <user_access_token>`
  2. `GET /api/v1/admin/models` — 模型管理 API
  3. `GET /api/v1/admin/config` — 系统配置 API
  4. `GET /api/v1/admin/datasources` — 数据源管理 API
- **Expected**:
  - 全部返回 `403 Forbidden`
  - Body 含 `{detail: "Insufficient permissions"}` 或类似
- **Evidence**: 4 个 `curl -i` 完整响应（每个都应返回 403）
- **Verdict**: ⏳ 待执行

---

### E2E-5: 管理员访问用户管理 → 200

- **Priority**: P0
- **Setup**: 使用 `test_admin`（role=admin）登录，获取 access_token
- **Action**:
  1. `GET /api/v1/admin/users` — Header `Authorization: Bearer <admin_access_token>`
  2. 验证返回的用户列表包含所有 4 个 seed 用户
- **Expected**:
  - 返回 `200 OK`
  - Body 为 JSON 数组，至少包含 4 个用户对象
  - 每个用户对象含 `id, username, email, role, is_active, created_at`（不含 password_hash）
- **Evidence**: `curl -i` 完整响应（含用户列表）
- **Verdict**: ⏳ 待执行

---

### E2E-6: Token 刷新正常流程

- **Priority**: P0
- **Setup**: 使用 `test_user` 登录，获取 `access_token` + `refresh_token`
- **Action**:
  1. `POST /api/v1/auth/refresh` — Body `{refresh_token: "<refresh_token>"}`
  2. 使用新 access_token 调用 `GET /api/v1/auth/me`
- **Expected**:
  - Refresh 返回 `200 OK`，含新 `{access_token, refresh_token, token_type: "bearer"}`
  - 新 access_token 与旧 token 不同（验证是真正刷新了）
  - 新 access_token 可正常用于 `/auth/me` 请求
- **Evidence**: `curl -i` 3 次调用完整响应
- **Verdict**: ⏳ 待执行

---

### E2E-7: 登出后无法访问受保护路由

- **Priority**: P0
- **Setup**: 使用 `test_user` 登录，获取 access_token
- **Action**:
  1. 验证 `GET /api/v1/auth/me` 返回 `200 OK`
  2. `POST /api/v1/auth/logout` — 传入 refresh_token（如果有服务端黑名单机制）
  3. 登出后再次 `GET /api/v1/auth/me` — 使用**未携带 token** 的请求
- **Expected**:
  - Logout 返回 `200 OK` 或 `204 No Content`
  - 登出后 `/auth/me` 返回 `401 Unauthorized`
  - 前端清除 localStorage/Cookie 中的 token → 用户被重定向到 `/login`
- **Evidence**: `curl -i` 完整响应 + 前端截图（登出后页面显示为 login 页）
- **Verdict**: ⏳ 待执行

---

### E2E-8: 各角色登录后可见菜单差异（前端路由守卫）

- **Priority**: P0
- **Setup**: 依次使用 4 个测试用户登录前端
- **Action**:
  1. 管理员登录 → 截图导航菜单
  2. 内部分析师登录 → 截图导航菜单
  3. 外部分析师登录 → 截图导航菜单
  4. 普通用户登录 → 截图导航菜单
  5. 对比 4 张截图，验证菜单项差异与权限矩阵一致
- **Expected**:
  - 管理员：可见全部功能菜单（含用户管理、系统配置、模型管理、训练优化）
  - 内部分析师：可见选股/方案/预测/回测/信号/预警/模拟交易/个股诊断/客户管理；**不可见**训练优化/系统配置/模型管理/用户管理/数据源管理/实盘交易
  - 外部分析师：可见选股/方案/预测/回测/信号/预警/个股诊断/客户管理；**不可见**模拟交易/实盘交易/训练优化/系统配置/模型管理/用户管理/数据源管理
  - 普通用户：可见选股/方案/预测/信号/预警/模拟交易/实盘交易/个股诊断；**不可见**回测/训练优化/系统配置/模型管理/用户管理/数据源管理/客户管理
- **Evidence**: 4 张截图（每角色一张，文件名 `evidence/E2E-8-{admin,internal_analyst,external_analyst,user}.png`）
- **Verdict**: ⏳ 待执行

---

### E2E-9: 重复用户名/邮箱注册 → 409

- **Priority**: P1
- **Setup**: 确保 `test_user`（`user@test.local`）已存在
- **Action**:
  1. `POST /api/v1/auth/register` — 使用已存在的 `email: "user@test.local"`
  2. `POST /api/v1/auth/register` — 使用已存在的 `username: "test_user"`（不同 email）
- **Expected**:
  - 两次请求均返回 `409 Conflict`
  - Body 分别含 `{detail: "Email already registered"}` 和 `{detail: "Username already taken"}`
- **Evidence**: 2 个 `curl -i` 完整响应
- **Verdict**: ⏳ 待执行

---

### E2E-10: 无效 Token / 篡改 Token → 401

- **Priority**: P1
- **Setup**: 不需要登录
- **Action**:
  1. `GET /api/v1/auth/me` — 不带 Authorization header
  2. `GET /api/v1/auth/me` — Header `Authorization: Bearer invalid_token_xyz`
  3. `GET /api/v1/auth/me` — Header `Authorization: Bearer <篡改后的合法 token（改中间一个字符）>`
- **Expected**:
  - 全部返回 `401 Unauthorized`
  - Body `{detail: "Not authenticated"}` 或 `{detail: "Invalid token"}`
- **Evidence**: 3 个 `curl -i` 完整响应
- **Verdict**: ⏳ 待执行

---

### E2E-11: 跨角色页面访问拦截（前端路由守卫）

- **Priority**: P1
- **Setup**: 使用 `test_user`（role=user）登录前端
- **Action**:
  1. 在浏览器地址栏直接输入 `/admin/users` 并回车
  2. 在浏览器地址栏直接输入 `/backtest` 并回车
  3. 在浏览器地址栏直接输入 `/training` 并回车
- **Expected**:
  - 全部被路由守卫拦截
  - 显示 `403 Forbidden` 页面或重定向到 Dashboard 并显示 "无权限访问" 提示
- **Evidence**: 3 张截图（每页面一张拦截结果）
- **Verdict**: ⏳ 待执行

---

### E2E-12: 注册输入校验（弱密码/空字段/无效邮箱）

- **Priority**: P1
- **Setup**: 不需要登录
- **Action**:
  1. `POST /api/v1/auth/register` — 密码为 `"123"`（过短）
  2. `POST /api/v1/auth/register` — 邮箱为 `"not-an-email"`
  3. `POST /api/v1/auth/register` — username 为空字符串
  4. `POST /api/v1/auth/register` — email 为空字符串
- **Expected**:
  - 全部返回 `422 Unprocessable Entity`
  - Body 含具体校验错误字段（password too short / invalid email format / username required / email required）
- **Evidence**: 4 个 `curl -i` 完整响应
- **Verdict**: ⏳ 待执行

---

## UAT 测试场景

### UAT-1 (P0): 管理员能创建用户并分配角色

- **Priority**: P0
- **Setup**: 使用 `test_admin` 登录
- **Action**:
  1. 登录管理端
  2. 进入用户管理页面
  3. 点击「新建用户」
  4. 填写：username=`uat_analyst_01`，email=`uat_analyst_01@test.local`，初始密码，角色选择「内部分析师」
  5. 提交
  6. 使用新用户凭据登录
  7. 验证新用户的角色权限（能访问选股/方案/信号，不能访问训练）
- **Expected**:
  - 创建成功，用户列表中出现新用户
  - 新用户可用分配的凭据登录
  - 新用户角色为 `internal_analyst`
  - 权限与 PRD §2.2 内部分析师行一致
- **Evidence**: 管理端创建截图 + 新用户登录截图 + 权限验证截图
- **Verdict**: ⏳ 待执行（P0 pass^2 需两次连续通过）

---

### UAT-2 (P0): 角色切换后权限即时生效

- **Priority**: P0
- **Setup**: 存在一个普通用户 `test_user`（role=user）
- **Action**:
  1. 管理员登录 → 用户管理 → 将 `test_user` 角色从 `user` 改为 `internal_analyst`
  2. `test_user` 当前 session 仍在 → 尝试访问回测功能（如果 token 中有 role claim，应立即得到 403 直到重新登录获取新 token）
  3. `test_user` 登出后重新登录
  4. 验证新登录后菜单和权限变为内部分析师级别（可访问回测/客户管理，不可访问训练/实盘交易）
- **Expected**:
  - 角色修改后，旧 token（role=user）访问内部分析师专属功能返回 `403 Forbidden`
  - 重新登录后，新 token 的 role 为 `internal_analyst`
  - 新 token 可正常访问回测、客户管理等内部分析师功能
- **Evidence**: 管理端角色修改截图 + 旧 token 403 截图 + 新 token 权限验证截图
- **Verdict**: ⏳ 待执行（P0 pass^2 需两次连续通过）

---

### UAT-3 (P0): 内部分析师能访问选股+方案+信号，不能访问训练

- **Priority**: P0
- **Setup**: 使用 `test_internal_analyst` 登录
- **Action**:
  1. 依次访问：选股页面 / 方案管理 / 交易信号 / 预测 / 回测 / 模拟交易 / 个股诊断 / 客户管理
  2. 尝试访问：训练优化页面 / 系统配置 / 用户管理 / 模型管理 / 数据源管理 / 实盘交易
- **Expected**:
  - ① 中全部页面返回 `200 OK`，功能可用
  - ② 中全部页面返回 `403 Forbidden` 或被路由守卫拦截
- **Evidence**: 每页面截图（文件名 `evidence/UAT-3-{page}-{result}.png`）
- **Verdict**: ⏳ 待执行（P0 pass^2 需两次连续通过）

---

### UAT-4 (P0): 普通用户能访问模拟交易，不能访问回测

- **Priority**: P0
- **Setup**: 使用 `test_user`（role=user）登录
- **Action**:
  1. 访问模拟交易页面（/trade?mode=paper）
  2. 查看模拟持仓、下单面板、盈亏统计
  3. 尝试访问回测页面（/backtest）
  4. 尝试访问训练优化页面（/training）
  5. 尝试访问客户管理页面（/clients）
- **Expected**:
  - 模拟交易页面正常可用（`200 OK`）
  - 回测页面返回 `403 Forbidden` 或被路由守卫拦截
  - 训练优化页面返回 `403 Forbidden`
  - 客户管理页面返回 `403 Forbidden`
- **Evidence**: 模拟交易截图 + 3 个被拦截页面的截图
- **Verdict**: ⏳ 待执行（P0 pass^2 需两次连续通过）

---

### UAT-5 (P1): 外部分析师能访问回测，不能访问模拟/实盘交易

- **Priority**: P1
- **Setup**: 使用 `test_external_analyst` 登录
- **Action**:
  1. 访问回测页面（/backtest）
  2. 访问方案管理页面
  3. 尝试访问模拟交易页面（/trade?mode=paper）
  4. 尝试访问实盘交易页面（/trade?mode=live）
- **Expected**:
  - 回测和方案管理正常可用（`200 OK`）
  - 模拟交易和实盘交易均返回 `403 Forbidden`
- **Evidence**: 回测截图 + 模拟交易 403 截图 + 实盘交易 403 截图
- **Verdict**: ⏳ 待执行

---

### UAT-6 (P1): 管理员全功能权限验证

- **Priority**: P1
- **Setup**: 使用 `test_admin` 登录
- **Action**:
  1. 依次访问 PRD §2.2 全部 16 个功能点对应的页面/API
  2. 特别验证仅管理员可用的功能：训练优化、系统配置、模型管理、用户管理、数据源管理
- **Expected**:
  - 全部 16 个功能点返回 `200 OK`，功能可用
- **Evidence**: 5 张截图（仅管理员功能的 5 个页面）
- **Verdict**: ⏳ 待执行

---

### UAT-7 (P1): 未登录用户访问任何受保护页面 → 重定向登录页

- **Priority**: P1
- **Setup**: 清除浏览器所有 Cookie/LocalStorage，或使用无痕窗口
- **Action**:
  1. 直接在地址栏输入 `/dashboard`
  2. 直接在地址栏输入 `/admin/users`
  3. 直接在地址栏输入 `/trade?mode=paper`
  4. 直接在地址栏输入 `/backtest`
- **Expected**:
  - 全部重定向到 `/login`（或弹出登录页面）
  - 登录成功后自动跳转回原目标页面（redirect_uri 参数）
- **Evidence**: 4 张截图（重定向到 /login 的结果）
- **Verdict**: ⏳ 待执行

---

### UAT-8 (P1): 同一浏览器多 Tab 登出 → 所有 Tab 状态同步

- **Priority**: P1
- **Setup**: 使用 `test_user` 登录，打开 3 个 Tab（Dashboard / Trade / Signals）
- **Action**:
  1. 在 Tab A 点击登出
  2. 切换到 Tab B（Trade）→ 尝试操作
  3. 切换到 Tab C（Signals）→ 尝试操作
- **Expected**:
  - Tab A 登出成功，清除 token
  - Tab B 检测到 token 失效 → 显示 "会话已过期，请重新登录" → 跳转 /login
  - Tab C 同理
  - 三个 Tab 不会出现部分仍可操作的情况
- **Evidence**: 3 张截图（每 Tab 的状态）
- **Verdict**: ⏳ 待执行

---

## 数据准备与执行脚本

### Seed 脚本伪代码

```python
# backend/scripts/seed_test_users.py
"""注入 E2E/UAT 测试用户到数据库。幂等：已存在则跳过。"""

import os
from passlib.context import CryptContext
from sqlalchemy import create_engine, text

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/investment_platform")

TEST_USERS = [
    ("test_admin",              "admin@test.local",             "admin"),
    ("test_internal_analyst",   "internal@test.local",          "internal_analyst"),
    ("test_external_analyst",   "external@test.local",          "external_analyst"),
    ("test_user",               "user@test.local",              "user"),
]

TEST_PASSWORD = "Test@123456"
password_hash = pwd_context.hash(TEST_PASSWORD)

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    for username, email, role in TEST_USERS:
        conn.execute(text("""
            INSERT INTO users (username, email, password_hash, role, is_active, created_at)
            VALUES (:username, :email, :password_hash, :role, true, NOW())
            ON CONFLICT (email) DO NOTHING
        """), {"username": username, "email": email, "password_hash": password_hash, "role": role})
    conn.commit()

print(f"Seeded {len(TEST_USERS)} test users (password: {TEST_PASSWORD})")
```

### E2E 执行顺序（推荐）

```
1. docker compose up -d                    # 启动 PostgreSQL
2. python backend/scripts/seed_test_users.py  # 注入测试数据
3. cd backend && uvicorn app.main:app --reload  # 启动后端
4. cd frontend && npm run dev              # 启动前端
5. 按 E2E-1 → E2E-12 顺序执行（依赖 token 的场景按编号递增）
6. E2E 全部通过后 → 启动 UAT-1 → UAT-8
```

---

## Cross-stage Notes

- **E2E → UAT 交接**：
  - UAT 需要 E2E 通过后，**不修改代码/不重建环境**，直接在同一环境执行
  - 若 UAT 发现 Defect，需要回退到 dev 修复后重新跑 E2E + UAT
  - P0 case 的 pass^2 要求在 UAT 阶段执行时**连续两次**通过（UAT-1~4）

- **已知限制（V1 不做）**：
  - OAuth / SSO 登录
  - 邮箱验证
  - 密码重置流程
  - MFA 二次验证
  - API Key 管理

---

## Cost (this QA session)

- **Tokens consumed**: 待 E2E/UAT 执行后统计
- **Estimated cost**: 待统计
- **同 feature 累计（E2E + UAT 总和）**: 待统计

---

## Hand-off

⏳ **当前状态**：策略框架已就绪，等待 code-review + SIT Audit 通过后开始 E2E 执行。

- E2E 通过 → Promote to UAT
- E2E 失败 → Block，SendMessage product-lead 列出 critical defect
- UAT 通过 → final SendMessage product-lead，附完整报告 + 建议判定

---

## 完成前自检

- [x] 每条场景都有 Setup / Action / Expected / Verdict 五段
- [ ] 每个 Pass 都有可验证 evidence（执行后补齐）
- [ ] Defects 表每行都有 Repro steps + Suspected file（执行后补齐）
- [x] Cost 预留了统计位
- [x] Verdict 决策树已嵌入（Summary 节）
- [x] Hand-off 触发条件已明确
