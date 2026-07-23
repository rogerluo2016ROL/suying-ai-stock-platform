#!/usr/bin/env python3
"""crowding_drawdown 单测: 纯逻辑 (分位/合成/level) + 端到端 (fake db).

不依赖真实 PG —— 用 fake db 构造已知序列验证.
"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kronos_factors.scorer.crowding_drawdown import (
    rolling_pctile, compute_ci, ci_to_level,
    compute_crowding_risk, COMPONENTS, HIGH_THRESHOLD,
)


# ─────────────────────────────────────────────────────────────────
# rolling_pctile
# ─────────────────────────────────────────────────────────────────
def test_rolling_pctile_highest():
    # history 全小于 current → 分位 = 1.0
    p = rolling_pctile([1, 2, 3, 4], 5)
    assert p is not None
    assert p == 1.0


def test_rolling_pctile_lowest():
    p = rolling_pctile([2, 3, 4, 5], 1)
    assert p is not None
    assert p < 0.1


def test_rolling_pctile_missing_current():
    assert rolling_pctile([1, 2, 3], None) is None
    assert rolling_pctile([1, 2, 3], float("nan")) is None


def test_rolling_pctile_filters_nan_in_history():
    # history 含 None/NaN 应被剔除, 不影响分位
    p = rolling_pctile([1, 2, None, 3, float("nan")], 4)
    assert p == 1.0


def test_rolling_pctile_too_short():
    assert rolling_pctile([], 1) is None  # 只有 current, len<2


# ─────────────────────────────────────────────────────────────────
# compute_ci
# ─────────────────────────────────────────────────────────────────
def test_compute_ci_equal_weight():
    pctls = {"a": 0.8, "b": 0.6, "c": 1.0}
    assert abs(compute_ci(pctls) - (0.8 + 0.6 + 1.0) / 3) < 1e-9


def test_compute_ci_skips_none():
    pctls = {"a": 0.8, "b": None, "c": 1.0, "d": None, "e": 0.6, "f": 0.4}
    # 有效 4 个: 0.8/1.0/0.6/0.4
    assert abs(compute_ci(pctls) - (0.8 + 1.0 + 0.6 + 0.4) / 4) < 1e-9


def test_compute_ci_too_few_returns_none():
    assert compute_ci({"a": 0.5, "b": 0.6}) is None  # < MIN_VALID(3)


# ─────────────────────────────────────────────────────────────────
# ci_to_level
# ─────────────────────────────────────────────────────────────────
def test_level_high():
    assert ci_to_level(0.95) == "high"


def test_level_medium():
    assert ci_to_level(0.85) == "medium"


def test_level_low():
    assert ci_to_level(0.5) == "low"


def test_level_none_ci():
    assert ci_to_level(None) == "low"


def test_level_ret20_extreme_overrides():
    # CI 仅 medium 但 20日涨幅分位极端 → 直接 high
    assert ci_to_level(0.82, ret20_pct=0.97) == "high"


# ─────────────────────────────────────────────────────────────────
# 端到端 (fake db)
# ─────────────────────────────────────────────────────────────────
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    """按 SQL 关键字路由到对应历史序列. rows = list[dict], 支持 r['col']."""

    def __init__(self, basic, kline, mf):
        self.basic, self.kline, self.mf = basic, kline, mf

    def execute(self, sql, params=None):
        s = sql.lower()
        if "daily_basic" in s:
            return _FakeResult(self.basic)
        if "daily_kline" in s:
            return _FakeResult(self.kline)
        if "moneyflow" in s:
            return _FakeResult(self.mf)
        return _FakeResult([])


def _make_rows(n, **fields):
    """生成 n 天 DESC 序列, fields 指定每列的 base 值; 最后一项(index0=当日)可覆盖."""
    base = fields.pop("base", {})
    last = fields.pop("last", {})
    rows = []
    for i in range(n):
        d = {"trade_date": f"2025-01-{i+1:02d}"}
        for k, v in base.items():
            d[k] = v
        rows.append(d)
    for k, v in last.items():
        rows[0][k] = v
    return rows


def test_end_to_end_high_crowding():
    # 当日各成分都是自身历史极端高 → high
    n = 60
    basic = _make_rows(n, base={"turnover_rate_f": 2.0, "volume_ratio": 1.0, "pb": 3.0},
                       last={"turnover_rate_f": 25.0, "volume_ratio": 5.0, "pb": 12.0})
    kline = _make_rows(n, base={"amount": 1e8, "close": 10.0},
                       last={"amount": 5e9, "close": 13.0})  # close 拉高 → ret20 高
    mf = _make_rows(n, base={"net_mf_amount": 1e7}, last={"net_mf_amount": 5e8})
    db = _FakeDB(basic, kline, mf)

    r = compute_crowding_risk(db, "688001", "2025-02-01", lookback=50)
    assert r["level"] == "high"
    assert r["ci_score"] is not None and r["ci_score"] > HIGH_THRESHOLD
    assert "turnover_extreme" in r["flags"]


def test_end_to_end_low_crowding():
    # 当日各成分都低于历史均值 → low
    n = 60
    basic = _make_rows(n, base={"turnover_rate_f": 5.0, "volume_ratio": 2.0, "pb": 6.0},
                       last={"turnover_rate_f": 0.5, "volume_ratio": 0.3, "pb": 1.0})
    kline = _make_rows(n, base={"amount": 1e9, "close": 10.0},
                       last={"amount": 1e7, "close": 8.0})  # close 下行
    mf = _make_rows(n, base={"net_mf_amount": 1e8}, last={"net_mf_amount": -5e7})
    db = _FakeDB(basic, kline, mf)

    r = compute_crowding_risk(db, "688001", "2025-02-01", lookback=50)
    assert r["level"] == "low"
    assert r["ci_score"] is not None and r["ci_score"] < 0.3


def test_end_to_side_data_gap_returns_low_with_none_ci():
    # 全部表空 → CI None, level low, rationale 提示数据不足
    db = _FakeDB([], [], [])
    r = compute_crowding_risk(db, "688999", "2025-02-01", lookback=50)
    assert r["level"] == "low"
    assert r["ci_score"] is None
    assert "数据不足" in r["rationale"]


def test_components_count():
    assert len(COMPONENTS) == 6


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
