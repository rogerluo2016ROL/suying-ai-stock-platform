"""匪爷可转债日内投机博弈模型 V2 — 概念驱动版.

选债逻辑:
  1. 开盘竞价锁定强势概念板块 (40%)
  2. 通过 cb_concept 映射概念 → 可转债
  3. 溢价率越低越好 (35%)
  4. 规模越小越好 (25%)
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_intraday")


class CbIntradayEngine:
    """匪爷可转债日内投机博弈模型 V2 — 概念驱动转债筛选."""

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

    @staticmethod
    def _premium_score(premium_rate: float) -> float:
        if premium_rate is None:
            return 50.0
        if premium_rate <= -10:
            return 100.0
        if premium_rate <= -5:
            return 95 + premium_rate * 0.5
        if premium_rate <= 0:
            return 85 + premium_rate * 2
        if premium_rate <= 15:
            return 85 - premium_rate * 2.5
        if premium_rate <= 30:
            return 47.5 - (premium_rate - 15) * 1.5
        if premium_rate <= 60:
            return 25 - (premium_rate - 30) * 0.7
        return max(5.0, 4 - premium_rate * 0.05)

    @staticmethod
    def _size_score(remain_size: float) -> float:
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

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        t0 = time.time()
        cur = self.db.cursor()

        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            trade_date = str(row[0]) if row and row[0] else date.today().strftime("%Y-%m-%d")

        logger.info("CbIntradayEngine V2: screening for %s, top_n=%d", trade_date, top_n)

        # ── Step 1: Get concept strength from auction + ths_daily ──
        concept_strength = self._get_concept_strength(cur, trade_date)
        if not concept_strength:
            logger.warning("CbIntradayEngine V2: no concept strength data for %s", trade_date)
            return []

        top_concepts = sorted(concept_strength.items(), key=lambda x: x[1], reverse=True)[:8]
        strong_concepts = {c for c, _ in top_concepts}
        concept_score_map = dict(top_concepts)

        logger.info("CbIntradayEngine V2: top concepts: %s",
                    [(c, round(s, 1)) for c, s in top_concepts])

        # ── Step 2: Find CBs in strong concepts ──
        placeholders = ",".join(["%s"] * len(strong_concepts))
        query = f"""
        SELECT DISTINCT
            cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
            cb.remain_size, cb.newest_rating, cb.maturity_date, cb.conv_price,
            d.close, d.cb_over_rate, d.pct_chg, d.amount,
            cc.concept,
            sk.close AS stock_close
        FROM cb_concept cc
        JOIN cb_basic cb ON cc.ts_code = cb.ts_code
        LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
        LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code AND sk.trade_date = %s
        WHERE cc.concept IN ({placeholders})
          AND (cb.delist_date IS NULL OR cb.delist_date > %s::date)
        """
        params = [trade_date, trade_date] + list(strong_concepts) + [trade_date]
        cur.execute(query, params)
        rows = cur.fetchall()

        if not rows:
            logger.warning("CbIntradayEngine V2: no CBs in strong concepts %s", strong_concepts)
            return []

        # ── Pre-fetch: 强赎 risk ──
        call_risk_map = {}
        try:
            cur.execute(
                "SELECT ts_code, is_call, call_date, call_price, call_reg_date FROM cb_call "
                "WHERE call_date >= CURRENT_DATE - INTERVAL '30 days'"
            )
            for r in cur.fetchall():
                if r[0] not in call_risk_map:
                    call_risk_map[r[0]] = {"is_call": r[1], "call_date": r[2],
                                           "call_price": r[3], "call_reg_date": r[4]}
        except Exception:
            pass

        # ── Step 3: Score each CB ──
        picks = []
        for r in rows:
            try:
                (ts_code, name, stk_code_ts, stk_name,
                 remain_size, rating, maturity_date_, conv_price,
                 close, cb_over_rate, pct_chg, amount,
                 concept,
                 stock_close) = r

                # Calculate premium rate
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                # Concept strength score (40%)
                concept_raw = concept_score_map.get(concept, 0)
                concept_score = min(100, max(0, 50 + concept_raw * 5))

                # Premium score (35%)
                premium_score = self._premium_score(cb_over_rate)

                # Size score (25%)
                size_score = self._size_score(remain_size)

                # 强赎 penalty
                call_info = call_risk_map.get(ts_code, {})
                call_risk = "安全"
                call_penalty = 0.0
                if call_info.get("is_call") == "公告实施强赎":
                    call_risk = "强赎中"
                    reg_date = call_info.get("call_reg_date")
                    if reg_date:
                        if isinstance(reg_date, str):
                            reg_date = datetime.strptime(reg_date, "%Y-%m-%d").date()
                        days_to_reg = (reg_date - date.today()).days
                        if days_to_reg < 0:
                            continue
                        if days_to_reg <= 3:
                            call_risk = "强赎中(最后3天!)"
                            call_penalty = -20.0
                        elif days_to_reg <= 7:
                            call_penalty = -10.0
                        else:
                            call_penalty = -5.0

                total = concept_score * 0.40 + premium_score * 0.35 + size_score * 0.25 + call_penalty

                if total >= 75:
                    grade = "S"
                elif total >= 60:
                    grade = "A"
                elif total >= 45:
                    grade = "B"
                else:
                    grade = "C"

                picks.append({
                    "code": ts_code, "name": name or ts_code,
                    "stk_code": stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or ""),
                    "stk_name": stk_name,
                    "concept": concept,
                    "concept_strength": round(concept_raw, 2),
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "call_risk": call_risk,
                    "call_date": str(call_info.get("call_date")) if call_info.get("call_date") else None,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "concept_score": round(concept_score, 1),
                        "premium_score": round(premium_score, 1),
                        "size_score": round(size_score, 1),
                    },
                })
            except Exception as e:
                logger.debug("CB intraday %s failed: %s", r[0] if r else "?", e)
                continue

        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info("CbIntradayEngine V2: %d picks from %d CBs (%.1fs)", len(picks), len(rows), elapsed)
        return picks

    def _get_concept_strength(self, cur, trade_date: str) -> dict:
        """Get concept strength from ths_daily + auction sector data.

        Priority:
        1. Use auction data via stocks.industry → concept mapping
        2. Fallback: ths_daily concept plates
        """
        # Try auction → industry first
        try:
            cur.execute("""
                SELECT s.industry, AVG(
                    CASE WHEN ao.close > 0
                    THEN (ao.open - ao.close) / ao.close * 100
                    ELSE 0 END
                ) AS avg_pct
                FROM stk_auction_o ao
                JOIN stocks s ON ao.code = s.code
                WHERE ao.trade_date = %s AND s.industry IS NOT NULL AND s.industry != ''
                  AND ao.close > 0
                GROUP BY s.industry
                HAVING COUNT(*) >= 3
                ORDER BY avg_pct DESC
                LIMIT 15
            """, (trade_date,))
            industry_strength = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
            if industry_strength:
                # Map industries to concepts via cb_concept
                concept_scores = {}
                for industry, strength in industry_strength.items():
                    cur.execute(
                        "SELECT DISTINCT cc.concept FROM cb_concept cc "
                        "JOIN cb_basic cb ON cc.ts_code = cb.ts_code "
                        "JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code "
                        "WHERE s.industry = %s", (industry,))
                    for r in cur.fetchall():
                        concept = r[0]
                        concept_scores[concept] = max(concept_scores.get(concept, 0), strength)
                if concept_scores:
                    return concept_scores
        except Exception:
            pass

        # Fallback: ths_daily concept plates
        try:
            cur.execute(
                "SELECT name, AVG(pct_chg) FROM ths_daily "
                "WHERE trade_date = %s AND pct_chg IS NOT NULL "
                "GROUP BY name HAVING COUNT(*) >= 2 "
                "ORDER BY AVG(pct_chg) DESC LIMIT 15",
                (trade_date,),
            )
            return {r[0]: float(r[1] or 0) for r in cur.fetchall()}
        except Exception:
            pass

        return {}
