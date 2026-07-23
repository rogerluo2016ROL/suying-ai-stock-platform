"""美股行情 + 全球指数同步 — Tushare VIP 主源, 东财 push2 兜底.

- sync_us_daily:   Tushare us_daily(trade_date=...) 全市场日线 (8:00 早报用前一夜美股收盘).
                   Tushare 单次上限 8000 行, offset 翻页; 数据未更新时回退东财实时快照.
- sync_us_basic:   Tushare us_basic 周级刷新 (ts_code → 中/英文名称映射).
- sync_global_index: Tushare index_global (IXIC/DJI/SPX/N225/KS11).
"""

import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

logger = logging.getLogger("data-service.us_market")

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# Tushare index_global 常用代码: 纳指/道指/标普/日经/韩国综合
GLOBAL_INDEX_CODES = ["IXIC", "DJI", "SPX", "N225", "KS11"]


def _pro():
    from app.config import TUSHARE_TOKEN
    if not TUSHARE_TOKEN:
        return None
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    return ts.pro_api()


# ── 美股日线 (Tushare 主源) ────────────────────────────────────────────────

def _fetch_us_daily_tushare(trade_date: str) -> list[tuple]:
    """按交易日拉全市场美股日线, offset 翻页 (单页上限 8000)."""
    pro = _pro()
    if pro is None:
        return []
    from app.sync.rate_limiter import rate_limit

    rows: list[tuple] = []
    for offset in range(0, 24000, 8000):
        rate_limit()
        try:
            df = pro.us_daily(trade_date=trade_date, offset=offset, limit=8000)
        except Exception as e:
            logger.debug("us_daily %s offset=%d failed: %s", trade_date, offset, e)
            break
        if df is None or len(df) == 0:
            break
        for _, r in df.iterrows():
            rows.append((
                trade_date,
                str(r.get("ts_code", "")),
                _f(r.get("close")), _f(r.get("pct_change")),
                _f(r.get("vol")), _f(r.get("amount")),
                "tushare", None,
            ))
        if len(df) < 8000:
            break
    return rows


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── 美股实时快照 (东财 push2 兜底) ─────────────────────────────────────────

def fetch_us_spot_eastmoney(pages: int = 6, page_size: int = 100) -> list[tuple]:
    """东财美股行情 (按涨幅降序取前 N 页 — 早报只需热门股, 不全量).

    返回 (trade_date, ts_code, close, pct_chg, vol, amount, source, snapshot_ts).
    trade_date 用北京日期 (快照时刻对应的当次美股交易时段).
    """
    rows: list[tuple] = []
    today = date.today().isoformat()
    now = datetime.now().replace(microsecond=0)
    for pn in range(1, pages + 1):
        params = {
            "pn": pn, "pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:105,m:106,m:107",
            "fields": "f12,f14,f2,f3,f5,f6",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        }
        url = "https://push2.eastmoney.com/api/qt/clist/get?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception as e:
            logger.warning("eastmoney us spot page %d failed: %s", pn, e)
            break
        diff = ((data or {}).get("data") or {}).get("diff") or []
        if not diff:
            break
        for it in diff:
            code = str(it.get("f12") or "")
            if not code or it.get("f3") in (None, "-"):
                continue
            rows.append((
                today, code, _f(it.get("f2")), _f(it.get("f3")),
                _f(it.get("f5")), _f(it.get("f6")),
                "eastmoney", now,
            ))
    return rows


