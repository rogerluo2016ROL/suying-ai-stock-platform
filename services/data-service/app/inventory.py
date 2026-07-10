"""真实数据表库存查询，与任务运行写入量严格分离。"""
from app.sync.pg_writer import PG_URL

TABLES = ("daily_kline", "stocks", "moneyflow", "stk_limit", "daily_basic")

def count_table(table: str) -> int:
    import psycopg2
    from psycopg2.sql import SQL, Identifier
    with psycopg2.connect(PG_URL, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL("SELECT COUNT(*) FROM {}").format(Identifier(table)))
            return int(cur.fetchone()[0])

def table_inventory(table: str) -> dict:
    rows = count_table(table)
    return {"table": table, "rows": rows}

def inventory() -> dict:
    return {"tables": {table: table_inventory(table) for table in TABLES}}
