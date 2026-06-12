"""秋神竞价概念选债引擎 — 竞价强势正股 → 概念转债映射.

流水线:
  1. 秋神竞价选出强势正股 (复用 AuctionScalpEngine 核心逻辑)
  2. 通过 cb_basic 找到对应转债
  3. 通过 cb_concept 扩展同概念转债
  4. 溢价率 + 规模 + 概念强度 三维评分
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_auction")


class CbAuctionEngine:
    """秋神竞价概念选债引擎 — 竞价→正股→概念→转债."""

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
        return max(20.0, 54 - (size_yi - 3) * 10)

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute auction concept-driven CB selection.

        Pipeline:
          1. Auction strong stocks → concepts
          2. Concepts → CBs (direct + same-concept expansion)
          3. Score: premium + size + concept heat
        """
        t0 = time.time()
        cur = self.db.cursor()

        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            trade_date = str(row[0]) if row and row[0] else date.today().strftime("%Y-%m-%d")

        logger.info("CbAuctionEngine: auction date %s, top_n=%d", trade_date, top_n)

        # ── Step 1: Auction strong stocks → sectors → concepts ──
        try:
            cur.execute("""
                WITH auction_strength AS (
                    SELECT s.code, s.name, s.industry,
                           (ao.open - ao.close) / ao.close * 100 AS gap_pct,
                           ao.vol, ao.amount
                    FROM stk_auction_o ao
                    JOIN stocks s ON ao.code = s.code
                    WHERE ao.trade_date = %s AND ao.close > 0
                      AND s.name NOT LIKE '%%ST%%'
                    ORDER BY gap_pct DESC
                    LIMIT 50
                )
                SELECT *, gap_pct FROM auction_strength WHERE gap_pct > 0.5
            """, (trade_date,))
            auction_stocks = cur.fetchall()
        except Exception as e:
            logger.warning("CbAuctionEngine: auction query failed: %s", e)
            return []

        if not auction_stocks:
            logger.warning("CbAuctionEngine: no strong stocks in auction")
            return []

        # ── Step 2: Find CBs for these stocks + expand by concept ──
        strong_stock_codes = [r[0] for r in auction_stocks]
        strong_industries = list(set(r[2] for r in auction_stocks if r[2]))

        # Get auction scores: r = (code, name, industry, gap_pct, vol, amount, gap_pct_dup)
        auction_score_map = {}  # {stock_code: gap_pct}
        for r in auction_stocks:
            auction_score_map[r[0]] = float(r[3] or 0)  # gap_pct at index 3

        # Direct CBs: underlying stock is strong
        direct_cbs = {}  # {ts_code: {stock_score, is_direct}}
        if strong_stock_codes:
            placeholders = ",".join(["%s"] * len(strong_stock_codes))
            cur.execute(
                f"SELECT cb.ts_code, cb.stk_code, cb.bond_short_name, cb.stk_short_name "
                f"FROM cb_basic cb WHERE SPLIT_PART(cb.stk_code, '.', 1) IN ({placeholders})",
                strong_stock_codes,
            )
            for r in cur.fetchall():
                stk_raw = r[1].split(".")[0] if r[1] and "." in r[1] else r[1]
                score = auction_score_map.get(stk_raw, 1.0)
                direct_cbs[r[0]] = {
                    "stk_code": stk_raw, "name": r[2], "stk_name": r[3],
                    "stock_score": score, "is_direct": True,
                }

        # Concept expansion: same-concept CBs
        concept_cbs = {}  # {ts_code: {concept, concept_strength}}
        try:
            # Find concepts of auction-strong industries
            if strong_industries:
                ind_placeholders = ",".join(["%s"] * len(strong_industries))
                cur.execute(
                    f"SELECT DISTINCT cc.concept FROM cb_concept cc "
                    f"JOIN cb_basic cb ON cc.ts_code = cb.ts_code "
                    f"JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code "
                    f"WHERE s.industry IN ({ind_placeholders})",
                    strong_industries,
                )
                hot_concepts = [r[0] for r in cur.fetchall()]
            else:
                hot_concepts = []

            # Also add concepts directly from strong stocks
            if strong_stock_codes:
                cur.execute(
                    f"SELECT DISTINCT cc.concept FROM cb_concept cc "
                    f"JOIN cb_basic cb ON cc.ts_code = cb.ts_code "
                    f"WHERE SPLIT_PART(cb.stk_code, '.', 1) IN ({placeholders})",
                    strong_stock_codes,
                )
                hot_concepts.extend([r[0] for r in cur.fetchall()])
            hot_concepts = list(set(hot_concepts))

            if hot_concepts:
                cp_placeholders = ",".join(["%s"] * len(hot_concepts))
                cur.execute(
                    f"SELECT cc.ts_code, cc.concept, cb.bond_short_name, cb.stk_code, cb.stk_short_name "
                    f"FROM cb_concept cc JOIN cb_basic cb ON cc.ts_code = cb.ts_code "
                    f"WHERE cc.concept IN ({cp_placeholders})",
                    hot_concepts,
                )
                for r in cur.fetchall():
                    cb_code = r[0]
                    if cb_code not in direct_cbs and cb_code not in concept_cbs:
                        concept_cbs[cb_code] = {
                            "concept": r[1], "name": r[2],
                            "stk_code": r[3].split(".")[0] if r[3] and "." in r[3] else r[3],
                            "stk_name": r[4], "is_direct": False,
                        }
        except Exception as e:
            logger.debug("Concept expansion failed: %s", e)

        # Merge all CBs
        all_cb_codes = list(set(list(direct_cbs.keys()) + list(concept_cbs.keys())))
        if not all_cb_codes:
            return []

        # ── Step 3: Fetch CB details + score ──
        cb_placeholders = ",".join(["%s"] * len(all_cb_codes))
        cur.execute(f"""
            SELECT cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
                   cb.remain_size, cb.conv_price, cb.newest_rating,
                   d.close, d.cb_over_rate,
                   sk.close AS stock_close
            FROM cb_basic cb
            LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
            LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code AND sk.trade_date = %s
            WHERE cb.ts_code IN ({cb_placeholders})
        """, [trade_date, trade_date] + all_cb_codes)
        cb_details = cur.fetchall()

        # ── 强赎 risk ──
        call_risk_map = {}
        try:
            cur.execute(
                "SELECT ts_code, is_call, call_date, call_reg_date FROM cb_call "
                "WHERE call_date >= CURRENT_DATE - INTERVAL '30 days'"
            )
            for r in cur.fetchall():
                if r[0] not in call_risk_map:
                    call_risk_map[r[0]] = {"is_call": r[1], "call_date": r[2], "call_reg_date": r[3]}
        except Exception:
            pass

        # ── Score ──
        picks = []
        for r in cb_details:
            try:
                ts_code, name, stk_code_ts, stk_name = r[0], r[1], r[2], r[3]
                remain_size, conv_price = r[4], r[5]
                close, cb_over_rate = r[7], r[8]
                stock_close = r[9]

                stk_raw = stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or "")

                # Get auction/stock score
                direct_info = direct_cbs.get(ts_code, {})
                concept_info = concept_cbs.get(ts_code, {})

                # Direct CBs get higher stock score weight
                is_direct = direct_info.get("is_direct", False)
                stock_score_raw = direct_info.get("stock_score", 0)
                if not is_direct:
                    stock_score_raw = stock_score_raw * 0.6  # concept expansion gets 60% weight

                stock_score = min(100, max(0, 50 + stock_score_raw * 8))

                # Premium rate
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                premium_score = self._premium_score(cb_over_rate)
                size_score = self._size_score(remain_size)

                # 强赎
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

                # Weighted: 竞价强度 35% + 溢价率 35% + 规模 20% + 直接映射 10%
                total = stock_score * 0.35 + premium_score * 0.35 + size_score * 0.20
                if is_direct:
                    total += 10  # Bonus for direct auction→CB mapping
                total += call_penalty

                if total >= 75:
                    grade = "S"
                elif total >= 60:
                    grade = "A"
                elif total >= 45:
                    grade = "B"
                else:
                    grade = "C"

                concept_tag = direct_info.get("concept_name", concept_info.get("concept", ""))

                picks.append({
                    "code": ts_code,
                    "name": name or ts_code,
                    "stk_code": stk_raw,
                    "stk_name": stk_name,
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "is_direct": is_direct,
                    "auction_score": round(stock_score_raw, 2),
                    "call_risk": call_risk,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "stock_score": round(stock_score, 1),
                        "premium_score": round(premium_score, 1),
                        "size_score": round(size_score, 1),
                    },
                })
            except Exception as e:
                logger.debug("CB auction %s failed: %s", r[0] if r else "?", e)
                continue

        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info("CbAuctionEngine: %d picks (%d direct) from %d CBs (%.1fs)",
                    len(picks), sum(1 for p in picks if p.get("is_direct")), len(cb_details), elapsed)

        return picks
