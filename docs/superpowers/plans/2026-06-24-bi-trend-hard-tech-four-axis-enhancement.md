# Bi Trend Hard Tech Four-Axis Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen the 毕师傅趋势启动硬核科技 screener across startup quality, ignition power, hard-tech conviction, and explanation output.

**Architecture:** Keep the existing `BiTrendLaunchEngine.run -> run_bi_screening -> _score_bi_trend_arrays` path. Add four helper functions in `bi_trend_launch.py`, then call them from `_score_bi_trend_arrays` so existing API consumers keep working while receiving richer fields.

**Tech Stack:** Python, numpy, pytest, existing `kronos_factors` package.

## Global Constraints

- Do not rewrite `run_bi_screening` or split `bi_trend_launch.py` in this pass.
- Do not modify the sell decision tree.
- Do not introduce new third-party dependencies.
- Do not add new database schema or extra per-stock database queries.
- Preserve existing returned fields such as `total_score`, `grade`, `signal`, `hard_tech_track`, `chokepoint_score`, `checklist_score`, and `ignition_bonus`.
- Use TDD: write each failing test before production code.
- Keep sample-based tuning out of comments and code.

---

## File Structure

- Modify: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
  - Add `_score_hard_tech_conviction`, `_score_startup_quality`, `_score_ignition_power`, and `_build_bi_trend_explanation`.
  - Integrate those helpers into `_score_bi_trend_arrays`.
- Create: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`
  - Cover helper behavior and the new return fields.
- Leave unchanged: `services/screener-service/app/routers/screener.py`
  - The current API path already calls `BiTrendLaunchEngine` with `hard_tech_only=True`.

---

### Task 1: Add Failing Tests For Hard-Tech Conviction And Explanation Shape

**Files:**
- Create: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`
- Modify: none
- Test: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`

**Interfaces:**
- Consumes:
  - `_score_hard_tech_conviction(industry: str, hard_tech_track: str = "", chokepoint_score: int = 0, peer_count: int | None = None) -> dict`
  - `_build_bi_trend_explanation(factor_breakdown: dict, quality_flags: list[str], risk_flags: list[str], power_flags: list[str], hard_tech: dict) -> dict`
- Produces:
  - Tests that fail until both helper functions exist and return stable keys.

- [ ] **Step 1: Write the failing tests**

Add this file:

```python
"""Tests for Bi trend launch four-axis enhancement."""

import numpy as np


def _trend_arrays(n=80):
    closes = np.linspace(10.0, 13.0, n)
    closes[-6:] = [12.5, 12.2, 11.9, 12.05, 12.25, 12.45]
    highs = closes * 1.02
    lows = closes * 0.98
    volumes = np.full(n, 1_000_000.0)
    volumes[-6] = 2_500_000.0
    volumes[-3:] = [650_000.0, 620_000.0, 680_000.0]
    return closes, highs, lows, volumes


def test_hard_tech_conviction_marks_core_ai_compute_track():
    from kronos_factors.engine.bi_trend_launch import _score_hard_tech_conviction

    result = _score_hard_tech_conviction(
        industry="CPO光模块与AI算力设备",
        hard_tech_track="AI算力",
        chokepoint_score=1,
        peer_count=6,
    )

    assert result["track"] == "AI算力"
    assert result["tier"] == "core"
    assert result["score_adj"] >= 5
    assert "光模块" in result["matched_keywords"]
    assert result["chokepoint_level"] == "oligopoly"
    assert "AI算力" in result["conviction_reason"]


def test_hard_tech_conviction_keeps_broad_match_low_conviction():
    from kronos_factors.engine.bi_trend_launch import _score_hard_tech_conviction

    result = _score_hard_tech_conviction(
        industry="电子制造",
        hard_tech_track="硬科技",
        chokepoint_score=0,
        peer_count=30,
    )

    assert result["tier"] == "broad"
    assert result["score_adj"] <= 2
    assert result["chokepoint_level"] == "normal"


