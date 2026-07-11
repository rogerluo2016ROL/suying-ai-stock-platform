from pathlib import Path

from app.domains.supply_chain import service


def test_supply_chain_annotations_import_on_python_311():
    source = Path(service.__file__).read_text(encoding="utf-8")
    assert "from typing import Any, Optional" in source


def test_data_readiness_always_returns_contract(monkeypatch):
    def unavailable():
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(service.repository, "connect", unavailable)
    result = service.data_readiness()
    assert result["version"] == "supply-chain-v2-readiness"
    assert result["status"] == "degraded"
    assert set(result["layer_coverage"]) == {f"L{i}" for i in range(1, 9)}


def test_l8_inference_builds_all_eight_layers():
    path = service._build_inferred_l1_l8_path({
        "chain_id": "ai_compute",
        "node_id": "ai_compute_hardware",
        "product_name": "光模块",
    })
    assert [item["layer"] for item in path] == [f"L{i}" for i in range(1, 9)]
    assert len(service._l8_dimension_payloads()) == 7
