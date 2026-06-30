"""PG 直写 — best-effort, ON CONFLICT DO NOTHING + executemany 批量写入.

ADR-012 §决策 5.2: _pg_write 改为 thin wrapper, 内部 delegate 给 kronos_data.etl._insert_rows
(获得自动列过滤能力 + 统一重试 + 数据量门禁). 保留 8 个 write_* helper 外部入口名与现有 column
mapping 逻辑 (write_moneyflow / write_daily_basic / write_index_daily 等的字段重排是业务必需).
"""

import logging, os, sys, time
from psycopg2.sql import SQL, Identifier

logger = logging.getLogger("data-service.pg_writer")

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")

_MAX_RETRIES = 3  # ADR-006 决策 6: 3 次指数退避 (1s, 4s, 16s); ADR-012 §决策 5.1 沿用

# ADR-013 §决策 4 (W-2): 数据量门禁阈值表 — 二档分级 (floor → ERROR, warn → WARN).
# 替代 ADR-012 单档 _VOLUME_FLOOR_MAP (新 _insert_rows 已支持 data_volume_warn 参数).
# 仅对 daily_kline / stk_mins 这两张 P0 量级表启用二档门禁; 其他表 None=不启用 (字典 .get 返回 {}).
# 单档历史阈值: <1000 ERROR + <3000 WARN (原 pg_writer._check_data_volume 内部硬编码), 二档表 1:1 还原.
_VOLUME_THRESHOLD_MAP: dict[str, dict[str, int]] = {
    "daily_kline": {"floor": 1000, "warn": 3000},
    "stk_mins":    {"floor": 1000, "warn": 3000},
}

# 确保 kronos-data 可 import (data-service 启动时 scheduler.py 已注入 sys.path,
# 但 pg_writer 可能被先 import; 复用同套 sys.path 注入策略)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
_KRONOS_DATA = os.path.join(_PROJ_ROOT, "packages", "kronos-data")
if _KRONOS_DATA not in sys.path:
    sys.path.insert(0, _KRONOS_DATA)


def _pg_write(table: str, columns: list[str], conflict_cols: list[str],
              rows: list[tuple],
              conflict_action: str = "nothing",
              update_cols: list[str] | None = None,
              now_cols: list[str] | None = None) -> int:
    """通用 PG 批量写入 — ADR-012 §决策 5.2: thin wrapper, delegate to kronos_data.etl._insert_rows.

    Args:
        table: 表名
        columns: 列名 (业务列)
        conflict_cols: ON CONFLICT 列 (保留参数兼容外部 8 个 write_* helper 签名;
                       ADR-012 §决策 5.2.bis: _insert_rows 用 ON CONFLICT DO NOTHING 依赖表 PK 约束,
                       与 ON CONFLICT(conflict_cols) DO NOTHING 仅在 conflict_cols ⊆ 表 PK 时等价;
                       grep 实证所有调用方传的 conflict_cols 都是表 PK / UNIQUE 约束列, 等价成立).
                       ADR-015.0 §决策 1: conflict_action="update" 时透传给 _insert_rows 作为
                       ON CONFLICT (cols) 约束声明 (非 DO NOTHING 等价回退).
        rows: 待写入数据
        conflict_action: ADR-015.0 §决策 1 — "nothing" (默认, DO NOTHING, 100% 向后兼容) |
                        "update" (DO UPDATE SET, 解锁 stocks / namechange UPSERT 语义).
        update_cols: conflict_action="update" 时必传 (⊆ columns, ∩ conflict_cols = ∅,
                    禁含 created_at/updated_at). 默认 None.
        now_cols: ADR-015.0 minor amend — DO UPDATE SET 走 NOW() 的列 (如 updated_at).
                  ∩ update_cols = ∅, ⊆ columns. 默认 None.

    Returns:
        实际写入行数 (扣除 ON CONFLICT 跳过的). 出错时 0.

    Raises:
        ValueError: ADR-015.0 conflict_action / cols 约束违反时由 _insert_rows raise.

    路径合并语义变化 (与旧实现对比):
      - 旧: 显式 ON CONFLICT(conflict_cols) DO NOTHING + 失败 print + return 0
      - 新: _insert_rows 自动列过滤 (列名错位时 WARN + 丢列, 不再整批 UndefinedColumn 归零)
            + retries=3 OperationalError 重试 (与旧实现等价)
            + data_volume_floor (daily_kline / stk_mins 触发)
            + conflict_action 可选 UPSERT (ADR-015.0)
      - conflict_cols 参数语义保留: 调用方仍按表 PK 列传, conflict_action="update" 时实际生效
    """
    if not rows:
        return 0
    # Lazy import 避免循环依赖 (kronos_data.etl 顶层不依赖 services/)
    from kronos_data.etl import _insert_rows, _get_etl_db
    db = _get_etl_db()
    try:
        # ADR-013 §决策 4 (W-2): 二档阈值映射 — {table: {floor, warn}}; 未配置表回退 {} → 双 None
        cfg = _VOLUME_THRESHOLD_MAP.get(table, {})
        written = _insert_rows(db, table, columns, rows,
                               retries=_MAX_RETRIES,
                               data_volume_floor=cfg.get("floor"),
                               data_volume_warn=cfg.get("warn"),
                               conflict_action=conflict_action,
                               conflict_cols=conflict_cols,
                               update_cols=update_cols,
                               now_cols=now_cols)
        return written
    except Exception as e:
        # _insert_rows 内部已 catch 大部分异常, 此处兜底 connection 失败等
        print(f"  [WARN] _pg_write {table} thin-wrapper 失败: {str(e)[:140]}", flush=True)
        logger.debug("PG write %s wrapper exception: %s", table, e)
        return 0
    finally:
        try:
            db.close()
        except Exception:
            pass


