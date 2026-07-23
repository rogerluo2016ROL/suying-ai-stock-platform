"""Tests for chain_deconstruct module.

AC verification:
- [AC-1] deconstruct_chain(theme_id, method) returns tree structure
- [AC-2] method='upstream_downstream' returns 5-layer tree
- [AC-3] method='value_chain' returns margin/pricing_power/value_added
- [AC-4] method='competition' returns concentration/leader_share/barrier/threat
- [AC-5] All methods return correct data structure
"""

import copy
import json

import pytest

from kronos_factors.engine.chain_deconstruct import (
    _to_float,
    annotate_competition,
    annotate_value_chain,
    build_bom_tree,
    build_competition_tree,
    build_upstream_downstream_tree,
    build_value_chain_tree,
    deconstruct_chain,
    LAYER_NAMES,
)


# Sample test data simulating chain_nodes table records
SAMPLE_NODES = [
    # Layer 1: 原材料
    {
        "node_id": "silicon",
        "theme_id": "semiconductor",
        "node_name": "硅片",
        "layer": 1,
        "parent_node_id": None,
        "upstream_nodes": [],
        "downstream_nodes": ["wafer_fab"],
        "value_chain": {"margin": 15, "pricing_power": 2, "value_added": 10},
        "competition": {"concentration": 0.8, "leader_share": 60, "barrier": 5, "threat": 2},
    },
    {
        "node_id": "photoresist",
        "theme_id": "semiconductor",
        "node_name": "光刻胶",
        "layer": 1,
        "parent_node_id": None,
        "upstream_nodes": [],
        "downstream_nodes": ["wafer_fab"],
        "value_chain": {"margin": 35, "pricing_power": 4, "value_added": 30},
        "competition": {"concentration": 0.9, "leader_share": 70, "barrier": 5, "threat": 3},
    },
    # Layer 2: 核心零部件
    {
        "node_id": "wafer_fab",
        "theme_id": "semiconductor",
        "node_name": "晶圆制造",
        "layer": 2,
        "parent_node_id": "silicon",
        "upstream_nodes": ["silicon", "photoresist"],
        "downstream_nodes": ["packaging"],
        "value_chain": {"margin": 25, "pricing_power": 3, "value_added": 20},
        "competition": {"concentration": 0.6, "leader_share": 40, "barrier": 4, "threat": 2},
    },
    # Layer 3: 制造
    {
        "node_id": "packaging",
        "theme_id": "semiconductor",
        "node_name": "封装测试",
        "layer": 3,
        "parent_node_id": "wafer_fab",
        "upstream_nodes": ["wafer_fab"],
        "downstream_nodes": ["distributor"],
        "value_chain": {"margin": 10, "pricing_power": 1, "value_added": 5},
        "competition": {"concentration": 0.3, "leader_share": 20, "barrier": 2, "threat": 4},
    },
    # Layer 4: 渠道
    {
        "node_id": "distributor",
        "theme_id": "semiconductor",
        "node_name": "分销渠道",
        "layer": 4,
        "parent_node_id": "packaging",
        "upstream_nodes": ["packaging"],
        "downstream_nodes": ["consumer_electronics"],
        "value_chain": {"margin": 5, "pricing_power": 1, "value_added": 3},
        "competition": {"concentration": 0.2, "leader_share": 15, "barrier": 1, "threat": 3},
    },
    # Layer 5: 终端应用
    {
        "node_id": "consumer_electronics",
        "theme_id": "semiconductor",
        "node_name": "消费电子",
        "layer": 5,
        "parent_node_id": "distributor",
        "upstream_nodes": ["distributor"],
        "downstream_nodes": [],
        "value_chain": {"margin": 20, "pricing_power": 2, "value_added": 15},
        "competition": {"concentration": 0.5, "leader_share": 30, "barrier": 3, "threat": 2},
    },
]


