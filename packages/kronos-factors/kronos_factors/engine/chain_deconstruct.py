"""Industry chain deconstruct module for multi-method chain analysis.

This module implements three deconstruct methods for industry chain analysis:
1. upstream_downstream: 5-layer tree (raw_material → component → manufacture → channel → terminal)
2. value_chain: margin/pricing_power/value_added per node
3. competition: concentration/leader_share/barrier/threat per node

PRD: docs/prd/supply-chain-reconstruct-2026-06-24.md §4.2
Migration: backend/alembic/versions/013_industry_chain_deconstruct.py
"""

from __future__ import annotations

from typing import Any


# Layer definitions for upstream_downstream view
LAYER_NAMES = {
    1: "原材料",
    2: "核心零部件",
    3: "制造",
    4: "渠道",
    5: "终端应用",
}


def _to_float(value: Any, default: float | None = None) -> float | None:
    """Convert value to float with fallback."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_tree_node(
    node: dict[str, Any],
    all_nodes: list[dict[str, Any]],
    include_children: bool = True,
) -> dict[str, Any]:
    """Build a tree node with recursive children."""
    result = {
        "node_id": node.get("node_id"),
        "name": node.get("node_name"),
        "layer": node.get("layer"),
    }

    if include_children:
        children = [
            n for n in all_nodes
            if n.get("parent_node_id") == node.get("node_id")
        ]
        if children:
            result["children"] = [
                _build_tree_node(child, all_nodes, include_children=True)
                for child in sorted(children, key=lambda x: x.get("layer", 0))
            ]

    return result


def build_upstream_downstream_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build 5-layer upstream_downstream tree structure.

    Args:
        nodes: List of chain_nodes records with node_id, node_name, layer, parent_node_id,
               upstream_nodes, downstream_nodes

    Returns:
        Tree structure with root and 5-layer children:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [
                {"node_id": "...", "name": "原材料", "layer": 1, "children": [...]},
                {"node_id": "...", "name": "核心零部件", "layer": 2, "children": [...]},
                ...
            ]
        }
    """
    if not nodes:
        return {"node_id": "root", "name": "空产业链", "children": []}

    # Find root nodes (no parent_node_id)
    root_nodes = [n for n in nodes if not n.get("parent_node_id")]

    if not root_nodes:
        # If all nodes have parent, find the theme-level root by layer=0 or min layer
        min_layer = min(n.get("layer", 1) for n in nodes)
        root_nodes = [n for n in nodes if n.get("layer") == min_layer]

    # Build tree from root nodes
    children = [
        _build_tree_node(root, nodes, include_children=True)
        for root in sorted(root_nodes, key=lambda x: x.get("layer", 0))
    ]

    # Group by layer for clearer structure
    theme_name = nodes[0].get("theme_id", "产业链") if nodes else "产业链"

    return {
        "node_id": "root",
        "name": theme_name,
        "children": children,
    }


