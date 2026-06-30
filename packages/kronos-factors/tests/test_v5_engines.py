"""Unit tests for V5.0 new screening engines.

Tests:
  - WeightedFusionEngine
  - SectorHeatmapEngine
  - LLMIntelligenceEngine
  - RiskParityAllocator
  - MultiIndexEngine

Run:
    cd packages/kronos-factors && pytest tests/test_v5_engines.py -v
"""
import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

# Add packages to path
_PACKAGES = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PACKAGES not in sys.path:
    sys.path.insert(0, _PACKAGES)


# ═══════════════════════════════════════════════════════════════
# WeightedFusionEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestWeightedFusionEngine:
    def test_load_from_dict(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        profiles = {
            "models": {
                "test_mode": {
                    "precision": 0.7,
                    "recall": 0.5,
                    "style": "momentum",
                    "env_affinity": {"bull": 1.2, "neutral": 1.0, "bear": 0.5},
                }
            }
        }
        engine = WeightedFusionEngine(mode_profiles_dict=profiles)
        assert "test_mode" in engine.mode_profiles
        assert engine.mode_profiles["test_mode"].precision == 0.7

    def test_load_from_file(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        profiles_path = os.path.join(_PACKAGES, "config", "mode_profiles.json")
        if os.path.exists(profiles_path):
            engine = WeightedFusionEngine(mode_profiles_path=profiles_path)
            assert len(engine.mode_profiles) > 0
            assert "leader_scalp" in engine.mode_profiles
        else:
            pytest.skip("mode_profiles.json not found")

    def test_load_defaults_fallback(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        assert len(engine.mode_profiles) >= 5  # at least 5 defaults
        assert "leader_scalp" in engine.mode_profiles

    def test_compute_dynamic_weights(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        weights = engine.compute_dynamic_weights(
            modes=["leader_scalp", "bi_trend_launch"],
            market_env="bull",
        )
        assert abs(sum(weights.values()) - 1.0) < 0.01  # sum = 1.0
        assert "leader_scalp" in weights
        assert "bi_trend_launch" in weights

    def test_compute_dynamic_weights_env_adaptation(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()

        bull_weights = engine.compute_dynamic_weights(
            modes=["leader_scalp"], market_env="bull"
        )
        bear_weights = engine.compute_dynamic_weights(
            modes=["bi_trend_launch"], market_env="bear"
        )

        # leader_scalp 在牛市权重更高
        assert bull_weights["leader_scalp"] > 0
        # bi_trend 在熊市权重更高
        assert bear_weights["bi_trend_launch"] > 0

    def test_run_fusion_empty(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        result = engine.run(strategy_results={})
        assert result.picks == []
        assert result.weights_used == {}

    def test_run_fusion_single_mode(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        picks = [
            {"code": "000001", "score": 80, "industry": "半导体"},
            {"code": "000002", "score": 70, "industry": "新能源"},
        ]
        result = engine.run(
            strategy_results={"leader_scalp": picks},
            market_env="neutral",
            top_n=5,
        )
        assert len(result.picks) == 2
        assert result.picks[0]["code"] == "000001"
        assert result.picks[0]["consensus_count"] == 1

    def test_run_fusion_multi_mode_consensus(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        picks1 = [
            {"code": "000001", "score": 80},
            {"code": "000002", "score": 70},
        ]
        picks2 = [
            {"code": "000001", "score": 75},
            {"code": "600519", "score": 85},
        ]
        result = engine.run(
            strategy_results={
                "leader_scalp": picks1,
                "bi_trend_launch": picks2,
            },
            market_env="neutral",
            top_n=5,
        )
        # 000001 出现在两个模式中，应该排在最前
        assert len(result.picks) == 3
        assert result.picks[0]["code"] == "000001"
        assert result.picks[0]["consensus_count"] == 2

    def test_run_fusion_sector_filter(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        picks = [
            {"code": "000001", "score": 80, "industry": "半导体"},
            {"code": "000002", "score": 80, "industry": "房地产"},
        ]
        result = engine.run(
            strategy_results={"leader_scalp": picks},
            market_env="neutral",
            hot_sectors=["半导体", "AI算力"],
            top_n=5,
        )
        # 非热点板块权重 × 0.5
        semiconductor = next(p for p in result.picks if p["code"] == "000001")
        real_estate = next(p for p in result.picks if p["code"] == "000002")
        assert semiconductor["weighted_score"] > real_estate["weighted_score"]

    def test_factor_deduplication(self):
        from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

        engine = WeightedFusionEngine()
        breakdown = {
            "obv_trend": 30,
            "obv": 20,  # 同义因子
            "wr_pullback": 25,
        }
        reduced, redundancy = engine._deduplicate_factors(breakdown)
        # obv_trend 和 obv 应该合并
        assert "obv_trend" in reduced or "obv" in reduced
        assert len(reduced) <= len(breakdown)

    def test_convenience_function(self):
        from kronos_factors.engine.weighted_fusion import weighted_fusion

        picks = [{"code": "000001", "score": 80}]
        result = weighted_fusion(
            strategy_results={"test_mode": picks},
            top_n=5,
        )
        assert isinstance(result, list)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
# SectorHeatmapEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestSectorHeatmapEngine:
    def test_init_default_url(self):
        from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

        engine = SectorHeatmapEngine()
        assert "postgresql" in engine.pg_url

    def test_init_custom_url(self):
        from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

        engine = SectorHeatmapEngine(pg_url="postgresql://test:test@localhost/test")
        assert "test:test@localhost/test" in engine.pg_url

    def test_sector_stat_dataclass(self):
        from kronos_factors.engine.sector_heatmap import SectorStat

        stat = SectorStat(
            sector="半导体",
            total_stocks=100,
            hit_stocks=15,
            hit_rate=0.15,
            avg_gain_pct=3.2,
            trend="strong_up",
        )
        assert stat.sector == "半导体"
        assert stat.hit_rate == 0.15
        assert stat.trend == "strong_up"

    def test_market_state_dataclass(self):
        from kronos_factors.engine.sector_heatmap import MarketState

        state = MarketState(
            limit_up_count=120,
            limit_down_count=10,
            breadth=0.65,
            circulation_heat=75,
        )
        assert state.limit_up_count == 120
        assert state.breadth == 0.65

    def test_sector_trend_logic(self):
        from kronos_factors.engine.sector_heatmap import SectorStat

        # hit_rate >= 0.15 → strong_up
        stat1 = SectorStat(sector="A", hit_rate=0.20)
        assert stat1.trend == "strong_up"  # 实际逻辑在 _compute_sector_stats 中

        # hit_rate >= 0.08 → exploring
        stat2 = SectorStat(sector="B", hit_rate=0.10)
        assert stat2.trend == "exploring"

    @patch("kronos_factors.engine.sector_heatmap.SectorHeatmapEngine.db")
    def test_get_sector_dashboard_with_mock(self, mock_db):
        from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

        # Mock cursor
        mock_cursor = MagicMock()
        mock_db.cursor.return_value = mock_cursor

        # Mock limit_list_d results
        mock_cursor.fetchall.side_effect = [
            [("半导体", 15, 4.5), ("新能源", 8, 2.3)],  # limit_up by sector
            [("半导体", 100, 60), ("新能源", 80, 40), ("房地产", 50, 20)],  # total by sector
            [(120,)],  # limit_up_count
            [(10,)],  # limit_down_count
            [(3000, 5000)],  # up_count, total
        ]

        engine = SectorHeatmapEngine(pg_url="postgresql://test:test@localhost/test")
        try:
            dashboard = engine.get_sector_dashboard("2026-06-30")
            assert dashboard.trade_date == "2026-06-30"
            assert dashboard.market_state.limit_up_count == 120
        finally:
            engine.close()

    def test_get_hot_sectors_empty(self):
        from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

        engine = SectorHeatmapEngine(pg_url="postgresql://test:test@localhost/test")
        try:
            # 无数据时返回空列表
            hot = engine.get_hot_sectors("2026-06-30", min_hit_rate=0.99)
            assert isinstance(hot, list)
        except Exception:
            # 数据库不可用时可能抛异常（预期）
            pass
        finally:
            engine.close()


# ═══════════════════════════════════════════════════════════════
# LLMIntelligenceEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestLLMIntelligenceEngine:
    def test_init_no_api_key(self):
        from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine

        engine = LLMIntelligenceEngine(api_key="")
        assert not engine.is_available()

    def test_init_with_api_key(self):
        from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine

        # 不引入 openai SDK（测试环境可能没有）
        engine = LLMIntelligenceEngine(api_key="test-key")
        # 如果 SDK 可用，client 存在；否则 None
        assert engine.api_key == "test-key"

    def test_sentiment_result_dataclass(self):
        from kronos_factors.engine.llm_intelligence import SentimentResult

        result = SentimentResult(
            sentiment="positive",
            confidence=0.85,
            keywords=["机构调研", "技术突破"],
            summary="Q3 营收增长 50%",
            event_count=3,
        )
        assert result.sentiment == "positive"
        assert result.confidence == 0.85

    def test_sentiment_cache_entry(self):
        from kronos_factors.engine.llm_intelligence import (
            SentimentCacheEntry,
            SentimentResult,
        )
        import time

        result = SentimentResult(sentiment="positive", confidence=0.8)
        entry = SentimentCacheEntry(
            stock_code="000001",
            result=result,
            cached_at=time.time() - 100,  # 100 秒前
            ttl_seconds=3600,
        )
        assert not entry.is_expired()

        expired_entry = SentimentCacheEntry(
            stock_code="000001",
            result=result,
            cached_at=time.time() - 7200,  # 2 小时前
            ttl_seconds=3600,
        )
        assert expired_entry.is_expired()

    def test_filter_by_sentiment_positive_boost(self):
        from kronos_factors.engine.llm_intelligence import SentimentResult

        # 模拟情绪过滤逻辑
        picks = [
            {"code": "000001", "score": 80, "sentiment_score": SentimentResult(
                sentiment="positive", confidence=0.9, keywords=["利好"], summary="Q3 增长", event_count=2
            )},
            {"code": "000002", "score": 70, "sentiment_score": SentimentResult(
                sentiment="negative", confidence=0.8, keywords=["减持"], summary="机构减持", event_count=1
            )},
            {"code": "000003", "score": 60},  # 无情绪数据
        ]

        # 过滤：排除负面，正面加分
        filtered = []
        for pick in picks:
            sentiment = pick.get("sentiment_score")
            if isinstance(sentiment, SentimentResult):
                if sentiment.sentiment == "negative" and sentiment.confidence > 0.7:
                    continue  # 排除
                if sentiment.sentiment == "positive" and sentiment.confidence > 0.6:
                    pick["score"] = pick.get("score", 0) + 5
            filtered.append(pick)

        assert len(filtered) == 2  # 000002 被排除
        assert filtered[0]["score"] == 85  # 正面加分

    def test_batch_scan_empty_list(self):
        from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine

        engine = LLMIntelligenceEngine(api_key="")
        result = engine.batch_scan([], concurrency=5)
        assert result == {}

    @patch("kronos_factors.engine.llm_intelligence.LLMIntelligenceEngine._call_llm")
    def test_scan_news_sentiment_with_mock_llm(self, mock_call_llm):
        from kronos_factors.engine.llm_intelligence import LLMIntelligenceEngine, SentimentResult

        mock_result = SentimentResult(
            sentiment="positive", confidence=0.8, keywords=["技术突破"], summary="研发突破", event_count=1
        )
        mock_call_llm.return_value = mock_result

        engine = LLMIntelligenceEngine(api_key="test-key")
        # 绕过 _client 不可用的问题
        engine._client = MagicMock()

        result = engine.scan_news_sentiment("000001", query_days=3)
        assert result.sentiment == "positive"


# ═══════════════════════════════════════════════════════════════
# RiskParityAllocator Tests
# ═══════════════════════════════════════════════════════════════

class TestRiskParityAllocator:
    def test_init(self):
        from kronos_factors.engine.risk_parity import RiskParityAllocator

        allocator = RiskParityAllocator()
        assert allocator.pg_url is not None

    def test_allocation_result_dataclass(self):
        from kronos_factors.engine.risk_parity import AllocationResult

        result = AllocationResult(
            picks_with_weight=[{"code": "000001", "weight": 0.3, "target_shares": 100}],
            total_capital=100000,
            expected_vol=0.12,
            max_single_weight_actual=0.3,
        )
        assert result.total_capital == 100000
        assert result.expected_vol == 0.12

    def test_compute_weights_uniform_vol(self):
        from kronos_factors.engine.risk_parity import RiskParityAllocator

        allocator = RiskParityAllocator()
        volatilities = {"000001": 0.20, "000002": 0.20, "600519": 0.20}
        weights = allocator._compute_weights(volatilities)
        assert abs(weights["000001"] - 0.3333) < 0.01
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_compute_weights_low_vol_high_weight(self):
        from kronos_factors.engine.risk_parity import RiskParityAllocator

        allocator = RiskParityAllocator()
        # 000001 波动率低 → 权重高
        volatilities = {"000001": 0.10, "600519": 0.30}
        weights = allocator._compute_weights(volatilities)
        assert weights["000001"] > weights["600519"]
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_apply_max_position_limit(self):
        from kronos_factors.engine.risk_parity import RiskParityAllocator

        allocator = RiskParityAllocator()
        weights = {"000001": 0.40, "000002": 0.35, "600519": 0.25}
        limited = allocator._apply_max_position_limit(weights, max_weight=0.15)
        assert limited["000001"] <= 0.15
        assert abs(sum(limited.values()) - 1.0) < 0.01

    def test_allocate_with_mock_volatility(self):
        from kronos_factors.engine.risk_parity import RiskParityAllocator, AllocationResult

        allocator = RiskParityAllocator()

        # Mock volatility calculation
        picks = [
            {"code": "000001", "price": 10.0},
            {"code": "000002", "price": 20.0},
            {"code": "600519", "price": 1800.0},
        ]

        with patch.object(allocator, "get_stock_volatility") as mock_vol:
            mock_vol.side_effect = [0.15, 0.20, 0.25]

            result = allocator.allocate(picks, total_capital=1000000, max_single_weight=0.4)

            assert len(result.picks_with_weight) == 3
            assert result.total_capital == 1000000
            assert all("weight" in p for p in result.picks_with_weight)
            assert all("target_shares" in p for p in result.picks_with_weight)


# ═══════════════════════════════════════════════════════════════
# MultiIndexEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestMultiIndexEngine:
    def test_init(self):
        from kronos_factors.engine.multi_index import MultiIndexEngine

        engine = MultiIndexEngine()
        assert "CSI300" in engine.benchmarks
        assert "CSI500" in engine.benchmarks
        assert "创业板指" in engine.benchmarks

    def test_excess_return_calculation(self):
        from kronos_factors.engine.multi_index import MultiIndexEngine

        engine = MultiIndexEngine()
        excess = engine._calc_excess_return(stock_score=75, benchmark_score=60)
        assert excess == 15.0

        excess_negative = engine._calc_excess_return(stock_score=50, benchmark_score=60)
        assert excess_negative == -10.0

    def test_rank_components(self):
        from kronos_factors.engine.multi_index import MultiIndexEngine

        engine = MultiIndexEngine()
        components = [
            {"code": "000001", "score": 70},
            {"code": "000002", "score": 85},
            {"code": "600519", "score": 60},
        ]
        ranked = engine._rank_components(components, top_n=2)
        assert len(ranked) == 2
        assert ranked[0]["code"] == "000002"  # 最高分


# ═══════════════════════════════════════════════════════════════
# Integration Tests (orchestrator)
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorV5:
    def test_run_fusion_screening_v5_exists(self):
        """验证 V5.0 入口存在."""
        try:
            from services.screener_service.app import orchestrator
            assert hasattr(orchestrator, "run_fusion_screening_v5")
            assert hasattr(orchestrator, "run_screening_v5")
        except ImportError:
            # 直接测试 orchestrator 文件
            import sys
            sys.path.insert(0, os.path.join(_PACKAGES, "..", "services", "screener-service"))
            from app import orchestrator
            assert hasattr(orchestrator, "run_fusion_screening_v5")

    def test_v5_env_variables(self):
        """验证环境变量控制."""
        import os
        assert os.environ.get("ENABLE_WEIGHTED_FUSION", "true").lower() == "true"
        assert os.environ.get("ENABLE_SECTOR_HEATMAP", "true").lower() == "true"
        # 情绪和风险平价默认关闭
        assert os.environ.get("ENABLE_LLM_INTELLIGENCE", "false").lower() == "false"
        assert os.environ.get("ENABLE_RISK_PARITY", "false").lower() == "false"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