class TestBuildUpstreamDownstreamTree:
    """Tests for build_upstream_downstream_tree function."""

    def test_empty_nodes_returns_empty_tree(self):
        """Empty input should return empty tree structure."""
        result = build_upstream_downstream_tree([])
        assert result["node_id"] == "root"
        assert result["name"] == "空产业链"
        assert result["children"] == []

    def test_returns_tree_with_correct_root(self):
        """Should return tree with root node_id='root'."""
        result = build_upstream_downstream_tree(SAMPLE_NODES)
        assert result["node_id"] == "root"
        assert "children" in result
        assert len(result["children"]) > 0

    def test_tree_contains_5_layers(self):
        """Tree should contain nodes from layers 1-5."""
        result = build_upstream_downstream_tree(SAMPLE_NODES)

        # Collect all layers from tree
        layers = set()
        def collect_layers(node):
            if "layer" in node and node["layer"] is not None:
                layers.add(node["layer"])
            for child in node.get("children", []):
                collect_layers(child)

        collect_layers(result)

        # Should have layers 1-5 (原材料 through 终端应用)
        expected_layers = {1, 2, 3, 4, 5}
        assert layers == expected_layers

    def test_tree_nodes_have_required_fields(self):
        """Each tree node should have node_id, name, layer."""
        result = build_upstream_downstream_tree(SAMPLE_NODES)

        def check_node_fields(node):
            assert "node_id" in node
            assert "name" in node
            if "children" in node and node["children"]:
                for child in node["children"]:
                    check_node_fields(child)

        check_node_fields(result)


class TestBuildValueChainTree:
    """Tests for build_value_chain_tree function."""

    def test_empty_nodes_returns_empty_value_chain(self):
        """Empty input should return empty value_chain."""
        result = build_value_chain_tree([])
        assert result["value_chain"] == {}

    def test_returns_value_chain_data(self):
        """Should return value_chain dict with node metrics."""
        result = build_value_chain_tree(SAMPLE_NODES)

        assert "value_chain" in result
        vc = result["value_chain"]

        # Check silicon node value_chain
        assert "silicon" in vc
        silicon_vc = vc["silicon"]
        assert silicon_vc["margin"] == 15.0
        assert silicon_vc["pricing_power"] == 2.0
        assert silicon_vc["value_added"] == 10.0
        assert "note" in silicon_vc

    def test_value_chain_contains_margin_pricing_power_value_added(self):
        """value_chain should contain margin, pricing_power, value_added."""
        result = build_value_chain_tree(SAMPLE_NODES)
        vc = result["value_chain"]

        # Check all nodes have the required fields
        for node_id, node_vc in vc.items():
            assert "margin" in node_vc
            assert "pricing_power" in node_vc
            assert "value_added" in node_vc
            assert "note" in node_vc

    def test_value_chain_handles_missing_data(self):
        """Should handle nodes with missing value_chain data."""
        nodes_with_missing = [
            {
                "node_id": "test_node",
                "node_name": "测试节点",
                "layer": 1,
                "parent_node_id": None,
                "value_chain": {},  # Empty value_chain
                "competition": {},
            }
        ]
        result = build_value_chain_tree(nodes_with_missing)

        assert "test_node" in result["value_chain"]
        assert result["value_chain"]["test_node"]["margin"] is None
        assert result["value_chain"]["test_node"]["note"] == "无数据"


