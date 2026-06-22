"""Training-service configuration — all environment-driven.

JWT secret 读法与 backend/app/config.py + packages/kronos-auth 统一（ADR-007 Q-2
分级 raise 契约）：env 优先；prod 缺失 raise；dev 缺失 warn + `dev-only-` 前缀 fallback。
修复 audit P0-1：原先 fallback 到 `dev-secret-change...`，与 backend 的
`dev-only-jwt-secret-...` 不一致 → 跨服务验签 100% 失败（所有带认证请求 401）。
"""

import os
import warnings


def _is_production() -> bool:
    return os.environ.get("KRONOS_ENV", "").lower() == "production"


def _secret(env_key: str, dev_fallback: str) -> str:
    """统一密钥读法：env 优先；prod 缺失 raise；dev 缺失 warn + dev-only- fallback。"""
    value = os.environ.get(env_key)
    if value:
        return value
    if _is_production():
        raise RuntimeError(
            f"{env_key} must be set in production (KRONOS_ENV=production)"
        )
    warnings.warn(
        f"{env_key} not set — using dev-only fallback. "
        "Set a real secret before production (KRONOS_ENV=production will raise).",
        RuntimeWarning,
        stacklevel=2,
    )
    return dev_fallback


# ── Server ──
HOST = os.environ.get("TRAINING_HOST", "0.0.0.0")
PORT = int(os.environ.get("TRAINING_PORT", "8008"))
DEBUG = os.environ.get("TRAINING_DEBUG", "false").lower() in ("1", "true", "yes")

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
# P0-1: fallback 值与 backend/app/config.py 完全一致，确保 dev 环境跨服务验签成功。
JWT_SECRET_KEY = _secret(
    "JWT_SECRET_KEY",
    "dev-only-jwt-secret-change-in-production-min-32-chars!!",
)
JWT_ALGORITHM = "HS256"

# ── Redis (for training progress pub/sub) ──
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:7379/0")

# ── MLflow ──
MLFLOW_TRACKING_URI = os.environ.get(
    "MLFLOW_TRACKING_URI", "http://localhost:5010"
)
# Set to "mock" to use in-memory mock MLflow (no MLflow server needed)
MLFLOW_MODE = os.environ.get("MLFLOW_MODE", "mock")

# ── Training defaults ──
TRAINING_NUM_THREADS = int(os.environ.get("TRAINING_NUM_THREADS", "4"))
TRAINING_OUTPUT_DIR = os.environ.get(
    "TRAINING_OUTPUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Kronos", "outputs", "models"),
)
