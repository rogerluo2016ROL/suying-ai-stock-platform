"""Diagnosis-service configuration — all environment-driven."""

import os

# ── Server ──
HOST = os.environ.get("DIAGNOSIS_HOST", "0.0.0.0")
PORT = int(os.environ.get("DIAGNOSIS_PORT", "8009"))
DEBUG = os.environ.get("DIAGNOSIS_DEBUG", "false").lower() in ("1", "true", "yes")

# ── Database (shared PostgreSQL with backend) ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kronos:kronos@localhost:6432/kronos",
)
DATABASE_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://kronos:kronos@localhost:6432/kronos",
)

# ── JWT (same secret as backend for token verification) ──
JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY", "dev-secret-change-in-production-min-32-chars!!"
)
JWT_ALGORITHM = "HS256"

# ── Redis (for diagnosis caching) ──
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ── Kronos prediction service ──
KRONOS_PREDICTION_URL = os.environ.get(
    "KRONOS_PREDICTION_URL", "http://localhost:8001/api/v1/prediction"
)
KRONOS_PREDICTION_TIMEOUT = int(os.environ.get("KRONOS_PREDICTION_TIMEOUT", "8"))

# ── Caching TTL ──
DIAGNOSIS_CACHE_TTL = int(os.environ.get("DIAGNOSIS_CACHE_TTL", "172800"))  # 48 hours
KRONOS_CACHE_TTL = int(os.environ.get("KRONOS_CACHE_TTL", "21600"))  # 6 hours (trading day)
KRONOS_CACHE_TTL_WEEKEND = int(os.environ.get("KRONOS_CACHE_TTL_WEEKEND", "86400"))  # 24 hours
