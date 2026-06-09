"""Market data acquisition service — Tushare-primary multi-source A-share data.

Sources (priority order):
  1. Tushare  (primary) — stock_basic + daily K-line + daily_basic (10000pts)
  2. mootdx   (fallback 1) — stock list + daily K-line
  3. tencent  (fallback 2) — historical K-line via gtimg.cn
  4. akshare  (fallback 3) — stock list + daily K-line (last resort)

Public API (unchanged signatures for backward compatibility):
  - sync_stock_list() -> dict
  - update_daily_kline(code, from_date) -> dict
  - get_kline_df(code, lookback) -> pd.DataFrame
  - get_stock_info(code) -> dict
  - is_trading_day(date_str) -> bool
"""
import json
import logging
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pandas as pd

from webui.services.database import get_db

logger = logging.getLogger("kronos-webui.market")

# ── Mootdx client (lazy singleton) ─────────────────────────────────
_mootdx_client = None


def _get_mootdx_client():
    """Lazy-init mootdx standard quotes client with best-IP selection."""
    global _mootdx_client
    if _mootdx_client is not None:
        return _mootdx_client
    try:
        from mootdx.quotes import Quotes
        _mootdx_client = Quotes.factory(market="std", multithread=True, heartbeat=True)
        logger.info("mootdx client initialized (std market, multithread)")
    except Exception:
        logger.exception("mootdx init failed")
        _mootdx_client = False
    return _mootdx_client


def _is_mootdx_available() -> bool:
    return _get_mootdx_client() is not False


# ── Market prefix helpers ──────────────────────────────────────────

def _market_prefix(code: str) -> str:
    """Return 'sh', 'sz', or 'bj' prefix for a 6-digit A-share code."""
    if code.startswith(("6", "5")):
        return "sh"
    if code.startswith(("9", "4", "8")):
        return "bj"
    return "sz"


def _classify_board(code: str) -> str:
    if code.startswith("688"):
        return "科创板"
    if code.startswith("300") or code.startswith("301"):
        return "创业板"
    if code.startswith("6") or code.startswith("5"):
        return "沪市主板"
    if code.startswith(("00", "001", "002", "003")):
        return "深市主板"
    return "北交所"


# ── Data-source implementations ────────────────────────────────────

# --- mootdx (primary) ---

def _fetch_stock_list_mootdx() -> Optional[pd.DataFrame]:
    """Fetch full A-share stock list from mootdx. Returns DataFrame with code, name."""
    client = _get_mootdx_client()
    if not client:
        return None
    try:
        dfs = []
        for mkt in (0, 1):  # 0=深圳, 1=上海
            df = client.stocks(market=mkt)
            if df is not None and not df.empty:
                dfs.append(df[["code", "name"]])
        if dfs:
            result = pd.concat(dfs, ignore_index=True)
            result["code"] = result["code"].astype(str).str.strip()
            result["name"] = result["name"].astype(str).str.strip()
            result = result[result["code"].str.match(r"^\d{6}$")]
            logger.info("mootdx stock list: %d stocks", len(result))
            return result
    except Exception:
        logger.exception("mootdx stock list fetch failed")
    return None


def _fetch_kline_mootdx(code: str, count: int = 400) -> Optional[pd.DataFrame]:
    """Fetch daily K-line from mootdx. Returns DataFrame with standard columns."""
    client = _get_mootdx_client()
    if not client:
        return None
    try:
        df = client.bars(symbol=code, frequency=4, offset=count)
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "date": "trade_date", "open": "open", "high": "high",
            "low": "low", "close": "close",
            "volume": "volume", "amount": "amount",
        })
        # Normalise date format
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        cols = ["trade_date", "open", "high", "low", "close", "volume", "amount"]
        available = [c for c in cols if c in df.columns]
        return df[available]
    except Exception:
        logger.debug("mootdx kline failed for %s", code)
    return None


