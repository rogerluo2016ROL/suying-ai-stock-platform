"""API Gateway — unified auth, rate-limit, reverse-proxy to backend services.

Usage: python -m uvicorn services.api-gateway.app.main:app --port 8000 --reload
"""

import logging
import os
import sys
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ── Configuration ──
JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY", "dev-secret-change-in-production-min-32-chars!!"
)
JWT_ALGORITHM = "HS256"
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kronos:kronos@localhost:6432/kronos",
)
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*").split(",")

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] gateway: %(message)s",
)
logger = logging.getLogger("api-gateway")

# ── Database engine (shared PostgreSQL for user/role lookup) ──
engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


# ── JWT Auth ──
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Validate JWT token, return user dict with id/name/email/role/is_active."""
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
    """Dependency factory: restrict endpoint to specific roles."""

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


# ── Rate Limiter (in-memory, per IP) ──
class RateLimiter:
    """Simple sliding-window rate limiter: max `requests` per `window_seconds` per IP."""

    def __init__(self, requests: int = 60, window_seconds: int = 60):
        self.requests = requests
        self.window_seconds = window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)

    def _clean(self, ip: str, now: float) -> None:
        cutoff = now - self.window_seconds
        entries = self._store[ip]
        while entries and entries[0] < cutoff:
            entries.pop(0)

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self._clean(ip, now)
        if len(self._store[ip]) >= self.requests:
            return False
        self._store[ip].append(now)
        return True

    async def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if not self.is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Max 60 requests per minute.",
            )


rate_limiter = RateLimiter(requests=60, window_seconds=60)

# ── Lifespan ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API Gateway starting on port %d...", GATEWAY_PORT)
    yield
    logger.info("API Gateway stopped.")


# ── FastAPI App ──
app = FastAPI(
    title="速赢AI - API Gateway",
    description="Unified authentication, rate-limiting, and reverse-proxy gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health ──


@app.get("/api/health")
async def health():
    return {"status": "healthy", "service": "api-gateway", "version": "0.1.0"}


# ── Routes ──
from app.routes import router  # noqa: E402

app.include_router(router)


# ── Entry ──
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=GATEWAY_PORT,
        reload=True,
    )