def test_scored_pick_contains_explanation_fields():
    from kronos_factors.engine.bi_trend_launch import _score_bi_trend_arrays

    closes, highs, lows, volumes = _trend_arrays()
    result = _score_bi_trend_arrays(
        closes,
        highs,
        lows,
        volumes,
        code="688001",
        name="硬核科技",
        industry="CPO光模块与AI算力设备",
        sector_change=1.2,
        hard_tech_track="AI算力",
        chokepoint_score=1,
        peer_count=6,
    )

    assert result is not None
    assert "factor_breakdown" in result
    assert "entry_reason" in result
    assert "risk_flags" in result
    assert "quality_flags" in result
    assert "hard_tech" in result
    assert result["hard_tech"]["tier"] == "core"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v
```

Expected: FAIL because `_score_hard_tech_conviction` does not exist or `_score_bi_trend_arrays` does not accept `peer_count`.

---

### Task 2: Implement Hard-Tech Conviction And Explanation Fields

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
- Test: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`

**Interfaces:**
- Consumes:
  - Existing `HARD_TECH_INDUSTRY_KW`
  - Existing `_score_bi_trend_arrays` scoring function
- Produces:
  - `_score_hard_tech_conviction(industry: str, hard_tech_track: str = "", chokepoint_score: int = 0, peer_count: int | None = None) -> dict`
  - `_build_bi_trend_explanation(factor_breakdown: dict, quality_flags: list[str], risk_flags: list[str], power_flags: list[str], hard_tech: dict) -> dict`
  - `_score_bi_trend_arrays(closes, highs, lows, volumes, code=None, name=None, industry=None, sector_change=0, hard_tech_track="", chokepoint_score=0, peer_count=None) -> dict | None`

- [ ] **Step 1: Add minimal helper implementation**

Add helpers above `_score_bi_trend_arrays`:

```python
def _score_hard_tech_conviction(industry: str, hard_tech_track: str = "",
                                chokepoint_score: int = 0,
                                peer_count: int | None = None) -> dict:
    text = industry or ""
    matched = [kw for kw in HARD_TECH_INDUSTRY_KW if kw and kw in text]
    track = hard_tech_track or _get_hard_tech_track(text)
    core_tracks = {"AI算力", "半导体", "机器人", "低空经济", "信创国产", "工业母机"}
    strategic_tracks = {"锂电储能", "新材料", "军工", "通信", "医药生物", "显示面板"}
    tier = "core" if track in core_tracks else ("strategic" if track in strategic_tracks else "broad")
    base = {"core": 4, "strategic": 2, "broad": 1}.get(tier, 0)
    scarcity = min(2, max(0, int(chokepoint_score or 0)))
    score_adj = min(6, base + scarcity)
    chokepoint_level = "normal"
    if peer_count is not None and peer_count <= 3:
        chokepoint_level = "scarce"
    elif peer_count is not None and peer_count <= 8:
        chokepoint_level = "oligopoly"
    return {
        "score_adj": score_adj,
        "track": track or "",
        "tier": tier,
        "matched_keywords": matched,
        "conviction_reason": f"{track or '硬科技'}{tier}赛道",
        "chokepoint_level": chokepoint_level,
        "peer_count": peer_count,
    }


def _build_bi_trend_explanation(factor_breakdown: dict, quality_flags: list[str],
                                risk_flags: list[str], power_flags: list[str],
                                hard_tech: dict) -> dict:
    reasons = []
    if power_flags:
        reasons.append("启动信号: " + "、".join(power_flags[:3]))
    if hard_tech.get("track"):
        reasons.append(f"硬科技: {hard_tech['track']}({hard_tech.get('tier', 'broad')})")
    if risk_flags:
        reasons.append("风险: " + "、".join(risk_flags[:3]))
    return {
        "factor_breakdown": factor_breakdown,
        "entry_reason": "；".join(reasons) if reasons else "趋势启动候选",
        "quality_flags": quality_flags,
        "risk_flags": risk_flags,
        "hard_tech": hard_tech,
    }
```

