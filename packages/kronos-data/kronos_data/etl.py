#!/usr/bin/env python3
"""Tushare premium data sync — batch-fetch and persist to SQLite.

Usage:
    python tools/tushare_sync.py                     # Sync all tables, last 30 days
    python tools/tushare_sync.py --days 5            # Last 5 days only
    python tools/tushare_sync.py --mode moneyflow    # Specific table only
    python tools/tushare_sync.py --mode all --days 60
"""

import argparse
import logging
import os
import sys
import sqlite3
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger("kronos-data.etl")

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # packages/kronos-data
_PROJ = os.path.dirname(os.path.dirname(_PKG_ROOT))  # project root (2 levels up)
sys.path.insert(0, os.path.join(_PKG_ROOT, "src"))
sys.path.insert(0, _PKG_ROOT)

# PG connection (preferred) or SQLite fallback
_PG_URL = os.environ.get("KRONOS_PG_URL", "")
_USE_PG = bool(_PG_URL)
# 线程本地连接: 同步函数经 asyncio.to_thread 并发执行后, 全局单例连接会被
# 其他线程的 db.close() 误关 (InterfaceError: connection already closed)。
# 每线程一条连接, 同线程内保持原有的"关闭后按需重连"语义。
_pg_local = threading.local()

DB_PATH = os.path.join(_PROJ, "Kronos", "webui", "stock_screening.db")
if not os.path.exists(DB_PATH):
    DB_PATH = os.path.join(_PROJ, "webui", "stock_screening.db")

# Rate limiting — 500 req/min max, ~120ms per call
_CALL_TIMES = []
_call_times_lock = threading.Lock()
_RATE_LIMIT = int(os.environ.get("TUSHARE_RATE_PER_MIN", "450"))  # safe margin below 500


def _rate_limit():
    """Enforce sliding-window rate limit (默认 450/min, TUSHARE_RATE_PER_MIN 可调).

    线程安全: 财报并行拉取 (ThreadPoolExecutor) 下多线程共用滑动窗口。
    """
    global _CALL_TIMES
    with _call_times_lock:
        now = time.time()
        _CALL_TIMES = [t for t in _CALL_TIMES if now - t < 60]
        if len(_CALL_TIMES) >= _RATE_LIMIT:
            sleep_for = 60 - (now - _CALL_TIMES[0]) + 0.1
            if sleep_for > 0:
                time.sleep(sleep_for)
                _CALL_TIMES = []
        _CALL_TIMES.append(time.time())


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
    """Lazy-init Tushare pro_api. Returns None if Tushare credentials are missing."""
    token = _get_secret("TUSHARE_TOKEN")
    if not token:
        print("  TUSHARE_TOKEN_FILE/TUSHARE_TOKEN not set — skipping")
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


def _date_from_tushare(value) -> str:
    """Normalize Tushare YYYYMMDD dates to PG-friendly YYYY-MM-DD."""
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


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
        # P2-1 (audit): row_factory is honored ONLY on the SQLite path (below).
        # The PG path uses psycopg2.extras.DictCursor in execute() instead —
        # setting row_factory on a psycopg2 connection is a no-op (the attribute
        # is ignored), so historical `db.row_factory = sqlite3.Row` lines in
        # callers were misleading dead code on PG. Centralising it here makes
        # the SQLite-vs-PG behaviour explicit; callers no longer need to set it.
        if not is_pg:
            conn.row_factory = sqlite3.Row
    def execute(self, sql: str, params: tuple = None):
        if self._pg:
            sql = sql.replace("?", "%s")
            # 用 DictCursor —— fetchall 返回的行支持 r["col"] (与 SQLite sqlite3.Row 行为一致)。
            # 否则 PG 返回 tuple, sync 函数里的 r["code"] 报 "tuple indices must be integers"。
            from psycopg2.extras import DictCursor
            cur = self._conn.cursor(cursor_factory=DictCursor)
            # params=None 时不传 args —— cur.execute(sql, params or ()) 会把空 tuple ()
            # 传给无 %s 占位符的 SQL, psycopg2 报 "tuple index out of range" (影响所有无参 db.execute)
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            return cur
        return self._conn.execute(sql, params or ())
    def commit(self):
        self._conn.commit()
    def close(self):
        self._conn.close()
    def rollback(self):
        try: self._conn.rollback()
        except Exception as e: logger.warning("rollback failed: %s", e)


# 模块级缓存: table -> 实际列名 (供 _insert_rows 自动过滤无效列, 止血 etl cols 与 PG schema 脱节)
_pg_table_cols_cache: dict = {}

def _get_pg_columns(conn, table: str) -> frozenset:
    """缓存查询 PG 表的实际列名."""
    if table not in _pg_table_cols_cache:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name=%s", (table,))
        _pg_table_cols_cache[table] = frozenset(r[0] for r in cur.fetchall())
    return _pg_table_cols_cache[table]


def _get_etl_db() -> _Db:
    """Return _Db wrapper. PG if KRONOS_PG_URL is set, else SQLite."""
    if _USE_PG:
        try:
            import psycopg2
            conn = getattr(_pg_local, "conn", None)
            if conn is None or conn.closed:
                conn = psycopg2.connect(_PG_URL)
                _pg_local.conn = conn
            return _Db(conn, True)
        except Exception as e:
            print(f"  PG connection failed ({e}), falling back to SQLite")
    return _Db(sqlite3.connect(DB_PATH), False)


def _ensure_pg_conn(db: _Db) -> None:
    """长时间 sync (如 per-stock 财务循环 >20min) 中 PG 服务端可能断开空闲连接,
    之后 db._conn.cursor() 直接抛 InterfaceError: connection already closed 使整个 sync 崩溃。
    写入前检测 closed 并重连 (复用 thread-local 语义), 连接正常时零开销。"""
    if db._pg and db._conn.closed:
        import psycopg2
        db._conn = psycopg2.connect(_PG_URL)
        _pg_local.conn = db._conn


def clean_before_write(db: _Db, table: str, days_back: int, date_col: str = "trade_date"):
    """Delete old rows within the sync window to avoid duplicates."""
    cutoff = (datetime.now() - timedelta(days=days_back + 1)).strftime("%Y-%m-%d")
    db.execute(f"DELETE FROM {table} WHERE {date_col} >= ?", (cutoff,))


# ADR-015.0 §决策 2 约束 3: update_cols 黑名单 (审计列)
# created_at: 不应被 UPSERT 刷新 (审计语义 "首次创建时间")
# updated_at: 应由 trigger / 显式 NOW() 维护, 不走 EXCLUDED
_UPDATE_COLS_BLACKLIST = frozenset({"created_at", "updated_at"})


