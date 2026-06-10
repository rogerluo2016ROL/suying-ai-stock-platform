# Auth + RBAC API 契约（已实现）

> 状态：已实现（2026-06-10）
> 关联 ADR：`docs/adr/001-auth-rbac.md`
> 关联 PRD：`docs/prd/auth-rbac-2026-06-10.md`

---

## 1. 数据库 Schema

### 1.1 Role 枚举

```sql
-- PostgreSQL 原生枚举（与 Python enum 双向映射）
CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'viewer');
```

| Role | 权限范围 |
|---|---|
| `admin` | 全部：用户管理、系统配置、查看所有数据 |
| `analyst` | 选股/回测/因子配置、查看自选 + 结果，不可管理用户 |
| `viewer` | 只读：查看筛选结果、自选列表、回测报告 |

### 1.2 users 表

```sql
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            user_role NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
```

**设计说明**：
- `password_hash` 存储 bcrypt（werkzeug 或 passlib），**绝不存明文**
- `role` 用 PostgreSQL 原生 enum → Python `enum.StrEnum` 双向映射，查询时可做 `WHERE role = 'admin'::user_role`
- `username` + `email` 双唯一约束：用户名用于显示，邮箱用于登录凭证
- 未设 `last_login` 字段 —— 登录审计由独立的 `login_audit_log` 表承载（后续迭代），避免 users 表写热点
- 风格对齐现有 SQL：`SERIAL PRIMARY KEY`、`TEXT NOT NULL`、`TIMESTAMP DEFAULT NOW()` 与 `init_postgres.sql` 中 `screening_scores`、`watchlist` 等应用层表一致

### 1.3 SQLAlchemy 模型（草案，位于 `backend/app/models/user.py`）

```python
import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from app.models.base import Base  # 与项目统一的 declarative base

class UserRole(str, enum.Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="user_role", create_type=False), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**注意**：`create_type=False` 告诉 SQLAlchemy 不自动创建 enum 类型（由 Alembic migration 显式管理），避免 `CREATE TYPE IF NOT EXISTS` 的竞态。

---

## 2. API 契约

所有端点前缀：`/api/v1/auth`（admin 端点：`/api/v1/admin`）

### 2.1 通用约定

- **Content-Type**：`application/json`（请求和响应）
- **认证方式**：`Authorization: Bearer <jwt_token>`（受保护端点）
- **错误响应**统一格式：

```json
{
  "detail": "人类可读的错误描述"
}
```

### 2.2 端点明细

#### POST /api/v1/auth/register — 注册

```
请求:
{
  "username": "string (3-32 chars, alphanumeric + _-)",
  "email": "string (valid email)",
  "password": "string (min 8 chars, 至少1大写+1数字)"
}

响应 201:
{
  "id": 1,
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "viewer",
  "created_at": "2026-06-10T12:00:00Z"
}

错误:
400 — 用户名或邮箱已存在 / 字段校验失败
422 — 请求体格式错误
```

**安全约束**：新注册用户默认 role=`viewer`，不可通过请求体指定 role。

#### POST /api/v1/auth/login — 登录

```
请求:
{
  "email": "string",
  "password": "string"
}

响应 200:
{
  "access_token": "eyJhbG...",
  "refresh_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": 1,
    "username": "zhangsan",
    "email": "zhangsan@example.com",
    "role": "admin"
  }
}

错误:
401 — 邮箱或密码错误
403 — 账号已停用 (is_active=false)
```

**实现要点**：
- access_token 有效期 `JWT_ACCESS_EXPIRE_SECONDS`（默认 3600）
- refresh_token 有效期 `JWT_REFRESH_EXPIRE_SECONDS`（默认 604800 = 7 天）
- JWT payload：`{ "sub": user.id, "role": user.role, "exp": ..., "iat": ..., "type": "access" }`

#### POST /api/v1/auth/refresh — 刷新 token

```
请求:
{
  "refresh_token": "eyJhbG..."
}

响应 200:
{
  "access_token": "eyJhbG...",
  "token_type": "bearer",
  "expires_in": 3600
}

错误:
401 — refresh_token 无效或过期
```

#### POST /api/v1/auth/logout — 登出

```
请求:
Authorization: Bearer <access_token>

