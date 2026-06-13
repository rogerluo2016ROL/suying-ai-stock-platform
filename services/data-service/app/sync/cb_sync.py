"""可转债 & 同花顺数据同步 — standalone sync functions.

包含:
  - sync_ths_daily: 同花顺概念板块每日行情 (pro.ths_daily)
  - sync_cb_price_chg_all: 转股价变动全量同步 (逐只遍历 cb_basic)
  - sync_ths_concept_map: 同花顺概念映射 (pro.ths_concept_map, 每月刷新)
"""

import logging, os, time
from datetime import datetime, timedelta

logger = logging.getLogger("data-service.cb_sync")

MAX_RETRIES = 3
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

# ── helpers ──

def _get_pro():
    """Lazy-init Tushare pro_api."""
    import tushare as ts
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        return None
    ts.set_token(token)
    return ts.pro_api()


def _get_trade_dates(days_back: int) -> list[str]:
    """Generate calendar dates for last N days (YYYYMMDD format)."""
    dates = []
    today = datetime.now()
    for i in range(days_back, 0, -1):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y%m%d"))
    return dates


def _safe_val(v):
    """Convert numpy scalars / NaN to native Python."""
    if v is None:
        return None
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            if np.isnan(v):
                return None
            return float(v)
    except ImportError:
        pass
    if isinstance(v, float) and str(v) == 'nan':
        return None
    return v


def _pg_bulk_insert(table: str, columns: list[str], conflict_cols: list[str],
                    rows: list[tuple]) -> int:
    """PG 批量写入 — ON CONFLICT DO NOTHING + 3 次指数退避重试."""
    if not rows:
        return 0
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            import psycopg2
            conn = psycopg2.connect(PG_URL)
            conn.autocommit = True
            cur = conn.cursor()
            col_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            conflict_str = ", ".join(conflict_cols)
            sql = (f"INSERT INTO {table}({col_str}) VALUES({placeholders}) "
                   f"ON CONFLICT({conflict_str}) DO NOTHING")
            cur.executemany(sql, rows)
            written = cur.rowcount
            conn.close()
            return written
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                sleep_s = 4 ** attempt  # 1, 4, 16
                logger.debug("PG write %s retry %d/%d after %.0fs: %s",
                             table, attempt + 1, MAX_RETRIES, sleep_s, e)
                time.sleep(sleep_s)
        except Exception as e:
            logger.debug("PG write %s: %s", table, e)
            return 0
    logger.warning("PG write %s failed after %d retries: %s", table, MAX_RETRIES, last_error)
    return 0


# ── sync functions ──

def sync_ths_daily(days_back: int = 30) -> dict:
    """同步同花顺概念板块每日行情 (pro.ths_daily).

    每个交易日拉取全量概念板块日线数据，写入 PG ths_daily 表。
    自带 3 次重试 + 结果日志。
    """
    pro = _get_pro()
    if pro is None:
        logger.warning("ths_daily: TUSHARE_TOKEN not set — skipped")
        return {"status": "skipped", "reason": "no Tushare token"}

    dates = _get_trade_dates(days_back)
    total, pg_written = 0, 0
    # API fields: ts_code, trade_date, open, high, low, close, pre_close,
    #   avg_price, change, pct_change, vol, turnover_rate
    # Note: API returns NO name/total_mv/float_mv; name comes from ths_concept_map join
    cols = ["ts_code", "trade_date", "close", "pct_change",
            "avg_price"]

    for d in dates:
        # 3 次重试拉取
        df = None
        for attempt in range(MAX_RETRIES):
            try:
                df = pro.ths_daily(trade_date=d)
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    sleep_s = 2 ** attempt
                    logger.warning("ths_daily fetch retry %d/%d for %s after %.0fs: %s",
                                   attempt + 1, MAX_RETRIES, d, sleep_s, e)
                    time.sleep(sleep_s)
                else:
                    logger.error("ths_daily fetch FAILED for %s after %d retries: %s",
                                 d, MAX_RETRIES, e)

        if df is None or df.empty:
            continue

        rows = []
        for _, r in df.iterrows():
            td = d[:4] + "-" + d[4:6] + "-" + d[6:8]
            rows.append((
                str(r.get("ts_code", "")),
                td,
                _safe_val(r.get("close")),
                _safe_val(r.get("pct_change")),
                _safe_val(r.get("avg_price")),
            ))

        total += len(rows)
        w = _pg_bulk_insert("ths_daily", cols, ["ts_code", "trade_date"], rows)
        pg_written += w
        if w > 0:
            logger.debug("ths_daily %s: %d rows written", d, w)

    logger.info("ths_daily: %d fetched, %d written (%d dates)",
                total, pg_written, len(dates))
    return {"status": "ok", "table": "ths_daily", "fetched": total,
            "pg_written": pg_written}


