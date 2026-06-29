"""Auth API routes — register, login, refresh, logout, me. PRD v1.1 compliant."""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import JWT_ACCESS_EXPIRE_SECONDS, JWT_REFRESH_EXPIRE_SECONDS
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    RefreshRequest,
    UpdateMeRequest,
    RegisterResponse,
    LoginResponse,
    AuthTokenResponse,
    UserResponse,
    TokenUserResponse,
    MessageResponse,
)
from app.services.auth_service import (
    create_user,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    store_refresh_token,
    revoke_user_tokens,
    update_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE_KEY = "refresh_token"
REFRESH_COOKIE_MAX_AGE = JWT_REFRESH_EXPIRE_SECONDS
REFRESH_COOKIE_SECURE = os.environ.get(
    "AUTH_COOKIE_SECURE",
    "true" if os.environ.get("KRONOS_ENV", "").lower() == "production" else "false",
).lower() in ("1", "true", "yes")


def _role_name(user: User) -> str:
    return user.role.name if user.role else "user"


def _role_defaults(role: str, user_id: int | None = None) -> dict[str, str | None]:
    if role == "admin":
        return {
            "tenant_id": "platform",
            "tenant_name": "平台运营",
            "default_trade_account_id": None,
            "trade_mode": "paper",
            "broker_adapter": "paper",
        }
    return {
        "tenant_id": "tenant-default",
        "tenant_name": "默认租户",
        "default_trade_account_id": f"paper-u{user_id}" if user_id is not None else "paper-default",
        "trade_mode": "paper",
        "broker_adapter": "paper",
    }


def _select_default(items: Any) -> Any | None:
    if not items:
        return None
    values = list(items)
    return next((item for item in values if getattr(item, "is_default", False)), values[0])


def _loaded_relation(user: User, name: str) -> Any:
    return getattr(user, "__dict__", {}).get(name)


def _platform_profile(user: User) -> dict[str, Any]:
    profile = _role_defaults(_role_name(user), user.id)
    membership = _select_default(_loaded_relation(user, "memberships"))
    tenant = getattr(membership, "tenant", None)
    if tenant is not None:
        profile["tenant_id"] = str(getattr(tenant, "slug", None) or getattr(tenant, "id", profile["tenant_id"]))
        profile["tenant_name"] = getattr(tenant, "name", None) or profile["tenant_name"]

    account = _select_default(_loaded_relation(user, "broker_accounts"))
    if account is not None:
        profile["default_trade_account_id"] = getattr(account, "account_id", None)
        profile["trade_mode"] = getattr(account, "trade_mode", None) or profile["trade_mode"]
        profile["broker_adapter"] = getattr(account, "adapter", None) or profile["broker_adapter"]

    account_id = profile.get("default_trade_account_id")
    profile["broker_connect_config"] = (
        {
            "broker_name": "mock_qmt",
            "account_id": account_id,
            "server_ip": "127.0.0.1",
            "server_port": 16001,
            "environment": "sandbox",
        }
        if account_id
        else None
    )

    return profile


def build_token_user_response(user: User) -> TokenUserResponse:
    return TokenUserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=_role_name(user),
        **_platform_profile(user),
    )


def build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=_role_name(user),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        **_platform_profile(user),
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set httpOnly refresh_token cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite="strict",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh_token cookie (logout)."""
    response.delete_cookie(
        key=REFRESH_COOKIE_KEY,
        path="/api/v1/auth",
        httponly=True,
        secure=REFRESH_COOKIE_SECURE,
        samesite="strict",
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account. Auto-login: returns access_token + sets refresh cookie."""
    try:
        user = await create_user(
            db,
            name=body.name,
            email=body.email,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    # Issue tokens for auto-login
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    await store_refresh_token(db, user.id, refresh_token)
    _set_refresh_cookie(response, refresh_token)

    return RegisterResponse(
        access_token=access_token,
        expires_in=JWT_ACCESS_EXPIRE_SECONDS,
        user=build_token_user_response(user),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email + password. access_token in body, refresh_token in httpOnly cookie."""
    user = await authenticate_user(db, body.email, body.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    await store_refresh_token(db, user.id, refresh_token)
    _set_refresh_cookie(response, refresh_token)

    return LoginResponse(
        access_token=access_token,
        expires_in=JWT_ACCESS_EXPIRE_SECONDS,
        user=build_token_user_response(user),
    )


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshRequest = RefreshRequest(),
    db: AsyncSession = Depends(get_db),
):
    """Exchange a valid refresh token (from httpOnly cookie or body) for a new access token."""
    # Body token is an explicit fallback/test path; prefer it when supplied so
    # replay checks are not masked by a newer cookie already stored in the client.
    refresh_token = body.refresh_token or request.cookies.get(REFRESH_COOKIE_KEY)

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    result = await rotate_refresh_token(db, refresh_token)

    if result is None:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已过期或无效",
        )

    new_access, new_refresh, _user = result
    _set_refresh_cookie(response, new_refresh)

    return AuthTokenResponse(
        access_token=new_access,
        expires_in=JWT_ACCESS_EXPIRE_SECONDS,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout: revoke all refresh tokens and clear cookie."""
    await revoke_user_tokens(db, current_user.id)
    _clear_refresh_cookie(response)
    return MessageResponse(message="已登出")


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user),
):
    """Return the current authenticated user's profile."""
    return build_user_response(current_user)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the current user's profile (name and/or password)."""
    try:
        user = await update_user(
            db,
            current_user,
            name=body.name,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return build_user_response(user)