# ADR-013 §决策 4 (W-2 联动 S-2): _check_data_volume 已删 — 二档分级逻辑迁移到 _insert_rows
# data_volume_floor / data_volume_warn 双参数 (etl.py:170). 历史阈值 (floor=1000/warn=3000) 在
# _VOLUME_THRESHOLD_MAP 透明保留. ADR-012 §决策 5.2 "_check_data_volume 被保留以兼容潜在外部
# 调用" 在 grep 实证下未发现任何外部调用 → 删除安全.


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
    """写入 limit_list_d 盘后 U 类型数据."""
    if not rows:
        return 0
    mapped = []
    for r in rows:
        trade_date_str = str(r[0])
        ts_code = str(r[1])
        mapped.append((trade_date_str, ts_code, "U", str(r[2]),
                       r[3], r[4], r[5], r[6], r[7],
                       r[8] or 0, str(r[9] or ""), str(r[10] or ""),
                       r[11] or 0, str(r[12] or ""), r[13] or 0))
    return _pg_write("limit_list_d",
                     ["trade_date", "ts_code", "limit_type", "name", "close", "pct_chg", "amount",
                      "float_mv", "turnover_ratio", "fd_amount", "first_time", "last_time",
                      "open_times", "up_stat", "limit_times"],
                     ["ts_code", "trade_date", "limit_type"], mapped)


def write_ths_daily(rows: list[tuple]) -> int:
    """写入 ths_daily (swap trade_date/ts_code, convert date to ISO)."""
    if not rows:
        return 0
    mapped = []
    for r in rows:
        # Tushare 顺序: (trade_date, ts_code, name, close, pct_change, avg_price, total_mv, float_mv)
        ts_code = str(r[1])
        trade_date_str = str(r[0])
        trade_date = (f"{trade_date_str[:4]}-{trade_date_str[4:6]}-{trade_date_str[6:8]}"
                      if len(trade_date_str) == 8 else trade_date_str)
        mapped.append((ts_code, trade_date, str(r[2]), r[3], r[4], r[5], r[6], r[7]))
    return _pg_write("ths_daily",
                     ["ts_code", "trade_date", "name", "close", "pct_change", "avg_price", "total_mv", "float_mv"],
                     ["ts_code", "trade_date"], mapped)


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
                cur.execute(SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(Identifier(view)))
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
