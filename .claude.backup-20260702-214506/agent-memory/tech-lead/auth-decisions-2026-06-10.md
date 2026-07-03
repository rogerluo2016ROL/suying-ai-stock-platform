---
name: auth-decisions-2026-06-10
description: Auth/RBAC 技术选型：PyJWT + argon2 + httpOnly cookie + FastAPI Depends
metadata:
  type: project
---

ADR-001 技术决策摘要（2026-06-10）：
- JWT: PyJWT 2.13.0（否决 python-jose，因 CVE 历史 + 维护不活跃）
- 密码哈希: argon2-cffi 25.1.0 Argon2id（否决 bcrypt，因其自身推荐迁移）
- Token 存储: Refresh Token 存 httpOnly Secure SameSite=Strict cookie；Access Token 存内存
- RBAC: FastAPI Depends() 依赖注入，4 角色
- Auth 服务: 独立 FastAPI 微服务，端口 8010
- 数据库: PostgreSQL，表命名延续 snake_case
- 否决备选: python-jose+bcrypt、Session认证、OAuth2/OIDC

**Why:** 项目首次建立认证体系，需在 Phase A 就选对技术栈以避免后续迁移成本。
**How to apply:** 所有后端服务的 auth 实现必须引用 ADR-001；新增依赖前查 ADR 是否已覆盖。
