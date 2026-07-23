"""数据访问工具：因子库连接、交易日解析、PG 小助手（从 service.py 拆出，零行为变化）。"""

import json
import logging
from typing import Any, Optional

from app.domains.supply_chain import repository as supply_chain_repository
from app.domains.supply_chain import service as supply_chain_service

logger = logging.getLogger("screener.routes")


def _load_supply_chain_bom_payload() -> dict:
    """Load BOM seed config and enrich it for read-only API responses."""
    return supply_chain_service.load_bom_payload()


def _seed_chain_nodes_for_deconstruct(theme_id: str) -> tuple[list[dict[str, Any]], str | None]:
    """Return BOM seed nodes in the shape expected by chain_deconstruct."""
    payload = _load_supply_chain_bom_payload()
    themes = payload.get("themes", [])
    theme = next((item for item in themes if item.get("theme_id") == theme_id), None)
    if not theme:
        return [], None

    level_order = {
        "theme": 0,
        "chain": 1,
        "industry": 1,
        "component": 2,
        "material": 2,
        "equipment": 3,
        "application": 4,
    }

    nodes = []
    for node in payload.get("nodes", []):
        if node.get("theme_id") != theme_id:
            continue
        level = str(node.get("level") or node.get("node_type") or "").lower()
        nodes.append({
            "node_id": str(node.get("node_id") or ""),
            "theme_id": str(node.get("theme_id") or ""),
            "chain_id": str(node.get("chain_id") or ""),
            "node_name": str(node.get("name") or node.get("node_name") or ""),
            "layer": level_order.get(level, 1),
            "parent_node_id": node.get("parent_node_id") or None,
            "keywords": node.get("keywords") or [],
            "node_type": node.get("node_type") or level,
            "source_level": node.get("level"),
            "upstream_nodes": node.get("upstream_nodes") or [],
            "downstream_nodes": node.get("downstream_nodes") or [],
            "value_chain": node.get("value_chain") or {},
            "competition": node.get("competition") or {},
        })
    return nodes, str(theme.get("name") or theme_id)


def _json_or_default(value, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


def _row_get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return round(float(value), 4)
    except (TypeError, ValueError):
        return default


def _pg_connect():
    return supply_chain_repository.connect()


def _pg_table_exists(cur, table_name: str) -> bool:
    return supply_chain_repository.table_exists(cur, table_name)


def _pg_column_exists(cur, table_name: str, column_name: str) -> bool:
    return supply_chain_repository.column_exists(cur, table_name, column_name)


def _pg_count(cur, table_name: str) -> int:
    return supply_chain_repository.count(cur, table_name)


def _pg_distinct_count(cur, table_name: str, column_name: str) -> int:
    return supply_chain_repository.distinct_count(cur, table_name, column_name)


def _pg_nonempty_text_count(cur, table_name: str, column_name: str, min_length: int = 20) -> int:
    return supply_chain_repository.nonempty_text_count(cur, table_name, column_name, min_length)


def _status_from_rows(rows: int, *, ready: int, partial: int = 1) -> str:
    return supply_chain_repository.status_from_rows(rows, ready=ready, partial=partial)