响应 200:
{
  "message": "Logged out successfully"
}
```

**实现要点**：若采用服务端 token 黑名单策略，此处将当前 access_token 加入黑名单（Redis TTL = token 剩余有效期）；若纯无状态 JWT，logout 仅客户端删 token，服务端空操作。

#### GET /api/v1/auth/me — 当前用户信息

```
请求:
Authorization: Bearer <access_token>

响应 200:
{
  "id": 1,
  "username": "zhangsan",
  "email": "zhangsan@example.com",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-06-10T12:00:00Z",
  "updated_at": "2026-06-10T12:00:00Z"
}

错误:
401 — 未认证或 token 过期
```

#### PUT /api/v1/auth/me — 更新个人信息

```
请求:
Authorization: Bearer <access_token>
{
  "username": "string (optional, 3-32)",
  "password": "string (optional, min 8, 至少1大写+1数字)"
}

响应 200:
{
  "id": 1,
  "username": "zhangsan_new",
  "email": "zhangsan@example.com",
  "role": "admin",
  "updated_at": "2026-06-10T13:00:00Z"
}

错误:
400 — 用户名已存在
401 — 未认证
```

**约束**：不可通过此端点修改 `role` 或 `email`；改邮箱单独走 `/api/v1/auth/change-email`（后续迭代，需邮件验证）。

#### GET /api/v1/admin/users — 管理员：用户列表

```
请求:
Authorization: Bearer <access_token>   # 需要 admin role
Query params:
  ?page=1&page_size=20&role=analyst&is_active=true&q=zhang

响应 200:
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "users": [
    {
      "id": 1,
      "username": "zhangsan",
      "email": "zhangsan@example.com",
      "role": "analyst",
      "is_active": true,
      "created_at": "2026-06-10T12:00:00Z"
    }
  ]
}

错误:
401 — 未认证
403 — 非 admin 角色
```

#### PUT /api/v1/admin/users/{id}/role — 管理员：修改角色

```
请求:
Authorization: Bearer <access_token>   # 需要 admin role
{
  "role": "analyst"
}

响应 200:
{
  "id": 1,
  "username": "zhangsan",
  "role": "analyst",
  "updated_at": "2026-06-10T14:00:00Z"
}

错误:
400 — 无效 role 值 / 不能修改自己的角色
401 — 未认证
403 — 非 admin 角色
404 — 用户不存在
```

**安全约束**：admin 不能降级自己的角色（防止最后一个 admin 被锁）。

---

## 3. JWT 中间件设计

### 3.1 依赖注入方案

```python
# 文件位置（草案）：backend/app/api/deps.py

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.auth import decode_access_token, get_user_by_id

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """从 Authorization header 解析 JWT，返回当前用户。

    用于所有需要认证的端点：
        @router.get("/me")
        async def me(user: User = Depends(get_current_user)):
            ...
    """
    payload = decode_access_token(credentials.credentials)
    user = await get_user_by_id(payload["sub"])
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user
```

### 3.2 RBAC 依赖工厂

```python
# 文件位置（草案）：backend/app/api/deps.py

from typing import List
from app.models.user import UserRole

