"""MultiIndexEngine — 宽基指数成分股超额收益挖掘.

识别跟踪因子超额收益的成分股，适配证监会"试点主动型 ETF"政策方向。

支持的指数:
  - CSI300 (沪深300): sh.000300
  - CSI500 (中证500): sh.000905
  - 创业板指: sz.399006
  - 科创50: sz.000688

Usage:
    from kronos_factors.engine.multi_index import MultiIndexEngine

    engine = MultiIndexEngine()
    picks = engine.run(index_code="CSI300", top_n=20, trade_date="2026-06-30")
"""
import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("kronos.multi_index")

# 指数代码映射
BENCHMARKS = {
    "CSI300": ("sh.000300", "沪深300"),
    "CSI500": ("sh.000905", "中证500"),
    "创业板指": ("sz.399006", "创业板指"),
    "科创50": ("sz.000688", "科创50"),
    # 扩展指数（政策导向）
    "人工智能": ("sz.930713", "AI 指数"),
    "芯片": ("sz.990001", "芯片指数"),
}

# 指数成分股查询表（需要定期更新）
INDEX_COMPONENT_TABLE = "index_component"  # 若不存在则降级到 PG 物化视图


class MultiIndexEngine:
    """宽基指数成分股超额收益挖掘引擎."""

    def __init__(self, pg_url: str | None = None):
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL",
            "postgresql://kronos:kronos@localhost:6432/kronos"
        )
        self.benchmarks = BENCHMARKS
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

    def get_available_indexes(self) -> list[str]:
        """返回可用指数列表."""
        return list(self.benchmarks.keys())

    def _calc_excess_return(
        self,
        stock_score: float,
        benchmark_score: float,
    ) -> float:
        """计算超额收益."""
        return round(stock_score - benchmark_score, 2)

    def _rank_components(
        self,
        components: list[dict],
        top_n: int = 20,
    ) -> list[dict]:
        """按综合评分排序成分股."""
        return sorted(
            components,
            key=lambda x: x.get("score", 0),
            reverse=True,
        )[:top_n]

    def _get_index_stocks(self, index_code: str, trade_date: str) -> list[str]:
        """获取指数成分股列表.

        优先查 index_component 表，若无则降级到物化视图。
        """
        try:
            cur = self.db.cursor()

            # 先尝试查成分股表
            benchmark_ts_code = self.benchmarks.get(index_code, ("", ""))[0]
            if not benchmark_ts_code:
                logger.warning("Unknown index: %s", index_code)
                return []

            try:
                cur.execute("""
                    SELECT code FROM index_component
                    WHERE ts_code = %s AND trade_date = %s
                """, (benchmark_ts_code, trade_date))
                rows = cur.fetchall()
                if rows:
                    return [r[0] for r in rows]
            except Exception:
                # 降级到物化视图
                logger.info("index_component 表不存在，降级到 mv_daily_composite_ranking")
                cur.execute("""
                    SELECT code FROM mv_daily_composite_ranking
                    ORDER BY composite_score DESC LIMIT 300
                """)
                rows = cur.fetchall()
                return [r[0] for r in rows]

            # 如果 trade_date 无数据，尝试最近交易日
            cur.execute("""
                SELECT code FROM index_component
                WHERE ts_code = %s
                ORDER BY trade_date DESC LIMIT 800
            """, (benchmark_ts_code,))
            rows = cur.fetchall()
            return [r[0] for r in rows]

        except Exception as e:
            logger.error("Failed to get index stocks: %s", e)
            return []

    def _get_stock_scores(
        self,
        codes: list[str],
        trade_date: str,
    ) -> dict[str, float]:
        """批量获取股票综合评分."""
        if not codes:
            return {}

        try:
            cur = self.db.cursor()
            # 从物化视图获取评分
            placeholders = ",".join(["%s"] * len(codes))
            cur.execute(f"""
                SELECT code, composite_score FROM mv_daily_composite_ranking
                WHERE code IN ({placeholders})
            """, codes)
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}

        except Exception as e:
            logger.error("Failed to get stock scores: %s", e)
            return {}

    def run(
        self,
        index_code: str = "CSI300",
        top_n: int = 20,
        trade_date: str | None = None,
    ) -> list[dict]:
        """运行指数选股.

        Args:
            index_code: 指数代码（如 CSI300, CSI500, 创业板指）
            top_n: 返回候选数
            trade_date: 交易日期

        Returns:
            超额收益高的成分股列表 [{code, name, score, excess_return, ...}]
        """
        # 默认取最近交易日
        if not trade_date:
            try:
                cur = self.db.cursor()
                cur.execute("SELECT MAX(trade_date) FROM daily_kline")
                trade_date = cur.fetchone()[0]
            except Exception:
                trade_date = "2026-06-30"

        logger.info("Running MultiIndexEngine for %s on %s", index_code, trade_date)

        # Step 1: 获取成分股
        codes = self._get_index_stocks(index_code, trade_date)
        if not codes:
            return []

        # Step 2: 获取评分
        scores = self._get_stock_scores(codes, trade_date)
        if not scores:
            return []

        # Step 3: 计算指数基准（成分股平均分）
        benchmark_score = float(np.mean(list(scores.values())))
        benchmark_score = round(benchmark_score, 1)

        # Step 4: 计算超额收益
        components = []
        for code in codes:
            score = scores.get(code, 0)
            excess = self._calc_excess_return(score, benchmark_score)
            components.append({
                "code": code,
                "score": score,
                "benchmark_score": benchmark_score,
                "excess_return": excess,
                "index_code": index_code,
            })

        # Step 5: 排序
        picks = self._rank_components(components, top_n)

        # Step 6: 补充名称
        try:
            cur = self.db.cursor()
            code_placeholders = ",".join(["%s"] * len(picks))
            cur.execute(f"SELECT code, name FROM stock_profiles WHERE code IN ({code_placeholders})", [p["code"] for p in picks])
            name_map = {r[0]: r[1] for r in cur.fetchall()}
            for pick in picks:
                pick["name"] = name_map.get(pick["code"], pick["code"])
        except Exception:
            for pick in picks:
                pick["name"] = pick["code"]

        return picks
