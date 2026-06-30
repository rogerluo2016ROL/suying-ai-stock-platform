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


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self, row=None, exc=None):
        self._row = row
        self._exc = exc

    def __enter__(self):
        if self._exc:
            raise self._exc
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql):
        assert "MAX(trade_date)" in sql
        return _FakeResult(self._row)


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
        assert "cb_auction_t0" in mode_ids
        assert "cb_auction_t0_v2" in mode_ids
        assert "cb_auction_t0_v2_1" in mode_ids

    def test_modes_have_required_fields(self, client):
        """Verify each mode has id, name, cycle, style."""
        response = client.get("/api/v1/screener/modes")
        data = response.json()
        for mode in data["modes"]:
            assert "id" in mode
            assert "name" in mode
            assert "cycle" in mode
            assert "style" in mode

    def test_modes_include_latest_trade_date(self, client, monkeypatch):
        """Verify the frontend can initialize its date picker from real data."""
        import app.routers.screener as screener_router

        monkeypatch.setattr(
            screener_router,
            "_query_screener_latest_dates",
            lambda: {
                "daily_kline": "2026-06-26",
                "stk_auction_o": "2026-06-29",
            },
        )

        response = client.get("/api/v1/screener/modes")

        assert response.status_code == 200
        data = response.json()
        assert data["latest_trade_date"] == "2026-06-26"
        assert data["latest_dates"]["stk_auction_o"] == "2026-06-29"
        assert data["data_freshness"]["as_of"] == "2026-06-26"
        assert data["data_freshness"]["source"] == "daily_kline"


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

    def test_cb_auction_t0_mode_is_registered_for_run(self, monkeypatch):
        """Verify cb_auction_t0 is a runnable CB screener mode."""
        import app.routers.screener as screener_router

        class DummyEngine:
            def run(self, trade_date=None, top_n=50):
                return {
                    "trade_date": trade_date or "2026-06-30",
                    "bonds": [
                        {
                            "cb_code": "123001.SZ",
                            "cb_name": "竞价转债",
                            "stk_code": "300001",
                            "stk_name": "触发科技",
                            "theme_score": 117.0,
                        }
                    ],
                }

            def close(self):
                pass

        monkeypatch.setattr(screener_router, "_CB_AUCTION_T0_ENGINE", DummyEngine)

        result = screener_router._run_cb_mode("cb_auction_t0", 5, "2026-06-30")

        assert result["mode"] == "cb_auction_t0"
        assert result["trade_date"] == "2026-06-30"
        assert result["total_picks"] == 1
        assert result["picks"][0]["code"] == "123001.SZ"
        assert result["picks"][0]["name"] == "竞价转债"
        assert result["picks"][0]["source_mode"] == "cb_auction_t0"

    def test_cb_auction_t0_v2_mode_is_registered_for_run(self, monkeypatch):
        """Verify cb_auction_t0_v2 is a runnable CB screener mode."""
        import app.routers.screener as screener_router

        class DummyEngine:
            def run(self, trade_date=None, top_n=50):
                return {
                    "trade_date": trade_date or "2026-06-30",
                    "bonds": [
                        {
                            "cb_code": "123001.SZ",
                            "cb_name": "竞价V2转债",
                            "stk_code": "300001",
                            "stk_name": "触发科技",
                            "theme_score": 117.0,
                            "quality_tier": "A",
                        }
                    ],
                }

            def close(self):
                pass

        monkeypatch.setattr(screener_router, "_CB_AUCTION_T0_V2_ENGINE", DummyEngine)

        result = screener_router._run_cb_mode("cb_auction_t0_v2", 5, "2026-06-30")

        assert result["mode"] == "cb_auction_t0_v2"
        assert result["trade_date"] == "2026-06-30"
        assert result["total_picks"] == 1
        assert result["picks"][0]["code"] == "123001.SZ"
        assert result["picks"][0]["name"] == "竞价V2转债"
        assert result["picks"][0]["quality_tier"] == "A"
        assert result["picks"][0]["source_mode"] == "cb_auction_t0_v2"

    def test_cb_auction_t0_v21_mode_is_registered_for_run(self, monkeypatch):
        """Verify cb_auction_t0_v2_1 is a runnable CB screener mode."""
        import app.routers.screener as screener_router

        class DummyEngine:
            def run(self, trade_date=None, top_n=50):
                return {
                    "trade_date": trade_date or "2026-06-30",
                    "bonds": [
                        {
                            "cb_code": "123001.SZ",
                            "cb_name": "竞价V21转债",
                            "stk_code": "300001",
                            "stk_name": "触发科技",
                            "theme_score": 117.0,
                            "quality_tier": "A",
                        }
                    ],
                    "observation_bonds": [
                        {
                            "cb_code": "123002.SZ",
                            "cb_name": "竞价V21观察转债",
                            "stk_code": "300002",
                            "stk_name": "观察科技",
                            "theme_score": 88.0,
                            "quality_tier": "B",
                            "observation_reason": "非A档观察",
                        }
                    ],
                }

            def close(self):
                pass

        monkeypatch.setattr(screener_router, "_CB_AUCTION_T0_V21_ENGINE", DummyEngine)

        result = screener_router._run_cb_mode("cb_auction_t0_v2_1", 5, "2026-06-30")

        assert result["mode"] == "cb_auction_t0_v2_1"
        assert result["trade_date"] == "2026-06-30"
        assert result["total_picks"] == 1
        assert result["picks"][0]["code"] == "123001.SZ"
        assert result["picks"][0]["name"] == "竞价V21转债"
        assert result["picks"][0]["quality_tier"] == "A"
        assert result["picks"][0]["source_mode"] == "cb_auction_t0_v2_1"
        assert result["observation_picks"][0]["code"] == "123002.SZ"
        assert result["observation_picks"][0]["name"] == "竞价V21观察转债"
        assert result["observation_picks"][0]["source_mode"] == "cb_auction_t0_v2_1"

    def test_resolve_trade_date_replaces_latest_with_pg_date(self, monkeypatch):
        """Verify leader modes never pass the literal latest token into PG date filters."""
        import app.routers.screener as screener_router

        monkeypatch.setattr(
            screener_router,
            "_get_factor_db",
            lambda: _FakeDb({"max": "2026-06-25"}),
        )

        assert screener_router._resolve_trade_date("latest") == "2026-06-25"
        assert screener_router._resolve_trade_date(None) == "2026-06-25"

    def test_resolve_trade_date_fails_fast_when_latest_unavailable(self, monkeypatch):
        """Verify latest resolution raises a clear service error instead of leaking latest into SQL."""
        import app.routers.screener as screener_router

        monkeypatch.setattr(
            screener_router,
            "_get_factor_db",
            lambda: _FakeDb(None),
        )

        with pytest.raises(RuntimeError, match="latest trade date unavailable"):
            screener_router._resolve_trade_date("latest")

    def test_with_screener_contract_uses_resolved_result_trade_date(self, monkeypatch):
        """Verify contract freshness follows the actual date used by the model."""
        import app.routers.screener as screener_router

        monkeypatch.setattr(
            screener_router,
            "_get_factor_db",
            lambda: _FakeDb({"max": "2026-06-26"}),
        )

        payload = {"mode": "short", "picks": []}
        result = screener_router._with_screener_contract(payload, mode="short", trade_date=None)

        assert result["trade_date"] == "2026-06-26"
        assert result["data_freshness"]["as_of"] == "2026-06-26"

    def test_with_screener_contract_uses_mode_data_source(self):
        """Verify freshness source matches the model's real input table."""
        import app.routers.screener as screener_router

        payload = {"mode": "leader_auction", "trade_date": "2026-06-29", "picks": []}
        result = screener_router._with_screener_contract(payload, mode="leader_auction")

        assert result["data_freshness"]["source"] == "stk_auction_o"


class TestHealthEndpoint:
    """Test the health endpoint."""

    def test_health_returns_ok(self, client):
        """Verify health endpoint returns healthy status."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "screener-service"
