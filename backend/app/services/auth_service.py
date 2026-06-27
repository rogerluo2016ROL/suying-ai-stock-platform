"""Auth service — JWT creation/verification, password hashing, user CRUD."""

import hashlib
import secrets
import time
from datetime import datetime, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
    JWT_ACCESS_EXPIRE_SECONDS,
    JWT_REFRESH_EXPIRE_SECONDS,
    ARGON2_TIME_COST,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
)
from app.models.user import User, Role, RefreshToken
from app.models.platform import Membership

# ── Argon2id hasher ──
_ph = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password with argon2id."""
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an argon2id hash."""
    try:
        return _ph.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# ── JWT ──

def _create_token(user: User, token_type: str, expire_seconds: int) -> str:
    """Create a signed JWT with standard claims."""
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "name": user.name,
        "role": user.role.name if user.role else "user",
        "iat": now,
        "exp": now + expire_seconds,
        "type": token_type,
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user: User) -> str:
    return _create_token(user, "access", JWT_ACCESS_EXPIRE_SECONDS)


def create_refresh_token(user: User) -> str:
    return _create_token(user, "refresh", JWT_REFRESH_EXPIRE_SECONDS)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Returns payload dict or raises JWT error."""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def _hash_token(token: str) -> str:
    """SHA-256 hash a refresh token for DB storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── User operations ──

async def create_user(
    db: AsyncSession,
    name: str,
    email: str,
    password: str,
    role_name: str = "user",
) -> User:
    """Create a new user with hashed password. Raises ValueError on duplicate."""
    # Check for duplicate email
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError("邮箱已注册")

    # Resolve role
    role = await _get_role_by_name(db, role_name)
    if not role:
        raise ValueError(f"Unknown role: {role_name}")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        role_id=role.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # Eager-load role
    await db.refresh(user, attribute_names=["role"])
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """Verify credentials and return user. Returns None if invalid."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User)
        .where(User.email == email)
        .options(
            selectinload(User.role),
            selectinload(User.memberships).selectinload(Membership.tenant),
            selectinload(User.broker_accounts),
        )
    )
    user = result.scalar_one_or_none()

    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    """Fetch a user by ID with role eager-loaded."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.role),
            selectinload(User.memberships).selectinload(Membership.tenant),
            selectinload(User.broker_accounts),
        )
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """Fetch a user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


# ── Role operations ──

async def _get_role_by_name(db: AsyncSession, name: str) -> Role | None:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def seed_roles(db: AsyncSession) -> dict[str, Role]:
    """Ensure the 4 standard roles exist. Returns name→Role map."""
    role_names = ["admin", "internal_analyst", "external_analyst", "user"]
    role_map: dict[str, Role] = {}

    for name in role_names:
        existing = await _get_role_by_name(db, name)
        if existing:
            role_map[name] = existing
        else:
            desc = {
                "admin": "系统管理员，拥有全部权限",
                "internal_analyst": "内部分析师，可回测和客户管理",
                "external_analyst": "外部分析师，可查看分析结果但不可交易",
                "user": "普通用户，可交易和查看选股结果",
            }.get(name, "")
            role = Role(name=name, description=desc)
            db.add(role)
            await db.flush()
            role_map[name] = role

    await db.commit()
    return role_map


# ── Refresh token operations ──

async def store_refresh_token(
    db: AsyncSession, user_id: int, token: str, family: str | None = None
) -> RefreshToken:
    """Store a hashed refresh token in DB. Creates a new token family if not provided."""
    if family is None:
        family = secrets.token_hex(16)

    exp = datetime.now(timezone.utc).timestamp() + JWT_REFRESH_EXPIRE_SECONDS
    token_record = RefreshToken(
        user_id=user_id,
        token_hash=_hash_token(token),
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
        family=family,
    )
    db.add(token_record)
    await db.commit()
    return token_record


async def rotate_refresh_token(
    db: AsyncSession, old_token: str
) -> tuple[str, str, User] | None:
    """Validate old refresh token, revoke the whole family, issue new pair.

    Returns (new_access_token, new_refresh_token, user) or None if invalid.

    P1-5: verify signature + ``type == refresh`` claim BEFORE the DB lookup.
    Security currently holds by coincidence (refresh_tokens table only stores
    hashes of tokens issued by create_refresh_token, so an access-token hash
    never matches), but verifying explicitly defends against any future code
    path that hashes non-refresh tokens into this table.
    """
    # P1-5: verify it's a valid refresh token before trusting it for rotation.
    # BE-P1 review W-1: widen the guard beyond jwt.PyJWTError so a non-string
    # token (None/int/dict from a future code path) raises TypeError/ValueError
    # and is rejected the same way as a malformed/expired JWT — matches the
    # docstring claim "defends against any future code path".
    try:
        payload = decode_token(old_token)
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
    if payload.get("type") != "refresh":
        return None

    token_hash = _hash_token(old_token)

    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .options(selectinload(RefreshToken.user).selectinload(User.role))
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        return None
    if token_record.revoked:
        # Replay attack detected — revoke entire family
        await _revoke_family(db, token_record.family)
        await db.commit()
        return None
    if token_record.expires_at < datetime.now(timezone.utc):
        return None

    # Revoke the entire family and issue new tokens
    family = token_record.family
    user = token_record.user

    await _revoke_family(db, family)

    # Create new token pair with the same family
    new_refresh = create_refresh_token(user)
    new_access = create_access_token(user)

    new_record = RefreshToken(
        user_id=user.id,
        token_hash=_hash_token(new_refresh),
        expires_at=datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() + JWT_REFRESH_EXPIRE_SECONDS,
            tz=timezone.utc,
        ),
        family=family,
    )
    db.add(new_record)
    await db.commit()

    return new_access, new_refresh, user


async def _revoke_family(db: AsyncSession, family: str) -> None:
    """Mark all tokens in a family as revoked."""
    from sqlalchemy import update

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family == family)
        .values(revoked=True)
    )


async def revoke_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Revoke all refresh tokens for a user (used on logout)."""
    from sqlalchemy import update

    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .values(revoked=True)
    )
    await db.commit()


