"""Data Service 配置 — 全部可环境变量覆盖."""

import os

# ── 调度时间 ──
SCHEDULES = {
    "rt_min": os.environ.get("DATA_SCHEDULE_RT_MIN", "*/1 9-15 * * 1-5"),
    "rt_min_auction": os.environ.get("DATA_SCHEDULE_AUCTION", "25 9 * * 1-5"),
    "post_market_core": os.environ.get("DATA_SCHEDULE_CORE", "30 15 * * 1-5"),
    "post_market_ext": os.environ.get("DATA_SCHEDULE_EXT", "35 15 * * 1-5"),
    "post_market_deep": os.environ.get("DATA_SCHEDULE_DEEP", "40 15 * * 1-5"),
    "weekly_finance": os.environ.get("DATA_SCHEDULE_WEEKLY", "0 2 * * 6"),
}

# ── 数据库路径 ──
DB_PATH = os.environ.get("KRONOS_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), "Kronos", "webui", "stock_screening.db"))
SQLITE_FALLBACK_ENABLED = os.environ.get("DATA_SQLITE_FALLBACK", "false").lower() in {"1", "true", "yes", "on"}

# ── Redis ──
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:7379/0")

# ── Tushare ──
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "").strip()


def is_tushare_configured() -> bool:
    """Return whether market-data jobs can call Tushare."""
    return bool(TUSHARE_TOKEN)


def get_runtime_config_status() -> dict:
    """Expose non-secret runtime config for readiness/status endpoints."""
    return {
        "tushare": {
            "configured": is_tushare_configured(),
            "env": "TUSHARE_TOKEN",
            "action": "set TUSHARE_TOKEN before enabling market-data jobs",
        },
        "sqlite_fallback": {
            "enabled": SQLITE_FALLBACK_ENABLED,
            "env": "DATA_SQLITE_FALLBACK",
        },
    }

# ── 并行度 ──
THREAD_POOL_SIZE = int(os.environ.get("DATA_THREAD_POOL", "8"))
TUSHARE_BATCH_SIZE = int(os.environ.get("DATA_TUSHARE_BATCH", "100"))
