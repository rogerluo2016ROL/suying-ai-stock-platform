from __future__ import annotations

from dataclasses import dataclass


REGIME_CAPS = {
    "bull": 0.50,
    "neutral": 0.30,
}
SINGLE_POSITION_CAP = 0.15
DAILY_ENTRY_LIMIT = 2


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


def adjusted_price(bar: dict, field: str) -> float:
    factor = bar.get("adj_factor")
    if factor is None or float(factor) <= 0:
        raise ValueError("adj_factor_missing")
    return float(bar[field]) * float(factor)


def simulate_portfolio(
    orders: list[EntryOrder],
    bars: dict[tuple[str, str], dict],
    initial_capital: float = 1_000_000.0,
    cost_bps: float = 14.0,
) -> PortfolioResult:
    buy_cost_rate = float(cost_bps) / 20_000.0
    sell_cost_rate = float(cost_bps) / 20_000.0
    cash = float(initial_capital)
    positions: list[dict] = []
    trades: list[dict] = []
    equity_curve: list[dict] = []

    orders_by_entry_date: dict[str, list[EntryOrder]] = {}
    for order in orders:
        orders_by_entry_date.setdefault(order.entry_date, []).append(order)

    dates = sorted(
        {trade_date for trade_date, _code in bars}
        | {order.entry_date for order in orders}
        | {order.exit_date for order in orders if order.exit_date}
    )

    for trade_date in dates:
        opening_exposure = 0.0
        for position in positions:
            bar = _require_bar(bars, trade_date, position["code"])
            opening_exposure += position["shares"] * adjusted_price(bar, "open")

        equity_open = cash + opening_exposure
        gross_exposure = opening_exposure

        day_orders = orders_by_entry_date.get(trade_date, [])[:DAILY_ENTRY_LIMIT]
        for order in day_orders:
            regime_cap = REGIME_CAPS.get(order.regime, 0.0)
            if regime_cap <= 0:
                continue

            available_capacity = max(0.0, equity_open * regime_cap - gross_exposure)
            if available_capacity <= 0:
                continue

            single_position_budget = equity_open * SINGLE_POSITION_CAP
            cash_budget = cash / (1.0 + buy_cost_rate)
            buy_notional = min(available_capacity, single_position_budget, cash_budget)
            if buy_notional <= 0:
                continue

            bar = _require_bar(bars, trade_date, order.code)
            entry_price = adjusted_price(bar, "open")
            shares = buy_notional / entry_price
            buy_cost = buy_notional * buy_cost_rate
            buy_cash = buy_notional + buy_cost

            cash -= buy_cash
            gross_exposure += buy_notional
            positions.append(
                {
                    "order": order,
                    "code": order.code,
                    "shares": shares,
                    "buy_notional": buy_notional,
                    "buy_cost": buy_cost,
                    "buy_cash": buy_cash,
                    "entry_price": entry_price,
                }
            )

        positions, cash, completed = process_exits(
            trade_date=trade_date,
            positions=positions,
            cash=cash,
            sell_cost_rate=sell_cost_rate,
        )
        trades.extend(completed)

        position_value = 0.0
        position_cost = 0.0
        for position in positions:
            bar = _require_bar(bars, trade_date, position["code"])
            position_value += position["shares"] * adjusted_price(bar, "close")
            position_cost += position["buy_cash"]

        equity_close = cash + position_value
        equity_curve.append(
            {
                "date": trade_date,
                "cash": cash,
                "position_value": position_value,
                "position_cost": position_cost,
                "equity_open": equity_open,
                "equity_close": equity_close,
                "gross_exposure": gross_exposure,
            }
        )

    return build_portfolio_result(
        initial_capital=float(initial_capital),
        trades=trades,
        equity_curve=equity_curve,
    )


def process_exits(
    *,
    trade_date: str,
    positions: list[dict],
    cash: float,
    sell_cost_rate: float,
) -> tuple[list[dict], float, list[dict]]:
    remaining_positions: list[dict] = []
    completed: list[dict] = []

    for position in positions:
        order: EntryOrder = position["order"]
        if order.exit_date != trade_date or order.exit_price is None:
            remaining_positions.append(position)
            continue

        gross_proceeds = position["shares"] * float(order.exit_price)
        sell_cost = gross_proceeds * sell_cost_rate
        net_proceeds = gross_proceeds - sell_cost
        cash += net_proceeds
        net_return_pct = (net_proceeds / position["buy_cash"] - 1.0) * 100.0

        completed.append(
            {
                "signal_date": order.signal_date,
                "entry_date": order.entry_date,
                "exit_date": order.exit_date,
                "code": order.code,
                "name": order.name,
                "regime": order.regime,
                "buy_notional": position["buy_notional"],
                "buy_cost": position["buy_cost"],
                "buy_cash": position["buy_cash"],
                "entry_price": position["entry_price"],
                "exit_price": float(order.exit_price),
                "sell_proceeds": net_proceeds,
                "sell_cost": sell_cost,
                "exit_reason": order.exit_reason,
                "net_return_pct": net_return_pct,
            }
        )

    return remaining_positions, cash, completed


def build_portfolio_result(
    *,
    initial_capital: float,
    trades: list[dict],
    equity_curve: list[dict],
) -> PortfolioResult:
    ending_capital = equity_curve[-1]["equity_close"] if equity_curve else initial_capital
    peak = float(initial_capital)
    max_drawdown = 0.0
    month_end_equity: dict[str, float] = {}

    for point in equity_curve:
        equity_close = float(point["equity_close"])
        peak = max(peak, equity_close)
        max_drawdown = min(max_drawdown, equity_close / peak - 1.0)
        month_end_equity[point["date"][:7]] = equity_close

    monthly_returns: dict[str, float] = {}
    prior_month_end = float(initial_capital)
    for month in sorted(month_end_equity):
        current_month_end = month_end_equity[month]
        monthly_returns[month] = (current_month_end / prior_month_end - 1.0) * 100.0
        prior_month_end = current_month_end

    winning_trades = sum(trade["net_return_pct"] > 0 for trade in trades)
    trade_count = len(trades)
    summary = {
        "total_trades": trade_count,
        "wins": winning_trades,
        "win_rate_pct": (winning_trades / trade_count * 100.0) if trade_count else 0.0,
        "initial_capital": float(initial_capital),
        "ending_capital": ending_capital,
        "total_return_pct": (ending_capital / initial_capital - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown * 100.0,
        "monthly_returns": monthly_returns,
        "worst_month_pct": min(monthly_returns.values(), default=0.0),
    }
    return PortfolioResult(summary=summary, trades=trades, equity_curve=equity_curve)


def _require_bar(bars: dict[tuple[str, str], dict], trade_date: str, code: str) -> dict:
    try:
        return bars[(trade_date, code)]
    except KeyError as exc:
        raise KeyError(f"missing_bar:{trade_date}:{code}") from exc