async def update_user(
    db: AsyncSession, user: User, name: str | None, password: str | None
) -> User:
    """Update user profile fields."""
    if name is not None:
        # Check uniqueness
        existing = await db.execute(
            select(User).where(User.name == name, User.id != user.id)
        )
        if existing.scalar_one_or_none():
            raise ValueError("用户名已存在")
        user.name = name

    if password is not None:
        user.password_hash = hash_password(password)

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
    role: str | None = None,
    is_active: bool | None = None,
    q: str | None = None,
) -> tuple[list[User], int]:
    """Paginated user listing with optional filters."""
    from sqlalchemy.orm import selectinload

    query = select(User).options(selectinload(User.role))
    count_query = select(func.count(User.id))

    if role:
        query = query.join(Role).where(Role.name == role)
        count_query = count_query.join(Role).where(Role.name == role)

    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    if q:
        like_pattern = f"%{q}%"
        query = query.where(
            (User.name.ilike(like_pattern)) | (User.email.ilike(like_pattern))
        )
        count_query = count_query.where(
            (User.name.ilike(like_pattern)) | (User.email.ilike(like_pattern))
        )

    # Get total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get page
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    users = list(result.scalars().all())

    return users, total


async def update_user_role(
    db: AsyncSession, target_user: User, role_name: str
) -> User:
    """Change a user's role."""
    role = await _get_role_by_name(db, role_name)
    if not role:
        raise ValueError(f"Unknown role: {role_name}")

    target_user.role_id = role.id
    target_user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target_user, attribute_names=["role"])
    return target_user


async def set_user_active(db: AsyncSession, target_user: User, is_active: bool) -> User:
    """Enable or disable a user account."""
    target_user.is_active = is_active
    target_user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target_user, attribute_names=["role"])
    return target_user