Use deterministic keyword matching. Core tracks are `AI算力`, `半导体`, `机器人`, `低空经济`, `信创国产`, and `工业母机`. Strategic tracks are `锂电储能`, `新材料`, `军工`, `通信`, `医药生物`, and `显示面板`. Unknown hard-tech matches use `broad`.

- [ ] **Step 2: Integrate helpers into `_score_bi_trend_arrays`**

Update the signature:

```python
def _score_bi_trend_arrays(closes, highs, lows, volumes, code=None, name=None,
                          industry=None, sector_change=0, hard_tech_track="",
                          chokepoint_score=0, peer_count=None):
```

Replace the old hard-tech score calculation with the helper output:

```python
hard_tech = _score_hard_tech_conviction(
    industry or "",
    hard_tech_track=hard_tech_track,
    chokepoint_score=chokepoint_score,
    peer_count=peer_count,
)
ht_score = min(6, hard_tech["score_adj"])
cp_score = min(2, chokepoint_score)
```

Add `factor_breakdown`, `entry_reason`, `quality_flags`, `risk_flags`, and `hard_tech` to the return dict.

- [ ] **Step 3: Pass `peer_count` from `run_bi_screening`**

Inside `run_bi_screening`, where `peer_count` already gets computed for chokepoint scoring, pass it into `_score_bi_trend_arrays`.

- [ ] **Step 4: Run Task 1 tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v
```

Expected: PASS for the first three tests.

---

### Task 3: Add Failing Tests For Startup Quality And Ignition Power

**Files:**
- Modify: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`
- Test: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`

**Interfaces:**
- Consumes:
  - `_score_startup_quality(regime: str = "neutral", daily_gain: float = 0.0, two_day_up: bool = False, wr_now: float = 50.0, ret_5d: float = 0.0, ma20_extension_penalty: int = 0, distribution_penalty: int = 0, annual_vol: float = 0.0, vol_regime: str = "normal", weekly_bearish: bool = False, dead_cat: bool = False) -> dict`
  - `_score_ignition_power(obv_days_above: int = 0, obv_positive: bool = False, obv_slope: float = 0.0, ignition_bonus: int = 0, coiling_bonus: int = 0, compression_reversal_bonus: int = 0, range_pos: float = 0.5, higher_low: bool = False, rebound_confirmed: bool = False, vol_ratio: float = 1.0, wr_now: float = 50.0, wr_level: str = "") -> dict`
- Produces:
  - Tests that fail until both helper functions exist.

- [ ] **Step 1: Add failing tests**

Append:

```python
def test_startup_quality_flags_late_rebound_and_distribution():
    from kronos_factors.engine.bi_trend_launch import _score_startup_quality

    result = _score_startup_quality(
        regime="weak",
        daily_gain=4.5,
        two_day_up=False,
        wr_now=82.0,
        ret_5d=10.0,
        ma20_extension_penalty=4,
        distribution_penalty=5,
        annual_vol=92.0,
        vol_regime="high",
        weekly_bearish=False,
        dead_cat=False,
    )

    assert result["score_adj"] < 0
    assert "late_rebound" in result["risk_flags"]
    assert "distribution_day" in result["risk_flags"]
    assert "weak_market_single_pop" in result["quality_flags"]


