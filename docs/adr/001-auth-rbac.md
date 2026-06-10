# ADR-001: 用户认证与 RBAC 权限系统

- 状态：Proposed
- 日期：2026-06-10
- 决策者：tech-lead
- 影响范围：全栈（新增 auth-service + 前端改造 + 现有服务集成）

## 上下文

速赢 AI 证券投资管理平台当前无用户认证与权限体系。Kronos WebUI（Flask）仅有简单的 API Key 认证（`KRONOS_API_KEY` 环境变量），所有 FastAPI 微服务（screener / prediction / strategy / signal / alert / trade / backtest / diagnosis）均无任何认证机制，CORS 全开（`allow_origins=["*"]`）。

PRD 要求实现 JWT + 4 角色 RBAC 系统，角色包括：管理员（admin）、内部分析师（internal_analyst）、外部分析师（external_analyst）、普通用户（user）。不同角色对 K 线数据、预测结果、交易功能有不同的访问和操作权限。

不做此决策的后果：任何知晓服务地址的人均可访问所有 API，无法区分内部/外部用户，无法审计操作来源，无法上线生产环境。

## 决策

| 维度 | 选型 | 理由 |
|---|---|---|
| JWT 库 | **PyJWT 2.13.0** | 比 python-jose 更活跃维护（2026-05 仍在发版）；无已知 CVE；API 更简洁；是 Python JWT 生态的事实标准。否决 python-jose 3.5.0：历史有 CVE-2024-33664/33663，维护节奏慢（最新版 2025-05，距今 13 个月无更新），且 python-jose 依赖链更重（ecdsa, rsa, pyasn1） |
| 密码哈希 | **argon2-cffi 25.1.0** (Argon2id) | OWASP 推荐的新项目默认算法；内存硬化抵抗 GPU/ASIC 并行破解；RFC 9106 标准；支持 Python 3.13/3.14。否决 bcrypt 5.0.0：其 PyPI 自述明确写"you should really use argon2id or scrypt"；72 字节密码截断；无内存硬化 |
| 访问令牌 | **JWT Access Token（15min）+ Refresh Token（7d）** | 短生命周期 Access Token 限制泄露影响范围；Refresh Token Rotation 每次刷新时轮换，可检测 token 重放；Refresh Token 存储于 httpOnly cookie 而非 Access Token，降低 XSS 风险 |
| 前端 Token 存储 | **httpOnly + Secure + SameSite=Strict Cookie**（仅存 Refresh Token） | XSS 无法读取 httpOnly cookie；Secure 确保仅 HTTPS 传输；SameSite=Strict 防 CSRF。否决 localStorage：任何 XSS 漏洞即可读取 token 并外传。Access Token 仅存于内存（React state），页面刷新后通过 Refresh Token 静默获取新 Access Token |
| RBAC 中间件 | **FastAPI `Depends()` 依赖注入** | 每个微服务通过共享的 `kronos-auth` Python 包引入 `require_role(role)` 依赖；无需独立网关层；与 FastAPI 生态原生集成。否决 API Gateway 集中鉴权：引入额外的网络跃点和单点故障；微服务间仍需服务间认证，网关不能完全替代 |
| 认证服务 | **独立 auth-service（FastAPI，端口 8010）** | 与现有微服务体系一致（FastAPI + uvicorn）；职责单一（登录/注册/刷新/登出/角色管理）；可独立扩缩容。备选：嵌入每个服务共享库——会被否决，因为 Refresh Token 黑名单/角色变更需要共享状态 |
| 数据库 | **PostgreSQL 15**（新增 users / roles 表） | 与现有基础设施一致（docker-compose 已运行 postgres:15-alpine）；利用行级安全 + 外键约束；表命名延续现有 snake_case 风格 |
| 密码存储参数 | Argon2id: `time_cost=3, memory_cost=65536, parallelism=2` | 目标验证时间 ~300ms（生产服务器基准）；memory_cost=65536 KiB = 64 MiB，符合 OWASP 中等偏上建议 |

## 备选方案

- **A. python-jose + bcrypt** — python-jose 曾经是 FastAPI 官方教程推荐的 JWT 库，社区文档多；bcrypt 历史悠久、兼容性好。否决理由：python-jose 维护活跃度明显低于 PyJWT，且过去两年有高危 CVE；bcrypt 自身文档推荐迁移到 argon2id；无理由选择技术债务更高的组合。

- **B. 基于 Session 的认证（Flask-Login / FastAPI-Sessions）** — 传统服务端 Session 无 JWT 的 token 泄露问题，可服务端即时撤销。否决理由：微服务架构下 Session 需要共享 Redis 存储，增加运维复杂度；前后端分离的 SPA 场景 JWT 更自然；Refresh Token Rotation 已提供足够的撤销能力。

- **C. OAuth2 / OIDC（Keycloak / Auth0）** — 功能完备，自带 UI 和管理后台。否决理由：Phase A 阶段引入独立 IDP 运维成本过高；当前用户量（预计 < 100）不需要企业级 IAM；可在后续 ADR 中评估迁移。

## 影响

