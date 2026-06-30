"""Mode Orchestrator — V5.0 multi-strategy fusion + Kronos prediction + pipeline.

V5.0 新增:
  - WeightedFusionEngine: 动态权重融合（替代 merge_picks）
  - SectorHeatmapEngine: 板块热度过滤
  - LLMIntelligenceEngine: 情绪情报（可选）
  - RiskParityAllocator: 风险平价仓位分配（可选）

向后兼容:
  - run_screening(): 单模式选股（不变）
  - run_fusion_screening(): V4.0 共识融合（不变）
  - run_fusion_screening_v5(): 新增 V5.0 入口

环境变量控制:
  - ENABLE_WEIGHTED_FUSION=true: 启用动态权重融合
  - ENABLE_SECTOR_HEATMAP=true: 启用板块热度过滤
  - ENABLE_LLM_INTELLIGENCE=false: 启用情绪情报（默认关闭）
  - ENABLE_RISK_PARITY=false: 启用风险平价（默认关闭）
"""
import asyncio
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger("screener.orchestrator")

# 环境变量控制
ENABLE_WEIGHTED_FUSION = os.environ.get("ENABLE_WEIGHTED_FUSION", "true").lower() == "true"
ENABLE_SECTOR_HEATMAP = os.environ.get("ENABLE_SECTOR_HEATMAP", "true").lower() == "true"
ENABLE_LLM_INTELLIGENCE = os.environ.get("ENABLE_LLM_INTELLIGENCE", "false").lower() == "true"
ENABLE_RISK_PARITY = os.environ.get("ENABLE_RISK_PARITY", "false").lower() == "true"

# Strategy engine registry (lazy import)
_ENGINES = {}
_executor = ThreadPoolExecutor(max_workers=3)

# V5.0 新引擎（懒加载）
_weighted_fusion_engine = None
_sector_heatmap_engine = None
_llm_intelligence_engine = None
_risk_parity_allocator = None

def _get_engine(mode: str):
    if mode in _ENGINES:
        return _ENGINES[mode]
    try:
        from kronos_factors.engine.modes import (
            ChokepointEngine, ShortModeEngine
        )
        from kronos_factors.engine.leader_scalp import LeaderScalpEngine
        from kronos_factors.engine.leader_intraday import IntradayScalpEngine
        from kronos_factors.engine.leader_auction import AuctionScalpEngine
        from kronos_factors.engine.leader_afternoon import AfternoonTrendFullEngine
        from kronos_factors.engine.cb_floor import CbFloorEngine
        from kronos_factors.engine.cb_intraday import CbIntradayEngine
        from kronos_factors.engine.cb_auction import CbAuctionEngine
        from kronos_factors.engine.bi_trend_launch import BiTrendLaunchEngine
        from kronos_factors.engine.supply_chain import SupplyChainEngine

        _ENGINES.update({
            "leader_scalp": LeaderScalpEngine,
            "leader_auction": AuctionScalpEngine,
            "leader_afternoon_trend_full": AfternoonTrendFullEngine,
            "intraday": IntradayScalpEngine,
            "short": ShortModeEngine,
            "chokepoint": ChokepointEngine,
            "bi_trend_launch": BiTrendLaunchEngine,
            "supply_chain": SupplyChainEngine,
            "cb_floor": CbFloorEngine,
            "cb_intraday": CbIntradayEngine,
            "cb_auction": CbAuctionEngine,
        })
        return _ENGINES.get(mode)
    except ImportError as e:
        logger.error("Failed to load engines: %s", e)
        return None


