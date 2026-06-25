"""股票列表同步 — 从 Tushare stock_basic 同步到 SQLite + PG."""

import logging, sqlite3, time
from datetime import date

from app.config import TUSHARE_TOKEN, DB_PATH, SQLITE_FALLBACK_ENABLED

logger = logging.getLogger("data-service.stocks")

# PG 连接 (复用 pg_writer 的配置)
import os
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def _code_from_ts(ts_code: str) -> str:
    return str(ts_code).split(".")[0][:6]


def sync_stock_list(exchange: str = "") -> dict:
    """从 Tushare stock_basic 同步股票列表到 SQLite + PG.

    全量同步所有 A 股股票基本信息（code, name, industry, market, list_date）。
    SQLite 使用 INSERT OR REPLACE，PG 使用 INSERT ON CONFLICT DO UPDATE 支持增量更新。

    Args:
        exchange: 交易所过滤 (SSE/SZSE/BSE，空字符串=全部)
    Returns:
        dict: {"sqlite_written": N, "pg_written": N, "total": N, "elapsed": S}
    """
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    t0 = time.time()

    # 拉取股票列表
    kwargs = {"list_status": "L"}
    if exchange:
        kwargs["exchange"] = exchange
    df = pro.stock_basic(**kwargs)
    if df is None or len(df) == 0:
        return {"status": "error", "message": "no data from stock_basic"}

    rows = []
    for _, r in df.iterrows():
        code = _code_from_ts(r["ts_code"])
        name = str(r.get("name", ""))
        industry = str(r.get("industry", "") or "")
        market = str(r.get("market", "") or "")  # 主板/创业板/科创板
        list_date = str(r.get("list_date", ""))
        # 格式化上市日期
        if len(list_date) == 8:
            list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
        is_st = 1 if "ST" in name else 0
        rows.append((code, name, market, industry, list_date, is_st))

    # ── PG 写入 (主路径, ADR-015.1: _pg_write UPSERT 替代 inline-cursor) ──
    # 业务语义: ON CONFLICT(code) DO UPDATE SET 5 业务列 + updated_at=NOW()
    # ADR-015.0 now_cols=["updated_at"] 走 NOW() 而非 EXCLUDED (审计列黑名单)
    pg_written = 0
    try:
        from app.sync.pg_writer import _pg_write
        pg_written = _pg_write(
            "stocks",
            columns=["code", "name", "board", "industry", "listed_date", "is_st"],
            conflict_cols=["code"],
            rows=rows,
            conflict_action="update",
            update_cols=["name", "board", "industry", "listed_date", "is_st"],
            now_cols=["updated_at"],
        )
        logger.info("PG stocks: %d rows written (UPSERT)", pg_written)
    except Exception as e:
        logger.debug("PG stocks write skipped: %s", e)

    # ── SQLite 写入 (fallback) ──
    sqlite_written = 0
    if SQLITE_FALLBACK_ENABLED:
        try:
            db = sqlite3.connect(DB_PATH)
            db.executemany(
                "INSERT OR REPLACE INTO stocks(code,name,board,industry,listed_date,is_st,updated_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))", rows)
            db.commit()
            sqlite_written = len(rows)
            db.close()
            logger.info("SQLite stocks: %d rows written", sqlite_written)
        except Exception as e:
            logger.warning("SQLite stocks write failed: %s", e)

    elapsed = time.time() - t0
    logger.info("sync_stock_list: SQLite=%d PG=%d total=%d %.1fs",
                sqlite_written, pg_written, len(rows), elapsed)
    return {"sqlite_written": sqlite_written, "pg_written": pg_written,
            "total": len(rows), "elapsed": elapsed}


def sync_stocks_incremental(trade_date: str = "") -> dict:
    """增量同步今日新上市股票 — ADR-006 决策 4: 每日盘前检测.

    仅拉取 list_date=today 的股票 (1 次 API 调用)，写入 SQLite + PG。
    stock_basic 不计入 Tushare 限频配额，可跳过 rate_limit()。
    """
    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    t0 = time.time()

    if not trade_date:
        trade_date = date.today().strftime("%Y%m%d")

    df = pro.stock_basic(list_status="L", list_date=trade_date)
    if df is None or len(df) == 0:
        return {"status": "ok", "new_stocks": 0, "message": "no new stocks today"}

    rows = []
    for _, r in df.iterrows():
        code = _code_from_ts(r["ts_code"])
        name = str(r.get("name", ""))
        market = str(r.get("market", "") or "")
        industry = str(r.get("industry", "") or "")
        list_date = str(r.get("list_date", ""))
        if len(list_date) == 8:
            list_date = f"{list_date[:4]}-{list_date[4:6]}-{list_date[6:8]}"
        is_st = 1 if "ST" in name else 0
        rows.append((code, name, market, industry, list_date, is_st))

    # PG 直写 (主路径, ADR-015.1: _pg_write UPSERT)
    pg_written = 0
    try:
        from app.sync.pg_writer import _pg_write
        pg_written = _pg_write(
            "stocks",
            columns=["code", "name", "board", "industry", "listed_date", "is_st"],
            conflict_cols=["code"],
            rows=rows,
            conflict_action="update",
            update_cols=["name", "board", "industry", "listed_date", "is_st"],
            now_cols=["updated_at"],
        )
    except Exception as e:
        logger.debug("PG stocks incremental skipped: %s", e)

    # SQLite 写入 (fallback)
    sqlite_written = 0
    if SQLITE_FALLBACK_ENABLED:
        try:
            db = sqlite3.connect(DB_PATH)
            db.executemany(
                "INSERT OR REPLACE INTO stocks(code,name,board,industry,listed_date,is_st,updated_at) "
                "VALUES(?,?,?,?,?,?,datetime('now','localtime'))", rows)
            db.commit()
            sqlite_written = len(rows)
            db.close()
        except Exception as e:
            logger.warning("SQLite stocks incremental failed: %s", e)

    elapsed = time.time() - t0
    logger.info("sync_stocks_incremental: date=%s SQLite=%d PG=%d %.1fs",
                trade_date, sqlite_written, pg_written, elapsed)
    return {"status": "ok", "trade_date": trade_date, "new_stocks": len(rows),
            "sqlite_written": sqlite_written, "pg_written": pg_written, "elapsed": elapsed}