def require_role(*roles: UserRole):
    """返回一个 FastAPI 依赖，校验当前用户是否拥有指定角色之一。

    用法：
        @router.get("/admin/users")
        async def list_users(
            user: User = Depends(require_role(UserRole.ADMIN))
        ):
            ...

    也支持多角色：
        @router.get("/analyst-or-admin")
        async def shared(
            user: User = Depends(require_role(UserRole.ADMIN, UserRole.ANALYST))
        ):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of roles: {[r.value for r in roles]}"
            )
        return current_user
    return role_checker
```

### 3.3 中间件注册

在 `backend/app/main.py` 中：

```python
# 全局 CORS（开发阶段 allow_origins=["*"]，生产收紧为前端域名）
app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)

# JWT 不走全局中间件 — 用 Depends 按端点注入，不影响 /health 等公开端点
```

### 3.4 Token 生命周期

```
┌─────────────┐       ┌──────────────┐       ┌───────────────┐
│  POST/login  │ ────> │ access_token │ ────> │  GET /me      │
│              │       │ (1h)         │       │  PUT /me      │
│              │       └──────┬───────┘       │  GET /admin/* │
│              │              │               └───────────────┘
│              │       ┌──────┴───────┐
│              │       │ refresh_token│
│              │       │ (7d)         │
└─────────────┘       └──────┬───────┘
                              │
                      ┌───────┴───────┐
                      │ POST/refresh   │ ────> 新 access_token
                      └───────────────┘
```

---

## 4. Pydantic Schema 草案（`backend/app/schemas/auth.py`）

```python
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.models.user import UserRole

# ── Request schemas ──

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class UpdateMeRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=32)
    password: str | None = Field(default=None, min_length=8)

class UpdateUserRoleRequest(BaseModel):
    role: UserRole

# ── Response schemas ──

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: str   # ISO 8601
    updated_at: str   # ISO 8601

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class PaginatedUsersResponse(BaseModel):
    total: int
    page: int
    page_size: int
    users: list[UserResponse]
```

---

## 5. 关键决策点（开放问题）

### 决策点 1：Token 存储策略 — httpOnly cookie vs Authorization header？

| 方案 | 优点 | 缺点 |
|---|---|---|
| **Authorization header** | 无 CSRF 风险；移动端/CLI 友好；RESTful 标准 | XSS 可窃取 token；前端需手动管理刷新逻辑 |
| **httpOnly cookie** | XSS 不可读 token；浏览器自动携带；refresh 静默 | CSRF 需额外防御（SameSite + CSRF token）；非浏览器客户端不友好 |

**建议倾向**：`Authorization header`。理由：
- 本项目面向投资分析工具，未来可能有 Python CLI / 小程序等非浏览器客户端
- 现有 screener-service 已使用 header 模式（fastapi `HTTPBearer`）
- CSRF 防御复杂度高于 XSS（前端框架如 React 默认转义输出，XSS 面小）
- **待 product-lead 确认。**

### 决策点 2：是否需要 refresh token rotation？

| 方案 | 描述 |
|---|---|
| **不 rotation** | refresh token 固定 7 天，过期需重新登录 |
| **rotation** | 每次 `/refresh` 返回新 refresh token，旧 token 立即失效（可检测 token 重放 = 盗用信号） |

**建议倾向**：**Phase 1 不做 rotation，Phase 2 引入**。理由：
- rotation 需要服务端存储 token 家族（Redis / DB），增加运维复杂度
- Phase 1 用户量小（内部分析师团队），refresh token 泄露面可控
- 7 天过期 + 登出黑名单（Redis TTL）已提供基本安全
- **待 product-lead 确认。**

### 决策点 3：登录审计日志 — 与 users 表同库还是独立表/独立服务？

**选项**：
- A) `login_audit_log` 表放在同一 PostgreSQL（简单，查询方便）
- B) 独立日志服务/文件（解耦，不增加主库写压力）

**建议倾向**：A，Phase 1 同库即可。用户量小时主库完全能承受。

---

## 6. 环境变量（草案）

```bash
# backend/.env（gitignored）
JWT_SECRET_KEY=<至少 256-bit 随机字符串>
JWT_ACCESS_EXPIRE_SECONDS=3600
JWT_REFRESH_EXPIRE_SECONDS=604800
BCRYPT_ROUNDS=12
```

`JWT_SECRET_KEY` 生成：`python -c "import secrets; print(secrets.token_hex(32))"`

---

## 7. 实施顺序建议

| Phase | 范围 |
|---|---|
| Phase 1 | `users` 表 + migration / register + login + `/me` + JWT 中间件 + RBAC 依赖 |
| Phase 2 | refresh / logout / admin 端点 |
| Phase 3 | 登录审计日志 / refresh token rotation / 密码重置流程 |

---

## 附录 A：与现有代码风格对齐检查清单

- [x] 表名用小写复数（`users` 对齐 `stocks`、`predictions`）
- [x] `SERIAL PRIMARY KEY` 对齐 `screening_scores`、`predictions`
- [x] `TIMESTAMP DEFAULT NOW()` 对齐全部应用层表
- [x] 索引命名 `idx_<table>_<column>` 对齐 `idx_daily_kline_code`
- [x] FastAPI 路由前缀 `/api/v1/` 对齐 `screener-service`
- [x] Pydantic `BaseModel` + `Field` 验证对齐 FastAPI 惯用模式
- [x] Config 从 `os.environ.get()` 对齐 `app/config.py` 风格
- [x] 服务层 `app/services/auth.py` 封装 JWT 加解密逻辑
