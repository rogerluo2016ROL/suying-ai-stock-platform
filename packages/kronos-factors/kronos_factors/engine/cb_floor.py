"""匪爷可转债底价选债模型 V2 — 12因子优化版.

优化要点 (基于回测发现):
  1. 过期收益率权重 25%→10% (削弱ST债偏好)
  2. 溢价率权重 20%→30% + 折价额外加分
  3. 评级从硬过滤改为软扣分
  4. 新增 CB动量(15%) + 正股动量(10%) + 成交量(5%)
  5. 剔除低效因子: 审计意见(0%)、下修权重下调

因子权重 V2:
  1. 溢价率越低越好 (30%)
  2. CB近10日动量 (15%)
  3. 到期收益率 (10%)
  4. 正股近5日动量 (10%)
  5. 近10日下修转股价优先 (10%)
  6. 热门题材 (5%)
  7. 下修历史 (5%)
  8. 规模越小越好 (5%)
  9. 非国企控股优先 (5%)
  10. CB成交量活跃 (5%)
  11. 评级软扣分 (-15 if 无/B级以下)
  -  到期剩余<3个月排除 (硬排除)
"""

import logging
import os
import time
from datetime import date, datetime

logger = logging.getLogger("screener.cb_floor")


class CbFloorEngine:
    """匪爷可转债底价选债模型 V2 — 12因子优化评分."""

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
        """V2: 折价加分 + 溢价惩罚. 0-100."""
        if premium_rate is None:
            return 50.0
        # Deep discount = full marks
        if premium_rate <= -15:
            return 100.0
        if premium_rate <= -10:
            return 97 + (premium_rate + 15) * 0.6
        if premium_rate <= -5:
            return 93 + (premium_rate + 10) * 0.8
        if premium_rate <= 0:
            return 85 + premium_rate * 1.6   # 0折价=85, -5折价=93
        if premium_rate <= 10:
            return 85 - premium_rate * 3.0    # 10%溢价→55
        if premium_rate <= 25:
            return 55 - (premium_rate - 10) * 2.0   # 25%→25
        if premium_rate <= 50:
            return 25 - (premium_rate - 25) * 0.8   # 50%→5
        return max(5.0, 5 - (premium_rate - 50) * 0.1)

    @staticmethod
    def _momentum_score(pct_changes: list) -> float:
        """V2: CB momentum score from recent daily returns. 0-100."""
        if not pct_changes:
            return 50.0
        valid = [p for p in pct_changes if p is not None]
        if not valid:
            return 50.0
        # Weighted: more recent = higher weight
        weights = list(reversed(range(1, len(valid) + 1)))
        weighted_sum = sum(w * v for w, v in zip(weights, valid))
        total_weight = sum(weights)
        avg = weighted_sum / total_weight if total_weight > 0 else 0
        # -5% daily avg → 0, 0% → 50, +5% → 100
        return min(100, max(0, 50 + avg * 10))

    @staticmethod
    def _volume_score(vol_amounts: list) -> float:
        """V2: CB volume activity score. Higher volume = more liquid. 0-100."""
        if not vol_amounts:
            return 50.0
        valid = [a for a in vol_amounts if a is not None and a > 0]
        if not valid:
            return 50.0
        avg_amount = sum(valid) / len(valid) / 1e4  # avg daily amount in 万
        # <10万 → 10, 100万 → 50, >1000万 → 100
        if avg_amount >= 1000:
            return 100.0
        if avg_amount >= 100:
            return 50 + (avg_amount - 100) / 900 * 50
        if avg_amount >= 10:
            return 10 + (avg_amount - 10) / 90 * 40
        return max(5.0, avg_amount)

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
            return 90 - (size_yi - 1) * 15
        if size_yi <= 5:
            return 60 - (size_yi - 3) * 12.5
        if size_yi <= 10:
            return 35 - (size_yi - 5) * 3
        if size_yi <= 20:
            return 20 - (size_yi - 10) * 1
        return max(5.0, 10 - size_yi * 0.1)

    @staticmethod
    def _rating_penalty(rating: str) -> float:
        """V2: Soft penalty for missing/low rating. Returns 0 to -15."""
        if not rating:
            return -10.0  # No rating = moderate penalty
        r = rating.upper().strip()
        if any(r.startswith(p) for p in ("AAA", "AA", "A")):
            return 0.0   # A and above = no penalty
        if r.startswith("BBB"):
            return -5.0
        if r.startswith("BB"):
            return -10.0
        return -15.0  # B or below

    # ── Main run ──

    def run(self, top_n: int = 20, trade_date: str = None, **kwargs) -> list[dict]:
        """Execute convertible bond floor-price screening V2.

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

        logger.info("CbFloorEngine V2: screening for %s, top_n=%d", trade_date, top_n)

        # ── Query: join cb_basic + cb_daily latest + stock kline + stock info ──
        query = """
        SELECT
            cb.ts_code, cb.bond_short_name, cb.stk_code, cb.stk_short_name,
            cb.maturity_date, cb.coupon_rate, cb.remain_size,
            cb.newest_rating, cb.issue_rating, cb.par,
            cb.conv_price, cb.list_date,
            d.close, d.cb_over_rate, d.pct_chg, d.amount,
            s.industry,
            sk.close AS stock_close,
            sk.change_pct AS stock_pct_chg
        FROM cb_basic cb
        LEFT JOIN cb_daily d ON cb.ts_code = d.ts_code AND d.trade_date = %s
        LEFT JOIN stocks s ON SPLIT_PART(cb.stk_code, '.', 1) = s.code
        LEFT JOIN daily_kline sk ON SPLIT_PART(cb.stk_code, '.', 1) = sk.code AND sk.trade_date = %s
        WHERE cb.delist_date IS NULL OR cb.delist_date > %s::date
        """
        cur.execute(query, (trade_date, trade_date, trade_date))
        rows = cur.fetchall()

        if not rows:
            logger.warning("CbFloorEngine V2: no CB data for %s", trade_date)
            return []

        # Build {ts_code: row} map
        row_map = {}
        for r in rows:
            row_map[r[0]] = r

        # ── Pre-fetch: CB daily history for momentum + volume ──
        cb_daily_history = {}  # {ts_code: [(date, close, pct_chg, amount), ...]}
        cur.execute(
            "SELECT ts_code, trade_date, close, pct_chg, amount FROM cb_daily "
            "WHERE trade_date <= %s AND trade_date >= %s::date - INTERVAL '15 days' "
            "ORDER BY ts_code, trade_date DESC",
            (trade_date, trade_date),
        )
        for r in cur.fetchall():
            cb_daily_history.setdefault(r[0], []).append(r[1:])

        # ── Pre-fetch: stock daily history for momentum ──
        stock_daily_history = {}  # {code: [(date, close, change_pct), ...]}
        cur.execute(
            "SELECT code, trade_date, close, change_pct FROM daily_kline "
            "WHERE trade_date <= %s AND trade_date >= %s::date - INTERVAL '10 days' "
            "ORDER BY code, trade_date DESC",
            (trade_date, trade_date),
        )
        for r in cur.fetchall():
            stock_daily_history.setdefault(r[0], []).append(r[1:])

        # ── Pre-fetch: price change history ──
        cur.execute(
            "SELECT ts_code, change_date, pre_price, new_price, change_reason "
            "FROM cb_price_chg ORDER BY ts_code, change_date DESC"
        )
        price_chg_map = {}
        for r in cur.fetchall():
            price_chg_map.setdefault(r[0], []).append(r)

        # ── Pre-fetch: hot themes ──
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

        # ── Resolve stock codes without suffix ──
        def _strip_code(ts_code: str) -> str:
            return ts_code.split(".")[0] if ts_code and "." in ts_code else (ts_code or "")

        # ── Score each CB ──
        picks = []
        for r in rows:
            try:
                (
                    ts_code, name, stk_code_ts, stk_name,
                    maturity_date_, coupon_rate, remain_size,
                    newest_rating, issue_rating, par,
                    conv_price, list_date_,
                    close, cb_over_rate, pct_chg, amount,
                    industry,
                    stock_close, stock_pct_chg,
                ) = r

                stk_code_raw = _strip_code(stk_code_ts or "")

                # ── Hard exclude: maturity < 3 months ──
                if maturity_date_:
                    if isinstance(maturity_date_, str):
                        mat_dt = datetime.strptime(maturity_date_, "%Y-%m-%d").date()
                    else:
                        mat_dt = maturity_date_
                    days_left = (mat_dt - date.today()).days
                    if days_left < 90:
                        continue

                # ── Calculate premium rate ──
                if cb_over_rate is None and conv_price and stock_close and close and conv_price > 0 and stock_close > 0:
                    conv_value = 100.0 / float(conv_price) * float(stock_close)
                    if conv_value > 0:
                        cb_over_rate = (float(close) / conv_value - 1) * 100

                # ── Factor 1: Premium rate (30%) ──
                premium_score = self._premium_score(cb_over_rate)

                # ── Factor 2: CB Momentum (15%) ──
                cb_hist = cb_daily_history.get(ts_code, [])
                # cb_hist elements: (trade_date, close, pct_chg, amount) — indices (0,1,2,3)
                # Compute daily returns from consecutive closes
                cb_closes = [(h[0], h[1]) for h in cb_hist[:11] if h[1] is not None and h[1] > 0]
                cb_changes = []
                for i in range(min(len(cb_closes) - 1, 10)):
                    prev_c = cb_closes[i + 1][1]
                    cur_c = cb_closes[i][1]
                    if prev_c and cur_c and prev_c > 0:
                        cb_changes.append((cur_c / prev_c - 1) * 100)
                momentum_score = self._momentum_score(cb_changes)

                # ── Factor 3: YTM (10%) ──
                ytm_score = self._score_ytm(close, coupon_rate, par, maturity_date_)

                # ── Factor 4: Stock Momentum (10%) ──
                stk_hist = stock_daily_history.get(stk_code_raw, [])
                # stk_hist elements: (trade_date, close, change_pct)  — indices (0, 1, 2)
                # Compute daily returns from consecutive closes (change_pct often NULL)
                stk_closes = [(h[0], h[1]) for h in stk_hist[:6] if h[1] is not None and h[1] > 0]
                stk_changes = []
                for i in range(len(stk_closes) - 1):
                    prev_close = stk_closes[i + 1][1]
                    cur_close = stk_closes[i][1]
                    if prev_close and cur_close and prev_close > 0:
                        stk_changes.append((cur_close / prev_close - 1) * 100)
                # Fallback to DB change_pct if no computed changes
                if not stk_changes:
                    stk_changes = [h[2] for h in stk_hist[:5] if len(h) > 2 and h[2] is not None]
                stock_momentum = self._momentum_score(stk_changes)

                # ── Factor 5: Recent downward revision (10%) ──
                revision_score = self._score_recent_revision(ts_code, price_chg_map)

                # ── Factor 6: Hot theme (5%) ──
                theme_score = 80.0 if industry and industry in hot_industries else 40.0

                # ── Factor 7: Downward revision history (5%) ──
                history_score = self._score_revision_history(ts_code, price_chg_map)

                # ── Factor 8: Size (5%) ──
                size_score = self._size_score(remain_size)

                # ── Factor 9: Non-SOE (5%) ──
                soe_score = self._score_ownership(cur, stk_code_raw)

                # ── Factor 10: Volume activity (5%) ──
                # cb_hist elements: (trade_date, close, pct_chg, amount) — amount at index 3
                cb_amounts = [h[3] for h in cb_hist[:5] if len(h) > 3 and h[3] is not None and h[3] > 0]
                volume_score = self._volume_score(cb_amounts)

                # ── Factor 11: Rating soft penalty ──
                rating = newest_rating or issue_rating or ""
                rating_penalty = self._rating_penalty(rating)

                # ── Weighted total ──
                total = (
                    premium_score * 0.30
                    + momentum_score * 0.15
                    + ytm_score * 0.10
                    + stock_momentum * 0.10
                    + revision_score * 0.10
                    + theme_score * 0.05
                    + history_score * 0.05
                    + size_score * 0.05
                    + soe_score * 0.05
                    + volume_score * 0.05
                    + rating_penalty
                )

                # Grade (adjusted thresholds V2)
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
                    "name": name or ts_code,
                    "stk_code": stk_code_raw,
                    "stk_name": stk_name,
                    "industry": industry,
                    "price": round(close, 2) if close else None,
                    "premium_rate": round(cb_over_rate, 2) if cb_over_rate else None,
                    "remain_size_yi": round(remain_size / 1e8, 2) if remain_size else None,
                    "maturity_date": str(maturity_date_) if maturity_date_ else None,
                    "rating": rating,
                    "cb_momentum": round(sum(cb_changes[:5]) if cb_changes else 0, 2),
                    "stock_momentum": round(sum(stk_changes[:3]) if stk_changes else 0, 2),
                    "total_score": round(total, 1),
                    "grade": grade,
                    "details": {
                        "premium_score": round(premium_score, 1),
                        "momentum_score": round(momentum_score, 1),
                        "ytm_score": round(ytm_score, 1),
                        "stock_momentum": round(stock_momentum, 1),
                        "revision_score": round(revision_score, 1),
                        "theme_score": round(theme_score, 1),
                        "history_score": round(history_score, 1),
                        "size_score": round(size_score, 1),
                        "soe_score": round(soe_score, 1),
                        "volume_score": round(volume_score, 1),
                        "rating_penalty": round(rating_penalty, 1),
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
            "CbFloorEngine V2: %d picks from %d CBs (%.1fs)",
            len(picks), len(rows), elapsed,
        )

        return picks

    # ── Factor implementations ──

    def _score_ytm(self, close, coupon_rate, par, maturity_date_):
        """Score yield-to-maturity. Higher YTM = higher score. V2: reduced impact."""
        if not close or close <= 0:
            return 30.0
        if not coupon_rate:
            coupon_rate = 0.0
        if not par:
            par = 100.0

        years_left = 3.0
        if maturity_date_:
            if isinstance(maturity_date_, str):
                mat_dt = datetime.strptime(maturity_date_, "%Y-%m-%d").date()
            else:
                mat_dt = maturity_date_
            years_left = max(0.1, (mat_dt - date.today()).days / 365.25)

        annual_coupon = par * coupon_rate / 100.0
        capital_gain = (par - close) / years_left
        ytm = (annual_coupon + capital_gain) / close * 100

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

    def _score_recent_revision(self, ts_code, price_chg_map, days=10) -> float:
        """Score recent downward conversion price revision. 0-100."""
        changes = price_chg_map.get(ts_code, [])
        if not changes:
            return 30.0

        cutoff = date.today()
        for chg_date, pre_price, new_price, reason in changes:
            if isinstance(chg_date, str):
                chg_date = datetime.strptime(chg_date, "%Y-%m-%d").date()
            if (cutoff - chg_date).days <= days and new_price and pre_price:
                if new_price < pre_price:
                    return 100.0

        for _, pre_price, new_price, reason in changes:
            if new_price and pre_price and new_price < pre_price:
                return 60.0

        return 30.0

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
                    downward_count += 1

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
                if any(kw in legal for kw in ("国有", "央企", "地方国企", "国资委", "国资")):
                    return 20.0
                return 90.0
        except Exception:
            pass

        if stk_code.startswith("6"):
            return 40.0
        return 70.0
