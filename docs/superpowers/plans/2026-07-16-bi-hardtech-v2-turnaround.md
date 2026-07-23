# Bi Hardtech V2 Turnaround Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立独立的“毕师傅硬核科技优化版 V2”实验路径，以弱市空仓、T+1 开盘确认、每日最多 2 只和动态总仓位约束减少无效交易，并在同口径下对比 Baseline、V2-A、V2-B。

**Architecture:** 保留 `bi_trend_launch` 作为候选信号源，新增无数据库依赖的 V2 规则层，再用独立的事件驱动组合模拟器处理开盘建仓、盘中退出、收盘盯市和资金上限。CLI 负责数据时点审计、生成三个对照臂并导出可重算 JSON/中文 Markdown 报告，不在本计划内注册为实盘主模型。

**Tech Stack:** Python 3.11、NumPy、PostgreSQL `daily_kline` / `adj_factor` / 历史板块数据、`kronos_factors` PG adapter、pytest、现有 `tools/backtest_bi_trend.py` 多日成交引擎。

## Global Constraints

- 保留 `bi_trend_launch` V13/V5.9 基线，不修改其默认实时行为。
- 年交易数为 200–400 笔，按完成买入的逐笔交易计数。
- 往返交易成本固定 14bp，期初资金 1,000,000 元，禁止杠杆。
- 主验收线：组合净收益 `> 0%`、最大回撤 `<= 15%`、任意单月收益 `>= -8%`。
- `bull` 总仓位上限 50%，`neutral` 上限 30%，单股上限 15%，每日最多新建 2 个头寸。
- `weak` / `recovery` / `bear` / `crash` 不开新仓。
- T+1 跳空确认区间固定为 `[-1.5%, +3.0%]`，不用最近一年搜索替代阈值。
- 第一阶段原样复用 5 日止损/止盈/移动止盈/到期卖出规则，不调参。
- 回测数据必须记录理论更新时间、实际最新时间和信号可用截止时间；缺失时禁止用收盘数据伪造竞价或开盘数据。
- 最近一年已被用于诊断，产物必须标记为“历史滚动模拟”，不得宣称为完全未见样本。

---

## File Structure

- Create `packages/kronos-factors/kronos_factors/engine/bi_hardtech_v2.py`: V2 固定参数、市场门控、T+1 确认、每日最多 2 只的纯函数。
- Create `packages/kronos-factors/kronos_factors/backtest/portfolio_v2.py`: 无杠杆事件驱动组合模拟、逐日盯市净值、回撤和月收益计算。
- Modify `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:505-875`: 为历史重放增加显式市场 regime 入口，避免历史日读取“今日”全局 regime。
- Create `tools/backtest_bi_hardtech_v2.py`: 数据审计、历史信号生成、三对照臂编排、JSON/Markdown 导出。
- Create `packages/kronos-factors/tests/test_bi_hardtech_v2.py`: V2 规则层单元测试。
- Create `packages/kronos-factors/tests/test_portfolio_v2.py`: 仓位、事件顺序、14bp 成本、盯市净值单元测试。
- Create `tools/tests/test_backtest_bi_hardtech_v2.py`: 数据时点审计、三臂产物和验收判定测试。
- Create runtime artifacts under `outputs/backtests/bi_hardtech_v2/<run_id>/`: `result.json`、`report.md`、`trades.csv`、`equity.csv`。

### Task 1: V2 Pure Rule Layer

**Files:**
- Create: `packages/kronos-factors/kronos_factors/engine/bi_hardtech_v2.py`
- Test: `packages/kronos-factors/tests/test_bi_hardtech_v2.py`

**Interfaces:**
- Consumes: baseline pick dictionaries containing `code`, `name`, `industry`, `sector_change`, and baseline sort order; `market_info["regime"]`; T close and T+1 open.
- Produces: `V2Config`, `market_allows_entry(regime: str) -> bool`, `confirm_t1_open(previous_close: float, open_price: float, sector_change: float | None, config: V2Config) -> Confirmation`, and `select_daily_entries(candidates: list[dict], open_by_code: dict[str, float], close_by_code: dict[str, float], config: V2Config) -> tuple[list[dict], list[dict]]`.

- [ ] **Step 1: Write failing market-gate and open-confirmation tests**

