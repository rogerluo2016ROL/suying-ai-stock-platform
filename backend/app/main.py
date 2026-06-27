"""FastAPI application entry point — 速赢AI智能选股平台."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import DEBUG
from app.database import engine, AsyncSessionLocal
from app.models.base import Base
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router


def _run_migrations() -> None:
    """AC-8: run `alembic upgrade head` programmatically before seed_roles.

    Ensures auth/audit/circuit_breaker tables exist regardless of how backend
    is started (docker compose / manual uvicorn). Idempotent. Sync (psycopg2
    via DATABASE_SYNC_URL); called via asyncio.to_thread from the async lifespan.
    ADR-007 Q-4 dual-track: business tables via init_postgres.sql, auth/audit/
    training/circuit_breaker tables via alembic — this runs the alembic track.
    Failure (e.g. PG unreachable) aborts startup cleanly rather than crashing
    later in seed_roles with a cryptic 'relation does not exist'.
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
    cfg = AlembicConfig(os.path.join(base_dir, "alembic.ini"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: migrate (alembic) + seed roles + admin user. Shutdown: dispose engine."""
    import asyncio

    # AC-8: ensure auth/audit/circuit_breaker schema exists before seed_roles.
    await asyncio.to_thread(_run_migrations)

    # Import here to avoid circular deps
    from app.services.auth_service import seed_roles
    from app.services.platform_service import ensure_platform_defaults
    from app.config import ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME

    async with AsyncSessionLocal() as db:
        # Ensure roles exist
        await seed_roles(db)

        # Seed admin user if not exists
        from sqlalchemy import select
        from app.models.user import User, Role
        from app.services.auth_service import hash_password

        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        if not result.scalar_one_or_none():
            role_result = await db.execute(select(Role).where(Role.name == "admin"))
            admin_role = role_result.scalar_one()
            admin_user = User(
                name=ADMIN_NAME,
                email=ADMIN_EMAIL,
                password_hash=hash_password(ADMIN_PASSWORD),
                role_id=admin_role.id,
            )
            db.add(admin_user)
            await db.commit()

        await ensure_platform_defaults(db)

    yield

    await engine.dispose()


app = FastAPI(
    title="速赢AI智能选股平台",
    version="0.2.0",
    lifespan=lifespan,
)

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/api/health")
async def health():
    return {"status": "healthy"}
