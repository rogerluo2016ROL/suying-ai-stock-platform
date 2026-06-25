"""互动问答同步 — 深交所互动易 (irm_qa_sz) + 上证e互动 (irm_qa_sh).

独立权限接口: ¥500/年 each.
投资者提问中经常提前暴露风险 (如商誉减值、质押风险等),
公司回复措辞变化也是重要的舆情前瞻信号.
"""

import logging, sqlite3, time
from datetime import date, timedelta

logger = logging.getLogger("data-service.interact")


def sync_interact_qa(days_back: int = 7) -> dict:
    """同步深交所 + 上交所互动问答.

    API:
      - pro.irm_qa_sz(ts_code, start_date, end_date) → 深交所互动易
      - pro.irm_qa_sh(ts_code, start_date, end_date) → 上证e互动

    按日期批量拉取全市场问答, 不需要逐只股票调用.
    输出: ts_code, name, trade_date, q (问题), a (回复), pub_time

    Args:
        days_back: 回补天数, 默认 7 天

    Returns:
        {"table": "interact_qa", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH
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

        # ── 深交所互动易 ──
        rate_limit()
        try:
            df_sz = pro.irm_qa_sz(ann_date=d_str)
        except Exception as e:
            logger.debug("irm_qa_sz %s failed: %s", d_str, e)
            df_sz = None

        if df_sz is not None and len(df_sz) > 0:
            rows = []
            for _, r in df_sz.iterrows():
                ts_code = str(r.get("ts_code", ""))
                code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code
                q_text = str(r.get("q", ""))
                if not q_text:
                    continue
                rows.append((
                    code, d_iso, q_text,
                    str(r.get("a", "")),
                    str(r.get("pub_time", "")),
                    "szse",
                ))
            if rows:
                total_rows += _write_batch(rows, "szse", d_iso, pg_written)
                pg_written += _pg_write_batch(rows)

        # ── 上证e互动 ──
        rate_limit()
        try:
            df_sh = pro.irm_qa_sh(ann_date=d_str)
        except Exception as e:
            logger.debug("irm_qa_sh %s failed: %s", d_str, e)
            df_sh = None

        if df_sh is not None and len(df_sh) > 0:
            rows = []
            for _, r in df_sh.iterrows():
                ts_code = str(r.get("ts_code", ""))
                code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code
                q_text = str(r.get("q", ""))
                if not q_text:
                    continue
                rows.append((
                    code, d_iso, q_text,
                    str(r.get("a", "")),
                    str(r.get("pub_time", "")),
                    "sse",
                ))
            if rows:
                total_rows += _write_batch(rows, "sse", d_iso, pg_written)
                pg_written += _pg_write_batch(rows)

    elapsed = time.time() - t0
    logger.info("interact_qa: %d rows over %d days, PG=%d, %.1fs",
                total_rows, days_back, pg_written, elapsed)
    return {
        "table": "interact_qa",
        "written": total_rows,
        "pg_written": pg_written,
        "days_back": days_back,
        "elapsed": elapsed,
    }


def _pg_write_batch(rows: list) -> int:
    """PG 直写一批互动问答."""
    try:
        from app.sync.pg_writer import _pg_write
        return _pg_write(
            "interact_qa",
            ["code", "pub_date", "question", "answer", "pub_time", "source"],
            ["code", "pub_date", "question"],
            rows,
        )
    except Exception:
        return 0


def _write_batch(rows: list, source: str, d_iso: str, _prev_pg: int) -> int:
    """SQLite fallback 写入."""
    from app.config import DB_PATH, SQLITE_FALLBACK_ENABLED
    if SQLITE_FALLBACK_ENABLED:
        try:
            db = sqlite3.connect(DB_PATH)
            db.executemany(
                "INSERT OR REPLACE INTO interact_qa(code, pub_date, question, answer, pub_time, source) "
                "VALUES(?,?,?,?,?,?)", rows)
            db.commit(); db.close()
        except Exception as e:
            logger.warning("SQLite write interact_qa(%s) %s failed: %s", source, d_iso, e)
    return len(rows)