```python
import pytest

from kronos_factors.engine.bi_hardtech_v2 import (
    V2Config,
    confirm_t1_open,
    market_allows_entry,
    select_daily_entries,
)


@pytest.mark.parametrize("regime,allowed", [
    ("bull", True),
    ("neutral", True),
    ("weak", False),
    ("recovery", False),
    ("bear", False),
    ("crash", False),
])
def test_market_gate(regime, allowed):
    assert market_allows_entry(regime) is allowed


@pytest.mark.parametrize("open_price,accepted,reason", [
    (98.49, False, "gap_below_min"),
    (98.50, True, "accepted"),
    (103.00, True, "accepted"),
    (103.01, False, "gap_above_max"),
])
def test_open_gap_boundaries(open_price, accepted, reason):
    decision = confirm_t1_open(100.0, open_price, 0.1, V2Config())
    assert decision.accepted is accepted
    assert decision.reason == reason


def test_missing_or_negative_sector_rejects_entry():
    assert confirm_t1_open(100.0, 100.0, None, V2Config()).reason == "sector_missing"
    assert confirm_t1_open(100.0, 100.0, -0.01, V2Config()).reason == "sector_negative"


def test_daily_entries_keep_baseline_order_and_cap_at_two():
    picks = [
        {"code": "000001", "sector_change": 1.0},
        {"code": "000002", "sector_change": 0.5},
        {"code": "000003", "sector_change": 0.2},
    ]
    selected, rejected = select_daily_entries(
        picks,
        open_by_code={p["code"]: 100.0 for p in picks},
        close_by_code={p["code"]: 100.0 for p in picks},
        config=V2Config(),
    )
    assert [p["code"] for p in selected] == ["000001", "000002"]
    assert rejected[-1]["reason"] == "daily_limit"
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py -q
```

Expected: collection fails with `ModuleNotFoundError: kronos_factors.engine.bi_hardtech_v2`.

- [ ] **Step 3: Implement the fixed V2 rule API**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class V2Config:
    gap_min_pct: float = -1.5
    gap_max_pct: float = 3.0
    max_daily_entries: int = 2
    bull_cap: float = 0.50
    neutral_cap: float = 0.30
    single_position_cap: float = 0.15


@dataclass(frozen=True)
class Confirmation:
    accepted: bool
    reason: str
    gap_pct: float | None


def market_allows_entry(regime: str) -> bool:
    return regime in {"bull", "neutral"}


def confirm_t1_open(
    previous_close: float,
    open_price: float,
    sector_change: float | None,
    config: V2Config,
) -> Confirmation:
    if previous_close <= 0 or open_price <= 0:
        return Confirmation(False, "price_missing", None)
    gap_pct = (open_price / previous_close - 1.0) * 100.0
    if gap_pct < config.gap_min_pct:
        return Confirmation(False, "gap_below_min", gap_pct)
    if gap_pct > config.gap_max_pct:
        return Confirmation(False, "gap_above_max", gap_pct)
    if sector_change is None:
        return Confirmation(False, "sector_missing", gap_pct)
    if sector_change < 0:
        return Confirmation(False, "sector_negative", gap_pct)
    return Confirmation(True, "accepted", gap_pct)


def select_daily_entries(candidates, open_by_code, close_by_code, config):
    selected, rejected = [], []
    for candidate in candidates:
        code = candidate["code"]
        decision = confirm_t1_open(
            close_by_code.get(code, 0.0),
            open_by_code.get(code, 0.0),
            candidate.get("sector_change"),
            config,
        )
        enriched = {**candidate, "confirmation_reason": decision.reason,
                    "gap_pct": decision.gap_pct}
        if not decision.accepted:
            rejected.append(enriched)
        elif len(selected) < config.max_daily_entries:
            selected.append(enriched)
        else:
            rejected.append({**enriched, "confirmation_reason": "daily_limit",
                             "reason": "daily_limit"})
    return selected, rejected
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py -q`

Expected: all parameterized cases pass.

- [ ] **Step 5: Commit the rule layer**

```bash
git add packages/kronos-factors/kronos_factors/engine/bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py
git commit -m "feat: add bi hardtech v2 entry rules"
```

### Task 2: Historical-Replay Guard for the Baseline Signal Source

**Files:**
- Modify: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:505-518`
- Modify: `packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py:790-833`
- Test: `packages/kronos-factors/tests/test_bi_hardtech_v2.py`

**Interfaces:**
- Consumes: optional `global_market_regime` supplied by a historical runner.
- Produces: `_resolve_global_market_regime(explicit: dict | None) -> tuple[dict, str]` and backward-compatible `run_bi_screening(db, trade_date, top_n=20, hard_tech_only=True, global_market_regime=None)`; default `None` keeps production behavior, explicit dictionaries prevent historical runs from querying today's global regime.

