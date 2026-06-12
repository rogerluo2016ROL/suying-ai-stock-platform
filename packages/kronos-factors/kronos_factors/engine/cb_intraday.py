"""匪爷可转债日内投机博弈模型 — 竞价→板块→转债映射引擎.

选债逻辑:
  1. 开盘竞价锁定强势板块/题材/个股 (40%)
  2. 映射板块到可转债
  3. 溢价率越低越好 (35%)
  4. 规模越小越好 (25%)
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_intraday")


class CbIntradayEngine:
    """匪爷可转债日内投机博弈模型 — 竞价驱动转债筛选."""

    def __init__(self, pg_url: str = None):
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"
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
            try:
                self._conn.close()
            except Exception:
                pass

    # ── Scoring helpers ──

    @staticmethod
    def _premium_score(premium_rate: float) -> float:
        """Lower premium = higher score. 0-100."""
        if premium_rate is None:
            return 50.0
        if premium_rate <= 0:
            return 100.0
        if premium_rate <= 5:
            return 100 - premium_rate * 2.0
        if premium_rate <= 15:
            return 90 - (premium_rate - 5) * 2.0
        if premium_rate <= 30:
            return 70 - (premium_rate - 15) * 1.67
        if premium_rate <= 60:
            return 45 - (premium_rate - 30) * 1.0
        return max(5.0, 15 - premium_rate * 0.1)

    @staticmethod
    def _size_score(remain_size: float) -> float:
        """Smaller size = higher score. 0-100."""
        if remain_size is None:
            return 50.0
        size_yi = remain_size / 1e8
        if size_yi <= 0.5:
            return 100.0
        if size_yi <= 1:
            return 100 - (size_yi - 0.5) * 20
        if size_yi <= 3:
            return 90 - (size_yi - 1) * 12
        if size_yi <= 5:
            return 66 - (size_yi - 3) * 13
        if size_yi <= 10:
            return 40 - (size_yi - 5) * 4
        return max(5.0, 20 - size_yi * 0.5)

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute intraday CB speculation screening.

        Pipeline:
          1. Auction data → sector strength ranking
          2. Map strong sectors → convertible bonds
          3. Score by premium rate + size

        Args:
            top_n: max picks to return
            trade_date: trading date (YYYY-MM-DD), default latest

        Returns:
            list of scored pick dicts sorted by total_score desc
        """
        t0 = time.time()
        cur = self.db.cursor()

        # Resolve trade_date
        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            trade_date = row[0] if row and row[0] else date.today().strftime("%Y-%m-%d")
            if isinstance(trade_date, date):
                trade_date = trade_date.strftime("%Y-%m-%d")

        logger.info("CbIntradayEngine: screening for %s, top_n=%d", trade_date, top_n)

        # ── Step 1: Auction sector strength ──
        sector_strength = self._get_sector_strength(cur, trade_date)
        if not sector_strength:
            logger.warning("CbIntradayEngine: no auction data for %s", trade_date)
            return []

        # Top 5 strongest sectors
        top_sectors = sorted(sector_strength.items(), key=lambda x: x[1], reverse=True)[:5]
        strong_sectors = {s for s, _ in top_sectors}
        sector_score_map = dict(top_sectors)

        logger.info(
            "CbIntradayEngine: top sectors: %s",
            [(s, round(sc, 1)) for s, sc in top_sectors],
        )

        # ── Step 2: Find CBs in strong sectors ──
        # Join cb_basic → stocks.industry → match strong sectors
        # Also get latest cb_daily for premium rate
        query = """
        SELECT
            cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
            cb.remain_size, cb.newest_rating, cb.maturity_date,
            d.close, d.cb_over_rate, d.pct_chg, d.amount, d.cb_value,
            s.industry, s.name AS stock_name,
            sk.close AS stock_close, cb.conv_price
        FROM cb_basic cb
        JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code
        LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
        LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code AND sk.trade_date = %s
        WHERE (cb.delist_date IS NULL OR cb.delist_date > %s::date)
          AND s.industry = ANY(%s)
        """
        cur.execute(query, (trade_date, trade_date, trade_date, list(strong_sectors)))
        rows = cur.fetchall()

        if not rows:
            logger.warning(
                "CbIntradayEngine: no CBs found in strong sectors %s",
                strong_sectors,
            )
            return []

        # ── Step 3: Score each CB ──
        picks = []
        for r in rows:
            try:
                (
                    ts_code, name, stk_code, stk_name,
                    remain_size, rating, maturity_date_,
                    close, cb_over_rate, pct_chg, amount, cb_value,
                    industry, stock_name,
                    stock_close, conv_price,
                ) = r

                # Calculate premium rate if not available from Tushare
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / conv_price * stock_close
                    if conv_value > 0:
                        cb_over_rate = (close / conv_value - 1) * 100

                # Sector strength → 0-100 score
                sector_strength_raw = sector_score_map.get(industry, 0)
                # Normalize: strength is typically -5 to +10 pct
                sector_score = min(100, max(0, 50 + sector_strength_raw * 5))

                # Premium rate score (35%)
                premium_score = self._premium_score(cb_over_rate)

                # Size score (25%)
                size_score = self._size_score(remain_size)

                # Weighted total
                total = (
                    sector_score * 0.40
                    + premium_score * 0.35
                    + size_score * 0.25
                )

                # Grade
                if total >= 80:
                    grade = "S"
                elif total >= 65:
                    grade = "A"
                elif total >= 50:
                    grade = "B"
                else:
                    grade = "C"

                picks.append({
                    "code": ts_code,
                    "name": name or ts_code,
                    "stk_code": stk_code,
                    "stk_name": stk_name,
                    "industry": industry,
                    "sector_strength": round(sector_strength_raw, 2),
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "rating": rating,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "sector_score": round(sector_score, 1),
                        "premium_score": round(premium_score, 1),
                        "size_score": round(size_score, 1),
                    },
                })

            except Exception as e:
                logger.debug("CB intraday %s scoring failed: %s", r[0] if r else "?", e)
                continue

        # Sort descending
        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info(
            "CbIntradayEngine: %d picks from %d CBs in %d sectors (%.1fs)",
            len(picks), len(rows), len(strong_sectors), elapsed,
        )

        return picks

    def _get_sector_strength(self, cur, trade_date: str) -> dict:
        """Aggregate auction data by industry → average pct_chg.

        Returns: {industry: avg_pct_chg}
        """
        query = """
        SELECT s.industry, AVG(
            CASE WHEN ao.close > 0
            THEN (ao.open - ao.close) / ao.close * 100
            ELSE 0 END
        ) AS avg_pct
        FROM stk_auction_o ao
        JOIN stocks s ON ao.code = s.code
        WHERE ao.trade_date = %s
          AND s.industry IS NOT NULL
          AND s.industry != ''
          AND ao.close > 0
        GROUP BY s.industry
        HAVING COUNT(*) >= 3
        ORDER BY avg_pct DESC
        """
        try:
            cur.execute(query, (trade_date,))
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}
        except Exception as e:
            logger.warning("CbIntradayEngine: sector strength query failed: %s", e)
            return {}
