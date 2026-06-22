"""M14: score_fundamental 去硬编码 000001 单测（AC-2）.

audit-model-2026-06-22 §M14：_build_features_from_kline 对每只股票算特征时
`fund = score_fundamental("000001")` 永远传深发展代码 → fund_score 对全部样本
是常数，对模型无信息量。修复：传当前股票 sym。

测试分两层：
1. 契约：_build_features_from_kline 签名含 sym 参数，调用 score_fundamental(sym)。
2. 行为：不同 sym → 不同 fund_score（不再恒常数）。
"""
import inspect

import sys
import os
_SVC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SVC)

from app.training_engine import _build_features_from_kline  # noqa: E402


def _make_kline(n=130):
    import pandas as pd
    import numpy as np
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    close = 10 + np.cumsum(np.random.RandomState(0).randn(n) * 0.1)
    return pd.DataFrame({
        "open": close, "high": close + 0.2, "low": close - 0.2,
        "close": close, "vol": 1e6, "amt": 1e7,
    }, index=idx)


def test_build_features_signature_accepts_sym():
    sig = inspect.signature(_build_features_from_kline)
    assert "sym" in sig.parameters, (
        "_build_features_from_kline 必须接受 sym 参数（M14: 去硬编码 000001）"
    )


def test_build_features_passes_sym_to_score_fundamental(monkeypatch):
    """sym 必须透传到 score_fundamental，不再写死 000001."""
    import pandas as pd
    import app.training_engine as te

    seen_codes = []

    real_call = _build_features_from_kline  # capture

    # 用 fake scoring 函数捕获 score_fundamental 实际收到的 code
    fake_mod = type(te)  # placeholder

    # 直接 monkeypatch _build_features_from_kline 内部 import 的符号：
    # 它在函数体内 `from webui.services.screener_service import score_fundamental`
    # 等，因此注入一个 fake webui.services 模块到 sys.modules。
    import types

    def make_fake_score_fundamental():
        def score_fundamental(code):
            seen_codes.append(code)
            # 不同 code 给不同分（否则 fund_score 仍恒常数）
            return hash(code) % 100 / 10.0
        return score_fundamental

    webui = types.ModuleType("webui")
    services = types.ModuleType("webui.services")
    screener_service = types.ModuleType("webui.services.screener_service")
    advanced_models = types.ModuleType("webui.services.advanced_models")

    screener_service.score_five_factor = lambda df: {
        "score": 20, "momentum": 5, "volume_factor": 5,
        "technical": 5, "quality": 5, "risk": 5,
    }
    screener_service.score_fundamental = make_fake_score_fundamental()

    def _stub_score(name):
        def _f(df):
            return {"score": 5.0}
        return _f

    for name in ["score_money_flow", "score_mean_reversion",
                 "score_trend_strength", "score_reversal", "score_liquidity"]:
        setattr(advanced_models, name, _stub_score(name))

    webui.services = services
    services.screener_service = screener_service
    services.advanced_models = advanced_models

    monkeypatch.setitem(sys.modules, "webui", webui)
    monkeypatch.setitem(sys.modules, "webui.services", services)
    monkeypatch.setitem(sys.modules, "webui.services.screener_service", screener_service)
    monkeypatch.setitem(sys.modules, "webui.services.advanced_models", advanced_models)

    df = _make_kline(130)
    # 调用两次，传不同 sym
    _build_features_from_kline(df, sym="000001")
    _build_features_from_kline(df, sym="600519")

    assert "000001" in seen_codes, f"score_fundamental 应收到 000001, 实际 seen={seen_codes}"
    assert "600519" in seen_codes, f"score_fundamental 应收到 600519, 实际 seen={seen_codes}"
    assert "000001" in seen_codes and "600519" in seen_codes


def test_fund_score_varies_across_symbols(monkeypatch):
    """两个 sym 的 fund_score 列应不同（不再恒常数）."""
    import types
    import pandas as pd

    webui = types.ModuleType("webui")
    services = types.ModuleType("webui.services")
    screener_service = types.ModuleType("webui.services.screener_service")
    advanced_models = types.ModuleType("webui.services.advanced_models")

    screener_service.score_five_factor = lambda df: {
        "score": 20, "momentum": 5, "volume_factor": 5,
        "technical": 5, "quality": 5, "risk": 5,
    }
    screener_service.score_fundamental = lambda code: {
        "000001": 7.0, "600519": 3.0,
    }.get(code, 5.0)

    def _stub(df):
        return {"score": 5.0}
    for name in ["score_money_flow", "score_mean_reversion",
                 "score_trend_strength", "score_reversal", "score_liquidity"]:
        setattr(advanced_models, name, _stub)

    webui.services = services
    services.screener_service = screener_service
    services.advanced_models = advanced_models
    monkeypatch.setitem(sys.modules, "webui", webui)
    monkeypatch.setitem(sys.modules, "webui.services", services)
    monkeypatch.setitem(sys.modules, "webui.services.screener_service", screener_service)
    monkeypatch.setitem(sys.modules, "webui.services.advanced_models", advanced_models)

    df = _make_kline(130)
    out_a = _build_features_from_kline(df, sym="000001")
    out_b = _build_features_from_kline(df, sym="600519")
    assert len(out_a) > 0 and len(out_b) > 0
    fund_a = out_a["fund_score"].iloc[0]
    fund_b = out_b["fund_score"].iloc[0]
    assert fund_a != fund_b, (
        f"fund_score 应随 sym 变化，000001={fund_a} vs 600519={fund_b}（M14: 不再恒常数）"
    )
