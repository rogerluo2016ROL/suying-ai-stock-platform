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


def stage_rank(stage: str | None) -> int:
    if not stage:
        return 0
    try:
        return int(str(stage)[1:])
    except (TypeError, ValueError, IndexError):
        return 0


def pool_for_business_tag(status: str, revenue_ratio: float | None, commercialization_stage: str, evidence_count: int) -> str:
    if status == "rejected": return "剔除池"
    if status == "verified" and revenue_ratio is not None and stage_rank(commercialization_stage) >= 3 and evidence_count > 0: return "核心池"
    if evidence_count > 0 and stage_rank(commercialization_stage) >= 1: return "进展池"
    return "观察池"


def layer_level_from_bom_level(level: str | None) -> str:
    key = str(level or "").lower()
    if key in {"theme", "policy"}: return "L1"
    if key in {"direction", "sector"}: return "L2"
    if key in {"chain", "industry"}: return "L3"
    if key in {"segment", "process"}: return "L4"
    if key in {"component", "material", "equipment"}: return "L5"
    if key in {"product", "technology", "application"}: return "L6"
    return "L5"


def build_layer_tree(nodes: list[dict]) -> list[dict]:
    node_by_id = {node["layer_node_id"]: dict(node, children=[]) for node in nodes}
    roots = []
    for node in node_by_id.values():
        parent_id = node.get("parent_node_id")
        if parent_id and parent_id in node_by_id: node_by_id[parent_id]["children"].append(node)
        else: roots.append(node)
    order = {f"L{i}": i for i in range(1, 9)}
    def sort_node(item):
        item["children"] = sorted((sort_node(child) for child in item.get("children", [])), key=lambda child: (order.get(child.get("layer_level"), 99), child.get("name") or ""))
        return item
    return sorted((sort_node(root) for root in roots), key=lambda node: (order.get(node.get("layer_level"), 99), node.get("name") or ""))


def fallback_layer_nodes() -> list[dict]:
    payload = load_bom_payload(); nodes = []; theme_names = {}
    for theme in payload.get("themes", []):
        theme_id = str(theme.get("theme_id") or "")
        if not theme_id: continue
        theme_names[theme_id] = str(theme.get("name") or theme_id)
        nodes.append({"layer_node_id": f"L1:{theme_id}", "parent_node_id": None, "layer_level": "L1", "layer_name": "政策主题", "name": theme_names[theme_id], "source_table": "policy_themes", "source_id": theme_id, "keywords": theme.get("keywords") or [], "metadata": {"policy_weight": theme.get("policy_weight")}})
    levels = {str(node.get("node_id") or ""): layer_level_from_bom_level(node.get("level") or node.get("node_type")) for node in payload.get("nodes", [])}
    for node in payload.get("nodes", []):
        node_id = str(node.get("node_id") or ""); theme_id = str(node.get("theme_id") or "")
        if not node_id: continue
        level = layer_level_from_bom_level(node.get("level") or node.get("node_type")); parent = node.get("parent_node_id")
        nodes.append({"layer_node_id": f"{level}:{node_id}", "parent_node_id": f"{levels.get(str(parent), 'L5')}:{parent}" if parent else f"L1:{theme_id}", "layer_level": level, "layer_name": {"L2":"产业方向","L3":"产业链","L4":"环节","L5":"BOM节点","L6":"产品/技术路线"}.get(level,"产业链节点"), "name": str(node.get("name") or node_id), "source_table":"supply_chain_bom_nodes", "source_id":node_id, "keywords":node.get("keywords") or [], "metadata":{"theme_id":theme_id,"theme_name":theme_names.get(theme_id),"chain_id":node.get("chain_id"),"node_type":node.get("node_type"),"level":node.get("level")}})
    return nodes
