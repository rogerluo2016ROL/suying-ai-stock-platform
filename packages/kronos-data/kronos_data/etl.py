#!/usr/bin/env python3
"""Tushare premium data sync — batch-fetch and persist to SQLite.

Usage:
    python tools/tushare_sync.py                     # Sync all tables, last 30 days
    python tools/tushare_sync.py --days 5            # Last 5 days only
    python tools/tushare_sync.py --mode moneyflow    # Specific table only
    python tools/tushare_sync.py --mode all --days 60
"""

import argparse
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # packages/kronos-data
_PROJ = os.path.dirname(os.path.dirname(_PKG_ROOT))  # project root (2 levels up)
sys.path.insert(0, os.path.join(_PKG_ROOT, "src"))
sys.path.insert(0, _PKG_ROOT)

# PG connection (preferred) or SQLite fallback
_PG_URL = os.environ.get("KRONOS_PG_URL", "")
_USE_PG = bool(_PG_URL)
_pg_conn = None

DB_PATH = os.path.join(_PROJ, "Kronos", "webui", "stock_screening.db")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(_PROJ, "webui", "stock_screening.db")

# Rate limiting — 500 req/min max, ~120ms per call
_CALL_TIMES = []
_RATE_LIMIT = 450  # safe margin below 500


def _rate_limit():
    """Enforce 450 req/min sliding-window rate limit."""
    global _CALL_TIMES
    now = time.time()
    _CALL_TIMES = [t for t in _CALL_TIMES if now - t < 60]
    if len(_CALL_TIMES) >= _RATE_LIMIT:
        sleep_for = 60 - (now - _CALL_TIMES[0]) + 0.1
        if sleep_for > 0:
            time.sleep(sleep_for)
            _CALL_TIMES = []
    _CALL_TIMES.append(time.time())


def _get_pro():
    """Lazy-init Tushare pro_api. Returns None if TUSHARE_TOKEN not set."""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        print("  TUSHARE_TOKEN not set — skipping")
        return None
    try:
        import tushare as ts
    except ImportError:
        print("  tushare not installed — skipping")
        return None
    ts.set_token(token)
    return ts.pro_api()


def _get_trade_dates(days_back: int) -> list[str]:
    """Generate calendar dates for last N days (YYYYMMDD format).
    We generate all calendar dates; Tushare filters to trading days server-side.
    """
    dates = []
    today = datetime.now()
    for i in range(days_back, 0, -1):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y%m%d"))
    return dates


def _ts_code(code: str) -> str:
    """Convert 6-digit code to Tushare ts_code format (000001.SZ)."""
    if "." in str(code):
        return str(code)
    c = str(code)
    if c.startswith("6") or c.startswith("5"):
        return f"{c}.SH"
    elif c.startswith("9") or c.startswith("4") or c.startswith("8"):
        return f"{c}.BJ"
    else:
        return f"{c}.SZ"


def _code_from_ts(ts_code: str) -> str:
    """Extract 6-digit code from Tushare ts_code (000001.SZ → 000001)."""
    return str(ts_code).split(".")[0][:6]


# ═══════════════════════════════════════════════════════════════
# DB helpers — PG-aware, fall back to SQLite
# ═══════════════════════════════════════════════════════════════

class _Db:
    """Unified DB wrapper — same API for PG and SQLite.

    Usage:
        db = _get_etl_db()
        db.execute("SELECT ...", (params,))
        db.commit()
        db.close()
    """
    def __init__(self, conn, is_pg: bool):
        self._conn = conn
        self._pg = is_pg
    def execute(self, sql: str, params: tuple = None):
        if self._pg:
            sql = sql.replace("?", "%s")
            cur = self._conn.cursor()
            cur.execute(sql, params or ())
            return cur
        return self._conn.execute(sql, params or ())
    def commit(self):
        self._conn.commit()
    def close(self):
        self._conn.close()
    def rollback(self):
        try: self._conn.rollback()
        except: pass

def _get_etl_db() -> _Db:
    """Return _Db wrapper. PG if KRONOS_PG_URL is set, else SQLite."""
    global _pg_conn
    if _USE_PG:
        try:
            import psycopg2
            if _pg_conn is None or _pg_conn.closed:
                _pg_conn = psycopg2.connect(_PG_URL)
            return _Db(_pg_conn, True)
        except Exception as e:
            print(f"  PG connection failed ({e}), falling back to SQLite")
    return _Db(sqlite3.connect(DB_PATH), False)


def clean_before_write(db: _Db, table: str, days_back: int, date_col: str = "trade_date"):
    """Delete old rows within the sync window to avoid duplicates."""
    cutoff = (datetime.now() - timedelta(days=days_back + 1)).strftime("%Y-%m-%d")
    db.execute(f"DELETE FROM {table} WHERE {date_col} >= ?", (cutoff,))


def _insert_rows(db: _Db, table: str, columns: list[str],
                 rows: list[tuple]) -> int:
    """INSERT with per-row error isolation. Uses PG or SQLite bulk insert."""
    col_str = ", ".join(columns)
    if db._pg:
        import psycopg2.extras
        cur = db._conn.cursor()
        sql = f"INSERT INTO {table}({col_str}) VALUES %s ON CONFLICT DO NOTHING"
        try:
            psycopg2.extras.execute_values(cur, sql, rows, page_size=1000)
            written = cur.rowcount
            db.commit()
            return written
        except Exception:
            db.rollback()
            placeholders = ", ".join(["%s"] * len(columns))
            sql2 = f"INSERT INTO {table}({col_str}) VALUES({placeholders}) ON CONFLICT DO NOTHING"
            written = 0
            for row in rows:
                try: cur.execute(sql2, tuple(row)); written += 1
                except: pass
            db.commit()
            return written
    else:
        placeholders = ",".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {table}({col_str}) VALUES({placeholders})"
        written = 0
        for row in rows:
            try: db.execute(sql, row); written += 1
            except: pass
        return written


# ═══════════════════════════════════════════════════════════════
# Per-API sync functions
# ═══════════════════════════════════════════════════════════════


