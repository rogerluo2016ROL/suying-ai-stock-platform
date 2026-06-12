"""PG 直写 — best-effort, ON CONFLICT DO NOTHING + executemany 批量写入."""

import logging, os, time

logger = logging.getLogger("data-service.pg_writer")

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

_MAX_RETRIES = 3  # ADR-006 决策 6: 3 次指数退避 (1s, 4s, 16s)


def _pg_write(table: str, columns: list[str], conflict_cols: list[str],
              rows: list[tuple]) -> int:
    """通用 PG 批量写入 — ON CONFLICT DO NOTHING + executemany.

    ADR-006 决策 6: psycopg2.OperationalError 自动重试 3 次指数退避 (1s, 4s, 16s).
    """
    if not rows:
        return 0
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            import psycopg2
            conn = psycopg2.connect(PG_URL)
            conn.autocommit = True
            cur = conn.cursor()
            col_str = ",".join(columns)
            placeholders = ",".join(["%s"] * len(columns))
            conflict_str = ",".join(conflict_cols)
            sql = (f"INSERT INTO {table}({col_str}) VALUES({placeholders}) "
                   f"ON CONFLICT({conflict_str}) DO NOTHING")
            cur.executemany(sql, rows)
            written = cur.rowcount
            conn.close()
            _check_data_volume(table, written)
            return written
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                sleep_s = 4 ** attempt  # 1, 4, 16
                logger.debug("PG write %s retry %d/%d after %.0fs: %s", table, attempt + 1, _MAX_RETRIES, sleep_s, e)
                time.sleep(sleep_s)
        except Exception as e:
            logger.debug("PG write %s: %s", table, e)
            return 0
    logger.warning("PG write %s failed after %d retries: %s", table, _MAX_RETRIES, last_error)
    return 0


def _check_data_volume(table: str, written: int):
    """数据量门禁: <1000 ERROR, <3000 WARN (仅日线/分钟线)."""
    if written == 0:
        return
    if written < 1000 and table in ("daily_kline", "stk_mins"):
        logger.error("PG %s: 写入量异常低 (%d 行 < 1000) — 可能 Tushare API 异常或权限过期",
                     table, written)
    elif written < 3000 and table in ("daily_kline", "stk_mins"):
        logger.warning("PG %s: 写入量偏低 (%d 行 < 3000)", table, written)


# ── 各表写入函数 ──

def write_stk_mins(rows: list[tuple]) -> int:
    """写入 stk_mins (ts_code→code 映射, ON CONFLICT 去重)."""
    if not rows:
        return 0
    mapped = []
    for r in rows:
        ts_code, trade_time, o, h, l, c, vol, amt, freq = r
        code = ts_code.split(".")[0][:6]
        mapped.append((code, trade_time, o, h, l, c, vol, amt, freq))
    return _pg_write("stk_mins",
                     ["code", "trade_time", "open", "high", "low", "close", "volume", "amount", "freq"],
                     ["code", "trade_time", "freq"], mapped)


def write_daily_kline(rows: list[tuple]) -> int:
    """写入 daily_kline — (code, trade_date, open, high, low, close, volume, amount)."""
    return _pg_write("daily_kline",
                     ["code", "trade_date", "open", "high", "low", "close", "volume", "amount"],
                     ["code", "trade_date"], rows)


def write_moneyflow(rows: list[tuple]) -> int:
    """写入 moneyflow (跳过 PG schema 中没有的 net_mf_vol, 即 rows 末尾第12列)."""
    if not rows:
        return 0
    mapped = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10])
              for r in rows]  # 去掉 net_mf_vol (r[11])
    return _pg_write("moneyflow",
                     ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
                      "buy_md_amount", "sell_md_amount", "buy_lg_amount",
                      "sell_lg_amount", "buy_elg_amount", "sell_elg_amount", "net_mf_amount"],
                     ["code", "trade_date"], mapped)


def write_stk_limit(rows: list[tuple]) -> int:
    """写入 stk_limit — (code, trade_date, up_limit, down_limit, pre_close)."""
    return _pg_write("stk_limit",
                     ["code", "trade_date", "up_limit", "down_limit", "pre_close"],
                     ["code", "trade_date"], rows)


def write_daily_basic(rows: list[tuple]) -> int:
    """写入 daily_basic (跳过 pe_ttm, 重排: code, trade_date, pe, pb, total_mv, circ_mv, turnover_rate, volume_ratio)."""
    if not rows:
        return 0
    mapped = [(r[0], r[1], r[4], r[6], r[7], r[8], r[2], r[3])
              for r in rows]
    return _pg_write("daily_basic",
                     ["code", "trade_date", "pe", "pb", "total_mv", "circ_mv", "turnover_rate", "volume_ratio"],
                     ["code", "trade_date"], mapped)


def write_index_daily(rows: list[tuple]) -> int:
    """写入 index_daily (ts_code→code, vol→volume, pct_chg→change_pct)."""
    if not rows:
        return 0
    mapped = []
    for r in rows:
        ts_code = str(r[0])
        code = ts_code.split(".")[0] if "." in ts_code else ts_code
        mapped.append((code, r[1], r[3], r[4], r[5], r[2], r[9], r[10], r[8]))
    return _pg_write("index_daily",
                     ["code", "trade_date", "open", "high", "low", "close", "volume", "amount", "change_pct"],
                     ["code", "trade_date"], mapped)


def write_limit_list_d(rows: list[tuple]) -> int:
    """写入 limit_list_d (ts_code→code, trade_date_str→trade_date)."""
    if not rows:
        return 0
    mapped = []
    for r in rows:
        trade_date_str = str(r[0])
        trade_date = (f"{trade_date_str[:4]}-{trade_date_str[4:6]}-{trade_date_str[6:8]}"
                      if len(trade_date_str) == 8 else trade_date_str)
        ts_code = str(r[1])
        code = ts_code.split(".")[0] if "." in ts_code else ts_code
        mapped.append((code, trade_date, ts_code, str(r[2]),
                       r[3], r[4], r[5], r[6], r[7],
                       r[8] or 0, str(r[9] or ""), str(r[10] or ""),
                       r[11] or 0, str(r[12] or ""), r[13] or 0))
    return _pg_write("limit_list_d",
                     ["code", "trade_date", "ts_code", "name", "close", "pct_chg", "amount",
                      "float_mv", "turnover_ratio", "fd_amount", "first_time", "last_time",
                      "open_times", "up_stat", "limit_times"],
                     ["code", "trade_date"], mapped)


# ── 物化视图刷新 ──

def refresh_materialized_views() -> dict:
    """刷新 PG 物化视图，返回每 view 结果."""
    views = ["mv_today_strong_stocks", "mv_sector_momentum", "mv_top_capital_inflow",
             "mv_daily_composite_ranking"]
    results = {}
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL)
        cur = conn.cursor()
        for view in views:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                cur.execute(f"SELECT COUNT(*) FROM {view}")
                row_count = cur.fetchone()[0]
                results[view] = {"status": "ok", "rows": row_count}
            except Exception as e:
                err_msg = str(e)
                conn.rollback()
                cur = conn.cursor()
                if "does not exist" in err_msg:
                    results[view] = {"status": "skipped", "reason": err_msg[:80]}
                else:
                    results[view] = {"status": "error", "error": err_msg[:80]}
                logger.debug("PG refresh %s: %s", view, err_msg[:80])
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("PG refresh all views failed: %s", e)
        return {v: {"status": "error", "error": str(e)[:80]} for v in views}

    return results
