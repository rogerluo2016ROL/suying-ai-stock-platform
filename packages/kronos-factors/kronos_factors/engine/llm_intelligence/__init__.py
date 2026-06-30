"""LLMIntelligenceEngine — 实时情绪情报引擎.

基于 LLM（DeepSeek API）对候选股进行新闻/公告情绪分析，输出 sentiment_score (0-100)。
作为可选层，仅在 fusion 后对 top_n 候选调用，避免全市场扫描。

核心能力:
  - scan_news_sentiment(): 单只股票情绪分析
  - batch_scan(): 批量扫描（并发控制 + Redis 缓存）
  - filter_by_sentiment(): 基于情绪过滤候选池

依赖:
  - openai SDK (pip install openai)
  - redis (可选，用于缓存)

Usage:
    from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine

    engine = LLMIntelligenceEngine(api_key="sk-xxx")
    result = engine.scan_news_sentiment("000001", query_days=3)
"""
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("kronos.llm_intelligence")

# LLM 模型配置
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_CONCURRENCY = 5

# Redis 缓存 TTL（秒）
DEFAULT_CACHE_TTL = 3600  # 1 hour

# 情绪判断阈值
MIN_CONFIDENCE_FOR_FILTER = 0.6
EXCLUDE_NEGATIVE_CONFIDENCE = 0.7


@dataclass
class SentimentResult:
    """情绪分析结果."""
    sentiment: str              # "positive" | "negative" | "neutral"
    confidence: float           # 0-1
    keywords: list[str] = field(default_factory=list)
    summary: str = ""           # ≤50字
    event_count: int = 0        # 正面事件 + 负面事件总数
    scanned_at: str = ""        # ISO 时间戳


@dataclass
class SentimentCacheEntry:
    """情绪缓存条目."""
    stock_code: str
    result: SentimentResult
    cached_at: float            # Unix timestamp
    ttl_seconds: int = DEFAULT_CACHE_TTL

    def is_expired(self) -> bool:
        return (time.time() - self.cached_at) > self.ttl_seconds


# LLM Prompt 模板
SENTIMENT_PROMPT_TEMPLATE = """你是一名专业的证券分析师。请对以下股票【{stock_code}】近 {query_days} 日的公开信息（新闻、公告、研报）进行情绪分析。

请严格按照以下 JSON 格式返回，不要包含任何其他内容：
{{
  "sentiment": "positive" | "negative" | "neutral",
  "confidence": <0-1 之间的浮点数>,
  "keywords": ["事件关键词1", "事件关键词2", "事件关键词3"],
  "summary": "<50字以内的事件摘要>",
  "event_count": <正面事件数 + 负面事件数>
}}

判断标准：
- positive: 利好消息为主（业绩超预期/机构调研/技术突破/政策支持/并购重组）
- negative: 利空消息为主（财务暴雷/监管处罚/商誉减值/机构减持/诉讼纠纷）
- neutral: 无显著事件或正负抵消

confidence 标准：
- 0.8+: 信息充足且情绪明确
- 0.6-0.8: 信息较少或情绪模糊
- <0.6: 信息不足无法判断"""


