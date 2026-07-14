"""PostgreSQL read boundary for supply-chain domain queries."""

import os
from psycopg2 import sql


def connect():
    import psycopg2
    return psycopg2.connect(os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"), connect_timeout=5)


def table_exists(cur, table_name: str) -> bool:
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)", (table_name,))
    return bool(cur.fetchone()[0])


def column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name=%s AND column_name=%s)", (table_name, column_name))
    return bool(cur.fetchone()[0])


def count(cur, table_name: str) -> int:
    if not table_exists(cur, table_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table_name)))
    return int(cur.fetchone()[0] or 0)


def distinct_count(cur, table_name: str, column_name: str) -> int:
    if not table_exists(cur, table_name) or not column_exists(cur, table_name, column_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(DISTINCT {}) FROM {}").format(sql.Identifier(column_name), sql.Identifier(table_name)))
    return int(cur.fetchone()[0] or 0)


def nonempty_text_count(cur, table_name: str, column_name: str, min_length: int = 20) -> int:
    if not table_exists(cur, table_name) or not column_exists(cur, table_name, column_name): return 0
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {} WHERE {} IS NOT NULL AND length({}::text) > %s").format(sql.Identifier(table_name), sql.Identifier(column_name), sql.Identifier(column_name)), (min_length,))
    return int(cur.fetchone()[0] or 0)


def status_from_rows(rows: int, *, ready: int, partial: int = 1) -> str:
    if rows >= ready: return "ready"
    if rows >= partial: return "partial"
    return "missing"


def _fetch_token_output_power_rows(
    cur,
    top_n: int,
    pool_codes: tuple[str, ...],
    pool_code: str | None = None,
    trade_date: str | None = None,
) -> list[dict]:
    if not table_exists(cur, "business_tag_token_pool_states"):
        return []
    if not table_exists(cur, "business_tag_mapping"):
        return []
    clauses = ["m.chain_id = %s", "COALESCE(m.status, '') NOT IN ('rejected', 'disabled')"]
    params: list = ["ai_token_output_power"]
    if pool_code:
        clauses.append("ps.pool_code = %s")
        params.append(pool_code)
    else:
        placeholders = ", ".join(["%s"] * len(pool_codes))
        clauses.append(f"ps.pool_code IN ({placeholders})")
        params.extend(pool_codes)
    if trade_date:
        clauses.append("ps.as_of_date <= %s::date")
        params.append(trade_date)
    params.append(max(1, min(int(top_n or 50), 200)))
    capacity_join = "LEFT JOIN business_tag_token_output_capacity_snapshots cs ON cs.mapping_id = ps.mapping_id AND cs.as_of_date = ps.as_of_date"
    sql_text = f"""
        SELECT
            ps.mapping_id,
            m.code,
            m.chain_id,
            m.node_id,
            m.tag_name,
            m.status AS mapping_status,
            ps.evidence_grade,
            ps.pool_code,
            ps.authenticity_score,
            ps.commercialization_score,
            ps.industrial_attractiveness_score,
            ps.coverage_ratio,
            ps.reason_codes,
            ps.next_validation_node,
            ps.next_validation_date,
            ps.review_status,
            ps.as_of_date,
            cs.snapshot_id,
            cs.model_profile,
            cs.hardware_type,
            cs.precision,
            cs.batch_mode,
            cs.billable_tokens,
            cs.cost_per_million_tokens,
            cs.calculation_status
        FROM business_tag_token_pool_states ps
        JOIN business_tag_mapping m ON m.mapping_id = ps.mapping_id
        {capacity_join}
        WHERE {' AND '.join(clauses)}
        ORDER BY ps.evidence_grade DESC, ps.industrial_attractiveness_score DESC NULLS LAST,
                 ps.as_of_date DESC, ps.created_at DESC
        LIMIT %s
    """
    cur.execute(sql_text, tuple(params))
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_token_output_power_snapshot(
    cur=None,
    top_n: int = 50,
    pool_code: str | None = None,
    trade_date: str | None = None,
) -> list[dict]:
    """Read formal A/B/C Token output candidates from the latest snapshots."""

    if cur is not None:
        return _fetch_token_output_power_rows(cur, top_n, ("A", "B", "C"), pool_code, trade_date)
    with connect() as pg:
        return _fetch_token_output_power_rows(pg.cursor(), top_n, ("A", "B", "C"), pool_code, trade_date)


def fetch_token_output_power_provisional_snapshot(
    cur=None,
    top_n: int = 50,
    pool_code: str | None = None,
    trade_date: str | None = None,
) -> list[dict]:
    """Read D-pool provisional Token output candidates."""

    if cur is not None:
        return _fetch_token_output_power_rows(cur, top_n, ("D",), pool_code, trade_date)
    with connect() as pg:
        return _fetch_token_output_power_rows(pg.cursor(), top_n, ("D",), pool_code, trade_date)


def _fetch_token_mapping_detail(cur, mapping_id: str) -> dict:
    if not table_exists(cur, "business_tag_mapping"):
        return {}
    cur.execute(
        """
        SELECT mapping_id, code, chain_id, node_id, tag_name, l1_l8_path,
               confidence, status, evidence_ids
        FROM business_tag_mapping
        WHERE mapping_id = %s
          AND COALESCE(status, '') NOT IN ('rejected', 'disabled')
        """,
        (mapping_id,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    columns = [desc[0] for desc in cur.description]
    payload = dict(zip(columns, row))
    payload["mapping_id"] = str(payload.get("mapping_id") or mapping_id)
    payload["evidence_chain"] = []
    payload["capacity_snapshots"] = []
    payload["dimension_scores"] = []
    payload["pool_states"] = []
    payload["pool_transitions"] = []
    payload["market_layer"] = {"separate_from_industry_evidence": True, "snapshots": []}

    if table_exists(cur, "business_tag_token_output_power_evidence"):
        cur.execute(
            "SELECT * FROM business_tag_token_output_power_evidence WHERE mapping_id = %s ORDER BY as_of_date DESC, created_at DESC",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["evidence_chain"] = [dict(zip(names, item)) for item in cur.fetchall()]
    if table_exists(cur, "business_tag_token_output_capacity_snapshots"):
        cur.execute(
            "SELECT * FROM business_tag_token_output_capacity_snapshots WHERE mapping_id = %s ORDER BY as_of_date DESC, created_at DESC",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["capacity_snapshots"] = [dict(zip(names, item)) for item in cur.fetchall()]
    if table_exists(cur, "business_tag_token_dimension_scores"):
        cur.execute(
            "SELECT * FROM business_tag_token_dimension_scores WHERE mapping_id = %s ORDER BY as_of_date DESC, dimension_id",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["dimension_scores"] = [dict(zip(names, item)) for item in cur.fetchall()]
    if table_exists(cur, "business_tag_token_pool_states"):
        cur.execute(
            "SELECT * FROM business_tag_token_pool_states WHERE mapping_id = %s ORDER BY as_of_date DESC, created_at DESC",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["pool_states"] = [dict(zip(names, item)) for item in cur.fetchall()]
    if table_exists(cur, "business_tag_token_pool_transitions"):
        cur.execute(
            "SELECT * FROM business_tag_token_pool_transitions WHERE mapping_id = %s ORDER BY transition_date DESC, created_at DESC",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["pool_transitions"] = [dict(zip(names, item)) for item in cur.fetchall()]
    if table_exists(cur, "business_tag_token_market_snapshots"):
        cur.execute(
            "SELECT * FROM business_tag_token_market_snapshots WHERE mapping_id = %s ORDER BY trade_date DESC, created_at DESC",
            (mapping_id,),
        )
        names = [desc[0] for desc in cur.description]
        payload["market_layer"]["snapshots"] = [dict(zip(names, item)) for item in cur.fetchall()]
    return payload


def fetch_token_output_power_mapping(cur=None, mapping_id: str = "") -> dict:
    """Return one mapping and its complete Token evidence trace."""

    if cur is not None:
        return _fetch_token_mapping_detail(cur, mapping_id)
    with connect() as pg:
        return _fetch_token_mapping_detail(pg.cursor(), mapping_id)