- **对现有代码**：新增 `services/auth-service/` 目录 + 共享包 `packages/kronos-auth/`；8 个现有微服务各增加 1 个 `Depends(require_role(...))` 调用；Kronos WebUI（Flask）的 API Key 认证保留但标记为 deprecated，建议迁移至统一 auth-service；前端新增登录页 + AuthContext + axios interceptor
- **对团队**：前端开发者需理解 httpOnly cookie 的读取限制和 token 刷新流程；后端开发者需理解 FastAPI Depends 依赖注入和 JWT 声明结构
- **对成本**：新增 PostgreSQL 表 ~10KB；无外部服务费用；auth-service 1 个容器（与现有服务共享 docker-compose 编排）
- **对运维**：新增监控点——登录失败率（告警阈值 >20%/min）、token 刷新失败率（>5%/min）、密码哈希耗时 p99（>1s）；Auth Service 必须配置 `KRONOS_JWT_SECRET`（至少 256-bit 随机值）

## 本 ADR 不覆盖的决策

- **多因素认证（MFA）**：Phase A 不实现，留给后续 ADR
- **OAuth2 社交登录**（微信/Google）：留给 Phase B
- **API Key 管理**（程序化访问）：现有 Kronos WebUI 的 API Key 机制保留不动，本 ADR 不改变其行为
- **服务间认证**（mTLS / shared secret）：当前微服务在 Docker 内网通信，暂不做服务间认证；留给上生产前的安全审计 ADR
- **用户注册流程**：本 ADR 仅覆盖技术选型与数据模型，注册审批流程由 PRD 定义

## 后续工作

- [ ] backend-dev: 创建 `services/auth-service/` 项目骨架（FastAPI + uvicorn + Dockerfile），预计 1d
- [ ] backend-dev: 创建 `packages/kronos-auth/` 共享包（JWT 工具 + RBAC Depends），预计 1d
- [ ] backend-dev: 实现 users / roles 数据库迁移脚本（Alembic），预计 0.5d
- [ ] backend-dev: 实现 POST /login, POST /refresh, POST /logout, GET /me 端点，预计 1d
- [ ] backend-dev: 为 8 个现有微服务添加 `Depends(require_role(...))`，预计 1d
- [ ] frontend-dev: 实现登录页 + AuthContext + axios interceptor（token 刷新），预计 2d
- [ ] product-lead: 确认 4 角色的具体权限矩阵（哪些 API 哪个角色可访问），AD 通过后触发

## 版本与查证

> tech-lead 行事原则 #3「先查最新版再决策」的回填段。新增技术或大版本升级时必填。

**查证基线日期**：2026-06-10

| 选型 | 选定版本 | 最新稳定版 | 与最新版差距 | 维护状态 | 信息来源（含原文摘录） |
|---|---|---|---|---|---|
| PyJWT | 2.13.0 | 2.13.0 | 无差距 | Active — 2026-05-21 发版 | [GitHub Releases](https://github.com/jpadilla/pyjwt/releases) — "PyJWT 2.13.0, released May 21, 2026" |
| argon2-cffi | 25.1.0 | 25.1.0 | 无差距 | Active — 2025-06-03 发版，支持 Python 3.14 | [PyPI](https://pypi.org/project/argon2-cffi/) — "25.1.0 — added official support for Python 3.13 and 3.14" |
| FastAPI | 0.136.3 | 0.136.3 | 无差距 | Active — 2026-05-23 发版 | [GitHub Releases](https://github.com/fastapi/fastapi/releases) — "0.136.3, latest stable" |
| PostgreSQL | 15-alpine | 17 | 2 个 major 落后 | Active — PG 15 EOL 2027-11 | [docker-compose.yml](../docker/docker-compose.yml) 已用 `postgres:15-alpine`；PG 15 仍受支持，不在此 ADR 中强制升级 |

**备选（被否决）技术的版本记录**：

| 选型 | 当时最新版 | 否决原因 |
|---|---|---|
| python-jose | 3.5.0 (2025-05-28) | 13 个月未更新；历史 CVE-2024-33664/33663；依赖链更重 |
| bcrypt | 5.0.0 (2025 末) | 自身文档推荐 argon2id；无内存硬化；72 字节截断 |

---

### 数据库 Schema（参考）

以下为推荐的表结构，遵循现有 `services/sql/init_postgres.sql` 的命名与风格：

```sql
-- ── 认证与权限表 ──

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,          -- admin, internal_analyst, external_analyst, user
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,   -- SHA-256 of the actual refresh token
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    family TEXT NOT NULL,              -- rotation family for replay detection
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
```

### JWT Payload 结构

```json
{
  "sub": "1",
  "username": "analyst_zhang",
  "role": "internal_analyst",
  "iat": 1718000000,
  "exp": 1718000900,
  "type": "access"
}
```

### 前端 Token 流程

```
登录成功 → 后端 Set-Cookie: refresh_token (httpOnly, Secure, SameSite=Strict, path=/api/v1/auth, max-age=604800)
         → 响应 body 返回 access_token
         → 前端存 access_token 于 React state (内存)

API 请求 → axios interceptor 注入 Authorization: Bearer <access_token>

access_token 过期 → axios interceptor 拦截 401
                  → POST /api/v1/auth/refresh (cookie 自动携带 refresh_token)
                  → 成功 → 更新内存中的 access_token，重试原请求
                  → 失败 → 清除状态，跳转登录页

登出 → POST /api/v1/auth/logout
     → 后端 revoke refresh_token family + Clear-Cookie
```