def sync_us_daily(days_back: int = 3) -> dict:
    """同步美股日线: 优先 Tushare (最近 days_back 天内有新数据即写), 全部缺失时东财快照兜底."""
    from app.sync.pg_writer import _pg_write

    t0 = time.time()
    total, pg_written = 0, 0

    today = date.today()
    for i in range(days_back):
        d = (today - timedelta(days=i)).strftime("%Y%m%d")
        rows = _fetch_us_daily_tushare(d)
        if not rows:
            continue
        try:
            pg_written += _pg_write(
                "us_stock_daily",
                ["trade_date", "ts_code", "close", "pct_chg", "vol", "amount", "source", "snapshot_ts"],
                ["trade_date", "ts_code"],
                rows,
            )
            total += len(rows)
        except Exception as e:
            logger.warning("PG write us_stock_daily %s failed: %s", d, e)
        if total:  # 拉到最近一个有数据的交易日即可, 历史回补由更长 days_back 显式触发
            break

    source = "tushare"
    if total == 0:
        spot = fetch_us_spot_eastmoney()
        if spot:
            try:
                pg_written += _pg_write(
                    "us_stock_daily",
                    ["trade_date", "ts_code", "close", "pct_chg", "vol", "amount", "source", "snapshot_ts"],
                    ["trade_date", "ts_code"],
                    spot,
                )
                total = len(spot)
                source = "eastmoney"
            except Exception as e:
                logger.warning("PG write us_stock_daily(eastmoney) failed: %s", e)

    elapsed = time.time() - t0
    logger.info("us_daily: source=%s rows=%d pg=%d %.1fs", source, total, pg_written, elapsed)
    return {"table": "us_stock_daily", "written": total, "pg_written": pg_written,
            "source": source, "elapsed": elapsed}


def sync_us_basic(days_back: int = 0) -> dict:
    """刷新美股基础信息 (全量覆盖写, ON CONFLICT DO NOTHING 足够 — 名称基本不变)."""
    from app.sync.pg_writer import _pg_write

    pro = _pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    from app.sync.rate_limiter import rate_limit

    t0 = time.time()
    rate_limit()
    try:
        df = pro.us_basic(fields="ts_code,name,enname,classify,list_date,delist_date")
    except Exception as e:
        logger.warning("us_basic failed: %s", e)
        return {"table": "us_stock_basic", "written": 0, "error": str(e)[:120]}

    rows = [tuple(x) for x in df.fillna("").itertuples(index=False, name=None)] if df is not None else []
    pg_written = 0
    if rows:
        try:
            pg_written = _pg_write(
                "us_stock_basic",
                ["ts_code", "name", "enname", "classify", "list_date", "delist_date"],
                ["ts_code"],
                rows,
            )
        except Exception as e:
            logger.warning("PG write us_stock_basic failed: %s", e)
    elapsed = time.time() - t0
    logger.info("us_basic: rows=%d pg=%d %.1fs", len(rows), pg_written, elapsed)
    return {"table": "us_stock_basic", "written": len(rows), "pg_written": pg_written, "elapsed": elapsed}


def sync_global_index(days_back: int = 5) -> dict:
    """同步全球指数日线 (纳指/道指/标普/日经/韩国综合)."""
    from app.sync.pg_writer import _pg_write

    pro = _pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    from app.sync.rate_limiter import rate_limit

    t0 = time.time()
    start = (date.today() - timedelta(days=days_back + 5)).strftime("%Y%m%d")
    end = date.today().strftime("%Y%m%d")
    total, pg_written = 0, 0
    for code in GLOBAL_INDEX_CODES:
        rate_limit()
        try:
            df = pro.index_global(ts_code=code, start_date=start, end_date=end)
        except Exception as e:
            logger.debug("index_global %s failed: %s", code, e)
            continue
        if df is None or len(df) == 0:
            continue
        rows = []
        for _, r in df.iterrows():
            td = str(r.get("trade_date", ""))
            rows.append((code, f"{td[:4]}-{td[4:6]}-{td[6:]}",
                         _f(r.get("close")), _f(r.get("pct_chg"))))
        try:
            pg_written += _pg_write(
                "global_index_daily",
                ["ts_code", "trade_date", "close", "pct_chg"],
                ["ts_code", "trade_date"],
                rows,
            )
            total += len(rows)
        except Exception as e:
            logger.warning("PG write global_index_daily %s failed: %s", code, e)
    elapsed = time.time() - t0
    logger.info("global_index: rows=%d pg=%d %.1fs", total, pg_written, elapsed)
    return {"table": "global_index_daily", "written": total, "pg_written": pg_written, "elapsed": elapsed}