class TestBuildCompetitionTree:
    """Tests for build_competition_tree function."""

    def test_empty_nodes_returns_empty_competition(self):
        """Empty input should return empty competition."""
        result = build_competition_tree([])
        assert result["competition"] == {}

    def test_returns_competition_data(self):
        """Should return competition dict with node metrics."""
        result = build_competition_tree(SAMPLE_NODES)

        assert "competition" in result
        comp = result["competition"]

        # Check silicon node competition
        assert "silicon" in comp
        silicon_comp = comp["silicon"]
        assert silicon_comp["concentration"] == 0.8
        assert silicon_comp["leader_share"] == 60.0
        assert silicon_comp["barrier"] == 5.0
        assert silicon_comp["threat"] == 2.0
        assert "note" in silicon_comp

    def test_competition_contains_required_fields(self):
        """competition should contain concentration, leader_share, barrier, threat."""
        result = build_competition_tree(SAMPLE_NODES)
        comp = result["competition"]

        # Check all nodes have the required fields
        for node_id, node_comp in comp.items():
            assert "concentration" in node_comp
            assert "leader_share" in node_comp
            assert "barrier" in node_comp
            assert "threat" in node_comp
            assert "note" in node_comp

    def test_competition_handles_missing_data(self):
        """Should handle nodes with missing competition data."""
        nodes_with_missing = [
            {
                "node_id": "test_node",
                "node_name": "测试节点",
                "layer": 1,
                "parent_node_id": None,
                "value_chain": {},
                "competition": {},  # Empty competition
            }
        ]
        result = build_competition_tree(nodes_with_missing)

        assert "test_node" in result["competition"]
        assert result["competition"]["test_node"]["concentration"] is None
        assert result["competition"]["test_node"]["note"] == "无数据"


class TestBuildBomTree:
    """Tests for build_bom_tree function."""

    def test_empty_nodes_returns_empty_bom_layers(self):
        """Empty input should return empty L1-L8 BOM layer coverage."""
        result = build_bom_tree([])

        assert result["node_id"] == "root"
        assert result["children"] == []
        assert set(result["bom_layers"].keys()) == {f"L{i}" for i in range(1, 9)}
        assert all(items == [] for items in result["bom_layers"].values())

    def test_returns_bom_layers_and_paths(self):
        """BOM view should expose L1-L8 layer buckets and node paths."""
        result = build_bom_tree(SAMPLE_NODES)

        assert "bom_layers" in result
        assert "bom_paths" in result
        assert result["bom_layers"]["L1"]
        assert any(path[-1]["node_id"] == "consumer_electronics" for path in result["bom_paths"])

    def test_bom_view_returns_completed_semantic_eight_layer_table(self):
        """BOM view should fill L1-L8 semantic table rows, not placeholder gaps."""
        result = deconstruct_chain(
            "future_industry_core",
            "bom",
            [
                {
                    "node_id": "quantum_core",
                    "theme_id": "future_industry_core",
                    "chain_id": "quantum",
                    "node_name": "量子科技",
                    "layer": 1,
                    "parent_node_id": None,
                    "keywords": ["量子计算", "量子通信", "量子测量"],
                }
            ],
            theme_name="未来产业主攻方向",
        )

        assert result["bom_layers"]["L1"][0]["name"] == "未来产业主攻方向"
        assert result["bom_layers"]["L2"][0]["name"] == "量子科技"
        for layer in ("L3", "L4", "L5", "L6", "L7", "L8"):
            assert result["bom_layers"][layer], f"{layer} should not be empty"

        assert result["bom_table"]
        row = result["bom_table"][0]
        assert row["L1"] == "未来产业主攻方向"
        assert row["L2"] == "量子科技"
        assert "量子计算" in row["L6"]
        assert "业务" in row["L7"]
        assert "客户验证" in row["L8"]
        assert "待拆" not in "".join(str(value) for value in row.values())
        assert "待挂接" not in "".join(str(value) for value in row.values())


