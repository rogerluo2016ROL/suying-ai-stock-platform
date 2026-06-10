"""FastAPI dependencies — JWT auth + RBAC for training-service.

Verifies tokens using the same JWT_SECRET_KEY as the backend,
reads user/role data from the shared PostgreSQL database.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import JWT_SECRET_KEY, JWT_ALGORITHM
from app.database import get_db

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    """Extract JWT from Authorization header, validate, return user record.

    Returns a dict with keys: id, name, email, role, is_active.
    Raises 401 if missing/invalid token or inactive user.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    # Query user with role from shared PostgreSQL
    result = await db.execute(
        sa_text(
            "SELECT u.id, u.name, u.email, u.is_active, r.name as role "
            "FROM users u JOIN roles r ON u.role_id = r.id "
            "WHERE u.id = :uid"
        ),
        {"uid": int(user_id)},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    user = dict(row._mapping)
    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    return user


def require_role(*roles: str):
    """FastAPI dependency factory: restrict endpoint to specific roles.

    Usage:
        @router.post("/training/run")
        async def run_training(
            user: dict = Depends(require_role("admin"))
        ):
            ...
    """

    async def role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        user_role = current_user.get("role", "")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(roles)}",
            )
        return current_user

    return role_checker