- [ ] **Step 1: Add a failing regression test for explicit historical regime**

```python
from unittest.mock import patch

from kronos_factors.engine import bi_trend_launch


def test_explicit_historical_regime_skips_current_regime_lookup():
    explicit = {"regime": "neutral", "bonus": 0.0}
    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        side_effect=AssertionError("current regime must not be read"),
    ):
        regime, source = bi_trend_launch._resolve_global_market_regime(explicit)
    assert regime == explicit
    assert source == "explicit"


def test_default_regime_keeps_runtime_lookup():
    expected = {"regime": "bull", "bonus": 0.1}
    with patch(
        "kronos_factors.scorer.screening_scorers.get_market_regime",
        return_value=expected,
    ) as lookup:
        regime, source = bi_trend_launch._resolve_global_market_regime(None)
    lookup.assert_called_once_with()
    assert regime == expected
    assert source == "current_runtime"
```

- [ ] **Step 2: Run the regression test and verify RED**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_bi_hardtech_v2.py::test_explicit_historical_regime_skips_current_regime_lookup -q`

Expected: FAIL with `AttributeError` because `_resolve_global_market_regime` does not exist.

- [ ] **Step 3: Add the backward-compatible parameter and provenance field**

```python
def _resolve_global_market_regime(explicit=None):
    if explicit is not None:
        return dict(explicit), "explicit"
    market_regime = {"regime": "neutral", "bonus": 0.0}
    try:
        from kronos_factors.scorer.screening_scorers import get_market_regime
        market_regime = get_market_regime()
    except Exception:
        pass
    return market_regime, "current_runtime"


def run_bi_screening(
    db,
    trade_date,
    top_n=20,
    hard_tech_only=True,
    global_market_regime=None,
):
    market_regime, global_regime_source = _resolve_global_market_regime(
        global_market_regime
    )

    # Keep the existing breadth, candidate scoring and risk-control body unchanged.
    # Before returning, add this provenance to the existing market_info dictionary:
    market_info["global_regime_source"] = global_regime_source
```

Do not alter the production callers: omitted parameter means existing behavior.

- [ ] **Step 4: Run focused and baseline engine tests**

Run:

```bash
bash tools/codex-lowio.sh py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_bi_trend_four_axis.py -q
```

Expected: all tests pass, and the explicit-regime test proves no current-runtime lookup occurs.

- [ ] **Step 5: Commit the historical guard**

```bash
git add packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py
git commit -m "fix: isolate historical bi trend regime"
```

### Task 3: Event-Driven Portfolio Simulator

**Files:**
- Create: `packages/kronos-factors/kronos_factors/backtest/portfolio_v2.py`
- Test: `packages/kronos-factors/tests/test_portfolio_v2.py`

**Interfaces:**
- Consumes: `EntryOrder` objects, adjusted daily bars indexed by `(date, code)`, and exit outcomes generated with the unchanged `simulate_position` semantics.
- Produces: `PortfolioResult(summary: dict, trades: list[dict], equity_curve: list[dict])` and `simulate_portfolio(...)`.

- [ ] **Step 1: Write failing tests for caps, event order, costs and mark-to-market**

```python
import pytest

from kronos_factors.backtest.portfolio_v2 import EntryOrder, simulate_portfolio


def _bars(dates, prices):
    out = {}
    for trade_date in dates:
        for code, value in prices.items():
            close = value[trade_date]
            out[(trade_date, code)] = {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adj_factor": 1.0,
            }
    return out


def _order(code, entry_date, exit_date, exit_price, regime="bull"):
    return EntryOrder(
        signal_date="2026-01-01",
        entry_date=entry_date,
        code=code,
        regime=regime,
        weight=1.0,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason="hold_to_maturity",
    )


def test_bull_opening_cap_and_single_stock_cap():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(dates, {
        "000001": {d: 100.0 for d in dates},
        "000002": {d: 100.0 for d in dates},
    })
    orders = [
        _order("000001", "2026-01-02", "2026-01-05", 100.0),
        _order("000002", "2026-01-02", "2026-01-05", 100.0),
    ]
    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)
    assert result.trades[0]["buy_notional"] <= 150_000
    assert result.trades[1]["buy_notional"] <= 150_000
    assert sum(t["buy_notional"] for t in result.trades) <= 500_000