# --- Tencent API (fallback 1) ---

_TENCENT_HEADERS = {
    "Referer": "https://finance.qq.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}
_TENCENT_KL_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    "?param={prefix}{code},day,,,{count},qfq"
)


def _fetch_kline_tencent(code: str, count: int = 400) -> Optional[pd.DataFrame]:
    """Fetch daily K-line from Tencent API. Returns DataFrame with standard columns.

    Tencent field order: [date, open, close, high, low, volume] — note close/high swap!
    """
    prefix = _market_prefix(code)
    url = _TENCENT_KL_URL.format(prefix=prefix, code=code, count=count)
    try:
        req = urllib.request.Request(url, headers=_TENCENT_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("gbk", errors="replace")
    except Exception:
        logger.debug("Tencent API unreachable for %s", code)
        return None

    # Strip JS variable wrapper
    try:
        json_str = raw.split("=", 1)[1].strip()
        data = json.loads(json_str)
    except (IndexError, json.JSONDecodeError):
        logger.debug("Tencent JSON parse failed for %s", code)
        return None

    if data.get("code") != 0:
        return None

    stock_key = f"{prefix}{code}"
    stock_data = data.get("data", {}).get(stock_key, {})
    klines = stock_data.get("qfqday") or stock_data.get("day") or []
    if not klines:
        return None

    rows = []
    for row in klines:
        try:
            if len(row) < 6:
                continue
            rows.append({
                "trade_date": str(row[0])[:10],
                "open": float(row[1]),
                "close": float(row[2]),   # Tencent: close at index 2
                "high": float(row[3]),     # Tencent: high at index 3
                "low": float(row[4]),      # Tencent: low at index 4
                "volume": float(row[5]),
            })
        except (ValueError, TypeError, IndexError):
            continue

    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["amount"] = df["close"] * df["volume"]  # Tencent doesn't provide amount
    return df[["trade_date", "open", "high", "low", "close", "volume", "amount"]]


# --- akshare (fallback 2 / last resort) ---

def _fetch_stock_list_akshare() -> Optional[pd.DataFrame]:
    """Fetch full A-share stock list from akshare."""
    try:
        import akshare as ak
    except ImportError:
        logger.error("akshare not installed")
        return None
    try:
        df = ak.stock_zh_a_spot_em()
        df = df.rename(columns={"代码": "code", "名称": "name"})
        df["code"] = df["code"].astype(str).str.strip()
        return df[["code", "name"]]
    except Exception:
        try:
            sh = ak.stock_info_sh_name_code()
            sz = ak.stock_info_sz_name_code()
            df = pd.concat([sh, sz], ignore_index=True)
            df = df.rename(columns={"证券代码": "code", "证券简称": "name"})
            df["code"] = df["code"].astype(str).str.strip()
            return df[["code", "name"]]
        except Exception:
            logger.exception("akshare stock list fetch failed")
    return None


def _fetch_kline_akshare(code: str, from_date: str) -> Optional[pd.DataFrame]:
    """Fetch daily K-line from akshare."""
    try:
        import akshare as ak
    except ImportError:
        return None
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=from_date,
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "日期": "trade_date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low",
            "成交量": "volume", "成交额": "amount",
            "换手率": "turnover_rate", "涨跌幅": "change_pct",
            "振幅": "amplitude",
        })
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        cols = ["trade_date", "open", "high", "low", "close", "volume", "amount",
                "turnover_rate", "change_pct", "amplitude"]
        available = [c for c in cols if c in df.columns]
        return df[available]
    except Exception:
        logger.debug("akshare kline failed for %s", code)
    return None


# ── Tushare (primary) ──────────────────────────────────────────────

def _get_tushare_pro():
    """Lazy-init Tushare pro_api. Returns None if token not set."""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        return None
    try:
        import tushare as ts
        ts.set_token(token)
        return ts.pro_api()
    except ImportError:
        return None


