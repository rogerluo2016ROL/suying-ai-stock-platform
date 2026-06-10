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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: seed roles + admin user. Shutdown: dispose engine."""
    # Import here to avoid circular deps
    from app.services.auth_service import seed_roles
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