class TestDeconstructChain:
    """Tests for deconstruct_chain function."""

    def test_invalid_method_raises_error(self):
        """Invalid method should raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            deconstruct_chain("semiconductor", "invalid_method")
        assert "Invalid method" in str(exc_info.value)

    def test_upstream_downstream_returns_correct_structure(self):
        """[AC-1] [AC-2] upstream_downstream method returns correct tree structure."""
        result = deconstruct_chain("semiconductor", "upstream_downstream", SAMPLE_NODES)

        # Check theme info
        assert result["theme"]["id"] == "semiconductor"
        assert result["view"] == "upstream_downstream"

        # Check tree structure
        assert "tree" in result
        assert result["tree"]["node_id"] == "root"

        # Verify it does NOT include value_chain or competition
        assert "value_chain" not in result
        assert "competition" not in result

    def test_value_chain_returns_correct_structure(self):
        """[AC-3] value_chain method returns margin/pricing_power/value_added."""
        result = deconstruct_chain("semiconductor", "value_chain", SAMPLE_NODES)

        # Check theme info
        assert result["theme"]["id"] == "semiconductor"
        assert result["view"] == "value_chain"

        # Check tree and value_chain
        assert "tree" in result
        assert "value_chain" in result

        # Verify value_chain data structure
        vc = result["value_chain"]
        assert "silicon" in vc
        assert vc["silicon"]["margin"] == 15.0
        assert vc["silicon"]["pricing_power"] == 2.0
        assert vc["silicon"]["value_added"] == 10.0

    def test_competition_returns_correct_structure(self):
        """[AC-4] competition method returns concentration/leader_share/barrier/threat."""
        result = deconstruct_chain("semiconductor", "competition", SAMPLE_NODES)

        # Check theme info
        assert result["theme"]["id"] == "semiconductor"
        assert result["view"] == "competition"

        # Check tree and competition
        assert "tree" in result
        assert "competition" in result

        # Verify competition data structure
        comp = result["competition"]
        assert "silicon" in comp
        assert comp["silicon"]["concentration"] == 0.8
        assert comp["silicon"]["leader_share"] == 60.0
        assert comp["silicon"]["barrier"] == 5.0
        assert comp["silicon"]["threat"] == 2.0

    def test_bom_returns_layered_structure(self):
        """BOM method returns L1-L8 layer coverage and node paths."""
        result = deconstruct_chain("semiconductor", "bom", SAMPLE_NODES)

        assert result["theme"]["id"] == "semiconductor"
        assert result["view"] == "bom"
        assert "tree" in result
        assert "bom_layers" in result
        assert "bom_paths" in result
        assert set(result["bom_layers"].keys()) == {f"L{i}" for i in range(1, 9)}

    def test_empty_nodes_returns_empty_structure(self):
        """[AC-5] Empty nodes returns correct empty structure for each method."""
        for method in ("upstream_downstream", "value_chain", "competition", "bom"):
            result = deconstruct_chain("test", method, [])

            assert result["theme"]["id"] == "test"
            assert result["view"] == method
            assert result["tree"]["node_id"] == "root"
            assert result["tree"]["children"] == []

            if method == "value_chain":
                assert result["value_chain"] == {}
            elif method == "competition":
                assert result["competition"] == {}
            elif method == "bom":
                assert result["bom_layers"] == {f"L{i}": [] for i in range(1, 9)}
                assert result["bom_paths"] == []

    def test_accepts_theme_name_override(self):
        """Should accept theme_name parameter for display."""
        result = deconstruct_chain(
            "semiconductor",
            "upstream_downstream",
            SAMPLE_NODES,
            theme_name="集成电路"
        )

        assert result["theme"]["name"] == "集成电路"


class TestLayerNames:
    """Tests for LAYER_NAMES constant."""

    def test_layer_names_has_5_layers(self):
        """LAYER_NAMES should have entries for layers 1-5."""
        assert len(LAYER_NAMES) == 5
        assert LAYER_NAMES[1] == "原材料"
        assert LAYER_NAMES[2] == "核心零部件"
        assert LAYER_NAMES[3] == "制造"
        assert LAYER_NAMES[4] == "渠道"
        assert LAYER_NAMES[5] == "终端应用"


class TestBomLayerParenting:
    """Tests for round-robin L4-L8 parent mounting (fix: children no longer
    all hang under the first parent item)."""

    NODES = [
        {
            "node_id": "near_memory_computing",
            "theme_id": "future_industry_core",
            "chain_id": "near_memory_computing",
            "node_name": "近存计算",
            "layer": 1,
            "parent_node_id": None,
            "keywords": ["存算一体", "HBM-PIM", "CXL"],
        }
    ]

    def test_l5_children_distributed_across_l4_parents(self):
        result = build_bom_tree(self.NODES, theme_name="未来产业主攻方向")
        layers = result["bom_layers"]
        l5_parents = {item["parent_node_id"] for item in layers["L5"]}
        l4_ids = {item["node_id"] for item in layers["L4"]}
        # 不再全部挂第一个 L4; 且每个父都是真实 L4 节点
        assert len(l5_parents) > 1
        assert l5_parents <= l4_ids

    def test_each_layer_parents_come_from_previous_layer(self):
        result = build_bom_tree(self.NODES, theme_name="未来产业主攻方向")
        layers = result["bom_layers"]
        for child_layer, parent_layer in (("L6", "L5"), ("L7", "L6"), ("L8", "L7")):
            parent_ids = {item["node_id"] for item in layers[parent_layer]}
            child_parents = {item["parent_node_id"] for item in layers[child_layer]}
            assert len(child_parents) > 1, f"{child_layer} 仍全挂单父节点"
            assert child_parents <= parent_ids

    def test_round_robin_covers_all_parents_when_more_children(self):
        result = build_bom_tree(self.NODES, theme_name="未来产业主攻方向")
        layers = result["bom_layers"]
        # 近存计算 profile: L5(13) > L4(6), 轮转后每个 L4 至少有一个 L5 子项
        used = {item["parent_node_id"] for item in layers["L5"]}
        assert used == {item["node_id"] for item in layers["L4"]}

    def test_single_parent_still_works(self):
        nodes = [
            {
                "node_id": "custom_chain",
                "theme_id": "t",
                "node_name": "未知定制链",
                "layer": 1,
                "parent_node_id": None,
                "keywords": [],
            }
        ]
        result = build_bom_tree(nodes, theme_name="t")
        layers = result["bom_layers"]
        assert layers["L5"]
        assert all(item["parent_node_id"] for item in layers["L5"])


class TestCompetitionScale:
    """competition 指标统一 0-100 百分数标度."""

    def test_concentration_label_uses_0_to_100_scale(self):
        nodes = [
            {"node_id": "hi", "node_name": "高集中", "layer": 1, "parent_node_id": None,
             "competition": {"concentration": 80}},
            {"node_id": "mid", "node_name": "中集中", "layer": 1, "parent_node_id": None,
             "competition": {"concentration": 50}},
            {"node_id": "lo", "node_name": "低集中", "layer": 1, "parent_node_id": None,
             "competition": {"concentration": 10}},
        ]
        comp = build_competition_tree(nodes)["competition"]
        assert "高集中度" in comp["hi"]["note"]
        assert "中集中度" in comp["mid"]["note"]
        assert "低集中度" in comp["lo"]["note"]

    def test_leader_share_printed_as_percent_of_0_to_100(self):
        nodes = [
            {"node_id": "n1", "node_name": "龙头", "layer": 1, "parent_node_id": None,
             "competition": {"leader_share": 60}},
        ]
        comp = build_competition_tree(nodes)["competition"]
        assert "龙头份额60%" in comp["n1"]["note"]


class TestTemplateLoading:
    """Template config loading: cached and single source path."""

    def test_load_templates_cached(self):
        from kronos_factors.engine.chain_deconstruct import load_industry_chain_templates
        first = load_industry_chain_templates()
        second = load_industry_chain_templates()
        assert first is second  # lru_cache 命中同一对象

    def test_template_tree_builds(self):
        result = deconstruct_chain("ai", "bom", template="complex_tech")
        assert result["template"]["template_id"] == "complex_tech"
        assert result["tree"]["children"]
        assert result["macro_context"]


class TestTransmissionLayer:
    """传导链 (transmission) 层: 新列优先, 旧 layer 推导兜底, 与钻取链 L1-L8 解耦."""

    def test_legacy_mapping_covers_layers_1_to_5(self):
        from kronos_factors.engine.chain_deconstruct import (
            LEGACY_LAYER_TO_TRANSMISSION,
            TRANSMISSION_LAYER_NAMES,
        )
        assert LEGACY_LAYER_TO_TRANSMISSION == {
            1: "foundation",
            2: "core_product",
            3: "integration",
            4: "supporting",
            5: "commercialization",
        }
        # 所有映射目标都是合法的传导链 layer_id
        assert set(LEGACY_LAYER_TO_TRANSMISSION.values()) <= set(TRANSMISSION_LAYER_NAMES)

    def test_tree_node_derives_transmission_layer_from_legacy_layer(self):
        nodes = [
            {"node_id": "raw", "node_name": "硅片", "layer": 1, "parent_node_id": None},
            {"node_id": "fab", "node_name": "晶圆制造", "layer": 2, "parent_node_id": "raw"},
        ]
        tree = build_upstream_downstream_tree(nodes)
        root = tree["children"][0]
        assert root["layer"] == 1  # 旧字段保留, 向后兼容
        assert root["transmission_layer"] == "foundation"
        assert root["transmission_layer_name"] == "底层支撑层"
        child = root["children"][0]
        assert child["transmission_layer"] == "core_product"

    def test_explicit_transmission_layer_takes_precedence(self):
        nodes = [
            {
                "node_id": "n1",
                "node_name": "液冷",
                "layer": 2,
                "parent_node_id": None,
                "transmission_layer": "infrastructure",
            },
            {"node_id": "n2", "node_name": "未知", "layer": 9, "parent_node_id": None},
        ]
        tree = build_upstream_downstream_tree(nodes)
        by_id = {child["node_id"]: child for child in tree["children"]}
        # 显式值优先于 legacy 推导
        assert by_id["n1"]["transmission_layer"] == "infrastructure"
        assert by_id["n1"]["transmission_layer_name"] == "基础设施层"
        # 无映射的 layer 不输出 transmission_layer 字段
        assert "transmission_layer" not in by_id["n2"]

    def test_template_children_carry_transmission_layer(self):
        result = deconstruct_chain("ai", "bom", template="complex_tech")
        for child in result["tree"]["children"]:
            assert child["transmission_layer"] == child["layer_id"]


# ---------------------------------------------------------------------------
# Golden legacy implementations (重构前的独立树逻辑, 用于逐字段对比)
# ---------------------------------------------------------------------------


def _legacy_build_value_chain_tree(nodes):
    """Pre-refactor build_value_chain_tree logic (kept as golden reference)."""
    if not nodes:
        return {"node_id": "root", "name": "空产业链", "children": [], "value_chain": {}}
    tree = build_upstream_downstream_tree(nodes)
    value_chain_data = {}
    for node in nodes:
        node_id = node.get("node_id")
        vc_raw = node.get("value_chain") or {}
        margin = _to_float(vc_raw.get("margin"))
        pricing_power = _to_float(vc_raw.get("pricing_power"))
        value_added = _to_float(vc_raw.get("value_added"))
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


def _legacy_build_competition_tree(nodes):
    """Pre-refactor build_competition_tree logic (kept as golden reference)."""
    if not nodes:
        return {"node_id": "root", "name": "空产业链", "children": [], "competition": {}}
    tree = build_upstream_downstream_tree(nodes)
    competition_data = {}
    for node in nodes:
        node_id = node.get("node_id")
        comp_raw = node.get("competition") or {}
        concentration = _to_float(comp_raw.get("concentration"))
        leader_share = _to_float(comp_raw.get("leader_share"))
        barrier = _to_float(comp_raw.get("barrier"))
        threat = _to_float(comp_raw.get("threat"))
        note_parts = []
        if concentration is not None:
            cc_label = "高" if concentration >= 70 else ("中" if concentration >= 40 else "低")
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


def _legacy_deconstruct_chain(theme_id, method, nodes, theme_name=None):
    """Pre-refactor deconstruct_chain method-branch logic (golden reference)."""
    if nodes is None:
        nodes = []
    if theme_name and nodes:
        for node in nodes:
            if not node.get("parent_node_id"):
                node["theme_id"] = theme_name
    if method == "bom":
        tree = build_bom_tree(nodes, theme_name=theme_name, theme_id=theme_id)
        return {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "bom_layers": tree.get("bom_layers", {f"L{i}": [] for i in range(1, 9)}),
            "bom_paths": tree.get("bom_paths", []),
            "bom_table": tree.get("bom_table", []),
            "layer_definitions": tree.get("layer_definitions", {}),
        }
    if method == "upstream_downstream":
        tree = build_upstream_downstream_tree(nodes)
        return {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
        }
    if method == "value_chain":
        tree = _legacy_build_value_chain_tree(nodes)
        return {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "value_chain": tree.get("value_chain", {}),
        }
    if method == "competition":
        tree = _legacy_build_competition_tree(nodes)
        return {
            "theme": {"id": theme_id, "name": theme_name or theme_id},
            "view": method,
            "tree": tree,
            "competition": tree.get("competition", {}),
        }
    raise ValueError(method)


class TestAnnotateValueChain:
    """Tests for annotate_value_chain overlay annotator."""

    def test_empty_nodes_returns_empty_dict(self):
        assert annotate_value_chain([]) == {}

    def test_output_matches_tree_embedded_value_chain(self):
        nodes = copy.deepcopy(SAMPLE_NODES)
        annotations = annotate_value_chain(nodes)
        tree = build_value_chain_tree(copy.deepcopy(SAMPLE_NODES))
        assert annotations == tree["value_chain"]

    def test_output_matches_legacy_golden(self):
        nodes = copy.deepcopy(SAMPLE_NODES)
        assert annotate_value_chain(nodes) == _legacy_build_value_chain_tree(
            copy.deepcopy(SAMPLE_NODES)
        )["value_chain"]

    def test_contains_margin_pricing_power_value_added_note(self):
        annotations = annotate_value_chain(copy.deepcopy(SAMPLE_NODES))
        entry = annotations["silicon"]
        assert entry["margin"] == 15.0
        assert entry["pricing_power"] == 2.0
        assert entry["value_added"] == 10.0
        assert "毛利率15%" in entry["note"]


class TestAnnotateCompetition:
    """Tests for annotate_competition overlay annotator."""

    def test_empty_nodes_returns_empty_dict(self):
        assert annotate_competition([]) == {}

    def test_output_matches_tree_embedded_competition(self):
        nodes = copy.deepcopy(SAMPLE_NODES)
        annotations = annotate_competition(nodes)
        tree = build_competition_tree(copy.deepcopy(SAMPLE_NODES))
        assert annotations == tree["competition"]

    def test_output_matches_legacy_golden(self):
        nodes = copy.deepcopy(SAMPLE_NODES)
        assert annotate_competition(nodes) == _legacy_build_competition_tree(
            copy.deepcopy(SAMPLE_NODES)
        )["competition"]

    def test_contains_required_fields(self):
        annotations = annotate_competition(copy.deepcopy(SAMPLE_NODES))
        entry = annotations["wafer_fab"]
        for field in ("concentration", "leader_share", "barrier", "threat", "note"):
            assert field in entry


class TestThinWrapperGolden:
    """build_value_chain_tree / build_competition_tree 薄包装与旧实现逐字段一致。"""

    def test_value_chain_tree_matches_legacy_golden(self):
        current = build_value_chain_tree(copy.deepcopy(SAMPLE_NODES))
        legacy = _legacy_build_value_chain_tree(copy.deepcopy(SAMPLE_NODES))
        assert json.dumps(current, sort_keys=True, ensure_ascii=False) == json.dumps(
            legacy, sort_keys=True, ensure_ascii=False
        )

    def test_competition_tree_matches_legacy_golden(self):
        current = build_competition_tree(copy.deepcopy(SAMPLE_NODES))
        legacy = _legacy_build_competition_tree(copy.deepcopy(SAMPLE_NODES))
        assert json.dumps(current, sort_keys=True, ensure_ascii=False) == json.dumps(
            legacy, sort_keys=True, ensure_ascii=False
        )

    def test_empty_trees_match_legacy_golden(self):
        assert build_value_chain_tree([]) == _legacy_build_value_chain_tree([])
        assert build_competition_tree([]) == _legacy_build_competition_tree([])


class TestDeconstructOverlays:
    """Tests for deconstruct_chain overlays contract."""

    def test_no_overlays_output_byte_identical_to_legacy(self):
        for method in ("bom", "upstream_downstream", "value_chain", "competition"):
            current = deconstruct_chain(
                "semiconductor", method, copy.deepcopy(SAMPLE_NODES), "半导体"
            )
            legacy = _legacy_deconstruct_chain(
                "semiconductor", method, copy.deepcopy(SAMPLE_NODES), "半导体"
            )
            assert "overlays" not in current
            assert json.dumps(current, sort_keys=True, ensure_ascii=False) == json.dumps(
                legacy, sort_keys=True, ensure_ascii=False
            )

    def test_overlays_adds_overlays_key_on_upstream_downstream(self):
        result = deconstruct_chain(
            "semiconductor",
            "upstream_downstream",
            copy.deepcopy(SAMPLE_NODES),
            overlays=["value_chain", "competition"],
        )
        assert result["overlays"]["value_chain"] == annotate_value_chain(
            copy.deepcopy(SAMPLE_NODES)
        )
        assert result["overlays"]["competition"] == annotate_competition(
            copy.deepcopy(SAMPLE_NODES)
        )

    def test_overlays_merge_labels_onto_tree_nodes(self):
        result = deconstruct_chain(
            "semiconductor",
            "upstream_downstream",
            copy.deepcopy(SAMPLE_NODES),
            overlays=["value_chain", "competition"],
        )
        vc = result["overlays"]["value_chain"]
        comp = result["overlays"]["competition"]

        def walk(node):
            nid = node.get("node_id")
            if nid in vc:
                assert node["value_chain"] == vc[nid]
                assert node["competition"] == comp[nid]
            for child in node.get("children") or []:
                walk(child)

        walk(result["tree"])
        # 至少根层节点被合并到标签
        assert "value_chain" in result["tree"]["children"][0]

    def test_overlays_on_bom_method(self):
        result = deconstruct_chain(
            "semiconductor",
            "bom",
            copy.deepcopy(SAMPLE_NODES),
            "半导体",
            overlays=["value_chain"],
        )
        assert "overlays" in result
        assert set(result["overlays"]) == {"value_chain"}
        # bom 既有字段不受影响
        assert "bom_layers" in result and "bom_paths" in result

    def test_overlays_on_value_chain_method_keeps_legacy_key(self):
        result = deconstruct_chain(
            "semiconductor",
            "value_chain",
            copy.deepcopy(SAMPLE_NODES),
            overlays=["competition"],
        )
        # 旧 method 契约不变
        assert "value_chain" in result
        # overlay 额外叠加
        assert set(result["overlays"]) == {"competition"}

    def test_overlays_single_annotation(self):
        result = deconstruct_chain(
            "semiconductor",
            "upstream_downstream",
            copy.deepcopy(SAMPLE_NODES),
            overlays=["value_chain"],
        )
        assert set(result["overlays"]) == {"value_chain"}

    def test_invalid_overlay_raises_error(self):
        with pytest.raises(ValueError, match="Invalid overlays"):
            deconstruct_chain(
                "semiconductor",
                "upstream_downstream",
                copy.deepcopy(SAMPLE_NODES),
                overlays=["unknown_overlay"],
            )

    def test_overlays_none_and_empty_list_leave_output_unchanged(self):
        baseline = deconstruct_chain(
            "semiconductor", "upstream_downstream", copy.deepcopy(SAMPLE_NODES)
        )
        for overlays in (None, []):
            result = deconstruct_chain(
                "semiconductor",
                "upstream_downstream",
                copy.deepcopy(SAMPLE_NODES),
                overlays=overlays,
            )
            assert "overlays" not in result
            assert json.dumps(result, sort_keys=True, ensure_ascii=False) == json.dumps(
                baseline, sort_keys=True, ensure_ascii=False
            )
