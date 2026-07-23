import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[3] / "tools" / "seed_ai_token_output_power_candidates.py"
SPEC = importlib.util.spec_from_file_location("seed_token_candidates", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_classify_layer_uses_specific_hardware_before_generic_software():
    assert MODULE.classify_layer("高速光模块") == ("L4", "核心算力硬件")
    assert MODULE.classify_layer("数据中心/智算中心业务") == ("L7", "电力与智算基础设施")
    assert MODULE.classify_layer("基础软件/算力调度软件业务") == ("L5", "算力集群与调度")


def test_build_path_is_complete_and_marks_candidate_layer():
    path = MODULE.build_path("L4", "核心算力硬件", "Token出口候选：高速光模块")
    assert [item["level"] for item in path] == [f"L{i}" for i in range(1, 9)]
    assert path[3]["source"] == "cross_chain_candidate"
    assert path[3]["name"] == "Token出口候选：高速光模块"
