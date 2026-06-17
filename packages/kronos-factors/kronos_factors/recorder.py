"""因子快照记录器 — 轻量自学习 (无需 pgvector).

每次选股后调用 record_picks(), T+1 调用 backfill_outcomes().
"""
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("kronos.recorder")

# 可注入 PG 连接, 不注入则尝试环境变量
_pg_conn = None


def _get_conn():
    global _pg_conn
    if _pg_conn and not _pg_conn.closed:
        return _pg_conn
    import psycopg2, os
    url = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")
    _pg_conn = psycopg2.connect(url)
    _pg_conn.autocommit = True
    return _pg_conn


def record_picks(model_key: str, trade_date: str, time_slot: str, picks: list[dict]) -> int:
    """记录一批选股结果的因子快照.

    Args:
        model_key: 'leader_intraday_v7'
        trade_date: '2026-06-15'
        time_slot: '14:40'
        picks: [{code, total_score, grade, gain_14, sector_leader_score, ...}, ...]

    Returns:
        写入行数
    """
    if not picks:
        return 0

    # 提取因子键 (从 screening_models 读取, 或从第一条 pick 推断)
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT factor_keys FROM screening_models WHERE model_key = %s", (model_key,))
    row = cur.fetchone()
    if row:
        factor_keys = row[0]
    else:
        # 推断: 取 pick 中所有的数值字段
        factor_keys = [k for k, v in picks[0].items()
                       if isinstance(v, (int, float)) and k not in ('code',)]
        cur.execute("""
            INSERT INTO screening_models (model_key, display_name, category, factor_keys)
            VALUES (%s, %s, 'auto', %s)
            ON CONFLICT (model_key) DO NOTHING
        """, (model_key, model_key, factor_keys))
        conn.commit()

    rows = []
    for rank, pick in enumerate(picks):
        factors = {k: pick.get(k) for k in factor_keys if k in pick}
        rows.append((
            model_key, trade_date, pick["code"], time_slot,
            json_dumps(factors),
            pick.get("total_score"), pick.get("grade"),
            rank + 1
        ))

    from psycopg2.extras import execute_values
    execute_values(cur, """
        INSERT INTO screening_snapshots
            (model_key, trade_date, stock_code, time_slot, factors, total_score, grade, rank_in_day)
        VALUES %s
        ON CONFLICT DO NOTHING
    """, rows, page_size=100)
    conn.commit()

    n = cur.rowcount
    cur.close()
    if n:
        logger.info("recorder: %s %s — %d picks recorded", model_key, trade_date, n)
    return n


def backfill_outcomes(model_key: Optional[str] = None, days_back: int = 10):
    """回写最近 N 天快照的次日实际收益.

    Args:
        model_key: None=全部模型, 或指定模型
        days_back: 回看天数
    """
    conn = _get_conn()
    cur = conn.cursor()

    today = date.today()
    start = today - timedelta(days=days_back + 1)

    where = "WHERE next_day_return IS NULL"
    params = [start.isoformat(), today.isoformat()]
    if model_key:
        where += " AND model_key = %s"
        params.insert(0, model_key)

    cur.execute(f"""
        UPDATE screening_snapshots s
        SET next_day_return = (
            SELECT (k.close / d.close - 1) * 100
            FROM daily_kline d
            JOIN daily_kline k ON d.code = k.code AND k.trade_date > d.trade_date
            WHERE d.code = s.stock_code AND d.trade_date = s.trade_date
            AND k.trade_date = (SELECT MIN(trade_date) FROM daily_kline WHERE code = d.code AND trade_date > d.trade_date)
        ),
        is_win = (
            SELECT (k.close / d.close - 1) * 100 > 0
            FROM daily_kline d
            JOIN daily_kline k ON d.code = k.code AND k.trade_date > d.trade_date
            WHERE d.code = s.stock_code AND d.trade_date = s.trade_date
            AND k.trade_date = (SELECT MIN(trade_date) FROM daily_kline WHERE code = d.code AND trade_date > d.trade_date)
        ),
        outcome_at = NOW()
        {where}
        AND s.trade_date >= %s AND s.trade_date <= %s
    """, tuple(params))
    conn.commit()

    n = cur.rowcount
    cur.close()
    if n:
        logger.info("recorder: %d outcomes backfilled", n)
    return n


