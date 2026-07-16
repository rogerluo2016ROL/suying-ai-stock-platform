import pytest

from kronos_factors.backtest.portfolio_v2 import EntryOrder, simulate_portfolio


def _bars(dates, prices, *, factors=None):
    out = {}
    factors = factors or {}
    for trade_date in dates:
        for code, value in prices.items():
            close = value[trade_date]
            bar = {
                "open": close,
                "high": close,
                "low": close,
                "close": close,
            }
            if code in factors and trade_date in factors[code]:
                if factors[code][trade_date] is not _MISSING:
                    bar["adj_factor"] = factors[code][trade_date]
            else:
                bar["adj_factor"] = 1.0
            out[(trade_date, code)] = bar
    return out


class _MissingFactor:
    pass


_MISSING = _MissingFactor()


def _order(code, entry_date, exit_date=None, exit_price=None, regime="bull", weight=1.0):
    return EntryOrder(
        signal_date="2026-01-01",
        entry_date=entry_date,
        code=code,
        regime=regime,
        weight=weight,
        exit_date=exit_date,
        exit_price=exit_price,
        exit_reason="hold_to_maturity" if exit_date else None,
    )


def test_bull_opening_cap_and_single_stock_cap():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(
        dates,
        {
            "000001": {d: 100.0 for d in dates},
            "000002": {d: 100.0 for d in dates},
        },
    )
    orders = [
        _order("000001", "2026-01-02", "2026-01-05", 100.0),
        _order("000002", "2026-01-02", "2026-01-05", 100.0),
    ]

    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)

    assert result.trades[0]["buy_notional"] <= 150_000
    assert result.trades[1]["buy_notional"] <= 150_000
    assert sum(t["buy_notional"] for t in result.trades) <= 500_000


def test_daily_limit_executes_at_most_two_new_positions():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(
        dates,
        {
            "000001": {d: 100.0 for d in dates},
            "000002": {d: 100.0 for d in dates},
            "000003": {d: 100.0 for d in dates},
        },
    )
    orders = [
        _order("000001", "2026-01-02", "2026-01-05", 100.0),
        _order("000002", "2026-01-02", "2026-01-05", 100.0),
        _order("000003", "2026-01-02", "2026-01-05", 100.0),
    ]

    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)

    assert [trade["code"] for trade in result.trades] == ["000001", "000002"]


def test_neutral_cap_subtracts_old_positions_at_open():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    bars = _bars(
        dates,
        {
            "000001": {d: 100.0 for d in dates},
            "000002": {d: 100.0 for d in dates},
        },
    )
    orders = [
        _order("000001", "2026-01-02", "2026-01-07", 100.0, "neutral"),
        _order("000002", "2026-01-06", "2026-01-07", 100.0, "neutral"),
    ]

    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)
    day_two = next(point for point in result.equity_curve if point["date"] == "2026-01-06")
    second_trade = next(trade for trade in result.trades if trade["code"] == "000002")

    assert day_two["gross_exposure"] <= day_two["equity_open"] * 0.30 + 0.01
    assert second_trade["buy_notional"] <= 150_000


def test_round_trip_cost_is_fourteen_basis_points_split_across_buy_and_sell():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(dates, {"000001": {d: 100.0 for d in dates}})

    result = simulate_portfolio(
        [_order("000001", "2026-01-02", "2026-01-05", 100.0)],
        bars,
        1_000_000,
        14.0,
    )

    assert result.trades[0]["buy_cost"] == pytest.approx(105.0)
    assert result.trades[0]["sell_cost"] == pytest.approx(105.0)
    assert result.trades[0]["net_return_pct"] == pytest.approx(-0.14, abs=0.001)


def test_close_equity_marks_open_positions_to_market_and_excludes_unrealized_from_win_rate():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    bars = _bars(
        dates,
        {
            "000001": {
                "2026-01-02": 100.0,
                "2026-01-05": 105.0,
                "2026-01-06": 110.0,
            }
        },
    )

    result = simulate_portfolio(
        [_order("000001", "2026-01-02")],
        bars,
        1_000_000,
        14.0,
    )

    point = next(p for p in result.equity_curve if p["date"] == "2026-01-06")
    assert point["equity_close"] > point["cash"] + point["position_cost"]
    assert result.summary["total_trades"] == 0
    assert result.summary["win_rate_pct"] == 0.0


def test_open_orders_are_processed_before_same_day_close_exits():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    bars = _bars(
        dates,
        {
            "000001": {d: 100.0 for d in dates},
            "000002": {d: 100.0 for d in dates},
        },
    )
    orders = [
        _order("000001", "2026-01-02", "2026-01-06", 100.0, "neutral"),
        _order("000002", "2026-01-06", "2026-01-07", 100.0, "neutral"),
    ]

    result = simulate_portfolio(orders, bars, 1_000_000, 14.0)
    new_trade = next(t for t in result.trades if t["code"] == "000002")

    assert new_trade["buy_notional"] <= 150_000


def test_monthly_returns_use_month_end_equity_chain():
    dates = ["2026-01-30", "2026-01-31", "2026-02-28"]
    bars = _bars(
        dates,
        {
            "000001": {
                "2026-01-30": 100.0,
                "2026-01-31": 110.0,
                "2026-02-28": 120.0,
            }
        },
    )

    result = simulate_portfolio(
        [_order("000001", "2026-01-30", "2026-02-28", 120.0)],
        bars,
        1_000_000,
        14.0,
    )

    assert result.summary["monthly_returns"]["2026-01"] == pytest.approx(1.4895, abs=1e-4)
    assert result.summary["monthly_returns"]["2026-02"] == pytest.approx(1.46557033, abs=1e-6)


def test_max_drawdown_uses_daily_close_equity():
    dates = ["2026-01-30", "2026-01-31", "2026-02-03", "2026-02-04"]
    bars = _bars(
        dates,
        {
            "000001": {
                "2026-01-30": 100.0,
                "2026-01-31": 110.0,
                "2026-02-03": 90.0,
                "2026-02-04": 95.0,
            }
        },
    )

    result = simulate_portfolio(
        [_order("000001", "2026-01-30", "2026-02-04", 95.0)],
        bars,
        1_000_000,
        14.0,
    )

    expected_drawdown = (984_895.0 / 1_014_895.0 - 1.0) * 100.0
    assert result.summary["max_drawdown_pct"] == pytest.approx(expected_drawdown, abs=1e-6)


def test_missing_adj_factor_raises_error():
    dates = ["2026-01-02", "2026-01-05"]
    bars = _bars(
        dates,
        {"000001": {d: 100.0 for d in dates}},
        factors={"000001": {"2026-01-02": _MISSING}},
    )

    with pytest.raises(ValueError, match="adj_factor_missing"):
        simulate_portfolio(
            [_order("000001", "2026-01-02", "2026-01-05", 100.0)],
            bars,
            1_000_000,
            14.0,
        )
