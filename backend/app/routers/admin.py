"""Admin API routes — user management."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UpdateUserRequest,
    UserResponse,
    PaginatedUsersResponse,
)
from app.schemas.admin import (
    PaginatedMembershipsResponse,
    RolePermissionsListResponse,
    RolePermissionsResponse,
    UpdateRolePermissionsRequest,
    UpdateUserAuthorizationRequest,
)
from app.services.auth_service import (
    get_user_by_id,
    list_users,
    update_user_role,
    set_user_active,
)
from app.services.rbac_service import (
    VALID_MEMBERSHIP_STATUSES,
    default_membership_for_user,
    list_membership_users,
    list_role_permissions,
    role_permissions_for_user,
    set_role_permissions,
    summarize_membership,
    update_user_authorization,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _role_name(user: User) -> str:
    return user.role.name if user.role else "user"


def _user_to_response(user: User) -> UserResponse:
    membership = default_membership_for_user(user)
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=_role_name(user),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        permissions=role_permissions_for_user(user),
        membership=summarize_membership(membership),
    )


def _membership_user_to_response(user: User) -> dict:
    membership = default_membership_for_user(user)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": _role_name(user),
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "membership": summarize_membership(membership),
    }


@router.get("/permissions/roles", response_model=RolePermissionsListResponse)
async def admin_list_role_permissions(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List role menu permissions. Admin only."""
    roles = await list_role_permissions(db)
    return RolePermissionsListResponse(roles=roles)


@router.put("/permissions/roles/{role_name}", response_model=RolePermissionsResponse)
async def admin_update_role_permissions(
    role_name: str,
    body: UpdateRolePermissionsRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Replace enabled permissions for a role. Admin only."""
    try:
        return await set_role_permissions(db, role_name, body.permission_keys)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/users", response_model=PaginatedUsersResponse)
async def admin_list_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: str | None = Query(None, description="Filter by role"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    q: str | None = Query(None, description="Search by name or email"),
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination and optional filters. Admin only."""
    users, total = await list_users(
        db, page=page, page_size=page_size, role=role, is_active=is_active, q=q
    )
    return PaginatedUsersResponse(
        total=total,
        page=page,
        page_size=page_size,
        users=[_user_to_response(u) for u in users],
    )


@router.put("/users/{user_id}/role", response_model=UserResponse)
async def admin_update_user_role(
    user_id: int,
    body: UpdateUserRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role. Admin only. Cannot change own role."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的角色",
        )

    target = await get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if body.role:
        try:
            target = await update_user_role(db, target, body.role)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if body.is_active is not None:
        target = await set_user_active(db, target, body.is_active)

    return _user_to_response(target)


@router.put("/users/{user_id}/authorization", response_model=UserResponse)
async def admin_update_user_authorization(
    user_id: int,
    body: UpdateUserAuthorizationRequest,
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Update a user's role, active flag, and membership entitlement. Admin only."""
    if user_id == current_user.id and (body.role is not None or body.is_active is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的角色或启停状态",
        )

    target = await get_user_by_id(db, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    membership_update = (
        body.membership.model_dump(exclude_unset=True)
        if body.membership is not None
        else None
    )
    try:
        updated = await update_user_authorization(
            db,
            target,
            role_name=body.role,
            is_active=body.is_active,
            membership_update=membership_update,
            actor_user_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return _user_to_response(updated)


@router.get("/memberships", response_model=PaginatedMembershipsResponse)
async def admin_list_memberships(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: str | None = Query(None, alias="status", description="Membership status"),
    q: str | None = Query(None, description="Search by name or email"),
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """List users with membership entitlement summary. Admin only."""
    if status_filter is not None and status_filter not in VALID_MEMBERSHIP_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="会员状态无效")

    users, total = await list_membership_users(
        db,
        page=page,
        page_size=page_size,
        status=status_filter,
        q=q,
    )
    return PaginatedMembershipsResponse(
        total=total,
        page=page,
        page_size=page_size,
        members=[_membership_user_to_response(user) for user in users],
    )
