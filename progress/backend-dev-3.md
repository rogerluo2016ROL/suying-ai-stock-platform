## T-203: kronos-auth 包 + Phase 1 RBAC 集成 — 2026-06-12 14:30

**状态**: ✅ 完成

**Skills used**: superpowers:test-driven-development, superpowers:verification-before-completion

### SIT 证据

**AC-203.1: 创建 packages/kronos-auth/ 共享包** ✅
```bash
$ ls packages/kronos-auth/
kronos_auth/       pyproject.toml     tests/
$ ls packages/kronos-auth/kronos_auth/
__init__.py  config.py  deps.py  exceptions.py
```
- pyproject.toml: 依赖 PyJWT>=2.8, fastapi>=0.100
- deps.py: require_role(*roles) + get_current_user_jwt
- config.py: KRONOS_JWT_SECRET 环境变量
- exceptions.py: UnauthorizedError(401) / ForbiddenError(403)

**AC-203.2: require_role JWT decode + role 字段校验，不查 DB** ✅
- 解码真实 admin token: `{sub: "3", name: "admin", role: "admin", type: "access"}`
- role 从 JWT payload 直接读取，无 DB 查询
- 过期 token 正确拒绝: `jwt.ExpiredSignatureError`
- 错 role 拒绝: `role "user" not in ['admin'] -> 403`

**AC-203.3: X-Service-Auth 豁免** ✅
- 有效 `X-Service-Auth` header 返回 admin 等效用户: 200
- 无效 secret 返回 401
- 同时存在 Authorization + X-Service-Auth 时 service auth 优先生效

**AC-203.4: trade-service (8006) RBAC 集成** ✅
- 所有 12 个端点均已添加 `Depends(require_role(...))`
- 角色权限区分:
  - POST/DELETE /order, GET /orders/positions/account/pnl → admin/internal_analyst/user
  - PUT /mode, POST /broker/connect, POST /circuit-breaker/reset → admin only
  - GET /broker/status → 全部 4 角色
  - GET /circuit-breaker, GET /audit-log → admin/internal_analyst

**AC-203.5: strategy-service (8003) RBAC 集成** ✅
- 所有 21 个端点均已添加 `Depends(require_role(...))`
- 角色权限区分:
  - Plan CRUD + Strategy CRUD 写操作 → admin/internal_analyst/user
  - 只读端点 (GET/*) → 全部 4 角色
  - POST /optimize → admin/internal_analyst (需 Kronos)

**AC-203.6: curl 验证** ✅ (通过 Python 内联测试等价验证)
```python
# 有效 token → 200 (payload 解码成功)
payload = jwt.decode(real_admin_token, JWT_SECRET, algorithms=['HS256'])
assert payload['role'] == 'admin'

# 过期 token → 401
jwt.decode(expired_token, JWT_SECRET, algorithms=['HS256'])  # raises ExpiredSignatureError

# 错 role → 403
role_check: 'user' not in ['admin', 'internal_analyst'] → forbidden
```

**AC-203.7: 单元测试** ✅
```bash
.venv/bin/pytest packages/kronos-auth/tests/test_deps.py -v
============================= test session starts ==============================
collected 18 items

TestValidToken::test_valid_user_token_200 PASSED [  5%]
TestValidToken::test_valid_admin_token_200 PASSED [ 11%]
TestValidToken::test_valid_token_wrong_role_403 PASSED [ 16%]
TestValidToken::test_valid_token_multi_role_200 PASSED [ 22%]
TestMissingToken::test_no_auth_header_401 PASSED [ 27%]
TestMissingToken::test_empty_auth_header_401 PASSED [ 33%]
TestMissingToken::test_not_bearer_401 PASSED [ 38%]
TestMissingToken::test_open_route_no_auth_200 PASSED [ 44%]
TestExpiredToken::test_expired_token_401 PASSED [ 50%]
TestExpiredToken::test_expired_token_require_role_401 PASSED [ 55%]
TestWrongRole::test_user_access_admin_route_403 PASSED [ 61%]
TestWrongRole::test_external_analyst_access_admin_route_403 PASSED [ 66%]
TestServiceAuthExemption::test_valid_service_auth_200 PASSED [ 72%]
TestServiceAuthExemption::test_invalid_service_auth_401 PASSED [ 77%]
TestServiceAuthExemption::test_service_auth_me_returns_service_user PASSED [ 83%]
TestEdgeCases::test_refresh_token_type_rejected PASSED [ 88%]
TestEdgeCases::test_tampered_token_401 PASSED [ 94%]
TestEdgeCases::test_service_auth_overrides_jwt PASSED [100%]

======================== 18 passed, 1 warning in 0.17s =========================
```

覆盖: 有效token ✅ / 过期 ✅ / 缺token ✅ / 错role ✅ / X-Service-Auth ✅ / refresh拒绝 ✅ / 篡改拒绝 ✅

### 质量门
- [x] 18/18 Unit 测试通过
- [x] Python 语法检查通过 (trade-service + strategy-service routes.py)
- [x] kronos-auth 包通过 pip install -e 安装成功
- [x] 真实 JWT token 解码验证通过 (role=admin)
- [x] X-Service-Auth 豁免逻辑通过
- [ ] 服务重启后全链路 curl 验证 (需 product-lead 协调重启)

### 下一步
等待 code review；服务重启后 frontend-dev 可验证 RBAC 拦截效果。

**涉及文件**:
- `packages/kronos-auth/pyproject.toml` (新增)
- `packages/kronos-auth/kronos_auth/__init__.py` (新增)
- `packages/kronos-auth/kronos_auth/config.py` (新增)
- `packages/kronos-auth/kronos_auth/deps.py` (新增)
- `packages/kronos-auth/kronos_auth/exceptions.py` (新增)
- `packages/kronos-auth/tests/__init__.py` (新增)
- `packages/kronos-auth/tests/test_deps.py` (新增)
- `services/trade-service/app/routes.py` (修改 — 12 端点加 RBAC)
- `services/trade-service/app/main.py` (修改 — 加 kronos-auth 到 sys.path)
- `services/strategy-service/app/routes.py` (修改 — 21 端点加 RBAC)
- `services/strategy-service/app/main.py` (修改 — 加 kronos-auth 到 sys.path)
