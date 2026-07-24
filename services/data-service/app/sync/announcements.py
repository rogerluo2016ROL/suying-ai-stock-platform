"""上市公司公告同步 — Tushare anns_d API.

独立权限接口（¥1,000/年），不含在积分体系内。
每日盘后拉取全市场公告标题+PDF链接，写入 PG (主) + SQLite (fallback)。
"""

import logging, sqlite3, time
from datetime import date, timedelta

logger = logging.getLogger("data-service.announcements")


def sync_announcements(days_back: int = 7) -> dict:
    """同步上市公司公告 — 按日期批量拉取全市场公告.

    API: pro.anns_d(ann_date=YYYYMMDD) → ann_date, ts_code, name, title, url
    每次调用返回当日所有公告，无需按股票分页。

    Args:
        days_back: 回补天数，默认 7 天

    Returns:
        {"table": "announcements", "written": N, "pg_written": N, "elapsed": S}
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
        d = (today - timedelta(days=i))
        d_str = d.strftime("%Y%m%d")
        d_iso = d.strftime("%Y-%m-%d")

        rate_limit()
        try:
            df = pro.anns_d(ann_date=d_str)
        except Exception as e:
            logger.debug("anns_d %s failed: %s", d_str, e)
            continue

        if df is None or len(df) == 0:
            continue

        rows = []
        for _, r in df.iterrows():
            ts_code = str(r.get("ts_code", ""))
            code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code
            title = str(r.get("title", ""))
            url = str(r.get("url", ""))
            rec_time = str(r.get("rec_time", "") or "").strip()
            # PG rec_time 是 timestamp 列, 空串/'nan' 会整批报 invalid input syntax —— 归一为 NULL
            if rec_time.lower() in ("", "nan", "nat", "none"):
                rec_time = None

            # 跳过无效行
            if not title:
                continue

            rows.append((code, d_iso, title, url, rec_time))

        if not rows:
            continue

        # ── PG 直写 (主路径) ──
        if rows:
            try:
                from app.sync.pg_writer import _pg_write
                pg_w = _pg_write(
                    "announcements",
                    ["code", "ann_date", "title", "url", "rec_time"],
                    ["code", "ann_date", "title"],
                    rows,
                )
                pg_written += pg_w
            except Exception as e:
                logger.debug("PG write announcements %s skipped: %s", d_iso, e)

        # ── SQLite 写入 (fallback) ──
        if SQLITE_FALLBACK_ENABLED:
            try:
                db = sqlite3.connect(DB_PATH)
                db.executemany(
                    "INSERT OR REPLACE INTO announcements(code, ann_date, title, url, rec_time) "
                    "VALUES(?,?,?,?,?)",
                    rows,
                )
                db.commit()
                db.close()
            except Exception as e:
                logger.warning("SQLite write announcements %s failed: %s", d_iso, e)

        total_rows += len(rows)

    elapsed = time.time() - t0
    logger.info("announcements: %d rows over %d days, PG=%d, %.1fs",
                total_rows, days_back, pg_written, elapsed)
    return {
        "table": "announcements",
        "written": total_rows,
        "pg_written": pg_written,
        "days_back": days_back,
        "elapsed": elapsed,
    }
