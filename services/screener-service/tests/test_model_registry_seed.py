"""Model registry seed coverage tests."""
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_MODEL_NAMES = {
    "leader_intraday_v7",
    "leader_closing_v3",
    "leader_auction_v4",
    "leader_scalp_v4",
    "leader_afternoon_v1",
    "leader_afternoon_trend_full_v1",
    "short_v1",
    "chokepoint_v1",
    "bi_trend_launch_v13",
    "bi_trend_full_market_v1",
    "supply_chain_bom_v5",
    "cb_auction_v1",
    "cb_auction_t0_v1",
    "cb_auction_t0_v2",
    "cb_auction_t0_v2_1",
    "cb_floor_v1",
    "cb_floor_v3",
    "cb_intraday_v1",
}

REMOVED_MODEL_NAMES = {
    "long",
    "all",
    "long_v1",
    "all_v1",
}


def _seeded_model_names(sql_path: str) -> set[str]:
    sql = (REPO_ROOT / sql_path).read_text(encoding="utf-8")
    return set(re.findall(r"\('([^']+)'", sql))


def test_pgvector_seed_registers_all_current_screener_models():
    seeded = _seeded_model_names("services/sql/pgvector_init.sql")
    assert EXPECTED_MODEL_NAMES <= seeded
    assert seeded.isdisjoint(REMOVED_MODEL_NAMES)


def test_self_learning_seed_registers_all_current_screener_models():
    seeded = _seeded_model_names("services/sql/self_learning_init.sql")
    assert EXPECTED_MODEL_NAMES <= seeded
    assert seeded.isdisjoint(REMOVED_MODEL_NAMES)