def test_neutral_cap_subtracts_old_positions_at_open():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    bars = _bars(dates, {
        "000001": {d: 100.0 for d in dates},
        "000002": {d: 100.0 for d in dates},
    })
    orders = [
        _order("000001", "2026-01-02", "2026-01-07", 100.0, "neutral"),
        _order("000002", "2026-01-06", "2026-01-07", 100.0, "neutral"),
    ]
    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)
    day_two = next(p for p in result.equity_curve if p["date"] == "2026-01-06")
    assert day_two["gross_exposure"] <= day_two["equity_open"] * 0.30 + 0.01


def test_round_trip_cost_is_fourteen_basis_points():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(dates, {"000001": {d: 100.0 for d in dates}})
    result = simulate_portfolio(
        [_order("000001", "2026-01-02", "2026-01-05", 100.0)],
        bars,
        1_000_000,
        14.0,
    )
    assert result.trades[0]["net_return_pct"] == pytest.approx(-0.14, abs=0.001)


def test_close_equity_marks_open_positions_to_market():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    bars = _bars(dates, {"000001": {
        "2026-01-02": 100.0,
        "2026-01-05": 105.0,
        "2026-01-06": 110.0,
        "2026-01-07": 110.0,
    }})
    result = simulate_portfolio(
        [_order("000001", "2026-01-02", "2026-01-07", 110.0)],
        bars,
        1_000_000,
        14.0,
    )
    point = next(p for p in result.equity_curve if p["date"] == "2026-01-06")
    assert point["equity_close"] > point["cash"] + point["position_cost"]


def test_open_orders_are_processed_before_same_day_close_exits():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    bars = _bars(dates, {
        "000001": {d: 100.0 for d in dates},
        "000002": {d: 100.0 for d in dates},
    })
    orders = [
        _order("000001", "2026-01-02", "2026-01-06", 100.0, "neutral"),
        _order("000002", "2026-01-06", "2026-01-07", 100.0, "neutral"),
    ]
    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)
    new_trade = next(t for t in result.trades if t["code"] == "000002")
    assert new_trade["buy_notional"] <= 150_000
```

- [ ] **Step 2: Run the portfolio test and verify RED**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_portfolio_v2.py -q`

Expected: collection fails because `portfolio_v2` does not exist.

- [ ] **Step 3: Implement the simulator's public types and fixed event loop**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryOrder:
    signal_date: str
    entry_date: str
    code: str
    regime: str
    weight: float
    name: str = ""
    exit_date: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None


@dataclass
class PortfolioResult:
    summary: dict
    trades: list[dict]
    equity_curve: list[dict]


REGIME_CAPS = {"bull": 0.50, "neutral": 0.30}
SINGLE_POSITION_CAP = 0.15


def simulate_portfolio(orders, bars, initial_capital=1_000_000.0, cost_bps=14.0):
    buy_cost = cost_bps / 20_000.0
    sell_cost = cost_bps / 20_000.0
    cash = float(initial_capital)
    positions = []
    trades = []
    equity_curve = []

    for trade_date in sorted({d for d, _code in bars}):
        equity_open = cash + sum(
            p["shares"] * adjusted_price(bars[(trade_date, p["code"])], "open")
            for p in positions if (trade_date, p["code"]) in bars
        )
        gross_exposure = equity_open - cash
        day_orders = [o for o in orders if o.entry_date == trade_date][:2]
        for order in day_orders:
            cap = REGIME_CAPS.get(order.regime, 0.0)
            available = max(0.0, equity_open * cap - gross_exposure)
            budget = min(available, equity_open * SINGLE_POSITION_CAP,
                         cash / (1.0 + buy_cost))
            if budget <= 0:
                continue
            entry_price = adjusted_price(bars[(trade_date, order.code)], "open")
            shares = budget / entry_price
            buy_cash = budget * (1.0 + buy_cost)
            cash -= buy_cash
            positions.append({"order": order, "code": order.code, "shares": shares,
                              "buy_notional": budget, "buy_cash": buy_cash,
                              "entry_price": entry_price})
            gross_exposure += budget

        # Resolve intraday/close exits only after all opening orders use opening cash.
        positions, cash, completed = process_exits(
            trade_date, positions, bars, cash, sell_cost
        )
        trades.extend(completed)
        close_value = sum(
            p["shares"] * adjusted_price(bars[(trade_date, p["code"])], "close")
            for p in positions if (trade_date, p["code"]) in bars
        )
        equity_curve.append({"date": trade_date, "cash": cash,
                             "position_value": close_value,
                             "position_cost": sum(p["buy_cash"] for p in positions),
                             "equity_close": cash + close_value,
                             "equity_open": equity_open,
                             "gross_exposure": gross_exposure})

    return build_portfolio_result(initial_capital, trades, equity_curve)