def test_ignition_power_rewards_fresh_coiling_reversal():
    from kronos_factors.engine.bi_trend_launch import _score_ignition_power

    result = _score_ignition_power(
        obv_days_above=2,
        obv_positive=True,
        obv_slope=8.0,
        ignition_bonus=4,
        coiling_bonus=3,
        compression_reversal_bonus=8,
        range_pos=0.22,
        higher_low=True,
        rebound_confirmed=True,
        vol_ratio=0.68,
        wr_now=72.0,
        wr_level="急跌→止跌→反弹🔥",
    )

    assert result["score_adj"] >= 7
    assert "fresh_obv_breakout" in result["power_flags"]
    assert "coiling_after_ignition" in result["power_flags"]
    assert "compression_reversal" in result["power_flags"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v
```

Expected: FAIL because `_score_startup_quality` and `_score_ignition_power` do not exist.

---

### Task 4: Implement Startup Quality And Ignition Power Integration

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py`
- Test: `packages/kronos-factors/tests/test_bi_trend_four_axis.py`

**Interfaces:**
- Consumes:
  - Existing `_score_bi_trend_arrays` local variables
- Produces:
  - `_score_startup_quality(regime: str = "neutral", daily_gain: float = 0.0, two_day_up: bool = False, wr_now: float = 50.0, ret_5d: float = 0.0, ma20_extension_penalty: int = 0, distribution_penalty: int = 0, annual_vol: float = 0.0, vol_regime: str = "normal", weekly_bearish: bool = False, dead_cat: bool = False) -> dict`
  - `_score_ignition_power(obv_days_above: int = 0, obv_positive: bool = False, obv_slope: float = 0.0, ignition_bonus: int = 0, coiling_bonus: int = 0, compression_reversal_bonus: int = 0, range_pos: float = 0.5, higher_low: bool = False, rebound_confirmed: bool = False, vol_ratio: float = 1.0, wr_now: float = 50.0, wr_level: str = "") -> dict`
  - `startup_quality_score`, `ignition_power_score`, `quality_flags`, `risk_flags`, and `power_flags` in pick output.

- [ ] **Step 1: Add helper implementations**

Add helpers above `_score_bi_trend_arrays`:

```python
def _score_startup_quality(regime: str = "neutral", daily_gain: float = 0.0,
                           two_day_up: bool = False, wr_now: float = 50.0,
                           ret_5d: float = 0.0, ma20_extension_penalty: int = 0,
                           distribution_penalty: int = 0, annual_vol: float = 0.0,
                           vol_regime: str = "normal", weekly_bearish: bool = False,
                           dead_cat: bool = False) -> dict:
    score_adj = 0
    quality_flags = []
    risk_flags = []
    if regime in ("weak", "recovery") and daily_gain > 3 and not two_day_up:
        score_adj -= 3
        quality_flags.append("weak_market_single_pop")
    if wr_now >= 80 and ret_5d > 8:
        score_adj -= 4
        risk_flags.append("late_rebound")
    if ma20_extension_penalty > 0:
        score_adj -= min(3, ma20_extension_penalty)
        risk_flags.append("ma20_extension")
    if distribution_penalty > 0:
        score_adj -= min(4, distribution_penalty)
        risk_flags.append("distribution_day")
    if vol_regime == "extreme":
        score_adj -= 4
        risk_flags.append("extreme_volatility")
    elif vol_regime == "high" or annual_vol >= 80:
        score_adj -= 2
        risk_flags.append("high_volatility")
    if weekly_bearish:
        score_adj -= 2
        risk_flags.append("weekly_bearish")
    if dead_cat:
        score_adj -= 2
        risk_flags.append("dead_cat_bounce")
    return {"score_adj": max(-12, min(4, score_adj)),
            "quality_flags": quality_flags, "risk_flags": risk_flags}


def _score_ignition_power(obv_days_above: int = 0, obv_positive: bool = False,
                          obv_slope: float = 0.0, ignition_bonus: int = 0,
                          coiling_bonus: int = 0, compression_reversal_bonus: int = 0,
                          range_pos: float = 0.5, higher_low: bool = False,
                          rebound_confirmed: bool = False, vol_ratio: float = 1.0,
                          wr_now: float = 50.0, wr_level: str = "") -> dict:
    score_adj = 0
    power_flags = []
    if obv_positive and obv_days_above <= 3 and obv_slope > 0:
        score_adj += 3
        power_flags.append("fresh_obv_breakout")
    if ignition_bonus > 0 and coiling_bonus > 0 and vol_ratio < 0.85:
        score_adj += 3
        power_flags.append("coiling_after_ignition")
    if compression_reversal_bonus > 0 and range_pos < 0.35 and wr_now > 60:
        score_adj += 3
        power_flags.append("compression_reversal")
    if higher_low and rebound_confirmed and vol_ratio < 1.0:
        score_adj += 2
        power_flags.append("higher_low_rebound")
    if "🔥" in wr_level and wr_now <= 75:
        score_adj += 1
        power_flags.append("wr_reversal_track")
    return {"score_adj": max(0, min(10, score_adj)), "power_flags": power_flags}
```

Clamp `startup_quality.score_adj` to `[-12, 4]` and `ignition_power.score_adj` to `[0, 10]`.

- [ ] **Step 2: Integrate helpers into scoring**

After the existing signal context variables are available, compute:

```python
startup_quality = _score_startup_quality(
    regime=regime,
    daily_gain=daily_gain,
    two_day_up=two_day_up,
    wr_now=wr_now,
    ret_5d=ret_5d,
    ma20_extension_penalty=ma20_extension_penalty,
    distribution_penalty=distribution_penalty,
    annual_vol=annual_vol,
    vol_regime=vol_regime,
    weekly_bearish=weekly_bearish,
    dead_cat=dead_cat,
)
ignition_power = _score_ignition_power(
    obv_days_above=obv_days_above,
    obv_positive=bool(obv[-1] > 0) if len(obv) else False,
    obv_slope=obv_slope,
    ignition_bonus=ignition_bonus,
    coiling_bonus=coiling_bonus,
    compression_reversal_bonus=compression_reversal_bonus,
    range_pos=range_pos,
    higher_low=higher_low,
    rebound_confirmed=rebound_confirmed,
    vol_ratio=vol_ratio,
    wr_now=wr_now,
    wr_level=wr_level,
)
```

Add both score adjustments into `total_raw`. Add helper flags to the return dict and explanation.

- [ ] **Step 3: Preserve signal semantics**

After signal type is computed, apply only these new downgrades:

```python
if "late_rebound" in risk_flags and signal_type == "strong_buy":
    signal_type = "buy"
```

Existing distribution downgrade remains the source of distribution handling.

- [ ] **Step 4: Run four-axis tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py -v
```

Expected: PASS.

---

### Task 5: Run Regression Tests And Commit

**Files:**
- Modify: none unless tests reveal a defect
- Test:
  - `packages/kronos-factors/tests/test_bi_trend_four_axis.py`
  - `packages/kronos-factors/tests/test_m15_params_extraction.py`
  - `packages/kronos-factors/tests/test_calc_obv_wr_vectorized.py`

**Interfaces:**
- Consumes:
  - Completed helper functions and return fields
- Produces:
  - Verified code and a commit containing only this task's files.

- [ ] **Step 1: Run targeted tests**

Run:

```bash
cd packages/kronos-factors && pytest tests/test_bi_trend_four_axis.py tests/test_m15_params_extraction.py tests/test_calc_obv_wr_vectorized.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Inspect diff**

Run:

```bash
git diff -- packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py packages/kronos-factors/tests/test_bi_trend_four_axis.py docs/superpowers/plans/2026-06-24-bi-trend-hard-tech-four-axis-enhancement.md
```

Expected: diff only contains four-axis enhancement work.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py packages/kronos-factors/tests/test_bi_trend_four_axis.py docs/superpowers/plans/2026-06-24-bi-trend-hard-tech-four-axis-enhancement.md
git commit -m "feat: enhance bi trend hard tech screener"
```

Expected: commit succeeds.