def sync_moneyflow(days_back: int = 30) -> dict:
    """Sync pro.moneyflow() — per-date full-market returns."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "moneyflow", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
            "buy_md_amount", "sell_md_amount", "buy_lg_amount", "sell_lg_amount",
            "buy_elg_amount", "sell_elg_amount", "net_mf_amount", "net_mf_vol"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.moneyflow(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("buy_sm_amount"), r.get("sell_sm_amount"),
                r.get("buy_md_amount"), r.get("sell_md_amount"),
                r.get("buy_lg_amount"), r.get("sell_lg_amount"),
                r.get("buy_elg_amount"), r.get("sell_elg_amount"),
                r.get("net_mf_amount"), r.get("net_mf_vol"),
            ))
        total += len(rows)
        written += _insert_rows(db, "moneyflow", cols, rows)

    db.commit()
    db.close()
    print(f"  moneyflow: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "moneyflow", "fetched": total, "written": written}


def sync_hk_hold(days_back: int = 30) -> dict:
    """Sync pro.hk_hold() — north-bound holding details."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "hk_holdings", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "vol", "ratio", "hold_vol"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.hk_hold(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("vol"), r.get("ratio"), r.get("hold_vol"),
            ))
        total += len(rows)
        written += _insert_rows(db, "hk_holdings", cols, rows)

    db.commit()
    db.close()
    print(f"  hk_hold: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "hk_holdings", "fetched": total, "written": written}


def sync_margin(days_back: int = 30) -> dict:
    """Sync pro.margin_detail() — margin trading details."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "margin_detail", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "rzye", "rqye", "rzmre", "rqyl", "rzche", "rqchl"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.margin_detail(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("rzye"), r.get("rqye"), r.get("rzmre"),
                r.get("rqyl"), r.get("rzche"), r.get("rqchl"),
            ))
        total += len(rows)
        written += _insert_rows(db, "margin_detail", cols, rows)

    db.commit()
    db.close()
    print(f"  margin_detail: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "margin_detail", "fetched": total, "written": written}


def sync_top_list(days_back: int = 30) -> dict:
    """Sync pro.top_list() — 龙虎榜明细."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "top_list", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "name", "close", "pct_change",
            "turnover_rate", "amount", "l_sell", "l_buy", "net_amount", "reason"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.top_list(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("name"), r.get("close"), r.get("pct_change"),
                r.get("turnover_rate"), r.get("amount"),
                r.get("l_sell"), r.get("l_buy"), r.get("net_amount"),
                r.get("reason"),
            ))
        total += len(rows)
        written += _insert_rows(db, "top_list", cols, rows)

    db.commit()
    db.close()
    print(f"  top_list: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "top_list", "fetched": total, "written": written}


def sync_daily_basic(days_back: int = 30) -> dict:
    """Sync pro.daily_basic() — daily indicators (turnover, PE/PB, market cap)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "daily_basic", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "turnover_rate", "turnover_rate_f",
            "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm",
            "dv_ratio", "total_mv", "circ_mv"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.daily_basic(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("turnover_rate"), r.get("turnover_rate_f"),
                r.get("volume_ratio"), r.get("pe"), r.get("pe_ttm"),
                r.get("pb"), r.get("ps"), r.get("ps_ttm"),
                r.get("dv_ratio"), r.get("total_mv"), r.get("circ_mv"),
            ))
        total += len(rows)
        written += _insert_rows(db, "daily_basic", cols, rows)

    db.commit()
    db.close()
    print(f"  daily_basic: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "daily_basic", "fetched": total, "written": written}


def sync_stk_limit(days_back: int = 30) -> dict:
    """Sync pro.stk_limit() — daily limit-up/limit-down prices."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "stk_limit", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "up_limit", "down_limit", "pre_close"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.stk_limit(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("up_limit"), r.get("down_limit"), r.get("pre_close"),
            ))
        total += len(rows)
        written += _insert_rows(db, "stk_limit", cols, rows)

    db.commit()
    db.close()
    print(f"  stk_limit: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "stk_limit", "fetched": total, "written": written}


def sync_weekly_kline(days_back: int = 365) -> dict:
    """Sync pro.weekly() — weekly K-line data."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "weekly_kline", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "open", "high", "low", "close", "volume", "amount"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.weekly(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                r.get("vol"), r.get("amount"),
            ))
        total += len(rows)
        written += _insert_rows(db, "weekly_kline", cols, rows)

    db.commit()
    db.close()
    print(f"  weekly_kline: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "weekly_kline", "fetched": total, "written": written}


def sync_monthly_kline(days_back: int = 365 * 2) -> dict:
    """Sync pro.monthly() — monthly K-line data."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "monthly_kline", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "open", "high", "low", "close", "volume", "amount"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.monthly(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                r.get("vol"), r.get("amount"),
            ))
        total += len(rows)
        written += _insert_rows(db, "monthly_kline", cols, rows)

    db.commit()
    db.close()
    print(f"  monthly_kline: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "monthly_kline", "fetched": total, "written": written}


def sync_adj_factor(days_back: int = 30) -> dict:
    """Sync pro.adj_factor() — 复权因子 for computing adjusted close."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "adj_factor", days_back)

    total, written = 0, 0
    cols = ["code", "trade_date", "adj_factor"]

    for d in dates:
        _rate_limit()
        try:
            df = pro.adj_factor(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r["adj_factor"],
            ))
        total += len(rows)
        written += _insert_rows(db, "adj_factor", cols, rows)

    db.commit()
    db.close()
    print(f"  adj_factor: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "adj_factor", "fetched": total, "written": written}


def sync_index_basic(days_back: int = 30) -> dict:
    """Sync pro.index_basic() — index metadata (上证/深证/创业板等)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    cols = ["ts_code", "name", "market", "publisher", "category",
            "base_date", "base_point", "list_date"]

    total, written = 0, 0
    for market in ["SSE", "SZSE", "CICC"]:
        _rate_limit()
        try:
            df = pro.index_basic(market=market)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                r["ts_code"], r["name"], r.get("market"), r.get("publisher"),
                r.get("category"), r.get("base_date"), r.get("base_point"),
                r.get("list_date"),
            ))
        total += len(rows)
        written += _insert_rows(db, "index_basic", cols, rows)

    db.commit()
    db.close()
    print(f"  index_basic: {total} fetched, {written} written")
    return {"status": "ok", "table": "index_basic", "fetched": total, "written": written}


