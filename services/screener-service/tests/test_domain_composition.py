"""Structural contract for the screener domain composition root."""

from app.domains import router as domains_router
from app.domains.candidates import router as candidates_router
from app.domains.screening import router as screening_router
from app.domains.supply_chain import router as supply_chain_router


def test_composition_root_includes_each_business_domain_once():
    root_paths = {route.path for route in domains_router.router.routes}
    candidate_paths = {route.path for route in candidates_router.router.routes}
    screening_paths = {route.path for route in screening_router.router.routes}
    supply_chain_paths = {route.path for route in supply_chain_router.router.routes}
    assert candidate_paths
    assert screening_paths
    assert supply_chain_paths
    assert candidate_paths.isdisjoint(screening_paths | supply_chain_paths)
    assert screening_paths.isdisjoint(supply_chain_paths)
    assert candidate_paths | screening_paths | supply_chain_paths <= root_paths


def test_composition_root_exposes_all_domain_paths():
    paths = {route.path for route in domains_router.router.routes}
    expected = {
        "/api/v1/screener/modes",
        "/api/v1/screener/run",
        "/api/v1/screener/watchlist",
        "/api/v1/screener/supply-chain/layers",
        "/api/v1/screener/supply-chain/token-output-power",
        "/api/v1/screener/supply-chain/token-output-power/{mapping_id}",
    }
    assert expected <= paths