def get_similar(model_key: str, factors: dict, top_k: int = 10) -> list[dict]:
    """检索历史上因子最相似的 K 个案例.

    使用欧几里得距离 (无需 pgvector).
    """
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT stock_code, trade_date, factors, total_score, grade, next_day_return, is_win
        FROM screening_snapshots
        WHERE model_key = %s AND next_day_return IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT 500
    """, (model_key,))

    import numpy as np
    factor_keys = list(factors.keys())
    target = np.array([factors.get(k, 0) or 0 for k in factor_keys], dtype=np.float64)
    target_norm = np.linalg.norm(target)

    scored = []
    for row in cur.fetchall():
        hist_factors = row[2]  # JSONB dict
        hist_vec = np.array([float(hist_factors.get(k, 0) or 0) for k in factor_keys], dtype=np.float64)
        if np.linalg.norm(hist_vec) == 0:
            continue
        # Cosine similarity
        sim = np.dot(target, hist_vec) / (target_norm * np.linalg.norm(hist_vec))
        scored.append({
            "stock_code": row[0], "trade_date": row[1],
            "similarity": round(float(sim), 4),
            "next_day_return": row[4], "is_win": row[5],
        })

    scored.sort(key=lambda x: -x["similarity"])
    cur.close()
    return scored[:top_k]


def get_win_probability(model_key: str, factors: dict) -> Optional[float]:
    """基于相似案例, 估算胜率 (0-1)."""
    similar = get_similar(model_key, factors, top_k=20)
    if not similar:
        return None
    wins = sum(1 for s in similar if s["is_win"])
    # 相似度加权
    weighted = sum(s["similarity"] for s in similar if s["is_win"]) / max(0.001, sum(s["similarity"] for s in similar))
    return round(weighted, 4)


def get_model_stats(model_key: str) -> dict:
    """获取模型的累计统计数据."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*), COUNT(*) FILTER (WHERE is_win),
               AVG(next_day_return), SUM(next_day_return)
        FROM screening_snapshots
        WHERE model_key = %s AND next_day_return IS NOT NULL
    """, (model_key,))
    total, wins, avg_ret, cum_ret = cur.fetchone()
    cur.close()
    return {
        "total": total or 0,
        "wins": wins or 0,
        "win_rate": round(wins / total * 100, 1) if total else 0,
        "avg_return": round(avg_ret, 2) if avg_ret else 0,
        "cum_return": round(cum_ret, 2) if cum_ret else 0,
    }


# 工具: 确保 JSON 可序列化 (处理 numpy types)
def json_dumps(obj: dict) -> str:
    import json
    def _convert(o):
        import numpy as np
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o) if not np.isnan(o) else None
        if isinstance(o, np.ndarray): return o.tolist()
        return o
    return json.dumps({k: _convert(v) for k, v in obj.items()}, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════
# Multi-horizon performance tracking
# ═══════════════════════════════════════════════════════════════

HORIZONS = [
    (1, "next_day_return", "is_win", "outcome_at"),
    (3, "ret_3d", "is_win_3d", "ret_3d_at"),
    (5, "ret_5d", "is_win_5d", "ret_5d_at"),
    (10, "ret_10d", "is_win_10d", "ret_10d_at"),
    (20, "ret_20d", None, "ret_20d_at"),  # 20d win判定太远, 只记收益
]


def _get_nth_trading_day(cur, code, base_date, n):
    """Get the close price N trading days after base_date."""
    cur.execute("""
        SELECT close FROM daily_kline
        WHERE code = %s AND trade_date > %s
        ORDER BY trade_date ASC LIMIT 1 OFFSET %s
    """, (code, base_date, n - 1))
    row = cur.fetchone()
    return float(row[0]) if row else None


def backfill_multi_horizon(model_key: Optional[str] = None, days_back: int = 30):
    """回写最近 N 天快照的多周期实际收益 (T+1/3/5/10/20).

    Uses SQL OFFSET to find the Nth trading day after pick date.
    Safe to call multiple times — only updates rows where ret_Xd IS NULL.
    """
    conn = _get_conn()
    cur = conn.cursor()

    from datetime import date as dt_date
    today = dt_date.today()
    start = today - timedelta(days=days_back + 60)

    where = "WHERE (next_day_return IS NOT NULL AND (ret_3d IS NULL OR ret_5d IS NULL OR ret_10d IS NULL))"
    params = [start.isoformat(), today.isoformat()]
    if model_key:
        where += " AND model_key = %s"
        params.insert(0, model_key)

    # Fetch snapshots that need backfill
    cur.execute(f"""
        SELECT id, model_key, trade_date, stock_code
        FROM screening_snapshots
        {where}
        AND trade_date >= %s AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT 5000
    """, tuple(params))
    rows = cur.fetchall()
    cur.close()

    updated = 0
    cur2 = conn.cursor()
    for snap_id, mk, td, code in rows:
        td_str = str(td) if hasattr(td, 'isoformat') else td
        set_parts = []
        set_params = []

        for n, ret_col, win_col, at_col in HORIZONS:
            close_n = _get_nth_trading_day(cur2, code, td_str, n)
            if close_n is not None:
                # Get entry price from daily_kline on trade_date
                cur2.execute(
                    "SELECT close FROM daily_kline WHERE code=%s AND trade_date=%s",
                    (code, td_str)
                )
                entry_row = cur2.fetchone()
                if entry_row and entry_row[0] > 0:
                    ret = round((close_n / float(entry_row[0]) - 1) * 100, 2)
                    set_parts.append(f"{ret_col} = %s")
                    set_params.append(ret)
                    if win_col:
                        set_parts.append(f"{win_col} = %s")
                        set_params.append(ret > 0)
                    if at_col:
                        set_parts.append(f"{at_col} = NOW()")

        if set_parts:
            set_params.append(snap_id)
            cur2.execute(
                f"UPDATE screening_snapshots SET {', '.join(set_parts)} WHERE id = %s",
                set_params
            )
            updated += 1

    conn.commit()
    cur2.close()
    if updated:
        logger.info("recorder: %d snapshots multi-horizon backfilled", updated)
    return updated


def get_performance_report(model_key: Optional[str] = None,
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> dict:
    """获取模型绩效报告 — 按日期/模型聚合胜率和多周期收益.

    Returns:
        {
            "by_date": [{trade_date, total, wins, win_rate, avg_ret_1d, avg_ret_3d, avg_ret_5d}],
            "summary": {total_picks, overall_win_rate, avg_ret_1d, avg_ret_3d, avg_ret_5d, cum_ret},
        }
    """
    conn = _get_conn()
    cur = conn.cursor()

    where = "WHERE next_day_return IS NOT NULL"
    params = []
    if model_key:
        where += " AND model_key = %s"
        params.append(model_key)
    if start_date:
        where += " AND trade_date >= %s"
        params.append(start_date)
    if end_date:
        where += " AND trade_date <= %s"
        params.append(end_date)

    cur.execute(f"""
        SELECT trade_date, COUNT(*) as total,
               COUNT(*) FILTER (WHERE is_win) as wins,
               ROUND(AVG(next_day_return)::numeric, 2) as avg_ret_1d,
               ROUND(AVG(ret_3d)::numeric, 2) as avg_ret_3d,
               ROUND(AVG(ret_5d)::numeric, 2) as avg_ret_5d,
               ROUND(AVG(ret_10d)::numeric, 2) as avg_ret_10d
        FROM screening_snapshots
        {where}
        GROUP BY trade_date
        ORDER BY trade_date DESC
        LIMIT 90
    """, tuple(params) if params else None)

    by_date = []
    for row in cur.fetchall():
        td, total, wins, r1, r3, r5, r10 = row
        by_date.append({
            "trade_date": str(td),
            "total": total, "wins": wins or 0,
            "win_rate": round(wins / total * 100, 1) if total else 0,
            "avg_ret_1d": r1 or 0,
            "avg_ret_3d": r3 or 0,
            "avg_ret_5d": r5 or 0,
            "avg_ret_10d": r10 or 0,
        })

    # Summary stats
    cur.execute(f"""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE is_win) as wins,
               ROUND(AVG(next_day_return)::numeric, 2) as avg_r1,
               ROUND(AVG(ret_3d)::numeric, 2) as avg_r3,
               ROUND(AVG(ret_5d)::numeric, 2) as avg_r5,
               ROUND(SUM(next_day_return)::numeric, 2) as cum_ret
        FROM screening_snapshots
        {where}
    """, tuple(params) if params else None)
    t = cur.fetchone()
    cur.close()

    total = t[0] or 0
    wins = t[1] or 0
    summary = {
        "total_picks": total,
        "wins": wins,
        "overall_win_rate": round(wins / total * 100, 1) if total else 0,
        "avg_ret_1d": t[2] or 0,
        "avg_ret_3d": t[3] or 0,
        "avg_ret_5d": t[4] or 0,
        "cum_return": t[5] or 0,
        "models": [],
    }

    # Per-model breakdown
    cur2 = conn.cursor()
    cur2.execute("""
        SELECT model_key, COUNT(*), COUNT(*) FILTER (WHERE is_win),
               ROUND(AVG(next_day_return)::numeric, 2)
        FROM screening_snapshots
        WHERE next_day_return IS NOT NULL
        GROUP BY model_key
        ORDER BY COUNT(*) DESC
    """)
    for row in cur2.fetchall():
        mk, cnt, w, avg = row
        summary["models"].append({
            "model_key": mk,
            "total": cnt, "wins": w or 0,
            "win_rate": round(w / cnt * 100, 1) if cnt else 0,
            "avg_ret_1d": avg or 0,
        })
    cur2.close()

    return {"by_date": by_date, "summary": summary}


def get_pick_timeline(pick_id: int) -> dict:
    """获取单个选股的多周期表现时间线."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM screening_snapshots WHERE id = %s", (pick_id,)
    )
    row = cur.fetchone()
    cur.close()
    if not row:
        return {}
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))
