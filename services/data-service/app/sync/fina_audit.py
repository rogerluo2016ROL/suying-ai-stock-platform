"""财务审计意见同步 — Tushare fina_audit API.

积分要求: 2000pts.
按股票代码逐只拉取审计意见 (API 要求 ts_code 为必选参数).
审计意见类型是识别财务造假风险的关键信号.
"""

import logging, sqlite3, time
from datetime import date

logger = logging.getLogger("data-service.fina_audit")


def _recent_years(n: int = 3) -> tuple[str, str]:
    """返回最近 N 年的 start_date 和 end_date (YYYYMMDD)."""
    today = date.today()
    start = date(today.year - n, 1, 1)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def _get_all_stock_codes() -> list[str]:
    """从 PG 获取全市场股票代码列表."""
    import os
    pg_url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    try:
        import psycopg2
        conn = psycopg2.connect(pg_url, connect_timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT code FROM stocks WHERE listed_date IS NOT NULL ORDER BY code")
        codes = [r[0] for r in cur.fetchall()]
        conn.close()
        if codes:
            return codes
    except Exception as e:
        logger.debug("PG stocks query failed: %s", e)

    # Fallback: SQLite
    from app.config import DB_PATH
    try:
        db = sqlite3.connect(DB_PATH)
        rows = db.execute("SELECT code FROM stocks ORDER BY code").fetchall()
        db.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def _ts_code(code: str) -> str:
    """6-digit code → Tushare ts_code (000001.SZ)."""
    if "." in str(code):
        return str(code)
    c = str(code)
    if c.startswith("6") or c.startswith("5"):
        return f"{c}.SH"
    elif c.startswith("9") or c.startswith("4") or c.startswith("8"):
        return f"{c}.BJ"
    else:
        return f"{c}.SZ"


def sync_fina_audit(days_back: int = 365) -> dict:
    """同步财务审计意见 — 逐只股票拉取最近 N 年审计记录.

    API: pro.fina_audit(ts_code=XXX, start_date=YYYYMMDD, end_date=YYYYMMDD)
    输出: ann_date, end_date, audit_result, audit_fees, audit_agency, audit_sign

    审计意见类型 (audit_result):
      - 标准无保留意见 (clean opinion — 最健康)
      - 带强调事项段的无保留意见
      - 保留意见 (qualified — 风险信号)
      - 否定意见 (adverse — 强风险信号)
      - 无法表示意见 (disclaimer — 强风险信号)

    Args:
        days_back: 回补天数, 默认 365 天 (覆盖最近 3 年审计记录)

    Returns:
        {"table": "fina_audit", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()

    codes = _get_all_stock_codes()
    if not codes:
        return {"status": "skipped", "reason": "no stock codes found"}

    start_date, end_date = _recent_years(max(days_back // 365, 1) + 1)
    total_rows = 0
    pg_written = 0

    for i, code in enumerate(codes):
        rate_limit()
        try:
            df = pro.fina_audit(ts_code=_ts_code(code), start_date=start_date, end_date=end_date)
        except Exception:
            continue

        if df is None or len(df) == 0:
            continue

        rows = []
        for _, r in df.iterrows():
            ann_date_str = str(r.get("ann_date", ""))
            ann_date = (f"{ann_date_str[:4]}-{ann_date_str[4:6]}-{ann_date_str[6:8]}"
                        if len(ann_date_str) == 8 else ann_date_str)
            end_date_str = str(r.get("end_date", ""))
            end_date_val = (f"{end_date_str[:4]}-{end_date_str[4:6]}-{end_date_str[6:8]}"
                            if len(end_date_str) == 8 else end_date_str)
            rows.append((
                code,
                ann_date,
                end_date_val,
                str(r.get("audit_result", "")),
                r.get("audit_fees"),
                str(r.get("audit_agency", "")),
                str(r.get("audit_sign", "")),
            ))

        if not rows:
            continue

        # ── PG 直写 (主路径) ──
        try:
            from app.sync.pg_writer import _pg_write
            pg_w = _pg_write(
                "fina_audit",
                ["code", "ann_date", "end_date", "audit_result", "audit_fees",
                 "audit_agency", "audit_sign"],
                ["code", "end_date"],
                rows,
            )
            pg_written += pg_w
        except Exception as e:
            logger.debug("PG write fina_audit skipped: %s", e)

        # ── SQLite 写入 (fallback) ──
        try:
            db = sqlite3.connect(DB_PATH)
            db.executemany(
                "INSERT OR REPLACE INTO fina_audit(code, ann_date, end_date, audit_result, "
                "audit_fees, audit_agency, audit_sign) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            db.commit()
            db.close()
        except Exception as e:
            logger.debug("SQLite write fina_audit failed: %s", e)

        total_rows += len(rows)

        if (i + 1) % 500 == 0:
            logger.info("fina_audit: %d/%d stocks, %d rows", i + 1, len(codes), total_rows)

    elapsed = time.time() - t0
    logger.info("fina_audit: %d rows from %d stocks, PG=%d, %.1fs",
                total_rows, len(codes), pg_written, elapsed)
    return {
        "table": "fina_audit",
        "written": total_rows,
        "pg_written": pg_written,
        "stocks_processed": len(codes),
        "elapsed": elapsed,
    }
