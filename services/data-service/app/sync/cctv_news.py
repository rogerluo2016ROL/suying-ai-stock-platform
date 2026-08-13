"""新闻联播文字稿同步 — Tushare cctv_news API.

数据范围: 近 10 年央视新闻联播文本.
新闻联播是政策风向标, 领导人讲话和重点报道往往预示政策方向转变.
"""

import logging, sqlite3, time
from datetime import date, timedelta

logger = logging.getLogger("data-service.cctv_news")


def sync_cctv_news(days_back: int = 7) -> dict:
    """同步新闻联播文字稿 — 按日期逐日拉取.

    API: pro.cctv_news(date=YYYYMMDD)
    输出: datetime, title, content, channels

    Args:
        days_back: 回补天数, 默认 7 天

    Returns:
        {"table": "cctv_news", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH, SQLITE_FALLBACK_ENABLED
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()
    today = date.today()
    total_rows = 0
    pg_written = 0

    for i in range(days_back):
        d = today - timedelta(days=i)
        d_str = d.strftime("%Y%m%d")
        d_iso = d.strftime("%Y-%m-%d")

        rate_limit()
        try:
            df = pro.cctv_news(date=d_str)
        except Exception as e:
            logger.debug("cctv_news %s failed: %s", d_str, e)
            continue

        if df is None or len(df) == 0:
            continue

        rows = []
        for _, r in df.iterrows():
            title = str(r.get("title", ""))
            if not title:
                continue
            rows.append((
                d_iso,
                title,
                str(r.get("content", "")),
                str(r.get("channels", "")),
            ))

        if not rows:
            continue

        # ── PG 直写 ──
        try:
            from app.sync.pg_writer import _pg_write
            pg_written += _pg_write(
                "cctv_news",
                ["pub_date", "title", "content", "channels"],
                ["pub_date", "title"],
                rows,
            )
        except Exception as e:
            logger.warning("PG write cctv_news failed: %s", e)

        # ── SQLite fallback ──
        if SQLITE_FALLBACK_ENABLED:
            try:
                db = sqlite3.connect(DB_PATH)
                db.executemany(
                    "INSERT OR REPLACE INTO cctv_news(pub_date, title, content, channels) "
                    "VALUES(?,?,?,?)", rows)
                db.commit(); db.close()
            except Exception as e:
                logger.warning("SQLite write cctv_news failed: %s", e)

        total_rows += len(rows)

    elapsed = time.time() - t0
    logger.info("cctv_news: %d rows over %d days, PG=%d, %.1fs",
                total_rows, days_back, pg_written, elapsed)
    return {
        "table": "cctv_news",
        "written": total_rows,
        "pg_written": pg_written,
        "days_back": days_back,
        "elapsed": elapsed,
    }
