"""WeightedFusionEngine — V5.0 加权融合引擎.

替代 orchestrator.merge_picks() 的动态加权融合引擎.

核心改进:
  1. mode_profiles: 每模式历史 precision/recall 画像 → 动态权重
  2. 环境适配: 牛市/震荡市/熊市自动调整模式权重
  3. 因子去冗余: Pearson 相关性 > 0.8 的因子合并
  4. 板块热度修正: 非热点板块的权重 × 0.5

Usage:
    from kronos_factors.engine.weighted_fusion import WeightedFusionEngine

    engine = WeightedFusionEngine(mode_profiles_path="config/mode_profiles.json")
    result = engine.run(
        strategy_results={"leader_scalp": picks1, "bi_trend_launch": picks2},
        market_env="neutral",
        hot_sectors=["半导体", "AI算力"],
        top_n=30,
    )
"""
import json
import logging
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("kronos.weighted_fusion")

# 默认 mode_profiles 路径（相对于 kronos_factors 包）
_DEFAULT_PROFILES_PATH = Path(__file__).parent.parent.parent / "config" / "mode_profiles.json"

# Pearson 相关性阈值：> 此值的因子视为冗余，合并
FACTOR_CORRELATION_THRESHOLD = 0.8


@dataclass
class ModeProfile:
    """模式画像（从回测历史数据拟合）."""
    mode: str
    precision: float = 0.5      # 命中率 (0-1)
    recall: float = 0.5         # 覆盖率 (0-1)
    speed: str = "medium"       # "very_fast" | "fast" | "medium" | "slow"
    style: str = "trend"        # "momentum" | "trend" | "event_driven" | "statistical" | "theme"
    primary_factors: list[str] = field(default_factory=list)
    risk_preference: str = "moderate"  # "aggressive" | "moderate" | "conservative"
    env_affinity: dict[str, float] = field(default_factory=lambda: {"bull": 1.0, "neutral": 1.0, "bear": 1.0})
    note: str = ""


@dataclass
class FusionResult:
    """融合结果."""
    picks: list[dict]                          # 融合后的候选
    weights_used: dict[str, float] = field(default_factory=dict)   # {mode: weight}
    factor_redundancy: dict[str, list[str]] = field(default_factory=dict)  # {主因子: [冗余因子]}


