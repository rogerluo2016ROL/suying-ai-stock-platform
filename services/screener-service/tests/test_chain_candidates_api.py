"""Tests for /chain/candidates endpoint — Phase 3: Candidate screening API.

Tests cover:
- AC-1: GET /chain/candidates returns candidate list
- AC-2: filter parameter supports high_growth/high_profit/high_moat/chokepoint_core/all
- AC-3: resonance_level parameter supports 强启动/启动/关注/观察
- AC-4: Each candidate includes three_factor_scores + resonance summary
- AC-5: Each filter condition returns correct data
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client for screener service."""
    return TestClient(app)


class TestChainCandidatesEndpoint:
    """Test suite for /chain/candidates endpoint."""

    def test_ac1_endpoint_returns_candidates(self, client):
        """AC-1: GET /chain/candidates returns candidate list."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "candidates" in data
        assert "filter" in data
        assert "resonance_level" in data
        assert "total_candidates" in data
        assert "filtered_count" in data
        assert "filter_summary" in data
        assert "resonance_summary" in data
        assert "elapsed" in data

        # Verify candidates is a list
        assert isinstance(data["candidates"], list)

    def test_ac2_filter_high_growth(self, client):
        """AC-2: filter=high_growth returns candidates with performance_yield >= 15."""
        response = client.get("/api/v1/screener/chain/candidates?filter=high_growth&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "high_growth"
        assert data["candidates"] is not None

        # Verify each candidate has performance_yield >= 15 or empty result
        for candidate in data["candidates"]:
            three_factors = candidate.get("three_factor_scores", {})
            perf_yield = three_factors.get("performance_yield", 0)
            # Candidates filtered by high_growth should have perf_yield >= 15
            # (or result could be empty if no candidates match)
            if perf_yield > 0:
                assert perf_yield >= 15.0, f"Candidate {candidate.get('code')} should have perf_yield >= 15"

    def test_ac2_filter_high_profit(self, client):
        """AC-2: filter=high_profit returns candidates with high profitability."""
        response = client.get("/api/v1/screener/chain/candidates?filter=high_profit&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "high_profit"

        # Verify candidates have high profit indicators
        for candidate in data["candidates"]:
            gross_margin = candidate.get("gross_margin", 0)
            dim_scores = candidate.get("dimension_scores", {})
            profit_dim = dim_scores.get("profit", 0)          # 0-10 主阈值
            snap_profit = candidate.get("profit_score", 0)    # 0-100 快照回退阈值
            # High profit: gross_margin >= 50% OR profit_dim >= 10 OR snap_profit >= 75 (回退)
            if gross_margin or profit_dim or snap_profit:
                assert (gross_margin >= 50.0 or profit_dim >= 10.0 or snap_profit >= 75.0), \
                    f"Candidate {candidate.get('code')} should have high profit"

    def test_ac2_filter_high_moat(self, client):
        """AC-2: filter=high_moat returns candidates with moat signals."""
        response = client.get("/api/v1/screener/chain/candidates?filter=high_moat&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "high_moat"

        # Verify candidates have chokepoint/moat indicators
        for candidate in data["candidates"]:
            dim_scores = candidate.get("dimension_scores", {})
            chokepoint_score = dim_scores.get("chokepoint", 0)
            choke_keywords = candidate.get("chokepoint_keywords", [])
            # High moat: chokepoint_score >= 6 OR has keywords
            if chokepoint_score or choke_keywords:
                assert chokepoint_score >= 6.0 or len(choke_keywords) > 0, \
                    f"Candidate {candidate.get('code')} should have high moat"

    def test_ac2_filter_chokepoint_core(self, client):
        """AC-2: filter=chokepoint_core returns candidates classified as 卡脖子核心."""
        response = client.get("/api/v1/screener/chain/candidates?filter=chokepoint_core&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "chokepoint_core"

        # Verify all candidates are chokepoint_core level
        for candidate in data["candidates"]:
            chokepoint_level = candidate.get("chokepoint_level", "")
            assert chokepoint_level == "卡脖子核心", \
                f"Candidate {candidate.get('code')} should be chokepoint_core level"

    def test_ac2_filter_all(self, client):
        """AC-2: filter=all returns all candidates without filtering."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "all"
        # all filter should return the most candidates (up to top_n)
        assert data["filtered_count"] <= data["total_candidates"]

    def test_ac3_resonance_level_qiang_qidong(self, client):
        """AC-3: resonance_level=强启动 returns candidates with 3 factors passing."""
        response = client.get("/api/v1/screener/chain/candidates?resonance_level=强启动&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["resonance_level"] == "强启动"

        # Verify all candidates have resonance_signal = 强启动
        for candidate in data["candidates"]:
            signal = candidate.get("resonance_signal", "")
            assert signal == "强启动", f"Candidate {candidate.get('code')} should have signal 强启动"
            # Strong startup means 3 factors passed
            assert candidate.get("resonance_factors", 0) >= 3

    def test_ac3_resonance_level_qidong(self, client):
        """AC-3: resonance_level=启动 returns candidates with 2 factors passing."""
        response = client.get("/api/v1/screener/chain/candidates?resonance_level=启动&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["resonance_level"] == "启动"

        for candidate in data["candidates"]:
            signal = candidate.get("resonance_signal", "")
            assert signal == "启动", f"Candidate {candidate.get('code')} should have signal 启动"
            assert candidate.get("resonance_factors", 0) == 2

    def test_ac3_resonance_level_guanzhu(self, client):
        """AC-3: resonance_level=关注 returns candidates with 1 factor passing."""
        response = client.get("/api/v1/screener/chain/candidates?resonance_level=关注&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["resonance_level"] == "关注"

        for candidate in data["candidates"]:
            signal = candidate.get("resonance_signal", "")
            assert signal == "关注", f"Candidate {candidate.get('code')} should have signal 关注"
            assert candidate.get("resonance_factors", 0) == 1

    def test_ac3_resonance_level_guancha(self, client):
        """AC-3: resonance_level=观察 returns candidates with 0 factors passing."""
        response = client.get("/api/v1/screener/chain/candidates?resonance_level=观察&top_n=10")

        assert response.status_code == 200
        data = response.json()

        assert data["resonance_level"] == "观察"

        for candidate in data["candidates"]:
            signal = candidate.get("resonance_signal", "")
            assert signal == "观察", f"Candidate {candidate.get('code')} should have signal 观察"
            assert candidate.get("resonance_factors", 0) == 0

    def test_ac4_candidate_has_three_factor_scores(self, client):
        """AC-4: Each candidate includes three_factor_scores."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        for candidate in data["candidates"]:
            assert "three_factor_scores" in candidate, \
                f"Candidate {candidate.get('code')} missing three_factor_scores"

            three_factors = candidate["three_factor_scores"]
            assert "industry_cycle" in three_factors
            assert "policy_intensity" in three_factors
            assert "performance_yield" in three_factors

            # Verify scores are numeric
            assert isinstance(three_factors["industry_cycle"], (int, float))
            assert isinstance(three_factors["policy_intensity"], (int, float))
            assert isinstance(three_factors["performance_yield"], (int, float))

    def test_ac4_candidate_has_resonance_summary(self, client):
        """AC-4: Each candidate includes resonance summary."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        for candidate in data["candidates"]:
            assert "resonance_signal" in candidate, \
                f"Candidate {candidate.get('code')} missing resonance_signal"
            assert "resonance_factors" in candidate, \
                f"Candidate {candidate.get('code')} missing resonance_factors"
            assert "resonance_details" in candidate, \
                f"Candidate {candidate.get('code')} missing resonance_details"

            # Verify resonance_signal is valid
            valid_signals = {"强启动", "启动", "关注", "观察"}
            assert candidate["resonance_signal"] in valid_signals, \
                f"Candidate {candidate.get('code')} has invalid signal: {candidate['resonance_signal']}"

    def test_ac5_combined_filter_and_resonance(self, client):
        """AC-5: Combined filter + resonance_level returns correct intersection."""
        response = client.get(
            "/api/v1/screener/chain/candidates?filter=high_growth&resonance_level=启动&top_n=10"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["filter"] == "high_growth"
        assert data["resonance_level"] == "启动"

        # Verify each candidate matches both criteria
        for candidate in data["candidates"]:
            # Check high_growth filter
            three_factors = candidate.get("three_factor_scores", {})
            perf_yield = three_factors.get("performance_yield", 0)
            if perf_yield > 0:
                assert perf_yield >= 15.0

            # Check resonance_level filter
            signal = candidate.get("resonance_signal", "")
            assert signal == "启动"

    def test_invalid_filter_returns_400(self, client):
        """Invalid filter parameter returns 400 error."""
        response = client.get("/api/v1/screener/chain/candidates?filter=invalid_filter")

        assert response.status_code == 400
        data = response.json()
        assert "Invalid filter" in data.get("detail", "")

    def test_invalid_resonance_level_returns_400(self, client):
        """Invalid resonance_level parameter returns 400 error."""
        response = client.get("/api/v1/screener/chain/candidates?resonance_level=invalid_level")

        assert response.status_code == 400
        data = response.json()
        assert "Invalid resonance_level" in data.get("detail", "")

    def test_filter_summary_included(self, client):
        """Response includes filter_summary with counts for all filter types."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        assert "filter_summary" in data
        filter_summary = data["filter_summary"]

        # Verify all filter types are present
        expected_filters = {"high_growth", "high_profit", "high_moat", "chokepoint_core", "all"}
        assert set(filter_summary.keys()) == expected_filters

        # Verify counts are numeric
        for ft, count in filter_summary.items():
            assert isinstance(count, int)

    def test_resonance_summary_included(self, client):
        """Response includes resonance_summary with counts for all resonance levels."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=5")

        assert response.status_code == 200
        data = response.json()

        assert "resonance_summary" in data
        resonance_summary = data["resonance_summary"]

        # Verify all resonance levels are present
        expected_levels = {"强启动", "启动", "关注", "观察"}
        assert set(resonance_summary.keys()) == expected_levels

        # Verify counts are numeric
        for level, count in resonance_summary.items():
            assert isinstance(count, int)

    def test_candidates_sorted_by_resonance_then_score(self, client):
        """Candidates are sorted by resonance_factors (desc) then score (desc)."""
        response = client.get("/api/v1/screener/chain/candidates?filter=all&top_n=10")

        assert response.status_code == 200
        data = response.json()

        candidates = data["candidates"]
        if len(candidates) < 2:
            return  # Cannot verify sorting with < 2 candidates

        # Verify sorting: resonance_factors desc, then score desc
        for i in range(len(candidates) - 1):
            curr = candidates[i]
            next_c = candidates[i + 1]

            curr_factors = curr.get("resonance_factors", 0)
            next_factors = next_c.get("resonance_factors", 0)

            if curr_factors > next_factors:
                # Higher resonance_factors comes first - correct
                continue
            elif curr_factors == next_factors:
                # Same resonance_factors, check score
                curr_score = curr.get("score", 0)
                next_score = next_c.get("score", 0)
                assert curr_score >= next_score, \
                    f"Same resonance_factors {curr_factors} should sort by score desc"
            else:
                # Lower resonance_factors should not come before higher
                assert False, \
                    f"Candidate {curr.get('code')} (factors={curr_factors}) should not come before " \
                    f"{next_c.get('code')} (factors={next_factors})"

    def test_trade_date_parameter_accepted(self, client):
        """trade_date parameter is accepted and passed through."""
        response = client.get(
            "/api/v1/screener/chain/candidates?filter=all&trade_date=2024-01-15&top_n=5"
        )

        # Accept either 200 (success) or 503 (data not available for that date)
        assert response.status_code in (200, 503)

        if response.status_code == 200:
            data = response.json()
            assert "candidates" in data