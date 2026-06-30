"""Pydantic schemas for auth API — PRD v1.1 compliant."""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

VALID_ROLES = {"admin", "internal_analyst", "external_analyst", "user"}


# ── Request schemas ──

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50, description="Display name")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128, description="Min 8 chars")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Refresh token can come from httpOnly cookie or request body (fallback)."""
    refresh_token: str | None = None


class UpdateMeRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit")
        return v


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, description="New role name")
    is_active: bool | None = Field(default=None, description="Enable/disable account")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v


# ── Response schemas ──

class MembershipInfoResponse(BaseModel):
    status: str = "inactive"
    plan: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    source: str | None = None
    note: str | None = None
    is_member: bool = False
    days_remaining: int | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    tenant_id: str | None = None
    tenant_name: str | None = None
    default_trade_account_id: str | None = None
    trade_mode: str | None = None
    broker_adapter: str | None = None
    broker_connect_config: dict[str, str | int] | None = None
    permissions: list[str] = Field(default_factory=list)
    membership: MembershipInfoResponse | None = None

    model_config = {"from_attributes": True}


class TokenUserResponse(BaseModel):
    """User info embedded in login/register token responses."""
    id: int
    name: str
    email: str
    role: str
    tenant_id: str | None = None
    tenant_name: str | None = None
    default_trade_account_id: str | None = None
    trade_mode: str | None = None
    broker_adapter: str | None = None
    broker_connect_config: dict[str, str | int] | None = None
    permissions: list[str] = Field(default_factory=list)
    membership: MembershipInfoResponse | None = None


class AuthTokenResponse(BaseModel):
    """Token response without refresh_token (goes via httpOnly cookie)."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(AuthTokenResponse):
    user: TokenUserResponse


class RegisterResponse(AuthTokenResponse):
    user: TokenUserResponse


class MessageResponse(BaseModel):
    message: str


class PaginatedUsersResponse(BaseModel):
    total: int
    page: int
    page_size: int
    users: list[UserResponse]
