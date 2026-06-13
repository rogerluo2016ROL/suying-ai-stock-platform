"""PostgreSQL database adapter for kronos-factors.

Usage:
    from kronos_factors.pg_adapter import create_pg_adapter
    set_db_adapter(create_pg_adapter(os.environ['KRONOS_PG_URL']))
"""

import logging, os, re
from typing import Optional
import pandas as pd

logger = logging.getLogger("kronos-factors.pg")


def create_pg_adapter(pg_url: str = None):
    """Create a PG-based DB adapter. Falls back to SQLite if PG unavailable."""
    pg_url = pg_url or os.environ.get('KRONOS_PG_URL', '')
    sqlite_path = os.environ.get('KRONOS_SQLITE_PATH', '')

    if pg_url:
        try:
            import psycopg2
            import psycopg2.extras
            return _PgAdapter(pg_url)
        except ImportError:
            logger.warning("psycopg2 not installed, falling back to SQLite")
        except Exception as e:
            logger.warning("PG connection failed: %s, falling back to SQLite", e)

    if sqlite_path:
        return _SqliteFallbackAdapter(sqlite_path)

    return None


def _translate_sqlite_date(m: re.Match) -> str:
    """Translate SQLite date('now', ...) to PostgreSQL CURRENT_DATE +/- INTERVAL."""
    modifier = m.group(1)  # e.g. '-90 days', 'start of month', etc.
    if not modifier:
        return "CURRENT_DATE"
    # Handle '-N days' / '+N days' modifiers
    days_match = re.match(r'([+-]\d+)\s*days?', modifier)
    if days_match:
        days = days_match.group(1)
        op = '+' if days.startswith('+') else '-'
        n = days.lstrip('+-')
        return f"CURRENT_DATE - INTERVAL '{n} days'"
    return "CURRENT_DATE"  # fallback for unsupported modifiers