def _fetch_stock_list_tushare() -> Optional[pd.DataFrame]:
    """Fetch full A-share stock list from Tushare stock_basic (list_status='L')."""
    pro = _get_tushare_pro()
    if pro is None:
        return None
    try:
        df = pro.stock_basic(
            exchange="", list_status="L",
            fields="ts_code,symbol,name,area,industry,list_date,is_hs,market"
        )
        if df is None or df.empty:
            return None
        df["code"] = df["symbol"].astype(str).str.strip()
        df["name"] = df["name"].astype(str).str.strip()
        df["industry"] = df["industry"].astype(str).str.strip()
        df["list_date"] = df["list_date"].astype(str).str.strip()
        df = df[df["code"].str.match(r"^\d{6}$")]
        logger.info("Tushare stock_basic: %d stocks", len(df))
        return df
    except Exception:
        logger.debug("Tushare stock_basic failed")
    return None


def _fetch_kline_tushare(code: str, count: int = 400) -> Optional[pd.DataFrame]:
    """Fetch daily K-line from Tushare for a single stock."""
    pro = _get_tushare_pro()
    if pro is None:
        return None
    from datetime import timedelta
    ts_code = f"{code}.SH" if code.startswith(("6", "5")) else \
               f"{code}.BJ" if code.startswith(("9", "4", "8")) else f"{code}.SZ"
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")
        df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            return None
        df = df.rename(columns={
            "trade_date": "trade_date", "open": "open", "high": "high",
            "low": "low", "close": "close", "vol": "volume", "amount": "amount",
        })
        df["trade_date"] = df["trade_date"].apply(
            lambda x: f"{str(x)[:4]}-{str(x)[4:6]}-{str(x)[6:8]}" if len(str(x)) == 8 else str(x)
        )
        df = df.sort_values("trade_date").tail(count)
        cols = ["trade_date", "open", "high", "low", "close", "volume", "amount"]
        return df[cols]
    except Exception:
        logger.debug("Tushare daily failed for %s", code)
    return None


# ── Orchestrator ───────────────────────────────────────────────────

def _fetch_kline_with_fallback(code: str, count: int = 400,
                                from_date: str = "20200101") -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    """Try data sources in order; return (source_name, DataFrame) or (None, None).
    Priority: Tushare → mootdx → Tencent → akshare."""
    # Primary: Tushare
    df = _fetch_kline_tushare(code, count)
    if df is not None and not df.empty:
        return "tushare", df

    # Fallback 1: mootdx
    df = _fetch_kline_mootdx(code, count)
    if df is not None and not df.empty:
        return "mootdx", df

    # Fallback 2: Tencent
    df = _fetch_kline_tencent(code, count)
    if df is not None and not df.empty:
        return "tencent", df

    # Fallback 3: akshare
    df = _fetch_kline_akshare(code, from_date)
    if df is not None and not df.empty:
        return "akshare", df

    return None, None


# ── Public API (unchanged signatures) ──────────────────────────────

