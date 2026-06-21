"""Kronos Auth configuration — environment-driven.

ADR-007 Q-2 分级 raise 契约：
- `KRONOS_ENV=production` 且密钥缺失 → `raise RuntimeError`（进程退出非 0）
- 否则 `warnings.warn` + 带 `dev-only-` 前缀的明确 fallback（日志一眼识别）
- 三个密钥读法统一，禁硬编码默认值 / 禁 `secrets.token_hex` 进程内随机
"""

import os
import warnings


def _is_production() -> bool:
    return os.environ.get("KRONOS_ENV", "").lower() == "production"


def _secret(env_key: str, dev_fallback: str) -> str:
    """统一密钥读法：env 优先；prod 缺失 raise；dev 缺失 warn + dev-only- fallback。

    Args:
        env_key: 环境变量名（如 KRONOS_SERVICE_SECRET）。
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


KRONOS_JWT_SECRET = _secret(
    "JWT_SECRET_KEY",
    "dev-only-jwt-secret-change-in-production-min-32-chars!!",
)

KRONOS_SERVICE_SECRET = _secret(
    "KRONOS_SERVICE_SECRET",
    "dev-only-service-secret-change-in-production",
)

# C-1 (code-reviewer 验收清单 §3-2/3): X-Service-Auth 服务间豁免仅在 secret 已换成
# 真实值（非 dev-only- 前缀）时启用。仓库内可见的 dev fallback 绝不能授予
# admin-equivalent 豁免（防越权后门）。deps.py 用此布尔做守卫，不依赖部署 KRONOS_ENV。
SERVICE_AUTH_ENABLED = not KRONOS_SERVICE_SECRET.startswith("dev-only-")

JWT_ALGORITHM = "HS256"
