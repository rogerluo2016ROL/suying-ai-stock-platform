"""Tushare 并行数据同步 — ThreadPool 批量拉取."""

import logging, sqlite3, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from app.config import TUSHARE_TOKEN, DB_PATH, THREAD_POOL_SIZE
from app.sync.rate_limiter import rate_limit

logger = logging.getLogger("data-service.tushare")


def _get_pro():
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    return ts.pro_api()


def _to_dash(d: str) -> str:
    d = str(d).replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def _code_from_ts(ts_code: str) -> str:
    return str(ts_code).split(".")[0][:6]


def sync_daily_kline(trade_date: str) -> dict:
    """拉取全量日线 (分页, 单线程足够)."""
    pro = _get_pro()
    tushare_date = trade_date.replace("-", "")
    t0 = time.time()
    db = sqlite3.connect(DB_PATH)

    all_rows = []
    for page in range(10):
        rate_limit()
        df = pro.daily(trade_date=tushare_date, limit=5000, offset=page * 5000)
        if df is None or len(df) == 0:
            break
        for _, r in df.iterrows():
            code = _code_from_ts(r["ts_code"])
            all_rows.append((code, trade_date,
                             r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                             r.get("vol"), r.get("amount")))
            # 同步 pre_close (best-effort)
            pc = r.get("pre_close")
            if pc and pc > 0:
                try:
                    db.execute("UPDATE stk_limit SET pre_close=? WHERE code=? AND trade_date=? AND pre_close=0",
                               (pc, code, trade_date))
                except Exception:
                    pass

    # PG 直写 (主路径)
    pg_written = 0
    if all_rows:
        try:
            from app.sync.pg_writer import write_daily_kline
            pg_written = write_daily_kline(all_rows)
        except Exception as e:
            logger.debug("PG write daily_kline skipped: %s", e)

    # SQLite 写入 (fallback)
    try:
        db.executemany(
            "INSERT OR REPLACE INTO daily_kline(code,trade_date,open,high,low,close,volume,amount) "
            "VALUES(?,?,?,?,?,?,?,?)", all_rows)
        db.commit()
    except Exception as e:
        logger.warning("SQLite write daily_kline failed: %s", e)
    finally:
        db.close()

    return {"table": "daily_kline", "written": len(all_rows), "pg_written": pg_written, "elapsed": time.time() - t0}


def sync_single_table(api_name: str, trade_date: str, table: str, cols: list) -> tuple:
    """通用单表同步 — 仅拉取数据，返回 rows，SQLite/PG 由调用方处理.

    返回 (result_dict, rows) 以便调用方做 PG 直写（主路径）+ SQLite 落盘（fallback）。
    """
    pro = _get_pro()
    tushare_date = trade_date.replace("-", "")
    fn = getattr(pro, api_name)
    t0 = time.time()

    rate_limit()
    df = fn(trade_date=tushare_date)
    if df is None or len(df) == 0:
        return {"table": table, "written": 0, "warning": "no data"}, []

    rows = []
    for _, r in df.iterrows():
        row = []
        for c in cols:
            if c == "code":
                row.append(_code_from_ts(r["ts_code"]))
            elif c == "trade_date":
                row.append(trade_date)
            else:
                row.append(r.get(c))
        rows.append(tuple(row))

    return {"table": table, "written": len(rows), "elapsed": time.time() - t0}, rows


# ── 批量同步函数 (并行调用多个 API) ──

