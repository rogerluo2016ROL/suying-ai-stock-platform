"""Tushare API 统一限频控制 — 滑动窗口 400 次/分钟.

所有 Tushare `pro.xxx()` 调用前执行 `rate_limit()` 以避免触发 500/min 限制。
股票列表同步 (stock_basic) 不计入限频配额，可跳过。
"""

import logging, threading, time

logger = logging.getLogger("data-service.rate_limiter")

_RATE_LIMIT = 400  # 安全上限，低于 Tushare 500/min 限制
_call_times: list[float] = []
_lock = threading.Lock()


def rate_limit():
    """滑动窗口限频：当前 60 秒内已超过 400 次调用则等待.

    线程安全 (threading.Lock)，可在 ThreadPoolExecutor 中并发使用。
    """
    global _call_times, _lock
    with _lock:
        now = time.time()
        # 清理 60 秒前的调用记录
        _call_times = [t for t in _call_times if now - t < 60]
        if len(_call_times) >= _RATE_LIMIT:
            sleep_for = 60 - (now - _call_times[0]) + 0.1
            if sleep_for > 0:
                logger.debug("Rate limit: sleeping %.1fs (%d calls in window)", sleep_for, len(_call_times))
                time.sleep(sleep_for)
                _call_times = []
        _call_times.append(time.time())


def get_rate_limit_status() -> dict:
    """获取当前限频状态 (debug 用)."""
    with _lock:
        now = time.time()
        recent = [t for t in _call_times if now - t < 60]
        return {
            "calls_in_window": len(recent),
            "limit": _RATE_LIMIT,
            "window_seconds": 60,
            "remaining": _RATE_LIMIT - len(recent),
        }
