"""匪爷竞价选债模型 V4 — 竞价股票→同花顺概念聚合→转债映射.

流水线:
  1. stk_auction_o 竞价 Top 100 → ths_member → 概念聚合
  2. 强势概念 → cb_concept → 转债候选池
  3. 硬过滤: 规模<10亿 + 正股竞价>0.5% + 退市>15天
  4. 溢价率评分(强赎感知) + 竞价强度 × 板块分 → 综合排序
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_auction")


class CbAuctionEngine:
    """匪爷竞价选债引擎 V4 — 概念聚合 + 转债直选."""

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

    # ── Factor scoring ──

    @staticmethod
    def _premium_score(premium_rate: float, call_status: str = None) -> float:
        """溢价率评分 — 强赎状态感知."""
        if premium_rate is None:
            return 50.0

        if call_status == '公告不强赎':
            if premium_rate <= 0:    return 100.0
            if premium_rate <= 15:   return 100.0 - premium_rate * 1.33
            if premium_rate <= 30:   return 80.0 - (premium_rate - 15) * 2.0
            if premium_rate <= 50:   return 50.0 - (premium_rate - 30) * 1.25
            return max(15.0, 25.0 - (premium_rate - 50) * 0.2)

        elif call_status == '公告实施强赎':
            if premium_rate <= 0:    return 100.0
            if premium_rate <= 3:    return 100.0 - premium_rate * 6.67
            if premium_rate <= 10:   return 80.0 - (premium_rate - 3) * 7.14
            if premium_rate <= 20:   return 30.0 - (premium_rate - 10) * 2.5
            return 0.0

        elif call_status in ('已满足强赎条件', '公告提示强赎'):
            if premium_rate <= 0:    return 100.0
            if premium_rate <= 5:    return 100.0 - premium_rate * 3.0
            if premium_rate <= 15:   return 85.0 - (premium_rate - 5) * 4.0
            if premium_rate <= 25:   return 45.0 - (premium_rate - 15) * 3.5
            if premium_rate <= 40:   return max(5.0, 10.0 - (premium_rate - 25) * 0.33)
            return 0.0

        else:
            if premium_rate <= 0:    return 100.0
            if premium_rate <= 5:    return 100.0 - premium_rate * 3.0
            if premium_rate <= 15:   return 85.0 - (premium_rate - 5) * 3.0
            if premium_rate <= 25:   return 55.0 - (premium_rate - 15) * 3.0
            if premium_rate <= 50:   return 25.0 - (premium_rate - 25) * 0.8
            return 0.0

    @staticmethod
    def _concept_strength(avg_gap: float, stock_cnt: int) -> float:
        """概念强度: 竞价涨幅 + 上榜股票数."""
        if avg_gap <= 0:
            return 0.0
        return min(100.0, avg_gap * 12.0 + stock_cnt * 1.5)

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        t0 = time.time()
        cur = self.db.cursor()

        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            trade_date = str(row[0]) if row and row[0] else date.today().strftime("%Y-%m-%d")

        cur.execute("SELECT MAX(trade_date) FROM cb_daily")
        row = cur.fetchone()
        daily_date = str(row[0]) if row and row[0] else trade_date

        logger.info("CbAuctionEngine V4: auction=%s, daily=%s, top_n=%d",
                    trade_date, daily_date, top_n)

        # ── Step 1: 竞价 Top 100 → 正股→转债→板块聚合 (用cb_sector) ──
        cur.execute("""
            WITH top100 AS (
                SELECT ao.code,
                       (ao.open - ao.close) / NULLIF(ao.close, 0) * 100 AS gap_pct
                FROM stk_auction_o ao
                JOIN stocks s ON ao.code = s.code
                WHERE ao.trade_date = %s AND ao.close > 0
                  AND s.name NOT LIKE '%%ST%%'
                ORDER BY gap_pct DESC LIMIT 100
            ),
            stock_sector AS (
                -- 路径1: cb_sector 用户板块
                SELECT DISTINCT t.code, t.gap_pct, s.sector_name AS sector
                FROM top100 t
                JOIN cb_basic b ON SPLIT_PART(b.stk_code, '.', 1) = t.code
                JOIN cb_sector s ON b.ts_code = s.ts_code
                WHERE t.gap_pct > 0
                UNION ALL
                -- 路径2: ths_member 概念 (正股→同花顺概念, 即使没有转债也能识别板块热度)
                SELECT DISTINCT t.code, t.gap_pct, i.name AS sector
                FROM top100 t
                JOIN ths_member m ON m.con_code LIKE t.code || '.%%'
                JOIN ths_index i ON m.ts_code = i.ts_code
                WHERE t.gap_pct > 0
                  AND LEFT(m.ts_code, 3) IN ('881','882','883','884','885','886')
                  AND i.name NOT LIKE '%%同花顺%%' AND i.name NOT LIKE '%%(A股)%%'
                  AND i.name NOT LIKE '%%昨日%%' AND i.name NOT LIKE '%%百日%%'
                  AND i.name NOT LIKE '%%首板%%' AND i.name NOT LIKE '%%重仓%%'
                  AND i.name NOT LIKE '%%新高%%' AND i.name NOT LIKE '%%减持%%'
                  AND i.name NOT LIKE '%%盈利%%' AND i.name NOT LIKE '%%股息%%'
                  AND i.name NOT LIKE '%%估值%%' AND i.name NOT LIKE '%%动量%%'
                  AND i.name NOT LIKE '%%大盘%%' AND i.name NOT LIKE '%%小盘%%'
                  AND i.name NOT IN ('浙江','江苏','广东','上海','北京','深圳','山东','福建','安徽','四川','湖北','湖南','河南','河北')
                UNION ALL
                -- 路径3: cb_concept 补充 (不在前两条路径中的转债)
                SELECT DISTINCT t.code, t.gap_pct, cc.concept AS sector
                FROM top100 t
                JOIN cb_basic b ON SPLIT_PART(b.stk_code, '.', 1) = t.code
                JOIN cb_concept cc ON b.ts_code = cc.ts_code
                LEFT JOIN cb_sector s ON b.ts_code = s.ts_code
                WHERE t.gap_pct > 0
                  AND s.ts_code IS NULL
                  AND cc.concept NOT LIKE '%%同花顺%%' AND cc.concept NOT LIKE '%%(A股)%%'
                  AND cc.concept NOT LIKE '%%昨日%%' AND cc.concept NOT LIKE '%%百日%%'
                  AND cc.concept NOT LIKE '%%首板%%' AND cc.concept NOT LIKE '%%重仓%%'
                  AND cc.concept NOT LIKE '%%新高%%' AND cc.concept NOT LIKE '%%减持%%'
                  AND cc.concept NOT LIKE '%%盈利%%' AND cc.concept NOT LIKE '%%股息%%'
                  AND cc.concept NOT LIKE '%%估值%%' AND cc.concept NOT LIKE '%%动量%%'
                  AND cc.concept NOT LIKE '%%均衡%%' AND cc.concept NOT LIKE '%%大盘%%'
                  AND cc.concept NOT LIKE '%%主板%%' AND cc.concept NOT LIKE '%%全A%%'
                  AND cc.concept NOT IN ('浙江','江苏','广东','上海','北京','深圳','山东','福建','安徽','四川','湖北','湖南','河南','河北')
            )
            SELECT sector,
                   AVG(gap_pct) AS avg_gap,
                   COUNT(DISTINCT code) AS stock_cnt
            FROM stock_sector
            GROUP BY sector
            HAVING COUNT(DISTINCT code) >= 1
            ORDER BY avg_gap DESC
        """, (trade_date,))
        concept_rows = cur.fetchall()

        if not concept_rows:
            logger.warning("CbAuctionEngine V4: no strong concepts in auction top 100")
            return []

        concept_strength = {}
        for concept, avg_gap, cnt in concept_rows:
            concept_strength[concept] = self._concept_strength(float(avg_gap), cnt)

        top_c = sorted(concept_strength.items(), key=lambda x: x[1], reverse=True)
        logger.info("CbAuctionEngine V4: top concepts: %s",
                    [(c[:20], round(s, 1)) for c, s in top_c[:12]])

        # ── Step 2: 强势概念 → 转债 + 正股竞价筛选 ──
        strong_concepts = list(concept_strength.keys())
        cp_holders = ",".join(["%s"] * len(strong_concepts))

        cur.execute(f"""
            SELECT b.ts_code, b.bond_short_name, b.stk_code, b.stk_short_name,
                   b.remain_size, b.conv_price, src.sector,
                   (ao.open - ao.close) / NULLIF(ao.close, 0) * 100 AS stock_gap
            FROM (
                -- 主路径: cb_sector
                SELECT s.ts_code, s.sector_name AS sector FROM cb_sector s
                WHERE s.sector_name IN ({cp_holders})
                UNION ALL
                -- 补充: cb_concept (不在cb_sector中的转债)
                SELECT cc.ts_code, cc.concept AS sector FROM cb_concept cc
                LEFT JOIN cb_sector s ON cc.ts_code = s.ts_code
                WHERE cc.concept IN ({cp_holders}) AND s.ts_code IS NULL
            ) src
            JOIN cb_basic b ON src.ts_code = b.ts_code
            JOIN stk_auction_o ao ON ao.code = SPLIT_PART(b.stk_code, '.', 1)
                                  AND ao.trade_date = %s
            WHERE (b.delist_date IS NULL OR b.delist_date > CURRENT_DATE + INTERVAL '15 days')
              AND b.remain_size < 10e8
              AND b.cb_type = 'CB'
              AND b.bond_short_name NOT LIKE '%%定%%'
              AND ao.close > 0
              AND (ao.open - ao.close) / NULLIF(ao.close, 0) * 100 > 0.5
            ORDER BY b.ts_code
        """, strong_concepts + strong_concepts + [trade_date])
        cb_rows = cur.fetchall()

        if not cb_rows:
            logger.warning("CbAuctionEngine V4: no CBs in strong sectors")
            return []

        # 每个板块的转债数 (越小越细分, 两个来源)
        concept_size = {}
        try:
            cur.execute(f"""
                SELECT sector_name AS name, COUNT(*) FROM cb_sector
                WHERE sector_name IN ({cp_holders}) GROUP BY sector_name
                UNION ALL
                SELECT concept AS name, COUNT(*) FROM cb_concept
                WHERE concept IN ({cp_holders}) GROUP BY concept
            """, strong_concepts + strong_concepts)
            for r in cur.fetchall():
                # 取最小值 (优先cb_sector的精确分类)
                if r[0] not in concept_size or r[1] < concept_size[r[0]]:
                    concept_size[r[0]] = r[1]
        except Exception:
            pass

        # 每个转债取最细分的板块 (cb_sector成员数最少 = 最精准)
        cb_best = {}
        for r in cb_rows:
            ts_code, name, stk_code_ts, stk_name = r[0], r[1], r[2], r[3]
            remain_size, conv_price = r[4], r[5]
            sector = r[6]
            stock_gap = float(r[7]) if r[7] else 0.0
            cs = concept_strength.get(sector, 0)
            sz = concept_size.get(sector, 9999)

            if ts_code not in cb_best or sz < cb_best[ts_code].get("concept_size", 9999):
                stk_raw = stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or "")
                cb_best[ts_code] = {
                    "name": name, "stk_code": stk_raw, "stk_name": stk_name,
                    "remain_size": remain_size, "conv_price": conv_price,
                    "sector": sector, "concept_score": cs,
                    "stock_gap": stock_gap, "concept_size": sz,
                }

        cb_codes = list(cb_best.keys())

        # ── Pre-fetch: cb_daily + stock close ──
        cb_phs = ",".join(["%s"] * len(cb_codes))
        cur.execute(f"""
            SELECT b.ts_code, d.close, d.cb_over_rate, d.amount,
                   sk.close AS stock_close
            FROM cb_basic b
            LEFT JOIN cb_daily d ON b.ts_code = d.ts_code AND d.trade_date = %s
            LEFT JOIN daily_kline sk ON SPLIT_PART(b.stk_code, '.', 1) = sk.code
                AND sk.trade_date = %s
            WHERE b.ts_code IN ({cb_phs})
        """, [daily_date, daily_date] + cb_codes)
        daily_map = {}
        for ts_code, close, cb_over_rate, amount, stock_close in cur.fetchall():
            daily_map[ts_code] = {
                "close": close, "cb_over_rate": cb_over_rate,
                "amount": amount, "stock_close": stock_close,
            }

        # ── Pre-fetch: 强赎 ──
        call_status_map = {}
        try:
            cur.execute("""
                SELECT DISTINCT ON (ts_code)
                    ts_code, is_call, call_date, call_reg_date
                FROM cb_call ORDER BY ts_code, ann_date DESC
            """)
            for r in cur.fetchall():
                call_status_map[r[0]] = {
                    "is_call": r[1], "call_date": r[2], "call_reg_date": r[3],
                }
        except Exception:
            pass

        # ── Step 3: 评分 ──
        picks = []
        for ts_code, info in cb_best.items():
            try:
                daily = daily_map.get(ts_code, {})
                close = daily.get("close")
                cb_over_rate = daily.get("cb_over_rate")
                amount = daily.get("amount")
                stock_close = daily.get("stock_close")
                conv_price = info["conv_price"]
                remain_size = info["remain_size"]
                stock_gap = info["stock_gap"]
                sector = info["sector"]

                # 溢价率
                if cb_over_rate is None and conv_price and stock_close and close \
                        and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                # 强赎
                call_info = call_status_map.get(ts_code, {})
                call_status = call_info.get("is_call", "")
                call_risk = "安全"
                skip = False
                if call_status == "公告实施强赎":
                    call_risk = "强赎中"
                    reg_date = call_info.get("call_reg_date")
                    if reg_date:
                        if isinstance(reg_date, str):
                            reg_date = datetime.strptime(reg_date, "%Y-%m-%d").date()
                        days_to_reg = (reg_date - date.today()).days
                        if days_to_reg < 0:
                            skip = True
                        elif days_to_reg <= 3:
                            call_risk = "强赎中(最后3天!)"
                        elif days_to_reg <= 7:
                            call_risk = "强赎中(7天内)"
                elif call_status == "公告提示强赎":
                    call_risk = "提示强赎"
                elif call_status == "已满足强赎条件":
                    call_risk = "已满足强赎条件"
                elif call_status == "公告不强赎":
                    call_risk = "不强赎"
                elif call_status == "公告到期赎回":
                    call_risk = "到期赎回"
                if skip:
                    continue

                # 竞价强度分: gap>5%=100, gap=2%=40
                gap_score = min(100.0, max(0.0, stock_gap * 20.0))

                # 溢价率分
                premium_score = self._premium_score(cb_over_rate, call_status)

                # 板块分 (竞价强度折扣: gap≥3%满分, gap<3%打折)
                gap_factor = max(0.0, min(1.0, stock_gap / 3.0))
                sector_score = info["concept_score"] * gap_factor

                # 综合: 概念40% + 溢价40% + 竞价20%
                total = sector_score * 0.40 + premium_score * 0.40 + gap_score * 0.20

                if total >= 75:    grade = "S"
                elif total >= 60:  grade = "A"
                elif total >= 45:  grade = "B"
                else:              grade = "C"

                picks.append({
                    "code": ts_code,
                    "name": info["name"] or ts_code,
                    "stk_code": info["stk_code"],
                    "stk_name": info["stk_name"],
                    "sector": sector,
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "stock_gap": round(stock_gap, 2),
                    "call_risk": call_risk,
                    "call_status": call_status,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "concept_score": round(sector_score, 1),
                        "gap_score": round(gap_score, 1),
                        "premium_score": round(premium_score, 1),
                        "premium_rate": round(cb_over_rate, 1) if cb_over_rate else None,
                        "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                        "call_status": call_status,
                    },
                })

            except Exception as e:
                logger.debug("CB %s failed: %s", ts_code, e)
                continue

        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info("CbAuctionEngine V4: %d picks from %d CBs in %d concepts (%.1fs)",
                    len(picks), len(cb_best), len(concept_strength), elapsed)

        return picks
