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
from app.services.auth_service import (
    get_user_by_id,
    list_users,
    update_user_role,
    set_user_active,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _role_name(user: User) -> str:
    return user.role.name if user.role else "user"


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        role=_role_name(user),
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


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