async def run_screening(mode: str, top_n: int = 30, trade_date: str = None) -> dict:
    """Execute stock screening via the specified mode engine."""
    engine_cls = _get_engine(mode)
    if not engine_cls:
        return {"error": f"Unknown mode: {mode}", "available": list(_ENGINES.keys())}

    try:
        engine = engine_cls()
        loop = asyncio.get_running_loop()
        kwargs = {"top_n": top_n}
        if trade_date:
            kwargs["trade_date"] = trade_date
        result = await loop.run_in_executor(None, lambda: engine.run(**kwargs))
        return {"picks": result, "mode": mode, "top_n": top_n}
    except Exception as e:
        err = str(e)
        logger.exception("Screening failed for mode=%s", mode)
        if "division by zero" in err.lower():
            return {"error": "数据不足：缺少行情数据，请先同步日线数据后再试", "mode": mode}
        if "does not exist" in err.lower():
            return {"error": "数据库表缺失：部分数据表未迁移，请检查数据同步状态", "mode": mode}
        return {"error": f"选股失败: {err}", "mode": mode}


# ── V4.0 Multi-strategy fusion ──

async def run_fusion_screening(modes: list[str], top_n: int = 30,
                               trade_date: str = None) -> dict:
    """V4.0 多策略并行 → 共识融合 → Kronos 预测.

    Runs multiple strategies in parallel, merges results by consensus,
    and optionally enriches with Kronos 30-day predictions.

    Args:
        modes: list of strategy modes (default: leader_scalp + short)
        top_n: picks per strategy
        trade_date: trading date

    Returns: {consensus: [...], strategies: {...}, fusion_stats: {...}}
    """
    if not modes:
        modes = ["leader_scalp", "short"]

    t0 = time.time()
    strategy_results = {}

    # Run all strategies in parallel
    def _run_one(mode):
        engine_cls = _get_engine(mode)
        if not engine_cls:
            return mode, None
        try:
            engine = engine_cls()
            kwargs = {"top_n": top_n}
            if trade_date:
                kwargs["trade_date"] = trade_date
            result = engine.run(**kwargs)
            # Normalize result to list of dicts
            if hasattr(result, 'picks'):
                result = result.picks
            if hasattr(result, 'results'):
                result = result.results
            if isinstance(result, dict) and 'picks' in result:
                result = result['picks']
            if not isinstance(result, list):
                result = []
            return mode, result
        except Exception as e:
            logger.error("Strategy %s failed: %s", mode, e)
            return mode, []

    with ThreadPoolExecutor(max_workers=len(modes)) as pool:
        futures = {pool.submit(_run_one, m): m for m in modes}
        for f in futures:
            mode, result = f.result()
            if result is not None:
                strategy_results[mode] = result

    # V4.0 consensus fusion: stocks picked by ≥2 strategies get weighted boost
    consensus = merge_picks(strategy_results, top_n)

    elapsed = time.time() - t0
    return {
        "consensus": consensus,
        "strategies": {k: len(v) for k, v in strategy_results.items()},
        "fusion_stats": {
            "modes_used": len(strategy_results),
            "total_candidates": sum(len(v) for v in strategy_results.values()),
            "consensus_count": len(consensus),
            "elapsed_sec": round(elapsed, 1),
        },
    }


def merge_picks(strategy_results: dict, top_n: int = 30) -> list[dict]:
    """V4.0 consensus fusion — stocks picked by multiple strategies get higher weight.

    Scoring: base = individual score, +10 per additional strategy that picked it,
             +5 if picked by leader_scalp (highest precision).
    """
    stock_scores = defaultdict(lambda: {"score": 0, "count": 0, "strategies": [], "data": {}})

    for mode, picks in strategy_results.items():
        if not picks or not isinstance(picks, list):
            continue
        for p in picks:
            code = p.get("code", "")
            if not code:
                continue
            s = stock_scores[code]
            s["count"] += 1
            s["strategies"].append(mode)
            # Keep highest-scored entry
            p_score = p.get("total_score", p.get("score", 50))
            if p_score > s["score"]:
                s["score"] = p_score
                s["data"] = p
            # Consensus boost
            boost = 10 if mode == "leader_scalp" else 5
            s["score"] += boost

    # Sort by count (consensus) then score
    ranked = sorted(stock_scores.items(),
                    key=lambda x: (x[1]["count"], x[1]["score"]), reverse=True)
    result = []
    for code, info in ranked[:top_n]:
        entry = {**info["data"], "consensus_count": info["count"],
                 "consensus_strategies": info["strategies"]}
        result.append(entry)
    return result