def build_value_chain_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build value chain tree with margin/pricing_power/value_added per node.

    Args:
        nodes: List of chain_nodes records with value_chain JSONB field

    Returns:
        Tree structure with value_chain metrics:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [...],
            "value_chain": {
                "<node_id>": {
                    "margin": 15.0,
                    "pricing_power": 2.0,
                    "value_added": 10.0,
                    "note": "毛利率15%, 定价权弱"
                }
            }
        }
    """
    if not nodes:
        return {
            "node_id": "root",
            "name": "空产业链",
            "children": [],
            "value_chain": {},
        }

    # Build base tree structure
    tree = build_upstream_downstream_tree(nodes)

    # Extract value_chain data from each node
    value_chain_data: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_id = node.get("node_id")
        vc_raw = node.get("value_chain") or {}

        # Parse value_chain JSONB
        margin = _to_float(vc_raw.get("margin"))
        pricing_power = _to_float(vc_raw.get("pricing_power"))
        value_added = _to_float(vc_raw.get("value_added"))

        # Build note from available data
        note_parts = []
        if margin is not None:
            note_parts.append(f"毛利率{margin:.0f}%")
        if pricing_power is not None:
            pp_label = "强" if pricing_power >= 4 else ("中" if pricing_power >= 2 else "弱")
            note_parts.append(f"定价权{pp_label}")
        if value_added is not None:
            note_parts.append(f"附加值{value_added:.0f}%")

        value_chain_data[node_id] = {
            "margin": margin,
            "pricing_power": pricing_power,
            "value_added": value_added,
            "note": ", ".join(note_parts) if note_parts else "无数据",
        }

    tree["value_chain"] = value_chain_data
    return tree


def build_competition_tree(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build competition tree with concentration/leader_share/barrier/threat per node.

    Args:
        nodes: List of chain_nodes records with competition JSONB field

    Returns:
        Tree structure with competition metrics:
        {
            "node_id": "root",
            "name": "<theme_name>",
            "children": [...],
            "competition": {
                "<node_id>": {
                    "concentration": 0.8,
                    "leader_share": 0.6,
                    "barrier": 5,
                    "threat": 2,
                    "note": "高集中度, 龙头份额60%, 高壁垒, 低威胁"
                }
            }
        }
    """
    if not nodes:
        return {
            "node_id": "root",
            "name": "空产业链",
            "children": [],
            "competition": {},
        }

    # Build base tree structure
    tree = build_upstream_downstream_tree(nodes)

    # Extract competition data from each node
    competition_data: dict[str, dict[str, Any]] = {}

    for node in nodes:
        node_id = node.get("node_id")
        comp_raw = node.get("competition") or {}

        # Parse competition JSONB
        concentration = _to_float(comp_raw.get("concentration"))
        leader_share = _to_float(comp_raw.get("leader_share"))
        barrier = _to_float(comp_raw.get("barrier"))
        threat = _to_float(comp_raw.get("threat"))

        # Build note from available data
        note_parts = []
        if concentration is not None:
            cc_label = "高" if concentration >= 0.7 else ("中" if concentration >= 0.4 else "低")
            note_parts.append(f"{cc_label}集中度")
        if leader_share is not None:
            note_parts.append(f"龙头份额{leader_share:.0f}%")
        if barrier is not None:
            bar_label = "高" if barrier >= 4 else ("中" if barrier >= 2 else "低")
            note_parts.append(f"{bar_label}壁垒")
        if threat is not None:
            th_label = "高" if threat >= 4 else ("中" if threat >= 2 else "低")
            note_parts.append(f"{th_label}威胁")

        competition_data[node_id] = {
            "concentration": concentration,
            "leader_share": leader_share,
            "barrier": barrier,
            "threat": threat,
            "note": ", ".join(note_parts) if note_parts else "无数据",
        }

    tree["competition"] = competition_data
    return tree


def deconstruct_chain(
    theme_id: str,
    method: str,
    nodes: list[dict[str, Any]] | None = None,
    theme_name: str | None = None,
) -> dict[str, Any]:
    """Deconstruct industry chain using specified method.

    Args:
        theme_id: Industry theme identifier (e.g., "semiconductor", "robot")
        method: Deconstruct method - one of:
            - "upstream_downstream": 5-layer tree structure
            - "value_chain": tree + margin/pricing_power/value_added
            - "competition": tree + concentration/leader_share/barrier/threat
        nodes: List of chain_nodes records (optional, for testing)
        theme_name: Human-readable theme name (optional)

    Returns:
        Deconstruct result with theme info and tree structure:
        {
            "theme": {"id": "...", "name": "..."},
            "view": "<method>",
            "tree": {...},
            "value_chain": {...} | None,
            "competition": {...} | None
        }
    """
    valid_methods = ("upstream_downstream", "value_chain", "competition")
    if method not in valid_methods:
        raise ValueError(f"Invalid method '{method}', must be one of {valid_methods}")

    # Use provided nodes or return empty structure
    if nodes is None:
        nodes = []

    # Add theme_name to nodes if provided (for root node name)
    if theme_name and nodes:
        for node in nodes:
            if not node.get("parent_node_id"):
                node["theme_id"] = theme_name

    # Build tree based on method
    if method == "upstream_downstream":
        tree = build_upstream_downstream_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
        }
    elif method == "value_chain":
        tree = build_value_chain_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "value_chain": tree.get("value_chain", {}),
        }
    elif method == "competition":
        tree = build_competition_tree(nodes)
        result = {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "competition": tree.get("competition", {}),
        }

    return result