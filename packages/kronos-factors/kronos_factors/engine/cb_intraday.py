"""匪爷可转债日内竞价选债模型 V6.1 — 趋势追随+均值回归混合.

V6.1: 回退动量评分到趋势追随(温和上涨最高分), 保留V6的ML≥2.0+溢价惩罚

因子权重 V6.1:
  1. 转债流动性 (35%) + 昨日动量 (30%) + 板块竞价 (20%) + 溢价率 (15%)
  + 下修加分 + 强赎惩罚 + ML重排(≥2.0) + 阈值过滤
"""

import logging
import os
import pickle
import time
import numpy as np
from datetime import date, datetime

logger = logging.getLogger("screener.cb_intraday")


class CbIntradayEngine:
    """匪爷可转债日内竞价选债模型 V5 — ML增强版."""

    _ensemble_models = None  # class-level cache for ML models

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

    # ── Factor scoring helpers ──

    @staticmethod
    def _premium_score(premium_rate: float) -> float:
        """V6: 溢价率线性惩罚. 折价越高越好, 高溢价强惩罚."""
        if premium_rate is None:
            return 50.0
        if premium_rate <= -10:
            return 100.0
        if premium_rate <= -5:
            return 95 + (premium_rate + 10) * 1.0
        if premium_rate <= 0:
            return 85 + premium_rate * 2.0
        if premium_rate <= 20:
            return 85 - premium_rate * 3.0     # 20%溢价→25分
        if premium_rate <= 50:
            return 25 - (premium_rate - 20) * 0.7  # 50%溢价→4分
        return max(1.0, 4 - (premium_rate - 50) * 0.05)  # >50%→接近0分

    @staticmethod
    def _yesterday_momentum_score(pct_chg: float) -> float:
        """V6.1: 趋势追随 + 均值回归混合.

        Args:
            pct_chg: T-1 涨跌幅(%)

        Returns:
            0-100. 温和上涨最佳(趋势健康), 极端涨跌不入.
        """
        if pct_chg is None:
            return 50.0
        # 昨涨>5%: 追高风险, 不入
        if pct_chg > 5:
            return 0.0
        # 理想: 1-5%温和上涨 (趋势健康, 非一日游)
        if 1 <= pct_chg <= 5:
            return 80 + (pct_chg - 1) * 5    # 85-100
        # 微涨0-1%: 中性偏正
        if 0 <= pct_chg < 1:
            return 55 + pct_chg * 25          # 55-80
        # 微跌-1~0%: 可接受
        if -1 <= pct_chg < 0:
            return 40 + (pct_chg + 1) * 15   # 40-55
        # 中跌-3~-1%: 均值回归机会, 给中等分
        if -3 <= pct_chg < -1:
            return 30 + (pct_chg + 3) * 5    # 30-40
        # 大跌<-3%: 可能有雷, 低分
        return max(10.0, 25 + (pct_chg + 3) * 2)

    @staticmethod
    def _liquidity_score(daily_amount: float, avg_amount_5d: float) -> float:
        """转债流动性评分: T-1 绝对成交额 + 相对5日均量.

        Args:
            daily_amount: T-1 成交额(元)
            avg_amount_5d: 近5日均成交额(元)

        Returns:
            0-100 评分, 流动性越好越容易日内进出
        """
        if daily_amount is None or daily_amount <= 0:
            return 20.0  # 无成交数据, 低分惩罚

        amount_wan = daily_amount / 1e4  # 万元
        # 1. 绝对成交额 (60%): 日成交100万以下难以日内进出
        if amount_wan >= 5000:
            abs_score = 100.0
        elif amount_wan >= 1000:
            abs_score = 80 + (amount_wan - 1000) / 4000 * 20
        elif amount_wan >= 500:
            abs_score = 65 + (amount_wan - 500) / 500 * 15
        elif amount_wan >= 100:
            abs_score = 40 + (amount_wan - 100) / 400 * 25
        elif amount_wan >= 50:
            abs_score = 20 + (amount_wan - 50) / 50 * 20
        else:
            abs_score = max(5.0, amount_wan * 0.4)

        # 2. 相对均量 (40%): 量能稳定度
        if avg_amount_5d and avg_amount_5d > 0:
            ratio = daily_amount / avg_amount_5d
            if ratio >= 1.2:
                rel_score = 80 + min(20, (ratio - 1.2) * 20)  # 放量, 上限100
            elif ratio >= 0.8:
                rel_score = 60 + (ratio - 0.8) * 50           # 正常 60-80
            elif ratio >= 0.5:
                rel_score = 30 + (ratio - 0.5) * 100          # 缩量 30-60
            else:
                rel_score = max(5.0, ratio * 60)              # 严重缩量
        else:
            rel_score = 50.0  # 无均量参考, 中性

        return abs_score * 0.60 + rel_score * 0.40

    # ── Opt 1: Revision catalyst bonus ──

    @staticmethod
    def _revision_bonus(revision_pct: float, days_since: int) -> float:
        """下修催化剂加分. 中幅下修(5-10%)性价比最高."""
        if revision_pct is None or revision_pct >= 0:
            return 0.0
        magnitude = abs(revision_pct)
        if 5 <= magnitude <= 10:
            return 4.0 if days_since <= 10 else (3.0 if days_since <= 30 else 1.0)
        elif magnitude < 5:
            return 1.0 if days_since <= 30 else 0.0
        else:
            return 2.0 if days_since <= 30 else 0.0

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute intraday CB screening V3 — auction sector-driven.

        Pipeline:
          1. stk_auction_o → 按行业聚合竞价涨幅 → 强势板块
          2. 强势板块 → cb_concept → 转债候选池
          3. 四维评分: 板块竞价(30%) + 溢价率(25%) + 正股趋势(25%) + 活跃度(20%)
          4. 排序 → 评级 → 返回 Top N

        Args:
            top_n: max picks to return
            trade_date: trading date (YYYY-MM-DD), default latest

        Returns:
            list of scored pick dicts sorted by total_score desc
        """
        t0 = time.time()
        cur = self.db.cursor()

        # Resolve dates: auction data may be T, daily data may be T-1
        if not trade_date:
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            row = cur.fetchone()
            auction_date = str(row[0]) if row and row[0] else date.today().strftime("%Y-%m-%d")
            # Use cb_daily for the most complete daily data
            cur.execute("SELECT MAX(trade_date) FROM cb_daily")
            row = cur.fetchone()
            daily_date = str(row[0]) if row and row[0] else auction_date
        else:
            auction_date = trade_date
            daily_date = trade_date

        logger.info("CbIntradayEngine V3: auction=%s, daily=%s, top_n=%d",
                    auction_date, daily_date, top_n)

        # ── Step 1: Get sector strength (auction → ths_daily today → ths_daily T-1 → neutral) ──
        sector_strength = self._get_sector_auction_strength(cur, auction_date)
        data_source = "auction"

        if not sector_strength:
            logger.info("CbIntradayEngine V3: no auction data, trying ths_daily today")
            sector_strength = self._get_concept_strength_from_ths(cur, auction_date)
            data_source = "ths_daily"

        # Opt 4: T-1 ths_daily as sector proxy when today's data is missing
        if not sector_strength:
            logger.info("CbIntradayEngine V3: no today ths_daily, trying T-1 ths_daily as proxy")
            sector_strength = self._get_concept_strength_from_ths(cur, daily_date)
            if sector_strength:
                data_source = "ths_daily_t1"

        if not sector_strength:
            logger.info("CbIntradayEngine V3: no sector data, scoring all CBs (neutral)")
            sector_strength = {"__all__": {"score": 50.0, "avg_gap": 0, "count": 0, "avg_amount": 0}}
            data_source = "neutral"

        top_sectors = sorted(sector_strength.items(), key=lambda x: x[1]["score"], reverse=True)[:10]
        sector_score_map = {ind: info["score"] for ind, info in sector_strength.items()}

        if data_source == "neutral":
            logger.info("CbIntradayEngine V3: scoring all CBs (neutral mode)")
        else:
            logger.info("CbIntradayEngine V3: top sectors(%s): %s", data_source,
                        [(ind, round(info["score"], 1)) for ind, info in top_sectors])

        # ── Step 2: Get CB candidates ──
        if data_source == "neutral":
            cb_candidates = self._get_all_active_cbs(cur, daily_date)
        else:
            strong_industries = {ind for ind, _ in top_sectors}
            cb_candidates = self._find_cbs_in_sectors(cur, strong_industries, daily_date)

        # Performance: cap candidates at 150 to keep pre-fetch queries fast
        if len(cb_candidates) > 150:
            cb_candidates = dict(list(cb_candidates.items())[:150])

        # If sector-driven candidates are too few, supplement with neutral picks
        if len(cb_candidates) < 10:
            logger.info("CbIntradayEngine V3: only %d sector candidates, supplementing neutral",
                        len(cb_candidates))
            neutral_candidates = self._get_all_active_cbs(cur, daily_date)
            # Merge: sector candidates first, then neutral fill
            for ts_code, info in neutral_candidates.items():
                if ts_code not in cb_candidates:
                    cb_candidates[ts_code] = info
                    if len(cb_candidates) >= 30:
                        break

        if not cb_candidates:
            logger.warning("CbIntradayEngine V3: no CB candidates for %s", daily_date)
            return []

        # ── Step 3: Pre-fetch auxiliary data ──
        cb_ts_codes = list(cb_candidates.keys())
        cb_daily_map = self._prefetch_cb_daily(cur, cb_ts_codes, daily_date)

        # Stock T-1 kline (only need yesterday's change_pct)
        stock_codes = list(set(info["stk_code"] for info in cb_candidates.values()))
        yesterday_map = self._prefetch_yesterday_pct(cur, stock_codes, daily_date)

        # CB 5-day avg amount (for liquidity scoring)
        cb_avg_amount_map = self._prefetch_cb_avg_amount(cur, cb_ts_codes, daily_date)

        # 强赎 risk
        call_risk_map = self._prefetch_call_risk(cur)

        # Opt 1: 下修催化剂
        revision_map = self._prefetch_recent_revisions(cur, cb_ts_codes)

        # ── Step 4: Score each CB ──
        picks = []
        for ts_code, info in cb_candidates.items():
            try:
                stk_code = info["stk_code"]
                sector = info["sector"]

                # Get daily data
                daily = cb_daily_map.get(ts_code, {})
                close = daily.get("close")
                cb_over_rate = daily.get("cb_over_rate")
                cb_pct_chg = daily.get("pct_chg")
                cb_amount = daily.get("amount")
                conv_price = info.get("conv_price")
                stock_close = daily.get("stock_close")

                # Calculate premium rate if missing
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                # ── Factor 1: Sector auction strength (35%) ──
                sector_score = sector_score_map.get(sector, 50.0)

                # ── Factor 2: Premium rate (25%) ──
                premium_score = self._premium_score(cb_over_rate)

                # ── Factor 3: Yesterday momentum (20%) ──
                yesterday_pct = yesterday_map.get(stk_code)

                # V6.1: Direction filter — 极端涨跌不入
                if yesterday_pct is not None:
                    if yesterday_pct > 5:    # 昨暴涨追高
                        continue
                    if yesterday_pct < -5:   # 昨暴跌有雷
                        continue

                momentum_score = self._yesterday_momentum_score(yesterday_pct)

                # ── Factor 4: Liquidity (20%) ──
                avg_amount_5d = cb_avg_amount_map.get(ts_code)
                liquidity_score = self._liquidity_score(cb_amount, avg_amount_5d)

                # ── Opt 1: Revision bonus ──
                rev_info = revision_map.get(ts_code, {})
                rev_bonus = self._revision_bonus(rev_info.get("pct_change"), rev_info.get("days_since", 999))

                # ── 强赎惩罚 ──
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
                            continue  # 登记日已过, 跳过
                        if days_to_reg <= 3:
                            call_risk = "强赎中(最后3天!)"
                            call_penalty = -20.0
                        elif days_to_reg <= 7:
                            call_penalty = -10.0
                        else:
                            call_penalty = -5.0
                elif call_info.get("is_call") == "公告提示强赎":
                    call_risk = "提示强赎"
                    call_penalty = -3.0

                # ── Weighted total V6 ──
                total = (
                    sector_score * 0.20
                    + premium_score * 0.15
                    + momentum_score * 0.30
                    + liquidity_score * 0.35
                    + rev_bonus
                    + call_penalty
                )

                # Grade
                if total >= 75:
                    grade = "S"
                elif total >= 60:
                    grade = "A"
                elif total >= 45:
                    grade = "B"
                else:
                    grade = "C"

                picks.append({
                    "code": ts_code,
                    "name": info.get("name") or ts_code,
                    "stk_code": stk_code,
                    "stk_name": info.get("stk_name"),
                    "sector": sector,
                    "sector_score": round(sector_score, 1),
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "yesterday_pct": round(yesterday_pct, 2) if yesterday_pct else None,
                    "cb_amount_wan": round(cb_amount / 1e4, 0) if cb_amount else None,
                    "call_risk": call_risk,
                    "call_date": str(call_info.get("call_date")) if call_info.get("call_date") else None,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "sector_score": round(sector_score, 1),
                        "premium_score": round(premium_score, 1),
                        "momentum_score": round(momentum_score, 1),
                        "liquidity_score": round(liquidity_score, 1),
                        "rev_bonus": round(rev_bonus, 1),
                        "call_penalty": round(call_penalty, 1),
                    },
                })

            except Exception as e:
                logger.debug("CB intraday %s scoring failed: %s", ts_code, e)
                continue

        # Sort by linear score
        picks.sort(key=lambda x: x["total_score"], reverse=True)

        # ── V5: ML re-ranking + threshold ──
        if kwargs.get("use_ml", True):
            try:
                self._load_ml_models()
                for p in picks:
                    d = p.get("details", {})
                    features = [
                        d.get("sector_score", 50), d.get("premium_score", 50),
                        d.get("momentum_score", 50), d.get("liquidity_score", 50),
                        d.get("rev_bonus", 0), d.get("call_penalty", 0),
                        p.get("premium_rate") or 0, p.get("yesterday_pct") or 0,
                        p.get("cb_amount_wan") or 0, 0, 0,
                    ]
                    X = np.array([features], dtype=np.float32)
                    p["ml_score"] = float(np.mean([m.predict(X)[0]
                        for m in self._ensemble_models.values()]))

                # ML re-rank + threshold
                # V6: ML≥2.0 (ML[1-2) only -0.08%, ML[2+) starts at +1.06%)
                picks = [p for p in picks if p.get("ml_score", 0) >= 2.0]
                picks.sort(key=lambda x: x.get("ml_score", 0), reverse=True)
            except Exception as e:
                logger.warning("ML re-rank failed, using linear: %s", e)

        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info(
            "CbIntradayEngine V5: %d picks from %d CBs (src=%s, %.1fs)",
            len(picks), len(cb_candidates), data_source, elapsed,
        )

        return picks

    @classmethod
    def _load_ml_models(cls):
        """加载 Ensemble ML 模型 (类级缓存)."""
        if cls._ensemble_models is not None:
            return
        cls._ensemble_models = {}
        _proj = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        for name in ['rf', 'lightgbm', 'catboost']:
            path = os.path.join(_proj, 'outputs', f'cb_ml_{name}.pkl')
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    cls._ensemble_models[name] = pickle.load(f)['model']

    # ── Data fetching helpers ──

    def _get_sector_auction_strength(self, cur, trade_date: str) -> dict:
        """从 stk_auction_o 按行业聚合竞价强度.

        Returns:
            {industry: {"score": float, "avg_gap": float, "count": int, "avg_amount": float}}
        """
        try:
            cur.execute("""
                SELECT s.industry,
                       AVG((ao.open - ao.close) / NULLIF(ao.close, 0) * 100) AS avg_gap,
                       COUNT(*) AS stock_count,
                       AVG(ao.amount) AS avg_amount
                FROM stk_auction_o ao
                JOIN stocks s ON ao.code = s.code
                WHERE ao.trade_date = %s
                  AND ao.open > 0 AND ao.close > 0
                  AND s.industry IS NOT NULL AND s.industry != ''
                  AND s.name NOT LIKE '%%ST%%'
                GROUP BY s.industry
                HAVING COUNT(*) >= 3
                   AND AVG((ao.open - ao.close) / NULLIF(ao.close, 0) * 100) > 0
                ORDER BY avg_gap DESC
            """, (trade_date,))
            rows = cur.fetchall()

            result = {}
            for industry, avg_gap, count, avg_amount in rows:
                if avg_gap is None:
                    continue
                gap = float(avg_gap)
                result[industry] = {
                    "score": round(self._normalize_sector_score(gap, count), 1),
                    "avg_gap": round(gap, 2),
                    "count": count,
                    "avg_amount": float(avg_amount or 0),
                }

            return result
        except Exception as e:
            logger.warning("_get_sector_auction_strength failed: %s", e)
            return {}

    def _get_concept_strength_from_ths(self, cur, trade_date: str) -> dict:
        """从 ths_daily + ths_concept_map 获取概念板块强度.

        Returns:
            {concept_name: {"score": float, "avg_gap": float, "count": int, "avg_amount": float}}
        """
        try:
            cur.execute("""
                SELECT m.name, d.change_pct, 1 AS cnt
                FROM ths_daily d
                JOIN ths_concept_map m ON d.code = m.ts_code
                WHERE d.trade_date = %s AND d.change_pct IS NOT NULL
                ORDER BY d.change_pct DESC LIMIT 30
            """, (trade_date,))
            rows = cur.fetchall()
            result = {}
            for name, pct, cnt in rows:
                if pct is None or not name or not name.strip():
                    continue
                pct = float(pct)
                # Use fixed count=5 to avoid count penalty for single-concept
                result[name] = {
                    "score": round(self._normalize_sector_score(pct, 5), 1),
                    "avg_gap": round(pct, 2),
                    "count": 5,
                    "avg_amount": 0,
                }
            return result
        except Exception as e:
            logger.warning("_get_concept_strength_from_ths failed: %s", e)
            return {}

    @staticmethod
    def _normalize_sector_score(gap_pct: float, count: int) -> float:
        """将板块平均涨幅归一化为 0-100 评分."""
        if gap_pct >= 4:
            score = 100.0
        elif gap_pct >= 2:
            score = 85 + (gap_pct - 2) * 7.5
        elif gap_pct >= 1:
            score = 70 + (gap_pct - 1) * 15
        elif gap_pct >= 0.5:
            score = 55 + (gap_pct - 0.5) * 30
        else:
            score = 40 + gap_pct * 30
        count_boost = min(10, (count - 3) * 1.5)
        return min(100, score + count_boost)

    def _find_cbs_in_sectors(self, cur, sector_keys: set, trade_date: str) -> dict:
        """通过 cb_concept 找到属于强势板块/概念的转债.

        两路径依次尝试:
        1. concept 精确匹配 → 模糊匹配 (cb_concept LIKE '%key%')
        2. industry 路径 (stocks.industry IN keys)

        Returns:
            {ts_code: {"stk_code", "name", "stk_name", "sector", "conv_price"}}
        """
        if not sector_keys:
            return {}

        result = {}
        sector_list = list(sector_keys)
        placeholders = ",".join(["%s"] * len(sector_list))
        try:
            all_matched_concepts = set()

            # ── Path 1a: exact concept match ──
            cur.execute(f"""
                SELECT DISTINCT cc.concept FROM cb_concept cc
                WHERE cc.concept IN ({placeholders})
            """, sector_list)
            all_matched_concepts.update(r[0] for r in cur.fetchall())

            # ── Path 1b: fuzzy: cb_concept contains key ──
            fuzzy_ors = " OR ".join(["cc.concept LIKE %s"] * len(sector_list))
            fuzzy_params = [f"%{k}%" for k in sector_list]
            cur.execute(f"""
                SELECT DISTINCT cc.concept FROM cb_concept cc
                WHERE {fuzzy_ors}
            """, fuzzy_params)
            all_matched_concepts.update(r[0] for r in cur.fetchall())

            # ── Path 2: industry → concept ──
            if not all_matched_concepts:
                cur.execute(f"""
                    SELECT DISTINCT cc.concept
                    FROM cb_concept cc
                    JOIN cb_basic cb ON cc.ts_code = cb.ts_code
                    JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code
                    WHERE s.industry IN ({placeholders})
                """, sector_list)
                all_matched_concepts.update(r[0] for r in cur.fetchall())

            if not all_matched_concepts:
                return {}

            # ── Bulk query: concepts → CBs ──
            cp_placeholders = ",".join(["%s"] * len(all_matched_concepts))
            cur.execute(f"""
                SELECT DISTINCT
                    cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
                    cb.conv_price, cb.remain_size, cc.concept
                FROM cb_concept cc
                JOIN cb_basic cb ON cc.ts_code = cb.ts_code
                WHERE cc.concept IN ({cp_placeholders})
                  AND (cb.delist_date IS NULL OR cb.delist_date > %s::date)
            """, list(all_matched_concepts) + [trade_date])

            for ts_code, name, stk_code_ts, stk_name, conv_price, remain_size, concept in cur.fetchall():
                stk_raw = stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or "")
                if ts_code not in result:
                    result[ts_code] = {
                        "stk_code": stk_raw, "name": name, "stk_name": stk_name,
                        "sector": concept, "conv_price": conv_price, "remain_size": remain_size,
                    }
        except Exception as e:
            logger.warning("_find_cbs_in_sectors failed: %s", e)

        return result

    def _get_all_active_cbs(self, cur, trade_date: str) -> dict:
        """获取所有活跃转债 (无板块过滤时使用).

        Returns:
            {ts_code: {"stk_code", "name", "stk_name", "sector", "conv_price"}}
        """
        result = {}
        try:
            cur.execute("""
                SELECT cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
                       cb.conv_price, cb.remain_size
                FROM cb_basic cb
                WHERE (cb.delist_date IS NULL OR cb.delist_date > %s::date)
                LIMIT 150
            """, (trade_date,))
            for ts_code, name, stk_code_ts, stk_name, conv_price, remain_size in cur.fetchall():
                stk_raw = stk_code_ts.split(".")[0] if stk_code_ts and "." in str(stk_code_ts) else (stk_code_ts or "")
                result[ts_code] = {
                    "stk_code": stk_raw, "name": name, "stk_name": stk_name,
                    "sector": "全市场", "conv_price": conv_price, "remain_size": remain_size,
                }
        except Exception as e:
            logger.warning("_get_all_active_cbs failed: %s", e)
        return result

    def _prefetch_cb_daily(self, cur, ts_codes: list, trade_date: str) -> dict:
        """预取转债日线数据.

        Returns:
            {ts_code: {close, cb_over_rate, pct_chg, amount, stock_close}}
        """
        if not ts_codes:
            return {}
        result = {}
        try:
            placeholders = ",".join(["%s"] * len(ts_codes))
            cur.execute(f"""
                SELECT cb.ts_code, d.close, d.cb_over_rate, d.pct_chg, d.amount,
                       sk.close AS stock_close
                FROM cb_basic cb
                LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
                LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code
                    AND sk.trade_date = %s
                WHERE cb.ts_code IN ({placeholders})
            """, [trade_date, trade_date] + ts_codes)
            for ts_code, close, cb_over_rate, pct_chg, amount, stock_close in cur.fetchall():
                result[ts_code] = {
                    "close": close,
                    "cb_over_rate": cb_over_rate,
                    "pct_chg": pct_chg,
                    "amount": amount,
                    "stock_close": stock_close,
                }
        except Exception as e:
            logger.warning("_prefetch_cb_daily failed: %s", e)
        return result

    def _prefetch_yesterday_pct(self, cur, stock_codes: list, trade_date: str) -> dict:
        """预取正股 T-1 涨跌幅, change_pct 缺失时用 close 计算.

        Returns:
            {code: pct_chg}  (T-1 change_pct, 或 None)
        """
        if not stock_codes:
            return {}
        result = {}
        try:
            placeholders = ",".join(["%s"] * len(stock_codes))
            # Get 2 most recent rows per stock to compute change_pct if needed
            cur.execute(f"""
                SELECT code, trade_date, change_pct, close
                FROM daily_kline
                WHERE code IN ({placeholders})
                  AND trade_date < %s
                ORDER BY code, trade_date DESC
            """, stock_codes + [trade_date])
            from collections import defaultdict
            stock_rows = defaultdict(list)
            for code, td, pct, close in cur.fetchall():
                stock_rows[code].append((td, pct, close))
            for code, rows in stock_rows.items():
                if not rows:
                    continue
                pct = rows[0][1]
                if pct is not None:
                    result[code] = float(pct)
                elif len(rows) >= 2 and rows[0][2] and rows[1][2]:
                    # Compute from close prices
                    result[code] = (float(rows[0][2]) - float(rows[1][2])) / float(rows[1][2]) * 100
                else:
                    result[code] = None
        except Exception as e:
            logger.warning("_prefetch_yesterday_pct failed: %s", e)
        return result

    def _prefetch_cb_avg_amount(self, cur, ts_codes: list, trade_date: str) -> dict:
        """预取转债近5日均成交额.

        Returns:
            {ts_code: avg_amount_5d}
        """
        if not ts_codes:
            return {}
        result = {}
        try:
            placeholders = ",".join(["%s"] * len(ts_codes))
            cur.execute(f"""
                SELECT ts_code, AVG(amount) AS avg_amount
                FROM cb_daily
                WHERE ts_code IN ({placeholders})
                  AND trade_date < %s
                  AND trade_date >= (%s::date - INTERVAL '10 days')
                  AND amount > 0
                GROUP BY ts_code
            """, ts_codes + [trade_date, trade_date])
            for ts_code, avg_amount in cur.fetchall():
                result[ts_code] = float(avg_amount) if avg_amount else None
        except Exception as e:
            logger.warning("_prefetch_cb_avg_amount failed: %s", e)
        return result

    def _prefetch_call_risk(self, cur) -> dict:
        """预取强赎风险数据.

        Returns:
            {ts_code: {is_call, call_date, call_price, call_reg_date}}
        """
        result = {}
        try:
            cur.execute(
                "SELECT ts_code, is_call, call_date, call_price, call_reg_date FROM cb_call "
                "WHERE call_date >= CURRENT_DATE - INTERVAL '30 days' "
                "ORDER BY ts_code, call_date DESC"
            )
            for r in cur.fetchall():
                if r[0] not in result:
                    result[r[0]] = {
                        "is_call": r[1], "call_date": r[2],
                        "call_price": r[3], "call_reg_date": r[4],
                    }
        except Exception:
            pass
        return result

    # ── Opt 1: 下修催化剂预取 ──

    def _prefetch_recent_revisions(self, cur, ts_codes: list) -> dict:
        """预取近期转股价下修数据.

        Returns:
            {ts_code: {"pct_change": float, "days_since": int}}
            pct_change 为负表示下修
        """
        if not ts_codes:
            return {}
        result = {}
        try:
            placeholders = ",".join(["%s"] * len(ts_codes))
            cur.execute(f"""
                SELECT ts_code, pre_price, new_price, change_date
                FROM cb_price_chg
                WHERE ts_code IN ({placeholders})
                  AND pre_price > 0 AND new_price > 0
                  AND change_date >= CURRENT_DATE - INTERVAL '90 days'
                ORDER BY ts_code, change_date DESC
            """, ts_codes)
            from datetime import date
            today = date.today()
            for ts_code, pre_price, new_price, change_date in cur.fetchall():
                if ts_code in result:
                    continue  # 只取最近一次
                if isinstance(change_date, str):
                    change_date = datetime.strptime(change_date, "%Y-%m-%d").date()
                pct = (float(new_price) - float(pre_price)) / float(pre_price) * 100
                days = (today - change_date).days
                result[ts_code] = {"pct_change": round(pct, 1), "days_since": days}
        except Exception as e:
            logger.debug("_prefetch_recent_revisions: %s", e)
        return result
