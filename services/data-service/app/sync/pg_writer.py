"""PG 双写 — best-effort, 不影响 SQLite 主路径."""

import logging, os
from datetime import date

logger = logging.getLogger("data-service.pg_writer")

PG_URL = os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


def write_stk_mins(rows: list[tuple]) -> int:
    """批量写入 stk_mins 到 PG (ts_code→code 映射).

    Note: PG stk_mins 暂无 (code,trade_time,freq) 唯一约束,
    会接受重复行。建议空闲时添加约束:
      ALTER TABLE stk_mins ADD CONSTRAINT stk_mins_uniq UNIQUE(code,trade_time,freq);
    """
    if not rows:
        return 0
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL)
        cur = conn.cursor()
        for r in rows:
            ts_code, trade_time, o, h, l, c, vol, amt, freq = r
            code = ts_code.split(".")[0] if "." in str(ts_code) else ts_code
            cur.execute(
                "INSERT INTO stk_mins(code,trade_time,open,high,low,close,volume,amount,freq) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (code, trade_time, o, h, l, c, vol, amt, freq))
        conn.commit(); conn.close()
        return len(rows)
    except Exception as e:
        logger.debug("PG write stk_mins: %s", e)
        return 0


def refresh_materialized_views() -> bool:
    """刷新 PG 物化视图."""
    try:
        import psycopg2
        conn = psycopg2.connect(PG_URL)
        cur = conn.cursor()
        for view in ["mv_today_strong_stocks", "mv_sector_momentum", "mv_top_capital_inflow"]:
            try:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
            except Exception:
                pass  # view may not exist
        conn.commit(); conn.close()
        return True
    except Exception:
        return False


def sync_daily_to_pg(trade_date: str) -> dict:
    """盘后同步核心表到 PG (调用 sync_to_pg.py)."""
    import subprocess
    kronos_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))), "Kronos")
    script = os.path.join(kronos_root, "tools", "sync_to_pg.py")
    if not os.path.exists(script):
        return {"error": "sync_to_pg.py not found"}

    try:
        result = subprocess.run(
            ["python3", script, "--mode", "p0", "--date", trade_date],
            cwd=kronos_root, capture_output=True, text=True, timeout=300)
        ok = result.returncode == 0
        return {"ok": ok, "stdout": result.stdout[-200:]}
    except Exception as e:
        return {"error": str(e)}
