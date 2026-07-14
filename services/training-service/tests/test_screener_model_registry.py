"""Training-service contracts for registry-only screener models."""

import sys
import types

import pytest
from pydantic import ValidationError


database_stub = types.ModuleType("app.database")


async def _unused_get_db():
    yield None


database_stub.get_db = _unused_get_db
database_stub.AsyncSessionLocal = None
sys.modules.setdefault("app.database", database_stub)

deps_stub = types.ModuleType("app.deps")
deps_stub.require_role = lambda *roles: (lambda: {"role": "admin"})
sys.modules.setdefault("app.deps", deps_stub)

from app.routes import _build_truthful_comparison
from app.schemas import ModelType, TrainingParams


def test_training_registry_accepts_screener_model_type():
    assert ModelType("screener") is ModelType.SCREENER


def test_training_params_reject_screener_registry_type():
    with pytest.raises(ValidationError):
        TrainingParams(model_type=ModelType.SCREENER)


def test_model_comparison_never_fills_missing_performance_metrics():
    comparisons, verdict, recommendation = _build_truthful_comparison({}, None)

    assert comparisons == []
    assert verdict == "insufficient_evidence"
    assert "缺少真实回测指标" in recommendation


def test_model_comparison_treats_less_negative_drawdown_as_better():
    old_metrics = {
        "ic": 0.05,
        "icir": 0.7,
        "sharpe": 1.5,
        "max_drawdown": -0.20,
        "annual_return": 0.25,
        "win_rate": 0.55,
        "profit_loss_ratio": 1.6,
    }
    new_metrics = {**old_metrics, "max_drawdown": -0.10}

    comparisons, _, _ = _build_truthful_comparison(new_metrics, old_metrics)
    drawdown = next(
        item for item in comparisons if item.metric == "max_drawdown"
    )

    assert drawdown.delta == 0.1
    assert drawdown.better is True
