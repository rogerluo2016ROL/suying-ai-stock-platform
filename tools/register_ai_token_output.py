#!/usr/bin/env python3
"""Register the AI Token commercial output chain in staging."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

import psycopg2


CHAIN_ID = "ai_token_output"
CONFIG = Path(__file__).resolve().parents[1] / "packages/kronos-factors/configs/industry_chain_templates.json"


def _template() -> dict[str, Any]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return next(row for row in data["templates"] if row.get("template_id") == CHAIN_ID)


def _rows(as_of_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    template = _template()
    nodes, views = [], []
    previous = None
    for layer in sorted(template["layers"], key=lambda row: row["order"]):
        level = f"L{layer['order']}"
        node_id = f"{CHAIN_ID}:{level}"
        nodes.append({
            "node_id": node_id, "parent_node_id": previous, "layer_level": level,
            "layer_name": layer["name"], "display_name": layer["name"],
            "policy_theme_id": "future_industry_core", "chain_id": CHAIN_ID,
            "bom_node_id": layer["layer_id"], "source_table": "industry_chain_templates",
            "source_id": layer["layer_id"], "keywords": layer["segments"],
            "metadata": {"evidence": layer["evidence"], "industry_dimensions": template["industry_dimensions"], "as_of_date": as_of_date},
        })
        views.append({
            "view_id": f"{node_id}:commercial_chain", "node_id": node_id,
            "view_type": "commercial_chain", "payload": {"segments": layer["segments"], "evidence": layer["evidence"], "market_layer_separate": True, "as_of_date": as_of_date},
            "evidence_ids": [],
        })
        previous = node_id
    return nodes, views


def _upsert(connection: Any, table: str, key: str, row: dict[str, Any]) -> str:
    fake = getattr(connection, "upsert", None)
    if callable(fake):
        return str(fake(table, key, row))
    cur = connection.cursor()
    if table == "supply_chain_hierarchy_nodes":
        cur.execute("""
            INSERT INTO supply_chain_hierarchy_nodes
            (node_id,parent_node_id,layer_level,layer_name,display_name,policy_theme_id,chain_id,bom_node_id,source_table,source_id,keywords,metadata)
            VALUES (%(node_id)s,%(parent_node_id)s,%(layer_level)s,%(layer_name)s,%(display_name)s,%(policy_theme_id)s,%(chain_id)s,%(bom_node_id)s,%(source_table)s,%(source_id)s,%(keywords)s::jsonb,%(metadata)s::jsonb)
            ON CONFLICT (node_id) DO UPDATE SET layer_name=EXCLUDED.layer_name,display_name=EXCLUDED.display_name,keywords=EXCLUDED.keywords,metadata=EXCLUDED.metadata,updated_at=CURRENT_TIMESTAMP
        """, {**row, "keywords": json.dumps(row["keywords"], ensure_ascii=False), "metadata": json.dumps(row["metadata"], ensure_ascii=False)})
    else:
        cur.execute("""
            INSERT INTO supply_chain_deconstruct_views (view_id,node_id,view_type,payload,evidence_ids)
            VALUES (%(view_id)s,%(node_id)s,%(view_type)s,%(payload)s::jsonb,%(evidence_ids)s::jsonb)
            ON CONFLICT (view_id) DO UPDATE SET payload=EXCLUDED.payload,evidence_ids=EXCLUDED.evidence_ids,updated_at=CURRENT_TIMESTAMP
        """, {**row, "payload": json.dumps(row["payload"], ensure_ascii=False), "evidence_ids": json.dumps(row["evidence_ids"])})
    return "inserted_or_updated"


def register(mode: str = "staging", pg_url: str = "postgresql://kronos:kronos@localhost:6432/kronos", as_of_date: str | None = None, connection: Any | None = None) -> dict[str, Any]:
    if mode == "production" and os.environ.get("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION") != "1":
        raise PermissionError("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1 is required")
    if mode not in {"staging", "production"}:
        raise ValueError("mode must be staging or production")
    effective_date = as_of_date or date.today().isoformat()
    nodes, views = _rows(effective_date)
    owned = connection is None
    connection = connection or psycopg2.connect(pg_url)
    inserted = updated = 0
    try:
        for table, key_name, rows in (("supply_chain_hierarchy_nodes", "node_id", nodes), ("supply_chain_deconstruct_views", "view_id", views)):
            for row in rows:
                result = _upsert(connection, table, row[key_name], row)
                updated += int(result == "updated")
                inserted += int(result != "updated")
        if owned:
            connection.commit()
        return {"mode": mode, "chain_id": CHAIN_ID, "as_of_date": effective_date, "node_count": len(nodes), "view_count": len(views), "inserted": inserted, "updated": updated}
    finally:
        if owned:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staging", "production"), default="staging")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()
    print(json.dumps(register(args.mode, args.pg_url, args.as_of_date), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