def _insert_rows(db: _Db, table: str, columns: list[str],
                 rows: list[tuple],
                 retries: int = 0,
                 data_volume_floor: int | None = None,
                 data_volume_warn: int | None = None,
                 conflict_action: str = "nothing",
                 conflict_cols: list[str] | None = None,
                 update_cols: list[str] | None = None,
                 now_cols: list[str] | None = None) -> int:
    """INSERT with per-row error isolation. Uses PG or SQLite bulk insert.

    Args:
        retries: PG ``psycopg2.OperationalError`` 重试次数 (默认 0 = 不重试, 保持旧行为).
                 ADR-012 §决策 5.1: 路径 #2/#3 改造时传 3 (沿用 pg_writer 现有 1s/4s/16s 指数退避).
                 仅 catch OperationalError —— 列错位等 SQL 语义错误仍走 WARN + return 0 路径,
                 retry 不掩盖代码 bug.
        data_volume_floor: 写入行数 < floor 时 print ERROR 提示 (best-effort, 不 raise).
                           ADR-012 §决策 5.1: 关键表 (daily_kline / stk_mins) 用 1000 floor;
                           默认 None = 关闭门禁, 保持旧行为. SQLite 路径不触发 (本地文件无 IO 抖动).
        data_volume_warn: 写入行数 < warn 时 print WARN 提示 (best-effort, 不 raise).
                          ADR-013 §决策 4 (W-2 二档恢复): 关键表 daily_kline / stk_mins 用 warn=3000
                          配合 floor=1000 形成两档分级 (< floor → ERROR, floor ≤ x < warn → WARN);
                          默认 None = 关闭, 保持旧行为. 与 floor 互不依赖, 可独立启用.
        conflict_action: ADR-015.0 §决策 1 — ``"nothing"`` (默认, ON CONFLICT DO NOTHING, 100%
                         向后兼容; 现有 31 个调用点全部沿用) | ``"update"`` (ON CONFLICT DO UPDATE
                         SET, 解锁 stocks / namechange UPSERT 语义). SQLite 路径忽略此参数
                         (SQLite 走 INSERT OR REPLACE, 本身就 UPSERT).
        conflict_cols: ``conflict_action="update"`` 时必传, 指定 ON CONFLICT (cols) 约束列;
                       必须 ⊆ 表 PK / UNIQUE 约束 (DB 层强制). 默认 None.
        update_cols: ``conflict_action="update"`` 时必传, 指定 DO UPDATE SET 列;
                     必须 ⊆ ``columns`` 且 ∩ ``conflict_cols`` = ∅ (PK 列 SET 是反模式);
                     不允许包含 ``created_at`` / ``updated_at`` (审计列黑名单 _UPDATE_COLS_BLACKLIST).
                     默认 None.
        now_cols: ADR-015.0 minor amend (2026-06-22) — DO UPDATE SET 时走 ``NOW()`` 而非
                  ``EXCLUDED.x`` 的列 (如 ``updated_at``). 专为审计列刷新设计: §决策 2 约束 3
                  黑名单禁止 updated_at 走 EXCLUDED, 但 stocks / namechange 业务需要每次
                  UPSERT 刷新 "最后同步时间" (MONITORED_TABLES detect_data_gaps 依赖).
                  约束: ∩ ``update_cols`` = ∅ (一列不能既 EXCLUDED 又 NOW); ⊆ ``columns``;
                  仅 ``conflict_action="update"`` 时生效, ``"nothing"`` 时忽略. 默认 None.

    Raises:
        ValueError: ``conflict_action="update"`` 但 ``conflict_cols`` / ``update_cols`` 缺失或违约
                    (update_cols ∩ conflict_cols ≠ ∅, 或 update_cols 含审计列, 或 update_cols ⊄ columns,
                    或 now_cols ∩ update_cols ≠ ∅, 或 now_cols ⊄ columns).
    """
    # ADR-015.0 §决策 1: conflict_action 参数早 fail 校验 (raise ValueError 防误用)
    if conflict_action not in ("nothing", "update"):
        raise ValueError(f"conflict_action must be 'nothing' or 'update', got {conflict_action!r}")
    if conflict_action == "update":
        if not conflict_cols:
            raise ValueError("conflict_action='update' requires non-empty conflict_cols")
        if not update_cols:
            raise ValueError("conflict_action='update' requires non-empty update_cols")
        # update_cols ⊆ columns
        if not set(update_cols).issubset(columns):
            extra = set(update_cols) - set(columns)
            raise ValueError(f"update_cols must be subset of columns; extra: {sorted(extra)}")
        # update_cols ∩ conflict_cols = ∅ (PK 列 SET 反模式)
        overlap = set(update_cols) & set(conflict_cols)
        if overlap:
            raise ValueError(f"update_cols must NOT overlap conflict_cols; overlap: {sorted(overlap)}")
        # update_cols ∩ 审计列黑名单 = ∅
        blacklisted = set(update_cols) & _UPDATE_COLS_BLACKLIST
        if blacklisted:
            raise ValueError(f"update_cols must NOT include audit cols {sorted(blacklisted)}; "
                             f"created_at/updated_at should be trigger-maintained or NOW() (use now_cols for updated_at)")
        # ADR-015.0 minor amend: now_cols 校验
        # now_cols 是独立追加列 (INSERT VALUES + DO UPDATE SET 都用 NOW()), 不要求 ⊆ columns,
        # 但必须与 columns / update_cols / conflict_cols 互斥 (防重复列 / 语义冲突)
        if now_cols:
            # now_cols ∩ columns = ∅ (不能既是业务列又是 NOW 列, 否则 INSERT 重复列)
            nc_cols_overlap = set(now_cols) & set(columns)
            if nc_cols_overlap:
                raise ValueError(f"now_cols must NOT overlap columns (now_cols 是独立追加列); "
                                 f"overlap: {sorted(nc_cols_overlap)}")
            # now_cols ∩ update_cols = ∅ (一列不能既 EXCLUDED 又 NOW)
            nc_overlap = set(now_cols) & set(update_cols)
            if nc_overlap:
                raise ValueError(f"now_cols must NOT overlap update_cols; overlap: {sorted(nc_overlap)}")
            # now_cols ∩ conflict_cols = ∅ (PK 列 NOW() 反模式, 同 update_cols 约束)
            nc_cc_overlap = set(now_cols) & set(conflict_cols)
            if nc_cc_overlap:
                raise ValueError(f"now_cols must NOT overlap conflict_cols; overlap: {sorted(nc_cc_overlap)}")
    import time
    col_str = ", ".join(columns)
    if db._pg:
        import psycopg2
        import psycopg2.extras
        # 长 sync 中连接可能已被服务端断开, 先确保连接可用再查表结构/写数据
        _ensure_pg_conn(db)
        # 止血: 查表实际列, 过滤 cols 中表不存在的列。etl cols 原为 SQLite 设计, 迁 PG 后大量列名脱节
        # (如 hk_holdings 的 hold_vol), 导致 execute_values 整批 "column does not exist" 失败;
        # 旧代码 except:pass 静默吞 → 表面成功实则 0 写入, 数据停滞数周无人察觉。
        actual = _get_pg_columns(db._conn, table)
        if not actual:
            print(f"  [WARN] _insert_rows: 表 {table} 不存在, 跳过写入", flush=True)
            return 0
        valid_cols = [c for c in columns if c in actual]
        dropped = [c for c in columns if c not in actual]
        if dropped:
            print(f"  [WARN] _insert_rows {table}: 丢弃表不存在的列 {dropped}", flush=True)
        if not valid_cols or not rows:
            return 0
        valid_idx = [columns.index(c) for c in valid_cols]
        filtered = [tuple(row[i] for i in valid_idx) for row in rows]
        col_str = ", ".join(valid_cols)
        # ADR-015.0 §决策 1: 按 conflict_action 分支生成 ON CONFLICT 子句
        # - "nothing" (默认): DO NOTHING (沿用 ADR-012 §决策 5.2 行为, 100% 向后兼容)
        # - "update": DO UPDATE SET {cols=EXCLUDED.cols} (解锁 stocks / namechange UPSERT)
        # 自动列过滤前置: update_cols / conflict_cols / now_cols 也需按 actual 过滤, 防 schema drift 时 SQL 报错
        # ADR-015.0 minor amend: now_cols 是独立追加列 (不在 columns 里), INSERT VALUES 用 NOW() 字面
        # (通过 execute_values template), DO UPDATE SET 也用 NOW(). 专为 updated_at 审计列刷新设计.
        valid_now_cols = [c for c in (now_cols or []) if c in actual] if conflict_action == "update" else []
        if conflict_action == "update":
            valid_update_cols = [c for c in (update_cols or []) if c in actual and c in valid_cols]
            valid_conflict_cols = [c for c in (conflict_cols or []) if c in actual]
            if not valid_update_cols or not valid_conflict_cols:
                # 过滤后空集 → 降级 DO NOTHING (best-effort, 与 valid_cols 为空时 return 0 同档)
                print(f"  [WARN] _insert_rows {table}: update/conflict cols 经 schema 过滤后为空 "
                      f"({update_cols=} {conflict_cols=}), 降级 DO NOTHING", flush=True)
                conflict_clause = "ON CONFLICT DO NOTHING"
                valid_now_cols = []  # 降级时 now_cols 也不生效
            else:
                cc_str = ", ".join(valid_conflict_cols)
                set_parts = [f"{c} = EXCLUDED.{c}" for c in valid_update_cols]
                set_parts.extend(f"{c} = NOW()" for c in valid_now_cols)
                set_str = ", ".join(set_parts)
                conflict_clause = f"ON CONFLICT ({cc_str}) DO UPDATE SET {set_str}"
        else:
            conflict_clause = "ON CONFLICT DO NOTHING"
            valid_now_cols = []  # nothing 时 now_cols 忽略
        # now_cols 追加到 INSERT columns + VALUES(NOW()), 用 execute_values template 实现
        if valid_now_cols:
            insert_cols = valid_cols + valid_now_cols
            insert_col_str = ", ".join(insert_cols)
            placeholders = ["%s"] * len(valid_cols) + ["NOW()"] * len(valid_now_cols)
            values_template = "(" + ", ".join(placeholders) + ")"
            sql = f"INSERT INTO {table}({insert_col_str}) VALUES %s {conflict_clause}"
        else:
            sql = f"INSERT INTO {table}({col_str}) VALUES %s {conflict_clause}"
            values_template = None
        # ADR-012 §决策 5.1: retries ≥ 1 时启用 OperationalError 指数退避 (1s/4s/16s).
        # max(1, retries) 保证 retries=0 时仍跑 1 次, 与旧行为 100% 一致.
        attempts = max(1, retries)
        last_err = None
        for attempt in range(attempts):
            _ensure_pg_conn(db)  # 重试前连接也可能已断, 每次 attempt 前兜底
            cur = db._conn.cursor()
            try:
                psycopg2.extras.execute_values(cur, sql, filtered, template=values_template, page_size=1000)
                written = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                db.commit()
                # 数据量门禁 (best-effort, 不 raise)
                # ADR-013 §决策 4 (W-2): floor → ERROR 优先 (严重); warn → WARN 次档 (温和).
                # 二档互斥分支 (ERROR 触发后不再 WARN), written>0 才检测 (0 不触发避免空跑误报).
                if written > 0:
                    if data_volume_floor is not None and written < data_volume_floor:
                        print(f"  [ERROR] _insert_rows {table}: 写入量 {written} 低于 floor {data_volume_floor}, "
                              f"可能 Tushare API 异常 / 权限过期", flush=True)
                    elif data_volume_warn is not None and written < data_volume_warn:
                        print(f"  [WARN] _insert_rows {table}: 写入量 {written} 低于 warn 阈值 {data_volume_warn}, "
                              f"可能上半场断网 / 部分日期缺数据", flush=True)
                return written
            except psycopg2.OperationalError as e:
                # 仅 OperationalError 走重试 (网络瞬时抖动); 其他 SQL 错误走下面 except Exception
                last_err = e
                db.rollback()
                if attempt < attempts - 1:
                    sleep_s = 4 ** attempt  # 1, 4, 16
                    print(f"  [INFO] _insert_rows {table} OperationalError retry {attempt+1}/{attempts} "
                          f"after {sleep_s}s: {str(e)[:120]}", flush=True)
                    time.sleep(sleep_s)
                    continue
                print(f"  [WARN] _insert_rows {table} 重试 {attempts} 次仍失败: {str(e)[:140]}", flush=True)
                return 0
            except Exception as e:
                # 不再静默吞: 真实写入失败 (非冲突) 必须可见, 否则数据停滞无人察觉
                db.rollback()
                print(f"  [WARN] _insert_rows {table} 写入失败: {str(e)[:140]}", flush=True)
                return 0
        # 兜底 (attempts=0 不该走到): 保留 last_err 痕迹
        if last_err is not None:
            print(f"  [WARN] _insert_rows {table} 最终失败: {str(last_err)[:140]}", flush=True)
        return 0
    else:
        placeholders = ",".join(["?"] * len(columns))
        sql = f"INSERT OR REPLACE INTO {table}({col_str}) VALUES({placeholders})"
        written = 0
        for row in rows:
            try: db.execute(sql, row); written += 1
            except Exception as e: logger.warning("SQLite insert failed for %s row: %s", table, e)
        return written


