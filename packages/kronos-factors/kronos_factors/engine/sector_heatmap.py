"""SectorHeatmapEngine — 板块实时热度引擎.

聚合当日涨停板/炸板/换手数据，输出每只股票所属板块的热度评分。
为 WeightedFusionEngine 提供板块过滤上下文（是否属于当日热点板块）。

数据来源:
  - limit_list_d: 涨停/跌停列表
  - daily_kline: 日线行情
  - stock_profiles: 个股基本面（industry 字段）

Usage:
    from kronos_factors.engine.sector_heatmap import SectorHeatmapEngine

    engine = SectorHeatmapEngine()
    dashboard = engine.get_sector_dashboard(trade_date="2026-06-30")
    hot_sectors = engine.get_hot_sectors(min_hit_rate=0.6)
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger("kronos.sector_heatmap")


@dataclass
class SectorStat:
    """板块热度统计."""
    sector: str                    # 板块名称 (industry 字段)
    total_stocks: int = 0          # 板块内总股票数
    upstocks: int = 0              # 当日上涨股票数
    hit_stocks: int = 0            # 涨停股票数 (limit_type='U')
    limit_up_count: int = 0        # 曾经涨停后回落数
    hit_rate: float = 0.0          # 涨停率 = hit_stocks / total_stocks
    avg_gain_pct: float = 0.0      # 板块平均涨幅
    volume_ratio: float = 1.0      # 板块量比 (相对 5 日均量)
    trend: str = "flat"            # "strong_up" | "exploring" | "flat" | "down"


@dataclass
class MarketState:
    """全市场环境."""
    limit_up_count: int = 0        # 全市场涨停数
    limit_down_count: int = 0      # 全市场跌停数
    breadth: float = 0.0           # 涨跌比 = 涨股数 / 总股数
    circulation_heat: int = 0      # 流通热度 (0-100)


@dataclass
class SectorDashboard:
    """板块热度仪表盘."""
    sectors: list[SectorStat] = field(default_factory=list)
    market_state: MarketState = field(default_factory=MarketState)
    trade_date: str = ""


class SectorHeatmapEngine:
    """板块实时热度引擎."""

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

    def get_sector_dashboard(self, trade_date: str) -> SectorDashboard:
        """返回全市场板块热度。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)

        Returns:
            SectorDashboard: 含 sectors + market_state
        """
        sectors = self._compute_sector_stats(trade_date)
        market_state = self._compute_market_state(trade_date)

        return SectorDashboard(
            sectors=sectors,
            market_state=market_state,
            trade_date=trade_date,
        )

    def get_hot_sectors(
        self,
        trade_date: str,
        top_n: int = 15,
        min_hit_rate: float = 0.6,
        min_avg_gain: float = 2.0,
    ) -> list[str]:
        """返回热度达标板块列表（用于过滤）。

        热度标准: hit_rate >= min_hit_rate AND avg_gain_pct >= min_avg_gain

        Args:
            trade_date: 交易日期
            top_n: 返回板块数
            min_hit_rate: 最低涨停率阈值
            min_avg_gain: 最低平均涨幅阈值

        Returns:
            板块名称列表 (已按 hit_rate 降序)
        """
        dashboard = self.get_sector_dashboard(trade_date)

        hot_sectors = []
        for sector in dashboard.sectors:
            if sector.hit_rate >= min_hit_rate and sector.avg_gain_pct >= min_avg_gain:
                hot_sectors.append(sector.sector)

        return hot_sectors[:top_n]

    def get_stock_sector_heat(
        self,
        code: str,
        trade_date: str,
    ) -> Optional[SectorStat]:
        """单只股票的板块热度查询.

        Args:
            code: 股票代码
            trade_date: 交易日期

        Returns:
            SectorStat 或 None（若板块无数据）
        """
        dashboard = self.get_sector_dashboard(trade_date)

        # 获取股票所属行业
        sector_name = self._get_stock_industry(code)
        if not sector_name:
            return None

        for sector in dashboard.sectors:
            if sector.sector == sector_name:
                return sector

        return None

    def _compute_sector_stats(self, trade_date: str) -> list[SectorStat]:
        """计算各板块热度统计."""
        sectors = []

        try:
            cur = self.db.cursor()

            # 1. 涨停板分板块统计
            cur.execute("""
                SELECT
                    sp.industry AS sector,
                    COUNT(*) AS hit_stocks,
                    AVG(dk.pct_chg) AS avg_gain_pct
                FROM limit_list_d ll
                LEFT JOIN stock_profiles sp ON sp.code = ll.code
                LEFT JOIN daily_kline dk ON dk.code = ll.code AND dk.trade_date = ll.trade_date
                WHERE ll.trade_date = %s AND ll.limit_type = 'U'
                  AND sp.industry IS NOT NULL
                GROUP BY sp.industry
                ORDER BY hit_stocks DESC
            """, (trade_date,))

            limit_up_by_sector = {}
            for row in cur.fetchall():
                sector_name = row[0]
                hit_stocks = int(row[1] or 0)
                avg_gain = float(row[2] or 0)

                limit_up_by_sector[sector_name] = {
                    "hit_stocks": hit_stocks,
                    "avg_gain_pct": avg_gain,
                }

            # 2. 全市场分板块上涨数
            cur.execute("""
                SELECT
                    sp.industry AS sector,
                    COUNT(*) AS total_stocks,
                    SUM(CASE WHEN dk.pct_chg > 0 THEN 1 ELSE 0 END) AS upstocks
                FROM daily_kline dk
                LEFT JOIN stock_profiles sp ON sp.code = dk.code
                WHERE dk.trade_date = %s AND sp.industry IS NOT NULL
                GROUP BY sp.industry
            """, (trade_date,))

            sector_total = {}
            for row in cur.fetchall():
                sector_name = row[0]
                total_stocks = int(row[1] or 0)
                upstocks = int(row[2] or 0)
                sector_total[sector_name] = {
                    "total_stocks": total_stocks,
                    "upstocks": upstocks,
                }

            # 3. 合并板块数据
            all_sectors = set(limit_up_by_sector.keys()) | set(sector_total.keys())

            for sector_name in all_sectors:
                limit_up = limit_up_by_sector.get(sector_name, {})
                total = sector_total.get(sector_name, {})

                total_stocks = total.get("total_stocks", 0)
                upstocks = total.get("upstocks", 0)
                hit_stocks = limit_up.get("hit_stocks", 0)
                avg_gain = limit_up.get("avg_gain_pct", 0)

                hit_rate = hit_stocks / total_stocks if total_stocks > 0 else 0

                # 趋势判断
                if hit_rate >= 0.15:
                    trend = "strong_up"
                elif hit_rate >= 0.08:
                    trend = "exploring"
                elif avg_gain < -1:
                    trend = "down"
                else:
                    trend = "flat"

                sectors.append(SectorStat(
                    sector=sector_name,
                    total_stocks=total_stocks,
                    upstocks=upstocks,
                    hit_stocks=hit_stocks,
                    hit_rate=hit_rate,
                    avg_gain_pct=avg_gain,
                    trend=trend,
                ))

            # 按 hit_rate 降序
            sectors.sort(key=lambda x: x.hit_rate, reverse=True)

        except Exception as e:
            logger.error("Failed to compute sector stats: %s", e)
            # 返回空列表（降级）

        return sectors

    def _compute_market_state(self, trade_date: str) -> MarketState:
        """计算全市场环境."""
        try:
            cur = self.db.cursor()

            # 涨停数
            cur.execute("""
                SELECT COUNT(*) FROM limit_list_d
                WHERE trade_date = %s AND limit_type = 'U'
            """, (trade_date,))
            limit_up_count = int(cur.fetchone()[0] or 0)

            # 跌停数
            cur.execute("""
                SELECT COUNT(*) FROM limit_list_d
                WHERE trade_date = %s AND limit_type = 'D'
            """, (trade_date,))
            limit_down_count = int(cur.fetchone()[0] or 0)

            # 涨跌比
            cur.execute("""
                SELECT
                    SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) AS up_count,
                    COUNT(*) AS total
                FROM daily_kline
                WHERE trade_date = %s
            """, (trade_date,))
            row = cur.fetchone()
            up_count = int(row[0] or 0)
            total = int(row[1] or 1)
            breadth = up_count / total if total > 0 else 0

            # 流通热度 (简化版: 涨停数 / 总股数 × 100)
            circulation_heat = int(limit_up_count / total * 100) if total > 0 else 0

            return MarketState(
                limit_up_count=limit_up_count,
                limit_down_count=limit_down_count,
                breadth=breadth,
                circulation_heat=circulation_heat,
            )

        except Exception as e:
            logger.error("Failed to compute market state: %s", e)
            return MarketState()

    def _get_stock_industry(self, code: str) -> Optional[str]:
        """获取股票所属行业."""
        try:
            cur = self.db.cursor()
            cur.execute("""
                SELECT industry FROM stock_profiles WHERE code = %s
            """, (code,))
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error("Failed to get industry for %s: %s", code, e)
            return None


# 便捷函数
def get_sector_heatmap(trade_date: str, pg_url: str | None = None) -> SectorDashboard:
    """便捷函数：获取板块热度仪表盘."""
    engine = SectorHeatmapEngine(pg_url=pg_url)
    try:
        return engine.get_sector_dashboard(trade_date)
    finally:
        engine.close()


def get_hot_sectors(
    trade_date: str,
    top_n: int = 15,
    min_hit_rate: float = 0.6,
    pg_url: str | None = None,
) -> list[str]:
    """便捷函数：获取热度达标板块列表."""
    engine = SectorHeatmapEngine(pg_url=pg_url)
    try:
        return engine.get_hot_sectors(trade_date, top_n, min_hit_rate)
    finally:
        engine.close()
