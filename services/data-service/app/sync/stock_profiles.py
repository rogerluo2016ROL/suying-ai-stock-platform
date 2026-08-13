"""上市公司基本信息同步 — Tushare stock_company API.

积分要求: 120pts (极低门槛, 基础数据).
按交易所分批拉取全市场公司基本信息, 写入 PG (主) + SQLite (fallback).
"""

import logging, math, sqlite3, time

logger = logging.getLogger("data-service.stock_profiles")


def _num_or_none(v):
    """NaN → None。Tushare 缺字段返回 NaN(float)，psycopg2 直传给 int4 列
    (employees) 会触发 PG 'integer out of range'，整批 execute_values 归零。"""
    return None if isinstance(v, float) and math.isnan(v) else v


def sync_stock_profiles(days_back: int = 0) -> dict:
    """同步上市公司基本信息 — 按交易所 (SSE/SZSE/BSE) 全量拉取.

    API: pro.stock_company(exchange=SSE|SZSE|BSE) → ts_code, com_name, chairman,
         manager, secretary, reg_capital, setup_date, province, city, website,
         email, office, employees, main_business, business_scope, introduction

    每交易所一次调用返回该交易所全部上市公司 (~2000-2500 条/次).
    days_back 参数保留以兼容 scheduler 接口, 实际不使用.

    Returns:
        {"table": "stock_profiles", "written": N, "pg_written": N, "elapsed": S}
    """
    from app.config import TUSHARE_TOKEN, DB_PATH, SQLITE_FALLBACK_ENABLED
    from app.sync.rate_limiter import rate_limit

    if not TUSHARE_TOKEN:
        return {"status": "skipped", "reason": "no Tushare token"}

    import tushare as ts
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()

    t0 = time.time()
    all_rows = []
    pg_written = 0

    for exchange in ("SSE", "SZSE", "BSE"):
        rate_limit()
        try:
            df = pro.stock_company(exchange=exchange)
        except Exception as e:
            logger.debug("stock_company exchange=%s failed: %s", exchange, e)
            continue

        if df is None or len(df) == 0:
            logger.debug("stock_company exchange=%s: no data", exchange)
            continue

        for _, r in df.iterrows():
            ts_code = str(r.get("ts_code", ""))
            code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code

            all_rows.append((
                code,
                str(r.get("com_name", "")),
                str(r.get("province", "")),
                str(r.get("city", "")),
                _num_or_none(r.get("reg_capital")),
                str(r.get("setup_date", "")),
                str(r.get("main_business", "")),
                str(r.get("business_scope", ""))[:500],
                str(r.get("website", "")),
                str(r.get("email", "")),
                str(r.get("chairman", "")),
                str(r.get("manager", "")),
                str(r.get("secretary", "")),
                _num_or_none(r.get("employees")),
                str(r.get("introduction", ""))[:2000] if r.get("introduction") else "",
            ))

    if not all_rows:
        return {"table": "stock_profiles", "written": 0, "note": "no data from any exchange"}

    pg_cols = ["code", "full_name", "province", "city", "reg_capital", "setup_date",
               "main_business", "business_scope", "website", "email", "chairman",
               "manager", "secretary", "employees", "introduction"]

    # ── PG 直写 (主路径, ADR-015.4: _pg_write UPSERT 替代 inline-execute_values) ──
    # 业务语义: ON CONFLICT(code) DO UPDATE SET 14 业务列 (不刷 updated_at, 100% 还原现状)
    # 若业务需刷 updated_at, 另开 follow-up (本 ADR 不扩 scope, 参考 ADR-013 S-1 教训)
    try:
        from app.sync.pg_writer import _pg_write
        pg_written = _pg_write(
            "stock_profiles",
            columns=pg_cols,
            conflict_cols=["code"],
            rows=all_rows,
            conflict_action="update",
            update_cols=[c for c in pg_cols if c != "code"],
        )
    except Exception as e:
        logger.warning("PG write stock_profiles failed: %s", e)

    # ── SQLite 写入 (fallback) ──
    if SQLITE_FALLBACK_ENABLED:
        try:
            db = sqlite3.connect(DB_PATH)
            # Ensure table has all needed columns
            db.executemany(
                "INSERT OR REPLACE INTO stock_profiles(code, full_name, province, reg_capital, main_business, website) "
                "VALUES(?,?,?,?,?,?)",
                [(r[0], r[1], r[2], r[4], r[6], r[8]) for r in all_rows],
            )
            db.commit()
            db.close()
        except Exception as e:
            logger.warning("SQLite write stock_profiles failed: %s", e)

    elapsed = time.time() - t0
    logger.info("stock_profiles: %d companies, PG=%d, %.1fs", len(all_rows), pg_written, elapsed)
    return {
        "table": "stock_profiles",
        "written": len(all_rows),
        "pg_written": pg_written,
        "elapsed": elapsed,
    }