def get_available_modes() -> list[str]:
    """Return list of registered screening modes."""
    return list(_ENGINES.keys()) if _ENGINES else [
        "leader_scalp", "intraday", "short", "chokepoint"
    ]


# ── V5.0 Lazy Loaders ──

def _get_weighted_fusion_engine():
    """懒加载 WeightedFusionEngine."""
    global _weighted_fusion_engine
    if _weighted_fusion_engine is None:
        try:
            from kronos_factors.engine.weighted_fusion import WeightedFusionEngine
            _weighted_fusion_engine = WeightedFusionEngine()
            logger.info("V5.0 WeightedFusionEngine loaded")
        except ImportError as e:
            logger.warning("WeightedFusionEngine not available: %s", e)
    return _weighted_fusion_engine


def _get_sector_heatmap_engine():
    """懒加载 SectorHeatmapEngine."""
    global _sector_heatmap_engine
    if _sector_heatmap_engine is None:
        try:
            from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine
            _sector_heatmap_engine = SectorHeatmapEngine()
            logger.info("V5.0 SectorHeatmapEngine loaded")
        except ImportError as e:
            logger.warning("SectorHeatmapEngine not available: %s", e)
    return _sector_heatmap_engine


def _get_llm_intelligence_engine():
    """懒加载 LLMIntelligenceEngine."""
    global _llm_intelligence_engine
    if _llm_intelligence_engine is None:
        try:
            from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine
            _llm_intelligence_engine = LLMIntelligenceEngine()
            if _llm_intelligence_engine.is_available():
                logger.info("V5.0 LLMIntelligenceEngine loaded")
            else:
                logger.warning("LLMIntelligenceEngine loaded but API key not configured")
        except ImportError as e:
            logger.warning("LLMIntelligenceEngine not available: %s", e)
    return _llm_intelligence_engine


def _get_risk_parity_allocator():
    """懒加载 RiskParityAllocator."""
    global _risk_parity_allocator
    if _risk_parity_allocator is None:
        try:
            from kronos_factors.engine.risk_parity import RiskParityAllocator
            _risk_parity_allocator = RiskParityAllocator()
            logger.info("V5.0 RiskParityAllocator loaded")
        except ImportError as e:
            logger.warning("RiskParityAllocator not available: %s", e)
    return _risk_parity_allocator


# ── V5.0 Multi-strategy Fusion ──