class WeightedFusionEngine:
    """V5.0 加权融合引擎.

    替代 orchestrator.merge_picks() 的动态加权融合引擎.
    """

    def __init__(
        self,
        mode_profiles_path: str | None = None,
        mode_profiles_dict: dict | None = None,
    ):
        """初始化融合引擎.

        Args:
            mode_profiles_path: mode_profiles.json 文件路径
            mode_profiles_dict: 直接传入字典（优先使用）
        """
        self.mode_profiles: dict[str, ModeProfile] = {}
        if mode_profiles_dict:
            self._load_from_dict(mode_profiles_dict)
        else:
            path = mode_profiles_path or str(_DEFAULT_PROFILES_PATH)
            self._load_from_file(path)

    def _load_from_file(self, path: str) -> None:
        """从 JSON 文件加载 mode_profiles."""
        if not os.path.exists(path):
            logger.warning("mode_profiles file not found: %s, using defaults", path)
            self._load_defaults()
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            models = data.get("models") or data
            for mode, profile_dict in models.items():
                self.mode_profiles[mode] = ModeProfile(
                    mode=mode,
                    precision=profile_dict.get("precision", 0.5),
                    recall=profile_dict.get("recall", 0.5),
                    speed=profile_dict.get("speed", "medium"),
                    style=profile_dict.get("style", "trend"),
                    primary_factors=profile_dict.get("primary_factors", []),
                    risk_preference=profile_dict.get("risk_preference", "moderate"),
                    env_affinity=profile_dict.get("env_affinity", {}),
                    note=profile_dict.get("note", ""),
                )
            logger.info("Loaded %d mode profiles from %s", len(self.mode_profiles), path)
        except Exception as e:
            logger.error("Failed to load mode_profiles: %s, using defaults", e)
            self._load_defaults()

    def _load_from_dict(self, data: dict) -> None:
        """从字典加载 mode_profiles."""
        for mode, profile_dict in (data.get("models") or data).items():
            self.mode_profiles[mode] = ModeProfile(
                mode=mode,
                precision=profile_dict.get("precision", 0.5),
                recall=profile_dict.get("recall", 0.5),
                speed=profile_dict.get("speed", "medium"),
                style=profile_dict.get("style", "trend"),
                primary_factors=profile_dict.get("primary_factors", []),
                risk_preference=profile_dict.get("risk_preference", "moderate"),
                env_affinity=profile_dict.get("env_affinity", {}),
                note=profile_dict.get("note", ""),
            )

    def _load_defaults(self) -> None:
        """加载默认模式画像（fallback）."""
        defaults = {
            "leader_scalp": ModeProfile(mode="leader_scalp", precision=0.72, recall=0.43),
            "leader_auction": ModeProfile(mode="leader_auction", precision=0.65, recall=0.35),
            "bi_trend_launch": ModeProfile(mode="bi_trend_launch", precision=0.55, recall=0.78),
            "short_mode": ModeProfile(mode="short_mode", precision=0.48, recall=0.62),
            "supply_chain": ModeProfile(mode="supply_chain", precision=0.60, recall=0.52),
        }
        self.mode_profiles = defaults

    def compute_dynamic_weights(
        self,
        modes: list[str],
        market_env: str = "neutral",
    ) -> dict[str, float]:
        """根据市场环境计算动态权重.

        算法:
          base_weight[mode] = (precision + recall) / 2
          env_factor = mode_profiles[mode].env_affinity[market_env]
          weight[mode] = base_weight[mode] × env_factor
          normalize sum = 1.0

        Args:
            modes: 参与融合的模式列表
            market_env: "bull" | "neutral" | "bear" | "crash"

        Returns:
            {mode: weight} (已归一化，sum=1.0)
        """
        weights = {}
        for mode in modes:
            profile = self.mode_profiles.get(mode, ModeProfile(mode=mode))
            base_weight = (profile.precision + profile.recall) / 2
            env_factor = profile.env_affinity.get(market_env, 1.0)
            weights[mode] = base_weight * env_factor

        # 归一化
        total = sum(weights.values())
        if total > 0:
            weights = {k: v / total for k, v in weights.items()}

        return weights

    def run(
        self,
        strategy_results: dict[str, list[dict]],
        market_env: str = "neutral",
        hot_sectors: list[str] | None = None,
        top_n: int = 30,
    ) -> FusionResult:
        """执行加权融合.

        Args:
            strategy_results: {mode_name: picks_list}
            market_env: "bull" | "neutral" | "bear" | "crash"
            hot_sectors: 板块热度过滤列表（可选）
            top_n: 返回候选数

        Returns:
            FusionResult: 含 picks + weights_used + factor_redundancy
        """
        if not strategy_results:
            return FusionResult(picks=[])

        # Step 1: 计算动态权重
        modes = list(strategy_results.keys())
        weights = self.compute_dynamic_weights(modes, market_env)

        # Step 2: 加权投票
        stock_data: dict[str, dict] = {}

        for mode, picks in strategy_results.items():
            if not picks or not isinstance(picks, list):
                continue

            weight = weights.get(mode, 0)

            for pick in picks:
                code = pick.get("code", "")
                if not code:
                    continue

                if code not in stock_data:
                    stock_data[code] = {
                        "code": code,
                        "weighted_score": 0.0,
                        "consensus_count": 0,
                        "modes": [],
                        "data": pick,
                        "factor_breakdown": pick.get("factor_breakdown", {}),
                    }

                entry = stock_data[code]
                score = pick.get("total_score", pick.get("score", 50))
                entry["weighted_score"] += score * weight
                entry["consensus_count"] += 1
                entry["modes"].append(mode)

                # 保留最高分的数据
                if score > entry["data"].get("score", 0):
                    entry["data"] = pick
                    entry["factor_breakdown"] = pick.get("factor_breakdown", {})

        # Step 3: 板块热度修正（非热点板块 × 0.5）
        if hot_sectors:
            for entry in stock_data.values():
                sector = entry["data"].get("industry", "")
                if sector and sector not in hot_sectors:
                    entry["weighted_score"] *= 0.5

        # Step 4: 排序（primary: consensus_count DESC, secondary: weighted_score DESC）
        ranked = sorted(
            stock_data.values(),
            key=lambda x: (x["consensus_count"], x["weighted_score"]),
            reverse=True,
        )

        # Step 5: 因子去冗余（Pearson 相关性 > 0.8 合并）
        picks_result = []
        for entry in ranked[:top_n]:
            pick = entry["data"].copy()
            pick["consensus_count"] = entry["consensus_count"]
            pick["consensus_modes"] = entry["modes"]
            pick["weighted_score"] = round(entry["weighted_score"], 2)
            pick["source_mode"] = entry["modes"][0] if entry["modes"] else "unknown"

            # 因子去冗余
            if entry["factor_breakdown"]:
                reduced_breakdown, redundancy = self._deduplicate_factors(entry["factor_breakdown"])
                pick["factor_breakdown"] = reduced_breakdown

            picks_result.append(pick)

        # 统计冗余
        all_redundancy: dict[str, list[str]] = {}
        for entry in ranked[:top_n]:
            if entry["factor_breakdown"]:
                _, redundancy = self._deduplicate_factors(entry["factor_breakdown"])
                for main_factor, redundant_factors in redundancy.items():
                    if main_factor not in all_redundancy:
                        all_redundancy[main_factor] = []
                    all_redundancy[main_factor].extend(redundant_factors)

        return FusionResult(
            picks=picks_result,
            weights_used=weights,
            factor_redundancy=all_redundancy,
        )

    def _deduplicate_factors(
        self,
        factor_breakdown: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        """因子去冗余（基于 Pearson 相关性）.

        简化版本：基于因子名称相似度（同义因子合并）。
        完整版：需要历史数据计算实际 Pearson 相关系数。

        Args:
            factor_breakdown: {factor_name: score}

        Returns:
            (reduced_breakdown, redundancy_map)
        """
        # 简化版本：基于因子名称相似度合并
        # 完整版本需要 factor_correlation_matrix（从历史数据计算）

        # 同义因子组（示例）
        synonym_groups = [
            {"obv_trend", "obv", "obv_score"},
            {"wr_pullback", "wr", "williams_r"},
            {"gain_quality", "gain", "price_momentum"},
            {"sector_leader", "sector_strength", "industry_leader"},
            {"volume_contract", "volume_shrink", "low_volume"},
        ]

        reduced = {}
        redundancy_map: dict[str, list[str]] = {}

        processed = set()

        for group in synonym_groups:
            # 找到组内得分最高的因子
            group_factors = {f: factor_breakdown.get(f, 0) for f in group if f in factor_breakdown}
            if not group_factors:
                continue

            main_factor = max(group_factors, key=group_factors.get)
            main_score = group_factors[main_factor]

            # 合并其他因子得分
            redundant_factors = []
            for factor, score in group_factors.items():
                if factor != main_factor:
                    main_score += score * 0.5  # 冗余因子贡献 50%
                    redundant_factors.append(factor)
                    processed.add(factor)

            reduced[main_factor] = round(main_score, 2)
            if redundant_factors:
                redundancy_map[main_factor] = redundant_factors

            processed.add(main_factor)

        # 未处理的因子直接保留
        for factor, score in factor_breakdown.items():
            if factor not in processed:
                reduced[factor] = score

        return reduced, redundancy_map


# 便捷函数（向后兼容 orchestrator.merge_picks）
def weighted_fusion(
    strategy_results: dict[str, list[dict]],
    market_env: str = "neutral",
    hot_sectors: list[str] | None = None,
    top_n: int = 30,
    mode_profiles_path: str | None = None,
) -> list[dict]:
    """便捷函数：加权融合.

    直接返回 picks 列表（不含 weights_used 等元信息）。
    """
    engine = WeightedFusionEngine(mode_profiles_path=mode_profiles_path)
    result = engine.run(
        strategy_results=strategy_results,
        market_env=market_env,
        hot_sectors=hot_sectors,
        top_n=top_n,
    )
    return result.picks