def adjusted_price(bar, field):
    price = float(bar[field])
    factor = bar.get("adj_factor")
    if factor is None or float(factor) <= 0:
        raise ValueError("adj_factor_missing")
    return price * float(factor)


def process_exits(trade_date, positions, bars, cash, sell_cost):
    remaining = []
    completed = []
    for position in positions:
        order = position["order"]
        if order.exit_date != trade_date:
            remaining.append(position)
            continue
        if order.exit_price is None:
            remaining.append(position)
            continue
        proceeds = position["shares"] * float(order.exit_price) * (1.0 - sell_cost)
        cash += proceeds
        net_return = proceeds / position["buy_cash"] - 1.0
        completed.append({
            "signal_date": order.signal_date,
            "entry_date": order.entry_date,
            "exit_date": order.exit_date,
            "code": order.code,
            "name": order.name,
            "buy_notional": position["buy_notional"],
            "entry_price": position["entry_price"],
            "exit_price": order.exit_price,
            "exit_reason": order.exit_reason,
            "net_return_pct": net_return * 100.0,
        })
    return remaining, cash, completed


def build_portfolio_result(initial_capital, trades, equity_curve):
    ending = equity_curve[-1]["equity_close"] if equity_curve else initial_capital
    peak = float(initial_capital)
    max_drawdown = 0.0
    monthly_points = {}
    for point in equity_curve:
        equity = float(point["equity_close"])
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        monthly_points.setdefault(point["date"][:7], []).append(equity)
    monthly_returns = {}
    prior_month_end = float(initial_capital)
    for month in sorted(monthly_points):
        month_end = monthly_points[month][-1]
        monthly_returns[month] = (month_end / prior_month_end - 1.0) * 100.0
        prior_month_end = month_end
    net_returns = [float(t["net_return_pct"]) for t in trades]
    summary = {
        "total_trades": len(trades),
        "wins": sum(value > 0 for value in net_returns),
        "win_rate_pct": (
            sum(value > 0 for value in net_returns) / len(net_returns) * 100.0
            if net_returns else 0.0
        ),
        "initial_capital": float(initial_capital),
        "ending_capital": ending,
        "total_return_pct": (ending / initial_capital - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "monthly_returns": monthly_returns,
        "worst_month_pct": min(monthly_returns.values(), default=0.0),
    }
    return PortfolioResult(summary=summary, trades=trades, equity_curve=equity_curve)
```

`process_exits` uses the exit date/price/reason already produced by the shared multi-day trade simulation and never chooses a more favorable price. Pending positions stay out of realized win rate while their latest available close remains in final equity.

- [ ] **Step 4: Run tests and verify cash-flow identities**

Run: `bash tools/codex-lowio.sh py packages/kronos-factors/tests/test_portfolio_v2.py -q`

Expected: all tests pass, and a flat trade loses exactly 0.14% before rounding.

- [ ] **Step 5: Commit the portfolio simulator**

```bash
git add packages/kronos-factors/kronos_factors/backtest/portfolio_v2.py \
  packages/kronos-factors/tests/test_portfolio_v2.py
git commit -m "feat: add marked-to-market v2 portfolio simulator"
```

### Task 4: Three-Arm Historical Backtest CLI and Data Audit

**Files:**
- Create: `tools/backtest_bi_hardtech_v2.py`
- Test: `tools/tests/test_backtest_bi_hardtech_v2.py`

**Interfaces:**
- Consumes: `run_bi_screening(..., global_market_regime={"regime": "neutral", "bonus": 0.0})`, V2 rule functions, existing `get_adjusted_bars` / `simulate_position` from `tools/backtest_bi_trend.py`, and `simulate_portfolio`.
- Produces: `audit_sources(db, start_date, end_date) -> dict`, `build_arms(...) -> dict[str, list[EntryOrder]]`, `evaluate_acceptance(summary: dict) -> dict`, plus CLI artifacts.

- [ ] **Step 1: Write failing audit, arm and acceptance tests**

```python
from backtest_bi_hardtech_v2 import evaluate_acceptance, validate_source_audit


def test_source_audit_rejects_daily_kline_before_requested_end():
    audit = {
        "result_data_end": "2026-07-15",
        "signal_end": "2026-07-08",
        "daily_kline_latest": "2026-07-14",
        "adj_factor_latest": "2026-07-14",
        "adj_factor_missing_trade_rows": 0,
        "sector_latest": "2026-07-08",
    }
    decision = validate_source_audit(audit)
    assert decision["errors"] == ["daily_kline_stale"]
    assert decision["warnings"] == ["adj_factor_lags_result_end"]


def test_acceptance_requires_all_five_gates():
    decision = evaluate_acceptance({
        "total_trades": 250,
        "total_return_pct": 3.0,
        "max_drawdown_pct": -12.0,
        "worst_month_pct": -7.0,
        "runtime_errors": 0,
    })
    assert decision["passed"] is True
    assert all(decision["gates"].values())


def test_acceptance_fails_profitable_but_overtraded_result():
    decision = evaluate_acceptance({
        "total_trades": 401,
        "total_return_pct": 3.0,
        "max_drawdown_pct": -12.0,
        "worst_month_pct": -7.0,
        "runtime_errors": 0,
    })
    assert decision["passed"] is False
    assert decision["gates"]["annual_trade_count"] is False
```

- [ ] **Step 2: Run the CLI unit test and verify RED**

Run: `bash tools/codex-lowio.sh py tools/tests/test_backtest_bi_hardtech_v2.py -q`

Expected: import fails because the CLI module does not exist.

- [ ] **Step 3: Implement source auditing and explicit CLI arguments**

```python
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    parser.add_argument("--cost-bps", type=float, default=14.0)
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def validate_source_audit(audit):
    errors = []
    warnings = []
    if (audit.get("daily_kline_latest") is None or
            audit["daily_kline_latest"] < audit["result_data_end"]):
        errors.append("daily_kline_stale")
    if (audit.get("sector_latest") is None or
            audit["sector_latest"] < audit["signal_end"]):
        errors.append("sector_stale")
    if audit.get("adj_factor_missing_trade_rows", 0) > 0:
        errors.append("adj_factor_trade_coverage_missing")
    elif (audit.get("adj_factor_latest") is None or
          audit["adj_factor_latest"] < audit["result_data_end"]):
        warnings.append("adj_factor_lags_result_end")
    return {"errors": errors, "warnings": warnings}


def evaluate_acceptance(summary):
    gates = {
        "annual_trade_count": 200 <= summary["total_trades"] <= 400,
        "positive_net_return": summary["total_return_pct"] > 0,
        "max_drawdown": summary["max_drawdown_pct"] >= -15,
        "worst_month": summary["worst_month_pct"] >= -8,
        "no_runtime_errors": summary["runtime_errors"] == 0,
    }
    return {"passed": all(gates.values()), "gates": gates}
```

`audit_sources` must execute these exact checks and save their results in `result.json`:

```sql
SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date), COUNT(*)
FROM daily_kline;

SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date), COUNT(*)
FROM adj_factor;

SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date), COUNT(*)
FROM index_daily;

SELECT COUNT(*) FROM st_history;

SELECT api, update_time, update_frequency, doc_url,
       extraction_status, evidence, updated_at
FROM tushare_api_update_metadata
WHERE api IN ('daily', 'adj_factor', 'index_daily')
ORDER BY api;
```

The metadata rows provide the theoretical publication contract; missing or `unknown` metadata must be emitted as a source warning rather than silently replaced by an assumed time. After orders are built, the runner must also count every entry/valuation/exit bar whose code has no factor on that date after an **as-of forward fill from an earlier factor**. Any such row sets `adj_factor_missing_trade_rows > 0` and blocks the run. A table-wide `adj_factor` max date earlier than the result-data end is only a warning when all actually traded rows have valid as-of factors. The implementation must never use a future factor to fill an earlier signal or valuation date.

- [ ] **Step 4: Implement the three arms without changing sell rules**

```python
ARMS = ("baseline", "v2_a", "v2_b")
HISTORICAL_GLOBAL_REGIME = {"regime": "neutral", "bonus": 0.0}


def next_trade_date(db, signal_date):
    row = db.execute(
        "SELECT MIN(trade_date) AS d FROM daily_kline WHERE trade_date > ?",
        (signal_date,),
    ).fetchone()
    return str(row["d"])[:10] if row and row["d"] else None


