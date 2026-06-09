"""Screener service configuration — all environment-driven."""

import os

# ── Server ──
HOST = os.environ.get("SCREENER_HOST", "0.0.0.0")
PORT = int(os.environ.get("SCREENER_PORT", "8001"))
DEBUG = os.environ.get("SCREENER_DEBUG", "false").lower() in ("1", "true", "yes")

# ── Data ──
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DB_PATH = os.environ.get("KRONOS_DB_PATH", os.path.join(_REPO_ROOT, "Kronos", "data", "kronos.db"))
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

# ── Default screening config ──
DEFAULT_TOP_N = int(os.environ.get("SCREENER_DEFAULT_TOP_N", "30"))
MAX_TOP_N = int(os.environ.get("SCREENER_MAX_TOP_N", "100"))

# ── Available screening modes ──
AVAILABLE_MODES = [
    "leader_scalp",      # 龙头战法 (收盘后)
    "leader_intraday",   # 龙头战法 (盘中)
    "short",             # 短线多因子
    "long",              # 长线价值
    "all",               # 综合多因子
    "chokepoint",        # 卡脖子专题
]
