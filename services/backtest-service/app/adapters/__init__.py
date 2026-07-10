"""Observed-evidence backtest adapter registry."""

from .registry import BACKTEST_ADAPTERS, get_adapter

__all__ = ["BACKTEST_ADAPTERS", "get_adapter"]
