"""Tushare 并行数据同步 — ThreadPool 批量拉取."""

import logging, sqlite3, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from app.config import TUSHARE_TOKEN, DB_PATH, THREAD_POOL_SIZE

logger = logging.getLogger("data-service.tushare")

_RATE_LIMIT = 400  # safe margin below 500


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
        df = pro.daily(trade_date=tushare_date, limit=5000, offset=page * 5000)
        if df is None or len(df) == 0:
            break
        for _, r in df.iterrows():
            code = _code_from_ts(r["ts_code"])
            all_rows.append((code, trade_date,
                             r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                             r.get("vol"), r.get("amount")))
            # 同步 pre_close
            pc = r.get("pre_close")
            if pc and pc > 0:
                db.execute("UPDATE stk_limit SET pre_close=? WHERE code=? AND trade_date=? AND pre_close=0",
                           (pc, code, trade_date))

    db.executemany(
        "INSERT OR REPLACE INTO daily_kline(code,trade_date,open,high,low,close,volume,amount) "
        "VALUES(?,?,?,?,?,?,?,?)", all_rows)
    db.commit()
    db.close()
    return {"table": "daily_kline", "written": len(all_rows), "elapsed": time.time() - t0}


def sync_single_table(api_name: str, trade_date: str, table: str, cols: list) -> dict:
    """通用单表同步 (moneyflow, stk_limit, daily_basic 等)."""
    pro = _get_pro()
    tushare_date = trade_date.replace("-", "")
    fn = getattr(pro, api_name)
    t0 = time.time()

    df = fn(trade_date=tushare_date)
    if df is None or len(df) == 0:
        return {"table": table, "written": 0, "warning": "no data"}

    db = sqlite3.connect(DB_PATH)
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

    placeholders = ",".join(["?"] * len(cols))
    db.executemany(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) VALUES({placeholders})", rows)
    db.commit()
    db.close()
    return {"table": table, "written": len(rows), "elapsed": time.time() - t0}


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
        df = fn(trade_date=tushare_date)
        if df is None or len(df) == 0:
            return {"table": table, "written": 0}
        rows = []
        for _, r in df.iterrows():
            row = []
            for c in cols:
                if c == "code": row.append(_code_from_ts(r["ts_code"]))
                elif c == "trade_date": row.append(trade_date)
                else: row.append(r.get(c))
            rows.append(tuple(row))
        db.executemany(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) VALUES({','.join(['?']*len(cols))})", rows)
        db.commit()
        return {"table": table, "written": len(rows)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_sync_one, "moneyflow", "moneyflow",
                         ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
                          "buy_md_amount", "sell_md_amount", "buy_lg_amount",
                          "sell_lg_amount", "buy_elg_amount", "sell_elg_amount",
                          "net_mf_amount", "net_mf_vol"])
        f2 = pool.submit(_sync_one, "stk_limit", "stk_limit",
                         ["code", "trade_date", "up_limit", "down_limit", "pre_close"])
        results["moneyflow"] = f1.result()
        results["stk_limit"] = f2.result()

    db.close()

    # index_daily
    pro2 = _get_pro()
    for ts_code in ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"]:
        df = pro2.index_daily(ts_code=ts_code, start_date=tushare_date, end_date=tushare_date)
        if df is not None and len(df) > 0:
            db2 = sqlite3.connect(DB_PATH)
            for _, r in df.iterrows():
                db2.execute("INSERT OR REPLACE INTO index_daily(ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (r["ts_code"], _to_dash(r["trade_date"]), r.get("close"), r.get("open"),
                             r.get("high"), r.get("low"), r.get("pre_close"), r.get("change"),
                             r.get("pct_chg"), r.get("vol"), r.get("amount")))
            db2.commit(); db2.close()

    results["index_daily"] = {"table": "index_daily", "written": "ok"}
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
        r = sync_single_table(name, td, table, cols)
        results[table] = r

    # limit_list_d
    pro = _get_pro()
    df = pro.limit_list_d(trade_date=trade_date.replace("-", ""), limit_type="U")
    if df is not None and len(df) > 0:
        db = sqlite3.connect(DB_PATH)
        db.execute("DELETE FROM limit_list_d WHERE trade_date=?", (trade_date.replace("-", ""),))
        for _, r in df.iterrows():
            db.execute("INSERT INTO limit_list_d(trade_date,ts_code,name,close,pct_chg,amount,float_mv,turnover_ratio,fd_amount,first_time,last_time,open_times,up_stat,limit_times) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (trade_date.replace("-", ""), str(r.get("ts_code", "")), str(r.get("name", "")),
                        r.get("close"), r.get("pct_chg"), r.get("amount"), r.get("float_mv"),
                        r.get("turnover_ratio"), r.get("fd_amount", 0), str(r.get("first_time", "")),
                        str(r.get("last_time", "")), r.get("open_times", 0), str(r.get("up_stat", "")),
                        r.get("limit_times", 0)))
        db.commit(); db.close()
        results["limit_list_d"] = {"table": "limit_list_d", "written": len(df)}
    return results
