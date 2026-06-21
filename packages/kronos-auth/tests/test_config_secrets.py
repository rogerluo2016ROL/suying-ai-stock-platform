"""AC-1 unit tests: KRONOS_SERVICE_SECRET / KRONOS_JWT_SECRET 分级 raise.

ADR-007 Q-2 契约：
- `KRONOS_ENV=production` 且密钥缺失 → `raise RuntimeError`（进程退出非 0）
- 否则 `warnings.warn` + 带 `dev-only-` 前缀的明确 fallback（日志一眼识别）
- 三个密钥读法统一，禁硬编码默认值 / 禁 `secrets.token_hex` 进程内随机

用强制重载模块体（从 sys.modules 删后重新 import）改 env 后验证两条路径。
"""

import importlib
import sys
import warnings

import pytest


_SECRET_ENV_KEYS = ("KRONOS_SERVICE_SECRET", "JWT_SECRET_KEY", "KRONOS_ENV")


def _reload_config():
    """强制重新执行 kronos_auth.config 模块体（从 sys.modules 删后重新 import）。"""
    sys.modules.pop("kronos_auth.config", None)
    import kronos_auth.config as cfg  # noqa: F811 — 重新执行模块体
    return cfg


@pytest.fixture
def _reset_env(monkeypatch):
    for key in _SECRET_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    # teardown：清掉 prod 标志 + 密钥后重载，恢复成 dev 状态，避免污染后续用例。
    import os as _os
    for _k in _SECRET_ENV_KEYS:
        _os.environ.pop(_k, None)
    _reload_config()


# ══════════════════════════════════════════════════════════════════════════
# AC-1: KRONOS_SERVICE_SECRET 分级 raise
# ══════════════════════════════════════════════════════════════════════════

class TestServiceSecretProdRaise:
    """KRONOS_ENV=production + 缺 KRONOS_SERVICE_SECRET → RuntimeError."""

    def test_prod_missing_service_secret_raises(self, monkeypatch, _reset_env):
        monkeypatch.setenv("KRONOS_ENV", "production")
        # JWT_SECRET_KEY 设了值 → config 顶层先解析 JWT 不 raise，
        # 轮到 KRONOS_SERVICE_SECRET（第二个 _secret 调用）才 raise。
        monkeypatch.setenv("JWT_SECRET_KEY", "prod-jwt-so-service-secret-raises-first")
        with pytest.raises(RuntimeError, match="KRONOS_SERVICE_SECRET"):
            _reload_config()

    def test_prod_missing_jwt_secret_raises(self, monkeypatch, _reset_env):
        """KRONOS_JWT_SECRET 同款分级 raise（统一密钥读法；config 顶层 JWT 先解析）。"""
        monkeypatch.setenv("KRONOS_ENV", "production")
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            _reload_config()


class TestServiceSecretDevFallback:
    """非 prod + 缺密钥 → warn + dev-only- 前缀 fallback。"""

    def test_dev_missing_service_secret_warns_and_fallback(self, monkeypatch, _reset_env):
        monkeypatch.delenv("KRONOS_ENV", raising=False)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _reload_config()
        assert cfg.KRONOS_SERVICE_SECRET.startswith("dev-only-"), cfg.KRONOS_SERVICE_SECRET
        assert any("dev-only" in str(x.message).lower() or "not set" in str(x.message).lower()
                   for x in w)

    def test_dev_missing_jwt_secret_fallback(self, monkeypatch, _reset_env):
        monkeypatch.delenv("KRONOS_ENV", raising=False)
        cfg = _reload_config()
        assert cfg.KRONOS_JWT_SECRET.startswith("dev-only-"), cfg.KRONOS_JWT_SECRET

    def test_explicit_env_used_when_set(self, monkeypatch, _reset_env):
        """设了 env → 直接用 env 值，不走 fallback。"""
        monkeypatch.setenv("KRONOS_SERVICE_SECRET", "real-prod-secret-xyz")
        monkeypatch.setenv("JWT_SECRET_KEY", "real-jwt-secret-abc")
        cfg = _reload_config()
        assert cfg.KRONOS_SERVICE_SECRET == "real-prod-secret-xyz"
        assert cfg.KRONOS_JWT_SECRET == "real-jwt-secret-abc"

    def test_prod_with_secret_set_works(self, monkeypatch, _reset_env):
        """prod + 设了密钥 → 不 raise，用 env 值。"""
        monkeypatch.setenv("KRONOS_ENV", "production")
        monkeypatch.setenv("KRONOS_SERVICE_SECRET", "prod-service-secret")
        monkeypatch.setenv("JWT_SECRET_KEY", "prod-jwt-secret-min-32-chars-padding!!")
        cfg = _reload_config()
        assert cfg.KRONOS_SERVICE_SECRET == "prod-service-secret"
