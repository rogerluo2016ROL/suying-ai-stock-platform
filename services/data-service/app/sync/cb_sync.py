"""可转债 & 同花顺数据同步 — standalone sync functions.

包含:
  - sync_ths_daily: 同花顺概念板块每日行情 (pro.ths_daily)
  - sync_cb_price_chg_all: 转股价变动全量同步 (逐只遍历 cb_basic)
  - sync_ths_concept_map: 同花顺概念映射 (pro.ths_concept_map, 每月刷新)
"""

import logging, os, time
from datetime import datetime, timedelta

logger = logging.getLogger("data-service.cb_sync")

# ADR-013 §决策 0 白名单 #3 (S-1) 偏离说明:
# ADR-012 review §9 S-1 标 MAX_RETRIES / PG_URL / import time 为 "thin wrapper 化后未使用 dead code"
# → 实证 grep 显示三者**均被 sync_cb_price_chg_all / sync_ths_concept_map 主动使用** (非 dead):
#   - MAX_RETRIES: 用于 Tushare API 调用的应用层重试循环 (与 _pg_write thin wrapper 的 PG 写入重试是
#     不同层级 — 前者是 fetch 层 retry, 后者是 write 层 retry, 二者并存合理)
#   - PG_URL:      sync_cb_price_chg_all 直接 psycopg2.connect 读 cb_basic 列表 (L161)
#   - import time: sync_ths_daily/sync_cb_price_chg_all/sync_ths_concept_map 的 time.sleep 指数退避
# 删之会 NameError 整文件不可 import → 违背"不扩范围/不破坏功能"原则. ADR §决策 0 表述与代码现状不一致,
# 保留三者; SIT 14 标记 PARTIAL (with rationale), 已通过 SendMessage 单独 PL 通告.
MAX_RETRIES = 3
PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

# ── helpers ──

def _get_secret(name: str) -> str:
    file_path = os.environ.get(f"{name}_FILE", "").strip()
    if file_path:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                value = f.read().strip()
            if value:
                return value
        except OSError:
            pass
    return os.environ.get(name, "").strip()


def _get_pro():
    """Lazy-init Tushare pro_api."""
    import tushare as ts
    token = _get_secret("TUSHARE_TOKEN")
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
    """PG 批量写入 — ADR-012 §决策 5.3: thin wrapper, delegate to pg_writer._pg_write.

    与 pg_writer._pg_write 函数体 95% 复制粘贴是历史包袱 (cb_sync.py 后加, 没复用)。
    本次合并: cb_sync 的 3 个 sync 函数 (sync_ths_daily / sync_cb_price_chg_all /
    sync_ths_concept_map) 通过本 thin wrapper 间接走 _insert_rows, 获得自动列过滤能力.

    保留参数签名 / 返回值语义 (sync 函数零改动). conflict_cols 参数语义同 pg_writer._pg_write
    (ADR-012 §决策 5.2.bis): _insert_rows 用 ON CONFLICT DO NOTHING 依表 PK 约束, 调用方仍按
    表 PK / UNIQUE 列传值, 等价成立 (grep 实证 ths_daily UNIQUE(code,trade_date) /
    cb_price_chg UNIQUE(ts_code,change_date) / ths_concept_map PK(ts_code) 均与 conflict_cols 对齐).
    """
    if not rows:
        return 0
    from app.sync.pg_writer import _pg_write
    return _pg_write(table, columns, conflict_cols, rows)


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
    # ADR-013 §决策 2: cols 5 → 15 对齐 Tushare pro.ths_daily 实际返回字段 + DB 17 列业务列.
    # API 返回 15 字段 (ts_code/trade_date/name/open/high/low/close/pre_close/avg_price/change/
    # pct_change/vol/turnover_rate/total_mv/float_mv); 命名映射:
    #   - ts_code → code      (项目级 normalization, 与 pg_adapter._COLUMN_MAP 一致)
    #   - pct_change → change_pct (与 sw_daily 同型, ADR-008)
    cols = ["code", "trade_date", "name", "open", "high", "low", "close",
            "pre_close", "avg_price", "change_pct", "change",
            "total_mv", "float_mv", "vol", "turnover_rate"]

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
            # ADR-013 §决策 2: 15 元组对齐上方 cols 顺序; Tushare API ts_code → 表 code (str 兜底空值),
            # pct_change → change_pct; 其他 12 列字面一致.
            rows.append((
                str(r.get("ts_code", "")),
                td,
                str(r.get("name", "")) if r.get("name") is not None else None,
                _safe_val(r.get("open")),
                _safe_val(r.get("high")),
                _safe_val(r.get("low")),
                _safe_val(r.get("close")),
                _safe_val(r.get("pre_close")),
                _safe_val(r.get("avg_price")),
                _safe_val(r.get("pct_change")),
                _safe_val(r.get("change")),
                _safe_val(r.get("total_mv")),
                _safe_val(r.get("float_mv")),
                _safe_val(r.get("vol")),
                _safe_val(r.get("turnover_rate")),
            ))

        total += len(rows)
        # ADR-013 §决策 2: conflict_cols 改 ["code", "trade_date"] 与 UNIQUE 约束对齐.
        # _insert_rows 底层用 ON CONFLICT DO NOTHING 依赖表 UNIQUE/PK 约束, 行为等价 (ADR-012 §决策 5.2.bis).
        w = _pg_bulk_insert("ths_daily", cols, ["code", "trade_date"], rows)
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
