import importlib.util
from pathlib import Path


PATH = Path(__file__).resolve().parents[3] / "tools" / "rebuild_ai_token_output_candidates.py"
SPEC = importlib.util.spec_from_file_location("rebuild_token_output", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def source(code, tag, status="verified", **facts):
    return {"mapping_id": f"source-{code}-{tag}", "code": code, "tag_name": tag, "status": status, "confidence": 0.9, "chain_id": "ai_compute", "facts": facts}


def test_rebuild_deduplicates_and_downgrades_cross_chain_rows():
    rows = [source("300308", "高速光模块"), source("300308.SZ", "高速光模块")]
    result = MODULE.build_candidates(rows)
    assert len(result) == 1
    assert result[0]["code"] == "300308"
    assert result[0]["status"] == "candidate"
    assert result[0]["evidence_grade"] == "E0"
    assert result[0]["layer_id"] == "L5"


def test_generic_tags_require_manual_review():
    result = MODULE.build_candidates([source("603881", "云服务")])
    assert result[0]["layer_id"] is None
    assert "broad_tag_requires_review" in result[0]["reason_codes"]
