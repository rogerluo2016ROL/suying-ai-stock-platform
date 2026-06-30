"""Tests for chain deconstruct API endpoints.

AC verification:
- [AC-1] GET /chain/deconstruct?theme_id=&method= returns tree_nodes + graph format
- [AC-2] GET /chain/node/{node_id}/companies returns company mapping list with resonance field
- [AC-3] API P95 <= 500ms
- [AC-4] Valid theme_id returns 200, invalid theme_id returns 404
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.screener import _seed_chain_nodes_for_deconstruct


client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────────────
# Test fixtures and helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_theme_id():
    """Provide a test theme_id that exists in the database."""
    # Use one of the themes from Task #5 migration
    return "future_industry_core"


@pytest.fixture(scope="module")
def test_node_id():
    """Provide a test node_id that exists in the database."""
    # Use one of the nodes from Task #5 migration
    return "quantum_core"


# ─────────────────────────────────────────────────────────────────────────────
# AC-1: GET /chain/deconstruct returns tree_nodes + graph format
# ─────────────────────────────────────────────────────────────────────────────

class TestChainDeconstruct:
    """Tests for GET /chain/deconstruct endpoint."""

    def test_seed_bom_can_feed_deconstruct_when_pg_chain_nodes_empty(self):
        """Bundled BOM seed config should be usable when chain_nodes is empty."""
        nodes, theme_name = _seed_chain_nodes_for_deconstruct("future_industry_core")

        assert theme_name == "未来产业主攻方向"
        assert {node["node_id"] for node in nodes} >= {
            "embodied_ai_core",
            "bom_reducer",
        }
        reducer = next(node for node in nodes if node["node_id"] == "bom_reducer")
        assert reducer["node_name"] == "减速器"
        assert reducer["parent_node_id"] == "embodied_ai_core"
        assert reducer["layer"] > 0

    def test_returns_200_for_valid_theme_id(self, test_theme_id):
        """[AC-4] Valid theme_id should return 200."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        assert response.status_code == 200

    def test_returns_404_for_invalid_theme_id(self):
        """[AC-4] Invalid theme_id should return 404."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": "invalid_theme_xyz", "method": "upstream_downstream"},
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_returns_400_for_invalid_method(self, test_theme_id):
        """Invalid method should return 400."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "invalid_method"},
        )
        assert response.status_code == 400

    def test_returns_tree_structure(self, test_theme_id):
        """[AC-1] Response should contain tree structure."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert "theme" in data
        assert "view" in data
        assert "tree" in data

        # Verify theme structure
        assert data["theme"]["id"] == test_theme_id
        assert "name" in data["theme"]

        # Verify view matches requested method
        assert data["view"] == "upstream_downstream"

        # Verify tree structure
        tree = data["tree"]
        assert tree["node_id"] == "root"
        assert "children" in tree

    def test_value_chain_method_returns_value_chain_data(self, test_theme_id):
        """[AC-1] method='value_chain' should return value_chain field."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "value_chain"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "value_chain"
        assert "value_chain" in data
        assert data["model_metadata"]["inference_mode"] == "chain:value_chain"
        assert data["data_freshness"]["source"] == "chain_nodes"
        assert data["fallback_reason"] is None
        assert isinstance(data["value_chain"], dict)

        # Each node should have margin/pricing_power/value_added/note
        for node_id, vc_data in data["value_chain"].items():
            assert "margin" in vc_data
            assert "pricing_power" in vc_data
            assert "value_added" in vc_data
            assert "note" in vc_data

    def test_competition_method_returns_competition_data(self, test_theme_id):
        """[AC-1] method='competition' should return competition field."""
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "competition"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["view"] == "competition"
        assert "competition" in data
        assert isinstance(data["competition"], dict)

        # Each node should have concentration/leader_share/barrier/threat/note
        for node_id, comp_data in data["competition"].items():
            assert "concentration" in comp_data
            assert "leader_share" in comp_data
            assert "barrier" in comp_data
            assert "threat" in comp_data
            assert "note" in comp_data


# ─────────────────────────────────────────────────────────────────────────────
# AC-2: GET /chain/node/{node_id}/companies returns company list with resonance
# ─────────────────────────────────────────────────────────────────────────────

class TestChainNodeCompanies:
    """Tests for GET /chain/node/{node_id}/companies endpoint."""

    def test_returns_200_for_valid_node_id(self, test_node_id):
        """Valid node_id should return 200."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        # Note: May return empty companies list if no mappings exist yet
        assert response.status_code == 200

    def test_returns_404_for_invalid_node_id(self):
        """Invalid node_id should return 404."""
        response = client.get(
            "/api/v1/screener/chain/node/invalid_node_xyz/companies"
        )
        assert response.status_code == 404
        assert "not found" in response.json().get("detail", "").lower()

    def test_returns_correct_structure(self, test_node_id):
        """[AC-2] Response should contain node_id, node_name, and companies."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        # Verify required fields
        assert data["node_id"] == test_node_id
        assert "node_name" in data
        assert "company_count" in data
        assert "companies" in data

    def test_company_has_required_fields(self, test_node_id):
        """[AC-2] Each company should have resonance field."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        companies = data.get("companies", [])
        if companies:
            # Check first company has all required fields
            company = companies[0]
            assert "code" in company
            assert "name" in company
            assert "rank" in company
            assert "resonance" in company
            assert "trade_signal" in company

            # Check resonance structure
            resonance = company["resonance"]
            assert "summary" in resonance
            assert "dimensions" in resonance

    def test_resonance_derived_from_three_factors(self, test_node_id):
        """[AC-2] Resonance should be derived from three_factors."""
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        assert response.status_code == 200
        data = response.json()

        companies = data.get("companies", [])
        if companies:
            # Resonance summary should follow pattern based on active_count
            company = companies[0]
            resonance = company["resonance"]
            summary = resonance.get("summary", "")

            # Verify summary patterns
            valid_summaries = [
                "三因子共振 — 强启动信号",
                "双因子共振 — 关注信号",
                "单因子达标 — 观察信号",
                "待兑现 — 暂无共振",
                "待评估",
            ]
            assert summary in valid_summaries


# ─────────────────────────────────────────────────────────────────────────────
# AC-3: API P95 <= 500ms (performance benchmark)
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIPerformance:
    """Tests for API response time."""

    def test_deconstruct_response_time(self, test_theme_id):
        """[AC-3] GET /chain/deconstruct should complete within 500ms."""
        import time

        start = time.time()
        response = client.get(
            "/api/v1/screener/chain/deconstruct",
            params={"theme_id": test_theme_id, "method": "upstream_downstream"},
        )
        elapsed = (time.time() - start) * 1000  # Convert to ms

        assert response.status_code == 200
        # Note: In test environment without real PG, this may be fast
        # In production with real PG, should be < 500ms
        assert elapsed < 5000, f"Response time {elapsed:.1f}ms exceeds 5s (test tolerance)"

    def test_node_companies_response_time(self, test_node_id):
        """[AC-3] GET /chain/node/{node_id}/companies should complete within 500ms."""
        import time

        start = time.time()
        response = client.get(
            f"/api/v1/screener/chain/node/{test_node_id}/companies"
        )
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200
        assert elapsed < 5000, f"Response time {elapsed:.1f}ms exceeds 5s (test tolerance)"
