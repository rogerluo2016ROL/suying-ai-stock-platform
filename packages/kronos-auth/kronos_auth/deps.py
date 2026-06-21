"""FastAPI dependencies — JWT auth + RBAC + X-Service-Auth exemption.

No database dependency. JWT payload carries the role string directly.

Usage:
    from kronos_auth import require_role, get_current_user_jwt

    @router.get("/admin/endpoint")
    async def admin_only(user=Depends(require_role("admin"))):
        ...

    @router.get("/any-authenticated")
    async def any_user(user=Depends(get_current_user_jwt)):
        ...
"""

import logging
from typing import Dict, Optional

import jwt
from fastapi import Depends, Header, Request
from jwt import ExpiredSignatureError, InvalidTokenError

from kronos_auth.config import KRONOS_JWT_SECRET, KRONOS_SERVICE_SECRET, JWT_ALGORITHM, SERVICE_AUTH_ENABLED
from kronos_auth.exceptions import UnauthorizedError, ForbiddenError

logger = logging.getLogger("kronos-auth")

X_SERVICE_AUTH_HEADER = "X-Service-Auth"
# C-1: must match the `dev-only-` prefix used by config._secret() dev fallbacks.
# Any secret still carrying this prefix MUST NOT grant X-Service-Auth exemption,
# regardless of whether KRONOS_ENV=production is set on the deployment side.
_DEV_SECRET_PREFIX = "dev-only-"


async def _extract_bearer_token(request: Request) -> str:
    """Extract the Bearer token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")
    return auth.split(" ", 1)[1]


def _decode_and_validate(token: str) -> dict:
    """Decode JWT and validate it is an access token.

    Returns the payload dict on success.
    Raises HTTPException (401) on any failure.
    """
    try:
        payload = jwt.decode(token, KRONOS_JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise UnauthorizedError("Token has expired")
    except InvalidTokenError:
        raise UnauthorizedError("Invalid authentication token")

    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid token type")

    return payload


async def get_current_user_jwt(request: Request) -> dict:
    """Decode JWT from Authorization header, return payload dict.

    Supports X-Service-Auth exemption for internal service-to-service calls.

    Raises 401 if missing/invalid token.
    Returns the decoded JWT payload dict with keys: sub, name, role, exp, iat, type, jti.
    """
    # ── X-Service-Auth exemption ──
    service_auth = request.headers.get(X_SERVICE_AUTH_HEADER, "")
    if service_auth:
        # C-1 安全硬约束（code-reviewer 验收清单 §3-3）：SERVICE_AUTH_ENABLED 仅在
        # secret 非 dev-only- 前缀时为 True。dev fallback（仓库可见）绝不能授予 admin
        # 豁免 → 一律拒绝。不依赖部署是否设 KRONOS_ENV=production。
        if not SERVICE_AUTH_ENABLED:
            logger.error(
                "X-Service-Auth rejected: KRONOS_SERVICE_SECRET is a dev-only "
                "fallback — inject a real secret to enable service-to-service auth"
            )
            raise UnauthorizedError("Service auth not configured (dev fallback)")
        if service_auth == KRONOS_SERVICE_SECRET:
            return {
                "sub": "service",
                "name": "internal-service",
                "role": "admin",
                "type": "access",
                "jti": "",
            }
        else:
            raise UnauthorizedError("Invalid service auth secret")

    # ── JWT Bearer token ──
    token = await _extract_bearer_token(request)
    return _decode_and_validate(token)


def require_role(*roles: str):
    """FastAPI dependency factory: restrict endpoint to specific roles.

    Checks the JWT payload's ``role`` field against *roles.
    Also accepts requests bearing a valid X-Service-Auth header (admin-equivalent).

    Usage::

        @router.get("/admin/users")
        async def list_users(user: dict = Depends(require_role("admin"))):
            ...

    Args:
        *roles: One or more role names that are allowed access.
    """

    async def role_checker(
        user: dict = Depends(get_current_user_jwt),
    ) -> dict:
        user_role = user.get("role", "")
        if user_role not in roles:
            raise ForbiddenError(
                f"Requires one of roles: {', '.join(roles)}"
            )
        return user

    return role_checker