class LLMIntelligenceEngine:
    """LLM 情绪情报引擎."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: int = DEFAULT_TIMEOUT,
        enable_cache: bool = True,
        redis_url: str | None = None,
    ):
        """初始化情绪引擎.

        Args:
            api_key: DeepSeek API key（或环境变量 DEEPSEEK_API_KEY）
            base_url: API base URL
            model: 模型名称
            timeout: 请求超时（秒）
            enable_cache: 是否启用 Redis 缓存
            redis_url: Redis 连接字符串（或环境变量 REDIS_URL）
        """
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or DEFAULT_BASE_URL
        self.model = model
        self.timeout = timeout
        self.enable_cache = enable_cache

        # OpenAI client
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=timeout,
                )
            except ImportError:
                logger.warning("openai SDK not installed, LLM intelligence disabled")
            except Exception as e:
                logger.error("Failed to initialize OpenAI client: %s", e)

        # Redis client (optional)
        self._redis = None
        if enable_cache:
            redis_url = redis_url or os.environ.get("REDIS_URL", "")
            if redis_url:
                try:
                    import redis
                    self._redis = redis.from_url(redis_url)
                    self._redis.ping()
                except Exception as e:
                    logger.warning("Redis not available, cache disabled: %s", e)

    def is_available(self) -> bool:
        """检查引擎是否可用."""
        return self._client is not None

    def scan_news_sentiment(
        self,
        stock_code: str,
        query_days: int = 3,
    ) -> SentimentResult:
        """扫描单只股票近 N 日新闻，返回情绪.

        Args:
            stock_code: 股票代码
            query_days: 查询天数

        Returns:
            SentimentResult: 情绪分析结果
        """
        # 1. 检查缓存
        if self.enable_cache and self._redis:
            cached = self._get_cache(stock_code)
            if cached:
                logger.debug("Cache hit for %s", stock_code)
                return cached

        # 2. 调用 LLM API
        result = self._call_llm(stock_code, query_days)

        # 3. 写入缓存
        if self.enable_cache and self._redis:
            self._set_cache(stock_code, result)

        return result

    def batch_scan(
        self,
        stock_codes: list[str],
        query_days: int = 3,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> dict[str, SentimentResult]:
        """批量扫描（并发限制，避免限流）.

        Args:
            stock_codes: 股票代码列表
            query_days: 查询天数
            concurrency: 并发数

        Returns:
            {stock_code: SentimentResult}
        """
        results = {}

        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)

        async def scan_one(code: str):
            async with semaphore:
                return code, self.scan_news_sentiment(code, query_days)

        async def scan_all():
            tasks = [scan_one(code) for code in stock_codes]
            return await asyncio.gather(*tasks, return_exceptions=True)

        # 运行异步任务
        loop = asyncio.new_event_loop()
        try:
            task_results = loop.run_until_complete(scan_all())
        finally:
            loop.close()

        # 处理结果
        for item in task_results:
            if isinstance(item, Exception):
                logger.error("Batch scan error: %s", item)
                continue
            if isinstance(item, tuple) and len(item) == 2:
                code, result = item
                results[code] = result

        return results

    def filter_by_sentiment(
        self,
        picks: list[dict],
        min_confidence: float = MIN_CONFIDENCE_FOR_FILTER,
        exclude_negative: bool = True,
    ) -> list[dict]:
        """基于情绪过滤候选池.

        规则:
          - sentiment="negative" 且 confidence > exclude_negative_confidence → 排除
          - sentiment="positive" 且 confidence > min_confidence → 加分 +5

        Args:
            picks: 候选股列表（每只含 sentiment_score 字段）
            min_confidence: 正面情绪最低置信度阈值
            exclude_negative: 是否排除负面情绪

        Returns:
            过滤后的候选股列表
        """
        filtered = []

        for pick in picks:
            sentiment = pick.get("sentiment_score", {})
            if not sentiment or not isinstance(sentiment, SentimentResult):
                filtered.append(pick)  # 无情绪数据，保留
                continue

            sent_value = sentiment.sentiment
            conf = sentiment.confidence

            # 排除负面情绪
            if exclude_negative and sent_value == "negative" and conf > EXCLUDE_NEGATIVE_CONFIDENCE:
                logger.info("Excluding %s due to negative sentiment (conf=%.2f)", pick.get("code"), conf)
                continue

            # 正面情绪加分
            if sent_value == "positive" and conf > min_confidence:
                score = pick.get("score", 0)
                pick["score"] = score + 5
                pick["sentiment_boost"] = 5

            filtered.append(pick)

        return filtered

    def _call_llm(self, stock_code: str, query_days: int) -> SentimentResult:
        """调用 LLM API 进行情绪分析."""
        if not self._client:
            logger.warning("LLM client not available, returning neutral")
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                keywords=[],
                summary="LLM 不可用",
                event_count=0,
                scanned_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        prompt = SENTIMENT_PROMPT_TEMPLATE.format(
            stock_code=stock_code,
            query_days=query_days,
        )

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result_dict = json.loads(content)

            return SentimentResult(
                sentiment=result_dict.get("sentiment", "neutral"),
                confidence=float(result_dict.get("confidence", 0)),
                keywords=result_dict.get("keywords", []),
                summary=result_dict.get("summary", ""),
                event_count=int(result_dict.get("event_count", 0)),
                scanned_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        except json.JSONDecodeError as e:
            logger.error("LLM response not JSON: %s", e)
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                keywords=[],
                summary="LLM 响应格式错误",
                event_count=0,
                scanned_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
        except Exception as e:
            logger.error("LLM API call failed: %s", e)
            return SentimentResult(
                sentiment="neutral",
                confidence=0.0,
                keywords=[],
                summary=f"LLM 调用失败: {str(e)[:50]}",
                event_count=0,
                scanned_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

    def _get_cache(self, stock_code: str) -> Optional[SentimentResult]:
        """从 Redis 获取缓存."""
        if not self._redis:
            return None

        try:
            key = f"sentiment:{stock_code}"
            cached_json = self._redis.get(key)
            if not cached_json:
                return None

            cached_dict = json.loads(cached_json)
            entry = SentimentCacheEntry(
                stock_code=stock_code,
                result=SentimentResult(**cached_dict["result"]),
                cached_at=cached_dict["cached_at"],
                ttl_seconds=cached_dict.get("ttl_seconds", DEFAULT_CACHE_TTL),
            )

            if entry.is_expired():
                return None

            return entry.result

        except Exception as e:
            logger.warning("Cache read failed for %s: %s", stock_code, e)
            return None

    def _set_cache(self, stock_code: str, result: SentimentResult) -> None:
        """写入 Redis 缓存."""
        if not self._redis:
            return

        try:
            key = f"sentiment:{stock_code}"
            entry = SentimentCacheEntry(
                stock_code=stock_code,
                result=result,
                cached_at=time.time(),
                ttl_seconds=DEFAULT_CACHE_TTL,
            )

            entry_dict = {
                "stock_code": stock_code,
                "result": {
                    "sentiment": result.sentiment,
                    "confidence": result.confidence,
                    "keywords": result.keywords,
                    "summary": result.summary,
                    "event_count": result.event_count,
                    "scanned_at": result.scanned_at,
                },
                "cached_at": entry.cached_at,
                "ttl_seconds": entry.ttl_seconds,
            }

            self._redis.setex(key, DEFAULT_CACHE_TTL, json.dumps(entry_dict, ensure_ascii=False))

        except Exception as e:
            logger.warning("Cache write failed for %s: %s", stock_code, e)


# 便捷函数
def scan_sentiment(
    stock_code: str,
    query_days: int = 3,
    api_key: str | None = None,
) -> SentimentResult:
    """便捷函数：扫描单只股票情绪."""
    engine = LLMIntelligenceEngine(api_key=api_key)
    return engine.scan_news_sentiment(stock_code, query_days)


def batch_scan_sentiment(
    stock_codes: list[str],
    query_days: int = 3,
    api_key: str | None = None,
) -> dict[str, SentimentResult]:
    """便捷函数：批量扫描情绪."""
    engine = LLMIntelligenceEngine(api_key=api_key)
    return engine.batch_scan(stock_codes, query_days)