def load_prices(db, trade_date, field, codes):
    if field not in {"open", "close"}:
        raise ValueError(f"unsupported price field: {field}")
    if not codes:
        return {}
    placeholders = ",".join("?" for _ in codes)
    rows = db.execute(
        f"SELECT code, {field} AS price FROM daily_kline "
        f"WHERE trade_date=? AND code IN ({placeholders})",
        [trade_date, *codes],
    ).fetchall()
    return {
        row["code"]: float(row["price"])
        for row in rows
        if row["price"] is not None and float(row["price"]) > 0
    }


def make_orders(picks, signal_date, entry_date, market_info):
    return [
        EntryOrder(
            signal_date=signal_date,
            entry_date=entry_date,
            code=pick["code"],
            name=pick.get("name", ""),
            regime=market_info.get("regime", ""),
            weight=float(pick.get("weight", 1.0)),
        )
        for pick in picks
    ]


def reject_day(picks, signal_date, reason):
    return [
        {"signal_date": signal_date, "code": pick["code"], "reason": reason}
        for pick in picks
    ]


def confirm_for_next_open(db, signal_date, picks, config):
    entry_date = next_trade_date(db, signal_date)
    if entry_date is None:
        return [], reject_day(picks, signal_date, "entry_date_missing")
    selected, rejected = select_daily_entries(
        picks,
        open_by_code=load_prices(db, entry_date, "open", [p["code"] for p in picks]),
        close_by_code=load_prices(db, signal_date, "close", [p["code"] for p in picks]),
        config=config,
    )
    return selected, [
        {"signal_date": signal_date, "code": row["code"],
         "reason": row["confirmation_reason"]}
        for row in rejected
    ]


def build_arms(db, signal_dates, top_n, config):
    arms = {name: [] for name in ARMS}
    rejected = []
    for signal_date in signal_dates:
        entry_date = next_trade_date(db, signal_date)
        if entry_date is None:
            rejected.append({"signal_date": signal_date,
                             "code": None, "reason": "entry_date_missing"})
            continue
        top, _scores, market_info = run_bi_screening(
            db,
            signal_date,
            top_n=top_n,
            global_market_regime=HISTORICAL_GLOBAL_REGIME,
        )
        arms["baseline"].extend(make_orders(top, signal_date, entry_date, market_info))
        if not market_allows_entry(market_info.get("regime", "")):
            rejected.extend(reject_day(top, signal_date, "market_gate"))
            continue
        arms["v2_a"].extend(make_orders(top, signal_date, entry_date, market_info))
        selected, day_rejected = confirm_for_next_open(db, signal_date, top, config)
        arms["v2_b"].extend(
            make_orders(selected, signal_date, entry_date, market_info)
        )
        rejected.extend(day_rejected)
    return arms, rejected
```

For every order in every arm, call the existing `simulate_position` with baseline `hold_days=5`, `take_profit=15`, `stop_loss=-10`, and existing trailing tiers. Do not count `data_truncated` or pending exits as completed wins/losses. Use the same adjusted bars and resulting exit prices in all three arms.

- [ ] **Step 5: Implement deterministic artifacts**

Write:

```text
outputs/backtests/bi_hardtech_v2/<run_id>/result.json
outputs/backtests/bi_hardtech_v2/<run_id>/report.md
outputs/backtests/bi_hardtech_v2/<run_id>/trades.csv
outputs/backtests/bi_hardtech_v2/<run_id>/equity.csv
```

`result.json` must contain `model_key`, baseline version, git commit, exact parameters, source audit, signal range, result-data end, arm summaries, monthly summaries, rejection reasons, runtime errors, acceptance decision, and limitations. `report.md` must lead with the Baseline/V2-A/V2-B comparison and state `PROMOTE_TO_PAPER` only when every acceptance gate is true; otherwise state `KEEP_EXPERIMENTAL`.

- [ ] **Step 6: Run CLI unit tests and focused regression tests**

Run:

```bash
bash tools/codex-lowio.sh py \
  tools/tests/test_backtest_bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_portfolio_v2.py \
  backend/tests/ml/test_simulate_position.py -q
```

Expected: all tests pass; no test connects to live PostgreSQL.

- [ ] **Step 7: Commit the backtest runner**

```bash
git add tools/backtest_bi_hardtech_v2.py \
  tools/tests/test_backtest_bi_hardtech_v2.py
