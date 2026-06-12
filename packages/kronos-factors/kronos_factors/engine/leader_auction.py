"""V4.3 竞价超预期战法引擎 — PG 适配版.

从 auction_scalp.py 提取核心评分逻辑, 适配 PostgreSQL 数据源.
供 screener-service orchestrator 调用.

四维评分:
  1. 涨幅超预期 (gap_z vs 历史均值/标准差)
  2. 量能反转 (缩量高开=真需求, 放量高开=出货)
  3. 金额超预期 (amt_z 大资金介入)
  4. 一字板封单检测 (fd_amount > 2亿 = 最强信号)
"""
import os, logging
from collections import defaultdict
import numpy as np

logger = logging.getLogger("kronos.leader_auction")

# V4.3 权重 (2年7218笔回测校准)
WEIGHTS = {
    "gap_surprise": 25,      # 涨幅超预期偏离度
    "sector_context": 25,    # V3.2: 板块联动升权
    "volume_surprise": 20,   # V4.0: 量能反转 (缩量加分!)
    "trap_reversal": 20,     # 弱转强 (昨日套人→今日突破)
    "amount_surprise": 12,   # 金额超预期
    "yizi_direction": 12,    # 一字定方向
    "gap_absolute": 8,       # 高开倒U型 (5-8%甜蜜区间)
    "big_cap_premium": 8,    # 大票抢筹 (>200亿+前日非涨停)
    "price_position": 5,     # 价格位置
    "auction_intensity": 2,  # 竞价强度
}


