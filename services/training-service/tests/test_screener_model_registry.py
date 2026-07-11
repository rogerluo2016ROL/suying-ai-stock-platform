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
