"""C-1 Verification — dev-fallback KRONOS_SERVICE_SECRET must NOT grant X-Service-Auth.

code-reviewer C-1 (Critical) + 验收清单 §3-4: X-Service-Auth 字符串比较 + compose 未接
KRONOS_ENV → 部署侧 secret 恒为仓库可见的 dev-only-... → 任意请求拿 role:admin。

修复（config.SERVICE_AUTH_ENABLED + deps.py 守卫）：secret 仍是 dev-only- 前缀时
SERVICE_AUTH_ENABLED=False，X-Service-Auth 一律拒绝，不依赖部署 KRONOS_ENV。

验收清单 §3-4 单测：prod + dev-fallback secret → 带 X-Service-Auth 断言 401/拒绝。

Run: cd packages/kronos-auth && PYTHONPATH=. ../../backend/.venv/bin/python -m pytest tests/test_service_auth_dev_guard.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kronos_auth import deps
from kronos_auth.exceptions import UnauthorizedError


def _req_with_header(header_value: str | None) -> MagicMock:
    req = MagicMock()
    req.headers = {"X-Service-Auth": header_value} if header_value is not None else {}
    return req


@pytest.mark.asyncio
async def test_dev_fallback_secret_rejected_even_if_value_matches(monkeypatch):
    """C-1 核心 / 验收清单 §3-4：SERVICE_AUTH_ENABLED=False（dev fallback）→ 即使 header
    值完全等于该 fallback，也拒绝（不授予 admin）。"""
    monkeypatch.setattr(deps, "SERVICE_AUTH_ENABLED", False)
    monkeypatch.setattr(
        deps, "KRONOS_SERVICE_SECRET", "dev-only-service-secret-change-in-production"
    )
    with pytest.raises(UnauthorizedError, match="dev fallback"):
        await deps.get_current_user_jwt(
            _req_with_header("dev-only-service-secret-change-in-production")
        )


@pytest.mark.asyncio
async def test_real_secret_accepted_as_admin(monkeypatch):
    """SERVICE_AUTH_ENABLED=True（真实 secret）+ header 值匹配 → admin-equivalent 豁免。"""
    monkeypatch.setattr(deps, "SERVICE_AUTH_ENABLED", True)
    monkeypatch.setattr(deps, "KRONOS_SERVICE_SECRET", "real-prod-secret-xyz-not-dev-prefix")
    result = await deps.get_current_user_jwt(_req_with_header("real-prod-secret-xyz-not-dev-prefix"))
    assert result["role"] == "admin"
    assert result["sub"] == "service"


@pytest.mark.asyncio
async def test_wrong_secret_value_rejected(monkeypatch):
    """SERVICE_AUTH_ENABLED=True 但 header 值不匹配 → 拒绝。"""
    monkeypatch.setattr(deps, "SERVICE_AUTH_ENABLED", True)
    monkeypatch.setattr(deps, "KRONOS_SERVICE_SECRET", "real-prod-secret-xyz-not-dev-prefix")
    with pytest.raises(UnauthorizedError):
        await deps.get_current_user_jwt(_req_with_header("totally-wrong-value"))


@pytest.mark.asyncio
async def test_no_service_auth_header_falls_through_to_jwt(monkeypatch):
    """无 X-Service-Auth header → 不走豁免分支，落到 JWT Bearer 校验（缺 token → 401）。"""
    monkeypatch.setattr(deps, "SERVICE_AUTH_ENABLED", False)
    with pytest.raises(UnauthorizedError):
        await deps.get_current_user_jwt(_req_with_header(None))
