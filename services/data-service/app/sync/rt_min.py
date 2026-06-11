"""实时分钟线采集 — rt_min API, 每 1 分钟调用."""

import logging, sqlite3, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from app.config import TUSHARE_TOKEN, DB_PATH, THREAD_POOL_SIZE, TUSHARE_BATCH_SIZE

logger = logging.getLogger("data-service.rt_min")


def _ts_code(code: str) -> str:
    if code.startswith("6"): return f"{code}.SH"
    if code.startswith(("0", "3")): return f"{code}.SZ"
    if code.startswith(("8", "9", "4")): return f"{code}.BJ"
    return f"{code}.SZ"


def _get_codes(db: sqlite3.Connection) -> list[str]:
    """从 stocks 表获取所有非 ST 代码."""
    return [r[0] for r in db.execute(
        "SELECT code FROM stocks WHERE is_st=0 AND name NOT LIKE '%ST%' "
        "AND code NOT LIKE '92%' AND code NOT LIKE '83%' "
        "AND code NOT LIKE '87%' AND code NOT LIKE '4%'"
    ).fetchall()]


def _fetch_batch(batch: list[str]) -> list[tuple]:
    """拉取一批股票的 rt_min 数据."""
    import tushare as ts
    pro = ts.pro_api(TUSHARE_TOKEN)
    ts_codes = ",".join(_ts_code(c) for c in batch)
    rows = []
    try:
        df = pro.rt_min(ts_code=ts_codes, freq="5MIN")
        if df is not None and len(df) > 0:
            for _, r in df.iterrows():
                tt = str(r.get("time", ""))
                if not tt or tt == "None":
                    continue
                rows.append((
                    str(r.get("ts_code", "")), tt,
                    r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                    r.get("vol"), r.get("amount"), "5min",
                ))
    except Exception as e:
        logger.debug("rt_min batch error: %s", e)
    return rows


def collect_rt_min(progress_callback=None) -> dict:
    """采集全市场实时分钟线 (ThreadPool 并行)."""
    t0 = time.time()
    db = sqlite3.connect(DB_PATH)
    codes = _get_codes(db)
    db.close()

    if not codes:
        return {"status": "error", "message": "no stock codes"}

    batches = [codes[i:i + TUSHARE_BATCH_SIZE] for i in range(0, len(codes), TUSHARE_BATCH_SIZE)]
    total_written = 0

    all_pg_rows = []  # 收集用于 PG 双写

    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as pool:
        futures = {pool.submit(_fetch_batch, b): i for i, b in enumerate(batches)}

        db = sqlite3.connect(DB_PATH)
        for f in as_completed(futures):
            rows = f.result()
            if rows:
                db.executemany(
                    "INSERT OR REPLACE INTO stk_mins(ts_code,trade_time,open,high,low,close,volume,amount,freq) "
                    "VALUES(?,?,?,?,?,?,?,?,?)", rows)
                total_written += len(rows)
                all_pg_rows.extend(rows)
            if progress_callback:
                progress_callback(len(futures))
        db.commit()

        # 🔥 Phase 3: PG 双写
        pg_written = 0
        try:
            from app.sync.pg_writer import write_stk_mins
            pg_written = write_stk_mins(all_pg_rows)
        except Exception as e:
            logger.debug("PG dual-write skipped: %s", e)

        db.close()

    elapsed = time.time() - t0
    logger.info("rt_min: %s stocks, %s rows (PG: %s), %.1fs", len(codes), total_written, pg_written, elapsed)
    return {"status": "ok", "stocks": len(codes), "written": total_written, "pg_written": pg_written, "elapsed": elapsed}


def collect_auction_snapshot() -> dict:
    """9:25 竞价完成后采集快照 (使用 5MIN 频率获取首根 K 线)."""
    return collect_rt_min()
