"""Pydantic schemas for admin authorization and membership APIs."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.auth import MembershipInfoResponse, VALID_ROLES
from app.services.rbac_service import VALID_MEMBERSHIP_STATUSES, VALID_PERMISSION_KEYS


class PermissionItemResponse(BaseModel):
    key: str
    label: str
    group: str
    description: str
    enabled: bool


class RolePermissionsResponse(BaseModel):
    role: str
    label: str
    description: str | None = None
    permissions: list[PermissionItemResponse]


class RolePermissionsListResponse(BaseModel):
    roles: list[RolePermissionsResponse]


class UpdateRolePermissionsRequest(BaseModel):
    permission_keys: list[str] = Field(default_factory=list)

    @field_validator("permission_keys")
    @classmethod
    def validate_permission_keys(cls, v: list[str]) -> list[str]:
        unknown = sorted(set(v) - VALID_PERMISSION_KEYS)
        if unknown:
            raise ValueError(f"Invalid permission keys: {', '.join(unknown)}")
        return sorted(set(v))


class MembershipUpdateRequest(BaseModel):
    status: str | None = None
    plan: str | None = Field(default=None, max_length=40)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    source: str | None = Field(default=None, max_length=40)
    note: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_MEMBERSHIP_STATUSES:
            raise ValueError(
                "Invalid membership status. Must be one of: "
                + ", ".join(sorted(VALID_MEMBERSHIP_STATUSES))
            )
        return v

    @model_validator(mode="after")
    def validate_period(self):
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("membership ends_at must be later than starts_at")
        return self


class UpdateUserAuthorizationRequest(BaseModel):
    role: str | None = Field(default=None, description="New role name")
    is_active: bool | None = Field(default=None, description="Enable/disable account")
    membership: MembershipUpdateRequest | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_ROLES:
            raise ValueError(f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}")
        return v


class MembershipUserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    membership: MembershipInfoResponse


class PaginatedMembershipsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    members: list[MembershipUserResponse]