async def run_fusion_screening_v5(
    modes: list[str],
    top_n: int = 30,
    trade_date: str = None,
    market_env: str = "neutral",
    enable_llm: bool = False,
    enable_risk_parity: bool = False,
    total_capital: float = 0.0,
) -> dict:
    """V5.0 多策略并行 → 加权融合 → 板块热度 → 情绪情报 → 风险平价.

    相比 V4.0 run_fusion_screening():
      1. WeightedFusionEngine 替代 merge_picks（动态权重 + 因子去冗余）
      2. SectorHeatmapEngine 板块热度过滤（可选，默认启用）
      3. LLMIntelligenceEngine 情绪情报（可选，默认关闭）
      4. RiskParityAllocator 仓位分配（可选，默认关闭）

    Args:
        modes: 策略模式列表（默认: leader_scalp + leader_auction + bi_trend_launch + short）
        top_n: 返回候选数
        trade_date: 交易日期
        market_env: 市场环境 "bull" | "neutral" | "bear" | "crash"
        enable_llm: 是否启用情绪情报
        enable_risk_parity: 是否启用风险平价仓位分配
        total_capital: 总资金（风险平价需要）

    Returns: {consensus: [...], strategies: {...}, fusion_stats: {...}, ...}
    """
    if not modes:
        modes = ["leader_scalp", "leader_auction", "bi_trend_launch", "short"]

    t0 = time.time()
    strategy_results = {}
    hot_sectors = None

    # ── Step 1: 并行运行各策略引擎（与 V4.0 相同） ──
    def _run_one(mode):
        engine_cls = _get_engine(mode)
        if not engine_cls:
            return mode, None
        try:
            engine = engine_cls()
            kwargs = {"top_n": top_n}
            if trade_date:
                kwargs["trade_date"] = trade_date
            result = engine.run(**kwargs)
            # Normalize result to list of dicts
            if hasattr(result, 'picks'):
                result = result.picks
            if hasattr(result, 'results'):
                result = result.results
            if isinstance(result, dict) and 'picks' in result:
                result = result['picks']
            if not isinstance(result, list):
                result = []
            return mode, result
        except Exception as e:
            logger.error("Strategy %s failed: %s", mode, e)
            return mode, []

    with ThreadPoolExecutor(max_workers=len(modes)) as pool:
        futures = {pool.submit(_run_one, m): m for m in modes}
        for f in futures:
            mode, result = f.result()
            if result is not None:
                strategy_results[mode] = result

    # ── Step 2: 板块热度分析（可选） ──
    if ENABLE_SECTOR_HEATMAP:
        heatmap_engine = _get_sector_heatmap_engine()
        if heatmap_engine:
            try:
                if trade_date:
                    hot_sectors = heatmap_engine.get_hot_sectors(trade_date, min_hit_rate=0.6)
                else:
                    # 无 trade_date 时跳过板块热度
                    logger.info("No trade_date provided, skipping sector heatmap")
                logger.info("Hot sectors: %s", hot_sectors[:5] if hot_sectors else "none")
            except Exception as e:
                logger.warning("Sector heatmap failed: %s", e)

    # ── Step 3: V5.0 加权融合（替代 merge_picks） ──
    if ENABLE_WEIGHTED_FUSION:
        fusion_engine = _get_weighted_fusion_engine()
        if fusion_engine:
            try:
                fusion_result = fusion_engine.run(
                    strategy_results=strategy_results,
                    market_env=market_env,
                    hot_sectors=hot_sectors,
                    top_n=top_n,
                )
                consensus = fusion_result.picks
                weights_used = fusion_result.weights_used
                factor_redundancy = fusion_result.factor_redundancy
            except Exception as e:
                logger.error("WeightedFusionEngine failed: %s, falling back to merge_picks", e)
                consensus = merge_picks(strategy_results, top_n)
                weights_used = {}
                factor_redundancy = {}
        else:
            consensus = merge_picks(strategy_results, top_n)
            weights_used = {}
            factor_redundancy = {}
    else:
        # 降级到 V4.0
        consensus = merge_picks(strategy_results, top_n)
        weights_used = {}
        factor_redundancy = {}

    # ── Step 4: 情绪情报过滤（可选） ──
    sentiment_results = None
    if enable_llm or ENABLE_LLM_INTELLIGENCE:
        llm_engine = _get_llm_intelligence_engine()
        if llm_engine and llm_engine.is_available():
            try:
                codes = [p.get("code", "") for p in consensus[:top_n]]
                codes = [c for c in codes if c]
                if codes:
                    sentiment_results = llm_engine.batch_scan(codes, concurrency=5)
                    # 基于情绪过滤
                    for pick in consensus:
                        code = pick.get("code", "")
                        if code in sentiment_results:
                            pick["sentiment_score"] = {
                                "sentiment": sentiment_results[code].sentiment,
                                "confidence": sentiment_results[code].confidence,
                                "keywords": sentiment_results[code].keywords,
                                "summary": sentiment_results[code].summary,
                            }
                    # 排除负面情绪
                    consensus = llm_engine.filter_by_sentiment(consensus)
            except Exception as e:
                logger.warning("LLM intelligence failed: %s", e)

    # ── Step 5: 风险平价仓位分配（可选） ──
    allocation = None
    if enable_risk_parity or ENABLE_RISK_PARITY:
        rp_allocator = _get_risk_parity_allocator()
        if rp_allocator and total_capital > 0:
            try:
                alloc_result = rp_allocator.allocate(consensus[:top_n], total_capital)
                consensus = alloc_result.picks_with_weight
                allocation = {
                    "expected_volatility": alloc_result.expected_vol,
                    "max_single_weight": alloc_result.max_single_weight_actual,
                }
            except Exception as e:
                logger.warning("Risk parity allocation failed: %s", e)

    # ── 组装返回 ──
    elapsed = time.time() - t0

    result = {
        "consensus": consensus,
        "strategies": {k: len(v) for k, v in strategy_results.items()},
        "fusion_stats": {
            "version": "v5.0",
            "modes_used": len(strategy_results),
            "total_candidates": sum(len(v) for v in strategy_results.values()),
            "consensus_count": len(consensus),
            "elapsed_sec": round(elapsed, 1),
        },
    }

    # 附加 V5.0 元信息
    if weights_used:
        result["fusion_weights"] = {
            k: round(v, 3) for k, v in weights_used.items()
        }
    if factor_redundancy:
        result["factor_redundancy"] = factor_redundancy
    if hot_sectors:
        result["hot_sectors"] = hot_sectors
    if sentiment_results:
        result["sentiment_coverage"] = len(sentiment_results)
    if allocation:
        result["allocation"] = allocation
    if market_env:
        result["market_env"] = market_env

    return result


