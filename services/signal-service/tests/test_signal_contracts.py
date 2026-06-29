import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import routes


def test_signal_contract_wraps_model_metadata_freshness_and_fallback():
    df = pd.DataFrame({"trade_date": ["2026-06-20", "2026-06-21"], "close": [210.0, 218.5]})

    result = routes._with_signal_contract(
        {"code": "300750", "signal": {"level": "BUY", "score": 72.0}},
        mode="analyze",
        data=df,
        fallback_reason=None,
    )

    assert result["model_metadata"] == {
        "name": "signal-six-dimension-v2",
        "version": "signal-v2.0",
        "provider": "signal-service",
        "inference_mode": "analyze",
    }
    assert result["data_freshness"]["status"] == "fresh"
    assert result["data_freshness"]["as_of"] == "2026-06-21"
    assert result["fallback_reason"] is None


def test_signal_levels_endpoint_includes_contract_fields():
    result = asyncio.run(routes.signal_levels())

    assert result["model_metadata"]["name"] == "signal-six-dimension-v2"
    assert result["data_freshness"]["source"] == "signal.rules"
    assert result["fallback_reason"] is None
