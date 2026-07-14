#!/usr/bin/env python3
"""Register the Token output power chain into staging tables."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any

import psycopg2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = PROJECT_ROOT / "packages" / "kronos-factors" / "configs" / "industry_chain_templates.json"
CHAIN_ID = "ai_token_output_power"


def _load_template() -> dict[str, Any]:
    data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return next(item for item in data.get("templates", []) if item.get("template_id") == CHAIN_ID)


def _registration_rows(as_of_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    template = _load_template()
    nodes: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    previous_node_id: str | None = None
    for layer in sorted(template.get("layers") or [], key=lambda item: int(item.get("order") or 0)):
        layer_id = str(layer.get("layer_id") or "")
        layer_level = f"L{int(layer.get('order') or 0)}"
        node_id = f"{CHAIN_ID}:{layer_level}"
        node = {
            "node_id": node_id,
            "parent_node_id": previous_node_id,
            "layer_level": layer_level,
            "layer_name": str(layer.get("name") or layer_id),
            "display_name": str(layer.get("name") or layer_id),
            "policy_theme_id": "future_industry_core",
            "chain_id": CHAIN_ID,
            "bom_node_id": layer_id,
            "source_table": "industry_chain_templates",
            "source_id": layer_id,
            "keywords": list(layer.get("segments") or []),
            "metadata": {
                "template_id": CHAIN_ID,
                "industry_dimensions": template.get("industry_dimensions") or [],
                "evidence": layer.get("evidence") or [],
                "as_of_date": as_of_date,
            },
        }
        nodes.append(node)
        views.append({
            "view_id": f"{node_id}:value_chain",
            "node_id": node_id,
            "view_type": "value_chain",
            "payload": {
                "chain_id": CHAIN_ID,
                "layer_id": layer_id,
                "segments": list(layer.get("segments") or []),
                "evidence": list(layer.get("evidence") or []),
                "market_layer_separate": True,
                "as_of_date": as_of_date,
            },
            "evidence_ids": [],
        })
        previous_node_id = node_id
    return nodes, views


def _upsert_fake(connection: Any, table: str, key: str, row: dict[str, Any]) -> str | None:
    upsert = getattr(connection, "upsert", None)
    if not callable(upsert):
        return None
    return str(upsert(table, key, row))


def _upsert_real(connection: Any, table: str, row: dict[str, Any]) -> None:
    cur = connection.cursor()
    if table == "supply_chain_hierarchy_nodes":
        cur.execute(
            """
            INSERT INTO supply_chain_hierarchy_nodes (
                node_id, parent_node_id, layer_level, layer_name, display_name,
                policy_theme_id, chain_id, bom_node_id, source_table, source_id,
                keywords, metadata
            ) VALUES (
                %(node_id)s, %(parent_node_id)s, %(layer_level)s, %(layer_name)s,
                %(display_name)s, %(policy_theme_id)s, %(chain_id)s, %(bom_node_id)s,
                %(source_table)s, %(source_id)s, %(keywords)s, %(metadata)s
            )
            ON CONFLICT (node_id) DO UPDATE SET
                parent_node_id = EXCLUDED.parent_node_id,
                layer_name = EXCLUDED.layer_name,
                display_name = EXCLUDED.display_name,
                keywords = EXCLUDED.keywords,
                metadata = EXCLUDED.metadata,
                updated_at = CURRENT_TIMESTAMP
            """,
            {**row, "keywords": json.dumps(row["keywords"]), "metadata": json.dumps(row["metadata"])},
        )
    else:
        cur.execute(
            """
            INSERT INTO supply_chain_deconstruct_views (
                view_id, node_id, view_type, payload, evidence_ids
            ) VALUES (%(view_id)s, %(node_id)s, %(view_type)s, %(payload)s, %(evidence_ids)s)
            ON CONFLICT (view_id) DO UPDATE SET
                payload = EXCLUDED.payload,
                evidence_ids = EXCLUDED.evidence_ids,
                updated_at = CURRENT_TIMESTAMP
            """,
            {**row, "payload": json.dumps(row["payload"]), "evidence_ids": json.dumps(row["evidence_ids"])},
        )


def _pool_counts(connection: Any) -> dict[str, int]:
    counts = {pool: 0 for pool in ("A", "B", "C", "D")}
    rows = getattr(connection, "rows", {})
    if isinstance(rows, dict):
        for (table, _key), row in rows.items():
            if table == "business_tag_token_pool_states":
                pool = str(row.get("pool_code") or "")
                if pool in counts:
                    counts[pool] += 1
        return counts
    cur = connection.cursor()
    cur.execute(
        """
        SELECT pool_code, COUNT(*)
        FROM business_tag_token_pool_states
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM business_tag_token_pool_states)
        GROUP BY pool_code
        """
    )
    for pool, count in cur.fetchall():
        if pool in counts:
            counts[pool] = int(count or 0)
    return counts


def register(
    mode: str = "staging",
    pg_url: str = "postgresql://kronos:kronos@localhost:6432/kronos",
    as_of_date: str | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
    if mode not in {"staging", "production"}:
        raise ValueError("mode must be staging or production")
    if mode == "production" and os.environ.get("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION") != "1":
        raise PermissionError("ALLOW_SUPPLY_CHAIN_PRODUCTION_REGISTRATION=1 is required for production registration")
    effective_date = as_of_date or date.today().isoformat()
    nodes, views = _registration_rows(effective_date)
    owned_connection = connection is None
    if owned_connection:
        connection = psycopg2.connect(pg_url)
    inserted = 0
    updated = 0
    try:
        for row in nodes:
            outcome = _upsert_fake(connection, "supply_chain_hierarchy_nodes", row["node_id"], row)
            if outcome is None:
                _upsert_real(connection, "supply_chain_hierarchy_nodes", row)
                inserted += 1
            elif outcome == "updated":
                updated += 1
            else:
                inserted += 1
        for row in views:
            outcome = _upsert_fake(connection, "supply_chain_deconstruct_views", row["view_id"], row)
            if outcome is None:
                _upsert_real(connection, "supply_chain_deconstruct_views", row)
                inserted += 1
            elif outcome == "updated":
                updated += 1
            else:
                inserted += 1
        if owned_connection:
            connection.commit()
        pool_counts = _pool_counts(connection)
        return {
            "mode": mode,
            "chain_id": CHAIN_ID,
            "as_of_date": effective_date,
            "node_count": len(nodes),
            "view_count": len(views),
            "inserted": inserted,
            "updated": updated,
            "formal_pool_count": pool_counts["A"] + pool_counts["B"] + pool_counts["C"],
            "provisional_pool_count": pool_counts["D"],
            "pool_counts": pool_counts,
        }
    finally:
        if owned_connection and connection is not None:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("staging", "production"), default="staging")
    parser.add_argument("--pg-url", default=os.environ.get("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos"))
    parser.add_argument("--as-of-date", default=None)
    args = parser.parse_args()
    print(json.dumps(register(args.mode, args.pg_url, args.as_of_date), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
