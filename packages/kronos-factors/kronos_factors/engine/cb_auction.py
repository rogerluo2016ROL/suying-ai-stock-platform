"""匪爷竞价选债模型 V5 — 自适应止盈 + 大盘感知 + 数据修复 + 可配权重.

流水线:
  1. stk_auction_o 竞价 Top 100 → cb_sector/ths_member/cb_concept → 概念聚合
  2. 强势概念 → 转债候选池
  3. 硬过滤: 规模<10亿 + 正股竞价>0.5% + 退市>15天
  4. ATR自适应止盈 + 大盘环境感知 + 强赎感知溢价率
  5. 输出: suggested_entry + take_profit(ATR) + stop_loss(market-aware)
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_auction")


class CbAuctionEngine:
    """匪爷竞价选债引擎 V5 — 自适应止盈止损."""

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

    @staticmethod
    def _adaptive_tp(stock_atr_pct: float, market_change: float) -> tuple:
        """自适应止盈止损 — 基于正股ATR和大盘环境.

        Args:
            stock_atr_pct: 正股近5日平均振幅(%)
            market_change: 上证当日涨跌幅(%)

        Returns:
            (tp_pct, sl_pct) 止盈/止损百分比
        """
        # 基础参数
        if stock_atr_pct and stock_atr_pct > 0:
            # ATR 2% → TP 1.5%, ATR 5% → TP 2.5%
            tp_base = 1.0 + stock_atr_pct * 0.3
            sl_base = -tp_base  # 对称
        else:
            tp_base, sl_base = 1.5, -1.5

        # 大盘调整
        if market_change is not None:
            if market_change < -1.0:
                # 熊市: 止损收紧, 止盈放宽(跌市反弹空间大)
                sl_base = max(-1.0, sl_base + 0.5)
                tp_base = min(3.0, tp_base + 0.5)
            elif market_change > 0.5:
                # 牛市: 止损放宽, 止盈适度(趋势延续)
                sl_base = min(-2.0, sl_base - 0.5)
                tp_base = min(3.0, tp_base - 0.2)

        return round(tp_base, 1), round(sl_base, 1)

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """竞价选债 V5.

        Args:
            top_n: 最大返回数
            trade_date: 交易日 (YYYY-MM-DD)
            w_concept: 概念权重 (默认0.40)
            w_premium: 溢价率权重 (默认0.40)
            w_gap: 竞价权重 (默认0.20)
        """
        t0 = time.time()
        cur = self.db.cursor()

        # 可配置权重
        w_concept = kwargs.get("w_concept", 0.40)
        w_premium = kwargs.get("w_premium", 0.40)
        w_gap = kwargs.get("w_gap", 0.20)

        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            trade_date = str(row[0]) if row and row[0] else date.today().strftime("%Y-%m-%d")

        cur.execute("SELECT MAX(trade_date) FROM cb_daily")
        row = cur.fetchone()
        daily_date = str(row[0]) if row and row[0] else trade_date

        # ── 大盘环境 ──
        market_change = None
        try:
            cur.execute("SELECT change_pct FROM index_daily WHERE code='000001' AND trade_date=%s",
                        (daily_date,))
            row = cur.fetchone()
            if row and row[0] is not None:
                market_change = float(row[0])
        except Exception:
            pass

        logger.info("CbAuctionEngine V5: auction=%s daily=%s market=%s top_n=%d w=%.0f/%.0f/%.0f",
                    trade_date, daily_date,
                    f"{market_change:+.1f}%" if market_change else "N/A",
                    top_n, w_concept*100, w_premium*100, w_gap*100)

        # ── Step 1: 竞价 Top 100 → 概念聚合 ──
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
                SELECT DISTINCT t.code, t.gap_pct, s.sector_name AS sector
                FROM top100 t
                JOIN cb_basic b ON SPLIT_PART(b.stk_code, '.', 1) = t.code
                JOIN cb_sector s ON b.ts_code = s.ts_code
                WHERE t.gap_pct > 0
                UNION ALL
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
                SELECT DISTINCT t.code, t.gap_pct, cc.concept AS sector
                FROM top100 t
                JOIN cb_basic b ON SPLIT_PART(b.stk_code, '.', 1) = t.code
                JOIN cb_concept cc ON b.ts_code = cc.ts_code
                LEFT JOIN cb_sector s ON b.ts_code = s.ts_code
                WHERE t.gap_pct > 0 AND s.ts_code IS NULL
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
            logger.warning("CbAuctionEngine V5: no strong concepts")
            return []

        concept_strength = {}
        for concept, avg_gap, cnt in concept_rows:
            concept_strength[concept] = self._concept_strength(float(avg_gap), cnt)

        # ── Step 2: 强势概念 → 转债 ──
        strong_concepts = list(concept_strength.keys())
        cp_holders = ",".join(["%s"] * len(strong_concepts))

        cur.execute(f"""
            SELECT b.ts_code, b.bond_short_name, b.stk_code, b.stk_short_name,
                   b.remain_size, b.conv_price, src.sector,
                   (ao.open - ao.close) / NULLIF(ao.close, 0) * 100 AS stock_gap,
                   ao.open AS stock_auction_open
            FROM (
                SELECT s.ts_code, s.sector_name AS sector FROM cb_sector s
                WHERE s.sector_name IN ({cp_holders})
                UNION ALL
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
            logger.warning("CbAuctionEngine V5: no CBs in strong sectors")
            return []

        # 板块细分度
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
                if r[0] not in concept_size or r[1] < concept_size[r[0]]:
                    concept_size[r[0]] = r[1]
        except Exception:
            pass

        # 取最细分板块
        cb_best = {}
        stock_codes = set()
        for r in cb_rows:
            ts_code, name, stk_code_ts, stk_name = r[0], r[1], r[2], r[3]
            remain_size, conv_price = r[4], r[5]
            sector = r[6]
            stock_gap = float(r[7]) if r[7] else 0.0
            stock_ao = float(r[8]) if r[8] else None
            cs_val = concept_strength.get(sector, 0)
            sz_val = concept_size.get(sector, 9999)

            stk_raw = stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or "")
            stock_codes.add(stk_raw)

            if ts_code not in cb_best or sz_val < cb_best[ts_code].get("concept_size", 9999):
                cb_best[ts_code] = {
                    "name": name, "stk_code": stk_raw, "stk_name": stk_name,
                    "remain_size": remain_size, "conv_price": conv_price,
                    "sector": sector, "concept_score": cs_val,
                    "stock_gap": stock_gap, "concept_size": sz_val,
                    "stock_ao": stock_ao,
                }

        cb_codes = list(cb_best.keys())

        # ── Pre-fetch: cb_daily ──
        cb_phs = ",".join(["%s"] * len(cb_codes))
        cur.execute(f"""
            SELECT b.ts_code, d.open, d.close, d.cb_over_rate, d.amount,
                   sk.close AS stock_close
            FROM cb_basic b
            LEFT JOIN cb_daily d ON b.ts_code = d.ts_code AND d.trade_date = %s
            LEFT JOIN daily_kline sk ON SPLIT_PART(b.stk_code, '.', 1) = sk.code
                AND sk.trade_date = %s
            WHERE b.ts_code IN ({cb_phs})
        """, [daily_date, daily_date] + cb_codes)
        daily_map = {}
        for ts_code, cb_open, close, cb_over_rate, amount, stock_close in cur.fetchall():
            daily_map[ts_code] = {
                "cb_open": cb_open, "close": close, "cb_over_rate": cb_over_rate,
                "amount": amount, "stock_close": stock_close,
            }

        # ── Pre-fetch: ATR (正股近5日平均振幅) ──
        stock_atr_map = {}
        if stock_codes:
            sc_phs = ",".join(["%s"] * len(stock_codes))
            try:
                cur.execute(f"""
                    SELECT code, AVG((high-low)/NULLIF(close,0)*100)
                    FROM (
                        SELECT code, high, low, close,
                               ROW_NUMBER() OVER (PARTITION BY code ORDER BY trade_date DESC) AS rn
                        FROM daily_kline
                        WHERE code IN ({sc_phs}) AND trade_date < %s
                    ) sub WHERE rn <= 5
                    GROUP BY code
                """, list(stock_codes) + [trade_date])
                for r in cur.fetchall():
                    stock_atr_map[r[0]] = float(r[1]) if r[1] else None
            except Exception:
                pass

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

        # ── Step 3: 评分 + 自适应止盈 ──
        picks = []
        for ts_code, info in cb_best.items():
            try:
                daily = daily_map.get(ts_code, {})
                cb_open = daily.get("cb_open")
                close = daily.get("close")
                cb_over_rate = daily.get("cb_over_rate")
                amount = daily.get("amount")
                stock_close = daily.get("stock_close")
                conv_price = info["conv_price"]
                remain_size = info["remain_size"]
                stock_gap = info["stock_gap"]
                sector = info["sector"]
                stk_code = info["stk_code"]

                # 溢价率
                if cb_over_rate is None and conv_price and stock_close and close \
                        and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                # 数据修复: cb_daily.open 缺失时, 用正股竞价开盘价估算
                if cb_open is None and info.get("stock_ao"):
                    stock_ao = info["stock_ao"]
                    if conv_price and conv_price > 0 and stock_close:
                        conv_value = 100.0 / float(conv_price) * float(stock_close) if stock_close else 100.0
                        if cb_over_rate is not None:
                            estimated_cb_open = conv_value * (1 + cb_over_rate / 100)
                        else:
                            estimated_cb_open = conv_value
                        cb_open = estimated_cb_open

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

                # 评分
                gap_score = min(100.0, max(0.0, stock_gap * 20.0))
                premium_score = self._premium_score(cb_over_rate, call_status)
                gap_factor = max(0.0, min(1.0, stock_gap / 3.0))
                sector_score = info["concept_score"] * gap_factor
                total = sector_score * w_concept + premium_score * w_premium + gap_score * w_gap

                if total >= 75:    grade = "S"
                elif total >= 60:  grade = "A"
                elif total >= 45:  grade = "B"
                else:              grade = "C"

                # ── 自适应止盈止损 ──
                stock_atr = stock_atr_map.get(stk_code)
                tp_pct, sl_pct = self._adaptive_tp(stock_atr, market_change)

                # 建议买入价: 开盘-0.5%限价单 (cb_daily有同日数据的用实际价, 否则用估算价)
                if cb_open:
                    suggested_entry = round(cb_open * 0.995, 2)
                    market_entry = round(cb_open, 2)
                    take_profit = round(suggested_entry * (1 + tp_pct / 100), 2)
                    stop_loss = round(suggested_entry * (1 + sl_pct / 100), 2)
                else:
                    suggested_entry = None
                    market_entry = None
                    take_profit = None
                    stop_loss = None

                picks.append({
                    "code": ts_code,
                    "name": info["name"] or ts_code,
                    "stk_code": stk_code,
                    "stk_name": info["stk_name"],
                    "sector": sector,
                    "price": round(close, 2) if close else None,
                    "market_entry": market_entry,
                    "suggested_entry": suggested_entry,
                    "take_profit": take_profit,
                    "stop_loss": stop_loss,
                    "tp_pct": tp_pct,
                    "sl_pct": sl_pct,
                    "stock_atr": round(stock_atr, 1) if stock_atr else None,
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
                        "tp_pct": tp_pct,
                        "sl_pct": sl_pct,
                        "stock_atr": round(stock_atr, 1) if stock_atr else None,
                        "market": round(market_change, 1) if market_change is not None else None,
                    },
                })

            except Exception as e:
                logger.debug("CB %s failed: %s", ts_code, e)
                continue

        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info("CbAuctionEngine V5: %d picks from %d CBs in %d concepts (%.1fs)",
                    len(picks), len(cb_best), len(concept_strength), elapsed)

        return picks