# ═══════════════════════════════════════════════════════════════
# Per-API sync functions
# ═══════════════════════════════════════════════════════════════


def _sync_per_date(table: str, api_call, cols: list[str], row_mapper,
                   days_back: int = 30, *, clean: bool = False, commit: bool = True) -> dict:
    """按交易日全市场拉取的通用同步骨架 — 消除 per-date sync 的重复样板。

    Args:
        table: 表名
        api_call: (pro, trade_date: str) -> DataFrame，调用 Tushare 拉取单日全市场数据
        cols: 写入列
        row_mapper: (row, trade_date: str) -> tuple，把单行 df 记录映射为写入元组
        days_back: 回看交易日数
        clean: 写前是否 clean_before_write（部分表需先清旧数据再重写）
        commit: 写后是否 commit（个别 sync 只 close 不 commit）
    """
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    if clean:
        clean_before_write(db, table, days_back)

    total, written = 0, 0
    for d in dates:
        _rate_limit()
        try:
            df = api_call(pro, d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = [row_mapper(r, d) for _, r in df.iterrows()]
        total += len(rows)
        written += _insert_rows(db, table, cols, rows)

    if commit:
        db.commit()
    db.close()
    print(f"  {table}: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": table, "fetched": total, "written": written}


def sync_moneyflow(days_back: int = 30) -> dict:
    """Sync pro.moneyflow() — per-date full-market returns."""
    cols = ["code", "trade_date", "buy_sm_amount", "sell_sm_amount",
            "buy_md_amount", "sell_md_amount", "buy_lg_amount", "sell_lg_amount",
            "buy_elg_amount", "sell_elg_amount", "net_mf_amount", "net_mf_vol"]

    def mapper(r, d):
        return (_code_from_ts(r["ts_code"]),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                r.get("buy_sm_amount"), r.get("sell_sm_amount"),
                r.get("buy_md_amount"), r.get("sell_md_amount"),
                r.get("buy_lg_amount"), r.get("sell_lg_amount"),
                r.get("buy_elg_amount"), r.get("sell_elg_amount"),
                r.get("net_mf_amount"), r.get("net_mf_vol"))

    return _sync_per_date("moneyflow", lambda pro, d: pro.moneyflow(trade_date=d),
                          cols, mapper, days_back, clean=True)


def sync_hk_hold(days_back: int = 30) -> dict:
    """Sync pro.hk_hold() — 港股通南向持股 (south-bound HK Stock Connect).

    hk_hold 的 exchange 参数区分南北向: 'SH'/'SZ'=北向A股, 'HK'=南向港股。
    本函数不传 exchange, Tushare 默认返回南向港股(.HK 5位码), 入 hk_holdings 表。

    ⚠️ 北向(exchange='SH'/'SZ')自 2024-08-19 交易所停止披露个股持股后返回空,
    2024-07 起已无数据 (实测 2023-12-29 北向仍有 SH 1513/SZ 1758 行)。
    如需北向历史回溯: 加 exchange='SH'+'SZ' 参数 + 限定 trade_date < '20240701'。
    近期北向个股资金流只能用 hsgt_top10 上榜名单(2024-08 后 net_amount 亦为空)。
    """
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
    # ADR-009 §决策4c: cols l_sell→sell_amount, l_buy→buy_amount 对齐表列 (r.get 值不变, Tushare 原字段名)
    cols = ["code", "trade_date", "name", "close", "pct_change",
            "turnover_rate", "amount", "sell_amount", "buy_amount", "net_amount", "reason"]

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
    # PG index_basic 主键列名是 code (非 ts_code); _insert_rows 的 PG 列过滤
    # 不会改名, 传 ts_code 会被当不存在列丢弃 → code NOT NULL 违规, 整批 0 写入.
    cols = ["code", "name", "market", "publisher", "category",
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
    # PG columns: code, trade_date, open, high, low, close, volume, amount, change_pct
    cols = ["code", "trade_date", "open", "high", "low", "close",
            "volume", "amount", "change_pct"]

    start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
    end = datetime.now().strftime("%Y%m%d")

    def _ts_to_code(tc):
        return tc.split(".")[0] if "." in str(tc) else str(tc)

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
                _ts_to_code(r["ts_code"]),
                str(r["trade_date"])[:4] + "-" + str(r["trade_date"])[4:6] + "-" + str(r["trade_date"])[6:8],
                r["open"], r["high"], r["low"], r["close"],
                r.get("vol"), r.get("amount"),
                r.get("pct_chg"),
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


# PG 表列名映射 (module 级, per-stock 与 bulk 两路共用).
_FINANCIAL_COLS_MAP = {
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
    # P4 修复: cols 用 PG 表列名 (非 Tushare 原名), 配合 field_aliases 取值.
    "financial_indicator": ["code", "end_date", "roe", "roa",
        "gross_margin", "net_margin", "debt_ratio",
        "eps", "current_ratio", "revenue_growth", "profit_growth"],
}
# PG 表列名 → Tushare API 字段名 (取值用 Tushare 名, 写入用 PG 列名).
_FINANCIAL_FIELD_ALIASES = {
    "financial_indicator": {
        "gross_margin": "grossprofit_margin", "net_margin": "netprofit_margin",
        "debt_ratio": "debt_to_assets", "revenue_growth": "or_yoy",
        "profit_growth": "netprofit_yoy",
    },
}


def _financial_rows_from_df(table: str, cols: list[str], df,
                            code_override: str | None = None) -> list[tuple]:
    """df → 写入行 tuples. code_override=None 时从 ts_code 拆 6 位代码 (bulk 路径)."""
    aliases = _FINANCIAL_FIELD_ALIASES.get(table, {})
    rows = []
    for _, r in df.iterrows():
        row_vals = []
        for c in cols:
            if c == "code":
                if code_override is not None:
                    row_vals.append(code_override)
                else:
                    row_vals.append(str(r.get("ts_code", "")).split(".")[0])
            elif c == "end_date":
                row_vals.append(str(r.get("end_date", "")))
            elif c == "report_type":
                row_vals.append(str(r.get("report_type", "")))
            else:
                v = r.get(aliases.get(c, c))
                if isinstance(v, (int, float)) is False and v is not None:
                    import numpy as _np
                    if isinstance(v, _np.floating):
                        v = float(v) if not _np.isnan(v) else None
                    elif isinstance(v, _np.integer):
                        v = int(v)
                elif isinstance(v, float):
                    import math
                    if math.isnan(v):
                        v = None
                row_vals.append(v)
        rows.append(tuple(row_vals))
    # 按 (code, end_date) 去重: 同期可能返回多版本行 (保留最后=最新版本)
    if len(rows) > 1:
        ci, ei = cols.index("code"), cols.index("end_date")
        dedup = {}
        for row in rows:
            dedup[(row[ci], row[ei])] = row
        rows = list(dedup.values())
    return rows


def _insert_financial_rows(db, table: str, cols: list[str], rows: list[tuple],
                           conflict_action: str) -> int:
    """按 conflict_action 写一批财报行, 返回写入行数."""
    if conflict_action == "update":
        upd = [c for c in cols if c not in ("code", "end_date", "report_type")]
        return _insert_rows(db, table, cols, rows, conflict_action="update",
                            conflict_cols=["code", "end_date"], update_cols=upd)
    return _insert_rows(db, table, cols, rows)


def _sync_bulk_financial(table: str, api_name: str, fields: str,
                         periods: list[str], conflict_action: str = "nothing") -> dict:
    """按报告期整批拉取的财报同步 (Tushare VIP 快速路径).

    pro.query(api_name, period=...) 一次调用拿全市场单季度 (~5000 行/页),
    2 个季度仅需数次调用, 替代 _sync_per_stock_financial 的 5022×2 次逐股调用
    (实测 15+ 分钟 → 约 1 分钟).
    """
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    db = _get_etl_db()
    db.row_factory = sqlite3.Row
    cols = _FINANCIAL_COLS_MAP.get(table, [])
    if not cols:
        db.close()
        return {"status": "error", "reason": f"unknown table: {table}"}

    total, written = 0, 0
    for period in periods:
        offset = 0
        while True:
            _rate_limit()
            try:
                df = pro.query(api_name, period=period, fields=fields,
                               limit=5000, offset=offset)
            except Exception as e:
                if "ts_code" in str(e) or "必填" in str(e):
                    # 当前账号不允许按 period 全市场拉取 → 降级并行逐股路径
                    print(f"  {api_name}: period 整批拉取被拒 ({str(e)[:40]}), 降级并行逐股")
                    db.close()
                    return _sync_per_stock_financial(table, api_name, fields, periods,
                                                     conflict_action=conflict_action)
                raise
            if df is None or df.empty:
                break
            rows = _financial_rows_from_df(table, cols, df)
            total += len(rows)
            written += _insert_financial_rows(db, table, cols, rows, conflict_action)
            if len(df) < 5000:
                break
            offset += 5000
        print(f"  {api_name} period={period}: fetched={total} written={written}")
    db.commit()
    db.close()
    return {"status": "ok", "table": table, "fetched": total, "written": written,
            "mode": "bulk_period"}


def _sync_per_stock_financial(table: str, api_name: str, fields: str,
                               periods: list[str], extra_kwargs: dict = None,
                               conflict_action: str = "nothing",
                               codes: list[str] = None) -> dict:
    """Generic per-stock financial data sync for quarterly statements.

    Calls pro.<api_name>(ts_code=<ts_code>, period=<period>, fields=<fields>) per stock.
    Rate-limited to ~450 calls/min.

    Args:
        conflict_action: "nothing" (默认, ON CONFLICT DO NOTHING) | "update" (回填已有行的
                         NULL 字段, 用于历史回填 growth 等). update 模式下 conflict_cols=[code,end_date],
                         update_cols=cols 去掉 code/end_date/report_type.
        codes: 指定股票代码列表 (None=全市场 _get_all_codes, 用于小范围历史回填).
    """
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}

    db = _get_etl_db()
    db.row_factory = sqlite3.Row
    if codes is None:
        codes = _get_all_codes(db)
    total, written = 0, 0

    # 列映射与别名已提升为模块级 _FINANCIAL_COLS_MAP / _FINANCIAL_FIELD_ALIASES
    # (与 _sync_bulk_financial 共用, P4 修复注释见模块级定义).
    cols = _FINANCIAL_COLS_MAP.get(table, [])
    if not cols:
        db.close()
        return {"status": "error", "reason": f"unknown table: {table}"}

    fn = getattr(pro, api_name)
    processed = 0

    # 并行拉取: API 调用是瓶颈 (每对 code×period 一次), 行构建与写库留在主线程
    # (thread-local 连接 + _insert_rows 串行, 无并发写风险).
    # max_workers 默认 8, TUSHARE_FINANCIAL_WORKERS 可调; _rate_limit 全局滑动窗口兜底.
    max_workers = int(os.environ.get("TUSHARE_FINANCIAL_WORKERS", "8"))
    from concurrent.futures import ThreadPoolExecutor

    def _fetch(pair):
        code, period = pair
        _rate_limit()
        try:
            kwargs = {"ts_code": _ts_code(code), "period": period,
                      "fields": fields}
            if extra_kwargs:
                kwargs.update(extra_kwargs)
            return code, fn(**kwargs)
        except Exception:
            return code, None

    def _drain(pairs_subset, workers: int) -> tuple[int, int, list]:
        """并行拉取+主线程写库一轮, 返回 (total, written, 失败 pairs)."""
        _total, _written = 0, 0
        failed = []
        nonlocal processed
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for code, df in ex.map(_fetch, pairs_subset):
                if df is None:
                    failed.append(code)
                if df is None or df.empty:
                    processed += 1
                    continue
                rows = _financial_rows_from_df(table, cols, df, code_override=code)
                _total += len(rows)
                _written += _insert_financial_rows(db, table, cols, rows, conflict_action)
                processed += 1
                if processed % 500 == 0:
                    print(f"  {api_name}: {processed}/{len(codes)} ({processed*100//len(codes)}%) "
                          f"- {written + _written} rows")
        return _total, _written, failed

    pairs = [(code, period) for code in codes for period in periods]
    total, written, failed_codes = _drain(pairs, max_workers)

    # 限流导致的静默失败: 串行慢速重试 2 轮 (高并发下 Tushare 服务端实际仍限流,
    # 实测 8 线程 2000/min 失败率 ~70%; 重试轮用单线程把失败对补回来)
    for retry_round in (1, 2):
        if not failed_codes:
            break
        print(f"  {api_name}: {len(failed_codes)} 只拉取失败, 串行重试第 {retry_round} 轮")
        time.sleep(5)
        retry_pairs = [(c, p) for c in failed_codes for p in periods]
        t2, w2, failed_codes = _drain(retry_pairs, workers=1)
        total += t2
        written += w2
    if failed_codes:
        print(f"  {api_name}: 重试后仍 {len(failed_codes)} 只失败: {failed_codes[:10]}")

    db.commit()
    db.close()
    print(f"  {api_name}: {total} fetched, {written} written "
          f"({len(codes)} stocks, {len(periods)} quarters)")
    return {"status": "ok", "table": table, "fetched": total, "written": written}


def _recent_quarters(n: int = 2) -> list[str]:
    """Compute the N most recent quarter-end dates dynamically (YYYYMMDD)."""
    today = datetime.now().date()
    quarters = []
    for year in range(today.year, today.year - 3, -1):
        for m, d in [("12", "31"), ("09", "30"), ("06", "30"), ("03", "31")]:
            try:
                qd = datetime(year, int(m), int(d)).date()
            except ValueError:
                continue
            if qd <= today:
                quarters.append(qd.strftime("%Y%m%d"))
            if len(quarters) >= n + 2:
                break
        if len(quarters) >= n + 2:
            break
    return sorted(set(quarters), reverse=True)[:n]


def sync_income(days_back: int = 30) -> dict:
    """Sync pro.income() — latest 2 quarters for all stocks (bulk 按报告期整批拉取)."""
    periods = _recent_quarters(2)
    fields = "ts_code,end_date,report_type,basic_eps,total_revenue,revenue,oper_cost,sell_expense,admin_expense,fin_expense,n_income,n_income_attr_p,operate_profit,total_profit"
    return _sync_bulk_financial("financial_income", "income", fields, periods)


def sync_balancesheet(days_back: int = 30) -> dict:
    """Sync pro.balancesheet() — latest 2 quarters for all stocks (bulk 按报告期整批拉取)."""
    periods = _recent_quarters(2)
    fields = "ts_code,end_date,report_type,total_assets,total_cur_assets,total_liab,total_cur_liab,total_hldr_eqy_exc_min_int,total_share,cap_rese,undistr_porfit"
    return _sync_bulk_financial("financial_balance", "balancesheet", fields, periods)


def sync_cashflow(days_back: int = 30) -> dict:
    """Sync pro.cashflow() — latest 2 quarters for all stocks (bulk 按报告期整批拉取)."""
    periods = _recent_quarters(2)
    fields = "ts_code,end_date,report_type,n_cashflow_act,n_cashflow_inv_act,n_cashflow_fin_act,c_fr_sale_sg,net_profit"
    return _sync_bulk_financial("financial_cashflow", "cashflow", fields, periods)


def sync_financial_indicator(days_back: int = 30) -> dict:
    """Sync pro.fina_indicator() — latest 2 quarters for all stocks (bulk 按报告期整批拉取).

    P4 修复: fields 含 netprofit_yoy (归母净利同比→profit_growth), 配合 cols_map/field_aliases
    正确写入 PG 列. 原 profit_dedt 是扣非净利绝对值非同比, 已弃用.
    """
    periods = _recent_quarters(2)
    fields = "ts_code,end_date,roe,roa,grossprofit_margin,netprofit_margin,debt_to_assets,eps,current_ratio,or_yoy,netprofit_yoy"
    return _sync_bulk_financial("financial_indicator", "fina_indicator", fields, periods)


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
            ex_date = str(r.get("ex_date", ""))
            if ex_date in {"", "nan", "NaT", "None"}:
                continue
            key = (_code_from_ts(r["ts_code"]), str(r.get("end_date", "")))
            if key in seen:
                continue
            seen.add(key)
            rows.append((
                _code_from_ts(r["ts_code"]),
                str(r.get("end_date", "")),
                str(r.get("ann_date", d)),
                r.get("cash_div"), r.get("stk_div"),
                r.get("stk_bo_rate"), r.get("record_date"), ex_date,
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
        except Exception as e: logger.warning("top_inst fetch failed for %s: %s", d, e); continue
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
        except Exception as e: logger.warning("block_trade fetch failed for %s: %s", d, e); continue
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
        except Exception as e: logger.warning("margin fetch failed for %s: %s", d, e); continue
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
        except Exception as e: logger.warning("moneyflow_hsgt fetch failed for %s: %s", d, e); continue
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
        except Exception as e: logger.warning("stk_holdertrade fetch failed for %s: %s", d, e); continue
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
        except Exception as e: logger.warning("stk_holdernumber fetch failed for %s: %s", code, e); continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            holder_num = r.get("holder_num")
            try:
                if holder_num is not None and float(holder_num) > 9223372036854775807:
                    logger.warning("stk_holdernumber out-of-range value skipped: %s", holder_num)
                    continue
            except (TypeError, ValueError, OverflowError):
                logger.warning("stk_holdernumber invalid value skipped: %s", holder_num)
                continue
            rows.append((code, str(r.get("end_date", "")), holder_num))
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
    # P1-3 (audit): cols[5] is the PG column name ``pledge_total_ratio`` and MUST
    # match the live DB schema (verified: \d pledge_detail → pledge_total_ratio).
    # The value at rows[*][5] comes from Tushare field ``p_total_ratio`` (the API
    # field name, not the column name) — see rows.append below. Position-aligned,
    # so the value lands in the correct column. Do NOT rename cols[5] to
    # ``p_total_ratio``: _insert_rows would then filter it out as an unknown PG
    # column and the data would be silently dropped.
    cols = ["code", "ann_date", "pledgor", "pledgee", "pledge_amount", "pledge_total_ratio"]
    for code in codes:
        _rate_limit()
        try: df = pro.pledge_detail(ts_code=_ts_code(code))
        except Exception as e: logger.warning("pledge_detail fetch failed for %s: %s", code, e); continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            # ADR-009 §决策4a: ann_date 格式化 "YYYYMMDD"→"YYYY-MM-DD" (同 sw_daily trade_date 模式, L1289-1291)
            td = str(r.get("ann_date", ""))
            ann_date = td[:4] + "-" + td[4:6] + "-" + td[6:8] if len(td) == 8 else td
            if ann_date in {"", "nan", "NaT", "None"}:
                continue
            rows.append((code, ann_date,
                str(r.get("pledgor", "")), str(r.get("pledgee", "")),
                r.get("pledge_amount"), r.get("p_total_ratio")))  # Tushare field p_total_ratio → PG col pledge_total_ratio (cols[5])
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
        except Exception as e: logger.warning("repurchase fetch failed for %s: %s", d, e); continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            end_date = r.get("end_date")
            if str(end_date) in {"", "nan", "NaT", "None"}:
                end_date = None
            rows.append((_code_from_ts(r["ts_code"]),
                str(r.get("ann_date", d)), end_date,
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
        except Exception as e: logger.warning("share_float fetch failed for %s: %s", d, e); continue
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
            except Exception as e: logger.warning("cyq_chips fetch failed for %s %s: %s", code, d, e); continue
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
        except Exception as e: logger.warning("broker_recommend fetch failed for %s: %s", month, e); continue
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
        except Exception as e: logger.warning("research_report fetch failed for %s..%s: %s", start, end, e); continue
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
    # 新闻接口不是个股接口，统一使用 MARKET 作为业务来源标识，满足表的 code 非空约束。
    cols = ["code", "pub_time", "title", "content", "source"]
    today = datetime.now()
    for i in range(0, days_back, 30):
        end = (today - timedelta(days=i)).strftime("%Y%m%d")
        start = (today - timedelta(days=min(days_back, i+30))).strftime("%Y%m%d")
        _rate_limit()
        # major_news
        try: df = pro.major_news(src="", start_date=start, end_date=end)
        except Exception: df = None
        if df is not None and not df.empty:
            rows = [("MARKET", str(r.get("pub_time",""))[:19], str(r.get("title","")), "", str(r.get("src",""))) for _, r in df.iterrows()]
            total += len(rows)
            written += _insert_rows(db, "stock_news_tushare", cols, rows)
        # news
        try: df = pro.news(start_date=start, end_date=end)
        except Exception: df = None
        if df is not None and not df.empty:
            rows = [("MARKET", str(r.get("datetime",""))[:19], str(r.get("title","")), str(r.get("content","")), "tushare_news") for _, r in df.iterrows()]
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
    # PG columns: code, trade_date, name, open, high, low, close, change, change_pct, pe, pb, float_mv, total_mv, vol, amount
    cols = ["code", "trade_date", "name", "open", "high", "low", "close",
            "change", "change_pct", "pe", "pb", "float_mv", "total_mv", "vol", "amount"]
    today = datetime.now()
    for i in range(0, days_back, 30):
        end = (today - timedelta(days=i)).strftime("%Y%m%d")
        start = (today - timedelta(days=min(days_back, i+30))).strftime("%Y%m%d")
        _rate_limit()
        try: df = pro.sw_daily(start_date=start, end_date=end)
        except Exception as e: logger.warning("sw_daily fetch failed for %s..%s: %s", start, end, e); continue
        if df is None or df.empty: continue
        rows = []
        for _, r in df.iterrows():
            tc = str(r.get("ts_code", ""))
            code = tc.split(".")[0] if "." in tc else tc
            td = str(r.get("trade_date", ""))
            rows.append((
                code, td[:4]+"-"+td[4:6]+"-"+td[6:8] if len(td)==8 else td,
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
    # ADR-009 §决策4b: cols trade_time→trade_date, ts_code→code (engine 命名; 下游 WHERE ts_code=? 经 pg_adapter 翻译)
    cols = ["code", "trade_date", "name", "close", "pre_close",
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
        # ADR-009 §决策4b: code=ts_code split 裸码, trade_date=trade_time 抽 date 部分
        tc = str(r.get("ts_code", ""))
        code = tc.split(".")[0] if "." in tc else tc
        trade_date = str(r.get("trade_time", ""))[:10]  # "2026-06-22 14:55:00" → "2026-06-22"
        rows.append((
            code, trade_date, str(r.get("name", "")).strip(),
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

    Aggregates stk_mins 5-min bars into daily OHLCV bars for the latest
    trading day. Uses PG-compatible SQL with subquery to avoid window-function
    vs GROUP BY conflicts.

    Called every 5 min during trading hours (L0 realtime).
    """
    import psycopg2
    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()
    t0 = time.time()
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
        # PG-compatible daily OHLCV aggregation from 5-min bars
        # Use subquery to avoid window-function + GROUP BY conflict
        sql = (
            "SELECT code, trade_date, "
            "(ARRAY_AGG(open ORDER BY trade_time))[1] AS open, "
            "MAX(high) AS high, MIN(low) AS low, "
            "(ARRAY_AGG(close ORDER BY trade_time DESC))[1] AS close, "
            "SUM(volume) AS vol, SUM(amount) AS amount "
            "FROM ("
            "  SELECT code, trade_time::date AS trade_date, trade_time, "
            "         open, high, low, close, volume, amount "
            "  FROM stk_mins "
            "  WHERE trade_time::date = %s::date AND freq='5min'"
            ") sub "
            "GROUP BY code, trade_date"
        )
        rows = db.execute(sql, (latest_dt,)).fetchall()
        total = len(rows)
        if total > 0:
            # ADR-015.6: inline-cursor 逐行 UPSERT → _insert_rows(update) 批量
            # 业务语义: 盘中每 5min 刷新当日 rt_k OHLCV (ON CONFLICT(code,trade_date) DO UPDATE)
            # 表无 updated_at, 不传 now_cols. 只写 8 列 (OHLCV+code+trade_date),
            # pre_close/change/pct_chg 不写 (聚合 SQL 没算, pre-existing 行为 100% 还原)
            insert_cols = ["code", "trade_date", "open", "high", "low", "close", "vol", "amount"]
            written = _insert_rows(
                db, "rt_k", insert_cols, [tuple(r) for r in rows],
                conflict_action="update",
                conflict_cols=["code", "trade_date"],
                update_cols=["open", "high", "low", "close", "vol", "amount"],
            )
            db.commit()
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)[:80]}
    db.close()
    elapsed = time.time() - t0
    print(f"  rt_k: {total} stocks aggregated from stk_mins ({latest_dt}), {written} written, {elapsed:.1f}s")
    return {"status": "ok", "table": "rt_k", "fetched": total, "written": written, "elapsed": elapsed}


def sync_stk_auction_o(trade_date: str = None) -> dict:
    """Sync pro.stk_auction() — 开盘集合竞价数据 (9:25-9:29 实时发布).

    Uses Tushare stk_auction (new) interface available daily at 9:25-9:29 AM.
    Falls back to stk_auction_o (old, EOD) if new interface unavailable.

    Field mapping: price→open, pre_close→close (no high/low/vwap in new API).

    Args:
        trade_date: YYYYMMDD format, defaults to today.
    """
    import numpy as np

    pro = _get_pro()
    if pro is None: return {"status": "skipped", "reason": "no Tushare token"}
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")
    total, written = 0, 0

    # Try new stk_auction first (real-time, 9:25-9:29)
    df = None
    try:
        df = pro.stk_auction(trade_date=trade_date)
    except Exception:
        pass

    # Fallback to old stk_auction_o (EOD update)
    if df is None or df.empty:
        try:
            df = pro.stk_auction_o(trade_date=trade_date)
        except Exception as e:
            err = str(e)
            if "权限" in err or "permission" in err.lower():
                return {"status": "no_permission", "reason": "stk_auction requires permission"}
            return {"status": "error", "reason": err[:80]}

    if df is None or df.empty:
        return {"status": "ok", "table": "stk_auction_o", "fetched": 0, "written": 0}

    # Detect API version and map fields
    has_open = 'open' in df.columns
    db = _get_etl_db()
    cols = ["code", "trade_date", "close", "open", "high", "low", "vol", "amount", "vwap"]
    rows = []
    for _, r in df.iterrows():
        ts_code = str(r.get("ts_code", ""))
        code = ts_code.split(".")[0][:6] if "." in ts_code else ts_code

        if has_open:
            # Old API: close/open/high/low/vwap present
            open_p = r.get("open")
            close_p = r.get("close")
            high_p = r.get("high", open_p)
            low_p = r.get("low", open_p)
            vwap_p = r.get("vwap", open_p)
        else:
            # New API: price=竞价均价, pre_close=昨收
            open_p = r.get("price")
            close_p = r.get("pre_close")
            high_p = open_p
            low_p = open_p
            vwap_p = open_p

        try:
            of = float(open_p) if open_p is not None else None
            cf = float(close_p) if close_p is not None else None
            if of is None or cf is None or np.isnan(of) or np.isnan(cf) or of <= 0 or cf <= 0:
                continue
        except (ValueError, TypeError):
            continue

        vol = r.get("vol", 0) or 0
        amt = r.get("amount", 0) or 0
        rows.append((code, f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
                     cf, of, float(high_p or of), float(low_p or of),
                     float(vol), float(amt), float(vwap_p or of)))

    total = len(rows)
    written = _insert_rows(db, "stk_auction_o", cols, rows)
    db.commit(); db.close()
    print(f"  stk_auction_o: {total} fetched, {written} written ({trade_date}) [src={'stk_auction' if not has_open else 'stk_auction_o'}]")
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
    cols = ["code", "trade_date", "open", "high", "low", "close",
            "volume", "amount", "change_pct"]
    for td in dates:
        try:
            df = pro.daily(trade_date=td)
            _rate_limit()
            if df is None or df.empty: continue
            rows = [(_code_from_ts(str(r["ts_code"])), _date_from_tushare(r["trade_date"]),
                     r.get("open"), r.get("high"), r.get("low"), r.get("close"),
                     r.get("vol"), r.get("amount"), r.get("pct_chg")) for _, r in df.iterrows()]
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


# ═══════════════════════════════════════════════════════════════
# 可转债同步 (3 functions)
# ═══════════════════════════════════════════════════════════════

def sync_cb_basic(days_back: int = 0) -> dict:
    """Sync pro.cb_basic() — full refresh of convertible bond basic info."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()

    cols = ["ts_code", "bond_full_name", "bond_short_name", "cb_code", "cb_type",
            "stk_code", "stk_short_name", "maturity", "par", "issue_price",
            "issue_size", "remain_size", "value_date", "maturity_date",
            "rate_type", "coupon_rate", "add_rate", "pay_per_year",
            "list_date", "delist_date", "exchange", "conv_start_date",
            "conv_end_date", "conv_stop_date", "first_conv_price", "conv_price",
            "rate_clause", "put_clause", "maturity_call_price", "call_clause",
            "reset_clause", "conv_clause", "guarantor", "guarantee_type",
            "issue_rating", "newest_rating", "rating_comp"]
    date_cols = {"value_date", "maturity_date", "list_date", "delist_date",
                 "conv_start_date", "conv_end_date", "conv_stop_date"}

    def _safe_val(c, v):
        if v is None:
            return None
        # Convert numpy scalars to native Python types
        try:
            import numpy as np
            if isinstance(v, (np.integer,)):
                return int(v)
            if isinstance(v, (np.floating,)):
                if np.isnan(v):
                    return None
                return float(v)
            if isinstance(v, np.bool_):
                return bool(v)
        except ImportError:
            pass
        if isinstance(v, float) and str(v) == 'nan':
            return None
        if c in date_cols and v is not None:
            s = str(v).strip()
            if len(s) == 8 and s.isdigit():
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            return s if s else None
        return v

    _rate_limit()
    try:
        df = pro.cb_basic(fields=",".join(cols))
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)}

    if df is None or df.empty:
        db.close()
        return {"status": "skipped", "reason": "no data"}

    rows = []
    for _, r in df.iterrows():
        rows.append(tuple(_safe_val(c, r.get(c)) for c in cols))

    written = _insert_rows(
        db,
        "cb_basic",
        cols,
        rows,
        conflict_action="update",
        conflict_cols=["ts_code"],
        update_cols=[c for c in cols if c != "ts_code"],
        now_cols=["updated_at"],
    )

    db.commit()
    db.close()
    print(f"  cb_basic: {len(rows)} fetched, {written} written")
    return {"status": "ok", "table": "cb_basic", "fetched": len(rows), "written": written}


def sync_cb_daily(days_back: int = 30) -> dict:
    """Sync pro.cb_daily() — daily CB quotes with premium rates."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "cb_daily", days_back)

    total, written = 0, 0
    cols = ["ts_code", "trade_date", "pre_close", "open", "high", "low",
            "close", "change", "pct_chg", "vol", "amount",
            "bond_value", "bond_over_rate", "cb_value", "cb_over_rate"]

    def _safe_cb_val(v):
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

    for d in dates:
        _rate_limit()
        try:
            df = pro.cb_daily(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            # 停牌/退市期间 Tushare 返回 OHLC 全 0 的占位行 — 无信息量且污染
            # 收益计算 (close=0 → -100%), 直接跳过 (历史存量见 2026-07-18 清理)
            ohlc = [_safe_cb_val(r.get(c)) for c in ("open", "high", "low", "close")]
            if all(v in (None, 0) for v in ohlc):
                continue
            rows.append(tuple(
                _safe_cb_val(r.get(c)) if c != "trade_date"
                else d[:4] + "-" + d[4:6] + "-" + d[6:8]
                for c in cols
            ))
        total += len(rows)
        written += _insert_rows(db, "cb_daily", cols, rows)

    db.commit()
    db.close()
    print(f"  cb_daily: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "cb_daily", "fetched": total, "written": written}


def sync_cb_price_chg(days_back: int = 365) -> dict:
    """Sync pro.cb_price_chg() — conversion price change history."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()
    clean_before_write(db, "cb_price_chg", days_back, date_col="change_date")

    total, written = 0, 0
    cols = ["ts_code", "change_date", "pre_price", "new_price", "change_reason"]

    def _safe_pc_val(v):
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
        return v

    for d in dates:
        _rate_limit()
        try:
            df = pro.cb_price_chg(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            rows.append((
                str(r.get("ts_code", "")),
                d[:4] + "-" + d[4:6] + "-" + d[6:8],
                _safe_pc_val(r.get("pre_price")),
                _safe_pc_val(r.get("new_price")),
                str(r.get("change_reason") or r.get("change_reason_desc") or "")[:200],
            ))
        total += len(rows)
        written += _insert_rows(db, "cb_price_chg", cols, rows)

    db.commit()
    db.close()
    print(f"  cb_price_chg: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "cb_price_chg", "fetched": total, "written": written}


def sync_cb_call(days_back: int = 365) -> dict:
    """Sync pro.cb_call() — redemption/call info for risk detection."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    db = _get_etl_db()

    cols = ["ts_code", "call_type", "is_call", "ann_date", "call_date",
            "call_price", "call_price_tax", "call_vol", "call_amount",
            "payment_date", "call_reg_date"]

    _rate_limit()
    try:
        df = pro.cb_call()
    except Exception as e:
        db.close()
        return {"status": "error", "reason": str(e)}

    if df is None or df.empty:
        db.close()
        return {"status": "skipped", "reason": "no data"}

    rows = []
    for _, r in df.iterrows():
        rows.append(tuple(
            str(r.get(c)) if c in ("ts_code", "call_type", "is_call") and r.get(c) is not None
            else (r.get(c) if not (isinstance(r.get(c), float) and str(r.get(c)) == 'nan') else None)
            for c in cols
        ))

    written = _insert_rows(db, "cb_call", cols, rows)

    db.commit()
    db.close()
    print(f"  cb_call: {len(rows)} fetched, {written} written")
    return {"status": "ok", "table": "cb_call", "fetched": len(rows), "written": written}


def sync_cb_factor(days_back: int = 30) -> dict:
    """Sync pro.cb_factor_pro() — selected technical indicators for CBs."""
    pro = _get_pro()
    if pro is None:
        return {"status": "skipped", "reason": "no Tushare token"}
    dates = _get_trade_dates(days_back)
    db = _get_etl_db()

    cols = ["ts_code", "trade_date", "close", "pre_close", "pct_change",
            "vol", "amount", "rsi_6", "rsi_12", "rsi_24",
            "macd", "macd_dif", "macd_dea",
            "boll_upper", "boll_mid", "boll_lower",
            "atr", "ma_5", "ma_20", "ma_60"]
    src_cols = ["close", "pre_close", "pct_change",
               "vol", "amount", "rsi_bfq_6", "rsi_bfq_12", "rsi_bfq_24",
               "macd_bfq", "macd_dif_bfq", "macd_dea_bfq",
               "boll_upper_bfq", "boll_mid_bfq", "boll_lower_bfq",
               "atr_bfq", "ma_bfq_5", "ma_bfq_20", "ma_bfq_60"]

    total, written = 0, 0
    for d in dates:
        _rate_limit()
        date_str = d[:4] + "-" + d[4:6] + "-" + d[6:8]
        try:
            df = pro.cb_factor_pro(trade_date=d)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        rows = []
        for _, r in df.iterrows():
            row_vals = [r.get("ts_code"), date_str]
            for c in src_cols:
                v = r.get(c)
                if isinstance(v, float) and str(v) == 'nan':
                    row_vals.append(None)
                else:
                    row_vals.append(v)
            rows.append(tuple(row_vals))

        total += len(rows)
        written += _insert_rows(db, "cb_factor", cols, rows)

    db.commit()
    db.close()
    print(f"  cb_factor: {total} fetched, {written} written ({len(dates)} dates)")
    return {"status": "ok", "table": "cb_factor", "fetched": total, "written": written}


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
    "cb_basic": sync_cb_basic,
    "cb_daily": sync_cb_daily,
    "cb_price_chg": sync_cb_price_chg,
    "cb_call": sync_cb_call,
    "cb_factor": sync_cb_factor,
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
