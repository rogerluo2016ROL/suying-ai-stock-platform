"""Application configuration — all environment-driven."""

import os

# ── Database ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kronos:kronos@localhost:6432/kronos",
)
DATABASE_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://kronos:kronos@localhost:6432/kronos",
)

# ── JWT ──
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    import secrets
    JWT_SECRET_KEY = secrets.token_hex(32)
    import warnings
    warnings.warn("JWT_SECRET_KEY not set — using random key. Set in production!", RuntimeWarning)
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRE_SECONDS = int(os.environ.get("JWT_ACCESS_EXPIRE_SECONDS", "900"))  # 15 min
JWT_REFRESH_EXPIRE_SECONDS = int(os.environ.get("JWT_REFRESH_EXPIRE_SECONDS", "604800"))  # 7 days

# ── Argon2 ──
ARGON2_TIME_COST = int(os.environ.get("ARGON2_TIME_COST", "3"))
ARGON2_MEMORY_COST = int(os.environ.get("ARGON2_MEMORY_COST", "65536"))  # 64 MiB
ARGON2_PARALLELISM = int(os.environ.get("ARGON2_PARALLELISM", "2"))

# ── Admin seed ──
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@suying.ai")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin123!")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "admin")

# ── Server ──
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