def sync_index_daily(days_back: int = 30) -> dict:
    """Sync pro.index_daily() — index OHLCV for major indices."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    # Major A-share indices
    MAJOR_INDICES = [
        "000001.SH",  # 上证指数
        "399001.SZ",  # 深证成指
        "399006.SZ",  # 创业板指
        "000688.SH",  # 科创50
        "000016.SH",  # 上证50
        "000300.SH",  # 沪深300
        "000905.SH",  # 中证500
        "399005.SZ",  # 中小板指
    ]

    db = _get_etl_db()
    clean_before_write(db, "index_daily", days_back)

    total, written = 0, 0
    cols = ["ts_code", "trade_date", "close", "open", "high", "low",
            "pre_close", "change", "pct_chg", "vol", "amount"]

    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    for code in MAJOR_INDICES:
        _rate_limit()
        try:
            df = pro.index_daily(ts_code=code, start_date=start, end_date=end)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                r["ts_code"],
                str(r["trade_date"])[:4] + "-" + str(r["trade_date"])[4:6] + "-" + str(r["trade_date"])[6:8],
                r["close"], r["open"], r["high"], r["low"],
                r.get("pre_close"), r.get("change"), r.get("pct_chg"),
                r.get("vol"), r.get("amount"),
            ))
        total += len(rows)
        written += _insert_rows(db, "index_daily", cols, rows)

    db.commit()
    db.close()
    print(f"  index_daily: {total} fetched, {written} written ({len(MAJOR_INDICES)} indices, {days_back}d)")
    return {"status": "ok", "table": "index_daily", "fetched": total, "written": written}


# ═══════════════════════════════════════════════════════════════
# Layer 2: Financial statement sync (per-stock, quarterly)
# ═══════════════════════════════════════════════════════════════

def _get_all_codes(db: sqlite3.Connection) -> list[str]:
    """Get all non-ST A-share stock codes (沪/深/创/科主板)."""
    return [r["code"] for r in db.execute(
        "SELECT code FROM stocks WHERE is_st=0 "
        "AND (code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%' OR code LIKE '68%') "
        "ORDER BY code"
    ).fetchall()]


def _sync_per_stock_financial(table: str, api_name: str, fields: str,
                               periods: list[str], extra_kwargs: dict = None) -> dict:
    """Generic per-stock financial data sync for quarterly statements.

    Calls pro.<api_name>(ts_code=<ts_code>, period=<period>, fields=<fields>) per stock.
    Rate-limited to ~450 calls/min.
    """
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    db = _get_etl_db()
    db.row_factory = sqlite3.Row
    codes = _get_all_codes(db)
    total, written = 0, 0

    cols_map = {
        "financial_income": ["code", "end_date", "report_type", "basic_eps",
            "total_revenue", "revenue", "oper_cost", "sell_expense",
            "admin_expense", "fin_expense", "n_income", "n_income_attr_p",
            "operate_profit", "total_profit"],
        "financial_balance": ["code", "end_date", "report_type", "total_assets",
            "total_cur_assets", "total_liab", "total_cur_liab",
            "total_hldr_eqy_exc_min_int", "total_share", "cap_rese", "undistr_porfit"],
        "financial_cashflow": ["code", "end_date", "report_type",
            "n_cashflow_act", "n_cashflow_inv_act", "n_cashflow_fin_act",
            "c_fr_sale_sg", "net_profit"],
        "financial_indicator": ["code", "end_date", "roe", "roa",
            "grossprofit_margin", "netprofit_margin", "debt_to_assets",
            "eps", "ocfps", "current_ratio", "quick_ratio", "or_yoy", "profit_dedt"],
    }

    cols = cols_map.get(table, [])
    if not cols:
        db.close()
        return {"status": "error", "reason": f"unknown table: {table}"}

    fn = getattr(pro, api_name)
    processed = 0

    for code in codes:
        for period in periods:
            _rate_limit()
            try:
                kwargs = {"ts_code": _ts_code(code), "period": period,
                          "fields": fields}
                if extra_kwargs:
                    kwargs.update(extra_kwargs)
                df = fn(**kwargs)
            except Exception:
                continue
            if df is None or df.empty:
                continue

            rows = []
            for _, r in df.iterrows():
                row_vals = []
                for c in cols:
                    if c == "code":
                        row_vals.append(code)
                    elif c == "end_date":
                        row_vals.append(str(r.get("end_date", "")))
                    elif c == "report_type":
                        row_vals.append(str(r.get("report_type", "")))
                    else:
                        # Map DB column to Tushare field (same name)
                        row_vals.append(r.get(c))
                rows.append(tuple(row_vals))
            total += len(rows)
            written += _insert_rows(db, table, cols, rows)

        processed += 1
        if processed % 500 == 0:
            print(f"  {api_name}: {processed}/{len(codes)} ({processed*100//len(codes)}%) "
                  f"- {written} rows")

    db.commit()
    db.close()
    print(f"  {api_name}: {total} fetched, {written} written "
          f"({len(codes)} stocks, {len(periods)} quarters)")
    return {"status": "ok", "table": table, "fetched": total, "written": written}


def sync_income(days_back: int = 30) -> dict:
    """Sync pro.income() — latest 2 quarters for all stocks."""
    periods = ["20260331", "20251231"]
    fields = "ts_code,end_date,report_type,basic_eps,total_revenue,revenue,oper_cost,sell_expense,admin_expense,fin_expense,n_income,n_income_attr_p,operate_profit,total_profit"
    return _sync_per_stock_financial("financial_income", "income", fields, periods)


def sync_balancesheet(days_back: int = 30) -> dict:
    """Sync pro.balancesheet() — latest 2 quarters for all stocks."""
    periods = ["20260331", "20251231"]
    fields = "ts_code,end_date,report_type,total_assets,total_cur_assets,total_liab,total_cur_liab,total_hldr_eqy_exc_min_int,total_share,cap_rese,undistr_porfit"
    return _sync_per_stock_financial("financial_balance", "balancesheet", fields, periods)


def sync_cashflow(days_back: int = 30) -> dict:
    """Sync pro.cashflow() — latest 2 quarters for all stocks."""
    periods = ["20260331", "20251231"]
    fields = "ts_code,end_date,report_type,n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act,c_fr_sale_sg,net_profit"
    return _sync_per_stock_financial("financial_cashflow", "cashflow", fields, periods)


def sync_financial_indicator(days_back: int = 30) -> dict:
    """Sync pro.fina_indicator() — latest 2 quarters for all stocks."""
    periods = ["20260331", "20251231"]
    fields = "ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,eps,ocfps,current_ratio,quick_ratio,or_yoy,profit_dedt"
    return _sync_per_stock_financial("financial_indicator", "fina_indicator", fields, periods)


def sync_forecast_data(days_back: int = 180) -> dict:
    """Sync pro.forecast() — batch by ann_date (last 6 months)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    dates = []
    today = datetime.now()
    for i in range(days_back):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y%m%d"))

    db = _get_etl_db()
    cols = ["code", "ann_date", "end_date", "forecast_type",
            "net_profit_min", "net_profit_max", "change_reason"]
    total, written = 0, 0

    for d in dates:
        _rate_limit()
        try:
            df = pro.forecast(ann_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                _code_from_ts(r["ts_code"]),
                str(r.get("ann_date", d)),
                str(r.get("end_date", "")),
                str(r.get("type", "")),
                r.get("net_profit_min"), r.get("net_profit_max"),
                str(r.get("change_reason", "")),
            ))
        if rows:
            total += len(rows)
            written += _insert_rows(db, "forecast_data", cols, rows)

    db.commit()
    db.close()
    print(f"  forecast: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "forecast_data", "fetched": total, "written": written}


def sync_dividend_data(days_back: int = 365) -> dict:
    """Sync pro.dividend() — batch by ann_date (last year)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    dates = []
    today = datetime.now()
    for i in range(days_back):
        d = today - timedelta(days=i)
        dates.append(d.strftime("%Y%m%d"))

    db = _get_etl_db()
    cols = ["code", "end_date", "ann_date", "cash_div", "stk_div",
            "stk_bo_rate", "record_date", "ex_date"]
    total, written = 0, 0
    seen = set()

    for d in dates:
        _rate_limit()
        try:
            df = pro.dividend(ann_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            key = (_code_from_ts(r["ts_code"]), str(r.get("end_date", "")))
            if key in seen:
                continue
            seen.add(key)
            rows.append((
                _code_from_ts(r["ts_code"]),
                str(r.get("end_date", "")),
                str(r.get("ann_date", d)),
                r.get("cash_div"), r.get("stk_div"),
                r.get("stk_bo_rate"), r.get("record_date"), r.get("ex_date"),
            ))
        if rows:
            total += len(rows)
            written += _insert_rows(db, "dividend_data", cols, rows)

    db.commit()
    db.close()
    print(f"  dividend: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "dividend_data", "fetched": total, "written": written}


def sync_top_inst(days_back: int = 30) -> dict:
    """Sync pro.top_inst() — 龙虎榜机构席位明细 (per-date batch)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "top_inst", days_back)
    total, written = 0, 0
    cols = ["code", "trade_date", "exalter", "buy", "buy_rate",
            "sell", "sell_rate", "net_buy"]
    for d in dates:
        _rate_limit()
        try: df = pro.top_inst(trade_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((_code_from_ts(r["ts_code"]),
                d[:4]+"-"+d[4:6]+"-"+d[6:8],
                r.get("exalter"), r.get("buy"), r.get("buy_rate"),
                r.get("sell"), r.get("sell_rate"), r.get("net_buy")))
        total += len(rows)
        written += _insert_rows(db, "top_inst", cols, rows)
    db.commit(); db.close()
    print(f"  top_inst: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "top_inst", "fetched": total, "written": written}


def sync_block_trade_data(days_back: int = 30) -> dict:
    """Sync pro.block_trade() — 大宗交易 (per-date batch)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "block_trade_data", days_back)
    total, written = 0, 0
    cols = ["code", "trade_date", "price", "vol", "amount", "buyer", "seller"]
    for d in dates:
        _rate_limit()
        try: df = pro.block_trade(trade_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((_code_from_ts(r["ts_code"]),
                d[:4]+"-"+d[4:6]+"-"+d[6:8],
                r.get("price"), r.get("vol"), r.get("amount"),
                str(r.get("buyer","")), str(r.get("seller",""))))
        total += len(rows)
        written += _insert_rows(db, "block_trade_data", cols, rows)
    db.commit(); db.close()
    print(f"  block_trade: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "block_trade_data", "fetched": total, "written": written}


def sync_margin_summary(days_back: int = 30) -> dict:
    """Sync pro.margin() — 融资融券市场汇总 (per-date)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "margin_summary", days_back)
    total, written = 0, 0
    cols = ["trade_date", "rzye", "rzmre", "rzche", "rqye", "rqmcl", "rzrqye"]
    for d in dates:
        _rate_limit()
        try: df = pro.margin(trade_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((d[:4]+"-"+d[4:6]+"-"+d[6:8],
                r.get("rzye"), r.get("rzmre"), r.get("rzche"),
                r.get("rqye"), r.get("rqmcl"), r.get("rzrqye")))
        total += len(rows)
        written += _insert_rows(db, "margin_summary", cols, rows)
    db.commit(); db.close()
    print(f"  margin_summary: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "margin_summary", "fetched": total, "written": written}


def sync_moneyflow_hsgt(days_back: int = 30) -> dict:
    """Sync pro.moneyflow_hsgt() — 沪深港通北向/南向资金流向 (per-date)."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "moneyflow_hsgt", days_back)
    total, written = 0, 0
    cols = ["trade_date", "ggt_ss", "ggt_sz", "hgt", "sgt", "north_money", "south_money"]
    for d in dates:
        _rate_limit()
        try: df = pro.moneyflow_hsgt(trade_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((d[:4]+"-"+d[4:6]+"-"+d[6:8],
                r.get("ggt_ss"), r.get("ggt_sz"), r.get("hgt"), r.get("sgt"),
                r.get("north_money"), r.get("south_money")))
        total += len(rows)
        written += _insert_rows(db, "moneyflow_hsgt", cols, rows)
    db.commit(); db.close()
    print(f"  moneyflow_hsgt: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "moneyflow_hsgt", "fetched": total, "written": written}


def sync_stk_holdertrade(days_back: int = 90) -> dict:
    """Sync pro.stk_holdertrade() — 股东增减持 (per-date batch)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["code", "ann_date", "holder_name", "holder_type", "in_de",
            "change_vol", "change_ratio"]
    for d in dates:
        _rate_limit()
        try: df = pro.stk_holdertrade(ann_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((_code_from_ts(r["ts_code"]),
                str(r.get("ann_date", d)), str(r.get("holder_name", "")),
                str(r.get("holder_type", "")), str(r.get("in_de", "")),
                r.get("change_vol"), r.get("change_ratio")))
        total += len(rows)
        written += _insert_rows(db, "stk_holdertrade", cols, rows)
    db.commit(); db.close()
    print(f"  stk_holdertrade: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "stk_holdertrade", "fetched": total, "written": written}


def sync_stk_holdernumber(days_back: int = 30) -> dict:
    """Sync pro.stk_holdernumber() — 股东人数 (top 500 stocks only for speed)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    db.row_factory = sqlite3.Row
    codes = [r["code"] for r in db.execute(
        "SELECT code FROM stocks WHERE is_st=0 AND (code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%' OR code LIKE '68%') "
        "ORDER BY market_cap DESC LIMIT 500").fetchall()]
    total, written = 0, 0
    cols = ["code", "end_date", "holder_num"]
    start = (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")
    for code in codes:
        _rate_limit()
        try: df = pro.stk_holdernumber(ts_code=_ts_code(code), start_date=start, end_date=end)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((code, str(r.get("end_date", "")), r.get("holder_num")))
        total += len(rows)
        written += _insert_rows(db, "stk_holdernumber", cols, rows)
    db.commit(); db.close()
    print(f"  stk_holdernumber: {total} fetched, {written} written ({len(codes)} stocks)")
    return {"status": "ok", "table": "stk_holdernumber", "fetched": total, "written": written}


def sync_pledge_detail(days_back: int = 30) -> dict:
    """Sync pro.pledge_detail() — 股权质押 (top 500 by market cap)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    db.row_factory = sqlite3.Row
    codes = [r["code"] for r in db.execute(
        "SELECT code FROM stocks WHERE is_st=0 AND (code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%' OR code LIKE '68%') "
        "ORDER BY market_cap DESC LIMIT 500").fetchall()]
    total, written = 0, 0
    cols = ["code", "ann_date", "pledgor", "pledgee", "pledge_amount", "pledge_total_ratio"]
    for code in codes:
        _rate_limit()
        try: df = pro.pledge_detail(ts_code=_ts_code(code))
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((code, str(r.get("ann_date", "")),
                str(r.get("pledgor", "")), str(r.get("pledgee", "")),
                r.get("pledge_amount"), r.get("pledge_total_ratio")))
        total += len(rows)
        written += _insert_rows(db, "pledge_detail", cols, rows)
    db.commit(); db.close()
    print(f"  pledge_detail: {total} fetched, {written} written ({len(codes)} stocks)")
    return {"status": "ok", "table": "pledge_detail", "fetched": total, "written": written}


def sync_repurchase(days_back: int = 90) -> dict:
    """Sync pro.repurchase() — 股票回购 (per-date batch)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["code", "ann_date", "end_date", "proc", "vol", "amount"]
    for d in dates:
        _rate_limit()
        try: df = pro.repurchase(ann_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((_code_from_ts(r["ts_code"]),
                str(r.get("ann_date", d)), str(r.get("end_date", "")),
                str(r.get("proc", "")), r.get("vol"), r.get("amount")))
        total += len(rows)
        written += _insert_rows(db, "repurchase", cols, rows)
    db.commit(); db.close()
    print(f"  repurchase: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "repurchase", "fetched": total, "written": written}


def sync_share_float(days_back: int = 90) -> dict:
    """Sync pro.share_float() — 限售解禁 (per-date batch)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    # Clean old data by ann_date
    cutoff = (datetime.now() - timedelta(days=days_back + 1)).strftime("%Y-%m-%d")
    db.execute("DELETE FROM share_float WHERE ann_date >= ?", (cutoff,))
    total, written = 0, 0
    cols = ["code", "ann_date", "float_date", "float_share", "float_ratio", "holder_name"]
    for d in dates:
        _rate_limit()
        try: df = pro.share_float(ann_date=d)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            rows.append((_code_from_ts(r["ts_code"]),
                str(r.get("ann_date", d)), str(r.get("float_date", "")),
                r.get("float_share"), r.get("float_ratio"),
                str(r.get("holder_name", ""))))
        total += len(rows)
        written += _insert_rows(db, "share_float", cols, rows)
    db.commit(); db.close()
    print(f"  share_float: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "share_float", "fetched": total, "written": written}


def sync_cyq_chips(days_back: int = 5) -> dict:
    """Sync pro.cyq_chips() — 筹码分布 (6000pts, per-stock for top 300 by market cap).

    API: cyq_chips(ts_code, trade_date) → per-price-level: [ts_code, trade_date, price, percent]
    Data available from 2018, updates daily 18-19h.
    """
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db(); db.row_factory = sqlite3.Row
    codes = [r["code"] for r in db.execute(
        "SELECT code FROM stocks WHERE is_st=0 AND market_cap>0 "
        "AND (code LIKE '00%' OR code LIKE '30%' OR code LIKE '60%' OR code LIKE '68%') "
        "ORDER BY market_cap DESC LIMIT 300").fetchall()]
    # Use last available trading date (data updates 18-19h daily)
    end = datetime.now()
    # Try last 5 trading days, use the one that returns data
    total, written = 0, 0
    cols = ["code", "trade_date", "price", "percent"]
    for code in codes:
        for offset in range(min(5, days_back)):
            d = (end - timedelta(days=offset)).strftime("%Y%m%d")
            _rate_limit()
            try:
                df = pro.cyq_chips(ts_code=_ts_code(code), trade_date=d)
            except: continue
            if df is None or df.empty: continue
            rows = [(code, d[:4]+"-"+d[4:6]+"-"+d[6:8],
                     r.get("price"), r.get("percent")) for _, r in df.iterrows()]
            total += len(rows)
            written += _insert_rows(db, "cyq_chips", cols, rows)
            break  # Got data for this stock, move on
    db.commit(); db.close()
    print(f"  cyq_chips: {total} fetched, {written} written ({len(codes)} stocks)")
    return {"status": "ok", "table": "cyq_chips", "fetched": total, "written": written}


def sync_broker_recommend(days_back: int = 90) -> dict:
    """Sync pro.broker_recommend() — 券商每月金股 (6000pts, monthly batch).

    API: broker_recommend(month='YYYYMM') → [month, broker, ts_code, name]
    Data published monthly (1st-3rd of each month for previous month).
    """
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["month", "broker", "code", "name"]
    # Sync last 6 months (data typically available with 1-month lag)
    today = datetime.now()
    for m_offset in range(1, 7):  # Start from last month
        month = (today - timedelta(days=30 * m_offset)).strftime("%Y%m")
        _rate_limit()
        try:
            df = pro.broker_recommend(month=month)
        except: continue
        if df is None or df.empty: continue
        rows = [(month, str(r.get("broker","")),
                 _code_from_ts(r["ts_code"]), str(r.get("name","")))
                for _, r in df.iterrows()]
        total += len(rows)
        written += _insert_rows(db, "broker_recommend", cols, rows)
    db.commit(); db.close()
    print(f"  broker_recommend: {total} fetched, {written} written (6 months)")
    return {"status": "ok", "table": "broker_recommend", "fetched": total, "written": written}


def sync_research_report(days_back: int = 3650) -> dict:
    """Sync pro.research_report() — 券商研报 (10 years, date-batched)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["trade_date", "title", "report_type", "author", "name", "code"]
    # Batch by 30-day windows (API returns max 1000 per call)
    today = datetime.now()
    for i in range(0, days_back, 30):
        end = (today - timedelta(days=i)).strftime("%Y%m%d")
        start = (today - timedelta(days=min(days_back, i+30))).strftime("%Y%m%d")
        _rate_limit()
        try: df = pro.research_report(start_date=start, end_date=end)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            td = str(r.get("trade_date", ""))
            rows.append((
                td[:4]+"-"+td[4:6]+"-"+td[6:8] if len(td)==8 else td,
                str(r.get("title", "")), str(r.get("report_type", "")),
                str(r.get("author", "")), str(r.get("name", "")),
                _code_from_ts(r["ts_code"]) if r.get("ts_code") else None,
            ))
        total += len(rows)
        written += _insert_rows(db, "research_reports_tushare", cols, rows)
        if (i//30+1) % 20 == 0:
            print(f"  research_report: {i//30+1}/{days_back//30} batches | {written:,} rows")
    db.commit(); db.close()
    print(f"  research_report: {total:,} fetched, {written:,} written (10yr)")
    return {"status": "ok", "table": "research_reports_tushare", "fetched": total, "written": written}


def sync_stock_news(days_back: int = 3650) -> dict:
    """Sync pro.major_news() + pro.news() — 新闻资讯 (10 years)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["pub_time", "title", "content", "source"]
    today = datetime.now()
    for i in range(0, days_back, 30):
        end = (today - timedelta(days=i)).strftime("%Y%m%d")
        start = (today - timedelta(days=min(days_back, i+30))).strftime("%Y%m%d")
        _rate_limit()
        # major_news
        try: df = pro.major_news(src="", start_date=start, end_date=end)
        except Exception: df = None
        if df is not None and not df.empty:
            rows = [(str(r.get("pub_time",""))[:10], str(r.get("title","")), "", str(r.get("src",""))) for _, r in df.iterrows()]
            total += len(rows)
            written += _insert_rows(db, "stock_news_tushare", cols, rows)
        # news
        try: df = pro.news(start_date=start, end_date=end)
        except Exception: df = None
        if df is not None and not df.empty:
            rows = [(str(r.get("datetime",""))[:10], str(r.get("title","")), str(r.get("content","")), "tushare_news") for _, r in df.iterrows()]
            total += len(rows)
            written += _insert_rows(db, "stock_news_tushare", cols, rows)
        if (i//30+1) % 20 == 0:
            print(f"  news: {i//30+1}/{days_back//30} batches | {written:,} rows")
    db.commit(); db.close()
    print(f"  stock_news: {total:,} fetched, {written:,} written (10yr)")
    return {"status": "ok", "table": "stock_news_tushare", "fetched": total, "written": written}


def sync_sw_daily(days_back: int = 3650) -> dict:
    """Sync pro.sw_daily() — 申万行业日线 (10 years, date-batched)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["ts_code", "trade_date", "name", "open", "high", "low", "close",
            "change", "pct_change", "pe", "pb", "float_mv", "total_mv", "vol", "amount"]
    today = datetime.now()
    for i in range(0, days_back, 30):
        end = (today - timedelta(days=i)).strftime("%Y%m%d")
        start = (today - timedelta(days=min(days_back, i+30))).strftime("%Y%m%d")
        _rate_limit()
        try: df = pro.sw_daily(start_date=start, end_date=end)
        except: continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            td = str(r.get("trade_date", ""))
            rows.append((
                str(r["ts_code"]), td[:4]+"-"+td[4:6]+"-"+td[6:8] if len(td)==8 else td,
                str(r.get("name", "")), r.get("open"), r.get("high"), r.get("low"),
                r.get("close"), r.get("change"), r.get("pct_change"),
                r.get("pe"), r.get("pb"), r.get("float_mv"), r.get("total_mv"),
                r.get("vol"), r.get("amount"),
            ))
        total += len(rows)
        written += _insert_rows(db, "sw_daily", cols, rows)
        if (i//30+1) % 20 == 0:
            print(f"  sw_daily: {i//30+1}/{days_back//30} batches | {written:,} rows")
    db.commit(); db.close()
    print(f"  sw_daily: {total:,} fetched, {written:,} written (10yr)")
    return {"status": "ok", "table": "sw_daily", "fetched": total, "written": written}


def sync_rt_sw_k(days_back: int = 1) -> dict:
    """Sync pro.rt_sw_k() — 申万实时行情 (snapshot, no history).

    Unlike sw_daily, rt_sw_k only returns current real-time snapshot.
    Should be called periodically (e.g., every 5 min during trading hours).
    """
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    cols = ["trade_time", "ts_code", "name", "close", "pre_close",
            "open", "high", "low", "vol", "amount", "pct_change"]
    try:
        df = pro.rt_sw_k()
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)[:80]}
    if df is None or df.empty:
        db.close()
        return {"status": "ok", "table": "rt_sw_k", "fetched": 0, "written": 0}
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get("trade_time", "")),
            str(r["ts_code"]), str(r.get("name", "")).strip(),
            r.get("close"), r.get("pre_close"),
            r.get("open"), r.get("high"), r.get("low"),
            r.get("vol"), r.get("amount"), r.get("pct_change"),
        ))
    total = len(rows)
    written = _insert_rows(db, "rt_sw_k", cols, rows)
    db.commit(); db.close()
    print(f"  rt_sw_k: {total} fetched, {written} written (SW indices real-time snapshot)")
    return {"status": "ok", "table": "rt_sw_k", "fetched": total, "written": written}


def sync_rt_k() -> dict:
    """Compute real-time daily K-line from stk_mins aggregation.

    rt_k (Tushare) requires separate ¥1000/mo permission. As an alternative,
    we aggregate stk_mins (already accessible) to produce the same data.

    Query the latest trade_date's minute bars, group by code to produce
    daily OHLCV bars. This is the same information rt_k would return.
    """
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    total, written = 0, 0
    try:
        # Get the latest trading day from stk_mins
        latest = db.execute(
            "SELECT MAX(trade_time) FROM stk_mins WHERE freq='5min'"
        ).fetchone()
        if not latest or not latest[0]:
            db.close()
            return {"status": "ok", "table": "rt_k", "fetched": 0, "written": 0,
                    "note": "no minute data available"}
        latest_dt = latest[0][:10]  # Extract date part
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)[:80]}

    cols = ["code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount"]
    try:
        # Aggregate 5-min bars into daily OHLCV
        rows = db.execute(
            "SELECT code, "
            "DATE(trade_time) as trade_date, "
            "FIRST_VALUE(open) OVER (PARTITION BY code ORDER BY trade_time) as open, "
            "MAX(high) as high, MIN(low) as low, "
            "LAST_VALUE(close) OVER (PARTITION BY code ORDER BY trade_time "
            "  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as close, "
            "SUM(volume) as vol, SUM(amount) as amount "
            "FROM stk_mins "
            "WHERE DATE(trade_time) = ? AND freq='5min' "
            "GROUP BY code",
            (latest_dt,)
        ).fetchall()
        total = len(rows)
        if total > 0:
            inserted = 0
            for r in rows:
                try:
                    db.execute(
                        "INSERT OR REPLACE INTO rt_k "
                        "(code, trade_date, open, high, low, close, vol, amount) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7])
                    )
                    inserted += 1
                except Exception:
                    pass
            written = inserted
            db.commit()
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)[:80]}
    db.close()
    print(f"  rt_k: {total} stocks aggregated from stk_mins ({latest_dt}), {written} written")
    return {"status": "ok", "table": "rt_k", "fetched": total, "written": written}


def sync_stk_auction_o(trade_date: str = None) -> dict:
    """Sync pro.stk_auction_o() — 开盘集合竞价数据 (盘后更新, 9:30后可得).

    Returns auction details per stock: open/close/high/low/vol/amount/vwap.
    Requires Tushare 集合竞价 permission (¥500/yr).

    Args:
        trade_date: YYYYMMDD format, defaults to today.
    """
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")
    total, written = 0, 0
    try:
        df = pro.stk_auction_o(trade_date=trade_date)
    except Exception as e:
        err = str(e)
        if "权限" in err or "permission" in err.lower():
            return {"status": "no_permission", "reason": "stk_auction_o requires ¥500/yr permission"}
        return {"status": "error", "reason": err[:80]}
    if df is None or df.empty:
        return {"status": "ok", "table": "stk_auction_o", "fetched": 0, "written": 0}

    # Actual fields: ts_code, trade_date, close, open, high, low, vol, amount, vwap
    db = _get_etl_db()
    cols = ["ts_code", "trade_date", "close", "open", "high", "low", "vol", "amount", "vwap"]
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get("ts_code", "")),
            str(r.get("trade_date", "")),
            r.get("close"), r.get("open"), r.get("high"), r.get("low"),
            r.get("vol"), r.get("amount"), r.get("vwap"),
        ))
    total = len(rows)
    written = _insert_rows(db, "stk_auction_o", cols, rows)
    db.commit(); db.close()
    print(f"  stk_auction_o: {total} fetched, {written} written ({trade_date})")
    return {"status": "ok", "table": "stk_auction_o", "fetched": total, "written": written}


def sync_all_new_apis(days_back: int = 3650) -> dict:
    """Sync all 3 newly purchased APIs: research_report + news + rt_sw_k."""
    results = {}
    print("\n=== Syncing new APIs (research_report + news + rt_sw_k) ===")
    results["research_report"] = sync_research_report(days_back)
    results["stock_news"] = sync_stock_news(days_back)
    results["sw_daily"] = sync_sw_daily(days_back)
    results["rt_sw_k"] = sync_rt_sw_k()
    ok = sum(1 for r in results.values() if r.get("status") == "ok")
    print(f"\nNew APIs sync: {ok}/{len(results)} ok")
    return {"status": "ok", "results": results}


# ═══════════════════════════════════════════════════════════════
# Main entry
# ═══════════════════════════════════════════════════════════════

def sync_stk_mins(days_back: int = 5) -> dict:
    """Sync Tushare stk_mins (5min K-line) — per-date, all codes."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db(); total = written = 0
    clean_before_write(db, "stk_mins", days_back + 1, "trade_time")
    cols = ["code", "trade_time", "open", "high", "low", "close", "volume", "amount", "freq"]
    for td in dates:
        try:
            df = pro.stk_mins(freq="5min", start_date=f"{td} 09:30:00", end_date=f"{td} 15:00:00")
            _rate_limit()
            if df is None or df.empty: continue
            rows = [
                (_code_from_ts(str(r.get("ts_code", ""))), str(r.get("trade_time", "")),
                 r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                 r.get("vol"), r.get("amount"), "5min")
                for _, r in df.iterrows()
            ]
            total += len(rows)
            written += _insert_rows(db, "stk_mins", cols, rows)
        except Exception as e:
            err = str(e)
            if "token" in err.lower() or "权限" in err:
                db.close()
                return {"status": "error", "reason": err[:80]}
    db.close()
    print(f"  stk_mins: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "stk_mins", "fetched": total, "written": written}


def sync_daily_kline(days_back: int = 30) -> dict:
    """Sync Tushare daily (日K线行情) — full OHLCV per date."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db(); total = written = 0
    cols = ["ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount"]
    for td in dates:
        try:
            df = pro.daily(trade_date=td)
            _rate_limit()
            if df is None or df.empty: continue
            rows = [(str(r["ts_code"]), str(r["trade_date"]),
                     r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                     r.get("pre_close"), r.get("change"), r.get("pct_chg"),
                     r.get("vol"), r.get("amount")) for _, r in df.iterrows()]
            total += len(rows)
            written += _insert_rows(db, "daily_kline", cols, rows)
        except Exception as e:
            if "token" in str(e).lower(): return {"status": "error", "reason": str(e)[:80]}
    db.close()
    print(f"  daily_kline: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "daily_kline", "fetched": total, "written": written}


def sync_limit_list_d(days_back: int = 30) -> dict:
    """Sync Tushare limit_list_d (涨跌停明细)."""
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db(); total = written = 0
    cols = ["ts_code", "trade_date", "limit_type", "up_limit", "down_limit",
            "first_time", "last_time", "open_times", "up_stat", "fd_amount",
            "pct_chg", "pre_close", "close", "open"]
    for td in dates:
        for lt in ("U", "D", "Z"):
            try:
                df = pro.limit_list_d(trade_date=td, limit_type=lt)
                _rate_limit()
                if df is None or df.empty: continue
                rows = [(str(r.get("ts_code", "")), str(r.get("trade_date", td)),
                         lt, r.get("up_limit"), r.get("down_limit"),
                         r.get("first_time"), r.get("last_time"), r.get("open_times"),
                         r.get("up_stat"), r.get("fd_amount"),
                         r.get("pct_chg"), r.get("pre_close"),
                         r.get("close"), r.get("open")) for _, r in df.iterrows()]
                total += len(rows)
                written += _insert_rows(db, "limit_list_d", cols, rows)
            except Exception:
                pass
    db.close()
    print(f"  limit_list_d: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "limit_list_d", "fetched": total, "written": written}


SYNC_MODES = {
    "moneyflow": sync_moneyflow,
    "hk_hold": sync_hk_hold,
    "margin": sync_margin,
    "top_list": sync_top_list,
    "daily_basic": sync_daily_basic,
    "stk_limit": sync_stk_limit,
    "weekly": sync_weekly_kline,
    "monthly": sync_monthly_kline,
    "adj_factor": sync_adj_factor,
    "index_basic": sync_index_basic,
    "index_daily": sync_index_daily,
    "daily_kline": sync_daily_kline,
    "limit_list": sync_limit_list_d,
    "income": sync_income,
    "balancesheet": sync_balancesheet,
    "cashflow": sync_cashflow,
    "fina_indicator": sync_financial_indicator,
    "forecast": sync_forecast_data,
    "dividend": sync_dividend_data,
    "top_inst": sync_top_inst,
    "block_trade": sync_block_trade_data,
    "margin_summary": sync_margin_summary,
    "moneyflow_hsgt": sync_moneyflow_hsgt,
    "stk_holdertrade": sync_stk_holdertrade,
    "stk_holdernumber": sync_stk_holdernumber,
    "pledge_detail": sync_pledge_detail,
    "repurchase": sync_repurchase,
    "share_float": sync_share_float,
    "cyq_chips": sync_cyq_chips,
    "broker_recommend": sync_broker_recommend,
    "research_report": sync_research_report,
    "stock_news": sync_stock_news,
    "sw_daily": sync_sw_daily,
    "rt_sw_k": sync_rt_sw_k,
    "rt_k": sync_rt_k,
    "stk_mins": sync_stk_mins,
    "stk_auction_o": sync_stk_auction_o,
    "all_new": sync_all_new_apis,
}


def sync_tushare_data(mode: str = "all", days: int = 30) -> dict:
    """Main sync entry point — dispatch to all or specific sync functions.

    Args:
        mode: "all" or one of moneyflow/hk_hold/margin/top_list/daily_basic
        days: how many days back to sync

    Returns:
        {"status": "ok"/"error", "tables": {...per-table results...}, "elapsed": float}
    """
    t0 = time.time()
    print(f"\n[Sync] Tushare premium data ({mode}, {days}d back)")

    if mode == "all":
        modes = list(SYNC_MODES.keys())
    elif mode in SYNC_MODES:
        modes = [mode]
    else:
        print(f"  Unknown mode: {mode}. Options: all, {', '.join(SYNC_MODES)}")
        return {"status": "error", "reason": f"unknown mode: {mode}"}

    results = {}
    for m in modes:
        try:
            results[m] = SYNC_MODES[m](days)
        except Exception as e:
            results[m] = {"status": "error", "reason": str(e)}
            print(f"  {m}: ERROR — {e}")

    elapsed = time.time() - t0
    ok = sum(1 for r in results.values() if r.get("status") == "ok")
    skipped = sum(1 for r in results.values() if r.get("status") == "skipped")
    print(f"  Done: {ok} ok, {skipped} skipped, {len(results)-ok-skipped} failed "
          f"({elapsed:.0f}s)")

    return {"status": "ok" if ok > 0 else "skipped",
            "tables": results, "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(
        description="Tushare premium data sync")
    parser.add_argument("--mode", type=str, default="all",
                        help=f"Table to sync: all, {', '.join(SYNC_MODES)}")
    parser.add_argument("--days", type=int, default=30,
                        help="Days back to sync (default 30)")
    args = parser.parse_args()

    os.chdir(_PROJ)
    sync_tushare_data(mode=args.mode, days=args.days)


if __name__ == "__main__":
    main()
