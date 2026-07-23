"""RiskParityAllocator — 风险平价仓位分配器.

对融合后的 top_n 候选，根据波动率倒数分配仓位权重，替代固定 max_position。

算法:
  1. 获取每只股票近 n 日波动率（stddev of pct_chg）
  2. 风险平价权重: w_i = (1/vol_i) / sum(1/vol_j)
  3. 单股上限裁剪: w_i > max_single_weight → 截断为 max，余量按比例再分配
  4. 按当前价格计算目标股数

Usage:
    from kronos_factors.engine.risk_parity import RiskParityAllocator

    allocator = RiskParityAllocator()
    result = allocator.allocate(picks, total_capital=500000)
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("kronos.risk_parity")

DEFAULT_LOOKBACK_DAYS = 20
DEFAULT_MAX_SINGLE_WEIGHT = 0.15
DEFAULT_TARGET_VOLATILITY = 0.15


@dataclass
class AllocationResult:
    """仓位分配结果."""
    picks_with_weight: list[dict] = field(default_factory=list)
    total_capital: float = 0.0
    expected_vol: float = 0.0          # 组合预期波动率
    max_single_weight_actual: float = 0.0  # 实际最大单股权重


class RiskParityAllocator:
    """风险平价仓位分配器."""

    def __init__(self, pg_url: str | None = None):
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL",
            "postgresql://kronos:kronos@localhost:6432/kronos"
        )
        self._conn = None

    @property
    def db(self):
        if self._conn is None or self._conn.closed:
            import psycopg2
            self._conn = psycopg2.connect(self.pg_url)
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    def get_stock_volatility(
        self,
        code: str,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> float:
        """获取单只股票的历史波动率.

        Args:
            code: 股票代码
            lookback_days: 回看天数

        Returns:
            日波动率 (0.0-1.0)，失败时返回 0.03
        """
        try:
            cur = self.db.cursor()
            cur.execute("""
                SELECT pct_chg FROM daily_kline
                WHERE code = %s
                ORDER BY trade_date DESC
                LIMIT %s
            """, (code, lookback_days))

            changes = [float(r[0]) for r in cur.fetchall() if r[0] is not None]

            if len(changes) < 5:
                logger.warning("Insufficient data for %s, using default vol=0.03", code)
                return 0.03

            vol = np.std(changes) / 100  # pct_chg 是百分比值
            # 最小波动率 0.01（避免除零）
            return max(vol, 0.01)

        except Exception as e:
            logger.error("Failed to get volatility for %s: %s", code, e)
            return 0.03  # 默认 3%

    def _compute_weights(self, volatilities: dict[str, float]) -> dict[str, float]:
        """计算风险平价权重.

        w_i = (1 / vol_i) / sum(1 / vol_j)
        """
        if not volatilities:
            return {}

        inv_vol = {code: 1 / max(vol, 1e-6) for code, vol in volatilities.items()}
        total_inv = sum(inv_vol.values())

        if total_inv == 0:
            n = len(volatilities)
            return {code: 1 / n for code in volatilities}

        return {code: inv / total_inv for code, inv in inv_vol.items()}

    def _apply_max_position_limit(
        self,
        weights: dict[str, float],
        max_weight: float = DEFAULT_MAX_SINGLE_WEIGHT,
    ) -> dict[str, float]:
        """单股上限裁剪（迭代重分配）.

        若 w_i > max_weight，截断为 max_weight，余量按比例重分配给未超限标的；
        重分配后若又有标的被推过上限，反复裁剪直至余量归零或无未超限容量可吸收。
        全部到顶（无未超限标的）时持现金（sum < 1.0），但绝不突破单股上限。
        """
        limited = dict(weights)
        eps = 1e-12

        while True:
            # 1. 截断所有超限标的，累计余量
            excess = 0.0
            for code in limited:
                if limited[code] > max_weight + eps:
                    excess += limited[code] - max_weight
                    limited[code] = max_weight

            if excess <= eps:
                break  # 无超限 → 收敛

            # 2. 余量按比例分给当前未超限的标的
            uncapped = [c for c in limited if limited[c] < max_weight - eps]
            if not uncapped:
                break  # 全部到顶，余量无处可去 → 持现金

            uncapped_total = sum(limited[c] for c in uncapped)
            if uncapped_total <= eps:
                # 未超限标的权重都 ≈0：均摊
                share = excess / len(uncapped)
                for c in uncapped:
                    limited[c] += share
            else:
                for c in uncapped:
                    limited[c] += (limited[c] / uncapped_total) * excess
            # 下一轮重新裁剪被推过上限的标的

        return limited

    def allocate(
        self,
        picks: list[dict],
        total_capital: float,
        max_single_weight: float = DEFAULT_MAX_SINGLE_WEIGHT,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> AllocationResult:
        """风险平价仓位分配.

        Args:
            picks: 候选股列表（每只含 code, price）
            total_capital: 总资金
            max_single_weight: 单股最大仓位（0.0-1.0）
            lookback_days: 波动率计算天数

        Returns:
            AllocationResult: 含 weight + target_shares
        """
        if not picks or total_capital <= 0:
            return AllocationResult()

        # Step 1: 获取波动率
        volatilities = {}
        for pick in picks:
            code = pick.get("code", "")
            if code:
                volatilities[code] = self.get_stock_volatility(code, lookback_days)

        # Step 2: 风险平价权重
        weights = self._compute_weights(volatilities)

        # Step 3: 上限裁剪
        weights = self._apply_max_position_limit(weights, max_single_weight)

        # Step 4: 计算目标股数
        picks_with_weight = []
        max_actual = 0.0
        for pick in picks:
            code = pick.get("code", "")
            weight = weights.get(code, 0.0)
            price = pick.get("price", 0) or pick.get("close", 0) or pick.get("entry_price", 0) or 1.0

            target_amount = weight * total_capital
            target_shares = int(target_amount / price / 100) * 100  # A 股 100 股整数倍

            entry = {**pick, "weight": round(weight, 4), "target_shares": max(target_shares, 100)}
            picks_with_weight.append(entry)
            max_actual = max(max_actual, weight)

        # Step 5: 组合预期波动率
        expected_vol = np.sqrt(
            sum(volatilities.get(p.get("code", ""), 0.03) ** 2 *
                weights.get(p.get("code", ""), 0.0) ** 2
                for p in picks)
        )

        return AllocationResult(
            picks_with_weight=picks_with_weight,
            total_capital=total_capital,
            expected_vol=float(expected_vol),
            max_single_weight_actual=max_actual,
        )
