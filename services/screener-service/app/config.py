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
    "leader_auction",     # 🔥秋神龙头竞价超预期战法 V4.3 (9:25选股)
    "leader_scalp",       # 秋神龙头战法-盘后
    "leader_intraday",    # 秋神龙头战法-盘中
    "leader_closing",     # 秋神龙头战法-尾盘顺势 V2.0 (14:40选股)
    "leader_afternoon",   # 秋神龙头战法-午后选股 V1.0 (14:30选股)
    "short",              # 匪爷短线多因子选股模型
    "long",               # 长线价值
    "all",                # 综合多因子
    "chokepoint",         # 大葱卡脖子选股模型
    "bi_trend_launch",    # 毕师傅趋势启动战法 V5.9 (硬核科技, OBV+WR)
    "bi_trend_full_market", # 毕师傅全市场趋势启动战法 V1.0 (全市场, VR过滤)
    "cb_floor",           # 匪爷可转债底价选债模型
    "cb_intraday",        # 匪爷可转债日内投机博弈模型
    "cb_auction",         # 秋神竞价概念选债模型
    "supply_chain",       # 大葱产业链解构选股 (中长线)
]
