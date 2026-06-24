"""Screener API integration tests — FastAPI TestClient."""
import os
import sys
import pytest
from fastapi.testclient import TestClient

# Setup path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "kronos-factors"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Ensure PG URL is set for tests
os.environ.setdefault("KRONOS_PG_URL", "postgresql://kronos:kronos@localhost:6432/kronos")


@pytest.fixture
def client():
    """Create test client for screener service."""
    from app.main import app
    return TestClient(app)


class TestScreenerModes:
    """Test the modes listing endpoint."""

    def test_list_modes_returns_supported_modes(self, client):
        """Verify /modes returns the supported screening modes."""
        response = client.get("/api/v1/screener/modes")
        assert response.status_code == 200
        data = response.json()
        assert "modes" in data
        assert len(data["modes"]) >= 10

        # Verify key modes are present
        mode_ids = [m["id"] for m in data["modes"]]
        assert len(mode_ids) == len(set(mode_ids))
        assert "leader_scalp" in mode_ids
        assert "leader_afternoon_trend_full" in mode_ids
        assert "short" in mode_ids
        assert "long" not in mode_ids
        assert "all" not in mode_ids
        assert "chokepoint" in mode_ids
        assert "supply_chain" in mode_ids
        assert "bi_trend_launch" in mode_ids
        assert "cb_floor" in mode_ids
        assert "cb_intraday" in mode_ids
        assert "cb_auction" in mode_ids

    def test_modes_have_required_fields(self, client):
        """Verify each mode has id, name, cycle, style."""
        response = client.get("/api/v1/screener/modes")
        data = response.json()
        for mode in data["modes"]:
            assert "id" in mode
            assert "name" in mode
            assert "cycle" in mode
            assert "style" in mode


class TestScreenerRun:
    """Test the screening run endpoint (basic validation)."""

    def test_run_invalid_mode_returns_400(self, client):
        """Verify invalid mode returns 400."""
        response = client.post("/api/v1/screener/run?mode=invalid_mode&top_n=10")
        assert response.status_code == 400
        assert "Unknown mode" in response.json()["detail"]

    def test_run_top_n_out_of_range(self, client):
        """Verify top_n < 5 returns validation error."""
        response = client.post("/api/v1/screener/run?mode=short&top_n=3")
        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.parametrize("mode", ["long", "all"])
    def test_removed_modes_return_400(self, client, mode):
        """Verify removed modes are no longer runnable."""
        response = client.post(f"/api/v1/screener/run?mode={mode}&top_n=5")
        assert response.status_code == 400
        assert "Unknown mode" in response.json()["detail"]

    def test_default_run_mode_remains_supported(self, client):
        """Verify the default run mode still points at a supported model."""
        response = client.post("/api/v1/screener/run?top_n=5")
        # May return 503 if no data, 200 if data available
        assert response.status_code in (200, 503)
        if response.status_code == 200:
            data = response.json()
            assert "picks" in data
            assert "elapsed" in data
            assert isinstance(data["picks"], list)
            assert len(data["picks"]) <= 5


class TestHealthEndpoint:
    """Test the health endpoint."""

    def test_health_returns_ok(self, client):
        """Verify health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "screener-service"