def sync_cb_price_chg_all(days_back: int = 365) -> dict:
    """同步转股价变动全量 — 遍历 cb_basic 逐只拉取 pro.cb_price_chg.

    与 etl.py sync_cb_price_chg 的按日期批量不同，此函数按 ts_code 逐只拉取，
    可获取每只可转债的完整转股价变动历史。
    自带 3 次重试 + 结果日志。
    """
    pro = _get_pro()
    if pro is None:
        logger.warning("cb_price_chg_all: TUSHARE_TOKEN not set — skipped")
        return {"status": "skipped", "reason": "no Tushare token"}

    # 从 PG 获取所有 cb_basic 的 ts_code
    codes = []
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL)
        cur = conn.cursor()
        cur.execute("SELECT ts_code FROM cb_basic")
        codes = [r[0] for r in cur.fetchall()]
        conn.close()
    except Exception as e:
        logger.warning("cb_price_chg_all: cannot read cb_basic from PG: %s", e)
        return {"status": "error", "reason": f"cb_basic read failed: {e}"}

    if not codes:
        logger.warning("cb_price_chg_all: no cb_basic records found")
        return {"status": "ok", "table": "cb_price_chg", "fetched": 0, "pg_written": 0}

    total, pg_written = 0, 0
    cols = ["ts_code", "change_date", "pre_price", "new_price", "change_reason"]

    for idx, ts_code in enumerate(codes):
        # 3 次重试拉取
        df = None
        for attempt in range(MAX_RETRIES):
            try:
                df = pro.cb_price_chg(ts_code=ts_code)
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.debug("cb_price_chg fetch FAILED for %s: %s", ts_code, e)

        if df is None or df.empty:
            continue

        rows = []
        for _, r in df.iterrows():
            change_date = str(r.get("change_date", ""))
            if len(change_date) == 8:
                change_date = f"{change_date[:4]}-{change_date[4:6]}-{change_date[6:8]}"
            rows.append((
                str(r.get("ts_code", ts_code)),
                change_date,
                _safe_val(r.get("pre_price")),
                _safe_val(r.get("new_price")),
                str(r.get("change_reason") or r.get("change_reason_desc") or "")[:200],
            ))

        if rows:
            total += len(rows)
            w = _pg_bulk_insert("cb_price_chg", cols, ["ts_code", "change_date"], rows)
            pg_written += w

        if (idx + 1) % 50 == 0:
            logger.debug("cb_price_chg_all: %d/%d codes, %d rows",
                         idx + 1, len(codes), pg_written)

    logger.info("cb_price_chg_all: %d fetched, %d written (%d codes)",
                total, pg_written, len(codes))
    return {"status": "ok", "table": "cb_price_chg", "fetched": total,
            "pg_written": pg_written, "codes_scanned": len(codes)}


def sync_ths_concept_map(days_back: int = 0) -> dict:
    """同步同花顺概念板块映射 (pro.ths_concept).

    拉取全量概念→成分股映射关系，存入 ths_concept_map 表。
    适合每月执行一次 (数据变动频率低)。
    自带 3 次重试 + 结果日志。
    """
    pro = _get_pro()
    if pro is None:
        logger.warning("ths_concept_map: TUSHARE_TOKEN not set — skipped")
        return {"status": "skipped", "reason": "no Tushare token"}

    total, pg_written = 0, 0
    cols = ["ts_code", "concept_name", "concept_code", "trade_date"]

    # 先获取所有概念列表
    concepts = []
    for attempt in range(MAX_RETRIES):
        try:
            df_concept = pro.ths_concept()
            if df_concept is not None and not df_concept.empty:
                for _, r in df_concept.iterrows():
                    concepts.append((
                        str(r.get("code", "")),
                        str(r.get("name", "")),
                    ))
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                logger.warning("ths_concept fetch retry %d/%d: %s",
                               attempt + 1, MAX_RETRIES, e)
            else:
                logger.error("ths_concept fetch FAILED: %s", e)
                return {"status": "error", "reason": str(e)[:200]}

    if not concepts:
        logger.warning("ths_concept_map: no concepts found")
        return {"status": "ok", "table": "ths_concept_map", "fetched": 0, "pg_written": 0}

    logger.info("ths_concept_map: %d concepts, fetching members...", len(concepts))

    # 逐概念拉取成分股
    trade_date = datetime.now().strftime("%Y-%m-%d")
    for idx, (concept_code, concept_name) in enumerate(concepts):
        for attempt in range(MAX_RETRIES):
            try:
                df = pro.ths_member(ts_code=concept_code)
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                else:
                    logger.debug("ths_member FAILED for %s: %s", concept_code, e)
                    df = None

        if df is None or df.empty:
            continue

        rows = []
        for _, r in df.iterrows():
            rows.append((
                str(r.get("ts_code", "")),
                concept_name,
                concept_code,
                trade_date,
            ))

        if rows:
            total += len(rows)
            w = _pg_bulk_insert("ths_concept_map", cols,
                               ["ts_code", "concept_name"], rows)
            pg_written += w

        if (idx + 1) % 50 == 0:
            logger.debug("ths_concept_map: %d/%d concepts, %d rows",
                         idx + 1, len(concepts), pg_written)

    logger.info("ths_concept_map: %d fetched, %d written (%d concepts)",
                total, pg_written, len(concepts))
    return {"status": "ok", "table": "ths_concept_map", "fetched": total,
            "pg_written": pg_written, "concepts": len(concepts)}