async def run_screening_v5(
    mode: str,
    top_n: int = 30,
    trade_date: str = None,
    market_env: str = "neutral",
) -> dict:
    """V5.0 单模式选股 + 板块热度 + 情绪情报.

    向后兼容 run_screening()，新增:
      - 板块热度过滤
      - 情绪情报（可选）

    Args:
        mode: 策略模式
        top_n: 返回候选数
        trade_date: 交易日期
        market_env: 市场环境

    Returns: {picks: [...], mode: ..., top_n: ..., ...}
    """
    # 复用原有单模式引擎
    base_result = await run_screening(mode, top_n, trade_date)

    if "error" in base_result:
        return base_result

    picks = base_result.get("picks", [])

    # 板块热度 enrich
    if ENABLE_SECTOR_HEATMAP and picks and trade_date:
        heatmap_engine = _get_sector_heatmap_engine()
        if heatmap_engine:
            try:
                hot_sectors = heatmap_engine.get_hot_sectors(trade_date, min_hit_rate=0.6)
                for pick in picks:
                    sector = pick.get("industry", "")
                    if sector:
                        pick["sector_hot"] = sector in hot_sectors
                base_result["hot_sectors"] = hot_sectors[:5]
            except Exception as e:
                logger.warning("Sector heatmap enrich failed: %s", e)

    # 情绪情报 enrich（可选）
    if ENABLE_LLM_INTELLIGENCE and picks:
        llm_engine = _get_llm_intelligence_engine()
        if llm_engine and llm_engine.is_available():
            try:
                codes = [p.get("code", "") for p in picks[:top_n]]
                codes = [c for c in codes if c]
                if codes:
                    sentiment_results = llm_engine.batch_scan(codes, concurrency=5)
                    for pick in picks[:top_n]:
                        code = pick.get("code", "")
                        if code in sentiment_results:
                            pick["sentiment_score"] = {
                                "sentiment": sentiment_results[code].sentiment,
                                "confidence": sentiment_results[code].confidence,
                                "keywords": sentiment_results[code].keywords,
                            }
                    base_result["sentiment_coverage"] = len(sentiment_results)
            except Exception as e:
                logger.warning("LLM intelligence enrich failed: %s", e)

    return base_result
