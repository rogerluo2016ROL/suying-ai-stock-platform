"""韩股行情同步 — Naver Finance 移动端 JSON API.

Tushare 无韩股个股数据, akshare 全球接口在本环境不可用 (Step 0 实测);
Naver m.stock.naver.com 提供 KOSPI/KOSDAQ 全市场快照 (市值排序分页, 字段含涨跌幅/成交额).
9:05 早报取开盘首小时数据 (韩国 9:00 开盘 = 北京 8:00).
"""

import json
import logging
import time
import urllib.request
from datetime import date, datetime

logger = logging.getLogger("data-service.kr_market")

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_TIMEOUT = 20
_MAX_PAGES_PER_MARKET = 20  # KOSPI ~10页, KOSDAQ ~17页 (pageSize=100)


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _fetch_market(market: str) -> list[tuple]:
    rows: list[tuple] = []
    today = date.today().isoformat()
    now = datetime.now().replace(microsecond=0)
    for page in range(1, _MAX_PAGES_PER_MARKET + 1):
        url = (f"https://m.stock.naver.com/api/stocks/marketValue/{market}"
               f"?page={page}&pageSize=100")
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception as e:
            logger.warning("naver %s page %d failed: %s", market, page, e)
            break
        stocks = (data or {}).get("stocks") or []
        if not stocks:
            break
        for s in stocks:
            code = str(s.get("itemCode") or "")
            pct = _num(s.get("fluctuationsRatio"))
            if not code or pct is None:
                continue
            rows.append((
                today, code,
                str(s.get("stockName") or ""),
                market, pct,
                _num(s.get("accumulatedTradingValue")),   # 百万韩元
                _num(s.get("accumulatedTradingVolume")),
                now,
            ))
        if len(stocks) < 100:
            break
    return rows


def sync_kr_daily(days_back: int = 1) -> dict:
    """同步韩股全市场快照 (KOSPI + KOSDAQ). 盘中每次调用覆盖当日快照语义:
    先删当日旧快照再写入 (同日 ON CONFLICT DO NOTHING 无法更新盘中数据)."""
    from app.sync.pg_writer import PG_URL, _pg_write

    t0 = time.time()
    rows = _fetch_market("KOSPI") + _fetch_market("KOSDAQ")

    pg_written = 0
    if rows:
        # 同日重跑时替换旧快照 (盘中数据会变化)
        try:
            import psycopg2
            with psycopg2.connect(PG_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM kr_stock_daily WHERE trade_date = %s",
                                (rows[0][0],))
        except Exception as e:
            logger.warning("kr_stock_daily delete-old failed: %s", e)
        try:
            pg_written = _pg_write(
                "kr_stock_daily",
                ["trade_date", "code", "name", "market", "pct_chg", "amount", "volume", "snapshot_ts"],
                ["trade_date", "code"],
                rows,
            )
        except Exception as e:
            logger.warning("PG write kr_stock_daily failed: %s", e)

    elapsed = time.time() - t0
    logger.info("kr_daily: rows=%d pg=%d %.1fs", len(rows), pg_written, elapsed)
    return {"table": "kr_stock_daily", "written": len(rows),
            "pg_written": pg_written, "elapsed": elapsed}
