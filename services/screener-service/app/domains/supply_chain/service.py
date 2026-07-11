"""Supply-chain domain services."""


def load_bom_payload() -> dict:
    """Load and enrich the policy BOM seed for API and screening consumers."""
    from kronos_factors.engine.supply_chain_bom import load_bom_config

    cfg = load_bom_config()
    themes = cfg.get("themes", [])
    nodes = cfg.get("nodes", [])
    edges = cfg.get("edges", [])
    theme_by_id = {theme.get("theme_id"): theme for theme in themes}
    children_by_parent: dict = {}
    for node in nodes:
        parent = node.get("parent_node_id")
        if parent:
            children_by_parent.setdefault(parent, []).append(node.get("node_id"))

    enriched_nodes = []
    for node in nodes:
        theme = theme_by_id.get(node.get("theme_id"), {})
        enriched = dict(node)
        enriched["policy_theme"] = theme.get("name", "")
        enriched["bom_path"] = [value for value in (theme.get("name"), node.get("name")) if value]
        enriched["child_node_ids"] = children_by_parent.get(node.get("node_id"), [])
        enriched["companies"] = []
        enriched_nodes.append(enriched)

    node_counts: dict = {}
    for node in enriched_nodes:
        node_counts[node.get("theme_id")] = node_counts.get(node.get("theme_id"), 0) + 1
    enriched_themes = []
    for theme in themes:
        enriched = dict(theme)
        enriched["node_count"] = node_counts.get(theme.get("theme_id"), 0)
        enriched["matrix"] = {
            "policy_weight": theme.get("policy_weight", 1.0),
            "high_growth": None, "high_profit": None, "high_moat": None,
        }
        enriched_themes.append(enriched)
    return {"version": cfg.get("version", "4.0"), "source": cfg.get("source", ""), "themes": enriched_themes, "nodes": enriched_nodes, "edges": edges}


def themes_payload() -> dict:
    payload = load_bom_payload()
    return {key: payload[key] for key in ("version", "source", "themes")}


def bom_payload() -> dict:
    payload = load_bom_payload()
    return {key: payload[key] for key in ("version", "source", "themes", "nodes", "edges")}