class AuctionScalpEngine:
    """V4.3 竞价超预期战法 — 9:25 选股, 9:30 前决策."""

    def __init__(self, pg_url: str = None):
        import psycopg2
        self.pg_url = pg_url or os.environ.get(
            "KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
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

    # ── 数据加载 ──

    def _get_auction_snapshot(self, trade_date: str) -> dict:
        """获取竞价快照: code → {open, volume, amount, high, low, close}."""
        cur = self.db.cursor()
        cur.execute("""
            SELECT code, open, high, low, close, vol, amount
            FROM stk_auction_o WHERE trade_date = %s AND open > 0 AND vol > 0
        """, (trade_date,))
        snap = {}
        for r in cur.fetchall():
            snap[r[0]] = {"open": float(r[1]), "high": float(r[2]), "low": float(r[3]),
                          "close": float(r[4]), "volume": float(r[5]), "amount": float(r[6])}
        return snap

    def _get_pre_close_map(self, trade_date: str) -> dict:
        """获取前收盘价 map: code → price."""
        cur = self.db.cursor()
        cur.execute("""
            SELECT a.code, COALESCE(sl.pre_close, d.close)
            FROM stk_auction_o a
            LEFT JOIN stk_limit sl ON sl.code = a.code AND sl.trade_date = a.trade_date
            LEFT JOIN daily_kline d ON d.code = a.code AND d.trade_date = (
                SELECT MAX(trade_date) FROM daily_kline WHERE code = a.code AND trade_date < %s)
            WHERE a.trade_date = %s AND a.open > 0
        """, (trade_date, trade_date))
        return {r[0]: float(r[1]) for r in cur.fetchall() if r[1] and float(r[1]) > 0}

    def _get_auction_history(self, code: str, trade_date: str, lookback: int = 20) -> dict:
        """获取历史竞价统计 或 日线开盘涨幅 fallback.

        优先使用 stk_auction_o 历史, 不足时用 daily_kline 开盘涨幅填充.
        """
        cur = self.db.cursor()
        # Try auction history first
        cur.execute("""
            SELECT a.open, d.close, a.vol, a.amount
            FROM stk_auction_o a
            JOIN daily_kline d ON d.code = a.code AND d.trade_date = (
                SELECT MAX(trade_date) FROM daily_kline WHERE code = a.code AND trade_date < a.trade_date)
            WHERE a.code = %s AND a.trade_date < %s AND a.open > 0 AND d.close > 0
            ORDER BY a.trade_date DESC LIMIT %s
        """, (code, trade_date, lookback))
        rows = cur.fetchall()

        # Fallback: use daily_kline open gaps as proxy
        if len(rows) < 5:
            cur.execute("""
                SELECT open, COALESCE(LAG(close) OVER (ORDER BY trade_date), open), volume, amount
                FROM daily_kline
                WHERE code = %s AND trade_date < %s AND open > 0 AND volume > 0
                ORDER BY trade_date DESC LIMIT %s
            """, (code, trade_date, lookback))
            rows = cur.fetchall()

        if len(rows) < 5:
            return None

        gaps = [(float(r[0]) - float(r[1])) / float(r[1]) * 100 for r in rows if r[1] and float(r[1]) > 0]
        vols = [float(r[2]) for r in rows]
        amts = [float(r[3]) for r in rows]
        if not gaps:
            return None
        return {
            "gap_mean": float(np.mean(gaps)), "gap_std": float(np.std(gaps)) if len(gaps) > 1 else 0.5,
            "vol_mean": float(np.mean(vols)), "vol_std": float(np.std(vols)) if len(vols) > 1 else max(float(np.mean(vols)) * 0.3, 1),
            "amt_mean": float(np.mean(amts)), "amt_std": float(np.std(amts)) if len(amts) > 1 else max(float(np.mean(amts)) * 0.3, 1),
        }

    def _get_sector_auction_stats(self, industry: str, trade_date: str) -> dict:
        """板块竞价统计: 同板块股票竞价均涨幅/量比."""
        cur = self.db.cursor()
        cur.execute("""
            SELECT AVG((a.open - COALESCE(sl.pre_close, d.close)) / NULLIF(COALESCE(sl.pre_close, d.close), 0)) * 100,
                   COUNT(*), AVG(a.vol), AVG(a.amount)
            FROM stk_auction_o a
            JOIN stocks s ON s.code = a.code
            LEFT JOIN stk_limit sl ON sl.code = a.code AND sl.trade_date = a.trade_date
            LEFT JOIN daily_kline d ON d.code = a.code AND d.trade_date = (
                SELECT MAX(trade_date) FROM daily_kline WHERE code = a.code AND trade_date < %s)
            WHERE a.trade_date = %s AND s.industry = %s AND a.open > 0
        """, (trade_date, trade_date, industry))
        r = cur.fetchone()
        if r and r[1] > 0:
            return {"avg_gap": float(r[0] or 0), "count": r[1], "avg_vol": float(r[2] or 0), "avg_amt": float(r[3] or 0)}
        return {"avg_gap": 0, "count": 0, "avg_vol": 0, "avg_amt": 0}

    def _get_yizi_board_seal(self, code: str, trade_date: str) -> float:
        """获取一字板封单金额 (limit_list_d.fd_amount)."""
        cur = self.db.cursor()
        cur.execute("""
            SELECT fd_amount FROM limit_list_d
            WHERE code = %s AND trade_date = %s::date
        """, (code, trade_date))
        r = cur.fetchone()
        return float(r[0] or 0) if r else 0

    def _is_one_char_board(self, code: str, trade_date: str) -> bool:
        """检测是否一字板 (开盘=涨停价)."""
        cur = self.db.cursor()
        cur.execute("""
            SELECT a.open, sl.up_limit
            FROM stk_auction_o a
            JOIN stk_limit sl ON sl.code = a.code AND sl.trade_date = a.trade_date
            WHERE a.code = %s AND a.trade_date = %s
        """, (code, trade_date))
        r = cur.fetchone()
        if r and r[0] and r[1] and r[1] > 0:
            return float(r[0]) >= float(r[1]) * 0.995
        return False

    # ── 核心评分 ──

    def score_auction_stock(self, code: str, trade_date: str, pre_close: float,
                            snap: dict, hist: dict, name: str = "", industry: str = "") -> dict | None:
        """V4.3 竞价单股评分.

        Returns: {code, name, industry, total_score, gap_pct, gap_z, vol_z, amt_z,
                  sector_boost, is_yizi, seal_amount, details} 或 None
        """
        auction_open = snap["open"]
        auction_vol = snap["volume"]
        auction_amt = snap["amount"]

        if auction_open <= 0 or pre_close <= 0:
            return None
        if code.startswith(('92', '83', '87', '4')) or 'ST' in name.upper():
            return None

        gap_pct = (auction_open / pre_close - 1) * 100

        # ── 因子1: 涨幅超预期 (0-30分) ──
        gap_z = (gap_pct - hist["gap_mean"]) / max(hist["gap_std"], 0.01)
        if gap_z >= 3.0: gap_score = 30
        elif gap_z >= 2.0: gap_score = 25
        elif gap_z >= 1.0: gap_score = 18
        elif gap_z >= 0.5: gap_score = 12
        elif gap_z >= 0: gap_score = 6
        else: gap_score = 0

        # ── 因子2: 量能反转 V4.0 (0-25分) ──
        vol_z = (auction_vol - hist["vol_mean"]) / max(hist["vol_std"], 1)
        if vol_z <= -0.5: vol_score = 25      # 🔥缩量高开=真需求
        elif vol_z <= 0: vol_score = 20
        elif vol_z <= 0.5: vol_score = 10
        elif vol_z <= 1.0: vol_score = 5
        elif vol_z <= 2.0: vol_score = 0
        else: vol_score = -15                 # 🔥极度放量=出货

        # ── 因子3: 金额超预期 (0-15分) ──
        amt_z = (auction_amt - hist["amt_mean"]) / max(hist["amt_std"], 1)
        if amt_z >= 3.0: amt_score = 15
        elif amt_z >= 2.0: amt_score = 12
        elif amt_z >= 1.0: amt_score = 8
        elif amt_z >= 0.5: amt_score = 5
        else: amt_score = 2

        # ── 因子4: 一字板封单检测 V4.3 (0-15分) ──
        is_yizi = self._is_one_char_board(code, trade_date)
        seal_amount = self._get_yizi_board_seal(code, trade_date) if is_yizi else 0
        if is_yizi and seal_amount >= 200_000_000: yizi_score = 15   # 封单≥2亿
        elif is_yizi and seal_amount >= 50_000_000: yizi_score = 10  # 封单5000万-2亿
        elif is_yizi: yizi_score = 5                                  # 一字板无封单=危险
        else: yizi_score = 0

        # ── 因子5: 板块联动 V3.2 (0-30分) ──
        sector = self._get_sector_auction_stats(industry, trade_date) if industry else {"avg_gap": 0, "count": 0}
        if sector["count"] >= 3 and sector["avg_gap"] > 0.5:
            sector_score = min(30, int(sector["avg_gap"] * 6 + sector["count"] * 0.5))
        elif sector["count"] >= 3:
            sector_score = 10  # 板块活跃但非领涨
        else:
            sector_score = 0   # 独苗惩罚

        # ── 加权总分 ──
        total = (
            gap_score * WEIGHTS["gap_surprise"] / 25 +
            vol_score * WEIGHTS["volume_surprise"] / 25 +
            amt_score * WEIGHTS["amount_surprise"] / 15 +
            yizi_score * WEIGHTS["yizi_direction"] / 15 +
            sector_score * WEIGHTS["sector_context"] / 30 +
            max(0, min(10, gap_pct * 2)) * WEIGHTS["gap_absolute"] / 10
        )

        return {
            "code": code, "name": name, "industry": industry,
            "total_score": round(total, 1),
            "gap_pct": round(gap_pct, 2),
            "gap_z": round(gap_z, 2), "vol_z": round(vol_z, 2), "amt_z": round(amt_z, 2),
            "is_yizi": is_yizi, "seal_amount": seal_amount,
            "sector_boost": sector_score,
            "details": {
                "gap_score": gap_score, "vol_score": vol_score, "amt_score": amt_score,
                "yizi_score": yizi_score, "sector_score": sector_score,
            }
        }

    # ── 批量评分入口 ──

    def run(self, trade_date: str = None, top_n: int = 20, **kwargs) -> list[dict]:
        """执行 V4.3 竞价选股.

        Args:
            trade_date: 交易日 (YYYY-MM-DD), 默认最新
            top_n: 返回前 N 只
        Returns:
            [{code, name, industry, total_score, gap_pct, ...}, ...]
        """
        if not trade_date:
            cur = self.db.cursor()
            cur.execute("SELECT MAX(trade_date) FROM stk_auction_o")
            trade_date = str(cur.fetchone()[0])

        logger.info("V4.3 Auction screening: %s ...", trade_date)
        import time
        t0 = time.time()

        snap = self._get_auction_snapshot(trade_date)
        pre_closes = self._get_pre_close_map(trade_date)
        logger.info("  snapshot: %d stocks, pre_close: %d", len(snap), len(pre_closes))

        scores = []
        processed = 0
        for code, s in snap.items():
            if code not in pre_closes:
                continue
            if code.startswith(('92', '83', '87', '4')):
                continue
            try:
                # Get name/industry from PG
                cur = self.db.cursor()
                cur.execute("SELECT name, industry FROM stocks WHERE code = %s", (code,))
                r = cur.fetchone()
                name = r[0] if r else ""
                industry = r[1] if r and r[1] else "其他"

                hist = self._get_auction_history(code, trade_date)
                if not hist:
                    continue

                res = self.score_auction_stock(code, trade_date, pre_closes[code],
                                               s, hist, name, industry)
                if res:
                    scores.append(res)
                processed += 1
            except Exception:
                continue

        scores.sort(key=lambda x: -x["total_score"])
        elapsed = time.time() - t0
        logger.info("V4.3 done: %d scored from %d in %.1fs, top score %.1f",
                     len(scores), processed, elapsed,
                     scores[0]["total_score"] if scores else 0)
        return scores[:top_n]
