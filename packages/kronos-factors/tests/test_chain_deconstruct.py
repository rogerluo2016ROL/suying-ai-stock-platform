"""Tests for chain_deconstruct module.

AC verification:
- [AC-1] deconstruct_chain(theme_id, method) returns tree structure
- [AC-2] method='upstream_downstream' returns 5-layer tree
- [AC-3] method='value_chain' returns margin/pricing_power/value_added
- [AC-4] method='competition' returns concentration/leader_share/barrier/threat
- [AC-5] All methods return correct data structure
"""

import pytest

from kronos_factors.engine.chain_deconstruct import (
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
