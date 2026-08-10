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

def table_preview(table: str, limit: int) -> dict:
    """预览指定表前 N 行。调用方必须先按 TABLES 白名单校验 table。"""
    import psycopg2
    from psycopg2.sql import SQL, Identifier
    with psycopg2.connect(PG_URL, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = %s"
                " ORDER BY ordinal_position",
                (table,),
            )
            columns = [{"name": name, "type": dtype} for name, dtype in cur.fetchall()]
            cur.execute(SQL("SELECT COUNT(*) FROM {}").format(Identifier(table)))
            total = int(cur.fetchone()[0])
            cur.execute(
                SQL("SELECT * FROM {} LIMIT %s").format(Identifier(table)),
                (limit,),
            )
            names = [desc[0] for desc in cur.description]
            rows = [dict(zip(names, row)) for row in cur.fetchall()]
    return {"table": table, "columns": columns, "rows": rows, "limit": limit, "total": total}

def inventory() -> dict:
    return {"tables": {table: table_inventory(table) for table in TABLES}}
