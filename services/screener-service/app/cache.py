"""Redis cache layer — per refactoring plan §7.2 L1-L5"""
import os, json, logging
from typing import Any, Optional

logger = logging.getLogger("screener.cache")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:7379/0")

_redis = None
try:
    import redis.asyncio as aioredis
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    logger.info("Redis connected: %s", REDIS_URL)
except ImportError:
    logger.warning("redis not installed — cache disabled")
except Exception as e:
    logger.warning("Redis unavailable: %s — cache disabled", e)

async def cache_get(key: str) -> Optional[Any]:
    if not _redis: return None
    try:
        val = await _redis.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None

async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    if not _redis: return
    try:
        await _redis.setex(key, ttl, json.dumps(value))
    except Exception:
        pass

async def cache_invalidate(pattern: str) -> None:
    if not _redis: return
    try:
        keys = await _redis.keys(pattern)
        if keys: await _redis.delete(*keys)
    except Exception:
        pass

# L1: 实时行情缓存 TTL 5s
# L2: 因子值缓存 TTL 当日
# L3: Kronos预测缓存 TTL 当日
# L4: 选股结果缓存 TTL 1h
# L5: 信号状态缓存 TTL 实时
