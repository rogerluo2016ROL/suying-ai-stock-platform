"""匪爷可转债底价选债模型 — 11因子综合评分引擎.

选债逻辑:
  1. 到期收益率越高越好 (25%)
  2. 债券评级 A级以上 (硬过滤)
  3. 溢价率越低越好 (20%)
  4. 正股财报标准无保留 (加分)
  5. 近10日下修转股价优先 (15%)
  6. 热门题材优先 (10%)
  7. 下修历史优先 (10%)
  8. 非国企控股优先 (5%)
  9. 规模越小越好 (10%)
  10. 到期剩余<3个月排除 (硬排除)
  11. 股东质押率低 (5%)
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_floor")


class CbFloorEngine:
    """匪爷可转债底价选债模型 — 11 维加权评分."""

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
    def _rating_to_score(rating: str) -> float:
        """Map credit rating to 0-100 score. A+ and above = full score."""
        if not rating:
            return 50.0
        r = rating.upper().strip()
        # AAA -> 100, AA+ -> 95, AA -> 90, AA- -> 85, A+ -> 80, A -> 75, A- -> 70
        # BBB+ -> 60, BBB -> 50, BB -> 30, B -> 15, CCC/CC/C -> 5
        base_map = {
            "AAA": 100, "AAA-": 97,
            "AA+": 95, "AA": 90, "AA-": 85,
            "A+": 80, "A": 75, "A-": 70,
            "BBB+": 65, "BBB": 60, "BBB-": 55,
            "BB+": 45, "BB": 35, "BB-": 25,
            "B+": 20, "B": 15, "B-": 10,
            "CCC": 5, "CC": 3, "C": 1, "D": 0,
        }
        return base_map.get(r, 50.0)

    @staticmethod
    def _premium_score(premium_rate: float) -> float:
        """Lower premium = higher score. 0-100."""
        if premium_rate is None:
            return 50.0
        if premium_rate <= 0:
            return 95.0
        if premium_rate <= 5:
            return 100 - premium_rate * 1.0
        if premium_rate <= 20:
            return 95 - (premium_rate - 5) * 1.33
        if premium_rate <= 50:
            return 75 - (premium_rate - 20) * 1.5
        if premium_rate <= 100:
            return 30 - (premium_rate - 50) * 0.4
        return max(5.0, 10 - premium_rate * 0.05)

    @staticmethod
    def _size_score(remain_size: float) -> float:
        """Smaller size = higher score. 0-100."""
        if remain_size is None:
            return 50.0
        size_yi = remain_size / 1e8  # convert to 亿
        if size_yi <= 0.5:
            return 100.0
        if size_yi <= 1:
            return 100 - (size_yi - 0.5) * 20
        if size_yi <= 3:
            return 90 - (size_yi - 1) * 15
        if size_yi <= 5:
            return 60 - (size_yi - 3) * 12.5
        if size_yi <= 10:
            return 35 - (size_yi - 5) * 3
        if size_yi <= 20:
            return 20 - (size_yi - 10) * 1
        return max(5.0, 10 - size_yi * 0.1)

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute convertible bond floor-price screening.

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
            cur.execute("SELECT MAX(trade_date) FROM cb_daily")
            row = cur.fetchone()
            trade_date = row[0] if row and row[0] else date.today().strftime("%Y-%m-%d")
            if isinstance(trade_date, date):
                trade_date = trade_date.strftime("%Y-%m-%d")

        logger.info("CbFloorEngine: screening for %s, top_n=%d", trade_date, top_n)

        # ── Query: join cb_basic + latest cb_daily + stock info + stock kline ──
        query = """
        SELECT
            cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
            cb.maturity_date, cb.coupon_rate, cb.remain_size,
            cb.newest_rating, cb.issue_rating, cb.par, cb.list_date,
            cb.conv_price, cb.exchange, cb.cb_type, cb.rate_type,
            d.close, d.cb_over_rate, d.bond_value, d.bond_over_rate,
            d.pre_close, d.pct_chg, d.amount,
            s.industry, s.market_cap,
            sk.close AS stock_close
        FROM cb_basic cb
        LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
        LEFT JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code
        LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code AND sk.trade_date = %s
        WHERE cb.delist_date IS NULL OR cb.delist_date > %s::date
        """
        cur.execute(query, (trade_date, trade_date, trade_date))
        rows = cur.fetchall()

        if not rows:
            logger.warning("CbFloorEngine: no CB data for %s", trade_date)
            return []

        # ── Pre-fetch: price change history for all CBs ──
        cur.execute("""
            SELECT ts_code, change_date, pre_price, new_price, change_reason
            FROM cb_price_chg
            ORDER BY ts_code, change_date DESC
        """)
        price_chg_rows = cur.fetchall()
        price_chg_map = {}  # {ts_code: [(change_date, pre, new, reason), ...]}
        for r in price_chg_rows:
            price_chg_map.setdefault(r[0], []).append(r)

        # ── Pre-fetch: pledge detail for underlying stocks ──
        stock_codes = list(set(r[2] for r in rows if r[2]))
        pledge_map = {}
        if stock_codes:
            placeholders = ",".join(["%s"] * len(stock_codes))
            try:
                cur.execute(
                    f"SELECT code, pledge_ratio FROM pledge_detail "
                    f"WHERE code IN ({placeholders}) "
                    f"ORDER BY code, trade_date DESC",
                    stock_codes,
                )
                for r in cur.fetchall():
                    if r[0] not in pledge_map:
                        pledge_map[r[0]] = r[1]
            except Exception:
                pass  # pledge_detail may not have pledge_ratio column

        # ── Pre-fetch: hot themes from ths_daily ──
        today = date.today().strftime("%Y-%m-%d")
        hot_industries = set()
        try:
            cur.execute(
                "SELECT DISTINCT industry FROM ths_daily WHERE trade_date = %s "
                "AND pct_chg > 2 ORDER BY pct_chg DESC LIMIT 15",
                (trade_date,),
            )
            hot_industries = {r[0] for r in cur.fetchall() if r[0]}
        except Exception:
            pass

        # ── Score each CB ──
        picks = []
        for r in rows:
            try:
                (
                    ts_code, name, stk_code, stk_name,
                    maturity_date_, coupon_rate, remain_size,
                    newest_rating, issue_rating, par, list_date_,
                    conv_price, exchange, cb_type, rate_type,
                    close, cb_over_rate, bond_value, bond_over_rate,
                    pre_close, pct_chg, amount,
                    industry, market_cap,
                    stock_close,
                ) = r

                # ── Hard filter: rating A- and above ──
                rating = newest_rating or issue_rating or ""
                if rating and not any(
                    rating.upper().startswith(p)
                    for p in ("AAA", "AA", "A")
                ):
                    continue

                # ── Hard exclude: maturity < 3 months ──
                if maturity_date_:
                    if isinstance(maturity_date_, str):
                        mat_dt = datetime.strptime(maturity_date_, "%Y-%m-%d").date()
                    else:
                        mat_dt = maturity_date_
                    days_left = (mat_dt - date.today()).days
                    if days_left < 90:
                        continue

                # ── Calculate premium rate if not available ──
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    # conv_value = (100 / conv_price) * stock_price
                    # premium_rate = (cb_price / conv_value - 1) * 100
                    conv_value = 100.0 / conv_price * stock_close
                    if conv_value > 0:
                        cb_over_rate = (close / conv_value - 1) * 100

                # ── Factor 1: YTM score (25%) ──
                ytm_score = self._score_ytm(
                    close, coupon_rate, par, maturity_date_, rate_type
                )

                # ── Factor 2: Rating score (embedded in hard filter above, bonus here) ──
                rating_score = self._rating_to_score(rating)

                # ── Factor 3: Premium score (20%) ──
                premium_score = self._premium_score(cb_over_rate)

                # ── Factor 4: Audit opinion (check financial_indicator) ──
                audit_bonus = self._check_audit_opinion(cur, stk_code)

                # ── Factor 5: Recent downward revision (15%) ──
                revision_score = self._score_recent_revision(
                    ts_code, price_chg_map, days=10
                )

                # ── Factor 6: Hot theme (10%) ──
                theme_score = 80.0 if industry and industry in hot_industries else 40.0

                # ── Factor 7: Downward revision history (10%) ──
                history_score = self._score_revision_history(
                    ts_code, price_chg_map
                )

                # ── Factor 8: Non-SOE priority (5%) ──
                soe_score = self._score_ownership(cur, stk_code)

                # ── Factor 9: Size score (10%) ──
                size_score = self._size_score(remain_size)

                # ── Factor 10: maturity filter (handled above) ──

                # ── Factor 11: Pledge score (5%) ──
                pledge_score = self._score_pledge(stk_code, pledge_map)

                # ── Weighted total ──
                total = (
                    ytm_score * 0.25
                    + rating_score * 0.05
                    + premium_score * 0.20
                    + audit_bonus * 0.05
                    + revision_score * 0.15
                    + theme_score * 0.10
                    + history_score * 0.05
                    + soe_score * 0.05
                    + size_score * 0.05
                    + pledge_score * 0.05
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
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "maturity_date": str(maturity_date_) if maturity_date_ else None,
                    "rating": rating,
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "ytm_score": round(ytm_score, 1),
                        "rating_score": round(rating_score, 1),
                        "premium_score": round(premium_score, 1),
                        "audit_bonus": round(audit_bonus, 1),
                        "revision_score": round(revision_score, 1),
                        "theme_score": round(theme_score, 1),
                        "history_score": round(history_score, 1),
                        "soe_score": round(soe_score, 1),
                        "size_score": round(size_score, 1),
                        "pledge_score": round(pledge_score, 1),
                    },
                })

            except Exception as e:
                logger.debug("CB %s scoring failed: %s", r[0] if r else "?", e)
                continue

        # Sort and truncate
        picks.sort(key=lambda x: x["total_score"], reverse=True)
        picks = picks[:top_n]

        elapsed = time.time() - t0
        logger.info(
            "CbFloorEngine: %d picks from %d CBs (%.1fs)",
            len(picks), len(rows), elapsed,
        )

        return picks

    # ── Factor implementations ──

    def _score_ytm(self, close, coupon_rate, par, maturity_date_, rate_type):
        """Score yield-to-maturity. Higher YTM = higher score."""
        if not close or close <= 0:
            return 30.0
        if not coupon_rate:
            coupon_rate = 0.0
        if not par:
            par = 100.0

        # Simple YTM approximation: (coupon + (par - price) / years_left) / price
        years_left = 3.0  # default
        if maturity_date_:
            if isinstance(maturity_date_, str):
                mat_dt = datetime.strptime(maturity_date_, "%Y-%m-%d").date()
            else:
                mat_dt = maturity_date_
            years_left = max(0.1, (mat_dt - date.today()).days / 365.25)

        annual_coupon = par * coupon_rate / 100.0
        capital_gain = (par - close) / years_left
        ytm = (annual_coupon + capital_gain) / close * 100

        # Score: YTM ≥ 5% -> 100, ≥ 3% -> 80, ≥ 1% -> 60, ≥ 0% -> 40, <0% -> 10
        if ytm >= 8:
            return 100.0
        if ytm >= 5:
            return 80 + (ytm - 5) * 6.67
        if ytm >= 3:
            return 60 + (ytm - 3) * 10
        if ytm >= 1:
            return 40 + (ytm - 1) * 10
        if ytm >= 0:
            return 20 + ytm * 20
        return max(5.0, 20 + ytm * 2)

    def _check_audit_opinion(self, cur, stk_code) -> float:
        """Check if the underlying stock has clean audit opinion. Return bonus 0-100."""
        if not stk_code:
            return 50.0
        try:
            cur.execute(
                "SELECT audit_opinion FROM financial_indicator "
                "WHERE code = %s AND audit_opinion IS NOT NULL "
                "ORDER BY end_date DESC LIMIT 1",
                (stk_code,),
            )
            row = cur.fetchone()
            if row and row[0]:
                opinion = str(row[0]).strip()
                if "标准无保留" in opinion or "无保留意见" in opinion:
                    return 100.0
                if "保留" in opinion:
                    return 30.0
                if "否定" in opinion or "无法表示" in opinion:
                    return 0.0
                return 60.0
        except Exception:
            pass
        return 50.0

    def _score_recent_revision(self, ts_code, price_chg_map, days=10) -> float:
        """Score recent downward conversion price revision. 0-100."""
        changes = price_chg_map.get(ts_code, [])
        if not changes:
            return 30.0

        cutoff = date.today()
        recent = False
        has_downward = False
        for chg_date, pre_price, new_price, reason in changes:
            if isinstance(chg_date, str):
                chg_date = datetime.strptime(chg_date, "%Y-%m-%d").date()
            if (cutoff - chg_date).days <= days and new_price and pre_price:
                if new_price < pre_price:
                    recent = True
                    break

        if recent:
            return 100.0

        # Check if any downward revision at all
        for _, pre_price, new_price, reason in changes:
            if new_price and pre_price and new_price < pre_price:
                has_downward = True
                break

        return 60.0 if has_downward else 30.0

    def _score_revision_history(self, ts_code, price_chg_map) -> float:
        """Score based on total number of downward revisions. 0-100."""
        changes = price_chg_map.get(ts_code, [])
        if not changes:
            return 20.0

        downward_count = 0
        for _, pre_price, new_price, reason in changes:
            if new_price and pre_price and new_price < pre_price:
                downward_count += 1
                reason_str = str(reason or "").lower()
                if any(kw in reason_str for kw in ("下修", "修正", "向下")):
                    downward_count += 1  # double count explicit 下修

        if downward_count >= 3:
            return 100.0
        if downward_count >= 2:
            return 85.0
        if downward_count >= 1:
            return 70.0
        return 20.0

    def _score_ownership(self, cur, stk_code) -> float:
        """Non-SOE = higher score. 0-100."""
        if not stk_code:
            return 50.0
        try:
            cur.execute(
                "SELECT legal_type FROM stock_profiles WHERE code = %s",
                (stk_code,),
            )
            row = cur.fetchone()
            if row and row[0]:
                legal = str(row[0])
                soe_keywords = ("国有", "央企", "地方国企", "国资委", "国资")
                if any(kw in legal for kw in soe_keywords):
                    return 20.0
                return 90.0
        except Exception:
            pass

        # Fallback: check stock code prefix for SOE hints (6xx mostly state-owned)
        if stk_code.startswith("6"):
            return 40.0
        return 70.0

    def _score_pledge(self, stk_code, pledge_map) -> float:
        """Lower pledge ratio = higher score. 0-100."""
        if not stk_code:
            return 50.0
        ratio = pledge_map.get(stk_code)
        if ratio is None:
            return 50.0
        # ratio is typically 0-100%
        if isinstance(ratio, (int, float)):
            if ratio <= 5:
                return 100.0
            if ratio <= 15:
                return 100 - ratio * 1.0
            if ratio <= 30:
                return 85 - (ratio - 15) * 2.0
            if ratio <= 50:
                return 55 - (ratio - 30) * 1.0
            return max(5.0, 35 - (ratio - 50) * 0.5)
        return 50.0
