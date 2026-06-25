"""央行货币政策执行报告同步 — Tushare monetary_policy API.

独立权限接口: ¥200/年.
数据范围: 2001 年至今, 每季度一篇.
央行货币政策报告是宏观环境评估的核心数据源.
"""

import logging, sqlite3, time

logger = logging.getLogger("data-service.mp_report")


def sync_mp_report(days_back: int = 90) -> dict:
    """同步央行货币政策执行报告.

    API: pro.monetary_policy(start_date, end_date, fields=...)
    输出: pub_date, title, url, pdf_url, content_html

    全量数据仅约 100 条 (每季度一篇), 一次调用即可全部拉取.

    Args:
        days_back: 回补天数, 默认 90 天 (覆盖一个季度)

    Returns:
        {"table": "mp_report", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH, SQLITE_FALLBACK_ENABLED
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()

    rate_limit()
    try:
        df = pro.monetary_policy(
            fields="pub_date,title,url,pdf_url,content_html"
        )
    except Exception as e:
        return {"status": "error", "reason": str(e)[:200]}

    if df is None or len(df) == 0:
        return {"table": "mp_report", "written": 0, "note": "no data"}

    rows = []
    for _, r in df.iterrows():
        pub_date_str = str(r.get("pub_date", ""))
        pub_date = (f"{pub_date_str[:4]}-{pub_date_str[4:6]}-{pub_date_str[6:8]}"
                   if len(pub_date_str) == 8 else pub_date_str)
        title = str(r.get("title", ""))
        if not title:
            continue
        rows.append((
            pub_date,
            title,
            str(r.get("url", "")),
            str(r.get("pdf_url", "")),
            str(r.get("content_html", ""))[:50000],
        ))

    # ── PG 直写 ──
    pg_written = 0
    if rows:
        try:
            from app.sync.pg_writer import _pg_write
            pg_written = _pg_write(
                "mp_report",
                ["pub_date", "title", "url", "pdf_url", "content_html"],
                ["pub_date", "title"],
                rows,
            )
        except Exception as e:
            logger.debug("PG write mp_report skipped: %s", e)

    # ── SQLite fallback ──
    if rows and SQLITE_FALLBACK_ENABLED:
        try:
            db = sqlite3.connect(DB_PATH)
            db.executemany(
                "INSERT OR REPLACE INTO mp_report(pub_date, title, url, pdf_url, content_html) "
                "VALUES(?,?,?,?,?)", rows)
            db.commit(); db.close()
        except Exception as e:
            logger.warning("SQLite write mp_report failed: %s", e)

    elapsed = time.time() - t0
    logger.info("mp_report: %d reports, PG=%d, %.1fs", len(rows), pg_written, elapsed)
    return {
        "table": "mp_report",
        "written": len(rows),
        "pg_written": pg_written,
        "elapsed": elapsed,
    }
