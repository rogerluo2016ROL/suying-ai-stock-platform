"""主营业务构成同步 — Tushare fina_mainbz_vip API.

积分要求: 5000pts (fina_mainbz_vip 按报告期获取全市场数据).
"""

import logging, sqlite3, time
from datetime import date

logger = logging.getLogger("data-service.fina_mainbz")


def _recent_quarters(n: int = 4) -> list[str]:
    """Compute the N most recent quarter-end dates (YYYYMMDD)."""
    today = date.today()
    quarters = []
    for year in range(today.year, today.year - 3, -1):
        for m, d in [("12", "31"), ("09", "30"), ("06", "30"), ("03", "31")]:
            try:
                from datetime import datetime
                qd = datetime(year, int(m), int(d)).date()
            except ValueError:
                continue
            if qd <= today:
                quarters.append(qd.strftime("%Y%m%d"))
            if len(quarters) >= n + 2:
                break
        if len(quarters) >= n + 2:
            break
    return sorted(set(quarters), reverse=True)[:n]


def sync_fina_mainbz(days_back: int = 120) -> dict:
    """同步主营业务构成 — 按报告期获取全市场数据.

    API: pro.fina_mainbz_vip(period=YYYYMMDD, type='P')
    获取某一季度全部上市公司的主营业务构成 (按产品分类).

    Args:
        days_back: 回补天数, 默认 120 天 (覆盖最近 1-2 个季度)

    Returns:
        {"table": "fina_mainbz", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH, SQLITE_FALLBACK_ENABLED
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()
    periods = _recent_quarters(max(days_back // 90, 1))
    total_rows = 0
    pg_written = 0

    for period in periods:
        # 拉取按产品分类的主营业务构成
        for biz_type in ("P", "D", "I"):
            rate_limit()
            try:
                df = pro.fina_mainbz_vip(period=period, type=biz_type)
            except Exception as e:
                logger.debug("fina_mainbz_vip period=%s type=%s failed: %s", period, biz_type, e)
                continue

            if df is None or len(df) == 0:
                continue

            rows = []
            for _, r in df.iterrows():
                ts_code = str(r.get("ts_code", ""))
                code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code
                end_date_str = str(r.get("end_date", ""))
                end_date = (f"{end_date_str[:4]}-{end_date_str[4:6]}-{end_date_str[6:8]}"
                            if len(end_date_str) == 8 else end_date_str)
                biz_item = str(r.get("bz_item", ""))
                biz_sales = r.get("bz_sales")

                if not biz_item or biz_sales is None:
                    continue

                rows.append((code, end_date, biz_item, float(biz_sales), biz_type))

            if not rows:
                continue

            # ── PG 直写 (主路径) ──
            try:
                from app.sync.pg_writer import _pg_write
                pg_w = _pg_write(
                    "fina_mainbz",
                    ["code", "end_date", "biz_item", "biz_income", "biz_type"],
                    ["code", "end_date", "biz_item"],
                    rows,
                )
                pg_written += pg_w
            except Exception as e:
                logger.warning("PG write fina_mainbz failed: %s", e)

            # ── SQLite 写入 (fallback) ──
            if SQLITE_FALLBACK_ENABLED:
                try:
                    db = sqlite3.connect(DB_PATH)
                    db.executemany(
                        "INSERT OR REPLACE INTO fina_mainbz(code, end_date, biz_item, biz_income) "
                        "VALUES(?,?,?,?)",
                        [(r[0], r[1], r[2], r[3]) for r in rows],
                    )
                    db.commit()
                    db.close()
                except Exception as e:
                    logger.warning("SQLite write fina_mainbz failed: %s", e)

            total_rows += len(rows)
            logger.debug("fina_mainbz period=%s type=%s: %d rows", period, biz_type, len(rows))

    elapsed = time.time() - t0
    logger.info("fina_mainbz: %d rows over %d periods, PG=%d, %.1fs",
                total_rows, len(periods) * 3, pg_written, elapsed)
    return {
        "table": "fina_mainbz",
        "written": total_rows,
        "pg_written": pg_written,
        "periods": len(periods),
        "elapsed": elapsed,
    }