def sync_post_market_core(trade_date: str) -> dict:
    """并行同步 P0 核心表."""
    jobs = [
        ("daily", trade_date, "daily_kline",
         ["code", "trade_date", "open", "high", "low", "close", "volume", "amount"]),
        ("moneyflow", trade_date, "moneyflow",
         ["code", "trade_date", "buy_sm_amount", "sell_sm_amount", "buy_md_amount",
          "sell_md_amount", "buy_lg_amount", "sell_lg_amount", "buy_elg_amount",
          "sell_elg_amount", "net_mf_amount", "net_mf_vol"]),
        ("stk_limit", trade_date, "stk_limit",
         ["code", "trade_date", "up_limit", "down_limit", "pre_close"]),
    ]

    # daily_kline needs special treatment (pagination), run it separately
    results = {}
    results["daily_kline"] = sync_daily_kline(trade_date)

    # moneyflow + stk_limit in parallel
    db = sqlite3.connect(DB_PATH)
    pro = _get_pro()
    tushare_date = trade_date.replace("-", "")

    def _sync_one(name, table, cols):
        fn = getattr(pro, name)
        rate_limit()
        df = fn(trade_date=tushare_date)
        if df is None or len(df) == 0:
            return {"table": table, "written": 0}, []
        rows = []
        for _, r in df.iterrows():
            row = []
            for c in cols:
                if c == "code": row.append(_code_from_ts(r["ts_code"]))
                elif c == "trade_date": row.append(trade_date)
                else: row.append(r.get(c))
            rows.append(tuple(row))
        return {"table": table, "written": len(rows)}, rows

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_sync_one, "moneyflow", "moneyflow",
                         ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
                          "buy_md_amount", "sell_md_amount", "buy_lg_amount",
                          "sell_lg_amount", "buy_elg_amount", "sell_elg_amount",
                          "net_mf_amount", "net_mf_vol"])
        f2 = pool.submit(_sync_one, "stk_limit", "stk_limit",
                         ["code", "trade_date", "up_limit", "down_limit", "pre_close"])
        mf_result, mf_rows = f1.result()
        sl_result, sl_rows = f2.result()
        results["moneyflow"] = mf_result
        results["stk_limit"] = sl_result

    db.close()

    # PG 直写 moneyflow + stk_limit (主路径)
    if mf_rows:
        try:
            from app.sync.pg_writer import write_moneyflow
            pg_mf = write_moneyflow(mf_rows)
            results["moneyflow"]["pg_written"] = pg_mf
        except Exception as e:
            logger.debug("PG write moneyflow skipped: %s", e)
    if sl_rows:
        try:
            from app.sync.pg_writer import write_stk_limit
            pg_sl = write_stk_limit(sl_rows)
            results["stk_limit"]["pg_written"] = pg_sl
        except Exception as e:
            logger.debug("PG write stk_limit skipped: %s", e)

    # SQLite 写入 moneyflow + stk_limit (fallback)
    if mf_rows:
        try:
            mf_db = sqlite3.connect(DB_PATH)
            mf_cols = ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
                       "buy_md_amount", "sell_md_amount", "buy_lg_amount", "sell_lg_amount",
                       "buy_elg_amount", "sell_elg_amount", "net_mf_amount", "net_mf_vol"]
            mf_db.executemany(f"INSERT OR REPLACE INTO moneyflow({','.join(mf_cols)}) VALUES({','.join(['?']*len(mf_cols))})", mf_rows)
            mf_db.commit(); mf_db.close()
        except Exception as e:
            logger.warning("SQLite write moneyflow failed: %s", e)
    if sl_rows:
        try:
            sl_db = sqlite3.connect(DB_PATH)
            sl_cols = ["code", "trade_date", "up_limit", "down_limit", "pre_close"]
            sl_db.executemany(f"INSERT OR REPLACE INTO stk_limit({','.join(sl_cols)}) VALUES({','.join(['?']*len(sl_cols))})", sl_rows)
            sl_db.commit(); sl_db.close()
        except Exception as e:
            logger.warning("SQLite write stk_limit failed: %s", e)

    # index_daily
    idx_rows = []
    pro2 = _get_pro()
    for ts_code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
        rate_limit()
        df = pro2.index_daily(ts_code=ts_code, start_date=tushare_date, end_date=tushare_date)
        if df is not None and len(df) > 0:
            for _, r in df.iterrows():
                row = (r["ts_code"], _to_dash(r["trade_date"]), r.get("close"), r.get("open"),
                        r.get("high"), r.get("low"), r.get("pre_close"), r.get("change"),
                        r.get("pct_chg"), r.get("vol"), r.get("amount"))
                idx_rows.append(row)

    # PG 直写 index_daily (主路径)
    pg_idx = 0
    if idx_rows:
        try:
            from app.sync.pg_writer import write_index_daily
            pg_idx = write_index_daily(idx_rows)
        except Exception as e:
            logger.debug("PG write index_daily skipped: %s", e)

    # SQLite 写入 index_daily (fallback)
    if idx_rows:
        try:
            db2 = sqlite3.connect(DB_PATH)
            for row in idx_rows:
                db2.execute("INSERT OR REPLACE INTO index_daily(ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            row)
            db2.commit(); db2.close()
        except Exception as e:
            logger.warning("SQLite write index_daily failed: %s", e)

    results["index_daily"] = {"table": "index_daily", "written": len(idx_rows), "pg_written": pg_idx}
    return results


def sync_post_market_ext(trade_date: str) -> dict:
    """并行同步 P1 扩展表."""
    results = {}
    jobs = [
        ("daily_basic", trade_date, "daily_basic",
         ["code", "trade_date", "turnover_rate", "volume_ratio", "pe", "pe_ttm", "pb", "total_mv", "circ_mv"]),
        ("ths_daily", trade_date.replace("-", ""), "ths_daily",
         ["trade_date", "ts_code", "name", "close", "pct_change", "avg_price", "total_mv", "float_mv"]),
    ]
    for name, td, table, cols in jobs:
        r, rows = sync_single_table(name, td, table, cols)
        # PG 直写 (主路径)
        pg_wr = 0
        if rows:
            try:
                if table == "daily_basic":
                    from app.sync.pg_writer import write_daily_basic
                    pg_wr = write_daily_basic(rows)
                elif table == "ths_daily":
                    from app.sync.pg_writer import write_ths_daily
                    pg_wr = write_ths_daily(rows)
            except Exception as e:
                logger.debug("PG write %s skipped: %s", table, e)
        r["pg_written"] = pg_wr
        # SQLite 写入 (fallback)
        if rows:
            try:
                db3 = sqlite3.connect(DB_PATH)
                placeholders = ",".join(["?"] * len(cols))
                db3.executemany(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) VALUES({placeholders})", rows)
                db3.commit()
                db3.close()
            except Exception as e:
                logger.warning("SQLite write %s failed: %s", table, e)
        results[table] = r

    # limit_list_d
    pro = _get_pro()
    rate_limit()
    df = pro.limit_list_d(trade_date=trade_date.replace("-", ""), limit_type="U")
    limit_rows = []
    if df is not None and len(df) > 0:
        for _, r in df.iterrows():
            row = (trade_date.replace("-", ""), str(r.get("ts_code", "")), str(r.get("name", "")),
                    r.get("close"), r.get("pct_chg"), r.get("amount"), r.get("float_mv"),
                    r.get("turnover_ratio"), r.get("fd_amount", 0), str(r.get("first_time", "")),
                    str(r.get("last_time", "")), r.get("open_times", 0), str(r.get("up_stat", "")),
                    r.get("limit_times", 0))
            limit_rows.append(row)

        # PG 直写 limit_list_d (主路径)
        pg_lim = 0
        try:
            from app.sync.pg_writer import write_limit_list_d
            pg_lim = write_limit_list_d(limit_rows)
        except Exception as e:
            logger.debug("PG write limit_list_d skipped: %s", e)

        # SQLite 写入 limit_list_d (fallback)
        try:
            db = sqlite3.connect(DB_PATH)
            db.execute("DELETE FROM limit_list_d WHERE trade_date=?", (trade_date.replace("-", ""),))
            for row in limit_rows:
                db.execute("INSERT INTO limit_list_d(trade_date,ts_code,name,close,pct_chg,amount,float_mv,turnover_ratio,fd_amount,first_time,last_time,open_times,up_stat,limit_times) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           row)
            db.commit(); db.close()
        except Exception as e:
            logger.warning("SQLite write limit_list_d failed: %s", e)
        results["limit_list_d"] = {"table": "limit_list_d", "written": len(df), "pg_written": pg_lim}
    else:
        results["limit_list_d"] = {"table": "limit_list_d", "written": 0}
    return results
