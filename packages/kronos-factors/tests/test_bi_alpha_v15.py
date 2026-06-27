#!/usr/bin/env python3
"""bi_alpha_v15 横截面多因子引擎单测.

不依赖真实 DB — 用轻量 FakeDB 注入截面数据, 验证打分/分级/风控继承/边界.
"""

import numpy as np
import pytest

from kronos_factors.engine import bi_alpha_v15 as v15


def test_factor_weights_normalized_to_one():
    """ICIR 权重应归一化到和为1, 低换手权重最高."""
    total = sum(v15.FACTOR_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6
    assert v15.FACTOR_WEIGHTS["turnover_inv"] > v15.FACTOR_WEIGHTS["pb_inv"]
    assert v15.FACTOR_WEIGHTS["turnover_inv"] > v15.FACTOR_WEIGHTS["revenue_growth"]


def test_pctile_ranks_monotonic():
    """百分位排名: 高 raw 值 → 高分位 (0-1)."""
    vals = {"a": -5.0, "b": -1.0, "c": 3.0}  # c 最高
    pct = v15._pctile_ranks(vals)
    assert pct["c"] == 1.0
    assert pct["a"] == 0.0
    assert 0 < pct["b"] < 1


def test_pctile_ranks_empty():
    assert v15._pctile_ranks({}) == {}


def test_annual_vol_regime_tiers():
    """波动率分级: normal/high/extreme 对齐阈值."""
    # 低波动: 接近平直
    flat = np.array([10.0 + 0.001 * i for i in range(30)])
    _, regime = v15._annual_vol_regime(flat)
    assert regime == "normal"
    # 极端波动: 大幅震荡
    rng = np.random.default_rng(0)
    wild = 10.0 * np.cumprod(1 + rng.normal(0, 0.12, 30))
    av, regime = v15._annual_vol_regime(wild)
    assert regime in ("high", "extreme")
    assert av > v15.HIGH_VOL_ANNUAL


def test_annual_vol_regime_insufficient_data():
    """数据不足返回默认 normal."""
    av, regime = v15._annual_vol_regime(np.array([10.0, 11.0]))
    assert regime == "normal"


# ── FakeDB: 模拟 PG 截面 ──
class _FakeRow(dict):
    pass


class FakeDB:
    """注入 stocks / daily_basic / financial_indicator / daily_kline 四类查询."""

    def __init__(self, stocks, daily_basic, fin, kline):
        self._stocks = stocks          # [{code,name,industry}]
        self._daily_basic = daily_basic  # {code: {pb,turnover_rate}}
        self._fin = fin                # {code: revenue_growth}
        self._kline = kline            # {code: [close,...]}

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        self._last = (s, params)
        return self

    def fetchall(self):
        s, params = self._last
        if "FROM stocks" in s:
            return [_FakeRow(r) for r in self._stocks]
        if "FROM daily_basic" in s:
            return [_FakeRow({"code": c, "pb": v.get("pb"),
                              "turnover_rate": v.get("turnover_rate")})
                    for c, v in self._daily_basic.items()]
        if "FROM financial_indicator" in s:
            return [_FakeRow({"code": c, "revenue_growth": rg})
                    for c, rg in self._fin.items()]
        if "FROM daily_kline" in s:
            code = params[0]
            closes = self._kline.get(code, [])
            return [_FakeRow({"close": c}) for c in reversed(closes)]
        return []


def _make_hardtech_stocks(n=12):
    # 用硬科技行业关键词命名 industry, 确保 _is_hard_tech_stock 命中
    inds = ["半导体", "AI算力", "光模块", "锂电池", "军工", "机器人"]
    return [{"code": f"{600000+i}", "name": f"股{i}", "industry": inds[i % len(inds)]}
            for i in range(n)]


def test_run_alpha_screening_selects_and_inherits_risk_controls():
    """端到端: 选出票 + 继承 V14 风控字段 (weight/stop_loss/hold_days)."""
    stocks = _make_hardtech_stocks(12)
    codes = [s["code"] for s in stocks]
    # 构造因子: 让 code 越大越优 (低换手=turnover小, 低PB=pb小, 高增长)
    daily_basic = {c: {"pb": 10.0 - i * 0.5, "turnover_rate": 20.0 - i}
                   for i, c in enumerate(codes)}
    fin = {c: float(i * 5) for i, c in enumerate(codes)}  # 增长递增
    # 平稳价格序列 (normal 波动)
    kline = {c: [10.0 + 0.01 * j for j in range(30)] for c in codes}

    db = FakeDB(stocks, daily_basic, fin, kline)
    top, scores, info = v15.run_alpha_screening(db, "2025-06-30", top_n=6)

    assert info["env"] == "alpha_v15"
    assert len(top) > 0
    # 风控字段已注入
    for s in top:
        assert "weight" in s and s["weight"] in (0.3, 0.6, 1.0)
        assert s["stop_loss"] in (-8, -10, -12)
        assert s["hold_days"] == 5
        assert s["take_profit"] == 15
    # 最低分散化: 至少 MIN_DIVERSIFICATION 只 (池足够大时)
    from kronos_factors.engine.params import MIN_DIVERSIFICATION
    assert len(top) >= min(MIN_DIVERSIFICATION, len(scores))


def test_single_factor_only_is_excluded():
    """只有 1 个因子有值的票应被淘汰 (需 >=2 因子防噪音)."""
    stocks = _make_hardtech_stocks(6)
    codes = [s["code"] for s in stocks]
    # 只给 PB, 不给换手/增长 → 每票仅1因子
    daily_basic = {c: {"pb": 5.0 + i, "turnover_rate": None} for i, c in enumerate(codes)}
    fin = {}
    kline = {c: [10.0] * 30 for c in codes}
    db = FakeDB(stocks, daily_basic, fin, kline)
    top, scores, info = v15.run_alpha_screening(db, "2025-06-30", top_n=6)
    # 单因子全被淘汰
    assert len(scores) == 0
    assert top == []


def test_grade_distribution_follows_percentile():
    """grade 按 composite 分位映射: 顶部应有 S, 底部为 C(被淘汰)."""
    stocks = _make_hardtech_stocks(20)
    codes = [s["code"] for s in stocks]
    daily_basic = {c: {"pb": 20.0 - i, "turnover_rate": 30.0 - i}
                   for i, c in enumerate(codes)}
    fin = {c: float(i) for i, c in enumerate(codes)}
    kline = {c: [10.0 + 0.01 * j for j in range(30)] for c in codes}
    db = FakeDB(stocks, daily_basic, fin, kline)
    top, scores, info = v15.run_alpha_screening(db, "2025-06-30", top_n=20)
    grades = {s["grade"] for s in scores}
    # 分位制下应同时存在高低分级
    assert "S" in grades
    assert any(g in grades for g in ("B", "C"))