class _PgAdapter:
    """PostgreSQL adapter for kronos-factors — thread-safe connection pool."""

    def __init__(self, pg_url: str):
        import psycopg2
        from psycopg2.pool import ThreadedConnectionPool
        self.pg_url = pg_url
        self._pool = ThreadedConnectionPool(minconn=2, maxconn=10, dsn=pg_url, connect_timeout=5)

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn):
        try:
            self._pool.putconn(conn)
        except Exception:
            pass  # connection may already be closed/invalid

    # Column name mapping: SQLite (engine) → PostgreSQL (Tushare)
    _COLUMN_MAP = {
        "pct_chg": "change_pct",
        "pct_change": "change_pct",   # ths_daily/sw_daily Tushare API field name
        "ts_code": "code",
    }

    def execute(self, sql: str, params: tuple = None):
        conn = self._get_conn()
        conn.autocommit = True  # read-only queries, no transaction needed
        try:
            cur = conn.cursor()
            # If query uses SQLite ? placeholders, translate to PG %s
            if '?' in sql:
                sql_pg = sql.replace('%', '%%').replace('?', '%s')
                param_tuple = tuple(params) if params else None
            else:
                sql_pg = sql
                param_tuple = params
            # Translate SQLite column names to PG column names (word-boundary aware)
            for old, new in self._COLUMN_MAP.items():
                sql_pg = re.sub(rf'\b{re.escape(old)}\b', new, sql_pg)
            # Translate SQLite date functions to PG equivalents
            sql_pg = re.sub(r"date\('now'(?:,'([^']*)')?\)", _translate_sqlite_date, sql_pg)
            # Handle 'latest' date params → PG subquery (tuple params only)
            if param_tuple and isinstance(param_tuple, (tuple, list)):
                params_list = list(param_tuple)
                for i, p in enumerate(params_list):
                    if isinstance(p, str) and re.match(r'^\d{6}\.(XSHE|XSHG|SZ|SH|BJ)$', p):
                        params_list[i] = p.split('.')[0]
                if params_list and any(p == 'latest' for p in params_list):
                    for i, p in enumerate(params_list):
                        if p == 'latest':
                            table_match = re.search(r'FROM\s+(\w+)', sql_pg, re.IGNORECASE)
                            if table_match:
                                table = table_match.group(1)
                                sql_pg = sql_pg.replace('%s', f"(SELECT MAX(trade_date) FROM {table})", 1)
                                params_list[i] = None
                    params_list = [p for p in params_list if p is not None]
                param_tuple = tuple(params_list) if params_list else None
            try:
                cur.execute(sql_pg, param_tuple or None)
            except Exception as e:
                err = str(e)
                # Handle previous aborted transaction — rollback and retry once
                if 'InFailedSqlTransaction' in err or 'current transaction is aborted' in err:
                    conn.rollback()
                    conn.autocommit = True
                    cur = conn.cursor()
                    cur.execute(sql_pg, param_tuple or None)
                # Graceful degradation: missing table/column/division-by-zero → return empty
                elif any(k in err for k in ('does not exist', 'UndefinedColumn', 'UndefinedTable',
                                             'DivisionByZero', 'division by zero')):
                    logger.debug("PG graceful degradation: %s — SQL: %s", err[:100], sql_pg[:120])
                    conn.rollback()
                    self._put_conn(conn)
                    return _EmptyCursor()
                else:
                    self._put_conn(conn)
                    raise
            # Eagerly fetch all results so we can return the connection to the pool
            col_names = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
            self._put_conn(conn)
            return _PgResult(col_names, rows)
        except Exception:
            self._put_conn(conn)
            raise

    def get_kline(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        conn = None
        try:
            conn = self._get_conn()
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute(
                "SELECT trade_date, open, high, low, close, volume, amount "
                "FROM daily_kline WHERE code=%s ORDER BY trade_date DESC LIMIT %s",
                (code, lookback))
            rows = cur.fetchall()
            if not rows:
                self._put_conn(conn)
                return None
            df = pd.DataFrame([dict(zip(['trade_date','open','high','low','close','volume','amount'], r))
                               for r in reversed(rows)])
            df['timestamps'] = pd.to_datetime(df['trade_date'])
            self._put_conn(conn)
            return df
        except Exception:
            if conn:
                self._put_conn(conn)
            return None

    def get_stock_info(self, code: str) -> Optional[dict]:
        conn = None
        try:
            conn = self._get_conn()
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("SELECT * FROM stocks WHERE code=%s", (code,))
            row = cur.fetchone()
            result = dict(zip([d[0] for d in cur.description], row)) if row else None
            self._put_conn(conn)
            return result
        except Exception:
            if conn:
                self._put_conn(conn)
            return None

    def get_all_codes(self, exclude_st: bool = True) -> list[str]:
        conn = None
        try:
            conn = self._get_conn()
            conn.autocommit = True
            cur = conn.cursor()
            if exclude_st:
                cur.execute("SELECT code FROM stocks WHERE is_st=0 ORDER BY code")
            else:
                cur.execute("SELECT code FROM stocks ORDER BY code")
            codes = [r[0] for r in cur.fetchall()]
            self._put_conn(conn)
            return codes
        except Exception:
            if conn:
                self._put_conn(conn)
            return []

    # MarketDataAdapter interface
    def get_kline_df(self, code: str, lookback: int = 400) -> Optional[pd.DataFrame]:
        """Get K-line DataFrame (MarketDataAdapter interface)."""
        return self.get_kline(code, lookback)

    def sync_stock_list(self) -> int: return 0
    def update_daily_kline(self, from_date: str) -> int: return 0

    def __enter__(self): return self
    def __exit__(self, *args): pass


class _EmptyCursor:
    def __init__(self):
        logger.debug("PG query returned empty cursor — data may be missing (table/column not found or division by zero)")
    def fetchone(self): return None
    def fetchall(self): return []

class _PgResult:
    """Eagerly-fetched result wrapper — holds pre-fetched data, no live cursor needed.

    This avoids keeping a live PostgreSQL cursor (and its connection) open,
    which is critical for thread-safe connection pooling.
    """
    # Result key mapping: PG column → engine-expected column (one-direction only)
    _KEY_MAP = {"change_pct": "pct_chg"}

    def __init__(self, col_names: list[str], rows: list[tuple]):
        self._col_names = col_names
        self._rows = rows
        self._idx = 0

    def _map_row(self, row_tuple) -> dict:
        result = {}
        for k, v in zip(self._col_names, row_tuple):
            from datetime import date, datetime as dt
            if isinstance(v, (date, dt)):
                v = str(v)
            result[self._KEY_MAP.get(k, k)] = v
        return result

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return self._map_row(row)

    def fetchall(self):
        return [self._map_row(r) for r in self._rows]


class _SqliteFallbackAdapter:
    def __init__(self, db_path): self.db_path = db_path
    def execute(self, sql, params=None):
        import sqlite3
        c = sqlite3.connect(self.db_path); c.row_factory = sqlite3.Row
        cur = c.cursor(); cur.execute(sql, params or ())
        class W:
            def fetchone(s): r = cur.fetchone(); return dict(r) if r else None
            def fetchall(s): return [dict(r) for r in cur.fetchall()]
        return W()
    def get_kline(self, c, l=400): return None
    def get_stock_info(self, c): return None
    def get_all_codes(self, e=True): return []
    def __enter__(s): return s
    def __exit__(s,*a): pass