class MarketDataService:
    """Acquires and manages A-share full-market data with multi-source fallback."""

    @staticmethod
    def sync_stock_list() -> dict:
        """Sync full A-share stock list into DB. Returns summary dict."""
        logger.info("Syncing A-share stock list...")
        t0 = time.time()

        # Try Tushare first, then mootdx, then akshare
        df = _fetch_stock_list_tushare()
        source = "tushare"
        if df is None:
            df = _fetch_stock_list_mootdx()
            source = "mootdx"
        if df is None:
            df = _fetch_stock_list_akshare()
            source = "akshare"
        if df is None:
            return {"status": "error", "message": "All stock-list sources failed"}

        new_count = 0
        update_count = 0
        has_tushare = source == "tushare"

        with get_db() as db:
            for _, row in df.iterrows():
                code = str(row.get("code", "")).strip()
                name = str(row.get("name", "")).strip()
                if not code or len(code) != 6 or not code.isdigit():
                    continue

                industry = str(row.get("industry", "")) if has_tushare and pd.notna(row.get("industry")) else None
                list_date = str(row.get("list_date", "")) if has_tushare and pd.notna(row.get("list_date")) else None
                is_hs = 1 if has_tushare and str(row.get("is_hs", "")).upper() == "Y" else None

                existing = db.execute(
                    "SELECT code FROM stocks WHERE code=?", (code,)
                ).fetchone()

                if existing:
                    updates = ["name=?, updated_at=?"]
                    params = [name, datetime.now().isoformat()]
                    if industry:
                        updates.append("industry=?")
                        params.append(industry)
                    if list_date:
                        updates.append("listed_date=?")
                        params.append(list_date)
                    params.append(code)
                    db.execute(f"UPDATE stocks SET {', '.join(updates)} WHERE code=?", params)
                    update_count += 1
                else:
                    board = _classify_board(code)
                    db.execute(
                        "INSERT INTO stocks(code,name,board,industry,listed_date,is_st,updated_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (code, name, board,
                         industry,
                         list_date,
                         1 if "ST" in name or "*ST" in name else 0,
                         datetime.now().isoformat()),
                    )
                    new_count += 1

        elapsed = time.time() - t0
        logger.info("Stock list synced via %s: %d new, %d updated (%.1fs)",
                     source, new_count, update_count, elapsed)
        return {
            "status": "ok",
            "source": source,
            "total": new_count + update_count,
            "new": new_count,
            "updated": update_count,
            "elapsed": round(elapsed, 1),
        }

    @staticmethod
    def sync_stock_financials() -> dict:
        """Sync PE/PB/market-cap/industry from Tushare daily_basic (primary) or akshare (fallback).

        Uses the daily_basic table (synced by tushare_sync.py) as the primary source.
        Falls back to akshare if Tushare data is unavailable.
        """
        logger.info("Syncing stock financials (PE/PB/MV)...")
        t0 = time.time()

        # Try Tushare daily_basic table first
        if os.environ.get("TUSHARE_TOKEN"):
            from webui.services.database import get_db as _get_db
            updated = 0
            failed = 0
            try:
                with _get_db(readonly=True) as rdb:
                    latest_date = rdb.execute(
                        "SELECT MAX(trade_date) FROM daily_basic"
                    ).fetchone()[0]
                if latest_date:
                    with _get_db() as wdb:
                        rows = wdb.execute(
                            "SELECT code, pe, pe_ttm, pb, total_mv, circ_mv "
                            "FROM daily_basic WHERE trade_date=?",
                            (latest_date,),
                        ).fetchall()
                        for r in rows:
                            try:
                                wdb.execute(
                                    "UPDATE stocks SET pe_ratio=?, pb_ratio=?, "
                                    "market_cap=?, float_mv=?, "
                                    "updated_at=datetime('now','localtime') "
                                    "WHERE code=?",
                                    (r["pe_ttm"] or r["pe"], r["pb"],
                                     r["total_mv"], r["circ_mv"], r["code"]),
                                )
                                updated += 1
                            except Exception:
                                failed += 1
                    elapsed = time.time() - t0
                    logger.info("Stock financials synced via Tushare: %d updated, %d failed (%.1fs)",
                                updated, failed, elapsed)
                    return {"status": "ok", "source": "tushare_daily_basic",
                            "date": latest_date, "updated": updated,
                            "failed": failed, "elapsed": round(elapsed, 1)}
            except Exception:
                logger.debug("Tushare daily_basic financial sync failed, falling back to akshare")

        # Fallback to akshare
        logger.info("Falling back to akshare for financial data...")
        try:
            import akshare as ak
        except ImportError:
            return {"status": "error", "message": "akshare not installed"}

        try:
            df = ak.stock_zh_a_spot_em()
        except Exception:
            logger.exception("akshare stock_zh_a_spot_em failed")
            return {"status": "error", "message": "akshare API failed"}

        if df is None or df.empty:
            return {"status": "error", "message": "Empty response from akshare"}

        col_map = {
            "代码": "code",
            "市盈率-动态": "pe_ratio",
            "市净率": "pb_ratio",
            "总市值": "market_cap",
            "流通市值": "float_mv",
            "行业": "industry",
        }
        df = df.rename(columns=col_map)
        df["code"] = df["code"].astype(str).str.strip()

        updated = 0
        failed = 0

        with get_db() as db:
            for _, row in df.iterrows():
                code = row.get("code", "")
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                try:
                    db.execute(
                        """UPDATE stocks SET
                            pe_ratio=?, pb_ratio=?, market_cap=?,
                            float_mv=?, industry=?,
                            updated_at=datetime('now','localtime')
                        WHERE code=?""",
                        (
                            _float_or_none(row, "pe_ratio"),
                            _float_or_none(row, "pb_ratio"),
                            _float_or_none(row, "market_cap"),
                            _float_or_none(row, "float_mv"),
                            str(row.get("industry", "")) if pd.notna(row.get("industry")) else None,
                            code,
                        ),
                    )
                    updated += 1
                except Exception:
                    failed += 1

        elapsed = time.time() - t0
        logger.info("Stock financials synced via akshare: %d updated, %d failed (%.1fs)",
                     updated, failed, elapsed)
        return {
            "status": "ok", "source": "akshare",
            "updated": updated,
            "failed": failed,
            "elapsed": round(elapsed, 1),
        }

    @staticmethod
    def update_daily_kline(code: Optional[str] = None,
                           from_date: Optional[str] = None) -> dict:
        """Update daily K-line data using multi-source fallback + concurrent fetching.

        Args:
            code: single stock code, or None for all stocks in DB
            from_date: start date (YYYYMMDD), defaults to 1 year ago
        """
        if from_date is None:
            from_date = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

        codes = [code] if code else _get_all_codes()
        if not codes:
            return {"status": "error", "message": "No stocks in database"}

        logger.info("Updating daily kline for %d stocks (concurrent, multi-source)...",
                     len(codes))
        t0 = time.time()
        success = 0
        failed = 0
        sources_used = {"mootdx": 0, "tencent": 0, "akshare": 0}
        max_workers = 10

        def _fetch_and_store(c: str) -> Tuple[bool, Optional[str]]:
            src, df = _fetch_kline_with_fallback(c, count=400, from_date=from_date)
            if df is None or df.empty:
                return False, None

            with get_db() as db:
                cols = df.columns
                for _, row in df.iterrows():
                    try:
                        trade_date = str(row.get("trade_date", ""))[:10]
                        if not trade_date or trade_date == "null":
                            continue
                        db.execute(
                            "INSERT OR REPLACE INTO daily_kline"
                            "(code,trade_date,open,high,low,close,volume,amount,"
                            "turnover_rate,change_pct,amplitude)"
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                c, trade_date,
                                _float(row, "open"), _float(row, "high"),
                                _float(row, "low"), _float(row, "close"),
                                _float(row, "volume"), _float(row, "amount"),
                                _float(row, "turnover_rate") if "turnover_rate" in cols else None,
                                _float(row, "change_pct") if "change_pct" in cols else None,
                                _float(row, "amplitude") if "amplitude" in cols else None,
                            ),
                        )
                    except Exception:
                        pass
            return True, src

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_and_store, c): c for c in codes}
            for i, fut in enumerate(as_completed(futures)):
                try:
                    ok, src = fut.result()
                    if ok:
                        success += 1
                        if src:
                            sources_used[src] = sources_used.get(src, 0) + 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

                if (i + 1) % 200 == 0:
                    elapsed = time.time() - t0
                    rate = (i + 1) / elapsed if elapsed > 0 else 0
                    eta = (len(codes) - i - 1) / rate / 60 if rate > 0 else 0
                    logger.info("  K-line progress: %d/%d ok=%d fail=%d | %.0f/min | ETA %.0fmin",
                                i + 1, len(codes), success, failed, rate * 60, eta)

        elapsed = time.time() - t0
        logger.info("K-line update done: %d ok, %d failed (%.1fs) | sources: %s",
                     success, failed, elapsed,
                     {k: v for k, v in sources_used.items() if v > 0})
        return {
            "status": "ok",
            "success": success,
            "failed": failed,
            "sources": {k: v for k, v in sources_used.items() if v > 0},
            "elapsed": round(elapsed, 1),
        }

    @staticmethod
    def get_kline_df(code: str, lookback: int = 400) -> pd.DataFrame:
        """Load daily kline for a single stock as DataFrame.

        Returns adjusted close when adj_factor data is available (close * adj_factor),
        plus open/high/low adjusted by the same factor for consistency.
        """
        with get_db(readonly=True) as db:
            rows = db.execute(
                "SELECT k.*, a.adj_factor FROM daily_kline k "
                "LEFT JOIN adj_factor a ON k.code = a.code AND k.trade_date = a.trade_date "
                "WHERE k.code=? "
                "ORDER BY k.trade_date DESC LIMIT ?",
                (code, lookback),
            ).fetchall()
        if not rows:
            raise ValueError(f"No kline data for {code}")
        df = pd.DataFrame([dict(r) for r in reversed(rows)])
        df["timestamps"] = pd.to_datetime(df["trade_date"])
        # Apply forward-adjusted (前复权) prices.
        # Fill missing adj_factor: forward-fill then backward-fill, normalize to latest VALID factor.
        if "adj_factor" in df.columns and df["adj_factor"].notna().any():
            adj = df["adj_factor"].copy()
            # Forward-fill missing values (new dates may not have adj_factor yet)
            adj = adj.ffill()
            # Backward-fill any leading NaNs
            adj = adj.bfill()
            # Normalize: latest VALID factor → 1.0, so latest close = raw close
            latest_valid = adj.dropna().iloc[-1] if adj.notna().any() else 1.0
            if latest_valid > 0:
                factor = adj / latest_valid
            else:
                factor = adj.fillna(1.0)
            df["close"] = df["close"] * factor
            df["open"] = df["open"] * factor
            df["high"] = df["high"] * factor
            df["low"] = df["low"] * factor
        return df[["timestamps", "open", "high", "low", "close", "volume", "amount"]]

    @staticmethod
    def get_stock_info(code: str) -> dict:
        """Get stock basic info."""
        with get_db(readonly=True) as db:
            row = db.execute(
                "SELECT * FROM stocks WHERE code=?", (code,)
            ).fetchone()
        return dict(row) if row else {}

    @staticmethod
    def is_trading_day(date_str: Optional[str] = None) -> bool:
        """Check if the given date (or today) is an A-share trading day."""
        day = date_str or datetime.now().strftime("%Y-%m-%d")
        with get_db(readonly=True) as db:
            count = db.execute(
                "SELECT COUNT(*) FROM daily_kline WHERE trade_date=?",
                (day,),
            ).fetchone()[0]
        return count > 0


# ── Internal helpers ───────────────────────────────────────────────

def _get_all_codes() -> List[str]:
    with get_db(readonly=True) as db:
        rows = db.execute(
            "SELECT code FROM stocks WHERE is_st=0 ORDER BY code"
        ).fetchall()
    return [r["code"] for r in rows]


def _float(row, col: str) -> float:
    try:
        return float(row.get(col, 0) or 0)
    except (ValueError, TypeError):
        return 0.0


def _float_or_none(row, col: str):
    """Return float value or None if missing/invalid (for nullable DB columns)."""
    try:
        val = row.get(col)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return None
        return float(val)
    except (ValueError, TypeError):
        return None
