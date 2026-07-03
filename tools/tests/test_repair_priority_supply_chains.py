import importlib.util
import sys
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "repair_priority_supply_chains.py"
_SPEC = importlib.util.spec_from_file_location("repair_priority_supply_chains", _SCRIPT_PATH)
module = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = module
_SPEC.loader.exec_module(module)


def test_normalize_code_removes_exchange_suffix():
    assert module.normalize_code("300699.SZ") == "300699"
    assert module.normalize_code("688083.SH") == "688083"
    assert module.normalize_code(" 002050 ") == "002050"


def test_build_l1_l8_path_is_structured():
    cfg = module.CHAIN_CONFIGS["future_materials"]
    node = cfg.nodes[0]

    path = module.build_l1_l8_path(cfg, node)

    assert path[0]["level"] == "L1"
    assert path[1]["name"] == "未来材料"
    assert path[4]["level"] == "L5"
    assert path[-1]["level"] == "L8"


def test_new_mapping_rows_do_not_invent_business_segment_id():
    cfg = module.CHAIN_CONFIGS["future_materials"]
    candidate = module.build_candidate_from_hits(
        cfg,
        "300699",
        [module.SourceHit("300699", "光威复材", "profile", None, "公司资料", "碳纤维复合材料", 2.5, ["碳纤维", "复合材料"])],
    )

    row = module.mapping_row_for_candidate(cfg, candidate)

    assert row["business_segment_id"] is None
    assert row["node_id"].startswith("REPAIR-L5-")


def test_candidate_prefers_stronger_source_and_keyword_hits():
    cfg = module.CHAIN_CONFIGS["industrial_software"]
    hits = [
        module.SourceHit("300496", "中科创达", "research", "2026-01-01", "工业软件点评", "公司布局工业软件", 1.5, ["工业软件"]),
        module.SourceHit("300496", "中科创达", "announcement", "2026-06-01", "公告", "工业操作系统和边缘控制平台", 3.0, ["操作系统", "边缘控制"]),
    ]

    candidate = module.build_candidate_from_hits(cfg, "300496", hits)

    assert candidate is not None
    assert candidate.code == "300496"
    assert candidate.node.tag_name == "工业操作系统/边缘控制"
    assert candidate.score > 5
    assert candidate.status == "candidate"


def test_rank_candidates_filters_weak_single_research_hit():
    cfg = module.CHAIN_CONFIGS["future_materials"]
    weak = module.build_candidate_from_hits(
        cfg,
        "000001",
        [module.SourceHit("000001", "平安银行", "research", "2026-01-01", "材料行业", "未来材料行业概览", 1.5, ["未来材料"])],
    )
    strong = module.build_candidate_from_hits(
        cfg,
        "300699",
        [module.SourceHit("300699", "光威复材", "profile", None, "公司资料", "碳纤维复合材料", 2.5, ["碳纤维", "复合材料"])],
    )

    ranked = module.rank_candidates([item for item in [weak, strong] if item])

    assert [item.code for item in ranked] == ["300699"]


def test_rank_candidates_filters_invalid_code_and_broad_research_only_hit():
    cfg = module.CHAIN_CONFIGS["embodied_intelligence"]
    invalid = module.build_candidate_from_hits(
        cfg,
        "nan",
        [module.SourceHit("nan", "", "announcement", "2026-01-01", "公告", "人形机器人", 3.0, ["人形机器人"])],
    )
    broad = module.build_candidate_from_hits(
        cfg,
        "600000",
        [module.SourceHit("600000", "浦发银行", "research", "2026-01-01", "人形机器人行业点评", "市场关注人形机器人", 1.5, ["人形机器人"])],
    )

    ranked = module.rank_candidates([item for item in [invalid, broad] if item])

    assert ranked == []