git commit -m "feat: add bi hardtech v2 comparison backtest"
```

### Task 5: Real Twelve-Month Run, Independent Recalculation and Decision

**Files:**
- Create: runtime artifacts under `outputs/backtests/bi_hardtech_v2/<run_id>/`
- Modify only if verification exposes a defect: files introduced in Tasks 1-4, with a failing regression test added before the fix.

**Interfaces:**
- Consumes: latest complete `daily_kline` date and all implementation interfaces from Tasks 1-4.
- Produces: one reproducible real-data comparison run and an evidence-based `PROMOTE_TO_PAPER` or `KEEP_EXPERIMENTAL` decision.

- [ ] **Step 1: Verify the latest complete source dates before choosing the window**

Run:

```bash
python3 - <<'PY'
import psycopg2

conn = psycopg2.connect("postgresql://kronos:kronos@localhost:6432/kronos")
cur = conn.cursor()
for table in ("daily_kline", "adj_factor"):
    cur.execute(f"SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM {table}")
    print(table, cur.fetchone())
conn.close()
PY
```

Expected: explicit min/max/count rows. Set the run end to the latest complete daily close that also has enough future bars to settle every included signal; do not assume the wall-clock date.

- [ ] **Step 2: Run the twelve-month comparison**

Run with dates resolved from Step 1:

```bash
KRONOS_PG_URL=postgresql://kronos:kronos@localhost:6432/kronos \
python3 tools/backtest_bi_hardtech_v2.py \
  --start-date 2025-07-16 \
  --end-date 2026-07-15 \
  --initial-capital 1000000 \
  --cost-bps 14 \
  --top-n 20 \
  --output-dir outputs/backtests/bi_hardtech_v2/20250716_20260715
```

Expected: exit code 0, all four artifacts exist, and the report records the actual source dates. A strategy failing acceptance is a valid research result, not a command failure.

- [ ] **Step 3: Independently recalculate the financial identities**

```python
import json
from pathlib import Path

path = Path("outputs/backtests/bi_hardtech_v2/20250716_20260715/result.json")
result = json.loads(path.read_text())
for arm, payload in result["arms"].items():
    curve = payload["equity_curve"]
    summary = payload["summary"]
    assert curve[-1]["equity_close"] == summary["ending_capital"]
    expected_return = (summary["ending_capital"] / 1_000_000 - 1) * 100
    assert abs(expected_return - summary["total_return_pct"]) < 1e-6
    assert all(t["entry_date"] > t["signal_date"] for t in payload["trades"])
    assert all(t["exit_date"] <= result["result_data_end"] for t in payload["trades"])
```

Run the snippet with `python3 - <<'PY' ... PY`. Expected: exit code 0 and no assertion output.

- [ ] **Step 4: Run all focused tests again after the real run**

Run:

```bash
bash tools/codex-lowio.sh py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_portfolio_v2.py \
  tools/tests/test_backtest_bi_hardtech_v2.py \
  backend/tests/ml/test_simulate_position.py -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 5: Record the decision without changing the registered model**

If every V2-B gate passes, report `PROMOTE_TO_PAPER` and create a separate registration/paper-trading design review. If any gate fails, report `KEEP_EXPERIMENTAL`, list the failed gates, and stop threshold searching. In both cases, do not modify `services/screener-service/app/config.py`, `orchestrator.py`, the frontend model list, or Feishu routing in this plan.

- [ ] **Step 6: Commit only implementation and reproducibility metadata**

```bash
git add packages/kronos-factors/kronos_factors/engine/bi_hardtech_v2.py \
  packages/kronos-factors/kronos_factors/backtest/portfolio_v2.py \
  packages/kronos-factors/kronos_factors/engine/bi_trend_launch.py \
  packages/kronos-factors/tests/test_bi_hardtech_v2.py \
  packages/kronos-factors/tests/test_portfolio_v2.py \
  tools/backtest_bi_hardtech_v2.py \
  tools/tests/test_backtest_bi_hardtech_v2.py
git commit -m "test: validate bi hardtech v2 turnaround"
```

Do not stage unrelated dirty-tree files or generated outputs unless the repository's existing artifact policy explicitly tracks the selected report.

## Completion Gate

Before claiming completion, verify all of the following from fresh command output:

1. Focused pytest command reports zero failures.
2. Real run reports zero runtime errors and exact source timestamps.
3. Every buy date is later than its signal date.
4. Every realized exit date is no later than the result-data end.
5. Final capital and return recompute from the exported equity curve.
6. Baseline、V2-A、V2-B use the same costs, exit outcomes and adjusted price source.
7. The report states `PROMOTE_TO_PAPER` only if all acceptance gates pass; otherwise it states `KEEP_EXPERIMENTAL`.
8. Existing `bi_trend_launch` remains the registered baseline and unrelated working-tree changes remain untouched.
