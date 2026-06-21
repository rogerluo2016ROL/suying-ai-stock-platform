"""Application configuration — all environment-driven.

ADR-007 Q-2 分级 raise 契约（与 packages/kronos-auth/kronos_auth/config.py 统一读法）：
- `KRONOS_ENV=production` 且密钥缺失 → `raise RuntimeError`（进程退出非 0）
- 否则 `warnings.warn` + 带 `dev-only-` 前缀的明确 fallback（日志一眼识别）
- **禁 `secrets.token_hex` 进程内随机**（多实例/重启 token 互不兼容，比硬编码默认更隐蔽）
- ADMIN_PASSWORD 不再硬编码 `Admin123!`
"""

import os
import warnings


def _is_production() -> bool:
    return os.environ.get("KRONOS_ENV", "").lower() == "production"


def _secret(env_key: str, dev_fallback: str) -> str:
    """统一密钥读法：env 优先；prod 缺失 raise；dev 缺失 warn + dev-only- fallback。

    Args:
        env_key: 环境变量名。
        dev_fallback: dev 缺失时的明确占位值（须以 `dev-only-` 前缀，日志一眼可识别）。
    """
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


# ── Database ──
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kronos:kronos@localhost:6432/kronos",
)
DATABASE_SYNC_URL = os.environ.get(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://kronos:kronos@localhost:6432/kronos",
)

# ── JWT ──（AC-3：分级 raise，移除 secrets.token_hex 进程内随机路径）
JWT_SECRET_KEY = _secret(
    "JWT_SECRET_KEY",
    "dev-only-jwt-secret-change-in-production-min-32-chars!!",
)
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRE_SECONDS = int(os.environ.get("JWT_ACCESS_EXPIRE_SECONDS", "900"))  # 15 min
JWT_REFRESH_EXPIRE_SECONDS = int(os.environ.get("JWT_REFRESH_EXPIRE_SECONDS", "604800"))  # 7 days

# ── Argon2 ──
ARGON2_TIME_COST = int(os.environ.get("ARGON2_TIME_COST", "3"))
ARGON2_MEMORY_COST = int(os.environ.get("ARGON2_MEMORY_COST", "65536"))  # 64 MiB
ARGON2_PARALLELISM = int(os.environ.get("ARGON2_PARALLELISM", "2"))

# ── Admin seed ──（AC-3 / AC-12：ADMIN_PASSWORD 分级 raise，移除 Admin123! 默认）
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@suying.ai")
ADMIN_PASSWORD = _secret(
    "ADMIN_PASSWORD",
    "dev-only-admin-pw-change-me",
)
ADMIN_NAME = os.environ.get("ADMIN_NAME", "admin")

# ── Server ──
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
DEBUG = os.environ.get("DEBUG", "false").lower() in ("1", "true", "yes")
