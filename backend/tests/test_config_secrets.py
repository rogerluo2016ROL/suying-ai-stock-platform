"""AC-3 unit tests: backend JWT_SECRET_KEY / ADMIN_PASSWORD 分级 raise.

ADR-007 Q-2 契约：
- `KRONOS_ENV=production` 且密钥缺失 → `raise RuntimeError`
- 否则 `warnings.warn` + `dev-only-` 前缀 fallback
- **移除 `secrets.token_hex` 进程内随机路径**（多实例/重启 token 互不兼容）
- ADMIN_PASSWORD 移除 `Admin123!` 硬编码默认
"""

import importlib
import sys
import warnings

import pytest


_SECRET_ENV_KEYS = (
    "JWT_SECRET_KEY", "ADMIN_PASSWORD", "ADMIN_EMAIL",
    "KRONOS_ENV", "DATABASE_URL", "DATABASE_SYNC_URL",
)


def _reload_config():
    """强制重新执行 app.config 模块体（从 sys.modules 删后重新 import）。

    普通 `import app.config` 只在首次执行模块体；改 env 后必须强制重载才能
    触发 config 顶层的分级 raise 逻辑。
    """
    sys.modules.pop("app.config", None)
    import app.config as cfg  # noqa: F811 — 重新执行模块体
    return cfg


@pytest.fixture
def _reset_config_env(monkeypatch):
    for key in _SECRET_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield
    # teardown：清掉 prod 标志 + 密钥后重载，恢复成 dev 状态，避免污染后续用例。
    import os as _os
    for _k in _SECRET_ENV_KEYS:
        _os.environ.pop(_k, None)
    _reload_config()


def _config_path():
    """config.py 绝对路径，给 grep-token_hex / Admin123! 断言用。"""
    import app.config as cfg
    return cfg.__file__


# ══════════════════════════════════════════════════════════════════════════
# AC-3: JWT_SECRET_KEY 分级 raise，无 token_hex 随机
# ══════════════════════════════════════════════════════════════════════════

class TestJwtSecretProdRaise:

    def test_prod_missing_jwt_raises(self, monkeypatch, _reset_config_env):
        monkeypatch.setenv("KRONOS_ENV", "production")
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            _reload_config()

    def test_no_token_hex_random_path(self):
        """AST 无对 `secrets.token_hex` 的 Call（移除进程内随机路径）。

        用 AST 而非子串匹配——docstring/注释里提及字样不算违规，只有真实调用算。
        AC-3 语义：「不再调用 secrets.token_hex 生成 key」。
        """
        import ast
        tree = ast.parse(open(_config_path()).read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # secrets.token_hex(...)
            if (isinstance(func, ast.Attribute)
                    and func.attr == "token_hex"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "secrets"):
                pytest.fail("config.py 仍调用 secrets.token_hex 进程内随机")
            # 直接 token_hex(...)（若 from secrets import token_hex）
            if isinstance(func, ast.Name) and func.id == "token_hex":
                pytest.fail("config.py 仍调用 token_hex() 进程内随机")


class TestJwtSecretDevFallback:

    def test_dev_missing_jwt_warns_and_fallback(self, monkeypatch, _reset_config_env):
        monkeypatch.delenv("KRONOS_ENV", raising=False)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            cfg = _reload_config()
        assert cfg.JWT_SECRET_KEY.startswith("dev-only-"), cfg.JWT_SECRET_KEY
        assert any("dev-only" in str(x.message).lower() or "not set" in str(x.message).lower()
                   for x in w)

    def test_jwt_secret_stable_across_reload_in_dev(self, monkeypatch, _reset_config_env):
        """dev fallback 必须是确定值（非随机），两次 reload 同一值。

        这正是 ADR-007 禁 token_hex 的理由：随机值让多实例/重启 token 互不兼容。
        """
        monkeypatch.delenv("KRONOS_ENV", raising=False)
        first = _reload_config().JWT_SECRET_KEY
        second = _reload_config().JWT_SECRET_KEY
        assert first == second, "dev fallback 应是确定值，不应每次 reload 变"

    def test_jwt_from_env(self, monkeypatch, _reset_config_env):
        monkeypatch.setenv("JWT_SECRET_KEY", "explicit-jwt-from-env-32-chars!")
        cfg = _reload_config()
        assert cfg.JWT_SECRET_KEY == "explicit-jwt-from-env-32-chars!"


# ══════════════════════════════════════════════════════════════════════════
# AC-3 / AC-12: ADMIN_PASSWORD 分级 raise，无 Admin123! 默认
# ══════════════════════════════════════════════════════════════════════════

class TestAdminPasswordProdRaise:

    def test_prod_missing_admin_pw_raises(self, monkeypatch, _reset_config_env):
        monkeypatch.setenv("KRONOS_ENV", "production")
        # 设了 JWT 避免 JWT raise 抢先（config 顶层按顺序 JWT 先于 ADMIN_PASSWORD 赋值）
        monkeypatch.setenv("JWT_SECRET_KEY", "prod-jwt-32-chars-padding!!")
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            _reload_config()

    def test_no_admin123_default(self):
        """`ADMIN_PASSWORD` 的默认值不是含 `Admin123` 的字符串字面量（移除硬编码弱口令）。

        用 AST 找 `os.environ.get("ADMIN_PASSWORD", <default>)` / `_secret("ADMIN_PASSWORD", <default>)`
        的 default 参数，断言它不是含 "Admin123" 的 str 字面量。docstring/注释提及不算违规。
        """
        import ast
        tree = ast.parse(open(_config_path()).read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_get = (isinstance(func, ast.Attribute)
                      and func.attr == "get"
                      and isinstance(func.value, ast.Attribute)
                      and func.value.attr == "environ")
            is_secret = (isinstance(func, ast.Name) and func.id == "_secret")
            if not (is_get or is_secret):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != "ADMIN_PASSWORD":
                continue
            if len(node.args) >= 2:
                default = node.args[1]
                if (isinstance(default, ast.Constant)
                        and isinstance(default.value, str)
                        and "Admin123" in default.value):
                    pytest.fail(
                        f"ADMIN_PASSWORD 仍以 {default.value!r} 为硬编码默认"
                    )


class TestAdminPasswordDevFallback:

    def test_dev_missing_admin_pw_fallback(self, monkeypatch, _reset_config_env):
        monkeypatch.delenv("KRONOS_ENV", raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "dev-jwt-placeholder-32-chars-ok!!")
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            cfg = _reload_config()
        assert cfg.ADMIN_PASSWORD.startswith("dev-only-"), cfg.ADMIN_PASSWORD
